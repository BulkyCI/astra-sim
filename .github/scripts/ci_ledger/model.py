"""Pure model for the persistent CI experiment ledger.

Every function here is total and effect-free. The GitHub credentials, the
process boundary, and the filesystem live in :mod:`ci_ledger.gh` and
:mod:`ci_ledger.cli`, so the reconciliation algebra below is testable without a
token.

Two operations carry the design:

:func:`plan`   the mutations that make one section equal its desired rendering.
               Idempotent by construction — applying a plan and re-planning
               yields the empty plan, so a re-run converges instead of
               appending duplicates.
:func:`index`  the issue's section table, derived from the comments that are
               actually published. Deriving rather than tracking is what keeps
               the index and the record in sync: there is no second copy of the
               truth to drift from.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import Enum

# 20 bytes render as exactly 32 base32 characters with no `=` padding, drawn
# from `a-z2-7` once lowercased — every one of them legal in a git ref.
RELEASE_TAG_BYTES = 20
# blake2b caps `person` at 16 bytes; this is 13.
RELEASE_TAG_PERSON = b"astra-sim-run"

# GitHub rejects an issue-comment body longer than 65_536 characters ("Body is
# too long"). The budget reserves headroom for the marker, heading, and
# backreference that every rendered part carries beside the payload.
COMMENT_HARD_LIMIT = 65_536
COMMENT_BODY_BUDGET = 60_000

# There is no API for issue file attachments; only the web uploader accepts
# them. Binary reproducibility bundles therefore stay in Actions artifacts.
ATTACHMENT_NOTE = (
    "GitHub has no API for issue file attachments, so this issue holds the "
    "permanent textual record — each comment capped at 65,536 characters and "
    "paginated — while the binary reproducibility bundles are published as "
    "assets on the release linked above, which does not expire the way an "
    "Actions artifact does."
)

_KEY_PATTERN = re.compile(r"\A[A-Za-z0-9._:\-]{1,96}\Z")

_MARKER_PATTERN = re.compile(
    r"<!--\s*astra-ledger\s+"
    r"key=(?P<key>[A-Za-z0-9._:\-]+)\s+"
    r"part=(?P<part>\d+)/(?P<parts>\d+)\s+"
    r"status=(?P<status>[a-z]+)\s+"
    r"digest=(?P<digest>[0-9a-f]{64})\s*-->"
)

_RUN_MARKER_PATTERN = re.compile(
    r"<!--\s*astra-ledger-run\s+repository=(?P<repository>\S+)\s+"
    r"run_id=(?P<run_id>\d+)\s*-->"
)


class LedgerError(ValueError):
    """An untrusted value cannot enter the ledger domain."""


def digest_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_key(raw: str) -> str:
    """Admit a section key into the trusted domain, or reject it.

    A key is embedded in an HTML marker and parsed back out of a comment body,
    so its character set is closed rather than merely trusted.
    """
    candidate = raw.strip()
    if _KEY_PATTERN.fullmatch(candidate) is None:
        raise LedgerError(
            f"invalid ledger key {raw!r}: expected 1-96 characters from [A-Za-z0-9._:-]"
        )
    return candidate


class Status(str, Enum):
    """Closed set of section outcomes; every eliminator matches all of them."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    MISSING = "missing"

    @property
    def badge(self) -> str:
        match self:
            case Status.SUCCESS:
                return "✅ success"
            case Status.FAILURE:
                return "❌ failure"
            case Status.CANCELLED:
                return "⚠️ cancelled"
            case Status.SKIPPED:
                return "⏭️ skipped"
            case Status.MISSING:
                return "🚫 missing"


def parse_status(raw: str) -> Status:
    """Map an Actions job result onto the closed status domain."""
    try:
        return Status(raw.strip().lower())
    except ValueError:
        return Status.MISSING


@dataclass(frozen=True, slots=True)
class Marker:
    """Self-describing identity carried by every ledger comment.

    The index is rebuilt from these, so a comment must state everything the
    index needs: which section, which part, how it ended, and what it holds.
    """

    key: str
    part: int
    parts: int
    status: Status
    digest: str

    def render(self) -> str:
        return (
            f"<!-- astra-ledger key={self.key} part={self.part}/{self.parts} "
            f"status={self.status.value} digest={self.digest} -->"
        )


def parse_marker(body: str) -> Marker | None:
    """Recover a marker from a comment body; ``None`` means "not ours"."""
    found = _MARKER_PATTERN.search(body)
    if found is None:
        return None
    part, parts = int(found["part"]), int(found["parts"])
    if not 1 <= part <= parts:
        return None
    return Marker(
        key=found["key"],
        part=part,
        parts=parts,
        status=parse_status(found["status"]),
        digest=found["digest"],
    )


def render_run_marker(repository: str, run_id: str) -> str:
    return f"<!-- astra-ledger-run repository={repository} run_id={run_id} -->"


