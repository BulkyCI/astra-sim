#!/usr/bin/env python3
"""Generate a reproducible critical-learning-regime (CLR) mask.

The schedule follows a decaying early-training probability with narrow Gaussian
spikes at epoch boundaries:

    P(CLR | t) = min(1, exp(-lambda * t) + sum_k spike(t - k * epoch_steps))

The sampled CSV is immutable experiment input: the simulator consumes its
``step_id,is_clr`` mapping and does not draw CLR decisions at runtime.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

DEFAULT_DECAY_RATE = 1.5
DEFAULT_EPOCH_STEPS = 2
DEFAULT_SPIKE_STDDEV_STEPS = 0.5
DEFAULT_SPIKE_AMPLITUDE = 1.0


@dataclass(frozen=True)
class ClrScheduleParameters:
    """Immutable controls for the CLR probability distribution."""

    decay_rate: float = DEFAULT_DECAY_RATE
    epoch_steps: int = DEFAULT_EPOCH_STEPS
    spike_stddev_steps: float = DEFAULT_SPIKE_STDDEV_STEPS
    spike_amplitude: float = DEFAULT_SPIKE_AMPLITUDE


@dataclass(frozen=True)
class ClrSchedule:
    """A sampled, read-only per-step CLR schedule."""

    step_ids: np.ndarray
    probabilities: np.ndarray
    is_clr: np.ndarray
    seed: int
    parameters: ClrScheduleParameters | None
    model: str = "exponential_decay_with_gaussian_epoch_spikes"

    def rows(self) -> Iterable[tuple[int, bool, float]]:
        return (
            (int(step_id), bool(is_clr), float(probability))
            for step_id, probability, is_clr in zip(
                self.step_ids, self.probabilities, self.is_clr, strict=True
            )
        )

    def is_clr_by_step(self) -> dict[str, bool]:
        return {str(step_id): is_clr for step_id, is_clr, _ in self.rows()}


def _require_positive_int(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _require_nonnegative_int(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _require_positive_float(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a positive finite number")
    result = float(value)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{field} must be a positive finite number")
    return result


def validate_parameters(parameters: ClrScheduleParameters) -> ClrScheduleParameters:
    """Validate and normalize immutable schedule parameters."""
    if not isinstance(parameters, ClrScheduleParameters):
        raise ValueError("parameters must be a ClrScheduleParameters instance")
    return ClrScheduleParameters(
        decay_rate=_require_positive_float(parameters.decay_rate, "decay_rate"),
        epoch_steps=_require_positive_int(parameters.epoch_steps, "epoch_steps"),
        spike_stddev_steps=_require_positive_float(
            parameters.spike_stddev_steps, "spike_stddev_steps"
        ),
        spike_amplitude=_require_positive_float(
            parameters.spike_amplitude, "spike_amplitude"
        ),
    )


def clr_probabilities(
    total_steps: int, parameters: ClrScheduleParameters = ClrScheduleParameters()
) -> np.ndarray:
    """Return the vectorized CLR probability for every one-based training step."""
    total_steps = _require_positive_int(total_steps, "total_steps")
    parameters = validate_parameters(parameters)
    step_indices = np.arange(total_steps, dtype=np.float64)
    probability = np.exp(-parameters.decay_rate * step_indices)
    boundary_indices = np.arange(
        parameters.epoch_steps, total_steps, parameters.epoch_steps, dtype=np.float64
    )
    if boundary_indices.size:
        normalized_distance = (
            step_indices[:, np.newaxis] - boundary_indices[np.newaxis, :]
        ) / parameters.spike_stddev_steps
        probability += parameters.spike_amplitude * np.exp(
            -0.5 * np.square(normalized_distance)
        ).sum(axis=1)
    return np.minimum(1.0, probability)


def generate_clr_schedule(
    total_steps: int,
    seed: int,
    parameters: ClrScheduleParameters = ClrScheduleParameters(),
) -> ClrSchedule:
    """Sample a reproducible static CLR mask without retaining mutable state."""
    total_steps = _require_positive_int(total_steps, "total_steps")
    seed = _require_nonnegative_int(seed, "seed")
    parameters = validate_parameters(parameters)
    probabilities = clr_probabilities(total_steps, parameters)
    mask = np.random.default_rng(seed).random(total_steps) < probabilities
    step_ids = np.arange(1, total_steps + 1, dtype=np.uint64)
    for values in (step_ids, probabilities, mask):
        values.setflags(write=False)
    return ClrSchedule(step_ids, probabilities, mask, seed, parameters)


def generate_explicit_clr_schedule(
    total_steps: int,
    seed: int,
    critical_steps: Iterable[int],
) -> ClrSchedule:
    """Build an immutable one-based CLR mask from explicit phase labels.

    This preserves externally derived phase labels exactly. Unlike the default
    decay-and-spike schedule, it performs no probabilistic phase sampling.
    """
    total_steps = _require_positive_int(total_steps, "total_steps")
    seed = _require_nonnegative_int(seed, "seed")
    steps = tuple(critical_steps)
    if any(isinstance(step, bool) or not isinstance(step, int) for step in steps):
        raise ValueError("critical_steps entries must be integers")
    if any(step < 1 or step > total_steps for step in steps):
        raise ValueError(
            "critical_steps entries must be within the training-step range"
        )
    if len(set(steps)) != len(steps):
        raise ValueError("critical_steps entries must be unique")

    step_ids = np.arange(1, total_steps + 1, dtype=np.uint64)
    probabilities = np.zeros(total_steps, dtype=np.float64)
    mask = np.zeros(total_steps, dtype=np.bool_)
    for step in steps:
        probabilities[step - 1] = 1.0
        mask[step - 1] = True
    for values in (step_ids, probabilities, mask):
        values.setflags(write=False)
    return ClrSchedule(
        step_ids,
        probabilities,
        mask,
        seed,
        None,
        "explicit_critical_steps",
    )


def write_clr_mask(path: Path, schedule: ClrSchedule) -> None:
    """Write a simulator-readable static step-to-CLR mapping."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("step_id", "is_clr", "probability"))
        writer.writerows(
            (step_id, int(is_clr), f"{probability:.17g}")
            for step_id, is_clr, probability in schedule.rows()
        )


