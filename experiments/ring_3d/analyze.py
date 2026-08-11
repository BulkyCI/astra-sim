#!/usr/bin/env python3
"""Validate and summarize telemetry emitted by the 3D Ring experiment."""

from __future__ import annotations

import argparse
import csv
import json
from array import array
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Any, Final

import numpy

# A 64-rank run emits one flow row per queue pair, which reaches millions of
# rows and gigabytes of CSV. Nothing in this module may retain a parsed row:
# every reported figure is a counter, a group-by over a bounded key space
# (training step, parallelism domain, flow kind), or a duration column held as
# a packed integer array. Materializing the rows costs ~2.9 KB each, which
# exceeds the memory of the runner that has to analyze them.


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


def iter_csv(path: Path) -> Iterator[dict[str, str]]:
    """Yield telemetry rows without materializing the file.

    The file stays open for the life of the generator, so consume it within
    the scope that created it rather than storing it for later.
    """
    if not path.is_file():
        raise FileNotFoundError(f"missing telemetry file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def load_csv(path: Path) -> list[dict[str, str]]:
    """Read a *bounded* telemetry file whole. Never use this for flow events."""
    return list(iter_csv(path))


def _iter_lines(path: Path) -> Iterator[tuple[int, str]]:
    """Yield numbered lines without holding the whole file in memory."""
    with path.open(encoding="utf-8") as handle:
        yield from enumerate(handle, start=1)


def _training_step_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _timing_statistics(values: Sequence[int]) -> dict[str, int | None]:
    """Return nearest-rank latency quantiles in nanoseconds.

    Accepts a packed `array("q")` as well as a list, and sorts through numpy so
    a column of millions of durations never becomes a list of Python integers.
    """
    count = len(values)
    if count == 0:
        return {
            "count": 0,
            "min_ns": None,
            "p50_ns": None,
            "p95_ns": None,
            "p99_ns": None,
            "max_ns": None,
        }
    ordered = numpy.sort(numpy.asarray(values, dtype=numpy.int64))

    def percentile(percent: int) -> int:
        return int(ordered[ceil(count * percent / 100) - 1])

    return {
        "count": count,
        "min_ns": int(ordered[0]),
        "p50_ns": percentile(50),
        "p95_ns": percentile(95),
        "p99_ns": percentile(99),
        "max_ns": int(ordered[-1]),
    }


def _flow_duration_ns(row: dict[str, str]) -> int:
    duration = _as_int(row, "end_time_ns") - _as_int(row, "start_time_ns")
    if duration < 0:
        raise ValueError("flow completion time must not be negative")
    return duration


def _durations() -> defaultdict[Any, array]:
    """Free monoid of durations per group key: identity empty, op append."""
    return defaultdict(lambda: array("q"))


def _timing_by_group(durations: dict[Any, array]) -> dict[str, Any]:
    return {
        name: _timing_statistics(values)
        for name, values in sorted(durations.items(), key=lambda entry: entry[0])
    }


def _timing_by_domain_and_kind(durations: dict[Any, array]) -> dict[str, Any]:
    nested: dict[str, dict[str, array]] = defaultdict(dict)
    for (domain, kind), values in durations.items():
        nested[domain][kind] = values
    return {
        domain: _timing_by_group(kinds)
        for domain, kinds in sorted(nested.items(), key=lambda entry: entry[0])
    }


@dataclass(slots=True)
class _Traffic:
    """Componentwise monoid on (count, logical bytes, physical bytes)."""

    flow_count: int = 0
    logical_bytes: int = 0
    physical_bytes: int = 0

    def add(self, logical_bytes: int, physical_bytes: int) -> None:
        self.flow_count += 1
        self.logical_bytes += logical_bytes
        self.physical_bytes += physical_bytes

    def summary(self) -> dict[str, int]:
        return {
            "flow_count": self.flow_count,
            "logical_bytes": self.logical_bytes,
            "physical_bytes": self.physical_bytes,
        }


@dataclass(frozen=True, slots=True)
class _Window:
    """A closed interval. `join` is the semilattice operation; the identity is
    `None`, so absence of a window is a state rather than a pair of nulls."""

    start_ns: int
    end_ns: int

    def join(self, start_ns: int, end_ns: int) -> _Window:
        return _Window(min(self.start_ns, start_ns), max(self.end_ns, end_ns))

    @property
    def span_ns(self) -> int:
        return self.end_ns - self.start_ns


def _timing_by_step(durations: dict[Any, array]) -> dict[str, Any]:
    """Group timings by training step, ordered numerically where possible."""
    return {
        step: _timing_statistics(values)
        for step, values in sorted(
            durations.items(), key=lambda entry: _training_step_sort_key(entry[0])
        )
    }


@dataclass(slots=True)
class _Operation:
    """One logical collective: the join of its ranks' intervals and how many
    ranks reported it. The contributing rows are never retained."""

    window: _Window
    rank_count: int = 1

    def record(self, start_ns: int, end_ns: int) -> None:
        self.window = self.window.join(start_ns, end_ns)
        self.rank_count += 1



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


def _summarize_collectives(rows: Iterator[dict[str, str]]) -> dict[str, Any]:
    """Fold per-rank collective events into per-rank and whole-operation timing.

    A logical collective is identified by (domain, type, step, workload node);
    its all-rank span is the join of every contributing rank's interval, so the
    rows themselves are not retained. Nesting by domain and type reuses the
    flow-side grouping rather than restating it.
    """
    rank_event_count = 0
    per_rank_durations = array("q")
    per_rank_by_domain = _durations()
    per_rank_by_domain_and_type = _durations()
    operations: dict[tuple[str, str, int, int], _Operation] = {}
    seen_rank_events: set[tuple[str, str, int, int, int]] = set()

    for row in rows:
        rank_event_count += 1
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
        per_rank_by_domain_and_type[(domain, collective_type)].append(duration)

        start_time_ns = _as_int(row, "start_time_ns")
        end_time_ns = _as_int(row, "end_time_ns")
        operation_key = (domain, collective_type, training_step, node_id)
        operation = operations.get(operation_key)
        if operation is None:
            operations[operation_key] = _Operation(_Window(start_time_ns, end_time_ns))
        else:
            operation.record(start_time_ns, end_time_ns)

    operation_spans = array("q")
    spans_by_domain = _durations()
    spans_by_domain_and_type = _durations()
    spans_by_step = _durations()
    rank_counts = array("q")
    for (domain, collective_type, training_step, _node), operation in operations.items():
        span = operation.window.span_ns
        operation_spans.append(span)
        spans_by_domain[domain].append(span)
        spans_by_domain_and_type[(domain, collective_type)].append(span)
        spans_by_step[str(training_step)].append(span)
        rank_counts.append(operation.rank_count)

    return {
        "status": "available",
        "rank_event_count": rank_event_count,
        "logical_collective_count": len(operations),
        "operation_rank_count": _timing_statistics(rank_counts),
        "per_rank_completion_time_ns": {
            "all": _timing_statistics(per_rank_durations),
            "by_parallelism_domain": _timing_by_group(per_rank_by_domain),
            "by_parallelism_domain_and_collective_type": _timing_by_domain_and_kind(
                per_rank_by_domain_and_type
            ),
        },
        "all_rank_operation_span_ns": {
            "all": _timing_statistics(operation_spans),
            "by_parallelism_domain": _timing_by_group(spans_by_domain),
            "by_parallelism_domain_and_collective_type": _timing_by_domain_and_kind(
                spans_by_domain_and_type
            ),
            "by_training_step": _timing_by_step(spans_by_step),
        },
    }


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise TypeError(f"invalid run manifest: {path}")
    return manifest


def _models_no_loss_mechanism(manifest: dict[str, Any] | None) -> bool:
    if manifest is None:
        return False
    if any(
        bool((manifest.get(key) or {}).get("enabled"))
        for key in ("data_plane_loss", "transport_recovery", "packet_trimming")
    ):
        return False
    # A best-effort fabric drops on buffer rejection, so only a lossless
    # flow-controlled one leaves nothing that can lose or reorder a packet.
    fabric = manifest.get("fabric")
    return isinstance(fabric, dict) and bool(fabric.get("pfc_enabled"))


def _flow_control_regime(manifest: dict[str, Any] | None) -> str:
    """Name how the fabric releases buffer pressure, for regime-aware gates.

    A ``lossless_pfc`` fabric pauses upstream ports, so congestion leaves
    completed PFC pause intervals. A ``best_effort`` fabric rejects buffer
    admission instead, so congestion leaves trimmed or dropped packets and
    can never leave a pause. A summary from a run without a manifest cannot
    name its regime.
    """
    if manifest is None:
        return "unknown"
    fabric = manifest.get("fabric")
    if not isinstance(fabric, dict):
        return "unknown"
    return "lossless_pfc" if fabric.get("pfc_enabled") else "best_effort"


def _verify_lossless_transport(
    flow_count: int,
    retransmitted_bytes: int,
    recovery_events: int,
    manifest: dict[str, Any] | None,
) -> dict[str, int | str]:
    """Require zero recovery from a run that models no loss mechanism.

    A lossless fabric with no timeout recovery and no trimming has nothing
    that can drop, reorder, or resend a packet, and per-flow ECMP keeps a
    single flow on a single path. Every recovery counter must therefore be
    zero. A nonzero one means a packet reached a queue pair it does not
    belong to, which is the observable signature of a source port reused
    while a straggler from its previous flow was still in the network. The
    check exists because that is otherwise silent: the receiver would fold
    the stray sequence numbers into a healthy flow.
    """
    if not _models_no_loss_mechanism(manifest):
        return {"status": "not_applicable"}
    if retransmitted_bytes or recovery_events:
        raise ValueError(
            "run models no loss mechanism but recorded transport recovery "
            f"(retransmitted_bytes={retransmitted_bytes}, "
            f"recovery_events={recovery_events})"
        )
    return {"status": "verified", "flow_count": flow_count}


_KEY_FIELD_BITS = 24
_KEY_TIME_BITS = 64


def _packed_flow_key(
    src: int, dst: int, source_port: int, start_time_ns: int
) -> int:
    """Pack a flow's identity into a single integer.

    Millions of these are live at once during the join, where one four-integer
    tuple per flow costs roughly three times what the packed form does.
    """
    for value, bits in (
        (src, _KEY_FIELD_BITS),
        (dst, _KEY_FIELD_BITS),
        (source_port, _KEY_FIELD_BITS),
        (start_time_ns, _KEY_TIME_BITS),
    ):
        if value < 0 or value >> bits:
            raise ValueError("flow identity is outside the joinable range")
    return (
        ((src << _KEY_FIELD_BITS | dst) << _KEY_FIELD_BITS | source_port)
        << _KEY_TIME_BITS
    ) | start_time_ns


def _flow_key(row: dict[str, str]) -> int:
    return _packed_flow_key(
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


def _load_fct_records(path: Path) -> dict[int, tuple[int, int] | None]:
    """Index `fct.txt` by packed flow key.

    A source port names a live five-tuple, not a flow: the ns-3 bridge reuses
    one once its queue pair terminates, so only the port together with the
    flow's start time identifies a flow across a whole run. Values are
    `(physical_bytes, duration_ns)`; the join replaces each with `None` as it
    consumes it, which both detects a duplicate on the telemetry side and
    releases the record while the pass is still running.
    """
    records: dict[int, tuple[int, int] | None] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
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
            try:
                value = (int(size), int(duration))
                int(standalone)
                key = _packed_flow_key(
                    _fct_node_id(source),
                    _fct_node_id(destination),
                    int(source_port),
                    int(start),
                )
            except ValueError as error:
                raise ValueError(
                    f"invalid numeric FCT record at {path}:{line_number}"
                ) from error
            if key in records:
                raise ValueError("FCT records contain a duplicate flow key")
            records[key] = value
    return records


_ABSENT: Final = object()
"""Distinguishes an unknown key from a consumed one in the FCT index."""


class _FctJoin:
    """Match completed flow telemetry against `fct.txt` one row at a time.

    The set-based join built a dict of every telemetry row *and* a dict of
    every FCT record, then compared the two key sets. Only the FCT side
    survives here, and each record passes through three states exactly once:
    unknown (absent from the index), pending (a byte/duration pair), consumed
    (`None`). Python cannot seal that sum, so the transition is confined to
    `consume` and the sentinel is compared by identity.
    """

    __slots__ = ("_matched", "_mismatch", "_missing", "_records", "available")

    def __init__(self, fct_path: Path) -> None:
        self.available = fct_path.is_file()
        self._records = _load_fct_records(fct_path) if self.available else {}
        self._matched = 0
        self._missing = 0
        self._mismatch: str | None = None

    def consume(self, row: dict[str, str]) -> None:
        if not self.available:
            return
        key = _flow_key(row)
        record = self._records.get(key, _ABSENT)
        if record is _ABSENT:
            self._missing += 1
            return
        if record is None:
            raise ValueError("flow telemetry contains a duplicate flow key")
        self._records[key] = None
        self._matched += 1
        # Report a missing or extra record ahead of a field mismatch, as the
        # set-based join did: an incomplete join explains the mismatches.
        if self._mismatch is not None:
            return
        physical_bytes, duration_ns = record
        if _as_int(row, "physical_bytes") != physical_bytes:
            self._mismatch = "telemetry/FCT physical-byte mismatch"
        elif _flow_duration_ns(row) != duration_ns:
            self._mismatch = "telemetry/FCT duration mismatch"

    def result(self, failed_flow_count: int) -> dict[str, int | str]:
        if not self.available:
            return {
                "status": "not_available",
                "failed_flow_count": failed_flow_count,
            }
        extra = len(self._records) - self._matched
        if self._missing or extra:
            raise ValueError(
                "telemetry/FCT join is incomplete "
                f"(missing={self._missing}, extra={extra})"
            )
        if self._mismatch is not None:
            raise ValueError(self._mismatch)
        return {
            "status": "verified" if failed_flow_count == 0 else "partial_verified",
            "telemetry_flow_count": self._matched,
            "fct_record_count": len(self._records),
            "failed_flow_count": failed_flow_count,
        }


def _summarize_transport_events(ns3_dir: Path) -> dict[str, Any]:
    path = ns3_dir / "transport_events.csv"
    if not path.is_file():
        return {"status": "not_available"}
    event_count = 0
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
    # The simulator aggregates in memory and emits one row per (event, plane)
    # pair at exit: a raw row per packet event grew past 100 GB per arm and
    # its per-packet flushes exhausted shared CI storage.
    for row in iter_csv(path):
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
        row_events = _as_int(row, "event_count")
        row_bytes = _as_int(row, "total_bytes")
        if row_events < 0 or row_bytes < 0:
            raise ValueError("transport event totals must be nonnegative")
        event_count += row_events
        events[event] += row_events
        bytes_by_event[event] += row_bytes
        plane_events[plane] += row_events
        plane_bytes[plane] += row_bytes
        event_plane_counts[event][plane] += row_events

    return {
        "status": "available",
        "event_count": event_count,
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
        for line_number, line in _iter_lines(queue_path):
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
        for line_number, line in _iter_lines(pfc_path):
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


_COUNTER_FIELDS: Final = (
    "data_attempted_bytes",
    "retransmitted_bytes",
    "recovery_events",
    "trimmed_payload_bytes",
    "trim_notifications",
    "trim_ftd_repairs",
    "trim_bts_notifications",
    "trim_lasthop_notifications",
    "trim_recovery_events",
    "stale_trim_notifications",
)
"""Telemetry columns summed verbatim. The column name is the only name they
have, so the totals stay keyed by it rather than restating each one."""

_FOREGROUND_LOGICAL_KINDS: Final = frozenset(
    {"foreground_payload", "provenance_control"}
)

_STEP_BUCKET_FIELDS: Final = (
    "flows",
    "completed_flows",
    "failed_flows",
    "shed_flows",
    "logical_bytes",
    "physical_bytes",
)


def _is_dp_all_reduce(row: dict[str, str]) -> bool:
    """A flow whose logical origin is a DP All-Reduce payload."""
    return (
        row.get("parallelism_domain") == "dp"
        and row.get("origin_transport_role") == "collective_payload"
        and row.get("collective_type") == "all_reduce"
    )


def _is_valid_shed(row: dict[str, str]) -> bool:
    """The selection policy may only substitute a DP All-Reduce payload."""
    return (
        _as_bool(row, "admission_eligible")
        and _is_dp_all_reduce(row)
        and row.get("flow_kind") == "provenance_control"
        and row.get("transport_role") == "provenance_control"
    )




class _FlowStatistics:
    """Every figure the analyzer derives from `flow_events.csv`, in one pass.

    Validation, aggregation, and the FCT join all consume the same row and
    then drop it. Duration columns are the only unbounded state and they hold
    8 bytes per flow, so a run with millions of queue pairs costs megabytes
    here instead of the tens of gigabytes that retaining the rows would.
    """

    __slots__ = (
        "_join",
        "all_durations",
        "background",
        "background_window",
        "by_domain_and_kind",
        "by_flow_kind",
        "by_parallelism_domain",
        "by_step",
        "by_training_step",
        "completed_count",
        "counters",
        "dp_all_reduce_traffic",
        "failed_by_reason",
        "failed_count",
        "flow_count",
        "foreground_traffic",
        "shed_count",
        "shed_logical_bytes",
        "total_logical_bytes",
        "total_physical_bytes",
        "total_traffic",
    )

    def __init__(self, join: _FctJoin) -> None:
        self._join = join
        self.flow_count = 0
        self.completed_count = 0
        self.failed_count = 0
        self.shed_count = 0
        self.total_logical_bytes = 0
        self.total_physical_bytes = 0
        self.shed_logical_bytes = 0
        self.counters = dict.fromkeys(_COUNTER_FIELDS, 0)
        self.failed_by_reason: dict[str, int] = defaultdict(int)
        self.total_traffic = _Traffic()
        self.foreground_traffic = _Traffic()
        self.dp_all_reduce_traffic = _Traffic()
        self.background = _Traffic()
        self.background_window: _Window | None = None
        self.by_step: dict[str, dict[str, int]] = defaultdict(
            lambda: dict.fromkeys(_STEP_BUCKET_FIELDS, 0)
        )
        self.all_durations = array("q")
        self.by_training_step = _durations()
        self.by_parallelism_domain = _durations()
        self.by_flow_kind = _durations()
        self.by_domain_and_kind = _durations()

    def consume(self, row: dict[str, str]) -> None:
        """Fold one flow into every accumulator, then drop it.

        The checks run in the order the row-list implementation ran them, so a
        malformed row still reports the same first violation.
        """
        logical_bytes = _as_int(row, "logical_bytes")
        physical_bytes = _as_int(row, "physical_bytes")
        outcome = _terminal_outcome(row)
        failure_reason = row.get("failure_reason")
        if outcome == "completed" and failure_reason:
            raise ValueError("completed flow must not have a failure reason")
        if outcome == "failed" and not failure_reason:
            raise ValueError("failed flow must record a failure reason")

        trim_notifications = _optional_nonnegative_int(row, "trim_notifications")
        if trim_notifications and (
            _optional_nonnegative_int(row, "trimmed_payload_bytes") == 0
        ):
            raise ValueError("trim notification must identify undelivered payload bytes")
        if (
            trim_notifications
            and outcome == "completed"
            and _optional_nonnegative_int(row, "data_attempted_bytes") < physical_bytes
        ):
            raise ValueError("completed flow cannot deliver more bytes than attempted")

        kind = row.get("flow_kind")
        domain = row.get("parallelism_domain")
        shed = row.get("decision") == "shed"
        if shed:
            if not _is_valid_shed(row):
                raise ValueError(
                    "shedding policy affected a flow outside DP All-Reduce payloads"
                )
            self.shed_count += 1
            self.shed_logical_bytes += logical_bytes
        if kind == "provenance_control" and physical_bytes <= 0:
            raise ValueError("provenance control flow must carry nonzero physical bytes")

        self.flow_count += 1
        self.total_logical_bytes += logical_bytes
        self.total_physical_bytes += physical_bytes
        for field in _COUNTER_FIELDS:
            self.counters[field] += _optional_nonnegative_int(row, field)

        self.total_traffic.add(logical_bytes, physical_bytes)
        if kind in _FOREGROUND_LOGICAL_KINDS:
            self.foreground_traffic.add(logical_bytes, physical_bytes)
        if _is_dp_all_reduce(row):
            self.dp_all_reduce_traffic.add(logical_bytes, physical_bytes)

        bucket = self.by_step[row.get("training_step", "unknown")]
        bucket["flows"] += 1
        bucket[f"{outcome}_flows"] += 1
        bucket["shed_flows"] += shed
        bucket["logical_bytes"] += logical_bytes
        bucket["physical_bytes"] += physical_bytes

        if kind == "background_microburst":
            self.background.add(logical_bytes, physical_bytes)
            start_time_ns = _as_int(row, "start_time_ns")
            end_time_ns = _as_int(row, "end_time_ns")
            window = self.background_window
            self.background_window = (
                _Window(start_time_ns, end_time_ns)
                if window is None
                else window.join(start_time_ns, end_time_ns)
            )

        if outcome == "failed":
            self.failed_count += 1
            self.failed_by_reason[failure_reason or ""] += 1
            return

        self.completed_count += 1
        duration = _flow_duration_ns(row)
        step = row.get("training_step") or "unknown"
        domain_name = domain or "unknown"
        kind_name = kind or "unknown"
        self.all_durations.append(duration)
        self.by_training_step[step].append(duration)
        self.by_parallelism_domain[domain_name].append(duration)
        self.by_flow_kind[kind_name].append(duration)
        self.by_domain_and_kind[(domain_name, kind_name)].append(duration)
        self._join.consume(row)

    def background_timeline(self) -> dict[str, int | str]:
        window = self.background_window
        if window is None:
            return {"status": "no_background_microburst"}
        return {
            "status": "available",
            **self.background.summary(),
            "start_time_ns": window.start_ns,
            "end_time_ns": window.end_ns,
            "span_ns": window.span_ns,
        }


def summarize(
    telemetry_dir: Path,
    fct_path: Path | None = None,
    ns3_dir: Path | None = None,
    expected_rank_count: int | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    telemetry_dir = telemetry_dir.resolve()
    flow_events = telemetry_dir / "flow_events.csv"
    if not flow_events.is_file():
        raise FileNotFoundError(f"missing telemetry file: {flow_events}")
    completion_rows = load_csv(telemetry_dir / "rank_completion.csv")
    collective_events = telemetry_dir / "collective_events.csv"
    if fct_path is None:
        fct_path = telemetry_dir.parent / "ns3" / "fct.txt"
    if ns3_dir is None:
        ns3_dir = telemetry_dir.parent / "ns3"
    if manifest_path is None:
        manifest_path = telemetry_dir.parent / "manifest.json"
    manifest = _load_manifest(manifest_path)

    rank_completion_status = _summarize_rank_completions(
        completion_rows, expected_rank_count
    )

    join = _FctJoin(fct_path.resolve())
    statistics = _FlowStatistics(join)
    for row in iter_csv(flow_events):
        statistics.consume(row)

    completion_times = [_as_int(row, "completion_time_ns") for row in completion_rows]
    flow_completion = _timing_statistics(statistics.all_durations)
    rank_completion = _timing_statistics(completion_times)
    fct_join = join.result(statistics.failed_count)
    lossless_transport = _verify_lossless_transport(
        statistics.flow_count,
        statistics.counters["retransmitted_bytes"],
        statistics.counters["recovery_events"],
        manifest,
    )
    collective_completion = (
        _summarize_collectives(iter_csv(collective_events))
        if collective_events.is_file()
        else {"status": "not_available"}
    )
    ns3_observability = _summarize_ns3_observability(ns3_dir.resolve())
    primary_eligible = (
        expected_rank_count is not None
        and not statistics.failed_count
        and rank_completion_status["status"] == "verified"
        and collective_completion["status"] == "available"
        and fct_join["status"] == "verified"
    )
    return {
        "flow_count": statistics.flow_count,
        "completed_flow_count": statistics.completed_count,
        "failed_flow_count": statistics.failed_count,
        "shed_flow_count": statistics.shed_count,
        "total_logical_bytes": statistics.total_logical_bytes,
        "total_physical_bytes": statistics.total_physical_bytes,
        "shed_logical_bytes": statistics.shed_logical_bytes,
        "completion_rank_count": len(completion_rows),
        "completion_time_ns_max": rank_completion["max_ns"] or 0,
        "rank_completion_time_ns": rank_completion,
        "rank_completion_status": rank_completion_status,
        "flow_completion_time_ns": {
            "all": flow_completion,
            "by_training_step": _timing_by_group(statistics.by_training_step),
            "by_parallelism_domain": _timing_by_group(
                statistics.by_parallelism_domain
            ),
            "by_flow_kind": _timing_by_group(statistics.by_flow_kind),
            "by_parallelism_domain_and_flow_kind": _timing_by_domain_and_kind(
                statistics.by_domain_and_kind
            ),
        },
        "transport_recovery": {
            "data_attempted_bytes": statistics.counters["data_attempted_bytes"],
            "retransmitted_bytes": statistics.counters["retransmitted_bytes"],
            "recovery_event_count": statistics.counters["recovery_events"],
            "failed_by_reason": dict(sorted(statistics.failed_by_reason.items())),
            "trimmed_payload_bytes": statistics.counters["trimmed_payload_bytes"],
            "trim_notification_count": statistics.counters["trim_notifications"],
            "trim_ftd_repair_count": statistics.counters["trim_ftd_repairs"],
            "trim_bts_notification_count": statistics.counters[
                "trim_bts_notifications"
            ],
            "trim_lasthop_notification_count": statistics.counters[
                "trim_lasthop_notifications"
            ],
            "trim_recovery_event_count": statistics.counters["trim_recovery_events"],
            "stale_trim_notification_count": statistics.counters[
                "stale_trim_notifications"
            ],
        },
        "collective_completion": collective_completion,
        "physical_traffic_bytes": {
            "total": statistics.total_traffic.summary(),
            "foreground_logical_operations": statistics.foreground_traffic.summary(),
            "dp_all_reduce": statistics.dp_all_reduce_traffic.summary(),
        },
        "background_microburst_timeline": statistics.background_timeline(),
        "fct_join": fct_join,
        "flow_control_regime": _flow_control_regime(manifest),
        "lossless_transport": lossless_transport,
        "ns3_observability": ns3_observability,
        "primary_analysis_eligibility": {
            "status": "eligible" if primary_eligible else "ineligible",
            "expected_rank_count": expected_rank_count,
            "failed_flow_count": statistics.failed_count,
            "rank_completion_status": rank_completion_status["status"],
            "collective_completion_status": collective_completion["status"],
            "fct_join_status": fct_join["status"],
        },
        "by_training_step": dict(
            sorted(
                statistics.by_step.items(),
                key=lambda entry: _training_step_sort_key(entry[0]),
            )
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
        "--manifest",
        type=Path,
        help=(
            "run manifest naming the modeled loss mechanisms; "
            "defaults to ../manifest.json"
        ),
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
        arguments.manifest.resolve() if arguments.manifest else None,
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
