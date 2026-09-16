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

# Every gate the plan step selects on. Each one is a family a dispatch can run
# alone, so each one owns a workflow_dispatch boolean and a jq selector.
GATES = {
    "always",
    "structural",
    "regime_map",
    "forgive",
    "forgive_dose",
    "forgive_v2",
    "forgive_r2",
    "forgive_ref",
}
GATE_INPUTS = {
    "always": "run_always",
    "structural": "run_structural_studies",
    "regime_map": "run_regime_map",
    "forgive": "run_forgive_studies",
    "forgive_dose": "run_forgive_dose",
    "forgive_v2": "run_forgive_v2",
    "forgive_r2": "run_forgive_r2",
    "forgive_ref": "run_forgive_ref",
}
# The closed sum the provision job validates and ci/dcs/evaluate.sh dispatches
# on. Nothing downstream of that validation branches on anything else.
KINDS = {"comparison", "single", "smoke"}
# The shedding domains that decide after a switch has trimmed a packet. Each
# adds a fourth arm to a comparison, which is what sizes the job budget.
FORGIVING_DOMAINS = {"recovery", "recovery_exempt"}
REQUIRED_KEYS = {
    "name",
    "profile",
    "run_directory",
    "artifact_name",
    "ledger_key",
    "kind",
    "comparison_seed",
    "arm_count",
    "execution_timeout_minutes",
    "simulation_timeout_seconds",
    "require_congestion",
    "gate",
    "notes",
}


def expected_arm_count(record: dict[str, object]) -> int:
    """How many ns-3 arms the job runs.

    A single or smoke record runs one. A comparison builds fixed-low,
    fixed-high, and the phase-aware policy, plus a fourth recovery arm when
    the profile names a domain that decides after the trim.
    """
    if record["kind"] != "comparison":
        return 1
    profile = json.loads(
        (REPOSITORY_ROOT / record["profile"]).read_text(encoding="utf-8")
    )
    domain = profile.get("selection_policy", {}).get("domain", "admission")
    return 4 if domain in FORGIVING_DOMAINS else 3


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

    def test_every_kind_is_one_of_the_three(self) -> None:
        for record in records():
            with self.subTest(record=record["name"]):
                self.assertIn(record["kind"], KINDS)

    def test_a_smoke_record_carries_no_seed(self) -> None:
        """A seed selects one simulation out of the seed set.

        A comparison runs one matched pair at it and a single arm runs the one
        simulation that pair's matching arm runs, which is what lets a single
        record join a comparison record. The smoke scripts take no seed, so a
        non-zero seed there is a value the job would silently drop.
        """
        for record in records():
            if record["kind"] != "smoke":
                continue
            with self.subTest(record=record["name"]):
                self.assertEqual(record["comparison_seed"], 0)

    def test_only_a_comparison_requires_congestion(self) -> None:
        """--require-congestion is a compare.py flag.

        It fails a paired evaluation that lacks raw queue, PFC, and
        background-traffic evidence; there is no such gate on a single run.
        """
        for record in records():
            if record["kind"] == "comparison":
                continue
            with self.subTest(record=record["name"]):
                self.assertFalse(record["require_congestion"])

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
        for gate in {record["gate"] for record in records()}:
            with self.subTest(gate=gate):
                self.assertIn(f"{GATE_INPUTS[gate]}:", workflow)
                self.assertIn(f'.gate == "{gate}"', workflow)

    def test_the_record_filter_narrows_the_gate_selection(self) -> None:
        """The filter is an input, not a gate.

        It is tested after the gate clause and only ever removes records, so
        a gate no dispatch enabled cannot be widened by naming a record of
        it. A gate of its own is what a family needs; this is what a subset
        of one needs.
        """
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("record_filter:", workflow)
        self.assertIn('--arg record_filter "$RECORD_FILTER"', workflow)
        self.assertIn(
            '| select($record_filter == ""\n'
            "                     or (.ledger_key | test($record_filter)))",
            workflow,
        )
        self.assertNotIn("record_filter", set(GATE_INPUTS.values()))

    def test_the_arm_count_matches_the_profile_the_record_names(self) -> None:
        """The record must say how many arms its job runs.

        The arms run sequentially inside one compare.py process, so the arm
        count is what turns a per-arm cap into a job cost. Deriving it here
        keeps a record from inheriting a budget sized for fewer arms.
        """
        for record in records():
            with self.subTest(record=record["name"]):
                self.assertEqual(record["arm_count"], expected_arm_count(record))

    def test_one_wedged_arm_dies_inside_the_job_budget(self) -> None:
        """A necessary condition, not the budget.

        The per-arm simulation cap bounds one wedged arm; it does not bound
        the job, because the caps do not sum inside the budget for any
        multi-arm record. test_a_multi_arm_record_names_walltime_as_its
        _backstop covers what actually stops the job.
        """
        for record in records():
            with self.subTest(record=record["name"]):
                self.assertLess(
                    record["simulation_timeout_seconds"],
                    record["execution_timeout_minutes"] * 60,
                )

    def test_a_multi_arm_record_names_walltime_as_its_backstop(self) -> None:
        """Where the caps do not sum, the record must say so.

        Every comparison record is in this position, and going from three
        arms to four made it 33% worse without changing a number. The note is
        what a fifth arm would have to revisit.
        """
        for record in records():
            budget_seconds = record["execution_timeout_minutes"] * 60
            cost = record["arm_count"] * record["simulation_timeout_seconds"]
            if cost <= budget_seconds:
                continue
            with self.subTest(record=record["name"]):
                self.assertIn("walltime", record["notes"])
                self.assertIn(str(record["arm_count"]), record["notes"])
