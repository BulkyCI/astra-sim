"""Laws of the segment-sealing algebra and the asset-name mapping."""

import unittest

from segment_uploader import asset_name, sealed_segments, segment_index


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
        ):
            self.assertIsNone(segment_index(name), name)


class SealedSegmentsTests(unittest.TestCase):
    def test_highest_index_per_base_is_held_back(self) -> None:
        paths = [
            "a/x.csv.zst.000",
            "a/x.csv.zst.001",
            "a/x.csv.zst.002",
            "b/y.csv.zst.000",
            "notes.txt",
        ]
        self.assertEqual(
            sealed_segments(paths, drain=False),
            ["a/x.csv.zst.000", "a/x.csv.zst.001"],
        )

    def test_single_segment_is_never_sealed_while_writer_lives(self) -> None:
        self.assertEqual(sealed_segments(["x.csv.zst.000"], drain=False), [])

    def test_drain_ships_everything(self) -> None:
        paths = ["x.csv.zst.000", "x.csv.zst.001"]
        self.assertEqual(sealed_segments(paths, drain=True), paths)

    def test_ordering_is_numeric_not_lexical(self) -> None:
        paths = ["x.csv.zst.010", "x.csv.zst.002", "x.csv.zst.011"]
        self.assertEqual(
            sealed_segments(paths, drain=False),
            ["x.csv.zst.002", "x.csv.zst.010"],
        )


class AssetNameTests(unittest.TestCase):
    def test_matches_release_archive_convention(self) -> None:
        self.assertEqual(
            asset_name("ring-3d-llama3-70b-64-sr2x-comparison",
                       "seed_1/ns3/transport_events.csv.zst.003"),
            "ring-3d-llama3-70b-64-sr2x-comparison--"
            "seed_1__ns3__transport_events.csv.zst.003",
        )


if __name__ == "__main__":
    unittest.main()
