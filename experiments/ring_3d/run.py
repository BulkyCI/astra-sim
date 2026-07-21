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
    from .generate import DEFAULT_DROP_PROBABILITY_BY_STEP, materialize
except ImportError:
    from generate import DEFAULT_DROP_PROBABILITY_BY_STEP, materialize


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BINARY_PATTERN = "extern/network_backend/ns-3/build/scratch/*AstraSimNetwork-default"


def find_default_binary() -> Path:
    matches = sorted(REPOSITORY_ROOT.glob(DEFAULT_BINARY_PATTERN))
    if not matches:
        raise FileNotFoundError(
            "No ns-3 AstraSimNetwork binary is available. Build it first, or pass --binary."
        )
    return matches[-1]


def lossless_drop_probabilities() -> dict[str, float]:
    """Return the enabled-policy baseline with zero logical suppression."""
    return {step: 0.0 for step in DEFAULT_DROP_PROBABILITY_BY_STEP}


def run_experiment(
    profile: Path,
    output: Path,
    *,
    binary: Path | None = None,
    clean: bool = False,
    seed: int | None = None,
    ns3_rng_seed: int = 1,
    ns3_rng_run: int | None = None,
    drop_probabilities: dict[str, float] | None = None,
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
    manifest = materialize(
        profile.resolve(),
        output,
        clean,
        seed_override=seed,
        drop_probabilities=drop_probabilities,
    )
    binary = binary.resolve() if binary else find_default_binary()
    if not binary.is_file() or not binary.stat().st_mode & 0o111:
        raise FileNotFoundError(f"ns-3 executable is unavailable or not executable: {binary}")

    command = [
        str(binary),
        f"--workload-configuration={manifest['workload_prefix']}",
        f"--system-configuration={manifest['system_config']}",
        f"--network-configuration={manifest['network_config']}",
        f"--remote-memory-configuration={manifest['remote_memory_config']}",
        f"--logical-topology-configuration={manifest['logical_topology']}",
        f"--comm-group-configuration={manifest['communicator_groups']}",
        f"--experiment-configuration={manifest['experiment_config']}",
        f"--experiment-output-dir={manifest['telemetry_dir']}",
        f"--ns3-rng-seed={ns3_rng_seed}",
        f"--ns3-rng-run={ns3_rng_run}",
    ]
    execution = {
        "dblp_selection_seed": manifest["seed"],
        "ns3_rng_seed": ns3_rng_seed,
        "ns3_rng_run": ns3_rng_run,
    }
    (output / "execution.json").write_text(
        json.dumps(execution, indent=2) + "\n", encoding="utf-8"
    )
    manifest["execution"] = execution
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)

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
    parser.add_argument("--binary", type=Path, help="path to an ns-3 AstraSimNetwork executable")
    parser.add_argument("--clean", action="store_true", help="replace an existing output directory")
    parser.add_argument("--seed", type=int, help="override the deterministic DBLP selection seed")
    parser.add_argument("--ns3-rng-seed", type=int, default=1)
    parser.add_argument("--ns3-rng-run", type=int, help="ns-3 random-stream run number")
    parser.add_argument(
        "--lossless-baseline",
        action="store_true",
        help="keep the policy and microbursts enabled while setting every suppression threshold to zero",
    )
    parser.add_argument("--skip-analysis", action="store_true")
    arguments = parser.parse_args()

    manifest = run_experiment(
        arguments.profile,
        arguments.output,
        binary=arguments.binary,
        clean=arguments.clean,
        seed=arguments.seed,
        ns3_rng_seed=arguments.ns3_rng_seed,
        ns3_rng_run=arguments.ns3_rng_run,
        drop_probabilities=(lossless_drop_probabilities() if arguments.lossless_baseline else None),
        skip_analysis=arguments.skip_analysis,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())