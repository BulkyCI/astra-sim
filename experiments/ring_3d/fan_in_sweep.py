#!/usr/bin/env python3
"""Aggregate paired comparisons across DP fan-in into one knee table.

Each input is a completed ``comparison.json`` from one sweep point: the same
70B event window, fabric, seeds, and selection policy, differing only in the
direct all-reduce window and therefore in the peak concurrent inbound DP
flows per receiving rank. The output orders those points by fan-in so the
congestion signals and the policy's relief can be read against the single
swept variable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# One row of raw pressure evidence per arm, read from the per-seed congestion
# records that the comparison pipeline already validates.
CONGESTION_SIGNALS = (
    "trim_notification_count",
    "data_natural_buffer_drop_count",
    "max_queue_bytes",
    "completed_pause_interval_count",
)
COMPARISON_ARMS = ("fixed_p_low_baseline", "dblp_policy")
# Aggregate relief metrics carried into the sweep table verbatim.
RELIEF_METRICS = (
    "makespan_ns",
    "dp_all_reduce_collective_operation_span_p99_ns",
    "dp_all_reduce_physical_bytes",
)


def _read_comparison(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _require(comparison: dict[str, Any], field: str, path: Path) -> Any:
    value = comparison.get(field)
    if value is None:
        raise ValueError(f"comparison artifact {path} is missing {field}")
    return value


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _arm_signals(
    per_seed: list[dict[str, Any]], arm: str, path: Path
) -> dict[str, float]:
    """Per-seed mean of each raw congestion signal for one arm."""
    signals: dict[str, float] = {}
    for name in CONGESTION_SIGNALS:
        values: list[float] = []
        for seed_entry in per_seed:
            congestion = seed_entry.get("congestion")
            if not isinstance(congestion, dict) or arm not in congestion:
                raise ValueError(
                    f"comparison artifact {path} has no congestion record "
                    f"for arm {arm}"
                )
            value = congestion[arm].get(name, 0)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"comparison artifact {path} has invalid {name} for {arm}"
                )
            values.append(float(value))
        signals[name] = _mean(values)
    return signals


def sweep_point(path: Path) -> dict[str, Any]:
    """Reduce one comparison artifact to its sweep-table row."""
    comparison = _read_comparison(path)
    fan_in = _require(comparison, "dp_fan_in", path)
    if isinstance(fan_in, bool) or not isinstance(fan_in, int) or fan_in < 1:
        raise ValueError(f"comparison artifact {path} has invalid dp_fan_in")
    per_seed = _require(comparison, "per_seed", path)
    if not isinstance(per_seed, list) or not per_seed:
        raise ValueError(f"comparison artifact {path} has no per-seed results")
    aggregate = _require(comparison, "aggregate", path)
    relief: dict[str, dict[str, Any]] = {}
    for metric in RELIEF_METRICS:
        entry = aggregate.get(metric)
        if not isinstance(entry, dict):
            raise ValueError(
                f"comparison artifact {path} is missing aggregate {metric}"
            )
        relief[metric] = {
            "baseline_mean_ns": entry["baseline_mean_ns"],
            "mean_reduction_ns": entry["mean_reduction_ns"],
            "mean_reduction_percent": entry["mean_reduction_percent"],
            "reduction_ci95_ns": entry.get("reduction_ci95_ns"),
        }
    return {
        "dp_fan_in": fan_in,
        "dp_all_reduce_implementation": _require(
            comparison, "dp_all_reduce_implementation", path
        ),
        "profile": _require(comparison, "profile", path),
        "seeds": _require(comparison, "seeds", path),
        "selection_policy": _require(comparison, "selection_policy", path),
        "congestion_signals": {
            arm: _arm_signals(per_seed, arm, path) for arm in COMPARISON_ARMS
        },
        "relief": relief,
    }


def aggregate_sweep(comparison_paths: list[Path]) -> dict[str, Any]:
    """Validate that the points form one sweep and order them by fan-in."""
    if len(comparison_paths) < 2:
        raise ValueError("a sweep requires at least two fan-in points")
    points = [sweep_point(path) for path in comparison_paths]

    fan_ins = [point["dp_fan_in"] for point in points]
    if len(set(fan_ins)) != len(fan_ins):
        raise ValueError("sweep points must have distinct dp_fan_in values")
    for field in ("seeds", "selection_policy"):
        distinct = {json.dumps(point[field], sort_keys=True) for point in points}
        if len(distinct) != 1:
            raise ValueError(f"sweep points must share {field}")

    points.sort(key=lambda point: point["dp_fan_in"])
    return {
        "swept_variable": "dp_fan_in",
        "seeds": points[0]["seeds"],
        "selection_policy": points[0]["selection_policy"],
        "points": points,
    }


def _format_bytes(value: float) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} B" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def render_sweep_report(sweep: dict[str, Any]) -> str:
    """Render the fan-in knee table as a self-contained Markdown record."""
    lines = [
        "# DP fan-in sweep",
        "",
        "> Every point shares the workload, fabric, schedule, seeds, and "
        "selection policy; only the direct all-reduce window differs, so the "
        "peak concurrent inbound DP flows per rank is the single swept "
        "variable. Congestion signals are per-seed means of raw switch "
        "counters; relief rows are paired baseline-minus-policy aggregates.",
        "",
        "## Buffer pressure against fan-in",
        "",
        "| Fan-in | Algorithm | Baseline trims | Policy trims | "
        "Baseline drops | Policy drops | Baseline peak queue | "
        "Policy peak queue |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for point in sweep["points"]:
        baseline = point["congestion_signals"]["fixed_p_low_baseline"]
        policy = point["congestion_signals"]["dblp_policy"]
        lines.append(
            f"| {point['dp_fan_in']} "
            f"| `{point['dp_all_reduce_implementation']}` "
            f"| {baseline['trim_notification_count']:.1f} "
            f"| {policy['trim_notification_count']:.1f} "
            f"| {baseline['data_natural_buffer_drop_count']:.1f} "
            f"| {policy['data_natural_buffer_drop_count']:.1f} "
            f"| {_format_bytes(baseline['max_queue_bytes'])} "
            f"| {_format_bytes(policy['max_queue_bytes'])} |"
        )
    lines += [
        "",
        "## Policy relief against fan-in",
        "",
        "| Fan-in | Makespan reduction | DP operation-span p99 reduction | "
        "DP physical-byte reduction |",
        "| --- | --- | --- | --- |",
    ]
    for point in sweep["points"]:
        relief = point["relief"]
        cells = []
        for metric in RELIEF_METRICS:
            entry = relief[metric]
            cells.append(f"{entry['mean_reduction_percent']:.2f}%")
        lines.append(f"| {point['dp_fan_in']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "A congestion knee appears where the baseline pressure columns stop "
        "growing linearly in fan-in; the claim under test is that the "
        "policy's relief widens past that knee.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--comparison",
        type=Path,
        nargs="+",
        required=True,
        help="comparison.json artifacts, one per fan-in point",
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    sweep = aggregate_sweep(arguments.comparison)
    arguments.output.mkdir(parents=True, exist_ok=True)
    (arguments.output / "fan_in_sweep.json").write_text(
        json.dumps(sweep, indent=2) + "\n", encoding="utf-8"
    )
    (arguments.output / "fan_in_sweep_report.md").write_text(
        render_sweep_report(sweep), encoding="utf-8"
    )
    print(json.dumps(sweep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
