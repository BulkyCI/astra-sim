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


def _terminal_outcome(row: dict[str, str]) -> str:
    """Read the explicit terminal outcome for an issued transport flow."""
    outcome = row.get("terminal_outcome")
    if outcome not in {"completed", "failed"}:
        raise ValueError(f"invalid terminal outcome {outcome!r} in telemetry")
    return outcome


def _optional_nonnegative_int(row: dict[str, str], key: str) -> int:
    value = row.get(key)
    if value is None or value == "":
        return 0
    parsed = _as_int(row, key)
    if parsed < 0:
        raise ValueError(f"telemetry field {key!r} must be nonnegative")
    return parsed


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"missing telemetry file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_optional_csv(path: Path) -> list[dict[str, str]] | None:
    return load_csv(path) if path.is_file() else None


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


def _summarize_rank_completions(
    completion_rows: list[dict[str, str]], expected_rank_count: int | None
) -> dict[str, int | str]:
    seen_ranks: set[int] = set()
    for row in completion_rows:
        rank = _as_int(row, "rank")
        completion_time_ns = _as_int(row, "completion_time_ns")
        if rank < 0 or completion_time_ns < 0:
            raise ValueError("rank completion telemetry must be nonnegative")
        if rank in seen_ranks:
            raise ValueError("rank completion telemetry contains a duplicate rank")
        seen_ranks.add(rank)

    result: dict[str, int | str] = {
        "status": "not_checked" if expected_rank_count is None else "verified",
        "recorded_rank_count": len(seen_ranks),
    }
    if expected_rank_count is not None:
        if expected_rank_count <= 0:
            raise ValueError("expected rank count must be positive")
        if seen_ranks != set(range(expected_rank_count)):
            raise ValueError(
                "rank completion telemetry does not cover every expected rank"
            )
        result["expected_rank_count"] = expected_rank_count
    return result


def _collective_duration_ns(row: dict[str, str]) -> int:
    duration = _as_int(row, "end_time_ns") - _as_int(row, "start_time_ns")
    if duration < 0:
        raise ValueError("collective completion time must not be negative")
    return duration


def _summarize_collectives(
    collective_rows: list[dict[str, str]] | None,
) -> dict[str, Any]:
    if collective_rows is None:
        return {"status": "not_available"}

    per_rank_durations: list[int] = []
    per_rank_by_domain: dict[str, list[int]] = defaultdict(list)
    per_rank_by_domain_and_type: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    operations: dict[tuple[str, str, int, int], list[dict[str, str]]] = defaultdict(
        list
    )
    seen_rank_events: set[tuple[str, str, int, int, int]] = set()

    for row in collective_rows:
        domain = row.get("parallelism_domain") or "unknown"
        collective_type = row.get("collective_type") or "unknown"
        training_step = _as_int(row, "training_step")
        node_id = _as_int(row, "workload_node_id")
        rank = _as_int(row, "rank")
        if rank < 0 or _as_int(row, "logical_bytes") < 0:
            raise ValueError(
                "collective telemetry rank and logical bytes must be nonnegative"
            )
        duration = _collective_duration_ns(row)
        event_key = (domain, collective_type, training_step, node_id, rank)
        if event_key in seen_rank_events:
            raise ValueError(
                "collective telemetry contains a duplicate rank completion"
            )
        seen_rank_events.add(event_key)
        per_rank_durations.append(duration)
        per_rank_by_domain[domain].append(duration)
        per_rank_by_domain_and_type[domain][collective_type].append(duration)
        operations[(domain, collective_type, training_step, node_id)].append(row)

    operation_spans: list[int] = []
    operation_spans_by_domain: dict[str, list[int]] = defaultdict(list)
    operation_spans_by_domain_and_type: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    operation_spans_by_step: dict[str, list[int]] = defaultdict(list)
    rank_counts: list[int] = []
    for (domain, collective_type, training_step, _node_id), rows in operations.items():
        start_time_ns = min(_as_int(row, "start_time_ns") for row in rows)
        end_time_ns = max(_as_int(row, "end_time_ns") for row in rows)
        span = end_time_ns - start_time_ns
        operation_spans.append(span)
        operation_spans_by_domain[domain].append(span)
        operation_spans_by_domain_and_type[domain][collective_type].append(span)
        operation_spans_by_step[str(training_step)].append(span)
        rank_counts.append(len(rows))

    def by_domain_and_type(
        durations: dict[str, dict[str, list[int]]],
    ) -> dict[str, dict[str, dict[str, int | None]]]:
        return {
            domain: {
                collective_type: _timing_statistics(values)
                for collective_type, values in sorted(types.items())
            }
            for domain, types in sorted(durations.items())
        }

    return {
        "status": "available",
        "rank_event_count": len(collective_rows),
        "logical_collective_count": len(operations),
        "operation_rank_count": _timing_statistics(rank_counts),
        "per_rank_completion_time_ns": {
            "all": _timing_statistics(per_rank_durations),
            "by_parallelism_domain": {
                domain: _timing_statistics(values)
                for domain, values in sorted(per_rank_by_domain.items())
            },
            "by_parallelism_domain_and_collective_type": by_domain_and_type(
                per_rank_by_domain_and_type
            ),
        },
        "all_rank_operation_span_ns": {
            "all": _timing_statistics(operation_spans),
            "by_parallelism_domain": {
                domain: _timing_statistics(values)
                for domain, values in sorted(operation_spans_by_domain.items())
            },
            "by_parallelism_domain_and_collective_type": by_domain_and_type(
                operation_spans_by_domain_and_type
            ),
            "by_training_step": {
                step: _timing_statistics(values)
                for step, values in sorted(
                    operation_spans_by_step.items(),
                    key=lambda entry: _training_step_sort_key(entry[0]),
                )
            },
        },
    }


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


