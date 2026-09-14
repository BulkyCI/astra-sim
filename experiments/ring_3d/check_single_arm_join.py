#!/usr/bin/env python3
"""Assert a single run.py arm reproduces compare.py's recovery arm.

The FORGIVE v2 variants run as single-arm records joined at the seed against
the v1 wave's comparison arms. That join is valid only if a single arm and a
comparison arm at the same profile and seed are the same simulation. Both
derive the DBLP selection seed and the ns-3 run number from the seed the same
way, so this reads the claim back off two materialized runs instead of
arguing it from the code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# One estimand per question the variants are read on: how long training took,
# how much gradient the receiver forgave, and how much the fabric trimmed.
ESTIMANDS: dict[str, tuple[str, ...]] = {
    "training_window_ns": ("rank_completion_time_ns", "max_ns"),
    "dp_all_reduce_span_p99_ns": (
        "collective_completion",
        "all_rank_operation_span_ns",
        "by_parallelism_domain_and_collective_type",
        "dp",
        "all_reduce",
        "p99_ns",
    ),
    "forgiven_bytes": ("forgiveness", "forgiven_bytes"),
    "forgiven_range_count": ("forgiveness", "forgiven_range_count"),
    "trim_notification_count": ("transport_recovery", "trim_notification_count"),
    "trimmed_payload_bytes": ("transport_recovery", "trimmed_payload_bytes"),
}


def _summary(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))


def _estimand(summary: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = summary
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"summary is missing {'/'.join(path)}")
        value = value[key]
    return value


def check(single: Path, comparison_arm: Path) -> list[str]:
    """Return every estimand the two runs disagree on."""
    left = _summary(single)
    right = _summary(comparison_arm)
    failures = [
        f"{name}: single arm {_estimand(left, path)}, comparison arm "
        f"{_estimand(right, path)}"
        for name, path in ESTIMANDS.items()
        if _estimand(left, path) != _estimand(right, path)
    ]
    # The same simulation writes the same rows, so the flow telemetry is the
    # decisive check and the estimands above name which one moved when it is
    # not. The manifests differ by output path and are excluded on purpose.
    single_rows = (single / "telemetry" / "flow_events.csv").read_bytes()
    comparison_rows = (
        comparison_arm / "telemetry" / "flow_events.csv"
    ).read_bytes()
    if single_rows != comparison_rows:
        failures.append(
            "the single arm and the comparison arm disagree on flow telemetry"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--single", type=Path, required=True)
    parser.add_argument("--comparison-arm", type=Path, required=True)
    arguments = parser.parse_args()
    failures = check(
        arguments.single.resolve(), arguments.comparison_arm.resolve()
    )
    if failures:
        for failure in failures:
            print(f"single-arm join failed: {failure}")
        return 1
    summary = _summary(arguments.single.resolve())
    print(
        "single-arm join holds: training window "
        f"{_estimand(summary, ESTIMANDS['training_window_ns'])} ns, "
        f"{_estimand(summary, ESTIMANDS['forgiven_bytes'])} B forgiven over "
        f"{_estimand(summary, ESTIMANDS['trim_notification_count'])} trims"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
