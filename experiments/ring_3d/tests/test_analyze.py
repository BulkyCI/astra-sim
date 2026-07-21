from __future__ import annotations

import csv
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
    "decision_hash",
    "start_time_ns",
    "end_time_ns",
]


class Ring3DAnalysisTests(unittest.TestCase):
    def write_telemetry(
        self,
        directory: Path,
        flows: dict[str, str] | list[dict[str, str]],
        completions: list[tuple[int, int]] | None = None,
    ) -> None:
        directory.mkdir(parents=True)
        if isinstance(flows, dict):
            flows = [flows]
        with (directory / "flow_events.csv").open("w", newline="", encoding="utf-8") as handle:
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
            (ns3 / "pfc.txt").write_text("pause\nresume\n", encoding="utf-8")

            summary = summarize(telemetry, fct, ns3)

            self.assertEqual(summary["fct_join"]["status"], "verified")
            self.assertEqual(summary["fct_join"]["fct_record_count"], 5)
            self.assertEqual(summary["flow_completion_time_ns"]["all"]["p50_ns"], 30)
            self.assertEqual(summary["flow_completion_time_ns"]["all"]["p95_ns"], 50)
            self.assertEqual(summary["rank_completion_time_ns"]["p50_ns"], 120)
            self.assertEqual(summary["rank_completion_time_ns"]["max_ns"], 140)
            self.assertEqual(summary["ns3_observability"]["queue"]["max_queue_bytes"], 240)
            self.assertEqual(summary["ns3_observability"]["pfc"]["event_count"], 2)

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


if __name__ == "__main__":
    unittest.main()