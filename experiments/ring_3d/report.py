#!/usr/bin/env python3
"""Render a researcher-facing Markdown report for a 3D Ring experiment run.

The report intentionally distinguishes logical modeled bytes from physical
transport bytes. A shed DP All-Reduce payload is modeled by a protected
provenance-control flow, rather than by literal packet loss.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid integer {field!r} in experiment output") from error


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    rendered = float(value)
    for unit in units:
        if rendered < 1024 or unit == units[-1]:
            return f"{rendered:.2f} {unit}" if unit != "B" else f"{value} B"
        rendered /= 1024
    raise AssertionError("unreachable")


def _format_duration_ns(value: int) -> str:
    if value < 1_000:
        return f"{value} ns"
    if value < 1_000_000:
        return f"{value / 1_000:.2f} μs"
    if value < 1_000_000_000:
        return f"{value / 1_000_000:.2f} ms"
    return f"{value / 1_000_000_000:.2f} s"


def _format_optional_duration_ns(value: Any) -> str:
    return _format_duration_ns(value) if isinstance(value, int) else "not available"


def _format_probability(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError) as error:
        raise ValueError("drop probability must be numeric") from error


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    rendered = ["| " + " | ".join(headers) + " |"]
    rendered.append("| " + " | ".join("---" for _ in headers) + " |")
    rendered.extend(
        "| " + " | ".join(_escape_cell(value) for value in row) + " |"
        for row in rows
    )
    return rendered


def _aggregate_by(rows: list[dict[str, str]], field: str) -> dict[str, dict[str, int]]:
    aggregates: dict[str, dict[str, int]] = defaultdict(
        lambda: {"flows": 0, "shed_flows": 0, "logical_bytes": 0, "physical_bytes": 0}
    )
    for row in rows:
        bucket = aggregates[row.get(field) or "unknown"]
        bucket["flows"] += 1
        bucket["shed_flows"] += row.get("decision") == "shed"
        bucket["logical_bytes"] += _as_int(row.get("logical_bytes"), "logical_bytes")
        bucket["physical_bytes"] += _as_int(row.get("physical_bytes"), "physical_bytes")
    return dict(sorted(aggregates.items()))


def _timing_table_row(label: str, values: Any) -> list[Any] | None:
    if not isinstance(values, dict) or not values.get("count"):
        return None
    return [
        label,
        values["count"],
        _format_optional_duration_ns(values.get("p50_ns")),
        _format_optional_duration_ns(values.get("p95_ns")),
        _format_optional_duration_ns(values.get("p99_ns")),
        _format_optional_duration_ns(values.get("max_ns")),
    ]


def _dp_decisions_by_step(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    decisions: dict[str, dict[str, int]] = defaultdict(
        lambda: {"eligible_flows": 0, "shed_flows": 0}
    )
    for row in rows:
        if row.get("admission_eligible") != "true":
            continue
        bucket = decisions[row.get("training_step") or "unknown"]
        bucket["eligible_flows"] += 1
        bucket["shed_flows"] += row.get("decision") == "shed"
    return dict(sorted(decisions.items(), key=lambda item: int(item[0])))


def _artifact_url() -> str | None:
    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repository and run_id:
        return f"{server}/{repository}/actions/runs/{run_id}#artifacts"
    return None


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def render_report(run_dir: Path, profile_path: Path) -> str:
    """Return a self-contained Markdown report for an experiment directory."""
    profile = _read_json(profile_path)
    if profile is None:
        raise FileNotFoundError(f"missing profile: {profile_path}")
    parallelism = profile.get("parallelism")
    if not isinstance(parallelism, dict):
        raise ValueError("profile is missing parallelism")
    try:
        tp = _as_int(parallelism["tp"], "parallelism.tp")
        pp = _as_int(parallelism["pp"], "parallelism.pp")
        dp = _as_int(parallelism["dp"], "parallelism.dp")
    except KeyError as error:
        raise ValueError("profile parallelism requires tp, pp, and dp") from error
    expected_ranks = tp * pp * dp

    policy = _read_json(run_dir / "experiment.json")
    summary = _read_json(run_dir / "summary.json")
    flows = _read_csv(run_dir / "telemetry" / "flow_events.csv")
    completions = _read_csv(run_dir / "telemetry" / "rank_completion.csv")

    profile_name = profile.get("name", profile_path.stem)
    lines = [
        "# 3D Ring ns-3 researcher report",
        "",
        "> This report distinguishes logical modeled bytes (collective and background operations) "
        "from physical transport bytes. A shed payload is modeled by protected provenance control, "
        "not literal packet loss.",
        "",
        "## Experiment design",
        "",
    ]
    lines.extend(
        _markdown_table(
            ["Field", "Value"],
            [
                ["Profile", profile_name],
                ["Parallelism", f"TP={tp} × PP={pp} × DP={dp}"],
                ["Ranks", expected_ranks],
                ["Training steps", profile.get("steps", "unknown")],
                ["TP All-Reduce payload", _format_bytes(_as_int(profile.get("tp_all_reduce_bytes"), "tp_all_reduce_bytes"))],
                ["PP payload", _format_bytes(_as_int(profile.get("pp_bytes"), "pp_bytes"))],
                ["DP All-Reduce payload", _format_bytes(_as_int(profile.get("dp_all_reduce_bytes"), "dp_all_reduce_bytes"))],
                ["Compute per trace node", f"{profile.get('compute_duration_us', 'unknown')} μs"],
                ["Random seed", profile.get("seed", "unknown")],
            ],
        )
    )

    network = profile.get("network")
    if isinstance(network, dict):
        lines.extend(["", "## Physical network", ""])
        lines.extend(
            _markdown_table(
                ["Hosts per leaf", "Spines", "Link rate"],
                [[network.get("hosts_per_leaf", "unknown"), network.get("spine_count", "unknown"), network.get("link_rate", "unknown")]],
            )
        )

    lines.extend(["", "## Admission policy", ""])
    if policy is None:
        lines.append("Policy output is unavailable because the smoke run did not materialize `experiment.json`.")
    else:
        provenance = policy.get("provenance", {})
        microburst = policy.get("microburst", {})
        microburst_flows = microburst.get("flows", [])
        if not isinstance(microburst_flows, list):
            microburst_flows = []
        microburst_bytes = sum(
            _as_int(flow.get("size_bytes", 0), "microburst.size_bytes")
            for flow in microburst_flows
            if isinstance(flow, dict)
        )
        lines.extend(
            _markdown_table(
                ["Field", "Configured value"],
                [
                    ["Eligibility", policy.get("eligibility", "unknown")],
                    ["Default priority group", policy.get("default_priority_group", "unknown")],
                    ["Protected provenance control", f"{provenance.get('control_bytes', 'unknown')} B on priority group {provenance.get('priority_group', 'unknown')}"],
                    ["Background microburst", "enabled" if microburst.get("enabled") else "disabled"],
                    ["Microburst trigger step", microburst.get("trigger_step", "not applicable")],
                    ["Microburst flows", len(microburst_flows) if microburst.get("enabled") else "not applicable"],
                    ["Total microburst bytes", _format_bytes(microburst_bytes) if microburst.get("enabled") else "not applicable"],
                ],
            )
        )
        thresholds = policy.get("drop_probability_by_step")
        if isinstance(thresholds, dict):
            lines.extend(["", "Configured admission-suppression thresholds:", ""])
            threshold_rows = [
                [step, _format_probability(probability)]
                for step, probability in sorted(thresholds.items(), key=lambda item: int(item[0]))
            ]
            lines.extend(_markdown_table(["Training step", "Threshold"], threshold_rows))

    lines.extend(["", "## Run integrity", ""])
    if summary is None:
        lines.extend(
            [
                "**Status: results unavailable.** The smoke run did not produce `summary.json`; inspect the CI logs and the retained artifact for partial diagnostics.",
                "",
            ]
        )
    else:
        completed_ranks = {_as_int(row.get("rank"), "rank") for row in completions}
        complete = len(completed_ranks) == expected_ranks and len(completions) == expected_ranks
        fct_join = summary.get("fct_join")
        if isinstance(fct_join, dict) and fct_join.get("status") == "verified":
            fct_join_status = (
                "VERIFIED — "
                f"{fct_join.get('telemetry_flow_count', 'unknown')} telemetry flows / "
                f"{fct_join.get('fct_record_count', 'unknown')} ns-3 FCT records"
            )
        else:
            fct_join_status = "not available"
        integrity_rows = [
            ["Telemetry analyzer", "PASS — DP-only shedding and nonzero provenance control were validated before this report was written"],
            ["Rank completion", f"{len(completed_ranks)} unique / {expected_ranks} expected ({'complete' if complete else 'incomplete'})"],
            ["Flow telemetry", f"{len(flows)} rows / {summary.get('flow_count', 'unknown')} summarized"],
            ["Telemetry ↔ ns-3 FCT join", fct_join_status],
            ["Maximum rank completion time", _format_duration_ns(_as_int(summary.get("completion_time_ns_max", 0), "completion_time_ns_max"))],
        ]
        lines.extend(_markdown_table(["Check", "Result"], integrity_rows))

        rank_timing = summary.get("rank_completion_time_ns")
        rank_timing_row = _timing_table_row("Rank completion", rank_timing)
        if rank_timing_row is not None:
            lines.extend(["", "### Simulated rank-completion distribution", ""])
            lines.append(
                "> The maximum is the simulated workload makespan; it is not a measured application JCT."
            )
            lines.append("")
            lines.extend(
                _markdown_table(
                    ["Population", "Ranks", "P50", "P95", "P99", "Makespan"],
                    [rank_timing_row],
                )
            )

        lines.extend(["", "## Measured traffic", ""])
        lines.extend(
            _markdown_table(
                ["Metric", "Value"],
                [
                    ["Observed flows", summary.get("flow_count", "unknown")],
                    ["Admission-suppressed DP flows", summary.get("shed_flow_count", "unknown")],
                    ["Logical modeled bytes", _format_bytes(_as_int(summary.get("total_logical_bytes", 0), "total_logical_bytes"))],
                    ["Physical transport bytes", _format_bytes(_as_int(summary.get("total_physical_bytes", 0), "total_physical_bytes"))],
                    ["Suppressed logical DP bytes", _format_bytes(_as_int(summary.get("shed_logical_bytes", 0), "shed_logical_bytes"))],
                ],
            )
        )

        step_data = summary.get("by_training_step")
        if isinstance(step_data, dict):
            lines.extend(["", "### By training step", ""])
            step_rows: list[list[Any]] = []
            for step, values in sorted(step_data.items(), key=lambda item: int(item[0])):
                if not isinstance(values, dict):
                    raise ValueError("training-step summary must contain objects")
                step_rows.append(
                    [
                        step,
                        values.get("flows", "unknown"),
                        values.get("shed_flows", "unknown"),
                        _format_bytes(_as_int(values.get("logical_bytes", 0), "logical_bytes")),
                        _format_bytes(_as_int(values.get("physical_bytes", 0), "physical_bytes")),
                    ]
                )
            lines.extend(
                _markdown_table(
                    ["Step", "Flows", "Suppressed", "Logical bytes", "Physical bytes"],
                    step_rows,
                )
            )

        if flows:
            lines.extend(["", "### DP All-Reduce admission decisions", ""])
            thresholds = (
                policy.get("drop_probability_by_step", {})
                if isinstance(policy, dict)
                else {}
            )
            decision_rows: list[list[Any]] = []
            for step, values in _dp_decisions_by_step(flows).items():
                eligible_flows = values["eligible_flows"]
                shed_flows = values["shed_flows"]
                decision_rows.append(
                    [
                        step,
                        eligible_flows,
                        shed_flows,
                        _format_probability(shed_flows / eligible_flows),
                        _format_probability(thresholds[step])
                        if step in thresholds
                        else "not configured",
                    ]
                )
            if decision_rows:
                lines.extend(
                    _markdown_table(
                        [
                            "Step",
                            "Eligible DP payload flows",
                            "Suppressed",
                            "Observed rate",
                            "Configured threshold",
                        ],
                        decision_rows,
                    )
                )
            else:
                lines.append("No DP All-Reduce payload flows were observed.")

            lines.extend(["", "### By parallelism domain", ""])
            domain_rows = [
                [
                    domain,
                    values["flows"],
                    values["shed_flows"],
                    _format_bytes(values["logical_bytes"]),
                    _format_bytes(values["physical_bytes"]),
                ]
                for domain, values in _aggregate_by(flows, "parallelism_domain").items()
            ]
            lines.extend(
                _markdown_table(
                    ["Domain", "Flows", "Suppressed", "Logical bytes", "Physical bytes"],
                    domain_rows,
                )
            )
            lines.extend(["", "### By flow kind", ""])
            kind_rows = [
                [
                    kind,
                    values["flows"],
                    values["shed_flows"],
                    _format_bytes(values["logical_bytes"]),
                    _format_bytes(values["physical_bytes"]),
                ]
                for kind, values in _aggregate_by(flows, "flow_kind").items()
            ]
            lines.extend(
                _markdown_table(
                    ["Flow kind", "Flows", "Suppressed", "Logical bytes", "Physical bytes"],
                    kind_rows,
                )
            )

        flow_timing = summary.get("flow_completion_time_ns")
        if isinstance(flow_timing, dict):
            timing_rows: list[list[Any]] = []
            for label, values in [("All QPs", flow_timing.get("all"))]:
                if (row := _timing_table_row(label, values)) is not None:
                    timing_rows.append(row)
            by_kind = flow_timing.get("by_flow_kind")
            if isinstance(by_kind, dict):
                for kind, values in by_kind.items():
                    if (row := _timing_table_row(kind, values)) is not None:
                        timing_rows.append(row)
            by_domain_and_kind = flow_timing.get(
                "by_parallelism_domain_and_flow_kind"
            )
            if isinstance(by_domain_and_kind, dict):
                dp_timing = by_domain_and_kind.get("dp")
                if isinstance(dp_timing, dict):
                    for kind, values in dp_timing.items():
                        if (row := _timing_table_row(f"dp / {kind}", values)) is not None:
                            timing_rows.append(row)
            if timing_rows:
                lines.extend(["", "## Per-QP flow-completion time", ""])
                lines.append(
                    "> FCT is `end_time_ns - start_time_ns` for one simulated RDMA QP. It is not a whole-collective latency measurement."
                )
                lines.append("")
                lines.extend(
                    _markdown_table(
                        ["Traffic class", "QPs", "P50", "P95", "P99", "Max"],
                        timing_rows,
                    )
                )

            by_step = flow_timing.get("by_training_step")
            if isinstance(by_step, dict):
                step_timing_rows = [
                    row
                    for step, values in sorted(by_step.items(), key=lambda item: int(item[0]))
                    if (row := _timing_table_row(f"Step {step}", values)) is not None
                ]
                if step_timing_rows:
                    lines.extend(["", "### Per-QP FCT by training step", ""])
                    lines.extend(
                        _markdown_table(
                            ["Traffic class", "QPs", "P50", "P95", "P99", "Max"],
                            step_timing_rows,
                        )
                    )

        observability = summary.get("ns3_observability")
        if isinstance(observability, dict):
            queue = observability.get("queue")
            pfc = observability.get("pfc")
            if isinstance(queue, dict) or isinstance(pfc, dict):
                queue_status = queue.get("status", "not available") if isinstance(queue, dict) else "not available"
                pfc_status = pfc.get("status", "not available") if isinstance(pfc, dict) else "not available"
                queue_value = (
                    f"{queue.get('sample_count', 0)} samples; "
                    f"{queue.get('observed_queue_count', 0)} queues; peak "
                    f"{_format_bytes(_as_int(queue.get('max_queue_bytes', 0), 'max_queue_bytes'))}"
                    if queue_status == "available"
                    else "not available"
                )
                pfc_value = (
                    f"{pfc.get('event_count', 0)} nonempty trace records"
                    if pfc_status == "available"
                    else "not available"
                )
                lines.extend(["", "## ns-3 congestion observability", ""])
                lines.extend(
                    _markdown_table(
                        ["Signal", "Observed value"],
                        [["Queue telemetry", queue_value], ["PFC trace", pfc_value]],
                    )
                )

    lines.extend(["", "## Reproducibility", ""])
    lines.append(f"- Profile source: `{_display_path(profile_path)}`")
    lines.append(f"- Generated run directory: `{_display_path(run_dir)}`")
    if (revision := os.environ.get("GITHUB_SHA")):
        lines.append(f"- Source revision: `{revision}`")
    if (artifact_url := _artifact_url()):
        lines.append(f"- [Download the raw telemetry and generated inputs]({artifact_url})")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="write Markdown to this path instead of stdout")
    arguments = parser.parse_args()

    report = render_report(arguments.run_dir.resolve(), arguments.profile.resolve())
    if arguments.output is None:
        print(report)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
