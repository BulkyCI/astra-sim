#!/usr/bin/env python3
"""Assert the recovery domain's safety properties on a materialized run.

Every claim here is checkable from telemetry the run already wrote. A failure
names the property, not a summary statistic, because a violated safety law
invalidates the arm rather than moving a number.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

CONTROL_FLOW_KINDS = frozenset({"provenance_control", "background_microburst"})


def _flows(run_dir: Path) -> list[dict[str, str]]:
    path = run_dir / "telemetry" / "flow_events.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _summary(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))


def _clr_steps(run_dir: Path) -> frozenset[str]:
    path = run_dir / "clr_mask.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return frozenset(
            row["step_id"] for row in csv.DictReader(handle) if row["is_clr"] == "1"
        )


def check(recovery_dir: Path, admission_dir: Path) -> list[str]:
    """Return every violated property, empty when the run is sound."""
    failures: list[str] = []
    flows = _flows(recovery_dir)
    if not flows:
        return ["recovery run emitted no flow telemetry"]

    incomplete = [flow for flow in flows if flow["terminal_outcome"] != "completed"]
    if incomplete:
        failures.append(
            f"{len(incomplete)} flows did not complete; forgiveness must not "
            "convert a transfer into a failure"
        )

    forgiven_total = 0
    clr_steps = _clr_steps(recovery_dir)
    for flow in flows:
        forgiven = int(flow["forgiven_bytes"])
        forgiven_total += forgiven
        if not forgiven:
            continue
        if flow["training_step"] in clr_steps:
            failures.append(
                f"forgave {forgiven} B on critical step {flow['training_step']}"
            )
        if flow["flow_kind"] in CONTROL_FLOW_KINDS:
            failures.append(f"forgave {forgiven} B on a {flow['flow_kind']} flow")
        if int(flow["delivered_bytes"]) != int(flow["physical_bytes"]) - forgiven:
            failures.append("delivered bytes do not exclude the forgiven bytes")
    if forgiven_total == 0:
        failures.append("recovery run forgave nothing; the fork never fired")

    law = _summary(recovery_dir)["forgiveness"]["ledger_law"]
    if law["status"] != "verified":
        failures.append(f"per-(dst, step) ledger law is {law['status']}: {law}")

    health = _summary(recovery_dir)["network_health"]
    if not health["W_prime"] < health["W"]:
        failures.append(
            f"W' {health['W_prime']} is not below W {health['W']}; forgiveness "
            "removed no repair work"
        )
    # The admission arm is reported, not gated. Its W is measured over fewer
    # offered bytes, because admission shedding takes whole payloads off the
    # wire while forgiveness only releases packets a switch already trimmed,
    # so the two W values do not order in either direction by construction.
    admission_health = _summary(admission_dir)["network_health"]
    print(
        f"recovery W={health['W']:.6f} W'={health['W_prime']:.6f}; "
        f"admission W={admission_health['W']:.6f} over "
        f"{admission_health['offered_physical_bytes']} offered bytes against "
        f"{health['offered_physical_bytes']}"
    )
    return failures


def check_race(run_dir: Path) -> list[str]:
    """Assert the retransmission race leaves the recovery domain sound.

    A retransmission timeout an order below the round trip resends ranges the
    receiver is still deciding about, so duplicate data arrives for ranges that
    were forgiven while it was in flight. The transfer must still complete, the
    duplicate must not re-credit anything, and the budget must not move
    backwards.
    """
    failures: list[str] = []
    flows = _flows(run_dir)
    summary = _summary(run_dir)
    recovery = summary["transport_recovery"]

    if recovery["timeout_count"] == 0:
        failures.append("race fixture fired no retransmission timeout")
    if recovery["retransmitted_bytes"] == 0:
        failures.append("race fixture retransmitted nothing")
    if summary["network_health"]["wire_per_offered"] <= 1.0:
        failures.append(
            "race fixture saw no duplicate arrivals, so nothing raced the "
            "forgiveness that made them redundant"
        )
    for flow in flows:
        if flow["terminal_outcome"] != "completed":
            failures.append(
                f"flow {flow['src']}->{flow['dst']} port {flow['source_port']} "
                f"ended {flow['terminal_outcome']} ({flow['failure_reason']})"
            )
        forgiven = int(flow["forgiven_bytes"])
        if forgiven > int(flow["physical_bytes"]):
            failures.append("a flow forgave more bytes than it offered")
        if int(flow["delivered_bytes"]) != int(flow["physical_bytes"]) - forgiven:
            failures.append("duplicate data re-credited a forgiven range")
    if any(
        flow["failure_reason"] == "no_forward_progress" for flow in flows
    ):
        failures.append("the forward-progress deadline fired")

    law = summary["forgiveness"]["ledger_law"]
    if law["status"] != "verified":
        failures.append(f"per-(dst, step) ledger law is {law['status']}: {law}")
    return failures


def check_congestion_neutrality(run_dir: Path) -> list[str]:
    """Every trim must cost the sender a rate cut, forgiven or pulled.

    A pulled trim reaches the sender as a NACK and cuts the rate there. A
    forgiven trim never reaches the sender, so the receiver owes the cut and
    carries it on its next ACK; one bool means several forgiven ranges can
    collapse into one flagged ACK. That bounds the count on both sides.
    """
    recovery = _summary(run_dir)["transport_recovery"]
    pulled = recovery["trim_notification_count"]
    forgiven_ranges = _summary(run_dir)["forgiveness"]["forgiven_range_count"]
    taken = recovery["cnp_received_count"]
    if not pulled <= taken <= pulled + forgiven_ranges:
        return [
            f"rate cuts taken ({taken}) outside the trims that owe them: "
            f"{pulled} pulled, up to {forgiven_ranges} forgiven"
        ]
    return []


def _identical_reruns(first: Path, second: Path) -> list[str]:
    """Two runs of one profile at one seed must produce identical telemetry."""
    left = (first / "telemetry" / "flow_events.csv").read_bytes()
    right = (second / "telemetry" / "flow_events.csv").read_bytes()
    return [] if left == right else ["same-seed reruns disagree on flow telemetry"]


def _forgiven_by_cell(flows: list[dict[str, str]]) -> dict[tuple[str, str], int]:
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for flow in flows:
        totals[(flow["dst"], flow["training_step"])] += int(flow["forgiven_bytes"])
    return dict(totals)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recovery", type=Path)
    parser.add_argument("admission", type=Path)
    parser.add_argument(
        "--rerun",
        type=Path,
        help="a second same-seed recovery run to compare byte for byte",
    )
    parser.add_argument(
        "--race",
        type=Path,
        help="a short-retransmission-timeout run to check against duplicates",
    )
    parser.add_argument(
        "--congestion-neutral",
        type=Path,
        help="a DCQCN run whose rate cuts must account for every trim",
    )
    arguments = parser.parse_args()
    failures = check(arguments.recovery.resolve(), arguments.admission.resolve())
    if arguments.rerun is not None:
        failures.extend(
            _identical_reruns(arguments.recovery.resolve(), arguments.rerun.resolve())
        )
    if arguments.race is not None:
        failures.extend(check_race(arguments.race.resolve()))
    if arguments.congestion_neutral is not None:
        failures.extend(
            check_congestion_neutrality(arguments.congestion_neutral.resolve())
        )
    if failures:
        for failure in failures:
            print(f"forgiveness check failed: {failure}")
        return 1
    cells = _forgiven_by_cell(_flows(arguments.recovery.resolve()))
    forgiven = sum(cells.values())
    print(
        f"forgiveness checks passed: {forgiven} B forgiven across "
        f"{sum(1 for total in cells.values() if total)} (dst, step) cells"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
