# Ring-3D experiment agent guide

Read the root [AGENTS.md](../../AGENTS.md) first, then load the full research
boundary document at
[docs/agents/ring-3d-research-context.md](../../docs/agents/ring-3d-research-context.md)
before changing model semantics, policy, CLR, microbursts, or telemetry.

## Commands

```sh
uv run --locked python -m unittest discover -s experiments/ring_3d/tests -v
uv run --locked python -m compileall -q experiments/ring_3d
bash experiments/ring_3d/smoke.sh
```

The smoke command requires the native ns-3 target. Build it with
`bash .github/workflows/build.sh` when needed. Never run a heavy profile merely
as a documentation check; use the smoke profile first and retain artifacts for
any research result.

## Local invariants

- Profiles are validated inputs, not optional suggestions. Extend the typed
  profile model, validation, generated manifest, tests, and documentation
  together when adding a field.
- A materialized run must preserve its profile, ET traces, topology, CLR mask,
  experiment configuration, execution controls, and telemetry paths. These
  artifacts are the reproducibility record.
- Paired baseline/policy runs share every non-treatment input: trace,
  topology, selected stressor, CLR mask, policy-selection seed, and ns-3 RNG
  seed/run. Change only the documented treatment.
- Preserve a strict distinction between logical bytes, physical bytes, packet
  loss, retransmission, background traffic, and policy substitution. Do not
  use names such as `drop_probability` for a new semantic without a migration
  and explicit report language.
- Completion is a correctness invariant. A selected policy payload must either
  follow the modeled completion contract or explicitly produce a recorded
  failure; never silently complete an incomplete transfer.

## Decision table

| Requested change | Required interpretation and follow-up |
| --- | --- |
| CLR schedule | It is an exogenous phase proxy. Keep it static and seed-reproducible; document empirical trace provenance or conduct schedule sensitivity analysis. |
| Background microburst | It is a finite RDMA incast described by bytes, endpoints, and start offsets; observed flow duration is not a configured injection duration. |
| Packet-loss experiment | Treat it as a transport-model change. Define $q$, window duration $D$, affected direction/traffic classes, recovery behavior, and retransmission telemetry. |
| DBLP comparison | Separate network loss $q$ from residual-loss tolerance $P$. Use fixed-$P_\mathrm{low}$ baseline only after implementing bounded-loss semantics. |
| Policy-selection change | Update eligibility tests, logical/physical accounting, telemetry schema, analyzer/report, validation protocol, and claim boundary. |

## Claim boundaries

The current mechanism models a lossless, congestion-inducing RDMA incast plus
phase-aware logical payload substitution. It can establish modeled latency and
traffic effects under that condition; it cannot establish model accuracy,
partial-gradient quality, literal packet loss, or the original paper's
selective-retransmission semantics. Keep this distinction visible in comments,
reports, and pull requests.