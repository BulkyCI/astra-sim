from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.ring_3d.compare import (
    aggregate_comparisons,
    compare_summaries,
    render_comparison_report,
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
    }


class Ring3DComparisonTests(unittest.TestCase):
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
            {"seed": 1, "metrics": compare_summaries(summary(1_000, 100), summary(900, 90))},
            {"seed": 2, "metrics": compare_summaries(summary(1_000, 100), summary(800, 80))},
        ]
        aggregate = aggregate_comparisons(per_seed)
        comparison = {"aggregate": aggregate}
        report = render_comparison_report(comparison)

        self.assertEqual(aggregate["makespan_ns"]["mean_reduction_ns"], 150.0)
        self.assertIsNotNone(aggregate["makespan_ns"]["reduction_ci95_ns"])
        self.assertIn("Paired DBLP comparison", report)
        self.assertIn("makespan_ns", report)
        self.assertIn("95% CI of reduction", report)


if __name__ == "__main__":
    unittest.main()
