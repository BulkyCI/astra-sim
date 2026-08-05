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

from experiments.ring_3d.run import find_default_binary, run_experiment


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
                "ranks": 8,
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
                )

            command = subprocess_run.call_args_list[0].args[0]
            self.assertIn("--ns3-rng-seed=9", command)
            self.assertIn("--ns3-rng-run=17", command)
            self.assertIn("--clr-mask-configuration=/tmp/clr_mask.csv", command)
            analyzer_command = subprocess_run.call_args_list[1].args[0]
            self.assertIn("--expected-rank-count", analyzer_command)
            self.assertIn("8", analyzer_command)
            self.assertEqual(subprocess_run.call_args_list[0].kwargs["timeout"], 960)
            self.assertEqual(
                returned["execution"],
                {
                    "dblp_selection_seed": 17,
                    "ns3_rng_seed": 9,
                    "ns3_rng_run": 17,
                    "simulation_timeout_seconds": 960,
                    "clr_mask": "/tmp/clr_mask.csv",
                },
            )
            self.assertEqual(
                json.loads((output / "execution.json").read_text(encoding="utf-8")),
                returned["execution"],
            )


class Ring3DBinaryDiscoveryTests(unittest.TestCase):
    def scratch_directory(self, root: Path) -> Path:
        scratch = root / "extern/network_backend/ns-3/build/scratch"
        scratch.mkdir(parents=True)
        return scratch

    def test_release_binary_wins_over_a_stale_development_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scratch = self.scratch_directory(root)
            (scratch / "ns3.42-AstraSimNetwork-default").touch()
            (scratch / "ns3.42-AstraSimNetwork-debug").touch()
            (scratch / "ns3.42-AstraSimNetwork").touch()

            with patch("experiments.ring_3d.run.REPOSITORY_ROOT", root):
                self.assertEqual(
                    find_default_binary().name, "ns3.42-AstraSimNetwork"
                )

    def test_development_binary_is_still_discoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scratch = self.scratch_directory(root)
            (scratch / "ns3.42-AstraSimNetwork-debug").touch()

            with patch("experiments.ring_3d.run.REPOSITORY_ROOT", root):
                self.assertEqual(
                    find_default_binary().name, "ns3.42-AstraSimNetwork-debug"
                )

    def test_missing_binary_is_an_explicit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.scratch_directory(root)

            with patch("experiments.ring_3d.run.REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(FileNotFoundError, "Build it first"):
                    find_default_binary()


if __name__ == "__main__":
    unittest.main()
