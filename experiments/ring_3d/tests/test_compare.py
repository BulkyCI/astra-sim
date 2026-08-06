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
    DEFAULT_SEEDS,
    aggregate_comparison_artifacts,
    aggregate_comparisons,
    compare_summaries,
    congestion_evidence,
    require_congestion,
    require_finite_buffer_data_drop,
    require_primary_analysis,
    render_comparison_report,
    run_comparison,
)


def summary(makespan: int, fct_p99: int) -> dict[str, object]:
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
            (314159265, 358979323, 846264338, 327950288, 419716939),
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
        self.assertIn("Paired phase-aware selection comparison", report)
        self.assertIn("makespan_ns", report)
        self.assertIn("95% CI of reduction", report)

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

        self.assertEqual(mocked_run.call_count, 2)
        self.assertTrue(
            all(
                call.kwargs["simulation_timeout_seconds"] == 960
                for call in mocked_run.call_args_list
            )
        )
        self.assertEqual(comparison["simulation_timeout_seconds"], 960)
        self.assertEqual(mocked_run.call_args_list[0].kwargs["p_low"], 0.005)
        self.assertEqual(mocked_run.call_args_list[0].kwargs["p_high"], 0.005)
        self.assertEqual(mocked_run.call_args_list[1].kwargs["p_low"], 0.005)
        self.assertEqual(mocked_run.call_args_list[1].kwargs["p_high"], 0.1)


if __name__ == "__main__":
    unittest.main()
