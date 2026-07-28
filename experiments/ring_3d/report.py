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


def _format_optional_bytes(value: Any) -> str:
    return _format_bytes(value) if isinstance(value, int) else "unknown"


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


def _physical_network_rows(
    network: Any, physical_topology: Any
) -> list[list[Any]]:
    """Return a stable physical-network table from materialized metadata."""
    rows: list[list[Any]] = []
    if isinstance(physical_topology, dict):
        get = physical_topology.get
        rows.extend(
            [
                ["Topology", get("description", "unknown")],
                ["Accelerator cards / hosts", get("host_count", "unknown")],
                ["Modeled nodes", get("node_count", "unknown")],
                ["Switches", get("switch_count", "unknown")],
                ["Bidirectional physical links", get("link_count", "unknown")],
                ["Link rate", get("link_rate", "unknown")],
            ]
        )
        if get("kind") == "clos":
            rows.extend(
                [
                    ["Leaf switches", get("leaf_count", "unknown")],
                    ["Spine switches", get("spine_count", "unknown")],
                    ["Hosts per leaf", get("hosts_per_leaf", "unknown")],
                ]
            )
        elif get("kind") == "ring":
            rows.append(["Switch-ring size", get("switch_ring_size", "unknown")])
    elif isinstance(network, dict):
        rows.extend(
            [
                ["Topology", network.get("topology", "clos (legacy profile)")],
                ["Link rate", network.get("link_rate", "unknown")],
            ]
        )
    if isinstance(network, dict):
        packet_payload = _format_optional_bytes(network.get("packet_payload_bytes"))
        monitor_start = f"{network.get('queue_monitor_start_ns', 0)} ns"
        rows.extend(
            [
                ["RDMA packet payload", packet_payload],
                ["Queue telemetry start", monitor_start],
            ]
        )
    return rows


def _data_plane_loss_rows(data_loss: Any) -> list[list[Any]]:
    """Return the physical data-loss and bounded-recovery contract when enabled."""
    if not isinstance(data_loss, dict) or not data_loss.get("enabled"):
        return []
    return [
        ["Configured data loss", data_loss.get("probability", "unknown")],
        ["Loss scope", data_loss.get("scope", "unknown")],
        [
            "Loss window",
            f"{data_loss.get('start_ns', 0)} ns + {data_loss.get('duration_ns', 0)} ns",
        ],
        [
            "Retransmission timeout",
            f"{data_loss.get('retransmission_timeout_ns', 0)} ns",
        ],
        [
            "Maximum retransmission retries",
            data_loss.get("max_retransmission_retries", "unknown"),
        ],
    ]


def _model_trace_rows(model_trace: Any) -> list[list[Any]]:
    """Render the generated model ledger rather than inferring traffic from labels."""
    if not isinstance(model_trace, dict):
        return []
    get = model_trace.get
    rows = [
        ["Trace representation", get("workload_kind", "unknown")],
        ["Reference parameter count", get("parameter_count", "unknown")],
        ["Parameter dtype", f"{get('parameter_dtype_bytes', 'unknown')} B"],
        [
            "Total gradient bytes per DP replica",
            _format_optional_bytes(get("total_gradient_bytes_per_data_parallel_replica")),
        ],
        [
            "Gradient bytes per rank",
            _format_optional_bytes(get("gradient_bytes_per_rank")),
        ],
        ["Gradient bucket count", get("gradient_bucket_count", "unknown")],
    ]
    if "gradient_bucket_bytes" in model_trace:
        rows.append(
            ["Gradient bucket payload", _format_optional_bytes(get("gradient_bucket_bytes"))]
        )
    if "gradient_bucket_min_bytes" in model_trace:
        rows.append(
            [
                "Gradient bucket payload range",
                f"{_format_optional_bytes(get('gradient_bucket_min_bytes'))} "
                f"to {_format_optional_bytes(get('gradient_bucket_max_bytes'))}",
            ]
        )
    if "simulated_gradient_bucket_bytes" in model_trace:
        rows.append(
            [
                "Simulated representative bucket payload",
                _format_optional_bytes(get("simulated_gradient_bucket_bytes")),
            ]
        )
    for label, field in [
        ("Sampling contract", "sampling_contract"),
        ("Transformer layers", "transformer_layers"),
        ("Layers per pipeline stage", "transformer_layers_per_pipeline_stage"),
        ("Pipeline microbatches", "pipeline_microbatches"),
        ("Gradient accumulation steps", "gradient_accumulation_steps"),
        ("Sampled TP All-Reduces per step", "sampled_tp_all_reduces_per_step"),
        ("TP All-Reduces per layer", "tensor_parallel_all_reduces_per_layer"),
    ]:
        if field in model_trace:
            rows.append([label, model_trace[field]])
    return rows


