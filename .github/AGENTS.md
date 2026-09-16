# CI agent guide

Read the root [AGENTS.md](../AGENTS.md) first. This file covers the workflows,
the reusable modules under `actions/`, and the experiment ledger under
`scripts/`.

## Commands

```sh
uv run --locked python -m unittest discover \
  -s .github/scripts/tests -t .github/scripts -v
uv run --locked python -m compileall -q .github/scripts
bash -n ci/dcs/evaluate.sh
actionlint            # optional; lints .github/workflows only
```

## Shape

```
workflows/workflow_main.yml     job graph and the ledger lifecycle
workflows/ns3-evaluation.yml    one cluster evaluation, called per record
workflows/evaluation-matrix.json  one record per experiment; the data the plan reads
actions/python-env/             the only definition site for the uv pin
actions/ledger-publish/         reconcile one report into the ledger issue
actions/release-archive/        publish one bundle to the run's release
scripts/ci_ledger/              the ledger: pure model, `gh` shell, CLI
../ci/dcs/evaluate.sh           the one experiment command, dispatched on `kind`
```

A composite action cannot check out the repository that contains it, so
`actions/checkout` stays inline in every job; everything after it is a module.

## Independence of runs

Each push is an independent experiment and must leave a record, so the
concurrency group is keyed by `github.run_id` and nothing is cancelled. Two
pushes leave no record because they start no run: a push whose changed files
all match the `paths-ignore` list in `workflow_main.yml` (documentation,
templates, the licence), and a push whose head commit subject contains
`[skip ci]`, which GitHub applies before any job exists. Neither opens a
ledger issue or a release; that is the point, since an evaluation wave
provisions two SLURM runners for every record it selects. Do not add a job-level keyword gate: jobs behind `always()`
would still run and write "missing" ledger rows, which is what run #118 did. The
repository accepts no pull requests, so the workflow has no `pull_request`
trigger and one concurrency group keyed by run id; do not add a second
concurrency block.

