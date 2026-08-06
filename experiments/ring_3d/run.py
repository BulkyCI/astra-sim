#!/usr/bin/env python3
"""Generate and execute a 3D Ring experiment using the locked uv environment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from .generate import Profile, load_profile, materialize
    from .generate_clr_schedule import ClrScheduleParameters
except ImportError:
    from generate import Profile, load_profile, materialize
    from generate_clr_schedule import ClrScheduleParameters


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BINARY_DIRECTORY = "extern/network_backend/ns-3/build/scratch"
# ns-3 suffixes a binary with its build profile and leaves `release` bare, so
# the evaluation build produces `ns3.42-AstraSimNetwork`. The patterns are
# disjoint and searched in order of decreasing optimization, which keeps a
# stale development binary from silently standing in for the release one.
DEFAULT_BINARY_PATTERNS = (
    f"{BINARY_DIRECTORY}/*AstraSimNetwork",
    f"{BINARY_DIRECTORY}/*AstraSimNetwork-default",
    f"{BINARY_DIRECTORY}/*AstraSimNetwork-debug",
)


def find_default_binary() -> Path:
    for pattern in DEFAULT_BINARY_PATTERNS:
        matches = sorted(REPOSITORY_ROOT.glob(pattern))
        if matches:
            return matches[-1]
    raise FileNotFoundError(
        "No ns-3 AstraSimNetwork binary is available. Build it first, or pass --binary."
    )


def fixed_p_low_baseline(profile: Profile) -> tuple[float, float]:
    """Return the requested fixed-low logical-selection control values."""
    return profile.selection_policy.p_low, profile.selection_policy.p_low


def run_experiment(
    profile: Path,
    output: Path,
    *,
    binary: Path | None = None,
    clean: bool = False,
    seed: int | None = None,
    ns3_rng_seed: int = 1,
    ns3_rng_run: int | None = None,
    simulation_timeout_seconds: int | None = None,
    p_low: float | None = None,
    p_high: float | None = None,
    allow_clr_exposure: bool = False,
    clr_schedule_parameters: ClrScheduleParameters | None = None,
    skip_analysis: bool = False,
) -> dict[str, Any]:
    """Materialize, execute, and analyze one reproducible policy invocation."""
    output = output.resolve()
    if ns3_rng_seed <= 0:
        raise ValueError("ns3_rng_seed must be positive")
    if ns3_rng_run is None:
        ns3_rng_run = seed if seed is not None else 1
    if ns3_rng_run <= 0:
        raise ValueError("ns3_rng_run must be positive")
    if simulation_timeout_seconds is not None and (
        isinstance(simulation_timeout_seconds, bool)
        or not isinstance(simulation_timeout_seconds, int)
        or simulation_timeout_seconds <= 0
    ):
        raise ValueError("simulation_timeout_seconds must be positive when set")
    manifest = materialize(
        profile.resolve(),
        output,
        clean,
        seed_override=seed,
        p_low=p_low,
        p_high=p_high,
        allow_clr_exposure=allow_clr_exposure,
        clr_schedule_parameters=clr_schedule_parameters,
    )
    binary = binary.resolve() if binary else find_default_binary()
    if not binary.is_file() or not binary.stat().st_mode & 0o111:
        raise FileNotFoundError(
            f"ns-3 executable is unavailable or not executable: {binary}"
        )

    command = [
        str(binary),
        f"--workload-configuration={manifest['workload_prefix']}",
        f"--system-configuration={manifest['system_config']}",
        f"--network-configuration={manifest['network_config']}",
        f"--remote-memory-configuration={manifest['remote_memory_config']}",
        f"--logical-topology-configuration={manifest['logical_topology']}",
        f"--comm-group-configuration={manifest['communicator_groups']}",
        f"--experiment-configuration={manifest['experiment_config']}",
        f"--clr-mask-configuration={manifest['clr_mask']}",
        f"--experiment-output-dir={manifest['telemetry_dir']}",
        f"--ns3-rng-seed={ns3_rng_seed}",
        f"--ns3-rng-run={ns3_rng_run}",
    ]
    execution = {
        "dblp_selection_seed": manifest["seed"],
        "ns3_rng_seed": ns3_rng_seed,
        "ns3_rng_run": ns3_rng_run,
        "simulation_timeout_seconds": simulation_timeout_seconds,
        "clr_mask": manifest["clr_mask"],
    }
    (output / "execution.json").write_text(
        json.dumps(execution, indent=2) + "\n", encoding="utf-8"
    )
    manifest["execution"] = execution
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=True,
        timeout=simulation_timeout_seconds,
    )

    if not skip_analysis:
        analysis = REPOSITORY_ROOT / "experiments/ring_3d/analyze.py"
        subprocess.run(
            [
                sys.executable,
                str(analysis),
                "--telemetry-dir",
                manifest["telemetry_dir"],
                "--fct-file",
                str(output / "ns3" / "fct.txt"),
                "--ns3-dir",
                str(output / "ns3"),
                "--expected-rank-count",
                str(manifest["ranks"]),
                "--manifest",
                str(output / "manifest.json"),
                "--output",
                str(output / "summary.json"),
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--binary", type=Path, help="path to an ns-3 AstraSimNetwork executable"
    )
    parser.add_argument(
        "--clean", action="store_true", help="replace an existing output directory"
    )
    parser.add_argument(
        "--seed", type=int, help="override the deterministic DBLP selection seed"
    )
    parser.add_argument("--ns3-rng-seed", type=int, default=1)
    parser.add_argument("--ns3-rng-run", type=int, help="ns-3 random-stream run number")
    parser.add_argument(
        "--simulation-timeout-seconds",
        type=int,
        help="maximum wall-clock seconds for the ns-3 simulator process",
    )
    parser.add_argument(
        "--fixed-p-low-baseline",
        action="store_true",
        help="keep the policy and microbursts enabled while setting p_low and p_high to p_low",
    )
    parser.add_argument(
        "--p-low",
        type=float,
        help="override the low logical-admission selection probability (0, 0.01]",
    )
    parser.add_argument(
        "--p-high",
        type=float,
        help="override the high logical-admission selection probability",
    )
    parser.add_argument(
        "--clr-decay-rate",
        type=float,
        help="CLR probability decay over the full normalized training run",
    )
    parser.add_argument(
        "--clr-epoch-steps",
        type=int,
        help="steps between Gaussian CLR epoch-boundary spikes",
    )
    parser.add_argument(
        "--clr-spike-stddev-steps",
        type=float,
        help="Gaussian CLR epoch-boundary spike width in steps",
    )
    parser.add_argument(
        "--clr-spike-amplitude",
        type=float,
        help="Gaussian CLR epoch-boundary spike amplitude",
    )
    parser.add_argument("--skip-analysis", action="store_true")
    arguments = parser.parse_args()
    clr_schedule_parameters = ClrScheduleParameters(
        **{
            field: value
            for field, value in {
                "decay_rate": arguments.clr_decay_rate,
                "epoch_steps": arguments.clr_epoch_steps,
                "spike_stddev_steps": arguments.clr_spike_stddev_steps,
                "spike_amplitude": arguments.clr_spike_amplitude,
            }.items()
            if value is not None
        }
    )

    if arguments.fixed_p_low_baseline and arguments.p_high is not None:
        parser.error("--fixed-p-low-baseline cannot be combined with --p-high")
    if arguments.fixed_p_low_baseline:
        profile = load_profile(arguments.profile.resolve())
        p_low = (
            profile.selection_policy.p_low
            if arguments.p_low is None
            else arguments.p_low
        )
        p_high = p_low
    else:
        p_low = arguments.p_low
        p_high = arguments.p_high
    manifest = run_experiment(
        arguments.profile,
        arguments.output,
        binary=arguments.binary,
        clean=arguments.clean,
        seed=arguments.seed,
        ns3_rng_seed=arguments.ns3_rng_seed,
        ns3_rng_run=arguments.ns3_rng_run,
        simulation_timeout_seconds=arguments.simulation_timeout_seconds,
        p_low=p_low,
        p_high=p_high,
        clr_schedule_parameters=clr_schedule_parameters,
        skip_analysis=arguments.skip_analysis,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
