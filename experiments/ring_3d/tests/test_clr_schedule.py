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
                decay_rate=3.0,
                epoch_steps=4,
                spike_stddev_steps=0.1,
                spike_amplitude=1.0,
            ),
        )

        self.assertEqual(probabilities[0], 1.0)
        self.assertGreater(probabilities[1], probabilities[2])
        # Epoch boundaries spike above their neighbors...
        self.assertGreater(probabilities[4], probabilities[3])
        self.assertGreater(probabilities[4], probabilities[5])
        self.assertGreater(probabilities[8], probabilities[7])
        self.assertGreater(probabilities[8], probabilities[9])
        # ...but each spike is scaled by the envelope, so later spikes fade
        # instead of saturating the tail of the schedule.
        self.assertGreater(probabilities[4], probabilities[8])
        self.assertLess(probabilities[8], 0.5)
        self.assertLess(probabilities[11], 0.06)

    def test_probability_trends_downward_at_any_step_count(self) -> None:
        for total_steps in (20, 40, 200):
            probabilities = clr_probabilities(total_steps)
            first_half = probabilities[: total_steps // 2].mean()
            second_half = probabilities[total_steps // 2 :].mean()
            self.assertGreater(
                first_half,
                second_half + 0.25,
                f"CLR schedule must trend downward at {total_steps} steps",
            )
            last_quarter = probabilities[-(total_steps // 4) :].mean()
            self.assertLess(
                last_quarter,
                0.2,
                f"converged tail must be mostly non-CLR at {total_steps} steps",
            )

    def test_probability_shape_is_invariant_to_step_count(self) -> None:
        # The same parameters must describe the same curve over normalized
        # training progress: sampling the 40-step schedule at every other
        # step reproduces the 20-step envelope away from spike centers.
        spikeless = ClrScheduleParameters(spike_amplitude=1e-12)
        coarse = clr_probabilities(20, spikeless)
        fine = clr_probabilities(39, spikeless)
        for index in range(20):
            self.assertAlmostEqual(coarse[index], fine[2 * index], places=9)

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
