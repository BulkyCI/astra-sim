#!/usr/bin/env python3
"""Generate and execute a 3D Ring experiment using the locked uv environment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from .generate import materialize
except ImportError:
    from generate import materialize


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BINARY_PATTERN = "extern/network_backend/ns-3/build/scratch/*AstraSimNetwork-default"


def find_default_binary() -> Path:
    matches = sorted(REPOSITORY_ROOT.glob(DEFAULT_BINARY_PATTERN))
    if not matches:
        raise FileNotFoundError(
            "No ns-3 AstraSimNetwork binary is available. Build it first, or pass --binary."
        )
    return matches[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path, help="path to an ns-3 AstraSimNetwork executable")
    parser.add_argument("--clean", action="store_true", help="replace an existing output directory")
    parser.add_argument("--skip-analysis", action="store_true")
    arguments = parser.parse_args()

    manifest = materialize(arguments.profile.resolve(), arguments.output.resolve(), arguments.clean)
    binary = (arguments.binary.resolve() if arguments.binary else find_default_binary())
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
    ]
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)

    if not arguments.skip_analysis:
        analysis = REPOSITORY_ROOT / "experiments/ring_3d/analyze.py"
        subprocess.run(
            [
                sys.executable,
                str(analysis),
                "--telemetry-dir",
                manifest["telemetry_dir"],
                "--output",
                str(arguments.output.resolve() / "summary.json"),
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())