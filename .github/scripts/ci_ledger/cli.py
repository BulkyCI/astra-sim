"""Command-line interpreter for the CI experiment ledger.

Three commands form one lifecycle:

``open``     create-or-adopt the issue that records this workflow run
``publish``  reconcile one section (a job's report) into that issue
``close``    rewrite the derived index and set the issue state

The decisions live in :mod:`ci_ledger.model`; this module only performs them.
Each command is idempotent, which is what lets a re-run, a retried step, or a
partially failed run converge on the same ledger.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .gh import Gh, GhError
from .model import (
    Create,
    Delete,
    LedgerError,
    RunContext,
    Section,
    Status,
    Update,
    index,
    issue_matches_run,
    parse_key,
    parse_status,
    plan,
    render_issue_body,
)

LEDGER_LABEL = "experiment-ledger"
LEDGER_LABEL_COLOR = "0e8a16"
LEDGER_LABEL_DESCRIPTION = (
    "Permanent record of one CI experiment run, published by Actions"
)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def run_context_from_environment() -> RunContext:
    """Parse the Actions environment into the trusted provenance record."""
    repository, run_id = _env("GITHUB_REPOSITORY"), _env("GITHUB_RUN_ID")
    if not repository or not run_id:
        raise LedgerError(
            "GITHUB_REPOSITORY and GITHUB_RUN_ID are required; this command "
            "runs inside GitHub Actions"
        )
    return RunContext(
        repository=repository,
        run_id=run_id,
        run_number=_env("GITHUB_RUN_NUMBER", "0"),
        run_attempt=_env("GITHUB_RUN_ATTEMPT", "1"),
        sha=_env("GITHUB_SHA"),
        ref=_env("GITHUB_REF"),
        ref_name=_env("GITHUB_REF_NAME"),
        event=_env("GITHUB_EVENT_NAME"),
        workflow=_env("GITHUB_WORKFLOW"),
        actor=_env("GITHUB_ACTOR"),
        server_url=_env("GITHUB_SERVER_URL", "https://github.com"),
    )


def _gh() -> Gh:
    """Build the `gh` facade. Authentication is `gh`'s concern, not ours."""
    if not (_env("GH_TOKEN") or _env("GITHUB_TOKEN")):
        raise LedgerError(
            "GH_TOKEN (or GITHUB_TOKEN) is required; `gh` reads it directly"
        )
    return Gh(repository=_env("GITHUB_REPOSITORY"))


