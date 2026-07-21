#!/usr/bin/env python3
"""Run matched DBLP and lossless-baseline experiments across fixed seeds."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

try:
	from .run import lossless_drop_probabilities, run_experiment
except ImportError:
	from run import lossless_drop_probabilities, run_experiment


DEFAULT_SEEDS = (20260317, 20260318, 20260319, 20260320, 20260321)
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


def _metric(summary: dict[str, Any], path: tuple[str, ...]) -> int:
	value: Any = summary
	for key in path:
		if not isinstance(value, dict) or key not in value:
			raise ValueError(f"summary is missing comparison metric {'/'.join(path)}")
		value = value[key]
	if isinstance(value, bool) or not isinstance(value, int):
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
}

BYTE_METRICS = {
	"foreground_logical_operation_physical_bytes",
	"dp_all_reduce_physical_bytes",
	"total_physical_bytes",
}


def compare_summaries(
	baseline: dict[str, Any], policy: dict[str, Any]
) -> dict[str, dict[str, float | int]]:
	"""Produce positive reductions when the policy is faster than baseline."""
	comparisons: dict[str, dict[str, float | int]] = {}
	for name, path in METRICS.items():
		baseline_value = _metric(baseline, path)
		policy_value = _metric(policy, path)
		if baseline_value == 0:
			raise ValueError(f"comparison baseline metric {name} must be nonzero")
		reduction = baseline_value - policy_value
		comparisons[name] = {
			"baseline_ns": baseline_value,
			"policy_ns": policy_value,
			"reduction_ns": reduction,
			"reduction_percent": reduction * 100 / baseline_value,
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
) -> dict[str, dict[str, float | int | list[float] | None]]:
	if not per_seed:
		raise ValueError("at least one paired seed result is required")
	aggregate: dict[str, dict[str, float | int | list[float] | None]] = {}
	for metric in METRICS:
		entries = [seed["metrics"][metric] for seed in per_seed]
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


def _format_duration_ns(value: float) -> str:
	if value < 1_000:
		return f"{value:.2f} ns"
	if value < 1_000_000:
		return f"{value / 1_000:.2f} μs"
	return f"{value / 1_000_000:.2f} ms"


def _format_bytes(value: float) -> str:
	units = ("B", "KiB", "MiB", "GiB", "TiB")
	for unit in units:
		if value < 1024 or unit == units[-1]:
			return f"{value:.2f} {unit}" if unit != "B" else f"{value:.0f} B"
		value /= 1024
	raise AssertionError("unreachable")


def render_comparison_report(comparison: dict[str, Any]) -> str:
	"""Render a self-contained Markdown record of the paired comparison."""
	lines = [
		"# Paired DBLP comparison",
		"",
		"> Each seed uses identical traces, topology, microburst configuration, and seed. "
		"The lossless baseline keeps the policy enabled but sets every admission-suppression threshold to zero. "
		"Baseline and policy share an ns-3 random-stream seed/run within each pair; successive pairs use distinct runs.",
		"",
		"| Metric | Baseline mean | Policy mean | Mean reduction | 95% CI of reduction | Mean reduction % |",
		"| --- | ---: | ---: | ---: | ---: | ---: |",
	]
	for metric, values in comparison["aggregate"].items():
		format_value = _format_bytes if metric in BYTE_METRICS else _format_duration_ns
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
	lines.extend(
		[
			"",
			"Positive reductions favor the DBLP policy. Logical collective metrics include every completed "
			"DP All-Reduce regardless of whether its payload used provenance control; all-QP FCT is a "
			"secondary transport diagnostic. Physical-byte reductions are reported against foreground, DP, "
			"and total offered traffic. Do not interpret a single seed or a confidence interval spanning zero "
			"as evidence of a performance benefit.",
			"",
		]
	)
	return "\n".join(lines)


def run_comparison(
	profile: Path,
	output: Path,
	seeds: list[int],
	*,
	binary: Path | None = None,
	clean: bool = False,
) -> dict[str, Any]:
	"""Run the matched experiment pairs and retain their individual artifacts."""
	if not seeds:
		raise ValueError("at least one seed is required")
	if len(set(seeds)) != len(seeds):
		raise ValueError("comparison seeds must be unique")
	output = output.resolve()
	if output.exists() and clean:
		shutil.rmtree(output)
	output.mkdir(parents=True, exist_ok=True)

	per_seed: list[dict[str, Any]] = []
	for seed in seeds:
		seed_dir = output / f"seed_{seed}"
		baseline_dir = seed_dir / "lossless_baseline"
		policy_dir = seed_dir / "dblp_policy"
		run_experiment(
			profile,
			baseline_dir,
			binary=binary,
			clean=True,
			seed=seed,
			ns3_rng_run=seed,
			drop_probabilities=lossless_drop_probabilities(),
		)
		run_experiment(
			profile,
			policy_dir,
			binary=binary,
			clean=True,
			seed=seed,
			ns3_rng_run=seed,
		)
		per_seed.append(
			{
				"seed": seed,
				"ns3_rng_seed": 1,
				"ns3_rng_run": seed,
				"lossless_baseline_dir": baseline_dir.relative_to(output).as_posix(),
				"dblp_policy_dir": policy_dir.relative_to(output).as_posix(),
				"metrics": compare_summaries(
					_read_summary(baseline_dir), _read_summary(policy_dir)
				),
			}
		)

	comparison = {
		"profile": profile.resolve().as_posix(),
		"seeds": seeds,
		"per_seed": per_seed,
		"aggregate": aggregate_comparisons(per_seed),
	}
	(output / "comparison.json").write_text(
		json.dumps(comparison, indent=2) + "\n", encoding="utf-8"
	)
	(output / "comparison_report.md").write_text(
		render_comparison_report(comparison), encoding="utf-8"
	)
	return comparison


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--profile", type=Path, required=True)
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--binary", type=Path, help="path to an ns-3 AstraSimNetwork executable")
	parser.add_argument(
		"--seeds",
		type=int,
		nargs="+",
		default=list(DEFAULT_SEEDS),
		help="unique matched seeds; defaults to five fixed research seeds",
	)
	parser.add_argument("--clean", action="store_true", help="replace an existing comparison directory")
	arguments = parser.parse_args()
	comparison = run_comparison(
		arguments.profile,
		arguments.output,
		arguments.seeds,
		binary=arguments.binary,
		clean=arguments.clean,
	)
	print(json.dumps(comparison, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
