# ASTRA-sim Agent Guide

## Start here

- Initialize the pinned workspace with `./utils/setup.sh`; use `uv` and
  `uv run --locked` for every project-owned Python command. Do not use `pip`
  or the system interpreter.
- Read the closest `AGENTS.md` before changing files in that subtree.
- Before committing, read and follow
  [`.github/skills/git-commit/SKILL.md`](.github/skills/git-commit/SKILL.md).
  It defines this repository's required Conventional Commit message format.
- A push to `main` runs the full evaluation wave unless every changed file is
  documentation or the head commit subject contains `[skip ci]`. Put
  `[skip ci]` on a push that must not start a wave.

## Verification

| Change | Run before commit |
| --- | --- |
| Python tooling or Ring-3D experiment | `uv lock --check && uv run --locked python -m compileall -q experiments/ring_3d && uv run --locked python -m unittest discover -s experiments/ring_3d/tests -v` |
| GitHub Actions workflow, composite action, or CI ledger | `uv run --locked python -m unittest discover -s .github/scripts/tests -t .github/scripts` and, if available, `actionlint` |
| Shell script | `bash -n <changed-script>` |
| Native ASTRA-sim or ns-3 integration | `bash .github/workflows/build.sh && bash .github/workflows/test.sh` |
| Ring-3D native integration | `bash experiments/ring_3d/smoke.sh` after the native build |
| Any change | `git diff --check` |

Run the narrowest applicable checks first. Do not commit failing checks; record
checks that are intentionally not run, especially costly simulator runs.

## Engineering contract

- Favor typed, validated configurations; explicit ownership and lifecycle
  boundaries; immutable inputs; deterministic seeds; and total state
  transitions. Make invalid states unrepresentable where the existing language
  and ABI permit.
- Treat error handling as part of the model: validate inputs at boundaries,
  preserve error context, and never silently swallow failures or convert them
  into fabricated simulation results.
- Optimize measured hot paths without weakening semantics. Avoid avoidable
  allocations, copies, dynamic dispatch, and repeated parsing in packet/event
  paths; measure before claiming a performance gain.
- Keep project-owned units cohesive and normally below 500 lines. When a
  change would materially grow a large file, extract a focused module first;
  document any unavoidable exception in the change description.
- Refactor decisively rather than maintaining duplicate legacy paths. When a
  schema or interface changes, migrate all owned call sites, profiles, tests,
  and documentation in the same change while preserving reproducibility.
- Preserve local style and public behavior unless a task deliberately changes
  them. Do not edit vendored or third-party submodules under `extern/` merely
  to work around an owned-code issue; make such changes only for a deliberate,
  tested transport/backend task.

## Scope and safety boundaries

- Never commit credentials, generated local run outputs, or changes inside
  `.venv/`, `build/`, or `runs/`.
- Pinned dependency changes update both `pyproject.toml` and `uv.lock` through
  `uv lock`; never hand-edit `uv.lock`.
- `extern/` entries are pinned submodules. Initialize with
  `git submodule update --init --recursive`; change a pointer only when that
  dependency revision is intentionally part of the task.
- The shared agent skills are the `.github/skills` submodule. Load skill files
  just in time; do not edit the vendored copy from this repository.

## Progressive context

- General development, validation, and change workflows:
  [docs/agents/development.md](docs/agents/development.md)
- Research scope, valid claims, and current transport-model limits:
  [docs/agents/ring-3d-research-context.md](docs/agents/ring-3d-research-context.md)
- DBLP baseline, loss-semantics, PFC, topology, and CLR validity threats:
  [docs/agents/ring-3d-known-flaws.md](docs/agents/ring-3d-known-flaws.md)
- Adopted loss-tolerant RDMA transport direction and model-level gates:
  [docs/agents/loss-tolerant-rdma-decision.md](docs/agents/loss-tolerant-rdma-decision.md)
- Verified current ns-3/QBB/RDMA implementation gaps for that direction:
  [docs/agents/loss-tolerant-rdma-audit.md](docs/agents/loss-tolerant-rdma-audit.md)
- Timeout triage, transport hot-path rules, liveness bounds, and CI budget
  arithmetic:
  [docs/agents/simulation-liveness-and-performance.md](docs/agents/simulation-liveness-and-performance.md)
- Building the ns-3 backend without root, with an ephemeral `/tmp` toolchain:
  [docs/agents/rootless-ephemeral-build.md](docs/agents/rootless-ephemeral-build.md)
- Ring-3D generator, policy, telemetry, or profile changes:
  [experiments/ring_3d/AGENTS.md](experiments/ring_3d/AGENTS.md)
- CI workflows, cache trust boundary, and the experiment ledger:
  [.github/AGENTS.md](.github/AGENTS.md)
- Agent-context index:
  [docs/agents/README.md](docs/agents/README.md)