def _flow_key(row: dict[str, str]) -> tuple[int, int, int, int]:
    return (
        _as_int(row, "src"),
        _as_int(row, "dst"),
        _as_int(row, "source_port"),
        _as_int(row, "start_time_ns"),
    )


def _fct_node_id(encoded_address: str) -> int:
    try:
        address = int(encoded_address, 16)
    except ValueError as error:
        raise ValueError(f"invalid FCT address: {encoded_address!r}") from error
    return (address >> 8) & 0xFFFF


def _load_fct_records(
    path: Path,
) -> dict[tuple[int, int, int, int], dict[str, int]]:
    # A source port names a live five-tuple, not a flow: the ns-3 bridge
    # reuses one once its queue pair terminates, so only the port together
    # with the flow's start time identifies a flow across a whole run.
    records: dict[tuple[int, int, int, int], dict[str, int]] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        fields = line.split()
        if len(fields) != 8:
            raise ValueError(f"invalid FCT record at {path}:{line_number}")
        (
            source,
            destination,
            source_port,
            _destination_port,
            size,
            start,
            duration,
            standalone,
        ) = fields
        key = (
            _fct_node_id(source),
            _fct_node_id(destination),
            int(source_port),
            int(start),
        )
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
            raise ValueError(
                f"invalid numeric FCT record at {path}:{line_number}"
            ) from error
    return records


def _verify_fct_join(
    flow_rows: list[dict[str, str]], fct_path: Path
) -> dict[str, int | str]:
    completed_rows = [row for row in flow_rows if _terminal_outcome(row) == "completed"]
    failed_flow_count = len(flow_rows) - len(completed_rows)
    if not fct_path.is_file():
        return {
            "status": "not_available",
            "failed_flow_count": failed_flow_count,
        }
    records = _load_fct_records(fct_path)
    telemetry = {_flow_key(row): row for row in completed_rows}
    if len(telemetry) != len(completed_rows):
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
        "status": "verified" if failed_flow_count == 0 else "partial_verified",
        "telemetry_flow_count": len(telemetry),
        "fct_record_count": len(records),
        "failed_flow_count": failed_flow_count,
    }


