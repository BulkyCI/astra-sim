from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.ring_3d.generate_clr_schedule import (
    ClrScheduleParameters,
    clr_probabilities,
    generate_clr_schedule,
    write_clr_mask,
)


class ClrScheduleTests(unittest.TestCase):
    def test_sampling_is_reproducible_and_returns_a_static_mask(self) -> None:
        parameters = ClrScheduleParameters(
            decay_rate=0.8,
            epoch_steps=5,
            spike_stddev_steps=0.25,
            spike_amplitude=1.0,
        )
        first = generate_clr_schedule(16, 1729, parameters)
        second = generate_clr_schedule(16, 1729, parameters)

        self.assertEqual(first.is_clr.tolist(), second.is_clr.tolist())
        self.assertTrue(first.is_clr[0])
        with self.assertRaises(ValueError):
            first.is_clr[0] = False

    def test_probability_has_decay_and_epoch_boundary_spikes(self) -> None:
        probabilities = clr_probabilities(
            12,
            ClrScheduleParameters(
                decay_rate=1.0,
                epoch_steps=4,
                spike_stddev_steps=0.1,
                spike_amplitude=1.0,
            ),
        )

        self.assertEqual(probabilities[0], 1.0)
        self.assertGreater(probabilities[1], probabilities[2])
        self.assertEqual(probabilities[4], 1.0)
        self.assertEqual(probabilities[8], 1.0)
        self.assertLess(probabilities[11], 0.001)

    def test_csv_has_one_boolean_mapping_per_training_step(self) -> None:
        schedule = generate_clr_schedule(5, 42)
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "clr_mask.csv"
            write_clr_mask(path, schedule)
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual([row["step_id"] for row in rows], ["1", "2", "3", "4", "5"])
        self.assertTrue({row["is_clr"] for row in rows} <= {"0", "1"})
        self.assertTrue(all(0.0 <= float(row["probability"]) <= 1.0 for row in rows))


if __name__ == "__main__":
    unittest.main()
