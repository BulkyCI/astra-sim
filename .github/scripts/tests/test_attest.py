"""Laws of the attestation composition and its total classifications."""

import json
import os
import tempfile
import unittest
from unittest import mock

from attest import (
    build_attestation,
    gather_outputs,
    gather_stream,
    main,
    parse_cpu,
    parse_mem_total_kb,
    provenance_markdown,
    stream_status,
)
from segment_hasher import DIGEST_FILENAME

CPUINFO = """\
processor\t: 0
model name\t: AMD EPYC 9634 84-Core Processor
flags\t\t: fpu avx2 fma avx512f avx512dq avx512cd avx512bw avx512vl sse4_2
processor\t: 1
model name\t: AMD EPYC 9634 84-Core Processor
"""


class ParserTests(unittest.TestCase):
    def test_cpu_parse_takes_first_processor_and_filters_flags(self) -> None:
        cpu = parse_cpu(CPUINFO)
        self.assertEqual(cpu["model"], "AMD EPYC 9634 84-Core Processor")
        self.assertEqual(
            cpu["isa_flags"],
            ["avx2", "fma", "avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl"],
        )

    def test_cpu_parse_is_total_on_garbage(self) -> None:
        self.assertEqual(parse_cpu(""), {"model": "", "isa_flags": []})
        self.assertEqual(parse_cpu("no colons here"), {"model": "", "isa_flags": []})

    def test_mem_total_parses_and_survives_absence(self) -> None:
        self.assertEqual(parse_mem_total_kb("MemTotal:  527987256 kB\n"), 527987256)
        self.assertEqual(parse_mem_total_kb(""), 0)
        self.assertEqual(parse_mem_total_kb("MemTotal: soon kB"), 0)


class StreamStatusTests(unittest.TestCase):
    """Total over the (digest presence x completeness x leftovers) space."""

    def test_no_digest_is_absent(self) -> None:
        self.assertEqual(stream_status(None, 0), "absent")
        # Leftover segments without a digest still classify - as absent,
        # because the hasher's testimony, not the files, is what is missing.
        self.assertEqual(stream_status(None, 3), "absent")

    def test_clean_drain_is_complete(self) -> None:
        digest = {"complete": True, "bases": {"a.zst": {"complete": True}}}
        self.assertEqual(stream_status(digest, 0), "complete")

    def test_any_incompleteness_is_partial(self) -> None:
        drained_with_bad_base = {
            "complete": True,
            "bases": {"a.zst": {"complete": False}},
        }
        self.assertEqual(stream_status(drained_with_bad_base, 0), "partial")
        undrained = {"complete": False, "bases": {"a.zst": {"complete": True}}}
        self.assertEqual(stream_status(undrained, 0), "partial")
        leftover = {"complete": True, "bases": {"a.zst": {"complete": True}}}
        self.assertEqual(stream_status(leftover, 2), "partial")


class ProvenanceMarkdownTests(unittest.TestCase):
    def attestation(self) -> dict:
        return build_attestation(
            identity={"ledger_key": "llama3-70b-32-direct"},
            code={
                "march": "x86-64-v4",
                "binary_sha256": "ab" * 32,
                "bundle": "cluster-runtime-1-x86-64-v4",
            },
            machine={
                "hostname": "node7",
                "cpu": {"model": "AMD EPYC 9634"},
                "glibc": "2.39",
                "kernel": "6.8.0",
                "slurm_job_id": "64274",
            },
            stream={
                "status": "complete",
                "bases": {
                    "seed_1/ns3/transport_events.csv.zst": {
                        "stream_sha256": "cd" * 32,
                        "uncompressed_bytes": 2**30,
                        "segment_count": 4,
                        "complete": True,
                    }
                },
            },
            outputs=[],
        )

    def test_section_carries_the_full_commitment(self) -> None:
        markdown = provenance_markdown(self.attestation())
        self.assertIn("## Provenance", markdown)
        self.assertIn("ab" * 32, markdown)  # binary identity, full hash
        self.assertIn("cd" * 32, markdown)  # stream commitment, full hash
        self.assertIn("x86-64-v4", markdown)
        self.assertIn("complete", markdown)
        self.assertNotIn("(incomplete)", markdown)

    def test_incomplete_stream_is_marked_inline(self) -> None:
        attestation = self.attestation()
        attestation["stream"]["status"] = "partial"
        base = attestation["stream"]["bases"]["seed_1/ns3/transport_events.csv.zst"]
        base["complete"] = False
        self.assertIn("(incomplete)", provenance_markdown(attestation))

    def test_absent_stream_renders_without_a_hash_table(self) -> None:
        attestation = self.attestation()
        attestation["stream"] = {"status": "absent", "bases": {}}
        markdown = provenance_markdown(attestation)
        self.assertIn("absent", markdown)
        self.assertNotIn("| Stream (uncompressed content) |", markdown)


class GatherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = self.dir.name

    def write(self, relative: str, payload: bytes) -> None:
        path = os.path.join(self.root, relative)
        os.makedirs(os.path.dirname(path) or self.root, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(payload)

    def test_outputs_exclude_segments_and_the_attestation_itself(self) -> None:
        self.write("comparison.json", b"{}")
        self.write("ns3/transport_summary.csv", b"event,plane\n")
        self.write("ns3/transport_events.csv.zst.007", b"leftover")
        self.write("attestation.json", b"{}")
        recorded = {entry["path"] for entry in gather_outputs(self.root)}
        self.assertEqual(recorded, {"comparison.json", "ns3/transport_summary.csv"})

    def test_corrupt_digest_degrades_to_absent_with_a_note(self) -> None:
        # A hasher defect must cost only the stream section, never the
        # attestation: outputs and code identity still attest.
        for payload in (b"not json at all", b"[1, 2, 3]"):
            self.write(DIGEST_FILENAME, payload)
            stream = gather_stream(self.root)
            self.assertEqual(stream["status"], "absent")
            self.assertIn("digest unreadable", stream["note"])
            self.assertEqual(stream["bases"], {})

    def test_stream_gather_reads_digest_and_counts_leftovers(self) -> None:
        digest = {"complete": True, "bases": {"e.zst": {"complete": True}}}
        self.write(DIGEST_FILENAME, json.dumps(digest).encode())
        self.write("e.zst.004", b"straggler")
        stream = gather_stream(self.root)
        self.assertEqual(stream["status"], "partial")
        self.assertEqual(stream["leftover_segments"], ["e.zst.004"])

    def test_end_to_end_writes_attestation_and_amends_report_first(self) -> None:
        digest = {
            "complete": True,
            "bases": {
                "e.zst": {
                    "complete": True,
                    "stream_sha256": "ef" * 32,
                    "uncompressed_bytes": 10,
                    "segment_count": 1,
                    "segments": [],
                }
            },
        }
        self.write(DIGEST_FILENAME, json.dumps(digest).encode())
        self.write("comparison_report.md", b"# Report\n")
        report = os.path.join(self.root, "comparison_report.md")
        argv = [
            "attest.py",
            "--run-dir",
            self.root,
            "--march",
            "x86-64-v3",
            "--bundle",
            "cluster-runtime-1-x86-64-v3",
            "--report",
            report,
        ]
        with mock.patch("sys.argv", argv):
            self.assertEqual(main(), 0)
        with open(os.path.join(self.root, "attestation.json"), encoding="utf-8") as f:
            attestation = json.load(f)
        self.assertEqual(attestation["schema"], 1)
        self.assertEqual(attestation["stream"]["status"], "complete")
        with open(report, encoding="utf-8") as f:
            amended = f.read()
        self.assertIn("## Provenance", amended)
        # The recorded report digest must match the amended file: the
        # provenance append happens before the output hashing pass.
        import hashlib

        (report_entry,) = [
            entry
            for entry in attestation["outputs"]
            if entry["path"] == "comparison_report.md"
        ]
        self.assertEqual(
            report_entry["sha256"],
            hashlib.sha256(amended.encode("utf-8")).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
