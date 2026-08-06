from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.ring_3d.fan_in_sweep import (
    aggregate_sweep,
    render_sweep_report,
    sweep_point,
)
from experiments.ring_3d.generate import dp_fan_in


def comparison(fan_in: int, *, trims: int, reduction_percent: float) -> dict:
    metric = {
        "baseline_mean_ns": 1_000.0,
        "policy_mean_ns": 1_000.0 - reduction_percent * 10,
        "mean_reduction_ns": reduction_percent * 10,
        "mean_reduction_percent": reduction_percent,
        "reduction_standard_deviation_ns": 0.0,
        "reduction_ci95_ns": None,
    }
    congestion = {
        "trim_notification_count": trims,
        "data_natural_buffer_drop_count": 2,
        "max_queue_bytes": 4 * 1024 * 1024,
        "completed_pause_interval_count": 0,
    }
    return {
        "profile": "/runs/profile.json",
        "selection_policy": {
            "semantics": "logical_admission_selection",
            "baseline": {"p_low": 0.005, "p_high": 0.005},
            "policy": {"p_low": 0.005, "p_high": 0.1},
        },
        "dp_all_reduce_implementation": (
            "direct" if fan_in == 7 else f"direct{fan_in}"
        ),
        "dp_fan_in": fan_in,
        "seeds": [314159265],
        "per_seed": [
            {
                "seed": 314159265,
                "congestion": {
                    "fixed_p_low_baseline": dict(congestion),
                    "dblp_policy": {**congestion, "trim_notification_count": 1},
                },
            }
        ],
        "aggregate": {
            "makespan_ns": dict(metric),
            "dp_all_reduce_collective_operation_span_p99_ns": dict(metric),
            "dp_all_reduce_physical_bytes": dict(metric),
        },
    }


def write_comparisons(directory: Path, documents: list[dict]) -> list[Path]:
    paths = []
    for index, document in enumerate(documents):
        path = directory / f"point_{index}" / "comparison.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(document), encoding="utf-8")
        paths.append(path)
    return paths


class DpFanInTests(unittest.TestCase):
    def test_fan_in_follows_algorithm_and_window(self) -> None:
        self.assertEqual(dp_fan_in(8, "ring"), 1)
        self.assertEqual(dp_fan_in(8, "direct"), 7)
        self.assertEqual(dp_fan_in(8, "direct1"), 1)
        self.assertEqual(dp_fan_in(8, "direct4"), 4)
        # The window cannot exceed the peer count.
        self.assertEqual(dp_fan_in(4, "direct16"), 3)
        # A single replica has no DP traffic at all.
        self.assertEqual(dp_fan_in(1, "direct"), 0)
        self.assertEqual(dp_fan_in(1, "ring"), 0)


class FanInSweepTests(unittest.TestCase):
    def test_sweep_orders_points_by_fan_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = write_comparisons(
                Path(temporary_directory),
                [
                    comparison(7, trims=900, reduction_percent=12.0),
                    comparison(1, trims=3, reduction_percent=0.1),
                    comparison(4, trims=200, reduction_percent=5.0),
                ],
            )
            sweep = aggregate_sweep(paths)

        self.assertEqual(
            [point["dp_fan_in"] for point in sweep["points"]], [1, 4, 7]
        )
        self.assertEqual(sweep["swept_variable"], "dp_fan_in")
        first = sweep["points"][0]
        self.assertEqual(
            first["congestion_signals"]["fixed_p_low_baseline"][
                "trim_notification_count"
            ],
            3.0,
        )
        self.assertEqual(
            first["congestion_signals"]["dblp_policy"][
                "trim_notification_count"
            ],
            1.0,
        )

    def test_sweep_rejects_duplicate_fan_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = write_comparisons(
                Path(temporary_directory),
                [
                    comparison(4, trims=10, reduction_percent=1.0),
                    comparison(4, trims=20, reduction_percent=2.0),
                ],
            )
            with self.assertRaisesRegex(ValueError, "distinct dp_fan_in"):
                aggregate_sweep(paths)

    def test_sweep_rejects_mismatched_policies(self) -> None:
        mismatched = comparison(7, trims=900, reduction_percent=12.0)
        mismatched["selection_policy"]["policy"]["p_high"] = 0.4
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = write_comparisons(
                Path(temporary_directory),
                [comparison(1, trims=3, reduction_percent=0.1), mismatched],
            )
            with self.assertRaisesRegex(ValueError, "selection_policy"):
                aggregate_sweep(paths)

    def test_sweep_requires_provenance_fields(self) -> None:
        legacy = comparison(4, trims=10, reduction_percent=1.0)
        del legacy["dp_fan_in"]
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = write_comparisons(
                Path(temporary_directory),
                [comparison(1, trims=3, reduction_percent=0.1), legacy],
            )
            with self.assertRaisesRegex(ValueError, "dp_fan_in"):
                aggregate_sweep(paths)

    def test_sweep_requires_at_least_two_points(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = write_comparisons(
                Path(temporary_directory),
                [comparison(1, trims=3, reduction_percent=0.1)],
            )
            with self.assertRaisesRegex(ValueError, "at least two"):
                aggregate_sweep(paths)

    def test_report_renders_both_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = write_comparisons(
                Path(temporary_directory),
                [
                    comparison(1, trims=3, reduction_percent=0.1),
                    comparison(7, trims=900, reduction_percent=12.0),
                ],
            )
            report = render_sweep_report(aggregate_sweep(paths))

        self.assertIn("# DP fan-in sweep", report)
        self.assertIn("Buffer pressure against fan-in", report)
        self.assertIn("Policy relief against fan-in", report)
        self.assertIn("| 7 | `direct` | 900.0 | 1.0 |", report)
        self.assertIn("| 7 | 12.00% | 12.00% | 12.00% |", report)


if __name__ == "__main__":
    unittest.main()
