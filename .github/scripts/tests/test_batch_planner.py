"""Laws of the batch-packing algebra."""

import io
import unittest

from batch_planner import plan_batches, read_null_records

CAP = 1000
OVERHEAD = 10


class PlanBatchesTests(unittest.TestCase):
    def test_every_batch_respects_the_cost_cap(self) -> None:
        entries = [("f{:02d}".format(i), 300) for i in range(7)]
        batches = plan_batches(entries, CAP, OVERHEAD)
        sizes = dict(entries)
        for batch in batches:
            self.assertTrue(batch)
            self.assertLessEqual(
                sum(sizes[p] + OVERHEAD for p in batch), CAP
            )

    def test_concatenation_is_the_sorted_input(self) -> None:
        entries = [("b", 300), ("a", 300), ("c", 300), ("d", 300)]
        batches = plan_batches(entries, CAP, OVERHEAD)
        flattened = [p for batch in batches for p in batch]
        self.assertEqual(flattened, ["a", "b", "c", "d"])

    def test_deterministic_regardless_of_input_order(self) -> None:
        entries = [("x/{}".format(i), 250) for i in range(9)]
        self.assertEqual(
            plan_batches(entries, CAP, OVERHEAD),
            plan_batches(list(reversed(entries)), CAP, OVERHEAD),
        )

    def test_empty_input_plans_zero_batches(self) -> None:
        self.assertEqual(plan_batches([], CAP, OVERHEAD), [])

    def test_single_file_over_budget_raises(self) -> None:
        with self.assertRaises(ValueError):
            plan_batches([("huge.bin", CAP)], CAP, OVERHEAD)

    def test_overhead_counts_toward_the_cap(self) -> None:
        # Two files of 495 fit only without overhead; with overhead 10
        # each costs 505 and they must split.
        batches = plan_batches([("a", 495), ("b", 495)], CAP, OVERHEAD)
        self.assertEqual(batches, [["a"], ["b"]])


class ReadNullRecordsTests(unittest.TestCase):
    def test_parses_size_tab_path_records(self) -> None:
        # Joined explicitly: a "\0456" literal would parse as octal "%6".
        stream = io.BytesIO(
            b"123\tns3/a.csv" + b"\x00" + b"456\tseed_1/b.txt" + b"\x00"
        )
        self.assertEqual(
            list(read_null_records(stream)),
            [("ns3/a.csv", 123), ("seed_1/b.txt", 456)],
        )

    def test_path_may_contain_tabs_after_the_first(self) -> None:
        stream = io.BytesIO(b"9\todd\tname\0")
        self.assertEqual(list(read_null_records(stream)), [("odd\tname", 9)])


if __name__ == "__main__":
    unittest.main()