def _summarize_transport_events(ns3_dir: Path) -> dict[str, Any]:
    path = ns3_dir / "transport_events.csv"
    if not path.is_file():
        return {"status": "not_available"}
    rows = load_csv(path)
    events: dict[str, int] = defaultdict(int)
    bytes_by_event: dict[str, int] = defaultdict(int)
    plane_events: dict[str, int] = defaultdict(int)
    plane_bytes: dict[str, int] = defaultdict(int)
    event_plane_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    valid_events = {
        "data_arrival",
        "data_deliver",
        "data_injected_drop",
        "control_arrival",
        "control_deliver",
        "queue_enqueue",
        "queue_dequeue",
        "qbb_drop",
        "switch_route_drop",
        "switch_admission_drop",
        "switch_egress_queue_drop",
        # A trimmed packet stays subject to the TC_med drop threshold at the
        # trimming switch and every downstream hop (UEC 1.0.3 section 4.1).
        "switch_trimmed_queue_drop",
        "trim_ftd_admission",
        "trim_ftd_egress_queue",
        "trim_ftd_lasthop_admission",
        "trim_ftd_lasthop_egress_queue",
        "trim_bts_admission",
        "trim_bts_egress_queue",
        "trim_bts_lasthop_admission",
        "trim_bts_lasthop_egress_queue",
    }
    trim_events = {event for event in valid_events if event.startswith("trim_")}
    for row in rows:
        event = row.get("event")
        plane = row.get("plane")
        if event not in valid_events or plane not in {"data", "control"}:
            raise ValueError("invalid transport event plane or event")
        if event.startswith("data_") and plane != "data":
            raise ValueError("configured data impairment dropped a control packet")
        if event.startswith("control_") and plane != "control":
            raise ValueError("invalid control transport event plane")
        if event.startswith("trim_") and plane != "data":
            raise ValueError("trim conversion must account for undelivered data")
        packet_bytes = _as_int(row, "packet_bytes")
        if packet_bytes < 0:
            raise ValueError("transport event packet bytes must be nonnegative")
        for field in ("time_ns", "protocol", "node", "node_type", "interface", "queue"):
            _as_int(row, field)
        events[event] += 1
        bytes_by_event[event] += packet_bytes
        plane_events[plane] += 1
        plane_bytes[plane] += packet_bytes
        event_plane_counts[event][plane] += 1

    return {
        "status": "available",
        "event_count": len(rows),
        "event_counts": dict(sorted(events.items())),
        "event_bytes": dict(sorted(bytes_by_event.items())),
        "plane_event_counts": {
            plane: plane_events[plane] for plane in ("data", "control")
        },
        "plane_bytes": {plane: plane_bytes[plane] for plane in ("data", "control")},
        "data_injected_drop_count": events["data_injected_drop"],
        "control_injected_drop_count": 0,
        "data_switch_admission_drop_count": event_plane_counts["switch_admission_drop"][
            "data"
        ],
        "control_switch_admission_drop_count": event_plane_counts[
            "switch_admission_drop"
        ]["control"],
        "data_switch_egress_queue_drop_count": event_plane_counts[
            "switch_egress_queue_drop"
        ]["data"],
        "control_switch_egress_queue_drop_count": event_plane_counts[
            "switch_egress_queue_drop"
        ]["control"],
        "data_natural_buffer_drop_count": (
            event_plane_counts["switch_admission_drop"]["data"]
            + event_plane_counts["switch_egress_queue_drop"]["data"]
        ),
        "control_natural_buffer_drop_count": (
            event_plane_counts["switch_admission_drop"]["control"]
            + event_plane_counts["switch_egress_queue_drop"]["control"]
        ),
        "packet_trimming": {
            "conversion_count": sum(events[event] for event in trim_events),
            "trimmed_payload_bytes": sum(
                bytes_by_event[event] for event in trim_events
            ),
            "ftd_conversion_count": sum(
                events[event]
                for event in trim_events
                if event.startswith("trim_ftd_")
            ),
            "bts_conversion_count": sum(
                events[event]
                for event in trim_events
                if event.startswith("trim_bts_")
            ),
            "admission_conversion_count": sum(
                events[event]
                for event in trim_events
                if event.endswith("_admission")
            ),
            "egress_queue_conversion_count": sum(
                events[event]
                for event in trim_events
                if event.endswith("_egress_queue")
            ),
            # DSCP_TRIMMED_LAST_HOP conversions are reported separately because
            # the source must not treat them as a path or NSCC congestion signal.
            "lasthop_conversion_count": sum(
                events[event] for event in trim_events if "_lasthop_" in event
            ),
            "trimmed_queue_drop_count": events["switch_trimmed_queue_drop"],
        },
    }


