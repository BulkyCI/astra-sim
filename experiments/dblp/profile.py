"""Separate DBLP profile projection onto the existing ns-3 backend."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from experiments.ring_3d.generate import (
    Profile as WorkloadProfile,
)
from experiments.ring_3d.generate import (
    materialize as materialize_ring_3d,
)
from experiments.ring_3d.generate import (
    parse_profile_document,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PROFILE_KEYS = {
    "schema_version",
    "name",
    "base_workload_profile",
    "loss_source",
    "transport_recovery",
    "completion_contract",
    "expectation",
}
_EXPECTATION_KEYS = {
    "terminal_outcome",
    "minimum_data_injected_drops",
    "maximum_natural_buffer_drops",
}


class TerminalExpectation(str, Enum):
    """The closed set of terminal outcomes a DBLP profile may require."""

    Completed = "completed"
    TransportFailure = "transport_failure"


@dataclass(frozen=True)
class DblpExpectation:
    """Native-run requirements for one configured loss source."""

    terminal_outcome: TerminalExpectation
    minimum_data_injected_drops: int
    maximum_natural_buffer_drops: int


@dataclass(frozen=True)
class DblpProfile:
    """A validated DBLP profile and its shared-backend projection."""

    path: Path
    name: str
    base_workload_profile: Path
    completion_contract: str
    expectation: DblpExpectation
    workload: WorkloadProfile
    projected_workload_document: dict[str, Any]


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            document = json.load(handle)
    except OSError as error:
        raise ValueError(f"unable to read {description}: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {description}: {path}") from error
    if not isinstance(document, dict):
        raise ValueError(f"{description} must be a JSON object")
    return document


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _positive_int(value: Any, field: str) -> int:
    parsed = _nonnegative_int(value, field)
    if parsed == 0:
        raise ValueError(f"{field} must be a positive integer")
    return parsed


def _resolve_base_profile(value: Any, profile_path: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("base_workload_profile must be a nonempty path")
    candidate = Path(value)
    base_path = (
        (profile_path.parent / candidate).resolve()
        if not candidate.is_absolute()
        else candidate.resolve()
    )
    try:
        base_path.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise ValueError(
            "base_workload_profile must remain inside the repository"
        ) from error
    if base_path.suffix != ".json" or not base_path.is_file():
        raise ValueError("base_workload_profile must name an existing JSON profile")
    return base_path


def _parse_expectation(value: Any) -> DblpExpectation:
    if not isinstance(value, dict) or set(value) != _EXPECTATION_KEYS:
        raise ValueError(
            f"expectation must contain exactly {sorted(_EXPECTATION_KEYS)}"
        )
    try:
        terminal_outcome = TerminalExpectation(value["terminal_outcome"])
    except (TypeError, ValueError) as error:
        raise ValueError(
            "expectation.terminal_outcome must be completed or transport_failure"
        ) from error
    return DblpExpectation(
        terminal_outcome=terminal_outcome,
        minimum_data_injected_drops=_positive_int(
            value["minimum_data_injected_drops"],
            "expectation.minimum_data_injected_drops",
        ),
        maximum_natural_buffer_drops=_nonnegative_int(
            value["maximum_natural_buffer_drops"],
            "expectation.maximum_natural_buffer_drops",
        ),
    )


def _project_workload_document(
    base_document: dict[str, Any],
    name: str,
    loss_source: Any,
    transport_recovery: Any,
) -> dict[str, Any]:
    if not isinstance(loss_source, dict) or loss_source.get("kind") != "injected_data":
        raise ValueError("loss_source.kind must be injected_data")
    network = base_document.get("network")
    if not isinstance(network, dict):
        raise ValueError("base_workload_profile.network must be an object")
    if any(
        key in network for key in ("data_loss", "transport_recovery", "packet_trimming")
    ):
        raise ValueError(
            "base_workload_profile must not configure loss, recovery, or trimming"
        )
    if base_document.get("microburst_enabled", True):
        raise ValueError(
            "base_workload_profile must disable microbursts so injected loss is the only impairment source"
        )

    projected = json.loads(json.dumps(base_document))
    projected["name"] = name
    projected["microburst_enabled"] = False
    data_loss = dict(loss_source)
    data_loss.pop("kind")
    projected["network"]["data_loss"] = data_loss
    projected["network"]["transport_recovery"] = transport_recovery
    return projected


def load_dblp_profile(profile_path: Path) -> DblpProfile:
    """Parse a DBLP profile through the shared Ring-3D network validator."""
    resolved_path = profile_path.resolve()
    document = _load_json(resolved_path, "DBLP profile")
    unknown = set(document) - _PROFILE_KEYS
    missing = _PROFILE_KEYS - set(document)
    if unknown or missing:
        raise ValueError(
            "DBLP profile keys do not match the schema "
            f"(unknown={sorted(unknown)}, missing={sorted(missing)})"
        )
    if document["schema_version"] != 1:
        raise ValueError("DBLP profile schema_version must be 1")
    name = document["name"]
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a nonempty string")
    completion_contract = document["completion_contract"]
    if completion_contract != "reliable_full_delivery":
        raise ValueError("completion_contract must be reliable_full_delivery")

    base_workload_profile = _resolve_base_profile(
        document["base_workload_profile"], resolved_path
    )
    projected_document = _project_workload_document(
        _load_json(base_workload_profile, "base_workload_profile"),
        name,
        document["loss_source"],
        document["transport_recovery"],
    )
    return DblpProfile(
        path=resolved_path,
        name=name,
        base_workload_profile=base_workload_profile,
        completion_contract=completion_contract,
        expectation=_parse_expectation(document["expectation"]),
        workload=parse_profile_document(projected_document),
        projected_workload_document=projected_document,
    )


def _disabled_experiment_config(profile: DblpProfile) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "enabled": False,
        "seed": profile.workload.seed,
        "run_id": profile.name,
        "default_priority_group": 3,
        "vnet_to_priority_group": {"0": 3},
        "microburst": {"enabled": False},
    }


def materialize_dblp_profile(
    profile_path: Path,
    output_dir: Path,
    clean: bool = False,
) -> tuple[DblpProfile, dict[str, Any]]:
    """Materialize a separate DBLP profile through the shared native backend."""
    profile = load_dblp_profile(profile_path)
    if output_dir.exists() and clean:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    resolved_workload_profile = output_dir / "resolved_workload_profile.json"
    resolved_workload_profile.write_text(
        json.dumps(profile.projected_workload_document, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = materialize_ring_3d(resolved_workload_profile, output_dir, clean=False)
    (output_dir / "dblp_profile.json").write_text(
        profile.path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (output_dir / "experiment.json").write_text(
        json.dumps(_disabled_experiment_config(profile), indent=2) + "\n",
        encoding="utf-8",
    )

    manifest.update(
        {
            "profile": profile.name,
            "profile_config": str((output_dir / "dblp_profile.json").resolve()),
            "dblp_profile": str((output_dir / "dblp_profile.json").resolve()),
            "base_workload_profile": str(profile.base_workload_profile),
            "resolved_workload_profile": str(resolved_workload_profile.resolve()),
            "selection_policy": {"semantics": "disabled"},
            "microburst": {"enabled": False},
            "dblp_transport": {
                "loss_source": "injected_data",
                "completion_contract": profile.completion_contract,
                "residual_loss_tolerance": "not_modeled",
                "queue_loss_treatment": "guard_only",
            },
            "expectation": {
                "terminal_outcome": profile.expectation.terminal_outcome.value,
                "minimum_data_injected_drops": (
                    profile.expectation.minimum_data_injected_drops
                ),
                "maximum_natural_buffer_drops": (
                    profile.expectation.maximum_natural_buffer_drops
                ),
            },
        }
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return profile, manifest
