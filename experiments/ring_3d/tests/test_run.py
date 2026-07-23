from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.ring_3d.run import run_experiment


class Ring3DRunnerTests(unittest.TestCase):
    def test_runner_records_and_passes_ns3_rng_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "run"
            output.mkdir()
            binary = root / "AstraSimNetwork-default"
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)
            manifest = {
                "seed": 17,
                "workload_prefix": "/tmp/workload/ring_3d",
                "system_config": "/tmp/system.json",
                "network_config": "/tmp/network.txt",
                "remote_memory_config": "/tmp/remote.json",
                "logical_topology": "/tmp/topology.json",
                "communicator_groups": "/tmp/groups.json",
                "experiment_config": "/tmp/experiment.json",
                "clr_mask": "/tmp/clr_mask.csv",
                "telemetry_dir": "/tmp/telemetry",
            }
            with (
                patch("experiments.ring_3d.run.materialize", return_value=manifest),
                patch("experiments.ring_3d.run.subprocess.run") as subprocess_run,
            ):
                returned = run_experiment(
                    REPOSITORY_ROOT / "experiments/ring_3d/profiles/smoke_8.json",
                    output,
                    binary=binary,
                    seed=17,
                    ns3_rng_seed=9,
                    ns3_rng_run=17,
                    simulation_timeout_seconds=960,
                    skip_analysis=True,
                )

            command = subprocess_run.call_args.args[0]
            self.assertIn("--ns3-rng-seed=9", command)
            self.assertIn("--ns3-rng-run=17", command)
            self.assertIn("--clr-mask-configuration=/tmp/clr_mask.csv", command)
            self.assertEqual(subprocess_run.call_args.kwargs["timeout"], 960)
            self.assertEqual(returned["execution"], {
                "dblp_selection_seed": 17,
                "ns3_rng_seed": 9,
                "ns3_rng_run": 17,
                "simulation_timeout_seconds": 960,
                "clr_mask": "/tmp/clr_mask.csv",
            })
            self.assertEqual(
                json.loads((output / "execution.json").read_text(encoding="utf-8")),
                returned["execution"],
            )


if __name__ == "__main__":
    unittest.main()