def _summarize_ns3_observability(ns3_dir: Path) -> dict[str, Any]:
    queue_path = ns3_dir / "qlen.txt"
    if queue_path.is_file():
        queue_rows = 0
        queues: set[tuple[int, int]] = set()
        max_queue_bytes = 0
        peak_queue_locations: set[tuple[int, int]] = set()
        for line_number, line in enumerate(
            queue_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            fields = line.split()
            if not fields:
                continue
            if len(fields) < 6 or fields[0] != "time" or (len(fields) - 3) % 3:
                raise ValueError(
                    f"invalid queue telemetry at {queue_path}:{line_number}"
                )
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
                    if queue_bytes > max_queue_bytes:
                        max_queue_bytes = queue_bytes
                        peak_queue_locations = {(switch, port)}
                    elif queue_bytes == max_queue_bytes:
                        peak_queue_locations.add((switch, port))
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
            "peak_switch_ports": [
                {"switch": switch, "port": port}
                for switch, port in sorted(peak_queue_locations)
            ],
        }
    else:
        queue = {"status": "not_available"}

    pfc_path = ns3_dir / "pfc.txt"
    if pfc_path.is_file():
        active_pauses: dict[tuple[int, int, int | None], list[int]] = defaultdict(list)
        intervals: list[int] = []
        pause_count = 0
        resume_count = 0
        unmatched_resumes = 0
        affected: dict[tuple[int, int, int | None], int] = {}
        event_count = 0
        uses_queue_identity = True
        for line_number, line in enumerate(
            pfc_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) == 6:
                timestamp, node, node_type, port, queue_field, event_type = fields
                queue_id: int | None = int(queue_field)
            elif len(fields) == 5:
                # Artifacts emitted before queue-aware PFC telemetry cannot
                # attribute pauses to a priority queue, but remain analyzable.
                timestamp, node, node_type, port, event_type = fields
                queue_id = None
                uses_queue_identity = False
            else:
                raise ValueError(f"invalid PFC telemetry at {pfc_path}:{line_number}")
            try:
                timestamp_ns = int(timestamp)
                node_id = int(node)
                node_kind = int(node_type)
                port_id = int(port)
                event = int(event_type)
            except ValueError as error:
                raise ValueError(
                    f"invalid PFC telemetry at {pfc_path}:{line_number}"
                ) from error
            if min(timestamp_ns, node_id, node_kind, port_id) < 0 or event not in (
                0,
                1,
            ):
                raise ValueError(f"invalid PFC telemetry at {pfc_path}:{line_number}")
            key = (node_id, port_id, queue_id)
            affected[key] = node_kind
            event_count += 1
            if event == 1:
                pause_count += 1
                if queue_id is not None and active_pauses[key]:
                    raise ValueError(
                        "PFC pause was received before the previous resume"
                    )
                active_pauses[key].append(timestamp_ns)
            else:
                resume_count += 1
                if not active_pauses[key]:
                    unmatched_resumes += 1
                    continue
                # Queue-unattributed historical traces cannot distinguish
                # overlapping pauses on one port. Pairing is deterministic but
                # explicitly labeled as an estimate below.
                start_time_ns = active_pauses[key].pop()
                if timestamp_ns < start_time_ns:
                    raise ValueError("PFC resume precedes its pause")
                intervals.append(timestamp_ns - start_time_ns)
        affected_switch_port_queues = [
            {
                "switch": node_id,
                "port": port_id,
                "queue": queue_id if queue_id is not None else "unknown",
            }
            for (node_id, port_id, queue_id), node_kind in sorted(affected.items())
            if node_kind == 1
        ]
        pfc = {
            "status": "available",
            "event_count": event_count,
            "pause_count": pause_count,
            "resume_count": resume_count,
            "completed_pause_interval_count": len(intervals),
            "total_paused_ns": sum(intervals),
            "max_paused_ns": max(intervals, default=0),
            "unmatched_resume_count": unmatched_resumes,
            "active_pause_count_at_end": sum(
                len(starts) for starts in active_pauses.values()
            ),
            "queue_identity_status": "available"
            if uses_queue_identity
            else "not_available",
            "pause_duration_status": (
                "exact" if uses_queue_identity else "estimated_without_queue_identity"
            ),
            "affected_switch_port_queues": affected_switch_port_queues,
        }
    else:
        pfc = {"status": "not_available"}
    return {
        "queue": queue,
        "pfc": pfc,
        "transport": _summarize_transport_events(ns3_dir),
    }


def _traffic_bytes(rows: list[dict[str, str]]) -> dict[str, int]:
    return {
        "flow_count": len(rows),
        "logical_bytes": sum(_as_int(row, "logical_bytes") for row in rows),
        "physical_bytes": sum(_as_int(row, "physical_bytes") for row in rows),
    }


