"""The argument vectors the ledger hands to the `gh` CLI.

`gh` owns authentication, host resolution, and pagination, so the only thing
left to get wrong here is the command line itself. These tests pin it, and pin
that report bodies travel on stdin rather than in argv.
"""

from __future__ import annotations

import json
import subprocess
import unittest

from ci_ledger.gh import Gh, GhError

REPOSITORY = "BTreeMap/astra-sim"


class RecordingRunner:
    """Replays a canned `gh` result and records every invocation."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.result = (returncode, stdout, stderr)
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, command, input=None, **_):  # `input` mirrors subprocess.run
        self.calls.append((list(command), input))
        return subprocess.CompletedProcess(command, *self.result)


def _gh(runner: RecordingRunner) -> Gh:
    return Gh(repository=REPOSITORY, runner=runner)


class IssueCommands(unittest.TestCase):
    def test_create_streams_the_body_and_returns_the_number(self) -> None:
        runner = RecordingRunner(stdout=f"https://github.com/{REPOSITORY}/issues/17\n")
        number = _gh(runner).create_issue("Title", "# Body", ["ledger"])
        command, stdin = runner.calls[0]
        self.assertEqual(number, 17)
        self.assertEqual(command[:3], ["gh", "issue", "create"])
        self.assertEqual(command[command.index("--body-file") + 1], "-")
        self.assertEqual(stdin, "# Body")
        # A 60 KB report must never appear as an argument.
        self.assertNotIn("# Body", command)

    def test_every_call_names_the_repository(self) -> None:
        runner = RecordingRunner(stdout="[]")
        gh = _gh(runner)
        gh.issues_with_label("experiment-ledger")
        gh.set_state(9, closed=True)
        for command, _ in runner.calls:
            self.assertEqual(command[command.index("--repo") + 1], REPOSITORY)

    def test_list_uses_structured_output_not_search(self) -> None:
        runner = RecordingRunner(stdout='[{"number": 3, "body": "x"}]')
        issues = _gh(runner).issues_with_label("experiment-ledger")
        command, _ = runner.calls[0]
        self.assertEqual(issues, ({"number": 3, "body": "x"},))
        self.assertIn("--json", command)
        self.assertNotIn("search", command)

    def test_state_transitions_use_porcelain(self) -> None:
        runner = RecordingRunner()
        gh = _gh(runner)
        gh.set_state(9, closed=True)
        gh.set_state(9, closed=False)
        self.assertEqual(runner.calls[0][0][:4], ["gh", "issue", "close", "9"])
        self.assertEqual(runner.calls[1][0][:4], ["gh", "issue", "reopen", "9"])

    def test_label_upsert_is_forced(self) -> None:
        runner = RecordingRunner()
        _gh(runner).ensure_label("experiment-ledger", "0e8a16", "record")
        command, _ = runner.calls[0]
        self.assertEqual(command[:4], ["gh", "label", "create", "experiment-ledger"])
        self.assertIn("--force", command)


class CommentCommands(unittest.TestCase):
    def test_listing_slurps_every_page_into_one_document(self) -> None:
        pages = json.dumps(
            [[{"id": 1, "body": "a", "html_url": "u1"}], [{"id": 2, "body": "b"}]]
        )
        runner = RecordingRunner(stdout=pages)
        comments = _gh(runner).comments(5)
        command, _ = runner.calls[0]
        self.assertEqual([c.identifier for c in comments], [1, 2])
        self.assertEqual([c.body for c in comments], ["a", "b"])
        self.assertIn("--paginate", command)
        self.assertIn("--slurp", command)

    def test_update_sends_a_json_body_on_stdin(self) -> None:
        runner = RecordingRunner()
        _gh(runner).update_comment(42, "new body")
        command, stdin = runner.calls[0]
        self.assertEqual(command[:4], ["gh", "api", "--method", "PATCH"])
        self.assertIn(f"repos/{REPOSITORY}/issues/comments/42", command)
        self.assertEqual(json.loads(stdin or ""), {"body": "new body"})

    def test_delete_targets_the_comment_endpoint(self) -> None:
        runner = RecordingRunner()
        _gh(runner).delete_comment(42)
        command, _ = runner.calls[0]
        self.assertEqual(command[:4], ["gh", "api", "--method", "DELETE"])
        self.assertIn(f"repos/{REPOSITORY}/issues/comments/42", command)


class FailureHandling(unittest.TestCase):
    def test_a_failing_invocation_surfaces(self) -> None:
        runner = RecordingRunner(returncode=1, stderr="HTTP 404: Not Found")
        with self.assertRaises(GhError):
            _gh(runner).delete_comment(1)
        self.assertEqual(len(runner.calls), 1)

    def test_unparsable_create_output_is_rejected(self) -> None:
        runner = RecordingRunner(stdout="something went sideways\n")
        with self.assertRaises(GhError):
            _gh(runner).create_issue("t", "b", [])


if __name__ == "__main__":
    unittest.main()
