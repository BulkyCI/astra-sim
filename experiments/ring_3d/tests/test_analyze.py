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

from experiments.ring_3d.analyze import summarize

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
    "data_attempted_bytes",
    "retransmitted_bytes",
    "trimmed_payload_bytes",
    "recovery_events",
    "trim_notifications",
    "trim_ftd_repairs",
    "trim_bts_notifications",
    "trim_lasthop_notifications",
    "trim_recovery_events",
    "stale_trim_notifications",
    "terminal_outcome",
    "failure_reason",
    "decision_hash",
    "start_time_ns",
    "end_time_ns",
]

COLLECTIVE_FIELDS = [
    "rank",
    "parallelism_domain",
    "collective_type",
    "training_step",
    "workload_node_id",
    "logical_bytes",
    "start_time_ns",
    "end_time_ns",
]


class Ring3DAnalysisTests(unittest.TestCase):
    def write_telemetry(
        self,
        directory: Path,
        flows: dict[str, str] | list[dict[str, str]],
        completions: list[tuple[int, int]] | None = None,
        collectives: list[dict[str, str]] | None = None,
    ) -> None:
        directory.mkdir(parents=True)
        if isinstance(flows, dict):
            flows = [flows]
        with (directory / "flow_events.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=FLOW_FIELDS)
            writer.writeheader()
            writer.writerows(flows)
        (directory / "rank_completion.csv").write_text(
            "rank,completion_time_ns\n"
            + "".join(
                f"{rank},{completion_time_ns}\n"
                for rank, completion_time_ns in (completions or [(0, 100), (1, 120)])
            ),
            encoding="utf-8",
        )
        if collectives is not None:
            with (directory / "collective_events.csv").open(
                "w", newline="", encoding="utf-8"
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=COLLECTIVE_FIELDS)
                writer.writeheader()
                writer.writerows(collectives)

    def write_fct(self, directory: Path, flows: list[dict[str, str]]) -> Path:
        directory.mkdir(parents=True)
        lines = []
        for flow in flows:
            source_address = 0x0B000001 | (int(flow["src"]) << 8)
            destination_address = 0x0B000001 | (int(flow["dst"]) << 8)
            duration = int(flow["end_time_ns"]) - int(flow["start_time_ns"])
            lines.append(
                f"{source_address:08x} {destination_address:08x} "
                f"{flow['source_port']} 100 {flow['physical_bytes']} "
                f"{flow['start_time_ns']} {duration} {duration}\n"
            )
        path = directory / "fct.txt"
        path.write_text("".join(lines), encoding="utf-8")
        return path

    def valid_shed_flow(self) -> dict[str, str]:
        return {
            "flow_kind": "provenance_control",
            "decision": "shed",
            "admission_eligible": "true",
            "parallelism_domain": "dp",
            "origin_transport_role": "collective_payload",
            "transport_role": "provenance_control",
            "collective_type": "all_reduce",
            "training_step": "2",
            "workload_node_id": "7",
            "message_sequence": "3",
            "src": "0",
            "dst": "4",
            "tag": "5",
            "source_port": "10000",
            "priority_group": "1",
            "logical_bytes": "1048576",
            "physical_bytes": "64",
            "data_attempted_bytes": "64",
            "retransmitted_bytes": "0",
            "trimmed_payload_bytes": "0",
            "recovery_events": "0",
            "trim_notifications": "0",
            "trim_ftd_repairs": "0",
            "trim_bts_notifications": "0",
            "trim_lasthop_notifications": "0",
            "trim_recovery_events": "0",
            "stale_trim_notifications": "0",
            "terminal_outcome": "completed",
            "failure_reason": "",
            "decision_hash": "42",
            "start_time_ns": "10",
            "end_time_ns": "20",
        }

    def test_summary_accepts_dp_all_reduce_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "telemetry"
            self.write_telemetry(telemetry, self.valid_shed_flow())
            summary = summarize(telemetry)
            self.assertEqual(summary["shed_flow_count"], 1)
            self.assertEqual(summary["total_physical_bytes"], 64)
            self.assertEqual(summary["completion_time_ns_max"], 120)

    def test_summary_rejects_missing_terminal_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "telemetry"
            missing_outcome = self.valid_shed_flow()
            missing_outcome.pop("terminal_outcome")
            self.write_telemetry(telemetry, missing_outcome)

            with self.assertRaisesRegex(ValueError, "terminal outcome"):
                summarize(telemetry)

    def test_summary_rejects_non_dp_shedding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "telemetry"
            invalid = self.valid_shed_flow()
            invalid["parallelism_domain"] = "tp"
            self.write_telemetry(telemetry, invalid)
            with self.assertRaisesRegex(ValueError, "outside DP All-Reduce"):
                summarize(telemetry)

    def test_summary_reports_verified_fct_latency_and_ns3_observability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            flows = []
            for index, duration in enumerate((10, 20, 30, 40, 50)):
                flow = self.valid_shed_flow()
                flow["source_port"] = str(10_000 + index)
                flow["workload_node_id"] = str(index)
                flow["message_sequence"] = str(index)
                flow["start_time_ns"] = str(100 + index * 100)
                flow["end_time_ns"] = str(100 + index * 100 + duration)
                if index:
                    flow.update(
                        {
                            "flow_kind": "foreground_payload",
                            "decision": "admitted",
                            "admission_eligible": "false",
                            "transport_role": "collective_payload",
                            "logical_bytes": "1024",
                            "physical_bytes": "1024",
                        }
                    )
                flows.append(flow)
            self.write_telemetry(telemetry, flows, [(0, 100), (1, 120), (2, 140)])
            ns3 = root / "ns3"
            fct = self.write_fct(ns3, flows)
            (ns3 / "qlen.txt").write_text(
                "time 10 8 j 3 120 j 4 240\ntime 20 8 j 3 180\n",
                encoding="utf-8",
            )
            (ns3 / "pfc.txt").write_text(
                "10 8 1 3 3 1\n20 8 1 3 3 0\n", encoding="utf-8"
            )

            summary = summarize(telemetry, fct, ns3)

            self.assertEqual(summary["fct_join"]["status"], "verified")
            self.assertEqual(summary["fct_join"]["fct_record_count"], 5)
            self.assertEqual(summary["flow_completion_time_ns"]["all"]["p50_ns"], 30)
            self.assertEqual(summary["flow_completion_time_ns"]["all"]["p95_ns"], 50)
            self.assertEqual(summary["rank_completion_time_ns"]["p50_ns"], 120)
            self.assertEqual(summary["rank_completion_time_ns"]["max_ns"], 140)
            self.assertEqual(
                summary["ns3_observability"]["queue"]["max_queue_bytes"], 240
            )
            self.assertEqual(summary["ns3_observability"]["pfc"]["event_count"], 2)
            self.assertEqual(summary["ns3_observability"]["pfc"]["total_paused_ns"], 10)
            self.assertEqual(
                summary["ns3_observability"]["pfc"]["affected_switch_port_queues"],
                [{"switch": 8, "port": 3, "queue": 3}],
            )

    def test_summary_reports_data_loss_without_control_injection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            self.write_telemetry(telemetry, self.valid_shed_flow())
            ns3 = root / "ns3"
            ns3.mkdir()
            (ns3 / "transport_events.csv").write_text(
                "time_ns,event,plane,protocol,node,node_type,interface,"
                "source_host,destination_host,source_port,packet_bytes,queue\n"
                "10,data_arrival,data,17,8,1,1,0,4,10000,1024,-1\n"
                "10,data_injected_drop,data,17,8,1,1,0,4,10000,1024,-1\n"
                "20,control_arrival,control,252,0,0,1,4,0,100,60,-1\n"
                "20,control_deliver,control,252,0,0,1,4,0,100,60,-1\n",
                encoding="utf-8",
            )

            summary = summarize(telemetry, ns3_dir=ns3)

            transport = summary["ns3_observability"]["transport"]
            self.assertEqual(transport["status"], "available")
            self.assertEqual(transport["data_injected_drop_count"], 1)
            self.assertEqual(transport["control_injected_drop_count"], 0)
            self.assertEqual(transport["plane_event_counts"], {"data": 2, "control": 2})

    def test_summary_distinguishes_natural_data_and_control_buffer_drops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            self.write_telemetry(telemetry, self.valid_shed_flow())
            ns3 = root / "ns3"
            ns3.mkdir()
            (ns3 / "transport_events.csv").write_text(
                "time_ns,event,plane,protocol,node,node_type,interface,"
                "source_host,destination_host,source_port,packet_bytes,queue\n"
                "10,switch_admission_drop,data,17,8,1,-1,0,4,10000,1024,-1\n"
                "11,switch_egress_queue_drop,data,17,8,1,-1,0,4,10000,1024,-1\n"
                "12,switch_egress_queue_drop,control,252,8,1,-1,4,0,10000,60,-1\n",
                encoding="utf-8",
            )

            summary = summarize(telemetry, ns3_dir=ns3)

            transport = summary["ns3_observability"]["transport"]
            self.assertEqual(transport["data_natural_buffer_drop_count"], 2)
            self.assertEqual(transport["control_natural_buffer_drop_count"], 1)
            self.assertEqual(transport["data_injected_drop_count"], 0)

    def test_summary_reconciles_ftd_trim_with_required_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            trimmed = self.valid_shed_flow()
            trimmed.update(
                {
                    "flow_kind": "foreground_payload",
                    "decision": "admitted",
                    "admission_eligible": "false",
                    "transport_role": "collective_payload",
                    "logical_bytes": "1024",
                    "physical_bytes": "1024",
                    "data_attempted_bytes": "2048",
                    "retransmitted_bytes": "1024",
                    "trimmed_payload_bytes": "1000",
                    "trim_notifications": "1",
                    "trim_ftd_repairs": "1",
                    "trim_recovery_events": "1",
                }
            )
            self.write_telemetry(telemetry, trimmed)
            ns3 = root / "ns3"
            ns3.mkdir()
            (ns3 / "transport_events.csv").write_text(
                "time_ns,event,plane,protocol,node,node_type,interface,"
                "source_host,destination_host,source_port,packet_bytes,queue\n"
                "10,trim_ftd_admission,data,17,8,1,-1,0,4,10000,1000,-1\n"
                "11,control_arrival,control,251,4,0,1,0,4,10000,60,-1\n"
                "12,control_deliver,control,250,0,0,1,4,0,10000,60,-1\n",
                encoding="utf-8",
            )

            summary = summarize(telemetry, ns3_dir=ns3)

            trim = summary["ns3_observability"]["transport"]["packet_trimming"]
            self.assertEqual(trim["conversion_count"], 1)
            self.assertEqual(trim["trimmed_payload_bytes"], 1000)
            self.assertEqual(trim["ftd_conversion_count"], 1)
            self.assertEqual(trim["lasthop_conversion_count"], 0)
            self.assertEqual(trim["trimmed_queue_drop_count"], 0)
            self.assertEqual(summary["transport_recovery"]["trim_ftd_repair_count"], 1)

    def test_summary_counts_lasthop_trims_and_trimmed_queue_drops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            trimmed = self.valid_shed_flow()
            trimmed.update(
                {
                    "flow_kind": "foreground_payload",
                    "decision": "admitted",
                    "admission_eligible": "false",
                    "transport_role": "collective_payload",
                    "logical_bytes": "1024",
                    "physical_bytes": "1024",
                    "data_attempted_bytes": "2048",
                    "retransmitted_bytes": "1024",
                    "trimmed_payload_bytes": "1000",
                    "trim_notifications": "1",
                    "trim_ftd_repairs": "1",
                    "trim_lasthop_notifications": "1",
                    "trim_recovery_events": "1",
                }
            )
            self.write_telemetry(telemetry, trimmed)
            ns3 = root / "ns3"
            ns3.mkdir()
            (ns3 / "transport_events.csv").write_text(
                "time_ns,event,plane,protocol,node,node_type,interface,"
                "source_host,destination_host,source_port,packet_bytes,queue\n"
                "10,trim_ftd_lasthop_admission,data,17,8,1,-1,0,4,10000,1000,-1\n"
                "11,switch_trimmed_queue_drop,data,17,8,1,-1,0,4,10000,60,-1\n",
                encoding="utf-8",
            )

            summary = summarize(telemetry, ns3_dir=ns3)

            trim = summary["ns3_observability"]["transport"]["packet_trimming"]
            self.assertEqual(trim["conversion_count"], 1)
            self.assertEqual(trim["ftd_conversion_count"], 1)
            self.assertEqual(trim["lasthop_conversion_count"], 1)
            self.assertEqual(trim["admission_conversion_count"], 1)
            self.assertEqual(trim["trimmed_queue_drop_count"], 1)
            self.assertEqual(
                summary["transport_recovery"]["trim_lasthop_notification_count"], 1
            )

    def test_summary_requires_exact_expected_rank_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "telemetry"
            self.write_telemetry(
                telemetry, self.valid_shed_flow(), [(0, 100), (1, 120)]
            )

            summary = summarize(telemetry, expected_rank_count=2)

            self.assertEqual(
                summary["rank_completion_status"],
                {
                    "status": "verified",
                    "recorded_rank_count": 2,
                    "expected_rank_count": 2,
                },
            )
            self.assertEqual(
                summary["primary_analysis_eligibility"]["status"], "ineligible"
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "telemetry"
            self.write_telemetry(
                telemetry, self.valid_shed_flow(), [(0, 100), (2, 120)]
            )
            with self.assertRaisesRegex(
                ValueError, "does not cover every expected rank"
            ):
                summarize(telemetry, expected_rank_count=2)

        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "telemetry"
            self.write_telemetry(
                telemetry, self.valid_shed_flow(), [(0, 100), (0, 120)]
            )
            with self.assertRaisesRegex(ValueError, "duplicate rank"):
                summarize(telemetry, expected_rank_count=2)

    def test_summary_rejects_control_configured_loss_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            self.write_telemetry(telemetry, self.valid_shed_flow())
            ns3 = root / "ns3"
            ns3.mkdir()
            (ns3 / "transport_events.csv").write_text(
                "time_ns,event,plane,protocol,node,node_type,interface,"
                "source_host,destination_host,source_port,packet_bytes,queue\n"
                "10,data_injected_drop,control,252,0,0,1,4,0,100,60,-1\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "configured data impairment"):
                summarize(telemetry, ns3_dir=ns3)

    def test_summary_reports_explicit_failed_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "telemetry"
            failed = self.valid_shed_flow()
            failed.update(
                {
                    "flow_kind": "foreground_payload",
                    "decision": "admitted",
                    "admission_eligible": "false",
                    "transport_role": "collective_payload",
                    "logical_bytes": "1024",
                    "physical_bytes": "1024",
                    "data_attempted_bytes": "4096",
                    "retransmitted_bytes": "3072",
                    "recovery_events": "3",
                    "terminal_outcome": "failed",
                    "failure_reason": "retry_exhausted",
                }
            )
            self.write_telemetry(telemetry, failed, completions=[])

            summary = summarize(telemetry)

            self.assertEqual(summary["completed_flow_count"], 0)
            self.assertEqual(summary["failed_flow_count"], 1)
            self.assertEqual(
                summary["transport_recovery"],
                {
                    "data_attempted_bytes": 4096,
                    "retransmitted_bytes": 3072,
                    "recovery_event_count": 3,
                    "failed_by_reason": {"retry_exhausted": 1},
                    "trimmed_payload_bytes": 0,
                    "trim_notification_count": 0,
                    "trim_ftd_repair_count": 0,
                    "trim_bts_notification_count": 0,
                    "trim_lasthop_notification_count": 0,
                    "trim_recovery_event_count": 0,
                    "stale_trim_notification_count": 0,
                },
            )

    def test_summary_uses_native_collective_events_for_logical_latency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "telemetry"
            collectives = [
                {
                    "rank": "0",
                    "parallelism_domain": "dp",
                    "collective_type": "all_reduce",
                    "training_step": "2",
                    "workload_node_id": "7",
                    "logical_bytes": "1048576",
                    "start_time_ns": "100",
                    "end_time_ns": "160",
                },
                {
                    "rank": "1",
                    "parallelism_domain": "dp",
                    "collective_type": "all_reduce",
                    "training_step": "2",
                    "workload_node_id": "7",
                    "logical_bytes": "1048576",
                    "start_time_ns": "110",
                    "end_time_ns": "180",
                },
            ]
            self.write_telemetry(
                telemetry, self.valid_shed_flow(), collectives=collectives
            )

            summary = summarize(telemetry)

            collective = summary["collective_completion"]
            self.assertEqual(collective["status"], "available")
            self.assertEqual(collective["rank_event_count"], 2)
            self.assertEqual(collective["logical_collective_count"], 1)
            per_rank = collective["per_rank_completion_time_ns"]
            self.assertEqual(per_rank["all"]["p50_ns"], 60)
            operation_span = collective["all_rank_operation_span_ns"]
            self.assertEqual(operation_span["all"]["p99_ns"], 80)
            self.assertEqual(operation_span["by_training_step"]["2"]["max_ns"], 80)

    def test_summary_rejects_duplicate_or_reversed_collective_events(self) -> None:
        collective = {
            "rank": "0",
            "parallelism_domain": "dp",
            "collective_type": "all_reduce",
            "training_step": "2",
            "workload_node_id": "7",
            "logical_bytes": "1048576",
            "start_time_ns": "100",
            "end_time_ns": "160",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "duplicate"
            self.write_telemetry(
                telemetry,
                self.valid_shed_flow(),
                collectives=[collective, dict(collective)],
            )
            with self.assertRaisesRegex(ValueError, "duplicate rank completion"):
                summarize(telemetry)

        with tempfile.TemporaryDirectory() as temporary_directory:
            telemetry = Path(temporary_directory) / "reversed"
            reversed_collective = dict(
                collective, start_time_ns="161", end_time_ns="160"
            )
            self.write_telemetry(
                telemetry, self.valid_shed_flow(), collectives=[reversed_collective]
            )
            with self.assertRaisesRegex(ValueError, "must not be negative"):
                summarize(telemetry)

    def test_summary_labels_queue_unattributed_pfc_durations_as_estimates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            self.write_telemetry(telemetry, self.valid_shed_flow())
            ns3 = root / "ns3"
            ns3.mkdir()
            (ns3 / "pfc.txt").write_text(
                "10 8 1 3 1\n12 8 1 3 1\n20 8 1 3 0\n24 8 1 3 0\n",
                encoding="utf-8",
            )

            summary = summarize(telemetry, ns3_dir=ns3)

            pfc = summary["ns3_observability"]["pfc"]
            self.assertEqual(pfc["queue_identity_status"], "not_available")
            self.assertEqual(
                pfc["pause_duration_status"], "estimated_without_queue_identity"
            )
            self.assertEqual(pfc["completed_pause_interval_count"], 2)

    def test_summary_rejects_fct_physical_byte_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            flow = self.valid_shed_flow()
            self.write_telemetry(telemetry, flow)
            fct = self.write_fct(root / "ns3", [flow])
            fct.write_text(
                fct.read_text(encoding="utf-8").replace(" 64 10 10 10", " 65 10 10 10"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "physical-byte mismatch"):
                summarize(telemetry, fct)

    def write_manifest(
        self,
        directory: Path,
        loss: bool,
        recovery: bool,
        trimming: bool,
        pfc: bool = True,
    ) -> Path:
        path = directory / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "data_plane_loss": {"enabled": loss},
                    "transport_recovery": {"enabled": recovery},
                    "packet_trimming": {"enabled": trimming},
                    "fabric": {"pfc_enabled": pfc},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_summary_verifies_lossless_run_recorded_no_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            self.write_telemetry(telemetry, self.valid_shed_flow())
            manifest = self.write_manifest(root, False, False, False)

            summary = summarize(telemetry, manifest_path=manifest)

            self.assertEqual(summary["lossless_transport"]["status"], "verified")

    def test_summary_rejects_recovery_without_a_loss_mechanism(self) -> None:
        # A stray packet reaching a reused source port surfaces exactly here.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            flow = self.valid_shed_flow()
            flow["recovery_events"] = "1"
            self.write_telemetry(telemetry, flow)
            manifest = self.write_manifest(root, False, False, False)

            with self.assertRaisesRegex(ValueError, "models no loss mechanism"):
                summarize(telemetry, manifest_path=manifest)

    def test_summary_allows_recovery_when_the_run_models_loss(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            flow = self.valid_shed_flow()
            flow["recovery_events"] = "2"
            flow["retransmitted_bytes"] = "64"
            self.write_telemetry(telemetry, flow)
            manifest = self.write_manifest(root, False, True, False)

            summary = summarize(telemetry, manifest_path=manifest)

            self.assertEqual(summary["lossless_transport"]["status"], "not_applicable")

    def test_summary_allows_recovery_on_a_best_effort_fabric(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            flow = self.valid_shed_flow()
            flow["recovery_events"] = "1"
            self.write_telemetry(telemetry, flow)
            manifest = self.write_manifest(root, False, False, False, pfc=False)

            summary = summarize(telemetry, manifest_path=manifest)

            self.assertEqual(summary["lossless_transport"]["status"], "not_applicable")

    def test_summary_skips_the_lossless_check_without_a_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            flow = self.valid_shed_flow()
            flow["recovery_events"] = "3"
            self.write_telemetry(telemetry, flow)

            summary = summarize(telemetry)

            self.assertEqual(summary["lossless_transport"]["status"], "not_applicable")

    def test_summary_joins_reused_source_ports(self) -> None:
        # The ns-3 bridge returns a source port to its host pair once the
        # queue pair terminates, so one port names several flows in a run.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            telemetry = root / "telemetry"
            flows = []
            for index, start in enumerate((100, 400, 700)):
                flow = self.valid_shed_flow()
                flow["source_port"] = "10000"
                flow["message_sequence"] = str(index)
                flow["start_time_ns"] = str(start)
                flow["end_time_ns"] = str(start + 10 * (index + 1))
                flows.append(flow)
            self.write_telemetry(telemetry, flows)
            fct = self.write_fct(root / "ns3", flows)

            summary = summarize(telemetry, fct)

            self.assertEqual(summary["fct_join"]["status"], "verified")
            self.assertEqual(summary["fct_join"]["fct_record_count"], 3)
            self.assertEqual(summary["fct_join"]["telemetry_flow_count"], 3)


if __name__ == "__main__":
    unittest.main()