def issue_matches_run(body: str, repository: str, run_id: str) -> bool:
    """True when an existing issue body already claims this workflow run."""
    found = _RUN_MARKER_PATTERN.search(body or "")
    return (
        found is not None
        and found["repository"] == repository
        and found["run_id"] == run_id
    )


@dataclass(frozen=True, slots=True)
class RunContext:
    """Immutable provenance of one workflow run.

    Every ledger artifact renders from this value, which is why the issue and
    its comments cannot disagree about which commit and which run they describe.
    """

    repository: str
    run_id: str
    run_number: str
    run_attempt: str
    sha: str
    ref: str
    ref_name: str
    event: str
    workflow: str
    actor: str
    server_url: str = "https://github.com"

    @property
    def short_sha(self) -> str:
        return self.sha[:12]

    @property
    def run_url(self) -> str:
        return f"{self.server_url}/{self.repository}/actions/runs/{self.run_id}"

    @property
    def attempt_url(self) -> str:
        return f"{self.run_url}/attempts/{self.run_attempt}"

    @property
    def commit_url(self) -> str:
        return f"{self.server_url}/{self.repository}/commit/{self.sha}"

    @property
    def tree_url(self) -> str:
        return f"{self.server_url}/{self.repository}/tree/{self.sha}"

    def issue_url(self, number: int) -> str:
        return f"{self.server_url}/{self.repository}/issues/{number}"

    @property
    def release_tag(self) -> str:
        """Git tag naming this run's permanent release.

        A pure function of the run's identity, so anyone holding the
        repository, commit, run and attempt can derive the tag offline and
        fetch the release without querying the API first.

        `run_attempt` is part of the identity, so re-running every job mints a
        new immutable release. Re-running only the failed jobs does not: the
        job that evaluates this property is not re-executed, its output is
        reused, and the surviving assets land in the original release. That
        only holds because the tag is computed once and passed downstream as an
        opaque value — recomputing it per job would split one experiment across
        two releases.
        """
        payload = f"{self.repository}\0{self.sha}\0{self.run_id}\0{self.run_attempt}"
        digest = hashlib.blake2b(
            payload.encode("utf-8"),
            digest_size=RELEASE_TAG_BYTES,
            # Domain separation belongs in the hash, not the message: a message
            # that happens to start with these bytes cannot forge the domain.
            person=RELEASE_TAG_PERSON,
        ).digest()
        # Lowercase is not cosmetic. Refs are stored as paths, so on a
        # case-insensitive filesystem two tags differing only in case would
        # collide as loose refs. One case makes that unrepresentable.
        return base64.b32encode(digest).decode("ascii").lower()

    def release_url(self, tag: str) -> str:
        return f"{self.server_url}/{self.repository}/releases/tag/{tag}"

    @property
    def title(self) -> str:
        return f"Experiment run #{self.run_number} · {self.short_sha} · {self.ref_name}"


@dataclass(frozen=True, slots=True)
class Section:
    """One publishable unit of the ledger: a job's report."""

    key: str
    title: str
    body: str
    status: Status = Status.SUCCESS

    @property
    def digest(self) -> str:
        return digest_of(self.body)


@dataclass(frozen=True, slots=True)
class RemoteComment:
    identifier: int
    body: str
    url: str = ""

    @property
    def marker(self) -> Marker | None:
        return parse_marker(self.body)


@dataclass(frozen=True, slots=True)
class Create:
    key: str
    part: int
    body: str


@dataclass(frozen=True, slots=True)
class Update:
    identifier: int
    body: str


@dataclass(frozen=True, slots=True)
class Delete:
    identifier: int


# Closed variant set; the CLI interpreter matches it exhaustively.
Action = Create | Update | Delete


def _hard_split(line: str, budget: int) -> Iterator[str]:
    for start in range(0, len(line), budget):
        yield line[start : start + budget]


def split_body(body: str, budget: int = COMMENT_BODY_BUDGET) -> tuple[str, ...]:
    """Partition ``body`` into pieces of at most ``budget`` characters.

    Laws the tests check:
      * ``"".join(split_body(b, n)) == b`` — nothing is lost or reordered
      * every piece satisfies ``len(piece) <= n``
      * the result is never empty, so a section always renders to >= 1 comment

    Line boundaries are preferred; a single over-long line is split verbatim,
    because dropping bytes would break the join law.
    """
    if budget <= 0:
        raise LedgerError(f"comment budget must be positive, got {budget}")
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in body.splitlines(keepends=True):
        pieces = _hard_split(line, budget) if len(line) > budget else (line,)
        for piece in pieces:
            if size + len(piece) > budget and current:
                chunks.append("".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece)
    if current or not chunks:
        chunks.append("".join(current))
    return tuple(chunks)


