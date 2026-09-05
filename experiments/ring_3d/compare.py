#!/usr/bin/env python3
"""Run matched fixed-low and phase-aware selection experiments across fixed seeds."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Final

try:
    from .generate import (
        REPOSITORY_ROOT,
        dp_fan_in,
        load_profile,
        resolve_selection_policy,
    )
    from .run import fixed_p_low_baseline, run_experiment
except ImportError:
    from generate import (
        REPOSITORY_ROOT,
        dp_fan_in,
        load_profile,
        resolve_selection_policy,
    )
    from run import fixed_p_low_baseline, run_experiment


# Consecutive 8-digit chunks of π's decimal expansion ("31415926",
# "53589793", ...), taken in order with none screened or discarded — the
# leading-zero chunk "02884197" simply parses to 2884197. Sixteen paired
# seeds shrink the standard error of paired deltas to ~σ/4, which resolves
# the ±3–4% ECMP path-collision noise floor on p99 metrics. Keeping the CLI
# and CI defaults identical makes local reruns exactly reproduce CI's sweep.
DEFAULT_SEEDS = (
    31415926, 53589793, 23846264, 33832795, 2884197, 16939937,
    51058209, 74944592, 30781640, 62862089, 98628034, 82534211,
    70679821, 48086513, 28230664, 70938446,
)
T_CRITICAL_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def _metric(
    summary: dict[str, Any], path: tuple[str, ...], *, ratio: bool = False
) -> int | float:
    value: Any = summary
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"summary is missing comparison metric {'/'.join(path)}")
        value = value[key]
    if isinstance(value, bool):
        raise ValueError(f"comparison metric {'/'.join(path)} must be a number")
    if ratio:
        if not isinstance(value, (int, float)):
            raise ValueError(f"comparison metric {'/'.join(path)} must be a number")
        return float(value)
    if not isinstance(value, int):
        raise ValueError(f"comparison metric {'/'.join(path)} must be an integer")
    return value


METRICS = {
    "makespan_ns": ("rank_completion_time_ns", "max_ns"),
    "dp_all_reduce_collective_per_rank_p99_ns": (
        "collective_completion",
        "per_rank_completion_time_ns",
        "by_parallelism_domain_and_collective_type",
        "dp",
        "all_reduce",
        "p99_ns",
    ),
    "dp_all_reduce_collective_operation_span_p99_ns": (
        "collective_completion",
        "all_rank_operation_span_ns",
        "by_parallelism_domain_and_collective_type",
        "dp",
        "all_reduce",
        "p99_ns",
    ),
    "all_qp_fct_p99_ns": ("flow_completion_time_ns", "all", "p99_ns"),
    "foreground_logical_operation_physical_bytes": (
        "physical_traffic_bytes",
        "foreground_logical_operations",
        "physical_bytes",
    ),
    "dp_all_reduce_physical_bytes": (
        "physical_traffic_bytes",
        "dp_all_reduce",
        "physical_bytes",
    ),
    "total_physical_bytes": ("physical_traffic_bytes", "total", "physical_bytes"),
    "W": ("network_health", "W"),
}

BYTE_METRICS = {
    "foreground_logical_operation_physical_bytes",
    "dp_all_reduce_physical_bytes",
    "total_physical_bytes",
}
# Dimensionless metrics: they carry no nanoseconds and no bytes, and a zero
# baseline means the fabric has no such events rather than a division by zero.
RATIO_METRICS = {"W"}

BURST_STEP_SPAN_METRIC = "dp_all_reduce_span_burst_step_ns"
AFTERMATH_STEP_SPAN_METRIC = "dp_all_reduce_span_aftermath_step_ns"
_DP_SPAN_BY_STEP: Final = (
    "collective_completion",
    "dp_all_reduce_span_ns_by_training_step",
)


def comparison_metrics(burst_step: int | None, aftermath_step: int | None) -> dict[
    str, tuple[str, ...]
]:
    """Metric paths for one profile: the fixed set plus its congestion episode.

    The burst step is the profile's ``microburst_trigger_step`` and the
    aftermath step is the next one, which a run ending at the burst does not
    have. Both are omitted for a profile with no incast.
    """
    metrics = dict(METRICS)
    if burst_step is not None:
        metrics[BURST_STEP_SPAN_METRIC] = (*_DP_SPAN_BY_STEP, str(burst_step))
    if aftermath_step is not None:
        metrics[AFTERMATH_STEP_SPAN_METRIC] = (*_DP_SPAN_BY_STEP, str(aftermath_step))
    return metrics

# One terse sentence per metric codeword, rendered as a report appendix so a
# reader can decode every table row without leaving the page.
METRIC_GLOSSARY = {
    "makespan_ns": (
        "Latest rank-completion time across all ranks: simulated whole-"
        "workload wall clock, not a measured application JCT."
    ),
    "dp_all_reduce_collective_per_rank_p99_ns": (
        "p99 over per-rank DP All-Reduce latencies, native collective issue "
        "to native completion, one sample per rank per collective."
    ),
    "dp_all_reduce_collective_operation_span_p99_ns": (
        "p99 over whole-collective spans, max(end) - min(start) across all "
        "ranks of one DP All-Reduce: how long the slowest collective held "
        "the group."
    ),
    "all_qp_fct_p99_ns": (
        "p99 flow-completion time over every simulated RDMA QP. Secondary "
        "transport diagnostic: shed payloads re-enter as 64 B provenance "
        "QPs, so shedding itself shifts this population."
    ),
    "foreground_logical_operation_physical_bytes": (
        "Physical wire bytes of foreground logical operations (collectives "
        "and PP transfers); excludes background microburst traffic."
    ),
    "dp_all_reduce_physical_bytes": (
        "Physical wire bytes of DP All-Reduce traffic alone: the only "
        "traffic shedding is allowed to touch."
    ),
    "total_physical_bytes": (
        "Physical wire bytes of all offered traffic, foreground plus "
        "background."
    ),
    "W": (
        "Trimmed-on-admission payload bytes per offered byte, the "
        "pre-registered network-health signal of the best-effort fabric. "
        "Dimensionless; a lower value is a healthier fabric."
    ),
    BURST_STEP_SPAN_METRIC: (
        "Worst DP All-Reduce all-rank span at the microburst trigger step: "
        "how long the incast held the collective it landed on."
    ),
    AFTERMATH_STEP_SPAN_METRIC: (
        "Worst DP All-Reduce all-rank span at the step after the trigger: "
        "the queue backlog the burst left behind."
    ),
}
assert METRIC_GLOSSARY.keys() == comparison_metrics(1, 2).keys(), (
    "every comparison metric needs exactly one glossary sentence"
)


def compare_summaries(
    baseline: dict[str, Any],
    policy: dict[str, Any],
    metrics: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, dict[str, float | int]]:
    """Produce positive reductions when the policy is faster than baseline."""
    comparisons: dict[str, dict[str, float | int]] = {}
    for name, path in (METRICS if metrics is None else metrics).items():
        ratio = name in RATIO_METRICS
        baseline_value = _metric(baseline, path, ratio=ratio)
        policy_value = _metric(policy, path, ratio=ratio)
        reduction = baseline_value - policy_value
        if baseline_value == 0:
            # Both arms share the fabric, so a ratio the baseline never
            # observed the policy cannot observe either; the relative
            # reduction is zero, not undefined. Any other zero baseline is a
            # broken run.
            if not ratio or reduction != 0:
                raise ValueError(f"comparison baseline metric {name} must be nonzero")
            reduction_percent = 0.0
        else:
            reduction_percent = reduction * 100 / baseline_value
        comparisons[name] = {
            "baseline_ns": baseline_value,
            "policy_ns": policy_value,
            "reduction_ns": reduction,
            "reduction_percent": reduction_percent,
        }
    return comparisons


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sample_standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _confidence_interval_95(values: list[float]) -> list[float] | None:
    if len(values) < 2:
        return None
    critical = T_CRITICAL_95.get(len(values) - 1, 1.96)
    margin = critical * _sample_standard_deviation(values) / math.sqrt(len(values))
    mean = _mean(values)
    return [mean - margin, mean + margin]


def aggregate_comparisons(
    per_seed: list[dict[str, Any]],
    metrics_field: str = "metrics",
) -> dict[str, dict[str, float | int | list[float] | None]] | None:
    """Aggregate one per-seed metric set; None when the field is absent.

    Absence happens only for comparison artifacts recorded before the
    fixed-high arm existed; a mixed set is rejected by artifact validation.
    """
    if not per_seed:
        raise ValueError("at least one paired seed result is required")
    if any(metrics_field not in seed for seed in per_seed):
        if all(metrics_field not in seed for seed in per_seed):
            return None
        raise ValueError(
            f"comparison seeds must all record {metrics_field} or none of them"
        )
    names = list(per_seed[0][metrics_field])
    if any(list(seed[metrics_field]) != names for seed in per_seed):
        raise ValueError(
            f"comparison seeds must record the same {metrics_field} names"
        )
    aggregate: dict[str, dict[str, float | int | list[float] | None]] = {}
    for metric in names:
        entries = [seed[metrics_field][metric] for seed in per_seed]
        baseline_values = [float(entry["baseline_ns"]) for entry in entries]
        policy_values = [float(entry["policy_ns"]) for entry in entries]
        reductions = [float(entry["reduction_ns"]) for entry in entries]
        reductions_percent = [float(entry["reduction_percent"]) for entry in entries]
        aggregate[metric] = {
            "paired_seed_count": len(entries),
            "baseline_mean_ns": _mean(baseline_values),
            "policy_mean_ns": _mean(policy_values),
            "mean_reduction_ns": _mean(reductions),
            "mean_reduction_percent": _mean(reductions_percent),
            "reduction_standard_deviation_ns": _sample_standard_deviation(reductions),
            "reduction_ci95_ns": _confidence_interval_95(reductions),
        }
    return aggregate


def _read_summary(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    with summary_path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {summary_path}")
    return value


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"summary is missing object {field}")
    return value


def _nonnegative_int(value: Any, field: str, *, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"summary field {field} must be a nonnegative integer")
    return value


def congestion_evidence(summary: dict[str, Any]) -> dict[str, bool | int | str]:
    """Extract the raw switch signals required for a congestion claim.

    Buffer pressure leaves a regime-specific signature: a lossless PFC fabric
    pauses upstream ports, while a best-effort fabric rejects admission and
    can only leave trimmed or naturally dropped packets. The gate therefore
    demands the signature of the regime the run actually modeled; a summary
    that predates regime recording accepts either signature.
    """
    observability = _mapping(summary.get("ns3_observability"), "ns3_observability")
    queue = _mapping(observability.get("queue"), "ns3_observability.queue")
    pfc = _mapping(observability.get("pfc"), "ns3_observability.pfc")
    transport_value = observability.get("transport")
    transport = transport_value if isinstance(transport_value, dict) else {}
    recovery_value = summary.get("transport_recovery")
    recovery = recovery_value if isinstance(recovery_value, dict) else {}
    background = _mapping(
        summary.get("background_microburst_timeline"), "background_microburst_timeline"
    )
    queue_status = queue.get("status")
    pfc_status = pfc.get("status")
    background_status = background.get("status")
    regime = str(summary.get("flow_control_regime", "unknown"))
    max_queue_bytes = _nonnegative_int(
        queue.get("max_queue_bytes"), "ns3_observability.queue.max_queue_bytes"
    )
    completed_pause_intervals = _nonnegative_int(
        pfc.get("completed_pause_interval_count"),
        "ns3_observability.pfc.completed_pause_interval_count",
    )
    background_physical_bytes = _nonnegative_int(
        background.get("physical_bytes"),
        "background_microburst_timeline.physical_bytes",
    )
    data_natural_buffer_drops = _nonnegative_int(
        transport.get("data_natural_buffer_drop_count"),
        "ns3_observability.transport.data_natural_buffer_drop_count",
    )
    trim_notifications = _nonnegative_int(
        recovery.get("trim_notification_count"),
        "transport_recovery.trim_notification_count",
    )
    pause_signature = completed_pause_intervals > 0
    rejection_signature = data_natural_buffer_drops + trim_notifications > 0
    pressure_signature = {
        "lossless_pfc": pause_signature,
        "best_effort": rejection_signature,
    }.get(regime, pause_signature or rejection_signature)
    return {
        "queue_status": str(queue_status),
        "pfc_status": str(pfc_status),
        "background_microburst_status": str(background_status),
        "flow_control_regime": regime,
        "max_queue_bytes": max_queue_bytes,
        "completed_pause_interval_count": completed_pause_intervals,
        "trim_notification_count": trim_notifications,
        "background_physical_bytes": background_physical_bytes,
        "transport_status": str(transport.get("status", "not_available")),
        "data_natural_buffer_drop_count": data_natural_buffer_drops,
        "control_natural_buffer_drop_count": _nonnegative_int(
            transport.get("control_natural_buffer_drop_count"),
            "ns3_observability.transport.control_natural_buffer_drop_count",
        ),
        "congestion_established": (
            queue_status == "available"
            and pfc_status == "available"
            and background_status == "available"
            and max_queue_bytes > 0
            and pressure_signature
            and background_physical_bytes > 0
        ),
    }


def require_congestion(
    summary: dict[str, Any], run_label: str
) -> dict[str, bool | int | str]:
    """Reject runs without observed microburst traffic, queueing, and PFC recovery."""
    evidence = congestion_evidence(summary)
    if not evidence["congestion_established"]:
        raise ValueError(
            f"{run_label} did not establish required congestion: {evidence}"
        )
    return evidence


def require_finite_buffer_data_drop(
    summary: dict[str, Any], run_label: str
) -> dict[str, bool | int | str]:
    """Reject congestion runs without an observed natural data-buffer drop."""
    evidence = congestion_evidence(summary)
    if (
        evidence["transport_status"] != "available"
        or evidence["data_natural_buffer_drop_count"] == 0
    ):
        raise ValueError(
            f"{run_label} did not establish finite-buffer data loss: {evidence}"
        )
    return evidence


def require_primary_analysis(summary: dict[str, Any], run_label: str) -> None:
    """Reject a paired metric extracted from incomplete native telemetry."""
    eligibility = _mapping(
        summary.get("primary_analysis_eligibility"), "primary_analysis_eligibility"
    )
    if eligibility.get("status") != "eligible":
        raise ValueError(
            f"{run_label} is ineligible for primary analysis: {eligibility}"
        )


def _format_duration_ns(value: float) -> str:
    if value < 1_000:
        return f"{value:.2f} ns"
    if value < 1_000_000:
        return f"{value / 1_000:.2f} μs"
    return f"{value / 1_000_000:.2f} ms"


def _format_ratio(value: float) -> str:
    return f"{value:.4f}"


def _format_bytes(value: float) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{value:.0f} B"
        value /= 1024
    raise AssertionError("unreachable")


_ARM_TITLES = {
    "fixed_p_low_baseline": "Fixed-low baseline",
    "fixed_p_high_baseline": "Fixed-high baseline",
    "dblp_policy": "Phase-aware policy",
}
_EVIDENCE_COLUMNS = (
    ("trim_notification_count", "Trims"),
    ("data_natural_buffer_drop_count", "Natural drops"),
    ("completed_pause_interval_count", "PFC pauses"),
    ("max_queue_bytes", "Peak queue"),
)


def _metric_table(
    aggregate: dict[str, Any], value_labels: tuple[str, str]
) -> list[str]:
    baseline_label, treatment_label = value_labels
    lines = [
        f"| Metric | {baseline_label} mean | {treatment_label} mean "
        "| Mean reduction | 95% CI of reduction | Mean reduction % |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for metric, values in aggregate.items():
        if metric in RATIO_METRICS:
            format_value = _format_ratio
        elif metric in BYTE_METRICS:
            format_value = _format_bytes
        else:
            format_value = _format_duration_ns
        ci = values["reduction_ci95_ns"]
        ci_text = (
            f"[{format_value(ci[0])}, {format_value(ci[1])}]"
            if isinstance(ci, list)
            else "not available (one seed)"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    metric,
                    format_value(float(values["baseline_mean_ns"])),
                    format_value(float(values["policy_mean_ns"])),
                    format_value(float(values["mean_reduction_ns"])),
                    ci_text,
                    f"{float(values['mean_reduction_percent']):.2f}%",
                ]
            )
            + " |"
        )
    return lines


def _coordinate_lines(comparison: dict[str, Any]) -> list[str]:
    """Expose every reproduction-relevant coordinate the artifact carries."""
    policy = comparison.get("selection_policy") or {}
    baseline = policy.get("baseline") or {}
    treatment = policy.get("policy") or {}
    coordinates = [
        ("Profile", comparison.get("profile", "not recorded")),
        ("Seeds", ", ".join(str(seed) for seed in comparison.get("seeds", []))),
        (
            "DP all-reduce implementation",
            comparison.get("dp_all_reduce_implementation", "not recorded"),
        ),
        ("DP fan-in", comparison.get("dp_fan_in", "not recorded")),
        (
            "Microburst source count",
            comparison.get("microburst_source_count", "not recorded"),
        ),
        (
            "Microburst trigger step",
            comparison.get("microburst_trigger_step", "not recorded"),
        ),
        (
            "Fixed-low baseline selection",
            f"p_low = p_high = {baseline.get('p_low', 'not recorded')}",
        ),
        (
            "Fixed-high baseline selection",
            f"p_low = p_high = {treatment.get('p_high', 'not recorded')} "
            "(deliberately exposes critical steps)",
        ),
        (
            "Phase-aware policy selection",
            f"p_low = {treatment.get('p_low', 'not recorded')}, "
            f"p_high = {treatment.get('p_high', 'not recorded')}",
        ),
        (
            "Per-simulator timeout",
            f"{comparison.get('simulation_timeout_seconds', 'not recorded')} s",
        ),
    ]
    lines = ["| Coordinate | Value |", "| --- | --- |"]
    lines.extend(f"| {name} | {value} |" for name, value in coordinates)
    return lines


def _evidence_lines(per_seed: list[dict[str, Any]]) -> list[str]:
    """Per-arm means of the raw switch counters, one row per arm."""
    arm_names = [
        arm for arm in _ARM_TITLES if arm in (per_seed[0].get("congestion") or {})
    ]
    if not arm_names:
        return ["Raw congestion evidence was not recorded."]
    regimes = {
        str((seed_entry["congestion"][arm]).get("flow_control_regime", "unknown"))
        for seed_entry in per_seed
        for arm in arm_names
    }
    lines = [
        f"Flow-control regime: {', '.join(sorted(regimes))}. "
        "Values are per-seed means of raw switch counters.",
        "",
        "| Arm | " + " | ".join(label for _, label in _EVIDENCE_COLUMNS) + " |",
        "| --- | " + " | ".join("---:" for _ in _EVIDENCE_COLUMNS) + " |",
    ]
    for arm in arm_names:
        cells = []
        for field, _ in _EVIDENCE_COLUMNS:
            values = [
                float(seed_entry["congestion"][arm].get(field, 0))
                for seed_entry in per_seed
            ]
            mean = _mean(values)
            cells.append(
                _format_bytes(mean) if field == "max_queue_bytes" else f"{mean:.1f}"
            )
        lines.append(f"| {_ARM_TITLES[arm]} | " + " | ".join(cells) + " |")
    return lines


def render_comparison_report(comparison: dict[str, Any]) -> str:
    """Render a self-contained Markdown record of the matched comparison."""
    congestion_statement = (
        "Every arm passed the required raw-signal gate: "
        "background microburst traffic, a nonzero queue peak, and the fabric's "
        "buffer-pressure signature (completed PFC pause intervals on a lossless "
        "fabric; trimmed or naturally dropped packets on a best-effort fabric)."
        if comparison.get("congestion_required")
        else "Raw congestion signals were recorded but not enforced as a comparison gate."
    )
    finite_buffer_statement = (
        "Every run also recorded at least one natural data-plane switch admission "
        "or egress-queue drop; configured injection remains a separate signal."
        if comparison.get("finite_buffer_data_drop_required")
        else "Natural finite-buffer data loss was recorded when available but not enforced."
    )
    lines = [
        "# Matched phase-aware selection comparison",
        "",
        "> Every arm of a seed uses identical traces, topology, microburst "
        "configuration, CLR mask, and ns-3 random stream; successive seeds use "
        "distinct runs. The fixed-low baseline holds the strict bound "
        "everywhere, the fixed-high baseline deliberately sheds at the "
        "permissive bound through critical steps to measure the headroom an "
        "unbounded policy would take, and the phase-aware policy switches "
        "bounds on the CLR mask.",
        "",
        congestion_statement,
        finite_buffer_statement,
        "",
        "## Experiment coordinates",
        "",
        *_coordinate_lines(comparison),
        "",
        "## Policy relief over the fixed-low baseline",
        "",
        *_metric_table(comparison["aggregate"], ("Fixed-low", "Policy")),
    ]
    headroom = comparison.get("headroom_aggregate")
    if headroom:
        lines.extend(
            [
                "",
                "## Unbounded-shedding headroom (fixed-high over fixed-low)",
                "",
                *_metric_table(headroom, ("Fixed-low", "Fixed-high")),
                "",
                "The policy's claim is captured headroom: its relief should "
                "approach the fixed-high ceiling while critical steps stay at "
                "the strict bound, which the fixed-high arm abandons.",
            ]
        )
    per_seed = comparison.get("per_seed") or []
    if per_seed:
        lines.extend(
            [
                "",
                "## Raw congestion evidence by arm",
                "",
                *_evidence_lines(per_seed),
            ]
        )
    lines.extend(
        [
            "",
            "Positive reductions favor the treatment column. Logical collective metrics include every completed "
            "DP All-Reduce regardless of whether its payload used provenance control; all-QP FCT is a "
            "secondary transport diagnostic. Physical-byte reductions are reported against foreground, DP, "
            "and total offered traffic. Do not interpret a single seed or a confidence interval spanning zero "
            "as evidence of a performance benefit.",
            "",
            "## Appendix: metric codewords",
            "",
            "| Codeword | Meaning |",
            "| --- | --- |",
            *(
                f"| `{name}` | {meaning} |"
                for name, meaning in METRIC_GLOSSARY.items()
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _write_comparison(output: Path, comparison: dict[str, Any]) -> None:
    """Persist a comparison and its Markdown report as one immutable bundle."""
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.json").write_text(
        json.dumps(comparison, indent=2) + "\n", encoding="utf-8"
    )
    (output / "comparison_report.md").write_text(
        render_comparison_report(comparison), encoding="utf-8"
    )


def _read_comparison(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


# Profiles live in exactly one directory, and everything from it down is
# common to every checkout of the repository.
_PROFILE_DIRECTORY: Final = ("experiments", "ring_3d", "profiles")


def repository_relative_profile(profile: Path) -> str:
    """Record a profile the way every checkout sees it, not this workspace.

    CI gives each seed of a sweep its own workspace, so an absolute path makes
    the artifacts of one experiment look like artifacts of several.
    """
    resolved = profile.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def profile_identity(profile: str) -> str:
    """Reduce a recorded profile path to its checkout-independent tail.

    Artifacts written against another checkout root still carry that root; a
    path outside the profile directory keeps the form it was recorded in.
    """
    parts = PurePosixPath(profile).parts
    width = len(_PROFILE_DIRECTORY)
    for index in range(len(parts) - width + 1):
        if parts[index : index + width] == _PROFILE_DIRECTORY:
            return PurePosixPath(*parts[index:]).as_posix()
    return profile


def aggregate_comparison_artifacts(comparison_paths: list[Path]) -> dict[str, Any]:
    """Combine independently executed one-seed comparisons without rerunning ns-3.

    The CI matrix gives every matched pair its own full job budget. This function
    validates that those artifacts describe one compatible experiment before
    constructing the same aggregate and confidence interval as a serial run.
    """
    if not comparison_paths:
        raise ValueError("at least one comparison artifact is required")

    profile: str | None = None
    selection_policy: dict[str, Any] | None = None
    require_congestion: bool | None = None
    require_finite_buffer_drop: bool | None = None
    simulation_timeout_seconds: int | None = None
    per_seed: list[dict[str, Any]] = []
    for path in comparison_paths:
        comparison = _read_comparison(path)
        artifact_profile = comparison.get("profile")
        if not isinstance(artifact_profile, str) or not artifact_profile:
            raise ValueError(f"comparison artifact {path} has no profile")
        identity = profile_identity(artifact_profile)
        if profile is None:
            profile = identity
        elif identity != profile:
            raise ValueError("comparison artifacts must use the same profile")

        artifact_policy = comparison.get("selection_policy")
        if not isinstance(artifact_policy, dict):
            raise ValueError(f"comparison artifact {path} has no selection policy")
        if selection_policy is None:
            selection_policy = artifact_policy
        elif artifact_policy != selection_policy:
            raise ValueError("comparison artifacts must use the same selection policy")

        artifact_congestion = comparison.get("congestion_required")
        if not isinstance(artifact_congestion, bool):
            raise ValueError(
                f"comparison artifact {path} has invalid congestion setting"
            )
        if require_congestion is None:
            require_congestion = artifact_congestion
        elif artifact_congestion != require_congestion:
            raise ValueError(
                "comparison artifacts must use the same congestion setting"
            )

        artifact_finite_buffer_drop = comparison.get(
            "finite_buffer_data_drop_required", False
        )
        if not isinstance(artifact_finite_buffer_drop, bool):
            raise ValueError(
                f"comparison artifact {path} has invalid finite-buffer drop setting"
            )
        if require_finite_buffer_drop is None:
            require_finite_buffer_drop = artifact_finite_buffer_drop
        elif artifact_finite_buffer_drop != require_finite_buffer_drop:
            raise ValueError(
                "comparison artifacts must use the same finite-buffer drop setting"
            )

        artifact_timeout = comparison.get("simulation_timeout_seconds")
        if isinstance(artifact_timeout, bool) or not isinstance(artifact_timeout, int):
            raise ValueError(
                f"comparison artifact {path} has invalid simulator timeout"
            )
        if simulation_timeout_seconds is None:
            simulation_timeout_seconds = artifact_timeout
        elif artifact_timeout != simulation_timeout_seconds:
            raise ValueError("comparison artifacts must use the same simulator timeout")

        artifact_per_seed = comparison.get("per_seed")
        if not isinstance(artifact_per_seed, list) or len(artifact_per_seed) != 1:
            raise ValueError(
                f"comparison artifact {path} must contain exactly one seed result"
            )
        seed_result = artifact_per_seed[0]
        if not isinstance(seed_result, dict):
            raise ValueError(f"comparison artifact {path} has an invalid seed result")
        seed = seed_result.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"comparison artifact {path} has an invalid seed")
        per_seed.append(seed_result)

    seeds = [entry["seed"] for entry in per_seed]
    if len(set(seeds)) != len(seeds):
        raise ValueError("comparison artifacts must not contain duplicate seeds")
    per_seed.sort(key=lambda entry: entry["seed"])
    # Profile equality is already enforced above, so the sweep coordinates of
    # the first artifact describe every artifact.
    first = _read_comparison(comparison_paths[0])
    return {
        "profile": profile,
        "selection_policy": selection_policy,
        "dp_all_reduce_implementation": first.get("dp_all_reduce_implementation"),
        "dp_fan_in": first.get("dp_fan_in"),
        "microburst_source_count": first.get("microburst_source_count"),
        "microburst_trigger_step": first.get("microburst_trigger_step"),
        "seeds": sorted(seeds),
        "congestion_required": require_congestion,
        "finite_buffer_data_drop_required": require_finite_buffer_drop,
        "simulation_timeout_seconds": simulation_timeout_seconds,
        "per_seed": per_seed,
        "aggregate": aggregate_comparisons(per_seed),
        "headroom_aggregate": aggregate_comparisons(per_seed, "headroom_metrics"),
    }


def run_comparison(
    profile: Path,
    output: Path,
    seeds: list[int],
    *,
    binary: Path | None = None,
    clean: bool = False,
    require_congestion_signals: bool = False,
    require_finite_buffer_data_drops: bool = False,
    simulation_timeout_seconds: int | None = None,
    p_low: float | None = None,
    p_high: float | None = None,
    only_arm: str | None = None,
    analyze_only: bool = False,
) -> dict[str, Any]:
    """Run the matched experiment pairs and retain their individual artifacts.

    ``only_arm`` runs a single arm's simulations and gates without building
    the comparison; ``analyze_only`` skips the simulations and builds the
    comparison from arm directories produced earlier. Together they let CI
    chain one job per arm, so the per-job wall-clock ceiling bounds one arm
    instead of the whole triple.
    """
    if not seeds:
        raise ValueError("at least one seed is required")
    if len(set(seeds)) != len(seeds):
        raise ValueError("comparison seeds must be unique")
    output = output.resolve()
    if output.exists() and clean:
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    profile_model = load_profile(profile.resolve())
    profile_policy = resolve_selection_policy(
        profile_model, p_low=p_low, p_high=p_high
    )
    baseline_p_low, baseline_p_high = fixed_p_low_baseline(profile_model)
    if p_low is not None:
        baseline_p_low = p_low
        baseline_p_high = p_low
    burst_step = (
        profile_model.microburst_trigger_step
        if profile_model.microburst_enabled
        else None
    )
    aftermath_step = (
        burst_step + 1
        if burst_step is not None and burst_step < profile_model.steps
        else None
    )
    metrics = comparison_metrics(burst_step, aftermath_step)

    per_seed: list[dict[str, Any]] = []
    for seed in seeds:
        seed_dir = output / f"seed_{seed}"
        # Three matched arms per seed. Fixed-low is the conservative control,
        # fixed-high deliberately sheds at the permissive rate through
        # critical steps to measure the headroom an unbounded policy would
        # take, and the phase-aware policy is the treatment. The claim is
        # that the policy captures most of the fixed-high headroom while
        # keeping critical steps at the strict bound.
        arms = {
            "fixed_p_low_baseline": {
                "directory": seed_dir / "fixed_p_low_baseline",
                "label": f"seed {seed} fixed-p-low baseline",
                "p_low": baseline_p_low,
                "p_high": baseline_p_high,
                "allow_clr_exposure": False,
            },
            "fixed_p_high_baseline": {
                "directory": seed_dir / "fixed_p_high_baseline",
                "label": f"seed {seed} fixed-p-high baseline",
                "p_low": profile_policy.p_high,
                "p_high": profile_policy.p_high,
                "allow_clr_exposure": True,
            },
            "dblp_policy": {
                "directory": seed_dir / "dblp_policy",
                "label": f"seed {seed} phase-aware selection policy",
                "p_low": profile_policy.p_low,
                "p_high": profile_policy.p_high,
                "allow_clr_exposure": False,
            },
        }
        if analyze_only:
            # Parse, don't validate: an arm's summary.json exists exactly when
            # its simulations and gates completed, so totality is checked here,
            # before any comparison work, instead of surfacing as a
            # FileNotFoundError from whichever arm happens to be read first.
            incomplete = [
                arm_name
                for arm_name, arm in arms.items()
                if not (arm["directory"] / "summary.json").exists()
            ]
            if incomplete:
                raise ValueError(
                    f"seed {seed}: arm(s) {', '.join(incomplete)} never completed "
                    "(no summary.json); inspect those arm jobs, not this analysis"
                )
        summaries: dict[str, dict[str, Any]] = {}
        congestion: dict[str, dict[str, bool | int | str]] = {}
        for arm_name, arm in arms.items():
            if only_arm is not None and arm_name != only_arm:
                continue
            if not analyze_only:
                run_experiment(
                    profile,
                    arm["directory"],
                    binary=binary,
                    clean=True,
                    seed=seed,
                    ns3_rng_run=seed,
                    simulation_timeout_seconds=simulation_timeout_seconds,
                    p_low=arm["p_low"],
                    p_high=arm["p_high"],
                    allow_clr_exposure=arm["allow_clr_exposure"],
                )
            summary = _read_summary(arm["directory"])
            require_primary_analysis(summary, arm["label"])
            evidence = congestion_evidence(summary)
            if require_congestion_signals:
                evidence = require_congestion(summary, arm["label"])
            if require_finite_buffer_data_drops:
                evidence = require_finite_buffer_data_drop(summary, arm["label"])
            summaries[arm_name] = summary
            congestion[arm_name] = evidence
        if only_arm is not None:
            continue
        per_seed.append(
            {
                "seed": seed,
                "ns3_rng_seed": 1,
                "ns3_rng_run": seed,
                **{
                    f"{arm_name}_dir": arm["directory"]
                    .relative_to(output)
                    .as_posix()
                    for arm_name, arm in arms.items()
                },
                "congestion": congestion,
                "metrics": compare_summaries(
                    summaries["fixed_p_low_baseline"],
                    summaries["dblp_policy"],
                    metrics,
                ),
                # The relief an unbounded permissive policy takes over the
                # conservative control: the ceiling the phase-aware policy is
                # measured against.
                "headroom_metrics": compare_summaries(
                    summaries["fixed_p_low_baseline"],
                    summaries["fixed_p_high_baseline"],
                    metrics,
                ),
            }
        )

    if only_arm is not None:
        return {"arm": only_arm, "seeds": seeds}

    comparison = {
        "profile": repository_relative_profile(profile),
        "selection_policy": {
            "semantics": "logical_admission_selection",
            "baseline": {"p_low": baseline_p_low, "p_high": baseline_p_high},
            "policy": {"p_low": profile_policy.p_low, "p_high": profile_policy.p_high},
        },
        # Self-describing sweep coordinates: a sweep aggregation needs only
        # the comparison artifacts, never the original profile paths.
        "dp_all_reduce_implementation": profile_model.dp_all_reduce_implementation,
        "dp_fan_in": dp_fan_in(
            profile_model.dp, profile_model.dp_all_reduce_implementation
        ),
        "microburst_source_count": (
            profile_model.microburst_flow_count
            if profile_model.microburst_enabled
            else 0
        ),
        "microburst_trigger_step": burst_step,
        "seeds": seeds,
        "congestion_required": require_congestion_signals,
        "finite_buffer_data_drop_required": require_finite_buffer_data_drops,
        "simulation_timeout_seconds": simulation_timeout_seconds,
        "per_seed": per_seed,
        "aggregate": aggregate_comparisons(per_seed),
        "headroom_aggregate": aggregate_comparisons(per_seed, "headroom_metrics"),
    }
    _write_comparison(output, comparison)
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--aggregate-inputs",
        type=Path,
        nargs="+",
        help="one-seed comparison.json artifacts to validate and aggregate",
    )
    parser.add_argument(
        "--binary", type=Path, help="path to an ns-3 AstraSimNetwork executable"
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=list(DEFAULT_SEEDS),
        help="unique matched seeds; defaults to the sixteen 8-digit pi-chunk "
        "research seeds",
    )
    parser.add_argument(
        "--require-congestion",
        action="store_true",
        help="require observed background traffic, queueing, and completed PFC pause intervals",
    )
    parser.add_argument(
        "--require-finite-buffer-data-drop",
        action="store_true",
        help="require a natural data-plane switch admission or egress-queue drop",
    )
    parser.add_argument(
        "--simulation-timeout-seconds",
        type=int,
        help="maximum wall-clock seconds for each ns-3 simulator process",
    )
    parser.add_argument(
        "--p-low",
        type=float,
        help="override the low logical-admission selection probability (0, 0.01]",
    )
    parser.add_argument(
        "--p-high",
        type=float,
        help="override the high logical-admission selection probability",
    )
    parser.add_argument(
        "--arm",
        choices=tuple(_ARM_TITLES),
        help="run only this arm's simulations and gates; compare later with --analyze-only",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="skip simulations and build the comparison from existing arm directories",
    )
    parser.add_argument(
        "--clean", action="store_true", help="replace an existing comparison directory"
    )
    arguments = parser.parse_args()
    if (arguments.profile is None) == (arguments.aggregate_inputs is None):
        parser.error("provide exactly one of --profile or --aggregate-inputs")
    if arguments.arm and arguments.analyze_only:
        parser.error("--arm and --analyze-only are mutually exclusive")
    if arguments.aggregate_inputs is not None:
        if arguments.clean and arguments.output.exists():
            shutil.rmtree(arguments.output)
        comparison = aggregate_comparison_artifacts(arguments.aggregate_inputs)
        _write_comparison(arguments.output, comparison)
    else:
        comparison = run_comparison(
            arguments.profile,
            arguments.output,
            arguments.seeds,
            binary=arguments.binary,
            clean=arguments.clean,
            require_congestion_signals=(
                arguments.require_congestion
                or arguments.require_finite_buffer_data_drop
            ),
            require_finite_buffer_data_drops=arguments.require_finite_buffer_data_drop,
            simulation_timeout_seconds=arguments.simulation_timeout_seconds,
            p_low=arguments.p_low,
            p_high=arguments.p_high,
            only_arm=arguments.arm,
            analyze_only=arguments.analyze_only,
        )
    print(json.dumps(comparison, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
