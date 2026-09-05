from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.ring_3d.compare import (
    AFTERMATH_STEP_SPAN_METRIC,
    BURST_STEP_SPAN_METRIC,
    DEFAULT_SEEDS,
    aggregate_comparison_artifacts,
    aggregate_comparisons,
    compare_summaries,
    congestion_evidence,
    require_congestion,
    require_finite_buffer_data_drop,
    require_primary_analysis,
    comparison_metrics,
    profile_identity,
    render_comparison_report,
    repository_relative_profile,
    run_comparison,
)


def summary(
    makespan: int,
    fct_p99: int,
    trimmed_per_offered: float = 0.02,
    dp_span_by_step: dict[str, int] | None = None,
) -> dict[str, object]:
    statistic = {
        "count": 8,
        "min_ns": fct_p99 - 10,
        "p50_ns": fct_p99 - 5,
        "p95_ns": fct_p99,
        "p99_ns": fct_p99,
        "max_ns": fct_p99,
    }
    return {
        "rank_completion_time_ns": {**statistic, "max_ns": makespan},
        "network_health": {
            "status": "available",
            "offered_physical_bytes": 20_000,
            "trimmed_admission_bytes": int(20_000 * trimmed_per_offered),
            "W": trimmed_per_offered,
            "data_arrival_bytes": 20_000,
            "wire_per_offered": 1.0,
            "burst_drain_ns": 500,
            "forgiven_bytes": 0,
            "W_prime": trimmed_per_offered,
        },
        "forgiveness": {
            "forgiven_bytes": 0,
            "forgiven_range_count": 0,
            "priority_pull_count": 0,
            "ledger_law": {"status": "verified"},
        },
        "collective_completion": {
            "per_rank_completion_time_ns": {
                "by_parallelism_domain_and_collective_type": {
                    "dp": {"all_reduce": statistic}
                }
            },
            "all_rank_operation_span_ns": {
                "by_parallelism_domain_and_collective_type": {
                    "dp": {"all_reduce": statistic}
                }
            },
            "dp_all_reduce_span_ns_by_training_step": (
                dp_span_by_step
                if dp_span_by_step is not None
                else {str(step): makespan // 2 for step in range(1, 21)}
            ),
        },
        "flow_completion_time_ns": {
            "all": statistic,
            "by_flow_kind": {"foreground_payload": statistic},
            "by_parallelism_domain_and_flow_kind": {
                "dp": {"foreground_payload": statistic}
            },
        },
        "physical_traffic_bytes": {
            "foreground_logical_operations": {"physical_bytes": 10_000},
            "dp_all_reduce": {"physical_bytes": 8_000},
            "total": {"physical_bytes": 20_000},
        },
        "primary_analysis_eligibility": {"status": "eligible"},
    }


def congested_summary() -> dict[str, object]:
    result = summary(1_000, 100)
    result["background_microburst_timeline"] = {
        "status": "available",
        "physical_bytes": 128 * 1024 * 1024,
    }
    result["ns3_observability"] = {
        "queue": {"status": "available", "max_queue_bytes": 32 * 1024 * 1024},
        "pfc": {"status": "available", "completed_pause_interval_count": 1},
        "transport": {
            "status": "available",
            "data_natural_buffer_drop_count": 1,
            "control_natural_buffer_drop_count": 0,
        },
    }
    return result


class Ring3DComparisonTests(unittest.TestCase):
    def test_default_seeds_are_consecutive_pi_chunks(self) -> None:
        self.assertEqual(
            DEFAULT_SEEDS,
            (
                31415926, 53589793, 23846264, 33832795, 2884197, 16939937,
                51058209, 74944592, 30781640, 62862089, 98628034, 82534211,
                70679821, 48086513, 28230664, 70938446,
            ),
        )
        profile = json.loads(
            (
                REPOSITORY_ROOT / "experiments/ring_3d/profiles/llama3_70b_16.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(profile["seed"], DEFAULT_SEEDS[0])

    def test_pairwise_metrics_use_positive_reduction_for_faster_policy(self) -> None:
        results = compare_summaries(summary(1_000, 100), summary(900, 90))

        self.assertEqual(results["makespan_ns"]["reduction_ns"], 100)
        self.assertEqual(results["makespan_ns"]["reduction_percent"], 10.0)
        self.assertEqual(
            results["dp_all_reduce_collective_operation_span_p99_ns"]["reduction_ns"],
            10,
        )
        self.assertEqual(results["dp_all_reduce_physical_bytes"]["reduction_ns"], 0)

    def test_aggregate_and_report_include_paired_uncertainty(self) -> None:
        per_seed = [
            {
                "seed": 1,
                "metrics": compare_summaries(summary(1_000, 100), summary(900, 90)),
            },
            {
                "seed": 2,
                "metrics": compare_summaries(summary(1_000, 100), summary(800, 80)),
            },
        ]
        aggregate = aggregate_comparisons(per_seed)
        comparison = {"aggregate": aggregate}
        report = render_comparison_report(comparison)

        self.assertEqual(aggregate["makespan_ns"]["mean_reduction_ns"], 150.0)
        self.assertIsNotNone(aggregate["makespan_ns"]["reduction_ci95_ns"])
        self.assertIn("Matched phase-aware selection comparison", report)
        self.assertIn("makespan_ns", report)
        self.assertIn("95% CI of reduction", report)

    def test_three_arm_report_exposes_headroom_and_evidence(self) -> None:
        low = summary(1_000, 100)
        high = summary(700, 70)
        policy = summary(800, 80)
        evidence = {
            "trim_notification_count": 10,
            "data_natural_buffer_drop_count": 2,
            "completed_pause_interval_count": 0,
            "max_queue_bytes": 4 * 1024 * 1024,
            "flow_control_regime": "best_effort",
        }
        per_seed = [
            {
                "seed": 1,
                "metrics": compare_summaries(low, policy),
                "headroom_metrics": compare_summaries(low, high),
                "congestion": {
                    "fixed_p_low_baseline": dict(evidence),
                    "fixed_p_high_baseline": {
                        **evidence,
                        "trim_notification_count": 2,
                    },
                    "dblp_policy": {**evidence, "trim_notification_count": 4},
                },
            }
        ]
        comparison = {
            "profile": "/runs/profile.json",
            "seeds": [1],
            "dp_all_reduce_implementation": "direct2",
            "dp_fan_in": 2,
            "selection_policy": {
                "baseline": {"p_low": 0.005, "p_high": 0.005},
                "policy": {"p_low": 0.005, "p_high": 0.1},
            },
            "simulation_timeout_seconds": 9000,
            "per_seed": per_seed,
            "aggregate": aggregate_comparisons(per_seed),
            "headroom_aggregate": aggregate_comparisons(
                per_seed, "headroom_metrics"
            ),
        }
        report = render_comparison_report(comparison)

        self.assertIn("## Experiment coordinates", report)
        self.assertIn("direct2", report)
        self.assertIn("deliberately exposes critical steps", report)
        self.assertIn("Unbounded-shedding headroom", report)
        self.assertIn("## Raw congestion evidence by arm", report)
        self.assertIn("| Fixed-high baseline | 2.0 |", report)
        self.assertIn("best_effort", report)
        # Headroom (300 ns) exceeds achieved relief (200 ns).
        self.assertEqual(
            comparison["headroom_aggregate"]["makespan_ns"]["mean_reduction_ns"],
            300.0,
        )

    def test_aggregate_comparisons_rejects_mixed_headroom_recording(self) -> None:
        per_seed = [
            {
                "seed": 1,
                "metrics": compare_summaries(summary(1_000, 100), summary(900, 90)),
                "headroom_metrics": compare_summaries(
                    summary(1_000, 100), summary(700, 70)
                ),
            },
            {
                "seed": 2,
                "metrics": compare_summaries(summary(1_000, 100), summary(800, 80)),
            },
        ]
        self.assertIsNone(
            aggregate_comparisons(
                [entry for entry in per_seed if "headroom_metrics" not in entry],
                "headroom_metrics",
            )
        )
        with self.assertRaisesRegex(ValueError, "headroom_metrics"):
            aggregate_comparisons(per_seed, "headroom_metrics")

    def test_aggregate_artifacts_validates_and_combines_one_seed_results(self) -> None:
        def one_seed_comparison(seed: int) -> dict[str, object]:
            per_seed = [
                {
                    "seed": seed,
                    "metrics": compare_summaries(
                        summary(1_000, 100), summary(900 - seed, 90 - seed)
                    ),
                }
            ]
            return {
                "profile": "/profiles/llama3_70b_16.json",
                "selection_policy": {
                    "semantics": "logical_admission_selection",
                    "baseline": {"p_low": 0.005, "p_high": 0.005},
                    "policy": {"p_low": 0.005, "p_high": 0.1},
                },
                "seeds": [seed],
                "congestion_required": True,
                "simulation_timeout_seconds": 9_000,
                "per_seed": per_seed,
                "aggregate": aggregate_comparisons(per_seed),
            }

        with tempfile.TemporaryDirectory() as temporary_directory:
            first = Path(temporary_directory) / "first.json"
            second = Path(temporary_directory) / "second.json"
            first.write_text(json.dumps(one_seed_comparison(1)), encoding="utf-8")
            second.write_text(json.dumps(one_seed_comparison(2)), encoding="utf-8")

            comparison = aggregate_comparison_artifacts([second, first])

        self.assertEqual(comparison["seeds"], [1, 2])
        self.assertEqual([entry["seed"] for entry in comparison["per_seed"]], [1, 2])
        self.assertEqual(comparison["aggregate"]["makespan_ns"]["paired_seed_count"], 2)
        self.assertEqual(
            comparison["selection_policy"]["baseline"],
            {"p_low": 0.005, "p_high": 0.005},
        )

    def test_aggregate_artifacts_match_across_differing_absolute_paths(self) -> None:
        """One sweep runs one profile even when its seeds ran in other workspaces."""

        def one_seed_comparison(seed: int, root: str) -> dict[str, object]:
            per_seed = [
                {
                    "seed": seed,
                    "metrics": compare_summaries(
                        summary(1_000, 100), summary(900 - seed, 90 - seed)
                    ),
                }
            ]
            return {
                "profile": f"{root}/experiments/ring_3d/profiles/llama3_70b_16.json",
                "selection_policy": {"semantics": "logical_admission_selection"},
                "seeds": [seed],
                "congestion_required": True,
                "simulation_timeout_seconds": 9_000,
                "per_seed": per_seed,
                "aggregate": aggregate_comparisons(per_seed),
            }

        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = []
            for index, (seed, root) in enumerate(
                ((1, "/home/runner/work/astra-sim/astra-sim"), (2, "/scratch/pp2/checkout"))
            ):
                path = Path(temporary_directory) / f"artifact_{index}.json"
                path.write_text(
                    json.dumps(one_seed_comparison(seed, root)), encoding="utf-8"
                )
                paths.append(path)

            comparison = aggregate_comparison_artifacts(paths)

        self.assertEqual(
            comparison["profile"],
            "experiments/ring_3d/profiles/llama3_70b_16.json",
        )
        self.assertEqual(comparison["seeds"], [1, 2])

    def test_profile_identity_keeps_a_path_outside_the_profile_directory(self) -> None:
        self.assertEqual(profile_identity("/tmp/generated.json"), "/tmp/generated.json")
        self.assertEqual(
            repository_relative_profile(
                REPOSITORY_ROOT / "experiments/ring_3d/profiles/smoke_8.json"
            ),
            "experiments/ring_3d/profiles/smoke_8.json",
        )

    def test_episode_metrics_track_the_profile_trigger_step(self) -> None:
        baseline = summary(1_000, 100, 0.25, {"18": 900, "19": 400})
        policy = summary(900, 90, 0.10, {"18": 600, "19": 300})
        metrics = compare_summaries(
            baseline,
            policy,
            comparison_metrics(18, 19),
        )

        self.assertEqual(metrics[BURST_STEP_SPAN_METRIC]["reduction_ns"], 300)
        self.assertEqual(metrics[AFTERMATH_STEP_SPAN_METRIC]["reduction_ns"], 100)
        self.assertAlmostEqual(metrics["W"]["reduction_ns"], 0.15)
        self.assertAlmostEqual(metrics["W"]["reduction_percent"], 60.0)

    def test_zero_trim_fabric_reports_no_relative_change_in_w(self) -> None:
        metrics = compare_summaries(summary(1_000, 100, 0.0), summary(900, 90, 0.0))

        self.assertEqual(metrics["W"]["reduction_ns"], 0.0)
        self.assertEqual(metrics["W"]["reduction_percent"], 0.0)

    def test_congestion_gate_requires_queue_and_pfc_evidence(self) -> None:
        evidence = congestion_evidence(congested_summary())
        self.assertTrue(evidence["congestion_established"])
        self.assertTrue(
            require_congestion(congested_summary(), "test run")[
                "congestion_established"
            ]
        )

        uncongested = congested_summary()
        uncongested["ns3_observability"] = {
            "queue": {"status": "available", "max_queue_bytes": 0},
            "pfc": {"status": "available", "completed_pause_interval_count": 0},
        }
        with self.assertRaisesRegex(
            ValueError, "did not establish required congestion"
        ):
            require_congestion(uncongested, "test run")

    def test_congestion_gate_matches_the_flow_control_regime(self) -> None:
        # A best-effort fabric can never pause, so its congestion signature
        # is trimmed or naturally dropped packets.
        best_effort = congested_summary()
        best_effort["flow_control_regime"] = "best_effort"
        best_effort["ns3_observability"]["pfc"][
            "completed_pause_interval_count"
        ] = 0
        best_effort["transport_recovery"] = {"trim_notification_count": 3}
        best_effort["ns3_observability"]["transport"][
            "data_natural_buffer_drop_count"
        ] = 0
        evidence = congestion_evidence(best_effort)
        self.assertTrue(evidence["congestion_established"])
        self.assertEqual(evidence["trim_notification_count"], 3)

        without_rejections = congested_summary()
        without_rejections["flow_control_regime"] = "best_effort"
        without_rejections["ns3_observability"]["transport"][
            "data_natural_buffer_drop_count"
        ] = 0
        with self.assertRaisesRegex(
            ValueError, "did not establish required congestion"
        ):
            require_congestion(without_rejections, "test run")

        # A lossless fabric must pause; drops cannot substitute.
        lossless = congested_summary()
        lossless["flow_control_regime"] = "lossless_pfc"
        lossless["ns3_observability"]["pfc"]["completed_pause_interval_count"] = 0
        with self.assertRaisesRegex(
            ValueError, "did not establish required congestion"
        ):
            require_congestion(lossless, "test run")

    def test_finite_buffer_drop_gate_requires_natural_data_drop(self) -> None:
        self.assertEqual(
            require_finite_buffer_data_drop(congested_summary(), "test run")[
                "data_natural_buffer_drop_count"
            ],
            1,
        )
        no_drop = congested_summary()
        no_drop["ns3_observability"]["transport"]["data_natural_buffer_drop_count"] = 0
        with self.assertRaisesRegex(ValueError, "finite-buffer data loss"):
            require_finite_buffer_data_drop(no_drop, "test run")

    def test_primary_analysis_gate_rejects_ineligible_summary(self) -> None:
        ineligible = summary(1_000, 100)
        ineligible["primary_analysis_eligibility"] = {
            "status": "ineligible",
            "failed_flow_count": 1,
        }
        with self.assertRaisesRegex(ValueError, "ineligible for primary analysis"):
            require_primary_analysis(ineligible, "test run")

    def test_comparison_propagates_per_simulation_timeout(self) -> None:
        def fake_run_experiment(
            _profile: Path, output: Path, **_kwargs: object
        ) -> dict[str, object]:
            output.mkdir(parents=True, exist_ok=True)
            (output / "summary.json").write_text(
                json.dumps(congested_summary()), encoding="utf-8"
            )
            return {}

        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch(
                "experiments.ring_3d.compare.run_experiment",
                side_effect=fake_run_experiment,
            ) as mocked_run:
                comparison = run_comparison(
                    REPOSITORY_ROOT / "experiments/ring_3d/profiles/smoke_8.json",
                    Path(temporary_directory) / "comparison",
                    [17],
                    simulation_timeout_seconds=960,
                )

        self.assertEqual(mocked_run.call_count, 3)
        self.assertTrue(
            all(
                call.kwargs["simulation_timeout_seconds"] == 960
                for call in mocked_run.call_args_list
            )
        )
        self.assertEqual(comparison["simulation_timeout_seconds"], 960)
        arm_policies = [
            (
                call.kwargs["p_low"],
                call.kwargs["p_high"],
                call.kwargs["allow_clr_exposure"],
            )
            for call in mocked_run.call_args_list
        ]
        self.assertEqual(
            arm_policies,
            [
                (0.005, 0.005, False),
                (0.1, 0.1, True),
                (0.005, 0.1, False),
            ],
        )
        self.assertIn("headroom_aggregate", comparison)

    def test_recovery_profile_builds_four_matched_arms(self) -> None:
        def fake_run_experiment(
            _profile: Path, output: Path, **_kwargs: object
        ) -> dict[str, object]:
            output.mkdir(parents=True, exist_ok=True)
            (output / "summary.json").write_text(
                json.dumps(congested_summary()), encoding="utf-8"
            )
            return {}

        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch(
                "experiments.ring_3d.compare.run_experiment",
                side_effect=fake_run_experiment,
            ) as mocked_run:
                comparison = run_comparison(
                    REPOSITORY_ROOT
                    / "experiments/ring_3d/profiles/forgiveness_smoke_8.json",
                    Path(temporary_directory) / "comparison",
                    [17],
                )

        self.assertEqual(mocked_run.call_count, 4)
        arms = [
            (
                call.kwargs["p_low"],
                call.kwargs["p_high"],
                call.kwargs["domain"].value,
            )
            for call in mocked_run.call_args_list
        ]
        # The recovery arm carries the policy's own budget, and only its domain
        # differs from the admission policy arm.
        self.assertEqual(
            arms,
            [
                (0.005, 0.005, "admission"),
                (0.1, 0.1, "admission"),
                (0.005, 0.1, "admission"),
                (0.005, 0.1, "recovery"),
            ],
        )
        self.assertIn("recovery_aggregate", comparison)
        self.assertIn("W_prime", comparison["recovery_aggregate"])
        self.assertIn("forgiven_bytes", comparison["recovery_aggregate"])
        self.assertEqual(comparison["selection_policy"]["domain"], "recovery")
        report = render_comparison_report(comparison)
        self.assertIn("## Recovery-domain relief over fixed-low", report)

    def test_admission_profile_builds_three_arms_and_no_recovery_metrics(
        self,
    ) -> None:
        def fake_run_experiment(
            _profile: Path, output: Path, **_kwargs: object
        ) -> dict[str, object]:
            output.mkdir(parents=True, exist_ok=True)
            (output / "summary.json").write_text(
                json.dumps(congested_summary()), encoding="utf-8"
            )
            return {}

        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch(
                "experiments.ring_3d.compare.run_experiment",
                side_effect=fake_run_experiment,
            ) as mocked_run:
                comparison = run_comparison(
                    REPOSITORY_ROOT / "experiments/ring_3d/profiles/smoke_8.json",
                    Path(temporary_directory) / "comparison",
                    [17],
                )

        self.assertEqual(mocked_run.call_count, 3)
        self.assertIsNone(comparison["recovery_aggregate"])
        self.assertNotIn("W_prime", comparison["aggregate"])

    def test_chained_arm_runs_then_analyze_only_matches_full_comparison(self) -> None:
        def fake_run_experiment(
            _profile: Path, output: Path, **_kwargs: object
        ) -> dict[str, object]:
            output.mkdir(parents=True, exist_ok=True)
            (output / "summary.json").write_text(
                json.dumps(congested_summary()), encoding="utf-8"
            )
            return {}

        profile = REPOSITORY_ROOT / "experiments/ring_3d/profiles/smoke_8.json"
        arms = ("fixed_p_low_baseline", "fixed_p_high_baseline", "dblp_policy")
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "comparison"
            with patch(
                "experiments.ring_3d.compare.run_experiment",
                side_effect=fake_run_experiment,
            ) as mocked_run:
                for arm in arms:
                    partial = run_comparison(profile, output, [17], only_arm=arm)
                    self.assertEqual(partial, {"arm": arm, "seeds": [17]})
                self.assertEqual(mocked_run.call_count, len(arms))
                comparison = run_comparison(profile, output, [17], analyze_only=True)
                # The analyze pass must never launch a simulation.
                self.assertEqual(mocked_run.call_count, len(arms))
            self.assertTrue((output.resolve() / "comparison.json").exists())
            # An incomplete arm must be named up front, not surface as a
            # FileNotFoundError from deep inside the comparison.
            (output.resolve() / "seed_17" / arms[1] / "summary.json").unlink()
            with self.assertRaisesRegex(ValueError, arms[1]):
                run_comparison(profile, output, [17], analyze_only=True)
        self.assertEqual(len(comparison["per_seed"]), 1)
        self.assertIn("aggregate", comparison)


if __name__ == "__main__":
    unittest.main()
