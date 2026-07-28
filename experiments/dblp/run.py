#!/usr/bin/env python3
"""Materialize and execute one separate DBLP injected-loss profile."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.dblp.profile import (
    DblpProfile,
    TerminalExpectation,
    materialize_dblp_profile,
)
from experiments.ring_3d.analyze import summarize
from experiments.ring_3d.run import find_default_binary


def _transport_observability(summary: dict[str, Any]) -> dict[str, Any]:
    try:
        transport = summary["ns3_observability"]["transport"]
    except KeyError as error:
        raise ValueError("native DBLP run did not retain transport telemetry") from error
    if transport.get("status") != "available":
        raise ValueError("native DBLP run did not retain transport telemetry")
    return transport


def validate_execution(
    profile: DblpProfile, returncode: int, summary: dict[str, Any]
) -> None:
    """Validate terminal and single-loss-source invariants from native telemetry."""
    if profile.expectation.terminal_outcome is TerminalExpectation.Completed:
        if returncode != 0:
            raise ValueError("DBLP profile expected completion but the simulator failed")
        if summary.get("failed_flow_count") != 0:
            raise ValueError("completed DBLP profile retained failed transport flows")
    else:
        if returncode == 0:
            raise ValueError("DBLP profile expected transport failure but completed")
        if int(summary.get("failed_flow_count", 0)) == 0:
            raise ValueError("DBLP transport failure retained no failed flow telemetry")

    transport = _transport_observability(summary)
    injected_data_drops = int(transport.get("data_injected_drop_count", 0))
    if injected_data_drops < profile.expectation.minimum_data_injected_drops:
        raise ValueError("DBLP profile did not observe the required injected data loss")
    if int(transport.get("control_injected_drop_count", -1)) != 0:
        raise ValueError("configured DBLP data loss impaired control traffic")
    natural_buffer_drops = (
        int(transport.get("data_natural_buffer_drop_count", 0))
        + int(transport.get("control_natural_buffer_drop_count", 0))
        + int(transport.get("event_counts", {}).get("qbb_drop", 0))
    )
    if natural_buffer_drops > profile.expectation.maximum_natural_buffer_drops:
        raise ValueError("DBLP profile mixed injected loss with natural buffer loss")


def run_dblp_profile(
    profile_path: Path,
    output_dir: Path,
    *,
    binary: Path | None = None,
    clean: bool = False,
    ns3_rng_seed: int = 1,
    ns3_rng_run: int = 1,
    simulation_timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Run the shared ns-3 backend with a separate validated DBLP profile."""
    if ns3_rng_seed <= 0 or ns3_rng_run <= 0:
        raise ValueError("ns3_rng_seed and ns3_rng_run must be positive")
    if simulation_timeout_seconds is not None and simulation_timeout_seconds <= 0:
        raise ValueError("simulation_timeout_seconds must be positive when set")

    output_dir = output_dir.resolve()
    profile, manifest = materialize_dblp_profile(profile_path, output_dir, clean)
    executable = binary.resolve() if binary else find_default_binary()
    if not executable.is_file() or not executable.stat().st_mode & 0o111:
        raise FileNotFoundError(
            f"ns-3 executable is unavailable or not executable: {executable}"
        )

    command = [
        str(executable),
        f"--workload-configuration={manifest['workload_prefix']}",
        f"--system-configuration={manifest['system_config']}",
        f"--network-configuration={manifest['network_config']}",
        f"--remote-memory-configuration={manifest['remote_memory_config']}",
        f"--logical-topology-configuration={manifest['logical_topology']}",
        f"--comm-group-configuration={manifest['communicator_groups']}",
        f"--experiment-configuration={manifest['experiment_config']}",
        f"--clr-mask-configuration={manifest['clr_mask']}",
        f"--experiment-output-dir={manifest['telemetry_dir']}",
        f"--ns3-rng-seed={ns3_rng_seed}",
        f"--ns3-rng-run={ns3_rng_run}",
    ]
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        timeout=simulation_timeout_seconds,
    )
    summary = summarize(
        Path(manifest["telemetry_dir"]),
        output_dir / "ns3" / "fct.txt",
        output_dir / "ns3",
        (
            profile.workload.ranks
            if profile.expectation.terminal_outcome is TerminalExpectation.Completed
            else None
        ),
    )
    validate_execution(profile, result.returncode, summary)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    execution = {
        "ns3_rng_seed": ns3_rng_seed,
        "ns3_rng_run": ns3_rng_run,
        "simulation_timeout_seconds": simulation_timeout_seconds,
        "native_returncode": result.returncode,
    }
    manifest["execution"] = execution
    (output_dir / "execution.json").write_text(
        json.dumps(execution, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--ns3-rng-seed", type=int, default=1)
    parser.add_argument("--ns3-rng-run", type=int, default=1)
    parser.add_argument("--simulation-timeout-seconds", type=int)
    arguments = parser.parse_args()
    manifest = run_dblp_profile(
        arguments.profile,
        arguments.output,
        binary=arguments.binary,
        clean=arguments.clean,
        ns3_rng_seed=arguments.ns3_rng_seed,
        ns3_rng_run=arguments.ns3_rng_run,
        simulation_timeout_seconds=arguments.simulation_timeout_seconds,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
