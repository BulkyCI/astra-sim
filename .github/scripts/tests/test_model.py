"""Laws and eliminators of the pure ledger model."""

from __future__ import annotations

import unittest
from collections.abc import Sequence

from ci_ledger.model import (
    COMMENT_HARD_LIMIT,
    Create,
    Delete,
    LedgerError,
    RemoteComment,
    RunContext,
    Section,
    Status,
    Update,
    digest_of,
    index,
    issue_matches_run,
    parse_key,
    parse_marker,
    parse_status,
    plan,
    render_issue_body,
    render_run_marker,
    render_section,
    split_body,
)

CONTEXT = RunContext(
    repository="BTreeMap/astra-sim",
    run_id="1234567890",
    run_number="42",
    run_attempt="2",
    sha="0123456789abcdef0123456789abcdef01234567",
    ref="refs/heads/dev",
    ref_name="dev",
    event="push",
    workflow="CI",
    actor="octocat",
)


def apply_plan(
    comments: Sequence[RemoteComment],
    actions: Sequence[object],
    next_identifier: int,
) -> tuple[tuple[RemoteComment, ...], int]:
    """Pure simulator of the `gh` interpreter, used to check idempotence."""
    surviving = list(comments)
    for action in actions:
        match action:
            case Delete(identifier=identifier):
                surviving = [c for c in surviving if c.identifier != identifier]
            case Update(identifier=identifier, body=body):
                surviving = [
                    RemoteComment(c.identifier, body)
                    if c.identifier == identifier
                    else c
                    for c in surviving
                ]
            case Create(body=body):
                surviving.append(RemoteComment(next_identifier, body))
                next_identifier += 1
    return tuple(surviving), next_identifier


class SplitBodyLaws(unittest.TestCase):
    def test_join_law_and_budget(self) -> None:
        for body in (
            "",
            "one line",
            "\n".join(f"row {number}" for number in range(500)),
            "x" * 5000,
            "short\n" + "y" * 4096 + "\ntail",
        ):
            for budget in (16, 97, 1024):
                with self.subTest(length=len(body), budget=budget):
                    pieces = split_body(body, budget)
                    self.assertEqual("".join(pieces), body)
                    self.assertTrue(all(len(piece) <= budget for piece in pieces))
                    self.assertGreaterEqual(len(pieces), 1)

    def test_prefers_line_boundaries(self) -> None:
        body = "".join(f"line {number}\n" for number in range(20))
        self.assertTrue(all(p.endswith("\n") for p in split_body(body, 40)[:-1]))

    def test_rejects_non_positive_budget(self) -> None:
        with self.assertRaises(LedgerError):
            split_body("payload", 0)


class MarkerRoundTrip(unittest.TestCase):
    def test_render_then_parse_is_identity(self) -> None:
        section = Section("native-integration", "Native", "body", Status.FAILURE)
        for part in render_section(section, CONTEXT):
            marker = parse_marker(part)
            self.assertIsNotNone(marker)
            assert marker is not None
            self.assertEqual(marker.key, "native-integration")
            self.assertEqual(marker.digest, digest_of("body"))
            self.assertIs(marker.status, Status.FAILURE)

    def test_foreign_comment_has_no_marker(self) -> None:
        self.assertIsNone(parse_marker("a human wrote this"))
        # part > parts is not a well-formed marker.
        self.assertIsNone(
            parse_marker(
                "<!-- astra-ledger key=x part=3/2 status=success digest="
                + "0" * 64
                + " -->"
            )
        )

    def test_key_domain_is_closed(self) -> None:
        self.assertEqual(parse_key(" native-integration "), "native-integration")
        for bad in ("", "has space", "emoji✨", "x" * 97, "slash/key"):
            with self.subTest(bad=bad), self.assertRaises(LedgerError):
                parse_key(bad)

    def test_run_marker_identifies_exactly_one_run(self) -> None:
        body = render_run_marker("BTreeMap/astra-sim", "1234567890")
        self.assertTrue(issue_matches_run(body, "BTreeMap/astra-sim", "1234567890"))
        self.assertFalse(issue_matches_run(body, "BTreeMap/astra-sim", "999"))
        self.assertFalse(issue_matches_run(body, "other/repo", "1234567890"))
        self.assertFalse(issue_matches_run("", "BTreeMap/astra-sim", "1"))

    def test_unknown_status_degrades_to_missing(self) -> None:
        self.assertIs(parse_status("neutral"), Status.MISSING)
        self.assertIs(parse_status(" SUCCESS "), Status.SUCCESS)

    def test_every_status_has_a_distinct_badge(self) -> None:
        self.assertEqual(len({status.badge for status in Status}), len(Status))


