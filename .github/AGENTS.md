# CI agent guide

Read the root [AGENTS.md](../AGENTS.md) first. This file covers the workflows,
the reusable modules under `actions/`, and the experiment ledger under
`scripts/`.

## Commands

```sh
uv run --locked python -m unittest discover \
  -s .github/scripts/tests -t .github/scripts -v
uv run --locked python -m compileall -q .github/scripts
bash -n .github/workflows/setup.sh
actionlint            # optional; lints .github/workflows only
```

## Shape

```
workflows/workflow_main.yml     job graph and the ledger lifecycle
workflows/ns3-evaluation.yml    one hosted evaluation, called per experiment
actions/python-env/             the only definition site for the uv pin
actions/native-build/           toolchain + trusted ccache + native build
actions/native-runtime/         unpack the run's single build; never compiles
actions/ledger-publish/         reconcile one report into the ledger issue
scripts/ci_ledger/              the ledger: pure model, `gh` shell, CLI
```

A composite action cannot check out the repository that contains it, so
`actions/checkout` stays inline in every job; everything after it is a module.

## Independence of runs

Each push is an independent experiment and must leave a record, so the
concurrency group is keyed by `github.run_id` and nothing is cancelled. A pull
request is an iteration of a proposal rather than an experiment, so its group is
keyed by the head ref with `cancel-in-progress`. Both live in one expression in
`workflow_main.yml`; do not add a second concurrency block.

Because runs no longer cancel each other, the account-level ten-job concurrency
limit is the real budget. `max-parallel` on the paired matrix is what keeps a
single run inside it; raising it makes concurrent runs starve each other.

## One build per run

`native-build` is the only job that compiles. It packages
`extern/network_backend/ns-3/build` and `build/astra_analytical/build` into a
tarball, and every other native job unpacks it through
`actions/native-runtime`. A push to `dev` schedules seven native jobs; without
this it paid for seven identical ns-3 builds, because they start together and
no cache can serve a job that has not finished yet.

Consequences to keep in mind when editing:

- Consumers check out with `submodules: false`. Nothing under `experiments/`
  references `extern/` outside the build directory, and nothing rebuilds; if
  that changes, the submodule fetch has to come back.
- The tarball must be produced with `tar`, not by handing directories to
  `upload-artifact`, which drops the executable bit and the analytical build's
  symlinks.
- ns-3 links with an absolute `RUNPATH`. It resolves only because every hosted
  job checks out to the same workspace path, so `native-runtime` also exports
  `LD_LIBRARY_PATH`. A container-based or relocated job would need that export
  to keep working.
- Evaluations now start after the build instead of alongside it. That trades a
  fixed front-loaded delay for six fewer builds — deliberate, since an
  evaluation runs for hours.

## Compiler-cache trust boundary

`actions/native-build` owns the entire cache lifecycle — restore, configure,
build, save — so no caller can restore an entry without the matching save
policy. Two properties keep it safe:

- **Only a push to `master` or `dev` publishes an entry.** The predicate has
  exactly one definition site, in the action's `identity` step. A caller's
  `allow-cache-write` input can restrict it and can never widen it.
  Pull-request code restores but never writes. There is deliberately **no fork
  check**: GitHub scopes caches per repository, so a fork and its parent share
  no cache and cannot contaminate each other. This repository *is* a fork, so
  testing `github.event.repository.fork` would hold `trusted` at false forever
  and silently disable the cache.
- **A restored entry cannot produce a wrong object file.** ccache runs with
  `compiler_check=content` and an empty `sloppiness`, so every hit is validated
  against the preprocessed source and the compiler binary's own content. A
  stale, foreign, or corrupted entry can only ever cause a miss.

The cache key is derived from git's own object names for the paths that decide
compilation — `astra-sim`, `build`, `extern`, the toolchain script, and the
action itself — plus the resolved compiler versions. Cache identity is therefore
a function of the build inputs: two commits with identical native sources share
one entry, and an entry is published only on an exact-key miss, so the 10 GB
repository quota holds one entry per distinct build input rather than one per
commit.

Bump `cache-version` to invalidate everything.

## The experiment ledger

Actions logs and artifacts expire; issues do not. Every push and manual dispatch
opens one `experiment-ledger` issue, each job publishes its report as a comment
on it, and a closing job proves the two agree.

- `scripts/ci_ledger/model.py` is pure and total: chunking, markers, the
  reconciliation plan, and the derived index. Test it directly.
- `scripts/ci_ledger/gh.py` is the only effect. It shells out to `gh`, which is
  preinstalled on runners and owns auth, pagination, and host resolution — the
  ledger implements none of that itself.
- `scripts/ci_ledger/cli.py` interprets a plan; it makes no decisions.

Platform limits that shape the design:

| Limit | Value | Consequence |
| --- | --- | --- |
| Issue-comment body | 65,536 characters | A report is paginated across comments; the budget is 60,000 to leave room for the marker and heading. |
| Issue file attachment | web upload only, no API | Binary bundles stay Actions artifacts and are referenced, never attached. |
| Comments per issue | unbounded in practice | Pagination is the right answer to a long report. |

Every comment carries a self-describing marker:

```text
<!-- astra-ledger key=… part=i/n status=… digest=… -->
```

The key is the section's stable identity, so republishing reconciles in place
instead of appending — a re-run converges rather than duplicating. The digest is
the sha256 of the exact report the job wrote, which is the same file the
adjacent `upload-artifact` step ships; the comment and the artifact are the same
bytes by construction, not by a later comparison.

`ledger close` therefore does not track a second copy of the truth. It reads the
comments back, folds them by key, and renders the issue's section index from
that fold. The index cannot drift from the record because it *is* the record.

A run whose every section succeeded closes its issue. Anything else stays open,
so the open `experiment-ledger` issues are exactly the runs still owing
attention.

Fork pull requests hold a read-only token and never publish; those runs are
recorded by artifacts and the run summary. `ledger_issue: 0` disables
publication entirely, which is also how a local invocation behaves.

## Privilege

The workflow default is `contents: read`, which overrides the repository's
default token scope for every job. `issues: write` is granted only to the jobs
that write the ledger, and `python-quality` holds neither. A job that publishes
does so in-process rather than handing its report to a privileged collector:
that keeps the record progressive — a six-hour evaluation appears as soon as it
finishes, and a later job's failure cannot erase it — at the cost of the write
scope living in the evaluation job. Both were weighed; do not widen the scope
further without revisiting that trade.

Every checkout sets `persist-credentials: false`, so no git credential survives
into the build, and the two ledger-only jobs sparse-checkout `.github/scripts`
rather than the full tree with submodules.

Actions are pinned to exact release tags (`astral-sh/setup-uv@v9.0.0`), not
floating majors. `actions/*` are first-party. Report bodies reach `gh` on stdin
and workflow inputs reach `bash` as environment variables, so no report or input
is ever interpolated into a shell command.

## Adding an evaluation

1. Add a job in `workflow_main.yml` that calls `ns3-evaluation.yml`.
2. Give it `permissions: { contents: read, issues: write }` and pass
   `ledger_issue: ${{ fromJSON(needs.ledger.outputs.issue || '0') }}` plus a
   `ledger_key` unique within the run and stable across re-runs.
3. Add the job to `ledger-close`'s `needs` list, or the ledger will be
   finalized before that job publishes.
4. Keep the run inside the account concurrency limit; the comment above
   `max-parallel` is the accounting.
5. Depend on `native-build`, not `python-quality`, so the job receives the
   prebuilt runtime instead of compiling its own.
