"""Laws of the archive-bucket function: pure, total, stable, in range."""

import unittest

from release_bucket import BUCKETS, bucket


class BucketTests(unittest.TestCase):
    def test_range_and_shape(self) -> None:
        for key in ("llama3-70b-64-pp2", "dblp-phase1-effnet-64dp", "x"):
            name = bucket(key)
            self.assertRegex(name, r"\Ab\d+\Z")
            self.assertLess(int(name[1:]), BUCKETS)

    def test_pinned_assignments(self) -> None:
        """Golden values: published releases are permanent, so a silent
        change to the hash or modulus would strand every future re-run's
        uploads away from its original bucket. Changing BUCKETS is
        allowed and moves future runs only; update these pins with it."""
        self.assertEqual(BUCKETS, 5)
        self.assertEqual(bucket("llama3-70b-16-seed-31415926"), "b1")
        self.assertEqual(bucket("llama3-70b-32-direct"), "b4")
        self.assertEqual(bucket("llama3-70b-64-fanin-direct"), "b1")

    def test_determinism(self) -> None:
        self.assertEqual(
            bucket("llama3-70b-64-sr2x"), bucket("llama3-70b-64-sr2x")
        )


if __name__ == "__main__":
    unittest.main()