Because runs no longer cancel each other, the account concurrency limit is the
real budget: **20 jobs on Free, 40 on Pro, shared across every repository in the
account** ([Limits](https://docs.github.com/en/actions/reference/limits)). The
`evaluations` matrix carries no `max-parallel`, so that limit is the only thing
pacing a wave.

## One build per run

`cluster-build` is the only job that compiles. It builds ns-3 with the rootless
conda toolchain (`ci/dcs/build.sh`) once per instruction-set level, `x86-64-v3`
and `x86-64-v4`, and uploads each level as a tarball. Every experiment job
picks the level its own CPU reports from `/proc/cpuinfo` and links against it
(`ci/dcs/install-runtime.sh`); the cluster fleet never compiles.

Consequences to keep in mind when editing:

- Consumers check out with `submodules: false`. Nothing under `experiments/`
  references `extern/` outside the build directory, and nothing rebuilds; if
  that changes, the submodule fetch has to come back.
- The bundle must be produced with `tar`, not by handing directories to
  `upload-artifact`, which drops the executable bit and the runtime env's
  symlinks.
- The bundle carries its own runtime libraries, and `install-runtime.sh`
  exports their path as `ASTRA_SIM_LD_LIBRARY_PATH`. Only the step that runs
  the simulator promotes it to `LD_LIBRARY_PATH`; job-global, the bundled
  libssl shadows the system OpenSSL for every later step's tooling.
- `cluster-seed` publishes both bundles as sealed shared store entries before
  the wave provisions, so a wave extracts one copy per ISA level instead of one
  per arm. Sharing is an optimization layer: any miss falls back to a private
  download and extraction.
- The wave starts after the build instead of alongside it. That trades a fixed
  front-loaded delay for provisioning zero SLURM allocations behind a broken
  build.

## Compiler-cache trust boundary

`cluster-build` owns the entire cache lifecycle in two inline steps, a
`cache/restore` before the build and a `cache/save` after it, so no other job
can restore an entry without the matching save policy. Two properties keep it
safe:

- **Only a push to `main` publishes an entry.** The predicate has exactly one
  definition site, the `if:` on the save step, which also requires an exact-key
  miss. There is deliberately **no fork check**: GitHub scopes caches per
  repository, so a fork and its parent share no cache and cannot contaminate
  each other. This repository *is* a fork, so testing
  `github.event.repository.fork` would hold the predicate at false forever and
  silently disable the cache.
- **A restored entry cannot produce a wrong object file.** ccache runs with
  `compiler_check=content` and an empty `sloppiness` (set in `ci/dcs/build.sh`),
  so every hit is validated against the preprocessed source and the compiler
  binary's own content. The conda toolchain floats per solve, and that is what
  makes an entry from a different solve safe: a stale, foreign, or corrupted
  entry can only ever cause a miss.

The key is `astra-sim-ccache-dcs-v1-<os>-<arch>-<march>-<hash>`, where the hash
is over `astra-sim/**`, `build/**`, `extern/**`, and `ci/dcs/**`, and the same
string without the hash is the restore-key. Cache identity is therefore a
function of the build inputs: two commits with identical native sources share
one entry, and an entry is published only on an exact-key miss, so the 10 GB
repository quota holds one entry per distinct build input rather than one per
commit. The ISA level sits in the prefix because the two cells' object sets are
disjoint and one shared key would leave the second cell's save colliding with
the first's.

Bump the `-v1` in the prefix to invalidate everything.

## Run identity is a value

The `ledger` job is the run's identity provider. It evaluates the release tag
once, opens the issue and the release, and emits both as job outputs. Nothing
downstream recomputes either one; they travel as opaque values.

That single evaluation site is what makes a partial re-run safe:

| Action | `ledger` re-runs? | Tag | Result |
| --- | --- | --- | --- |
| Re-run **failed** jobs | no, output reused | unchanged | assets land in the original release |
| Re-run **all** jobs | yes, `run_attempt` incremented | new | a new, immutable release |

Both halves are documented behaviour: "any outputs for any successful jobs in
the previous workflow run will be used for the re-run"
([Re-running](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)),
and `run_attempt` increments while `run_id` does not
([Contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts)).
Had each job derived the tag itself, a partial re-run would compute
`run_attempt=2` in the re-run jobs and `1` in the reused ones, splitting one
experiment across two releases.

Apply the same discipline to anything else that names a shared resource. The
cluster runtime's artifact prefix is an output of `cluster-build` for exactly
this reason: producer and consumer cannot drift apart if there is only one
place the name exists.

## The permanent archive

Actions artifacts expire after 90 days. Release assets do not, are capped at
2 GiB each with 1000 per release, and carry no storage or bandwidth charge
([About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)).
Every bundle is therefore published twice: to Actions, browsable and expiring,
and to the run's release, permanent.

The tag is `blake2b(digest_size=20, person=b"astra-sim-run")` over
`repository \0 sha \0 run_id \0 run_attempt`, base32-encoded and lowercased,
32 characters from `a-z2-7`. Three things about that are deliberate:

- **`person`, not a topic prefix.** Domain separation belongs in the hash, so a
  message that happens to start with the same bytes cannot forge the domain.
  blake2b caps `person` at 16 bytes; the label is 13. A longer one raises
  `ValueError` at run time, so a test pins the length.
- **Lowercase.** Refs are stored as paths. On a case-insensitive filesystem two
  tags differing only in case would collide as loose refs; one case makes that
  unrepresentable.
- **Derivable offline.** Given a repo, commit, run and attempt, anyone can
  compute the tag and fetch the release without querying the API first.

Releases are created `--prerelease --latest=false` so an experiment never
displaces the repository's real "Latest", and `--target <sha>` pins the tag to
the commit under test. Uploads use `--clobber`, which is what makes a re-run
replace an asset instead of failing on a duplicate name.

There is no recursion risk: `GITHUB_TOKEN` events do not start workflow runs,
and `on: push:` with only `branches:` never fires for tags
([Trigger a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)).

One tag accumulates per run, forever. The repository had none before this, and
clones fetch all tags by default, so the namespace grows slowly but
monotonically.

## The experiment ledger

Actions logs and artifacts expire; issues do not. Every push and manual dispatch
opens one `experiment-ledger` issue, each job publishes its report as a comment
on it, and a closing job proves the two agree.

- `scripts/ci_ledger/model.py` is pure and total: chunking, markers, the
  reconciliation plan, and the derived index. Test it directly.
- `scripts/ci_ledger/gh.py` is the only effect. It shells out to `gh`, which is
  preinstalled on runners and owns auth, pagination, and host resolution; the
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
instead of appending; a re-run converges rather than duplicating. The digest is
the sha256 of the exact report the job wrote, which is the same file the
adjacent `upload-artifact` step ships; the comment and the artifact are the same
bytes by construction, not by a later comparison.

`ledger close` therefore does not track a second copy of the truth. It reads the
comments back, folds them by key, and renders the issue's section index from
that fold. The index cannot drift from the record because it *is* the record.

A run whose every section succeeded closes its issue. Anything else stays open,
so the open `experiment-ledger` issues are exactly the runs still owing
attention.

`ledger_issue: 0` disables publication entirely, which is how a local
invocation behaves.

## Privilege: compute jobs and sink jobs

The workflow default is `contents: read`, which overrides the repository's
default token scope for every job. Beyond that, the graph is split in two:

```
evaluate   contents: read     runs ns-3 for hours, holds NO write scope
   |                          produces artifacts only
   v
archive    contents: write    downloads the bundle, tars it, uploads to the
           issues:   write    release, publishes the ledger section (~2 min)
```

Every job that executes experiment code (`cluster-build`, `cluster-seed`,
`evaluate`, and the `aggregate` job of each aggregation) holds no write scope
at all.
All outward-facing effects live in short sink jobs that run only `gh` and `tar`
and never execute anything from the artifact they unpack, so a malicious bundle
cannot reach the token. `contents: write` in particular can push commits and
move refs, which is why it must never sit in a six-hour simulator job.

The caller jobs for `ns3-evaluation.yml` declare `contents: write`; that is a
**ceiling for the called workflow, not a grant to the simulator**. Permissions
"can only be maintained or reduced — not elevated — throughout the chain"
([Reusing workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)),
and `evaluate` declares `contents: read`, which reduces it.

The trade is that the record is no longer progressive within a job: a bundle is
published when its sink job runs, moments after the producer finishes rather
than inside it. The step summary still shows the report live.

There is a test for this. The privilege split is asserted mechanically in the
verification snippet below; do not add a write scope to a compute job without
first deciding that assertion should change.

Every checkout sets `persist-credentials: false`, so no git credential survives
into the build, and the two ledger-only jobs sparse-checkout `.github/scripts`
rather than the full tree with submodules.

Actions are pinned to exact release tags (`astral-sh/setup-uv@v9.0.0`), not
floating majors. `actions/*` are first-party. Report bodies reach `gh` on stdin
and workflow inputs reach `bash` as environment variables, so no report or input
is ever interpolated into a shell command.

## Adding an evaluation

Add one record to `workflows/evaluation-matrix.json`. There is no job to
write: `evaluation-plan` selects the records whose `gate` the run enables, and
the `evaluations` matrix maps `ns3-evaluation.yml` over the result.

1. `kind` is the command the arm runs: `comparison` for a matched pair,
   `single` for one run and its report, `smoke` for the four smoke scripts and
   the 16-rank trace. `ci/dcs/evaluate.sh` dispatches on it; the `provision`
   job rejects anything else before a runner is minted.
2. Only a `comparison` may carry `require_congestion: true`. A `comparison`
   and a `single` may carry a non-zero `comparison_seed`, which runs that one
   seed; a `single` at the seed of a comparison of the same profile runs the
   same simulation as that comparison's matching arm, which is what lets the
   two join. `arm_count` is 1 for `single` and `smoke`, 3 for a comparison,
   and 4 when the profile's `selection_policy.domain` is `recovery` or
   `recovery_exempt`.
3. `ledger_key`, `artifact_name`, and `run_directory` are unique across the
   file, and `ledger_key` is stable across re-runs.
4. `simulation_timeout_seconds` stays under `execution_timeout_minutes * 60`.
   Where `arm_count * simulation_timeout_seconds` exceeds that budget, `notes`
   must name `walltime` as the backstop and give the arm count.
5. A new `gate` value needs a `workflow_dispatch` boolean and its own clause in
   the plan step's jq filter. The `record_filter` input is a regular
   expression on `ledger_key` that narrows what the gates already selected, so
   a subset of a gate dispatches without a gate of its own; empty runs every
   record the gates select.
6. Every record costs three hosted jobs (`provision`, `provision_courier`,
   `archive`) and two SLURM allocations (the arm and its courier). Keep the
   wave inside the account concurrency limit.

`scripts/tests/test_evaluation_matrix.py` asserts every rule above.

Assert the privilege split after any change to the job graph:

```sh
python3 - <<'EOF'
import yaml
for path in (".github/workflows/workflow_main.yml",
             ".github/workflows/ns3-evaluation.yml"):
    for name, job in yaml.safe_load(open(path))["jobs"].items():
        if job.get("uses"):
            continue  # a caller ceiling, not an executing job
        writes = [k for k, v in (job.get("permissions") or {}).items() if v == "write"]
        sink = name.startswith("archive") or name.startswith("ledger")
        assert sink or not writes, f"{name} holds {writes}"
print("no compute job holds a write scope")
EOF
```
