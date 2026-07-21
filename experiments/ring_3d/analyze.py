#!/usr/bin/env python3
"""Validate and summarize telemetry emitted by the 3D Ring experiment."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from math import ceil
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


def _training_step_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _timing_statistics(values: list[int]) -> dict[str, int | None]:
    """Return nearest-rank latency quantiles in nanoseconds."""
    if not values:
        return {
            "count": 0,
            "min_ns": None,
            "p50_ns": None,
            "p95_ns": None,
            "p99_ns": None,
            "max_ns": None,
        }
    ordered = sorted(values)

    def percentile(percent: int) -> int:
        return ordered[ceil(len(ordered) * percent / 100) - 1]

    return {
        "count": len(ordered),
        "min_ns": ordered[0],
        "p50_ns": percentile(50),
        "p95_ns": percentile(95),
        "p99_ns": percentile(99),
        "max_ns": ordered[-1],
    }


def _flow_duration_ns(row: dict[str, str]) -> int:
    duration = _as_int(row, "end_time_ns") - _as_int(row, "start_time_ns")
    if duration < 0:
        raise ValueError("flow completion time must not be negative")
    return duration


def _timing_by_field(
    flow_rows: list[dict[str, str]], field: str
) -> dict[str, dict[str, int | None]]:
    durations: dict[str, list[int]] = defaultdict(list)
    for row in flow_rows:
        durations[row.get(field) or "unknown"].append(_flow_duration_ns(row))
    return {
        name: _timing_statistics(values)
        for name, values in sorted(durations.items(), key=lambda entry: entry[0])
    }


def _timing_by_domain_and_kind(
    flow_rows: list[dict[str, str]],
) -> dict[str, dict[str, dict[str, int | None]]]:
    durations: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for row in flow_rows:
        domain = row.get("parallelism_domain") or "unknown"
        kind = row.get("flow_kind") or "unknown"
        durations[domain][kind].append(_flow_duration_ns(row))
    return {
        domain: {
            kind: _timing_statistics(values)
            for kind, values in sorted(kinds.items(), key=lambda entry: entry[0])
        }
        for domain, kinds in sorted(durations.items(), key=lambda entry: entry[0])
    }


def _flow_key(row: dict[str, str]) -> tuple[int, int, int]:
    return (
        _as_int(row, "src"),
        _as_int(row, "dst"),
        _as_int(row, "source_port"),
    )


def _fct_node_id(encoded_address: str) -> int:
    try:
        address = int(encoded_address, 16)
    except ValueError as error:
        raise ValueError(f"invalid FCT address: {encoded_address!r}") from error
    return (address >> 8) & 0xFFFF


def _load_fct_records(path: Path) -> dict[tuple[int, int, int], dict[str, int]]:
    records: dict[tuple[int, int, int], dict[str, int]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fields = line.split()
        if len(fields) != 8:
            raise ValueError(f"invalid FCT record at {path}:{line_number}")
        source, destination, source_port, _destination_port, size, start, duration, standalone = fields
        key = (_fct_node_id(source), _fct_node_id(destination), int(source_port))
        if key in records:
            raise ValueError("FCT records contain a duplicate flow key")
        try:
            records[key] = {
                "physical_bytes": int(size),
                "start_time_ns": int(start),
                "duration_ns": int(duration),
                "standalone_fct_ns": int(standalone),
            }
        except ValueError as error:
            raise ValueError(f"invalid numeric FCT record at {path}:{line_number}") from error
    return records


def _verify_fct_join(
    flow_rows: list[dict[str, str]], fct_path: Path
) -> dict[str, int | str]:
    if not fct_path.is_file():
        return {"status": "not_available"}
    records = _load_fct_records(fct_path)
    telemetry = {_flow_key(row): row for row in flow_rows}
    if len(telemetry) != len(flow_rows):
        raise ValueError("flow telemetry contains a duplicate flow key")
    missing = set(telemetry) - set(records)
    extra = set(records) - set(telemetry)
    if missing or extra:
        raise ValueError(
            "telemetry/FCT join is incomplete "
            f"(missing={len(missing)}, extra={len(extra)})"
        )
    for key, row in telemetry.items():
        record = records[key]
        if _as_int(row, "physical_bytes") != record["physical_bytes"]:
            raise ValueError("telemetry/FCT physical-byte mismatch")
        if _as_int(row, "start_time_ns") != record["start_time_ns"]:
            raise ValueError("telemetry/FCT start-time mismatch")
        if _flow_duration_ns(row) != record["duration_ns"]:
            raise ValueError("telemetry/FCT duration mismatch")
    return {
        "status": "verified",
        "telemetry_flow_count": len(telemetry),
        "fct_record_count": len(records),
    }


def _summarize_ns3_observability(ns3_dir: Path) -> dict[str, dict[str, int | str]]:
    queue_path = ns3_dir / "qlen.txt"
    if queue_path.is_file():
        queue_rows = 0
        queues: set[tuple[int, int]] = set()
        max_queue_bytes = 0
        for line_number, line in enumerate(
            queue_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            fields = line.split()
            if not fields:
                continue
            if len(fields) < 6 or fields[0] != "time" or (len(fields) - 3) % 3:
                raise ValueError(f"invalid queue telemetry at {queue_path}:{line_number}")
            try:
                switch = int(fields[2])
                for index in range(3, len(fields), 3):
                    if fields[index] != "j":
                        raise ValueError
                    port = int(fields[index + 1])
                    queue_bytes = int(fields[index + 2])
                    if queue_bytes < 0:
                        raise ValueError
                    queues.add((switch, port))
                    max_queue_bytes = max(max_queue_bytes, queue_bytes)
            except ValueError as error:
                raise ValueError(
                    f"invalid queue telemetry at {queue_path}:{line_number}"
                ) from error
            queue_rows += 1
        queue = {
            "status": "available",
            "sample_count": queue_rows,
            "observed_queue_count": len(queues),
            "max_queue_bytes": max_queue_bytes,
        }
    else:
        queue = {"status": "not_available"}

    pfc_path = ns3_dir / "pfc.txt"
    if pfc_path.is_file():
        pfc = {
            "status": "available",
            "event_count": sum(
                bool(line.strip())
                for line in pfc_path.read_text(encoding="utf-8").splitlines()
            ),
        }
    else:
        pfc = {"status": "not_available"}
    return {"queue": queue, "pfc": pfc}


def summarize(
    telemetry_dir: Path,
    fct_path: Path | None = None,
    ns3_dir: Path | None = None,
) -> dict[str, Any]:
    telemetry_dir = telemetry_dir.resolve()
    flow_rows = load_csv(telemetry_dir / "flow_events.csv")
    completion_rows = load_csv(telemetry_dir / "rank_completion.csv")
    if fct_path is None:
        fct_path = telemetry_dir.parent / "ns3" / "fct.txt"
    if ns3_dir is None:
        ns3_dir = telemetry_dir.parent / "ns3"

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
    flow_completion = _timing_statistics([_flow_duration_ns(row) for row in flow_rows])
    rank_completion = _timing_statistics(completion_times)
    return {
        "flow_count": len(flow_rows),
        "shed_flow_count": len(shed_rows),
        "total_logical_bytes": total_logical_bytes,
        "total_physical_bytes": total_physical_bytes,
        "shed_logical_bytes": sum(_as_int(row, "logical_bytes") for row in shed_rows),
        "completion_rank_count": len(completion_rows),
        "completion_time_ns_max": rank_completion["max_ns"] or 0,
        "rank_completion_time_ns": rank_completion,
        "flow_completion_time_ns": {
            "all": flow_completion,
            "by_training_step": _timing_by_field(flow_rows, "training_step"),
            "by_parallelism_domain": _timing_by_field(
                flow_rows, "parallelism_domain"
            ),
            "by_flow_kind": _timing_by_field(flow_rows, "flow_kind"),
            "by_parallelism_domain_and_flow_kind": _timing_by_domain_and_kind(
                flow_rows
            ),
        },
        "fct_join": _verify_fct_join(flow_rows, fct_path.resolve()),
        "ns3_observability": _summarize_ns3_observability(ns3_dir.resolve()),
        "by_training_step": dict(
            sorted(by_step.items(), key=lambda entry: _training_step_sort_key(entry[0]))
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry-dir", type=Path, required=True)
    parser.add_argument(
        "--fct-file",
        type=Path,
        help="ns-3 FCT output to join and verify; defaults to ../ns3/fct.txt",
    )
    parser.add_argument(
        "--ns3-dir",
        type=Path,
        help="directory containing ns-3 queue and PFC output; defaults to ../ns3",
    )
    parser.add_argument("--output", type=Path, help="write the JSON summary to this path")
    arguments = parser.parse_args()
    summary = summarize(
        arguments.telemetry_dir.resolve(),
        arguments.fct_file.resolve() if arguments.fct_file else None,
        arguments.ns3_dir.resolve() if arguments.ns3_dir else None,
    )
    encoded = json.dumps(summary, indent=2) + "\n"
    if arguments.output is None:
        print(encoded, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())