"""Shape laws of the evaluation matrix.

The matrix is data the workflow reads without validating: a typo in a gate
value silently drops an arm from every wave, and a typo in a profile path
fails hours into a job. Both are cheap to catch here.
"""

import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MATRIX = REPOSITORY_ROOT / ".github/workflows/evaluation-matrix.json"
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/workflow_main.yml"

# Every gate the plan step selects on. "always" needs no input; the rest are
# opt-in families behind a workflow_dispatch boolean.
GATES = {"always", "structural", "regime_map", "forgive"}
GATE_INPUTS = {
    "structural": "run_structural_studies",
    "regime_map": "run_regime_map",
    "forgive": "run_forgive_studies",
}
REQUIRED_KEYS = {
    "name",
    "profile",
    "run_directory",
    "artifact_name",
    "ledger_key",
    "comparison",
    "comparison_seed",
    "execution_timeout_minutes",
    "simulation_timeout_seconds",
    "require_congestion",
    "gate",
    "notes",
}


def records() -> list[dict[str, object]]:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


class EvaluationMatrixTests(unittest.TestCase):
    def test_every_record_has_exactly_the_expected_keys(self) -> None:
        for record in records():
            with self.subTest(record=record["name"]):
                self.assertEqual(set(record), REQUIRED_KEYS)

    def test_every_gate_is_known(self) -> None:
        for record in records():
            with self.subTest(record=record["name"]):
                self.assertIn(record["gate"], GATES)

    def test_every_profile_exists(self) -> None:
        for record in records():
            with self.subTest(record=record["name"]):
                self.assertTrue((REPOSITORY_ROOT / record["profile"]).is_file())

    def test_identities_are_unique(self) -> None:
        for field in ("ledger_key", "artifact_name", "run_directory"):
            values = [record[field] for record in records()]
            with self.subTest(field=field):
                self.assertEqual(len(set(values)), len(values))

    def test_every_gated_family_has_a_dispatch_input_and_a_selector(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        used = {record["gate"] for record in records()} - {"always"}
        for gate in used:
            with self.subTest(gate=gate):
                self.assertIn(f"{GATE_INPUTS[gate]}:", workflow)
                self.assertIn(f'.gate == "{gate}"', workflow)

    def test_the_simulator_cap_fits_inside_the_job_budget(self) -> None:
        for record in records():
            with self.subTest(record=record["name"]):
                self.assertLess(
                    record["simulation_timeout_seconds"],
                    record["execution_timeout_minutes"] * 60,
                )
