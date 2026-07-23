# Ring-3D experiment agent guide

Read the root [AGENTS.md](../../AGENTS.md) first. For policy or research work,
read in this order before changing model semantics, CLR, microbursts, loss, or
telemetry:

1. [DBLP paper brief](../../docs/agents/ring-3d-paper-brief.md)
2. [DBLP known flaws](../../docs/agents/ring-3d-known-flaws.md)
3. [Loss-tolerant RDMA decision](../../docs/agents/loss-tolerant-rdma-decision.md)
4. [Loss-tolerant RDMA implementation-gap audit](../../docs/agents/loss-tolerant-rdma-audit.md)
5. [ASTRA-sim pivot](../../docs/agents/ring-3d-astra-pivot.md)
6. [Ring-3D glossary](GLOSSARY.md)
7. [Research claim boundary](../../docs/agents/ring-3d-research-context.md)
8. [Validation protocol](VALIDATION_PROTOCOL.md)

For a code-path change, additionally read
[ns-3 policy implementation](../../astra-sim/network_frontend/ns3/POLICY_IMPLEMENTATION.md).

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
| CLR schedule | It is an exogenous phase proxy. Keep it static and seed-reproducible; document empirical trace provenance or conduct schedule sensitivity analysis. See [paper brief](../../docs/agents/ring-3d-paper-brief.md#critical-learning-regime). |
| Background microburst | It is a finite RDMA incast described by bytes, endpoints, and start offsets; observed flow duration is not a configured injection duration. See [glossary](GLOSSARY.md#background-microburst). |
| Packet-loss experiment | Treat it as a transport-model change. Read the [loss-tolerant decision](../../docs/agents/loss-tolerant-rdma-decision.md) and [implementation-gap audit](../../docs/agents/loss-tolerant-rdma-audit.md), then define $q$, window duration $D$, direction/scope, recovery behavior, and retransmission telemetry. |
| DBLP comparison | Separate network loss $q$ from residual-loss tolerance $P$. Use fixed-$P_\mathrm{low}$ baseline only after implementing bounded-loss semantics. See [pivot](../../docs/agents/ring-3d-astra-pivot.md#baseline-selection-is-part-of-the-claim). |
| Policy-selection change | Update eligibility tests, logical/physical accounting, telemetry schema, analyzer/report, validation protocol, and claim boundary. See [implementation guide](../../astra-sim/network_frontend/ns3/POLICY_IMPLEMENTATION.md). |

## Claim boundaries

The current mechanism models a lossless, congestion-inducing RDMA incast plus
phase-aware logical payload substitution. It can establish modeled latency and
traffic effects under that condition; it cannot establish model accuracy,
partial-gradient quality, literal packet loss, or the original paper's
selective-retransmission semantics. Keep this distinction visible in comments,
reports, and pull requests.