class RenderSection(unittest.TestCase):
    def test_every_part_fits_the_github_limit(self) -> None:
        parts = render_section(Section("huge", "Huge", "z" * 400_000), CONTEXT)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) < COMMENT_HARD_LIMIT for part in parts))

    def test_parts_reference_the_commit_and_the_run(self) -> None:
        parts = render_section(Section("k", "Title", "payload"), CONTEXT)
        self.assertEqual(len(parts), 1)
        self.assertIn(CONTEXT.commit_url, parts[0])
        self.assertIn(CONTEXT.attempt_url, parts[0])
        self.assertIn("### Title\n", parts[0])
        self.assertNotIn("part 1 of", parts[0])


class PlanAlgebra(unittest.TestCase):
    def test_empty_issue_creates_every_part_in_order(self) -> None:
        actions = plan(Section("native", "Native", "line\n" * 40_000), (), CONTEXT)
        self.assertTrue(all(isinstance(action, Create) for action in actions))
        self.assertEqual(
            [action.part for action in actions], list(range(1, len(actions) + 1))
        )

    def test_plan_is_idempotent(self) -> None:
        for body in ("small report", "line\n" * 40_000):
            with self.subTest(length=len(body)):
                section = Section("native", "Native", body)
                comments, _ = apply_plan((), plan(section, (), CONTEXT), 100)
                self.assertEqual(plan(section, comments, CONTEXT), ())

    def test_same_arity_updates_in_place(self) -> None:
        comments, _ = apply_plan(
            (), plan(Section("native", "Native", "before"), (), CONTEXT), 100
        )
        actions = plan(Section("native", "Native", "after"), comments, CONTEXT)
        self.assertTrue(all(isinstance(action, Update) for action in actions))
        self.assertEqual([action.identifier for action in actions], [100])

    def test_arity_change_replaces_wholesale(self) -> None:
        comments, next_id = apply_plan(
            (), plan(Section("native", "Native", "before"), (), CONTEXT), 100
        )
        large = Section("native", "Native", "x\n" * 60_000)
        actions = plan(large, comments, CONTEXT)
        self.assertEqual(
            sum(isinstance(action, Delete) for action in actions), len(comments)
        )
        replaced, _ = apply_plan(comments, actions, next_id)
        self.assertEqual(plan(large, replaced, CONTEXT), ())

    def test_foreign_comments_are_never_touched(self) -> None:
        human = RemoteComment(7, "a reviewer's note")
        other = Section("other", "Other", "body")
        occupied, next_id = apply_plan((human,), plan(other, (human,), CONTEXT), 100)
        section = Section("native", "Native", "body")
        after, _ = apply_plan(occupied, plan(section, occupied, CONTEXT), next_id)
        self.assertIn(human, after)
        self.assertEqual(plan(other, after, CONTEXT), ())


class DerivedIndex(unittest.TestCase):
    def _publish(self, *sections: Section) -> tuple[RemoteComment, ...]:
        comments: tuple[RemoteComment, ...] = ()
        next_id = 100
        for section in sections:
            comments, next_id = apply_plan(
                comments, plan(section, comments, CONTEXT), next_id
            )
        return comments

    def test_index_is_derived_from_the_published_comments(self) -> None:
        comments = self._publish(
            Section("b-native", "Native", "ok"),
            Section("a-paired", "Paired", "x\n" * 60_000, Status.FAILURE),
        )
        records = index(comments)
        self.assertEqual([record.key for record in records], ["a-paired", "b-native"])
        self.assertIs(records[0].status, Status.FAILURE)
        self.assertGreater(records[0].parts, 1)
        self.assertEqual(records[1].digest, digest_of("ok"))

    def test_index_ignores_comments_that_are_not_ours(self) -> None:
        comments = (RemoteComment(1, "hand-written note"),)
        self.assertEqual(index(comments), ())

    def test_republishing_does_not_duplicate_a_row(self) -> None:
        section = Section("native", "Native", "ok")
        comments = self._publish(section, section)
        self.assertEqual(len(index(comments)), 1)


class IssueBody(unittest.TestCase):
    def test_body_backreferences_commit_and_run(self) -> None:
        body = render_issue_body(CONTEXT)
        self.assertIn(CONTEXT.commit_url, body)
        self.assertIn(CONTEXT.run_url, body)
        self.assertIn(CONTEXT.tree_url, body)
        self.assertTrue(issue_matches_run(body, CONTEXT.repository, CONTEXT.run_id))

    def test_finalized_body_lists_every_section(self) -> None:
        comments, _ = apply_plan(
            (), plan(Section("native", "Native", "ok"), (), CONTEXT), 100
        )
        body = render_issue_body(CONTEXT, index(comments), finalized=True)
        self.assertIn("native", body)
        self.assertIn("✅ success", body)


if __name__ == "__main__":
    unittest.main()