def _emit(name: str, value: str) -> None:
    destination = os.environ.get("GITHUB_OUTPUT")
    if destination:
        with open(destination, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def _summarize(markdown: str) -> None:
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with open(destination, "a", encoding="utf-8") as handle:
            handle.write(markdown.rstrip() + "\n")
    print(markdown)


def command_open(arguments: argparse.Namespace) -> int:
    """Create the run's ledger issue, or adopt the one that already exists."""
    context = run_context_from_environment()
    gh = _gh()
    body = render_issue_body(context)

    # Adoption is what makes `open` idempotent: re-running the workflow reuses
    # the issue this run already owns instead of forking the record in two.
    adopted = next(
        (
            issue
            for issue in gh.issues_with_label(arguments.label)
            if issue_matches_run(
                str(issue.get("body") or ""), context.repository, context.run_id
            )
        ),
        None,
    )
    if adopted is None:
        gh.ensure_label(arguments.label, LEDGER_LABEL_COLOR, LEDGER_LABEL_DESCRIPTION)
        number = gh.create_issue(context.title, body, [arguments.label])
        action = "created"
    else:
        number = int(adopted["number"])
        gh.update_issue(number, context.title, body)
        action = "adopted"

    # The permanent archive is opened here and nowhere else, so its tag is
    # evaluated exactly once per run and travels downstream as an opaque value.
    tag = context.release_tag
    if gh.release_exists(tag):
        release_action = "adopted"
    else:
        gh.create_release(
            tag, context.sha, context.title, _release_notes(context, number)
        )
        release_action = "created"

    _emit("issue", str(number))
    _emit("release_tag", tag)
    _summarize(
        f"Experiment ledger {action}: [#{number}]({context.issue_url(number)}) · "
        f"archive {release_action}: [`{tag}`]({context.release_url(tag)})"
    )
    return 0


def _release_notes(context: RunContext, issue: int) -> str:
    """Release body: the same backreferences the ledger issue carries."""
    return "\n".join(
        (
            f"Permanent archive for {context.title}.",
            "",
            f"- Commit: [`{context.sha}`]({context.commit_url})",
            (
                f"- Workflow run: [#{context.run_number}]({context.run_url}) "
                f"(attempt {context.run_attempt})"
            ),
            f"- Ledger: [#{issue}]({context.issue_url(issue)})",
            "",
            (
                "Assets are the reproducibility bundles the run also uploaded "
                "as Actions artifacts. Those expire; these do not."
            ),
        )
    )


def _read_report(path: Path, title: str, declared: Status) -> tuple[str, Status]:
    """Read a report, recording an absence rather than claiming success."""
    try:
        return path.read_text(encoding="utf-8"), declared
    except OSError as error:
        note = (
            f"> The job did not produce `{path}` for **{title}**.\n>\n"
            f"> `{type(error).__name__}: {error}`\n"
        )
        return note, Status.MISSING


def command_publish(arguments: argparse.Namespace) -> int:
    """Reconcile one section into the ledger issue."""
    context = run_context_from_environment()
    key = parse_key(arguments.key)
    body, status = _read_report(
        arguments.body_file, arguments.title, parse_status(arguments.status)
    )
    section = Section(key=key, title=arguments.title, body=body, status=status)

    if arguments.issue <= 0:
        _summarize(f"Ledger disabled; `{key}` not published ({status.value}).")
        return 0

    gh = _gh()
    created = updated = deleted = 0
    for action in plan(section, gh.comments(arguments.issue), context):
        match action:
            case Delete(identifier=identifier):
                gh.delete_comment(identifier)
                deleted += 1
            case Update(identifier=identifier, body=rendered):
                gh.update_comment(identifier, rendered)
                updated += 1
            case Create(body=rendered):
                gh.create_comment(arguments.issue, rendered)
                created += 1
    _summarize(
        f"Ledger section `{key}` → issue #{arguments.issue} "
        f"({created} created, {updated} updated, {deleted} removed; "
        f"digest `{section.digest[:16]}`)."
    )
    return 0


def command_close(arguments: argparse.Namespace) -> int:
    """Rewrite the index from the published comments and set the issue state."""
    context = run_context_from_environment()
    if arguments.issue <= 0:
        _summarize("Ledger disabled; nothing to finalize.")
        return 0

    gh = _gh()
    records = index(gh.comments(arguments.issue))
    gh.update_issue(
        arguments.issue,
        context.title,
        render_issue_body(context, records, finalized=True),
    )
    # A fully successful run needs no attention, so its record is closed;
    # anything else stays in the open-issue queue.
    unresolved = arguments.keep_open or any(
        record.status is not Status.SUCCESS for record in records
    )
    gh.set_state(arguments.issue, closed=not unresolved)
    _summarize(
        f"Ledger #{arguments.issue} finalized with {len(records)} section(s); "
        f"issue {'left open' if unresolved else 'closed'}."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ledger", description="Persist CI experiment results in issues."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    opener = subcommands.add_parser("open", help="create or adopt the run issue")
    opener.add_argument("--label", default=LEDGER_LABEL)
    opener.set_defaults(handler=command_open)

    publisher = subcommands.add_parser("publish", help="publish one section")
    publisher.add_argument("--issue", type=int, required=True)
    publisher.add_argument("--key", required=True)
    publisher.add_argument("--title", required=True)
    publisher.add_argument("--body-file", type=Path, required=True)
    publisher.add_argument("--status", default=Status.SUCCESS.value)
    publisher.set_defaults(handler=command_publish)

    closer = subcommands.add_parser("close", help="finalize the ledger")
    closer.add_argument("--issue", type=int, required=True)
    closer.add_argument("--keep-open", action="store_true")
    closer.set_defaults(handler=command_close)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except (LedgerError, GhError) as error:
        print(f"ledger: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