def _background_timeline(rows: list[dict[str, str]]) -> dict[str, int | str]:
    background_rows = [
        row for row in rows if row.get("flow_kind") == "background_microburst"
    ]
    if not background_rows:
        return {"status": "no_background_microburst"}
    start_time_ns = min(_as_int(row, "start_time_ns") for row in background_rows)
    end_time_ns = max(_as_int(row, "end_time_ns") for row in background_rows)
    return {
        "status": "available",
        **_traffic_bytes(background_rows),
        "start_time_ns": start_time_ns,
        "end_time_ns": end_time_ns,
        "span_ns": end_time_ns - start_time_ns,
    }


def summarize(
    telemetry_dir: Path,
    fct_path: Path | None = None,
    ns3_dir: Path | None = None,
    expected_rank_count: int | None = None,
) -> dict[str, Any]:
    telemetry_dir = telemetry_dir.resolve()
    flow_rows = load_csv(telemetry_dir / "flow_events.csv")
    completion_rows = load_csv(telemetry_dir / "rank_completion.csv")
    collective_rows = _load_optional_csv(telemetry_dir / "collective_events.csv")
    if fct_path is None:
        fct_path = telemetry_dir.parent / "ns3" / "fct.txt"
    if ns3_dir is None:
        ns3_dir = telemetry_dir.parent / "ns3"

    rank_completion_status = _summarize_rank_completions(
        completion_rows, expected_rank_count
    )

    total_logical_bytes = sum(_as_int(row, "logical_bytes") for row in flow_rows)
    total_physical_bytes = sum(_as_int(row, "physical_bytes") for row in flow_rows)
    completed_rows = [row for row in flow_rows if _terminal_outcome(row) == "completed"]
    failed_rows = [row for row in flow_rows if _terminal_outcome(row) == "failed"]
    for row in completed_rows:
        if row.get("failure_reason"):
            raise ValueError("completed flow must not have a failure reason")
    for row in failed_rows:
        if not row.get("failure_reason"):
            raise ValueError("failed flow must record a failure reason")
    for row in flow_rows:
        if _optional_nonnegative_int(row, "trim_notifications") and (
            _optional_nonnegative_int(row, "trimmed_payload_bytes") == 0
        ):
            raise ValueError(
                "trim notification must identify undelivered payload bytes"
            )
        if (
            _optional_nonnegative_int(row, "trim_notifications")
            and _terminal_outcome(row) == "completed"
            and (
                _optional_nonnegative_int(row, "data_attempted_bytes")
                < _as_int(row, "physical_bytes")
            )
        ):
            raise ValueError("completed flow cannot deliver more bytes than attempted")
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
        raise ValueError(
            "shedding policy affected a flow outside DP All-Reduce payloads"
        )

    invalid_provenance = [
        row
        for row in flow_rows
        if row.get("flow_kind") == "provenance_control"
        and _as_int(row, "physical_bytes") <= 0
    ]
    if invalid_provenance:
        raise ValueError("provenance control flow must carry nonzero physical bytes")

    by_step: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "flows": 0,
            "completed_flows": 0,
            "failed_flows": 0,
            "shed_flows": 0,
            "logical_bytes": 0,
            "physical_bytes": 0,
        }
    )
    for row in flow_rows:
        step = row.get("training_step", "unknown")
        bucket = by_step[step]
        bucket["flows"] += 1
        bucket[f"{_terminal_outcome(row)}_flows"] += 1
        bucket["shed_flows"] += row.get("decision") == "shed"
        bucket["logical_bytes"] += _as_int(row, "logical_bytes")
        bucket["physical_bytes"] += _as_int(row, "physical_bytes")

    completion_times = [_as_int(row, "completion_time_ns") for row in completion_rows]
    flow_completion = _timing_statistics(
        [_flow_duration_ns(row) for row in completed_rows]
    )
    rank_completion = _timing_statistics(completion_times)
    foreground_logical_rows = [
        row
        for row in flow_rows
        if row.get("flow_kind") in ("foreground_payload", "provenance_control")
    ]
    dp_all_reduce_rows = [
        row
        for row in flow_rows
        if row.get("parallelism_domain") == "dp"
        and row.get("origin_transport_role") == "collective_payload"
        and row.get("collective_type") == "all_reduce"
    ]
    fct_join = _verify_fct_join(flow_rows, fct_path.resolve())
    collective_completion = _summarize_collectives(collective_rows)
    ns3_observability = _summarize_ns3_observability(ns3_dir.resolve())
    primary_eligible = (
        expected_rank_count is not None
        and not failed_rows
        and rank_completion_status["status"] == "verified"
        and collective_completion["status"] == "available"
        and fct_join["status"] == "verified"
    )
    return {
        "flow_count": len(flow_rows),
        "completed_flow_count": len(completed_rows),
        "failed_flow_count": len(failed_rows),
        "shed_flow_count": len(shed_rows),
        "total_logical_bytes": total_logical_bytes,
        "total_physical_bytes": total_physical_bytes,
        "shed_logical_bytes": sum(_as_int(row, "logical_bytes") for row in shed_rows),
        "completion_rank_count": len(completion_rows),
        "completion_time_ns_max": rank_completion["max_ns"] or 0,
        "rank_completion_time_ns": rank_completion,
        "rank_completion_status": rank_completion_status,
        "flow_completion_time_ns": {
            "all": flow_completion,
            "by_training_step": _timing_by_field(completed_rows, "training_step"),
            "by_parallelism_domain": _timing_by_field(
                completed_rows, "parallelism_domain"
            ),
            "by_flow_kind": _timing_by_field(completed_rows, "flow_kind"),
            "by_parallelism_domain_and_flow_kind": _timing_by_domain_and_kind(
                completed_rows
            ),
        },
        "transport_recovery": {
            "data_attempted_bytes": sum(
                _optional_nonnegative_int(row, "data_attempted_bytes")
                for row in flow_rows
            ),
            "retransmitted_bytes": sum(
                _optional_nonnegative_int(row, "retransmitted_bytes")
                for row in flow_rows
            ),
            "recovery_event_count": sum(
                _optional_nonnegative_int(row, "recovery_events") for row in flow_rows
            ),
            "failed_by_reason": {
                reason: sum(
                    1 for row in failed_rows if row.get("failure_reason") == reason
                )
                for reason in sorted(
                    {row.get("failure_reason", "") for row in failed_rows}
                )
            },
            "trimmed_payload_bytes": sum(
                _optional_nonnegative_int(row, "trimmed_payload_bytes")
                for row in flow_rows
            ),
            "trim_notification_count": sum(
                _optional_nonnegative_int(row, "trim_notifications")
                for row in flow_rows
            ),
            "trim_ftd_repair_count": sum(
                _optional_nonnegative_int(row, "trim_ftd_repairs") for row in flow_rows
            ),
            "trim_bts_notification_count": sum(
                _optional_nonnegative_int(row, "trim_bts_notifications")
                for row in flow_rows
            ),
            "trim_lasthop_notification_count": sum(
                _optional_nonnegative_int(row, "trim_lasthop_notifications")
                for row in flow_rows
            ),
            "trim_recovery_event_count": sum(
                _optional_nonnegative_int(row, "trim_recovery_events")
                for row in flow_rows
            ),
            "stale_trim_notification_count": sum(
                _optional_nonnegative_int(row, "stale_trim_notifications")
                for row in flow_rows
            ),
        },
        "collective_completion": collective_completion,
        "physical_traffic_bytes": {
            "total": _traffic_bytes(flow_rows),
            "foreground_logical_operations": _traffic_bytes(foreground_logical_rows),
            "dp_all_reduce": _traffic_bytes(dp_all_reduce_rows),
        },
        "background_microburst_timeline": _background_timeline(flow_rows),
        "fct_join": fct_join,
        "ns3_observability": ns3_observability,
        "primary_analysis_eligibility": {
            "status": "eligible" if primary_eligible else "ineligible",
            "expected_rank_count": expected_rank_count,
            "failed_flow_count": len(failed_rows),
            "rank_completion_status": rank_completion_status["status"],
            "collective_completion_status": collective_completion["status"],
            "fct_join_status": fct_join["status"],
        },
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
    parser.add_argument(
        "--expected-rank-count",
        type=int,
        help="require exactly one rank-completion row for every rank in [0, count)",
    )
    parser.add_argument(
        "--output", type=Path, help="write the JSON summary to this path"
    )
    arguments = parser.parse_args()
    summary = summarize(
        arguments.telemetry_dir.resolve(),
        arguments.fct_file.resolve() if arguments.fct_file else None,
        arguments.ns3_dir.resolve() if arguments.ns3_dir else None,
        arguments.expected_rank_count,
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
