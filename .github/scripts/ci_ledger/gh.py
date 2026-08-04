"""Effect boundary: the ledger's only contact with GitHub, via the `gh` CLI.

`gh` is preinstalled on every GitHub-hosted runner and already owns
authentication (`GH_TOKEN`), host resolution, pagination (`--paginate
--slurp`), and JSON shaping (`--json`). This module carries none of that — only
the mapping from a ledger operation to an argument vector.

Every call uses the argv form and streams report bodies on stdin, so a 60 KB
report is never spliced into a command line. Every call names `--repo`
explicitly, so the ledger works from a sparse checkout with no git remote.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .model import RemoteComment

# `gh issue list` needs an explicit ceiling. The ledger only ever looks for an
# issue opened by an earlier attempt of the *current* run and the list is
# newest-first, so this bound cannot hide a relevant issue. The search API is
# deliberately unused: it is eventually consistent, and a stale miss would fork
# the record in two.
ISSUE_LIST_LIMIT = 100


class GhError(RuntimeError):
    """A `gh` invocation failed."""


@dataclass(frozen=True, slots=True)
class Gh:
    """Ledger operations expressed as `gh` invocations."""

    repository: str
    executable: str = "gh"
    runner: Callable[..., subprocess.CompletedProcess] = field(
        default=subprocess.run, repr=False
    )

    def _run(self, arguments: Sequence[str], stdin: str | None = None) -> str:
        completed = self.runner(
            [self.executable, *arguments],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise GhError(f"`gh {' '.join(arguments)}` failed: {detail[:512]}")
        return completed.stdout

    def _repo(self, *arguments: str) -> list[str]:
        return [*arguments, "--repo", self.repository]

    def ensure_label(self, name: str, color: str, description: str) -> None:
        """Make the ledger label exist before an issue references it.

        The REST API creates unknown labels implicitly when an issue is opened;
        `gh issue create` resolves them first and fails instead. `--force` makes
        this an upsert, so it is safe on every run.
        """
        self._run(
            self._repo("label", "create", name)
            + ["--color", color, "--description", description, "--force"]
        )

    def issues_with_label(self, label: str) -> tuple[Mapping[str, Any], ...]:
        payload = self._run(
            self._repo("issue", "list")
            + [
                "--label",
                label,
                "--state",
                "all",
                "--limit",
                str(ISSUE_LIST_LIMIT),
                "--json",
                "number,body",
            ]
        )
        return tuple(json.loads(payload or "[]"))

    def create_issue(self, title: str, body: str, labels: Sequence[str]) -> int:
        arguments = self._repo("issue", "create") + [
            "--title",
            title,
            "--body-file",
            "-",
        ]
        for label in labels:
            arguments += ["--label", label]
        url = self._run(arguments, stdin=body).strip().splitlines()[-1].strip()
        tail = url.rstrip("/").rsplit("/", 1)[-1]
        try:
            return int(tail)
        except ValueError as error:
            raise GhError(f"could not read an issue number from {url!r}") from error

    def update_issue(self, number: int, title: str, body: str) -> None:
        self._run(
            self._repo("issue", "edit", str(number))
            + ["--title", title, "--body-file", "-"],
            stdin=body,
        )

    def set_state(self, number: int, closed: bool) -> None:
        if closed:
            self._run(
                self._repo("issue", "close", str(number)) + ["--reason", "completed"]
            )
        else:
            self._run(self._repo("issue", "reopen", str(number)))

    # `gh` has porcelain for creating a comment but not for listing, editing, or
    # deleting one, so those three fall through to `gh api`.

    def comments(self, number: int) -> tuple[RemoteComment, ...]:
        payload = self._run(
            [
                "api",
                f"repos/{self.repository}/issues/{number}/comments?per_page=100",
                # `--slurp` wraps every page into one outer array, so the result
                # is a single well-formed document, not concatenated pages.
                "--paginate",
                "--slurp",
            ]
        )
        return tuple(
            RemoteComment(
                identifier=int(raw["id"]),
                body=str(raw.get("body") or ""),
                url=str(raw.get("html_url") or ""),
            )
            for page in json.loads(payload or "[]")
            for raw in page
        )

    def create_comment(self, number: int, body: str) -> None:
        self._run(
            self._repo("issue", "comment", str(number)) + ["--body-file", "-"],
            stdin=body,
        )

    def update_comment(self, identifier: int, body: str) -> None:
        self._run(
            [
                "api",
                "--method",
                "PATCH",
                f"repos/{self.repository}/issues/comments/{identifier}",
                "--input",
                "-",
                "--silent",
            ],
            stdin=json.dumps({"body": body}),
        )

    def delete_comment(self, identifier: int) -> None:
        self._run(
            [
                "api",
                "--method",
                "DELETE",
                f"repos/{self.repository}/issues/comments/{identifier}",
                "--silent",
            ]
        )
