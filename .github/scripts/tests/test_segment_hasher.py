"""Laws of the sealing algebra and the digest fold."""

import hashlib
import json
import os
import tempfile
import unittest

import zstandard

from segment_hasher import (
    DIGEST_FILENAME,
    BaseState,
    digest_snapshot,
    process_once,
    sealed_by_base,
    segment_index,
)


class SegmentIndexTests(unittest.TestCase):
    def test_parses_zero_padded_and_wide_indices(self) -> None:
        self.assertEqual(
            segment_index("ns3/transport_events.csv.zst.000"),
            ("ns3/transport_events.csv.zst", 0),
        )
        self.assertEqual(
            segment_index("transport_events.csv.zst.1042"),
            ("transport_events.csv.zst", 1042),
        )

    def test_rejects_non_segment_files(self) -> None:
        for name in (
            "transport_events.csv.zst",  # the unsegmented base itself
            "transport_summary.csv",
            "transport_events.csv.zst.0a0",
            "comparison_report.md",
            DIGEST_FILENAME,  # the hasher must never eat its own output
        ):
            self.assertIsNone(segment_index(name), name)


class SealedByBaseTests(unittest.TestCase):
    def test_highest_index_per_base_is_held_back(self) -> None:
        paths = [
            "a/x.csv.zst.000",
            "a/x.csv.zst.001",
            "a/x.csv.zst.002",
            "b/y.csv.zst.000",
            "notes.txt",
        ]
        self.assertEqual(
            sealed_by_base(paths, drain=False),
            {
                "a/x.csv.zst": ((0, "a/x.csv.zst.000"), (1, "a/x.csv.zst.001")),
                "b/y.csv.zst": (),
            },
        )

    def test_single_segment_is_never_sealed_while_writer_lives(self) -> None:
        self.assertEqual(
            sealed_by_base(["x.csv.zst.000"], drain=False), {"x.csv.zst": ()}
        )

    def test_drain_seals_everything(self) -> None:
        paths = ["x.csv.zst.000", "x.csv.zst.001"]
        self.assertEqual(
            sealed_by_base(paths, drain=True),
            {"x.csv.zst": ((0, "x.csv.zst.000"), (1, "x.csv.zst.001"))},
        )

    def test_ordering_is_numeric_not_lexical(self) -> None:
        # ".999" < ".1042" numerically but not as strings; the stream fold
        # depends on numeric order, so this is load-bearing.
        paths = ["x.csv.zst.1042", "x.csv.zst.999", "x.csv.zst.1041"]
        self.assertEqual(
            sealed_by_base(paths, drain=False),
            {"x.csv.zst": ((999, "x.csv.zst.999"), (1041, "x.csv.zst.1041"))},
        )


def compress(payload: bytes) -> bytes:
    return zstandard.ZstdCompressor().compress(payload)


