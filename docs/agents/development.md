# Development workflow and decision rules

## Reproducible environment

The repository owns a CPython 3.11 environment through `uv`; `uv.lock` is the
complete Python dependency graph. Initialize a checkout with:

```sh
./utils/setup.sh
```

The script recursively initializes pinned submodules and runs `uv sync
--locked`. Use `uv run --locked` for project Python commands. If dependencies
change, update `pyproject.toml` and regenerate the lock with `uv lock`; then
verify it with `uv lock --check`.

## Change-routing table

| Need | Preferred location and action |
| --- | --- |
| Workload, profile, analysis, policy, or experiment tests | `experiments/ring_3d/`; read its local `AGENTS.md` first |
| Native simulation interface or telemetry bridge | `astra-sim/network_frontend/ns3/`; preserve logical completion and add focused tests |
| Packet loss, queueing, PFC, or RDMA recovery semantics | Bundled ns-3 backend under `extern/network_backend/ns-3/`; treat as a transport-model change and document the new semantics |
| General simulator behavior | `astra-sim/system/`, `astra-sim/common/`, or the relevant frontend; follow nearby C++ conventions |
| Dependency revision | `.gitmodules` plus the submodule pointer; do not modify submodule contents in place |
| Agent workflow or reusable agent procedure | Root/nested `AGENTS.md`, `docs/agents/`, or an upstream skill repository; keep task-specific context out of the root guide |

For Ring-3D work, read the documents in the order defined by the
[agent-context index](README.md#ring-3d-reading-order). Do not begin from an
implementation file when a request uses paper terms such as “loss”,
“microburst”, or $P_\mathrm{low}$: their original-paper meaning and current
code meaning are intentionally different.

## Change discipline

1. Locate the owning layer and read its closest guidance and tests before
   editing. Do not solve an owned-code defect by patching a generated artifact.
2. State the modeled invariant in code and tests. Use narrow types, validated
   JSON/profile fields, and explicit enums/state transitions rather than magic
   values or permissive fallback behavior.
3. Keep configuration, generated artifacts, telemetry schema, analysis, and
   documentation in sync. A configuration field without validation and a
   corresponding auditable output is incomplete.
4. Keep seeds, RNG stream/run values, and experiment inputs explicit. Paired
   comparisons must share every non-treatment input.
5. Run the narrow validation first, then the required integration validation.
   Do not claim model behavior from a partial run, a timeout, or fabricated
   telemetry.
6. Inspect `git diff --check` and the staged diff. Read the Git commit skill
   immediately before committing, then use its scope-resolution procedure and
   Conventional Commit format.

## Native and simulator constraints

- ASTRA-sim has project-owned C++ and Python code plus pinned third-party
  submodules. Treat the ns-3 backend as a model with explicit assumptions, not
  as a generic production network stack.
- Packet-level work must account for packet payload/header sizes, queues, PFC,
  congestion feedback, retransmission behavior, and completion/liveness.
  Tests must distinguish a modeled observation from an asserted assumption.
- Avoid unbounded event generation, global mutable experiment state, and
  cross-run leakage. Reset state at the appropriate simulation boundary.
- The project uses exception-based C++ configuration failures in places. Add
  actionable context to failures and preserve the existing ownership/cleanup
  discipline instead of catching and discarding errors.

## Documentation standards

Documentation for a simulation change must answer:

1. What input is configured and at which layer?
2. What physical or logical mechanism does that input model?
3. Which outcome is measured versus merely assumed?
4. What conclusion is supported, and what conclusion remains out of scope?
5. Which seed, artifact, and validation command make the result reproducible?

Use the Ring-3D research context for these answers instead of copying its
details into unrelated documents.