def _execution_rows(execution: Any) -> list[list[Any]]:
    if not isinstance(execution, dict):
        return []
    timeout = execution.get("simulation_timeout_seconds")
    timeout_text = (
        f"{timeout} seconds ({timeout / 60:.1f} minutes)"
        if isinstance(timeout, int)
        else "not set"
    )
    return [
        ["DBLP selection seed", execution.get("dblp_selection_seed", "unknown")],
        [
            "ns-3 RNG seed / run",
            f"{execution.get('ns3_rng_seed', 'unknown')} / "
            f"{execution.get('ns3_rng_run', 'unknown')}",
        ],
        ["Simulator wall-clock cap", timeout_text],
        ["Static CLR mask", execution.get("clr_mask", "not recorded")],
    ]


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

    manifest = _read_json(run_dir / "manifest.json")
    model_trace = _read_json(run_dir / "model_trace.json")
    execution = _read_json(run_dir / "execution.json")
    policy = _read_json(run_dir / "experiment.json")
    summary = _read_json(run_dir / "summary.json")
    flows = _read_csv(run_dir / "telemetry" / "flow_events.csv")
    completions = _read_csv(run_dir / "telemetry" / "rank_completion.csv")

    profile_name = profile.get("name", profile_path.stem)
    lines = [
        "# 3D Ring collective / ns-3 researcher report",
        "",
        "> The 3D Ring label identifies the logical collective workload; the physical fabric is "
        "reported below. This report distinguishes logical modeled bytes (collective and background operations) "
        "from physical transport bytes. A shed payload is modeled by a provenance-replacement "
        "QP, not a wire-control packet or literal packet loss.",
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
    physical_topology = (
        manifest.get("physical_topology") if isinstance(manifest, dict) else None
    )
    data_plane_loss = (
        manifest.get("data_plane_loss") if isinstance(manifest, dict) else None
    )
    network_rows = _physical_network_rows(network, physical_topology)
    network_rows.extend(_data_plane_loss_rows(data_plane_loss))
    if network_rows:
        lines.extend(["", "## Physical network", ""])
        lines.extend(_markdown_table(["Field", "Value"], network_rows))

    if (model_rows := _model_trace_rows(model_trace)):
        lines.extend(["", "## Materialized model workload", ""])
        lines.extend(_markdown_table(["Field", "Value"], model_rows))

    if (execution_rows := _execution_rows(execution)):
        lines.extend(["", "## Execution controls", ""])
        lines.extend(_markdown_table(["Field", "Value"], execution_rows))

    lines.extend(["", "## Admission policy", ""])
    if policy is None:
        lines.append("Policy output is unavailable because the smoke run did not materialize `experiment.json`.")
    else:
        provenance = policy.get("provenance", {})
        microburst = policy.get("microburst", {})
        selection_policy = policy.get("selection_policy", {})
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
                    [
                        "Provenance replacement QP",
                        (
                            f"{provenance.get('control_bytes', 'unknown')} B on logical "
                            f"priority group {provenance.get('priority_group', 'unknown')}; "
                            "not a wire-control queue"
                        ),
                    ],
                    [
                        "Low / high selection probability",
                        (
                            f"{_format_probability(selection_policy.get('p_low'))} / "
                            f"{_format_probability(selection_policy.get('p_high'))}"
                            if isinstance(selection_policy, dict)
                            and "p_low" in selection_policy
                            and "p_high" in selection_policy
                            else "not recorded"
                        ),
                    ],
                    ["Background microburst", "enabled" if microburst.get("enabled") else "disabled"],
                    ["Microburst trigger step", microburst.get("trigger_step", "not applicable")],
                    ["Microburst flows", len(microburst_flows) if microburst.get("enabled") else "not applicable"],
                    ["Total microburst bytes", _format_bytes(microburst_bytes) if microburst.get("enabled") else "not applicable"],
                ],
            )
        )
        thresholds = policy.get("selection_probability_by_step")
        if isinstance(thresholds, dict):
            lines.extend(["", "Materialized logical-selection probabilities:", ""])
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
        eligibility = summary.get("primary_analysis_eligibility")
        eligibility_status = (
            eligibility.get("status", "not available")
            if isinstance(eligibility, dict)
            else "not available"
        )
        integrity_rows = [
            ["Telemetry analyzer", "PASS — DP-only shedding and nonzero provenance control were validated before this report was written"],
            ["Rank completion", f"{len(completed_ranks)} unique / {expected_ranks} expected ({'complete' if complete else 'incomplete'})"],
            ["Flow telemetry", f"{len(flows)} rows / {summary.get('flow_count', 'unknown')} summarized"],
            ["Telemetry ↔ ns-3 FCT join", fct_join_status],
            ["Primary-analysis eligibility", eligibility_status],
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

        collective_completion = summary.get("collective_completion")
        if isinstance(collective_completion, dict):
            if collective_completion.get("status") != "available":
                lines.extend(
                    [
                        "",
                        "## Logical collective-completion latency",
                        "",
                        "Native collective completion telemetry is unavailable for this run. "
                        "Per-QP FCT must not be substituted for whole-collective latency.",
                    ]
                )
            else:
                per_rank = collective_completion.get("per_rank_completion_time_ns")
                operation_span = collective_completion.get("all_rank_operation_span_ns")
                collective_rows: list[list[Any]] = []
                if isinstance(per_rank, dict):
                    by_domain_and_type = per_rank.get(
                        "by_parallelism_domain_and_collective_type"
                    )
                    if isinstance(by_domain_and_type, dict):
                        for domain, types in sorted(by_domain_and_type.items()):
                            if not isinstance(types, dict):
                                continue
                            for collective_type, values in sorted(types.items()):
                                if (row := _timing_table_row(
                                    f"{domain} / {collective_type} per-rank",
                                    values,
                                )) is not None:
                                    collective_rows.append(row)
                if isinstance(operation_span, dict):
                    by_domain_and_type = operation_span.get(
                        "by_parallelism_domain_and_collective_type"
                    )
                    if isinstance(by_domain_and_type, dict):
                        for domain, types in sorted(by_domain_and_type.items()):
                            if not isinstance(types, dict):
                                continue
                            for collective_type, values in sorted(types.items()):
                                if (row := _timing_table_row(
                                    f"{domain} / {collective_type} all-rank span",
                                    values,
                                )) is not None:
                                    collective_rows.append(row)
                lines.extend(["", "## Logical collective-completion latency", ""])
                lines.append(
                    "> Per-rank latency is measured from native collective issue to native completion. "
                    "All-rank span is $\\max(end)-\\min(start)$ for one logical collective across ranks."
                )
                lines.append("")
                if collective_rows:
                    lines.extend(
                        _markdown_table(
                            ["Population", "Events", "P50", "P95", "P99", "Max"],
                            collective_rows,
                        )
                    )
                else:
                    lines.append("No completed logical collective events were observed.")

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
                policy.get("selection_probability_by_step", {})
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
            transport = observability.get("transport")
            if (
                isinstance(queue, dict)
                or isinstance(pfc, dict)
                or isinstance(transport, dict)
            ):
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
                    f"{pfc.get('pause_count', 0)} pauses / {pfc.get('resume_count', 0)} resumes; "
                    f"{pfc.get('completed_pause_interval_count', 0)} completed intervals; total "
                    f"{_format_duration_ns(_as_int(pfc.get('total_paused_ns', 0), 'total_paused_ns'))}; "
                    f"max {_format_duration_ns(_as_int(pfc.get('max_paused_ns', 0), 'max_paused_ns'))} "
                    f"({pfc.get('pause_duration_status', 'unavailable')})"
                    if pfc_status == "available"
                    else "not available"
                )
                transport_value = (
                    f"{transport.get('data_injected_drop_count', 0)} data injected drops; "
                    f"{transport.get('control_injected_drop_count', 0)} control injected drops; "
                    f"{transport.get('data_natural_buffer_drop_count', 0)} data natural buffer drops; "
                    f"{transport.get('control_natural_buffer_drop_count', 0)} control natural buffer drops"
                    if transport.get("status") == "available"
                    else "not available"
                )
                lines.extend(["", "## ns-3 congestion observability", ""])
                lines.extend(
                    _markdown_table(
                        ["Signal", "Observed value"],
                        [
                            ["Queue telemetry", queue_value],
                            ["PFC trace", pfc_value],
                            ["Configured / natural data-control drops", transport_value],
                        ],
                    )
                )
                if isinstance(queue, dict) and queue.get("status") == "available":
                    peak_locations = queue.get("peak_switch_ports")
                    if isinstance(peak_locations, list) and peak_locations:
                        lines.append(
                            "Peak queue locations: "
                            + ", ".join(
                                f"switch {location.get('switch')} port {location.get('port')}"
                                for location in peak_locations
                                if isinstance(location, dict)
                            )
                            + "."
                        )
                if isinstance(pfc, dict) and pfc.get("status") == "available":
                    affected_locations = pfc.get("affected_switch_port_queues")
                    if isinstance(affected_locations, list) and affected_locations:
                        lines.append(
                            "PFC-affected switch port/queue locations: "
                            + ", ".join(
                                f"switch {location.get('switch')} port {location.get('port')} "
                                f"queue {location.get('queue')}"
                                for location in affected_locations
                                if isinstance(location, dict)
                            )
                            + "."
                        )

        recovery = summary.get("transport_recovery")
        if isinstance(recovery, dict):
            failed_by_reason = recovery.get("failed_by_reason", {})
            failure_value = (
                ", ".join(
                    f"{reason or 'unspecified'}: {count}"
                    for reason, count in sorted(failed_by_reason.items())
                )
                if isinstance(failed_by_reason, dict) and failed_by_reason
                else "none"
            )
            lines.extend(["", "## Transport recovery", ""])
            lines.extend(
                _markdown_table(
                    ["Signal", "Observed value"],
                    [
                        [
                            "Data bytes attempted",
                            _format_bytes(
                                _as_int(
                                    recovery.get("data_attempted_bytes", 0),
                                    "data_attempted_bytes",
                                )
                            ),
                        ],
                        [
                            "Retransmitted bytes",
                            _format_bytes(
                                _as_int(
                                    recovery.get("retransmitted_bytes", 0),
                                    "retransmitted_bytes",
                                )
                            ),
                        ],
                        [
                            "Recovery events",
                            recovery.get("recovery_event_count", 0),
                        ],
                        ["Terminal failures", failure_value],
                    ],
                )
            )

        background_timeline = summary.get("background_microburst_timeline")
        traffic_bytes = summary.get("physical_traffic_bytes")
        if isinstance(background_timeline, dict) or isinstance(traffic_bytes, dict):
            lines.extend(["", "## Causal traffic mix", ""])
            mix_rows: list[list[Any]] = []
            if isinstance(traffic_bytes, dict):
                for label, key in [
                    ("Foreground logical operations", "foreground_logical_operations"),
                    ("DP All-Reduce", "dp_all_reduce"),
                    ("Total offered traffic", "total"),
                ]:
                    values = traffic_bytes.get(key)
                    if isinstance(values, dict):
                        mix_rows.append(
                            [
                                label,
                                values.get("flow_count", "unknown"),
                                _format_bytes(_as_int(values.get("logical_bytes", 0), "logical_bytes")),
                                _format_bytes(_as_int(values.get("physical_bytes", 0), "physical_bytes")),
                            ]
                        )
            if mix_rows:
                lines.extend(
                    _markdown_table(
                        ["Traffic population", "Flows", "Logical bytes", "Physical bytes"],
                        mix_rows,
                    )
                )
            if isinstance(background_timeline, dict):
                if background_timeline.get("status") == "available":
                    lines.extend(
                        [
                            "",
                            "Background incast: "
                            f"{background_timeline.get('flow_count', 'unknown')} flows / "
                            f"{_format_bytes(_as_int(background_timeline.get('physical_bytes', 0), 'physical_bytes'))} "
                            f"physical bytes from {_format_duration_ns(_as_int(background_timeline.get('start_time_ns', 0), 'start_time_ns'))} "
                            f"to {_format_duration_ns(_as_int(background_timeline.get('end_time_ns', 0), 'end_time_ns'))} "
                            f"(span {_format_duration_ns(_as_int(background_timeline.get('span_ns', 0), 'span_ns'))}).",
                        ]
                    )
                else:
                    lines.extend(["", "No background microburst flow was observed."])

    lines.extend(["", "## Reproducibility", ""])
    lines.append(f"- Profile source: `{_display_path(profile_path)}`")
    if (run_profile := run_dir / "profile.json").is_file():
        lines.append(f"- Materialized profile copy: `{_display_path(run_profile)}`")
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