class DigestFoldTests(unittest.TestCase):
    """The fold's laws, exercised against real files: the stream hash is
    sha256 of the uncompressed concatenation in index order, segments are
    deleted only after a successful fold, and anomalies are sticky."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = self.dir.name

    def write_segment(self, name: str, payload: bytes) -> None:
        path = os.path.join(self.root, name)
        os.makedirs(os.path.dirname(path) or self.root, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(compress(payload))

    def test_stream_hash_is_the_uncompressed_concatenation(self) -> None:
        pieces = [b"header,row\n", b"1,2\n" * 100, b"3,4\n" * 50]
        for index, piece in enumerate(pieces):
            self.write_segment(f"ns3/events.csv.zst.{index:03d}", piece)
        states: dict = {}
        process_once(self.root, states, drain=True, keep=False)
        snapshot = digest_snapshot(states, drained=True)
        entry = snapshot["bases"]["ns3/events.csv.zst"]
        self.assertEqual(
            entry["stream_sha256"], hashlib.sha256(b"".join(pieces)).hexdigest()
        )
        self.assertEqual(entry["uncompressed_bytes"], sum(map(len, pieces)))
        self.assertEqual(entry["segment_count"], 3)
        self.assertTrue(entry["complete"])
        # Per-segment digests localize divergence.
        self.assertEqual(
            [record["sha256"] for record in entry["segments"]],
            [hashlib.sha256(piece).hexdigest() for piece in pieces],
        )
        # Every folded segment was deleted.
        self.assertEqual(os.listdir(os.path.join(self.root, "ns3")), [])

    def test_incremental_folding_equals_one_shot_folding(self) -> None:
        pieces = [b"a" * 10, b"b" * 20, b"c" * 30]
        states: dict = {}
        # Segment 0 seals when 1 appears; the final one only at drain.
        self.write_segment("e.csv.zst.000", pieces[0])
        self.write_segment("e.csv.zst.001", pieces[1])
        process_once(self.root, states, drain=False, keep=False)
        self.assertFalse(os.path.exists(os.path.join(self.root, "e.csv.zst.000")))
        self.assertTrue(os.path.exists(os.path.join(self.root, "e.csv.zst.001")))
        self.write_segment("e.csv.zst.002", pieces[2])
        process_once(self.root, states, drain=False, keep=False)
        process_once(self.root, states, drain=True, keep=False)
        entry = digest_snapshot(states, drained=True)["bases"]["e.csv.zst"]
        self.assertEqual(
            entry["stream_sha256"], hashlib.sha256(b"".join(pieces)).hexdigest()
        )

    def test_mid_run_snapshot_is_not_complete(self) -> None:
        self.write_segment("e.csv.zst.000", b"x")
        self.write_segment("e.csv.zst.001", b"y")
        states: dict = {}
        process_once(self.root, states, drain=False, keep=False)
        entry = digest_snapshot(states, drained=False)["bases"]["e.csv.zst"]
        self.assertFalse(entry["complete"])

    def test_corrupt_segment_is_sticky_and_never_deleted(self) -> None:
        path = os.path.join(self.root, "e.csv.zst.000")
        with open(path, "wb") as handle:
            handle.write(b"this is not zstd")
        self.write_segment("e.csv.zst.001", b"fine")
        states: dict = {}
        process_once(self.root, states, drain=True, keep=False)
        entry = digest_snapshot(states, drained=True)["bases"]["e.csv.zst"]
        self.assertIn("segment 0", entry["note"])
        self.assertFalse(entry["complete"])
        # Forensics: the corrupt file survives, and so does its successor -
        # the fold stopped at the anomaly instead of hashing past a hole.
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists(os.path.join(self.root, "e.csv.zst.001")))

    def test_gap_at_drain_is_recorded(self) -> None:
        self.write_segment("e.csv.zst.001", b"orphan")
        states: dict = {}
        process_once(self.root, states, drain=True, keep=False)
        entry = digest_snapshot(states, drained=True)["bases"]["e.csv.zst"]
        self.assertIn("gap", entry["note"])
        self.assertFalse(entry["complete"])

    def test_keep_mode_hashes_without_deleting(self) -> None:
        self.write_segment("e.csv.zst.000", b"kept")
        states: dict = {}
        process_once(self.root, states, drain=True, keep=True)
        self.assertTrue(os.path.exists(os.path.join(self.root, "e.csv.zst.000")))
        entry = digest_snapshot(states, drained=True)["bases"]["e.csv.zst"]
        self.assertEqual(entry["segment_count"], 1)

    def test_snapshot_round_trips_through_json(self) -> None:
        self.write_segment("e.csv.zst.000", b"payload")
        states: dict = {}
        process_once(self.root, states, drain=True, keep=False)
        snapshot = digest_snapshot(states, drained=True)
        self.assertEqual(json.loads(json.dumps(snapshot)), snapshot)


class BaseStateTests(unittest.TestCase):
    def test_empty_state_snapshot_is_the_hash_of_nothing(self) -> None:
        entry = BaseState().snapshot(drained=False)
        self.assertEqual(entry["stream_sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(entry["uncompressed_bytes"], 0)
        self.assertEqual(entry["segments"], [])


if __name__ == "__main__":
    unittest.main()
