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


def _charged_equals_absorbed(
    flows: list[dict[str, str]], summary: dict[str, Any]
) -> list[str]:
    """The two sinks that count forgiven bytes must agree.

    The transport reports every forgiven range as a ``trim_forgiven`` event as
    it happens; the frontend charges the same clipped length to the flow record
    the row is written from. A disagreement means a charged flow lost its row,
    or the two sinks clipped the range differently.
    """
    charged = sum(int(flow["forgiven_bytes"]) for flow in flows)
    transport = summary["ns3_observability"]["transport"]
    if transport.get("status") != "available":
        return ["transport event summary is unavailable, so nothing cross-checks"]
    absorbed = int(transport["trim_forgiven_bytes"])
    if charged != absorbed:
        return [
            f"flows were charged {charged} B but the transport forgave "
            f"{absorbed} B"
        ]
    return []


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

    # The hash identifies the operation, not the decision taken on it, so a
    # recovery row must carry the same one an admission row would. Zero here
    # means the domain branch ran before the hash and the cross-arm join is
    # broken for a reason that is not the domain.
    unhashed = [
        flow
        for flow in flows
        if flow["admission_eligible"] == "true" and flow["decision_hash"] == "0"
    ]
    if unhashed:
        failures.append(
            f"{len(unhashed)} eligible flows carry decision_hash 0, so the "
            "recovery arm cannot be joined against an admission arm"
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
    failures.extend(_charged_equals_absorbed(flows, _summary(recovery_dir)))

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
    # Reported, not gated. The transport segments every packet and every
    # repair from a packet boundary, so no trim it produces today is partly
    # settled and the count is zero; a nonzero count means the segmentation
    # changed and the clip is now load-bearing.
    transport = _summary(recovery_dir)["ns3_observability"]["transport"]
    print(f"partly settled trims: {transport.get('clipped_trim_count', 0)}")
    return failures


def check_race(run_dir: Path) -> list[str]:
    """Assert the retransmission race leaves the recovery domain sound.

    A retransmission timeout an order below the round trip resends ranges the
    receiver is still deciding about, so duplicate data arrives for ranges that
    were forgiven while it was in flight. The timeout also re-segments the
    repair stream, so a trim can straddle the cumulative sequence or overlap a
    range already accepted. The transfer must still complete, the duplicate
    must not re-credit anything, the budget must not move backwards, and a
    partly settled range must be charged for its new bytes only.
    """
    failures: list[str] = []
    flows = _flows(run_dir)
    summary = _summary(run_dir)
    recovery = summary["transport_recovery"]

    if recovery["timeout_count"] == 0:
        failures.append("race fixture fired no retransmission timeout")
    failures.extend(_charged_equals_absorbed(flows, summary))
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
    """Every trim must cost the sender exactly one rate cut, forgiven or pulled.

    A pulled trim reaches the sender as a notification and cuts the rate there.
    A forgiven trim never reaches the sender, so the ACK the forgive emits
    carries the CNP and the sender cuts on that. One cut per trim either way,
    so the counts add rather than bound.
    """
    recovery = _summary(run_dir)["transport_recovery"]
    pulled = recovery["trim_notification_count"]
    forgiven_ranges = _summary(run_dir)["forgiveness"]["forgiven_range_count"]
    taken = recovery["cnp_received_count"]
    if taken != pulled + forgiven_ranges:
        return [
            f"rate cuts taken ({taken}) do not account for the trims that owe "
            f"them: {pulled} pulled plus {forgiven_ranges} forgiven"
        ]
    return []


def check_congestion_exemption(run_dir: Path) -> list[str]:
    """Assert the exemption reached exactly the flows the policy names.

    The exemption is granted once, at queue-pair creation, to an eligible DP
    payload flow on a non-critical step whose budget is not already spent, and
    it ends when the receiver reports that budget spent. Each clause below is
    one of those words, read back off telemetry the run already wrote.
    """
    failures: list[str] = []
    flows = _flows(run_dir)
    if not flows:
        return ["congestion-exempt run emitted no flow telemetry"]

    incomplete = [flow for flow in flows if flow["terminal_outcome"] != "completed"]
    if incomplete:
        failures.append(
            f"{len(incomplete)} flows did not complete; the exemption must not "
            "convert a transfer into a failure"
        )

    clr_steps = _clr_steps(run_dir)
    exempt = [flow for flow in flows if flow["cc_exempt"] == "true"]
    for flow in exempt:
        if flow["flow_kind"] != "foreground_payload":
            failures.append(f"exempted a {flow['flow_kind']} flow")
        if flow["admission_eligible"] != "true":
            failures.append("exempted an ineligible flow")
        if flow["training_step"] in clr_steps:
            failures.append(
                f"exempted a flow on critical step {flow['training_step']}"
            )
    if not exempt:
        failures.append("no flow was exempted; the exemption never fired")
    if not any(int(flow["cc_signal_withheld"]) for flow in exempt):
        failures.append(
            "no exempt flow withheld a congestion signal; the exemption cost "
            "the congestion control nothing"
        )
    for flow in flows:
        if flow["cc_exempt"] != "true" and int(flow["cc_signal_withheld"]):
            failures.append(
                f"a non-exempt {flow['flow_kind']} flow withheld "
                f"{flow['cc_signal_withheld']} congestion signals"
            )
    # An exemption ends on the receiver's report that the cell has no
    # allowance left, and on nothing else. The two counters are written at
    # different moments, so comparing them catches a report that re-armed
    # nothing and a re-arm no report explains.
    signalled = sum(1 for flow in exempt if int(flow["allowance_spent_signalled"]))
    rearmed = sum(1 for flow in exempt if int(flow["cc_rearmed_ns"]))
    if signalled != rearmed:
        failures.append(
            f"{signalled} exempt flows were told their allowance was spent "
            f"but {rearmed} re-armed"
        )
    for flow in flows:
        if int(flow["cc_rearmed_ns"]) == 0:
            continue
        if flow["cc_exempt"] != "true":
            failures.append("a flow that was never exempt was re-armed")
        if int(flow["cnp_received"]) == 0:
            failures.append(
                "a re-armed flow took no rate cut, so the report that "
                "re-armed it was not charged"
            )

    law = _summary(run_dir)["forgiveness"]["ledger_law"]
    if law["status"] != "verified":
        failures.append(f"per-(dst, step) ledger law is {law['status']}: {law}")

    forgiveness = _summary(run_dir)["forgiveness"]
    print(
        f"congestion-exempt: {len(exempt)} exempt flows, "
        f"{forgiveness['cc_signal_withheld_count']} congestion signals "
        f"withheld, {forgiveness['cc_rearmed_flow_count']} flows re-armed"
    )
    return failures


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
    parser.add_argument(
        "--congestion-exempt",
        type=Path,
        help="a DCQCN run whose eligible flows may ignore their rate cuts",
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
    if arguments.congestion_exempt is not None:
        failures.extend(
            check_congestion_exemption(arguments.congestion_exempt.resolve())
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
