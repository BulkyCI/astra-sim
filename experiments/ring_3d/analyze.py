#!/usr/bin/env python3
"""Validate and summarize telemetry emitted by the 3D Ring experiment."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _as_int(row: dict[str, str], key: str) -> int:
    try:
        return int(row[key])
    except (KeyError, ValueError) as error:
        raise ValueError(f"invalid integer field {key!r} in telemetry") from error


def _as_bool(row: dict[str, str], key: str) -> bool:
    value = row.get(key)
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"invalid boolean field {key!r} in telemetry")


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"missing telemetry file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summarize(telemetry_dir: Path) -> dict[str, Any]:
    flow_rows = load_csv(telemetry_dir / "flow_events.csv")
    completion_rows = load_csv(telemetry_dir / "rank_completion.csv")

    total_logical_bytes = sum(_as_int(row, "logical_bytes") for row in flow_rows)
    total_physical_bytes = sum(_as_int(row, "physical_bytes") for row in flow_rows)
    shed_rows = [row for row in flow_rows if row.get("decision") == "shed"]
    invalid_sheds = [
        row
        for row in shed_rows
        if not (
            _as_bool(row, "admission_eligible")
            and row.get("flow_kind") == "provenance_control"
            and row.get("parallelism_domain") == "dp"
            and row.get("origin_transport_role") == "collective_payload"
            and row.get("collective_type") == "all_reduce"
            and row.get("transport_role") == "provenance_control"
        )
    ]
    if invalid_sheds:
        raise ValueError("shedding policy affected a flow outside DP All-Reduce payloads")

    invalid_provenance = [
        row
        for row in flow_rows
        if row.get("flow_kind") == "provenance_control"
        and _as_int(row, "physical_bytes") <= 0
    ]
    if invalid_provenance:
        raise ValueError("provenance control flow must carry nonzero physical bytes")

    by_step: dict[str, dict[str, int]] = defaultdict(
        lambda: {"flows": 0, "shed_flows": 0, "logical_bytes": 0, "physical_bytes": 0}
    )
    for row in flow_rows:
        step = row.get("training_step", "unknown")
        bucket = by_step[step]
        bucket["flows"] += 1
        bucket["shed_flows"] += row.get("decision") == "shed"
        bucket["logical_bytes"] += _as_int(row, "logical_bytes")
        bucket["physical_bytes"] += _as_int(row, "physical_bytes")

    completion_times = [_as_int(row, "completion_time_ns") for row in completion_rows]
    return {
        "flow_count": len(flow_rows),
        "shed_flow_count": len(shed_rows),
        "total_logical_bytes": total_logical_bytes,
        "total_physical_bytes": total_physical_bytes,
        "shed_logical_bytes": sum(_as_int(row, "logical_bytes") for row in shed_rows),
        "completion_rank_count": len(completion_rows),
        "completion_time_ns_max": max(completion_times, default=0),
        "by_training_step": dict(sorted(by_step.items(), key=lambda entry: int(entry[0]))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="write the JSON summary to this path")
    arguments = parser.parse_args()
    summary = summarize(arguments.telemetry_dir.resolve())
    encoded = json.dumps(summary, indent=2) + "\n"
    if arguments.output is None:
        print(encoded, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())