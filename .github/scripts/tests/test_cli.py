"""End-to-end lifecycle of the ledger interpreter against an in-memory GitHub.

The `gh` facade is the only effect in :mod:`ci_ledger.cli`, so replacing it with
a deterministic double exercises the whole open/publish/close pipeline without a
token. :mod:`tests.test_gh` separately pins the argument vectors that facade
hands to `gh`.
"""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

from ci_ledger import cli
from ci_ledger.model import RemoteComment, issue_matches_run

ENVIRONMENT = {
    "GITHUB_REPOSITORY": "BTreeMap/astra-sim",
    "GITHUB_RUN_ID": "1234567890",
    "GITHUB_RUN_NUMBER": "42",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_SHA": "0123456789abcdef0123456789abcdef01234567",
    "GITHUB_REF": "refs/heads/dev",
    "GITHUB_REF_NAME": "dev",
    "GITHUB_EVENT_NAME": "push",
    "GITHUB_WORKFLOW": "CI",
    "GITHUB_ACTOR": "octocat",
    "GH_TOKEN": "not-a-real-token",
}


class FakeGh:
    """Stand-in with exactly the `ci_ledger.gh.Gh` surface the CLI uses."""

    def __init__(self) -> None:
        self.issues: dict[int, dict[str, object]] = {}
        self.threads: dict[int, list[RemoteComment]] = {}
        self.labels: dict[str, tuple[str, str]] = {}
        self._next_issue = 1
        self._next_comment = 1000

    def ensure_label(self, name: str, color: str, description: str) -> None:
        self.labels[name] = (color, description)

    def issues_with_label(self, label: str) -> tuple[Mapping[str, object], ...]:
        return tuple(i for i in self.issues.values() if label in i["labels"])

    def create_issue(self, title: str, body: str, labels) -> int:
        number = self._next_issue
        self._next_issue += 1
        self.issues[number] = {
            "number": number,
            "title": title,
            "body": body,
            "labels": list(labels),
            "state": "open",
        }
        self.threads[number] = []
        return number

    def update_issue(self, number: int, title: str, body: str) -> None:
        self.issues[number].update({"title": title, "body": body})

    def set_state(self, number: int, closed: bool) -> None:
        self.issues[number]["state"] = "closed" if closed else "open"

    def comments(self, number: int) -> tuple[RemoteComment, ...]:
        return tuple(self.threads[number])

    def create_comment(self, number: int, body: str) -> None:
        self.threads[number].append(RemoteComment(self._next_comment, body))
        self._next_comment += 1

    def update_comment(self, identifier: int, body: str) -> None:
        for number, bucket in self.threads.items():
            self.threads[number] = [
                RemoteComment(c.identifier, body) if c.identifier == identifier else c
                for c in bucket
            ]

    def delete_comment(self, identifier: int) -> None:
        for number, bucket in self.threads.items():
            self.threads[number] = [c for c in bucket if c.identifier != identifier]


class LedgerLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.gh = FakeGh()
        self.workspace = Path(tempfile.mkdtemp())
        for entry in (
            patch.dict("os.environ", ENVIRONMENT, clear=False),
            patch.object(cli, "_gh", lambda: self.gh),
        ):
            entry.start()
            self.addCleanup(entry.stop)

    def _report(self, name: str, text: str) -> Path:
        path = self.workspace / name
        path.write_text(text, encoding="utf-8")
        return path

    def _publish(self, key: str, path: Path, status: str = "success") -> int:
        return cli.main(
            [
                "publish",
                "--issue",
                "1",
                "--key",
                key,
                "--title",
                key.title(),
                "--body-file",
                str(path),
                "--status",
                status,
            ]
        )

    def test_open_publish_close_converges(self) -> None:
        self.assertEqual(cli.main(["open"]), 0)
        self.assertEqual(len(self.gh.issues), 1)
        # `gh issue create` rejects an unknown label, so it is upserted first.
        self.assertIn("experiment-ledger", self.gh.labels)
        self.assertTrue(
            issue_matches_run(
                str(self.gh.issues[1]["body"]), "BTreeMap/astra-sim", "1234567890"
            )
        )

        report = self._report("native.md", "# Native\n\nAll green.\n")
        self.assertEqual(self._publish("native-integration", report), 0)
        self.assertEqual(len(self.gh.threads[1]), 1)

        # Re-publishing the identical report is a no-op on the remote state.
        before = list(self.gh.threads[1])
        self._publish("native-integration", report)
        self.assertEqual(self.gh.threads[1], before)

        self.assertEqual(cli.main(["close", "--issue", "1"]), 0)
        self.assertEqual(self.gh.issues[1]["state"], "closed")
        self.assertIn("native-integration", str(self.gh.issues[1]["body"]))

    def test_open_is_idempotent_across_reruns(self) -> None:
        cli.main(["open"])
        cli.main(["open"])
        self.assertEqual(len(self.gh.issues), 1)

    def test_missing_report_records_an_explicit_absence(self) -> None:
        cli.main(["open"])
        self.assertEqual(self._publish("gone", self.workspace / "absent.md"), 0)
        self.assertIn("did not produce", self.gh.threads[1][0].body)
        # An unrecorded report keeps the run's record open for attention.
        cli.main(["close", "--issue", "1"])
        self.assertEqual(self.gh.issues[1]["state"], "open")

    def test_failed_section_keeps_the_record_open(self) -> None:
        cli.main(["open"])
        self._publish("native", self._report("n.md", "boom"), status="failure")
        cli.main(["close", "--issue", "1"])
        self.assertEqual(self.gh.issues[1]["state"], "open")
        self.assertIn("❌ failure", str(self.gh.issues[1]["body"]))

    def test_keep_open_overrides_a_clean_run(self) -> None:
        cli.main(["open"])
        self._publish("native", self._report("n.md", "ok"))
        cli.main(["close", "--issue", "1", "--keep-open"])
        self.assertEqual(self.gh.issues[1]["state"], "open")

    def test_disabled_ledger_touches_nothing(self) -> None:
        report = self._report("native.md", "body")
        self.assertEqual(
            cli.main(
                [
                    "publish",
                    "--issue",
                    "0",
                    "--key",
                    "native",
                    "--title",
                    "Native",
                    "--body-file",
                    str(report),
                ]
            ),
            0,
        )
        self.assertEqual(self.gh.issues, {})
        self.assertEqual(cli.main(["close", "--issue", "0"]), 0)


if __name__ == "__main__":
    unittest.main()
