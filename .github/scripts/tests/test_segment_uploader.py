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



class ClassifyHttpErrorTests(unittest.TestCase):
    def test_total_over_the_status_space(self) -> None:
        from segment_uploader import classify_http_error
        for status in (200, 301, 400, 401, 403, 404, 409, 422, 429, 500, 502, 599):
            kind, wait = classify_http_error(status, None)
            self.assertIsInstance(kind, str)
            self.assertGreaterEqual(wait, 0)

    def test_documented_semantics(self) -> None:
        from segment_uploader import (
            CREDENTIAL, DUPLICATE, RATE_LIMITED, RETRY_NOW, STALE_RELEASE,
            classify_http_error,
        )
        self.assertEqual(classify_http_error(422, None)[0], DUPLICATE)
        self.assertEqual(classify_http_error(404, None)[0], STALE_RELEASE)
        self.assertEqual(classify_http_error(401, None), (CREDENTIAL, 900))
        self.assertEqual(classify_http_error(403, None), (CREDENTIAL, 900))
        self.assertEqual(
            classify_http_error(403, {"Retry-After": "120"}),
            (RATE_LIMITED, 120),
        )
        self.assertEqual(classify_http_error(429, None), (RATE_LIMITED, 60))
        self.assertEqual(classify_http_error(502, None), (RETRY_NOW, 0))

    def test_retry_after_is_capped_and_parsed_defensively(self) -> None:
        from segment_uploader import RATE_LIMITED, classify_http_error
        self.assertEqual(
            classify_http_error(429, {"Retry-After": "999999"}),
            (RATE_LIMITED, 3600),
        )
        # A malformed header never crashes classification.
        kind, wait = classify_http_error(429, {"Retry-After": "soon"})
        self.assertEqual((kind, wait), (RATE_LIMITED, 60))

class ResolveReleaseTests(unittest.TestCase):
    """The uploader resolves, never creates: the ledger pre-opens the run
    release and every archive bucket before evaluations start, so this
    client holds no creation path at all."""

    def test_resolve_adopts_the_release_and_never_posts(self) -> None:
        from segment_uploader import ReleaseClient

        calls = []

        def request(url, method="GET", data=None, headers=None):
            calls.append(method)
            return {"id": 7}

        client = ReleaseClient("owner/repo", "tag-b3", "token")
        client._request = request
        client.resolve_release()
        self.assertEqual(calls, ["GET"])
        self.assertEqual(client.release_id, 7)
        self.assertFalse(hasattr(client, "create_release"))


if __name__ == "__main__":
    unittest.main()
