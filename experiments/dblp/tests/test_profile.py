from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from experiments.dblp.profile import (
    TerminalExpectation,
    load_dblp_profile,
    materialize_dblp_profile,
)
from experiments.dblp.run import validate_execution


class DblpProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile_path = (
            REPOSITORY_ROOT
            / "experiments/dblp/profiles/injected_loss_retry_exhaustion_8.json"
        )

    def test_profile_projects_one_loss_source_and_disables_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "run"
            profile, manifest = materialize_dblp_profile(self.profile_path, output)

            self.assertEqual(
                profile.expectation.terminal_outcome,
                TerminalExpectation.TransportFailure,
            )
            self.assertEqual(manifest["selection_policy"], {"semantics": "disabled"})
            self.assertEqual(manifest["microburst"], {"enabled": False})
            self.assertEqual(
                manifest["dblp_transport"],
                {
                    "loss_source": "injected_data",
                    "completion_contract": "reliable_full_delivery",
                    "residual_loss_tolerance": "not_modeled",
                    "queue_loss_treatment": "guard_only",
                },
            )
            experiment = json.loads(
                (output / "experiment.json").read_text(encoding="utf-8")
            )
            self.assertFalse(experiment["enabled"])
            self.assertFalse(experiment["microburst"]["enabled"])
            resolved = json.loads(
                (output / "resolved_workload_profile.json").read_text(encoding="utf-8")
            )
            self.assertFalse(resolved["microburst_enabled"])
            self.assertEqual(resolved["network"]["data_loss"]["probability"], 1.0)
            self.assertEqual(
                resolved["network"]["transport_recovery"],
                {"retransmission_timeout_ns": 1000, "max_retransmission_retries": 1},
            )
            network_config = (output / "network_config.txt").read_text(encoding="utf-8")
            self.assertIn("DATA_LOSS_PROBABILITY 1", network_config)
            self.assertIn("PACKET_TRIM_MODE disabled", network_config)

    def test_profile_rejects_base_microburst_as_a_second_impairment_source(
        self,
    ) -> None:
        document = json.loads(self.profile_path.read_text(encoding="utf-8"))
        document["base_workload_profile"] = str(
            REPOSITORY_ROOT / "experiments/ring_3d/profiles/smoke_8.json"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "invalid.json"
            profile_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "disable microbursts"):
                load_dblp_profile(profile_path)

    def test_profile_rejects_an_unmodeled_residual_tolerance(self) -> None:
        document = json.loads(self.profile_path.read_text(encoding="utf-8"))
        document["residual_loss_tolerance"] = 0.4
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "invalid.json"
            profile_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DBLP profile keys"):
                load_dblp_profile(profile_path)

    def test_execution_validation_requires_only_the_configured_loss_source(
        self,
    ) -> None:
        profile = load_dblp_profile(self.profile_path)
        summary = {
            "failed_flow_count": 1,
            "ns3_observability": {
                "transport": {
                    "status": "available",
                    "data_injected_drop_count": 4,
                    "control_injected_drop_count": 0,
                    "data_natural_buffer_drop_count": 0,
                    "control_natural_buffer_drop_count": 0,
                }
            },
        }
        validate_execution(profile, 1, summary)

        with self.assertRaisesRegex(ValueError, "natural buffer loss"):
            validate_execution(
                profile,
                1,
                {
                    **summary,
                    "ns3_observability": {
                        "transport": {
                            **summary["ns3_observability"]["transport"],
                            "data_natural_buffer_drop_count": 1,
                        }
                    },
                },
            )
        with self.assertRaisesRegex(ValueError, "natural buffer loss"):
            validate_execution(
                profile,
                1,
                {
                    **summary,
                    "ns3_observability": {
                        "transport": {
                            **summary["ns3_observability"]["transport"],
                            "event_counts": {"qbb_drop": 1},
                        }
                    },
                },
            )
        with self.assertRaisesRegex(ValueError, "expected transport failure"):
            validate_execution(profile, 0, summary)
        completed = replace(
            profile,
            expectation=replace(
                profile.expectation,
                terminal_outcome=TerminalExpectation.Completed,
            ),
        )
        with self.assertRaisesRegex(ValueError, "failed transport flows"):
            validate_execution(completed, 0, summary)


if __name__ == "__main__":
    unittest.main()