def render_section(
    section: Section, context: RunContext, budget: int = COMMENT_BODY_BUDGET
) -> tuple[str, ...]:
    """Render a section as the ordered comment bodies it must occupy."""
    key = parse_key(section.key)
    pieces = split_body(section.body, budget)
    digest, total = section.digest, len(pieces)
    backref = (
        f"{section.status.badge} · [`{context.short_sha}`]({context.commit_url}) · "
        f"[run #{context.run_number} attempt {context.run_attempt}]"
        f"({context.attempt_url})"
    )
    return tuple(
        f"{Marker(key, index, total, section.status, digest).render()}\n"
        f"### {section.title}{f' (part {index} of {total})' if total > 1 else ''}\n\n"
        f"{backref}\n\n"
        f"{piece.rstrip()}\n\n"
        f"<sub>`sha256:{digest[:16]}` · key `{key}`</sub>"
        for index, piece in enumerate(pieces, start=1)
    )


def owned_comments(
    comments: Sequence[RemoteComment], key: str
) -> tuple[RemoteComment, ...]:
    """Comments belonging to one section, in part order."""
    mine = [
        comment
        for comment in comments
        if (marker := comment.marker) is not None and marker.key == key
    ]
    return tuple(
        sorted(
            mine,
            key=lambda c: (c.marker.part if c.marker else 0, c.identifier),
        )
    )


def plan(
    section: Section,
    comments: Sequence[RemoteComment],
    context: RunContext,
    budget: int = COMMENT_BODY_BUDGET,
) -> tuple[Action, ...]:
    """Compute the mutations that make the issue agree with ``section``.

    A section's arity — how many comments it occupies — is part of its identity.
    When the arity matches, parts are updated pointwise so permalinks survive an
    edit. When it does not, the section is replaced wholesale: GitHub appends
    comments and cannot insert, so interleaving new parts among old ones would
    break reading order.
    """
    desired = render_section(section, context, budget)
    existing = owned_comments(comments, parse_key(section.key))
    if len(existing) != len(desired):
        return tuple(Delete(comment.identifier) for comment in existing) + tuple(
            Create(section.key, index, body)
            for index, body in enumerate(desired, start=1)
        )
    return tuple(
        Update(comment.identifier, body)
        for comment, body in zip(existing, desired)
        if comment.body != body
    )


@dataclass(frozen=True, slots=True)
class SectionRecord:
    """One row of the issue index, read back off the published comments."""

    key: str
    status: Status
    parts: int
    digest: str
    url: str


def index(comments: Sequence[RemoteComment]) -> tuple[SectionRecord, ...]:
    """Derive the section index from what is actually published.

    Nothing else records which sections exist, so the index cannot drift from
    the record: it *is* the record, folded by key.
    """
    grouped: dict[str, list[RemoteComment]] = {}
    for comment in comments:
        marker = comment.marker
        if marker is not None:
            grouped.setdefault(marker.key, []).append(comment)
    records = []
    for key, bucket in grouped.items():
        first = min(bucket, key=lambda c: c.marker.part if c.marker else 0)
        marker = first.marker
        assert marker is not None  # every element of `bucket` carries one
        records.append(
            SectionRecord(
                key=key,
                status=marker.status,
                parts=len(bucket),
                digest=marker.digest,
                url=first.url,
            )
        )
    return tuple(sorted(records, key=lambda record: record.key))


def render_issue_body(
    context: RunContext,
    records: Sequence[SectionRecord] = (),
    finalized: bool = False,
) -> str:
    """Render the ledger issue: provenance, then the derived section index."""
    lines = [
        render_run_marker(context.repository, context.run_id),
        f"# {context.title}",
        "",
        (
            "Permanent record of one CI experiment. Actions logs and artifacts "
            "expire; this issue does not."
        ),
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Commit | [`{context.sha}`]({context.commit_url}) |",
        f"| Tree | [browse at this commit]({context.tree_url}) |",
        (
            f"| Archive | [`{context.release_tag}`]"
            f"({context.release_url(context.release_tag)}) |"
        ),
        f"| Workflow run | [#{context.run_number}]({context.run_url}) |",
        f"| Attempt | [{context.run_attempt}]({context.attempt_url}) |",
        f"| Workflow | `{context.workflow}` |",
        f"| Trigger | `{context.event}` by @{context.actor} |",
        f"| Ref | `{context.ref}` |",
        "",
        "## Sections",
        "",
    ]
    if records:
        lines += [
            "| Section | Status | Parts | Content digest |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            f"| [{record.key}]({record.url}) | {record.status.badge} | "
            f"{record.parts} | `{record.digest[:16]}` |"
            if record.url
            else f"| {record.key} | {record.status.badge} | {record.parts} | "
            f"`{record.digest[:16]}` |"
            for record in records
        ]
    elif finalized:
        lines.append("_This run published no section._")
    else:
        lines.append("_Publishing; this index is rewritten when the run finishes._")
    lines += ["", "---", "", ATTACHMENT_NOTE, ""]
    return "\n".join(lines)
