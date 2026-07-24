#!/usr/bin/env python3
"""Run matched fixed-low and phase-aware selection experiments across fixed seeds."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

try:
	from .generate import load_profile, resolve_selection_policy
	from .run import fixed_p_low_baseline, run_experiment
except ImportError:
	from generate import load_profile, resolve_selection_policy
	from run import fixed_p_low_baseline, run_experiment


# Consecutive nine-digit chunks of π's decimal expansion. Keeping the CLI and
# CI defaults identical makes local reruns exactly reproduce CI's seed sweep.
DEFAULT_SEEDS = (314159265, 358979323, 846264338, 327950288, 419716939)
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
	"""Extract the raw queue/PFC signals required for a congestion claim."""
	observability = _mapping(summary.get("ns3_observability"), "ns3_observability")
	queue = _mapping(observability.get("queue"), "ns3_observability.queue")
	pfc = _mapping(observability.get("pfc"), "ns3_observability.pfc")
	background = _mapping(
		summary.get("background_microburst_timeline"), "background_microburst_timeline"
	)
	queue_status = queue.get("status")
	pfc_status = pfc.get("status")
	background_status = background.get("status")
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
	return {
		"queue_status": str(queue_status),
		"pfc_status": str(pfc_status),
		"background_microburst_status": str(background_status),
		"max_queue_bytes": max_queue_bytes,
		"completed_pause_interval_count": completed_pause_intervals,
		"background_physical_bytes": background_physical_bytes,
		"congestion_established": (
			queue_status == "available"
			and pfc_status == "available"
			and background_status == "available"
			and max_queue_bytes > 0
			and completed_pause_intervals > 0
			and background_physical_bytes > 0
		),
	}


def require_congestion(summary: dict[str, Any], run_label: str) -> dict[str, bool | int | str]:
	"""Reject runs without observed microburst traffic, queueing, and PFC recovery."""
	evidence = congestion_evidence(summary)
	if not evidence["congestion_established"]:
		raise ValueError(
			f"{run_label} did not establish required congestion: {evidence}"
		)
	return evidence


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
	congestion_statement = (
		"Every baseline and policy run passed the required raw-signal gate: "
		"background microburst traffic, a nonzero queue peak, and at least one completed PFC pause interval."
		if comparison.get("congestion_required")
		else "Raw congestion signals were recorded but not enforced as a comparison gate."
	)
	lines = [
		"# Paired phase-aware selection comparison",
		"",
		"> Each seed uses identical traces, topology, microburst configuration, and seed. "
		"The fixed-low baseline keeps the policy enabled while setting p_low and p_high to the same low value. "
		"Baseline and policy share an ns-3 random-stream seed/run within each pair; successive pairs use distinct runs.",
		"",
		congestion_statement,
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
			"Positive reductions favor the phase-aware selection policy. Logical collective metrics include every completed "
			"DP All-Reduce regardless of whether its payload used provenance control; all-QP FCT is a "
			"secondary transport diagnostic. Physical-byte reductions are reported against foreground, DP, "
			"and total offered traffic. Do not interpret a single seed or a confidence interval spanning zero "
			"as evidence of a performance benefit.",
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
	simulation_timeout_seconds: int | None = None
	per_seed: list[dict[str, Any]] = []
	for path in comparison_paths:
		comparison = _read_comparison(path)
		artifact_profile = comparison.get("profile")
		if not isinstance(artifact_profile, str) or not artifact_profile:
			raise ValueError(f"comparison artifact {path} has no profile")
		if profile is None:
			profile = artifact_profile
		elif artifact_profile != profile:
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
			raise ValueError(f"comparison artifact {path} has invalid congestion setting")
		if require_congestion is None:
			require_congestion = artifact_congestion
		elif artifact_congestion != require_congestion:
			raise ValueError("comparison artifacts must use the same congestion setting")

		artifact_timeout = comparison.get("simulation_timeout_seconds")
		if isinstance(artifact_timeout, bool) or not isinstance(artifact_timeout, int):
			raise ValueError(f"comparison artifact {path} has invalid simulator timeout")
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
	return {
		"profile": profile,
		"selection_policy": selection_policy,
		"seeds": sorted(seeds),
		"congestion_required": require_congestion,
		"simulation_timeout_seconds": simulation_timeout_seconds,
		"per_seed": per_seed,
		"aggregate": aggregate_comparisons(per_seed),
	}


def run_comparison(
	profile: Path,
	output: Path,
	seeds: list[int],
	*,
	binary: Path | None = None,
	clean: bool = False,
	require_congestion_signals: bool = False,
	simulation_timeout_seconds: int | None = None,
	p_low: float | None = None,
	p_high: float | None = None,
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
	profile_policy = resolve_selection_policy(
		load_profile(profile.resolve()), p_low=p_low, p_high=p_high
	)
	baseline_p_low, baseline_p_high = fixed_p_low_baseline(
		load_profile(profile.resolve())
	)
	if p_low is not None:
		baseline_p_low = p_low
		baseline_p_high = p_low

	per_seed: list[dict[str, Any]] = []
	for seed in seeds:
		seed_dir = output / f"seed_{seed}"
		baseline_dir = seed_dir / "fixed_p_low_baseline"
		policy_dir = seed_dir / "dblp_policy"
		run_experiment(
			profile,
			baseline_dir,
			binary=binary,
			clean=True,
			seed=seed,
			ns3_rng_run=seed,
			simulation_timeout_seconds=simulation_timeout_seconds,
			p_low=baseline_p_low,
			p_high=baseline_p_high,
		)
		run_experiment(
			profile,
			policy_dir,
			binary=binary,
			clean=True,
			seed=seed,
			ns3_rng_run=seed,
			simulation_timeout_seconds=simulation_timeout_seconds,
			p_low=profile_policy.p_low,
			p_high=profile_policy.p_high,
		)
		baseline_summary = _read_summary(baseline_dir)
		policy_summary = _read_summary(policy_dir)
		baseline_congestion = congestion_evidence(baseline_summary)
		policy_congestion = congestion_evidence(policy_summary)
		if require_congestion_signals:
			baseline_congestion = require_congestion(
				baseline_summary, f"seed {seed} fixed-p-low baseline"
			)
			policy_congestion = require_congestion(
				policy_summary, f"seed {seed} phase-aware selection policy"
			)
		per_seed.append(
			{
				"seed": seed,
				"ns3_rng_seed": 1,
				"ns3_rng_run": seed,
				"fixed_p_low_baseline_dir": baseline_dir.relative_to(output).as_posix(),
				"dblp_policy_dir": policy_dir.relative_to(output).as_posix(),
				"congestion": {
					"fixed_p_low_baseline": baseline_congestion,
					"dblp_policy": policy_congestion,
				},
				"metrics": compare_summaries(baseline_summary, policy_summary),
			}
		)

	comparison = {
		"profile": profile.resolve().as_posix(),
		"selection_policy": {
			"semantics": "logical_admission_selection",
			"baseline": {"p_low": baseline_p_low, "p_high": baseline_p_high},
			"policy": {"p_low": profile_policy.p_low, "p_high": profile_policy.p_high},
		},
		"seeds": seeds,
		"congestion_required": require_congestion_signals,
		"simulation_timeout_seconds": simulation_timeout_seconds,
		"per_seed": per_seed,
		"aggregate": aggregate_comparisons(per_seed),
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
	parser.add_argument("--binary", type=Path, help="path to an ns-3 AstraSimNetwork executable")
	parser.add_argument(
		"--seeds",
		type=int,
		nargs="+",
		default=list(DEFAULT_SEEDS),
		help="unique matched seeds; defaults to five fixed research seeds",
	)
	parser.add_argument(
		"--require-congestion",
		action="store_true",
		help="require observed background traffic, queueing, and completed PFC pause intervals",
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
	parser.add_argument("--clean", action="store_true", help="replace an existing comparison directory")
	arguments = parser.parse_args()
	if (arguments.profile is None) == (arguments.aggregate_inputs is None):
		parser.error("provide exactly one of --profile or --aggregate-inputs")
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
			require_congestion_signals=arguments.require_congestion,
			simulation_timeout_seconds=arguments.simulation_timeout_seconds,
			p_low=arguments.p_low,
			p_high=arguments.p_high,
		)
	print(json.dumps(comparison, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
