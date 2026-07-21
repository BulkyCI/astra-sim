from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.ring_3d.report import render_report


FLOW_FIELDS = [
    "flow_kind",
    "decision",
    "admission_eligible",
    "parallelism_domain",
    "origin_transport_role",
    "transport_role",
    "collective_type",
    "training_step",
    "workload_node_id",
    "message_sequence",
    "src",
    "dst",
    "tag",
    "source_port",
    "priority_group",
    "logical_bytes",
    "physical_bytes",
    "decision_hash",
    "start_time_ns",
    "end_time_ns",
]


class Ring3DReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile_path = REPOSITORY_ROOT / "experiments/ring_3d/profiles/smoke_8.json"

    def _write_completed_run(self, run_dir: Path) -> None:
        telemetry_dir = run_dir / "telemetry"
        telemetry_dir.mkdir(parents=True)
        run_dir.joinpath("experiment.json").write_text(
            json.dumps(
                {
                    "eligibility": "dp_all_reduce_only",
                    "default_priority_group": 3,
                    "provenance": {"control_bytes": 64, "priority_group": 1},
                    "drop_probability_by_step": {"1": 0.0, "2": 0.1, "3": 0.1},
                    "microburst": {"enabled": True, "trigger_step": 2},
                }
            ),
            encoding="utf-8",
        )
        run_dir.joinpath("summary.json").write_text(
            json.dumps(
                {
                    "flow_count": 2,
                    "shed_flow_count": 1,
                    "total_logical_bytes": 262_208,
                    "total_physical_bytes": 131_136,
                    "shed_logical_bytes": 131_072,
                    "completion_rank_count": 8,
                    "completion_time_ns_max": 2_500,
                    "rank_completion_time_ns": {
                        "count": 8,
                        "min_ns": 2_000,
                        "p50_ns": 2_200,
                        "p95_ns": 2_500,
                        "p99_ns": 2_500,
                        "max_ns": 2_500,
                    },
                    "flow_completion_time_ns": {
                        "all": {
                            "count": 2,
                            "min_ns": 99,
                            "p50_ns": 99,
                            "p95_ns": 100,
                            "p99_ns": 100,
                            "max_ns": 100,
                        },
                        "by_training_step": {},
                        "by_parallelism_domain": {},
                        "by_flow_kind": {
                            "foreground_payload": {
                                "count": 1,
                                "min_ns": 100,
                                "p50_ns": 100,
                                "p95_ns": 100,
                                "p99_ns": 100,
                                "max_ns": 100,
                            }
                        },
                        "by_parallelism_domain_and_flow_kind": {
                            "dp": {
                                "foreground_payload": {
                                    "count": 1,
                                    "min_ns": 100,
                                    "p50_ns": 100,
                                    "p95_ns": 100,
                                    "p99_ns": 100,
                                    "max_ns": 100,
                                }
                            }
                        },
                    },
                    "fct_join": {
                        "status": "verified",
                        "telemetry_flow_count": 2,
                        "fct_record_count": 2,
                    },
                    "ns3_observability": {
                        "queue": {
                            "status": "available",
                            "sample_count": 3,
                            "observed_queue_count": 2,
                            "max_queue_bytes": 4_096,
                        },
                        "pfc": {"status": "available", "event_count": 1},
                    },
                    "by_training_step": {
                        "1": {
                            "flows": 1,
                            "shed_flows": 0,
                            "logical_bytes": 131_072,
                            "physical_bytes": 131_072,
                        },
                        "2": {
                            "flows": 1,
                            "shed_flows": 1,
                            "logical_bytes": 131_136,
                            "physical_bytes": 64,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        flows = [
            {
                "flow_kind": "foreground_payload",
                "decision": "admitted",
                "admission_eligible": "true",
                "parallelism_domain": "dp",
                "origin_transport_role": "collective_payload",
                "transport_role": "collective_payload",
                "collective_type": "all_reduce",
                "training_step": "1",
                "workload_node_id": "1",
                "message_sequence": "1",
                "src": "0",
                "dst": "4",
                "tag": "1",
                "source_port": "10000",
                "priority_group": "3",
                "logical_bytes": "131072",
                "physical_bytes": "131072",
                "decision_hash": "1",
                "start_time_ns": "0",
                "end_time_ns": "100",
            },
            {
                "flow_kind": "provenance_control",
                "decision": "shed",
                "admission_eligible": "true",
                "parallelism_domain": "dp",
                "origin_transport_role": "collective_payload",
                "transport_role": "provenance_control",
                "collective_type": "all_reduce",
                "training_step": "2",
                "workload_node_id": "2",
                "message_sequence": "2",
                "src": "0",
                "dst": "4",
                "tag": "2",
                "source_port": "10001",
                "priority_group": "1",
                "logical_bytes": "131136",
                "physical_bytes": "64",
                "decision_hash": "2",
                "start_time_ns": "101",
                "end_time_ns": "200",
            },
        ]
        with (telemetry_dir / "flow_events.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FLOW_FIELDS)
            writer.writeheader()
            writer.writerows(flows)
        with (telemetry_dir / "rank_completion.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["rank", "completion_time_ns"])
            writer.writerows((rank, 2_500) for rank in range(8))

    def test_report_renders_experiment_and_measured_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "run"
            self._write_completed_run(run_dir)

            report = render_report(run_dir, self.profile_path)

            self.assertIn("# 3D Ring ns-3 researcher report", report)
            self.assertIn("TP=2 × PP=2 × DP=2", report)
            self.assertIn("8 unique / 8 expected (complete)", report)
            self.assertIn("PASS — DP-only shedding", report)
            self.assertIn("Protected provenance control", report)
            self.assertIn("Suppressed logical DP bytes", report)
            self.assertIn("By training step", report)
            self.assertIn("DP All-Reduce admission decisions", report)
            self.assertIn("Observed rate", report)
            self.assertIn("By parallelism domain", report)
            self.assertIn("provenance_control", report)
            self.assertIn("Telemetry ↔ ns-3 FCT join", report)
            self.assertIn("Per-QP flow-completion time", report)
            self.assertIn("Simulated rank-completion distribution", report)
            self.assertIn("ns-3 congestion observability", report)

    def test_report_explains_missing_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = render_report(Path(temporary_directory) / "absent", self.profile_path)

            self.assertIn("results unavailable", report)
            self.assertIn("TP=2 × PP=2 × DP=2", report)


if __name__ == "__main__":
    unittest.main()