def schedule_metadata(
    schedule: ClrSchedule,
) -> dict[str, int | float | str | list[int]]:
    """Return JSON-safe provenance for a materialized schedule."""
    metadata: dict[str, int | float | str | list[int]] = {
        "model": schedule.model,
        "seed": schedule.seed,
        "steps": int(schedule.step_ids.size),
        "clr_step_count": int(np.count_nonzero(schedule.is_clr)),
    }
    if schedule.parameters is not None:
        metadata.update(
            {
                "decay_rate": schedule.parameters.decay_rate,
                "epoch_steps": schedule.parameters.epoch_steps,
                "spike_stddev_steps": schedule.parameters.spike_stddev_steps,
                "spike_amplitude": schedule.parameters.spike_amplitude,
            }
        )
    else:
        metadata["critical_steps"] = [
            int(step_id)
            for step_id, is_clr in zip(schedule.step_ids, schedule.is_clr, strict=True)
            if is_clr
        ]
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, required=True, help="training-step count")
    parser.add_argument("--seed", type=int, required=True, help="fixed sampling seed")
    parser.add_argument(
        "--output", type=Path, required=True, help="output clr_mask.csv"
    )
    parser.add_argument("--decay-rate", type=float, default=DEFAULT_DECAY_RATE)
    parser.add_argument("--epoch-steps", type=int, default=DEFAULT_EPOCH_STEPS)
    parser.add_argument(
        "--spike-stddev-steps", type=float, default=DEFAULT_SPIKE_STDDEV_STEPS
    )
    parser.add_argument(
        "--spike-amplitude", type=float, default=DEFAULT_SPIKE_AMPLITUDE
    )
    arguments = parser.parse_args()
    parameters = ClrScheduleParameters(
        decay_rate=arguments.decay_rate,
        epoch_steps=arguments.epoch_steps,
        spike_stddev_steps=arguments.spike_stddev_steps,
        spike_amplitude=arguments.spike_amplitude,
    )
    schedule = generate_clr_schedule(arguments.steps, arguments.seed, parameters)
    write_clr_mask(arguments.output, schedule)
    print(json.dumps(schedule_metadata(schedule), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
