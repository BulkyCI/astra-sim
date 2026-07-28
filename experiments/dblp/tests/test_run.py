from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.dblp.profile import load_dblp_profile
from experiments.dblp.run import run_dblp_profile


class DblpRunnerTests(unittest.TestCase):
    def test_runner_omits_clr_mask_for_disabled_experiment(self) -> None:
        profile_path = (
            REPOSITORY_ROOT
            / "experiments/dblp/profiles/injected_loss_retry_exhaustion_8.json"
        )
        profile = load_dblp_profile(profile_path)
        manifest = {
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
        summary = {
            "failed_flow_count": 1,
            "ns3_observability": {
                "transport": {
                    "status": "available",
                    "data_injected_drop_count": 1,
                    "control_injected_drop_count": 0,
                    "data_natural_buffer_drop_count": 0,
                    "control_natural_buffer_drop_count": 0,
                }
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "run"
            output.mkdir()
            binary = root / "AstraSimNetwork-default"
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)
            with (
                patch(
                    "experiments.dblp.run.materialize_dblp_profile",
                    return_value=(profile, manifest),
                ),
                patch(
                    "experiments.dblp.run.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 1),
                ) as subprocess_run,
                patch("experiments.dblp.run.summarize", return_value=summary),
            ):
                run_dblp_profile(profile_path, output, binary=binary)

        command = subprocess_run.call_args.args[0]
        self.assertNotIn("--clr-mask-configuration=/tmp/clr_mask.csv", command)
        self.assertIn("--experiment-configuration=/tmp/experiment.json", command)


if __name__ == "__main__":
    unittest.main()
