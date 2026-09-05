# Ring-3D current claims and roadmap

## Read this after the mechanism documents

This document is the current-state boundary, not the explanation of the
original paper or a code-path guide. Read documents in this order:

1. [DBLP paper brief](ring-3d-paper-brief.md): original transport concepts.
2. [DBLP known flaws](ring-3d-known-flaws.md): evidence-labeled baseline,
  transport, PFC, topology, and CLR validity threats.
3. [Loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md): adopted
  transport contract and implementation evidence gates.
4. [ASTRA-sim pivot](ring-3d-astra-pivot.md): which concepts current Ring-3D
  models, abstracts, or does not model; it selects no remedy.
5. [Ring-3D glossary](../../experiments/ring_3d/GLOSSARY.md): exact current
  parameter names and generated artifacts.
6. This document: claims, backend limits, controls, and future work.
7. [Validation protocol](../../experiments/ring_3d/VALIDATION_PROTOCOL.md):
  canonical estimands and decision rules.

## Purpose

This project uses ASTRA-sim 2.0, Chakra execution traces, and the bundled ns-3
RDMA backend to study the **mechanism-level** effect of phase-aware
communication policy on collective tail latency. It is not a framework-training
replay, a hardware measurement, or an accuracy/convergence experiment.

The intended evidence path is:

> Under explicitly configured and reproducible modeled network conditions,
> phase-aware transport or communication policy improves DP All-Reduce tail
> latency and simulated makespan relative to an appropriate matched baseline.

This is deliberately narrower than “the method does not harm model accuracy”
or “the result proves performance on unavailable production-scale hardware.”
ASTRA-sim does not compute gradient values, optimization updates, validation
accuracy, or perplexity; it cannot substantiate those claims.

## Current Ring-3D condition

The flagship comparison profiles (`llama3_70b_*`) are **70B-class
gradient-bucket microbenchmarks** over 16, 32, or 64 ranks, not a full
Llama/Megatron/DeepSpeed replay:

- TP=8, one representative 1 GiB typed DP All-Reduce bucket per rank per step,
  a 20-step communication window overlapped with 5.4 ms compute per node, and
  a rail-optimised Clos (2:1 or 4:1, depending on the profile).
- Seven 128 MiB background RDMA flows target a downlink rank to create a
  synchronized incast stressor.
- The fabric is UEC-shaped best-effort: PFC is off, packet trimming
  forward-to-destination replaces a congested packet's payload at the switch,
  and TC_med (the trimmed-header class) is capped at a 25% link share. Every
  result to date recovers with go-back-N (no sender congestion control);
  `llama3_70b_64_sr2x` instead enables `transport_recovery.selective_repair`.
  See [the loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md) for
  the full transport contract.
- A flow has a configured byte size and start offset, but no configured fixed
  lifetime. Its observed completion time is determined by simulated queueing,
  trimming, recovery, and (for a profile that leaves `pfc_enabled` at its
  default `true`) PFC. `bytes / link_rate` is only an uncongested
  serialization lower bound.

See [experiments/ring_3d/README.md](../../experiments/ring_3d/README.md) and
[experiments/ring_3d/VALIDATION_PROTOCOL.md](../../experiments/ring_3d/VALIDATION_PROTOCOL.md)
for executable setup and predeclared estimands, and
[the run #117 wave readout](run-117-wave-readout.md) for the current measured
result.

## Current CLR proxy

CLR is exogenous to ASTRA-sim; the simulator reads a precomputed mask and does
not sample CLR state at runtime. Every flagship comparison profile sets
`clr_schedule` to the pinned explicit critical-step list `[1, 2, 3, 20]` (see
[CLR schedule evidence](clr-schedule-evidence.md) for the literature behind
that choice). A profile that omits `clr_schedule` instead falls back to the
generator's seeded decay/spike proxy:

$$
P(\mathrm{CLR}\mid t)=\min\left(1,e^{-\lambda t}+
\sum_k A\exp\left(-\frac{(t-kT)^2}{2\sigma^2}\right)\right).
$$

Neither form is simulator-derived gradient behavior; both are explicit phase
proxies. A stronger study uses a mask derived from real gradient-norm traces.

Never describe either proxy as simulator-derived gradient behavior.

## Current policy semantics

Only requests typed as `dp`, `CollectivePayload`, and `All_Reduce` are policy
eligible. A deterministic hash selects a whole eligible logical payload.
Selected payloads use a reliable protected 64-byte provenance-control QP on
priority group 1; its completion resolves the original logical sender and
receiver. Telemetry records logical and physical bytes separately.

Therefore the current policy is **phase-aware logical admission suppression**.
Call its thresholds selection probabilities: $s_\mathrm{CLR}=0.005$ and
$s_\mathrm{stable}=0.1$ in the flagship condition. Each comparison runs three
matched arms per seed:

- Fixed-low: selection probability 0.5% on every step.
- Policy: 0.5% on the critical steps `[1, 2, 3, 20]`, 10% elsewhere.
- Fixed-high: selection probability 10% on every step.
- These values are whole-payload selection probabilities, not packet-loss rates
  or DBLP residual-loss tolerances $P_\mathrm{low}$ and
  $P_\mathrm{high}$.

The current study is a useful congestion-relief ablation, but it must be
called DBLP-inspired rather than a reproduction of DBLP bounded-loss
transport. Do not imply that its 64-byte replacement models partial gradient
delivery, receiver bitmaps, or selective retransmission.

## Separate the three quantities

Use distinct terms and fields for:

| Quantity | Meaning | Current status |
| --- | --- | --- |
| $q$ | An explicitly configured data-plane packet-loss probability | Not configured on the flagship fabric; trimming instead produces real, congestion-driven data loss that is not a stated $q$ |
| $D$ | Duration of the packet-loss window or sender injection window | No loss window; background-flow completion is observed, not configured |
| $P$ | Residual missing-data tolerance at which a DBLP round stops recovery | Not modeled; current values are admission-selection probabilities |

Do not label $P$ as “loss rate” in reports. Do not infer $D$ from background
flow bytes without stating that it is a lower bound rather than an input.
The [glossary](../../experiments/ring_3d/GLOSSARY.md) is the canonical mapping
from these terms to current profile/configuration fields.

## Bundled backend: what it can and cannot support now

The ns-3 backend implements the
[loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md)'s contract:
packets are classified before an impairment applies, control traffic
(ACK/NACK/PFC/CNP) bypasses the configured data-loss model, and packet
trimming forward-to-destination models congestion-induced loss on the
best-effort fabric. Recovery is go-back-N with an RTO backstop, or range-based
selective repair with out-of-order acceptance when a profile sets
`transport_recovery.selective_repair`. It still does not model packet
spraying, reorder buffering beyond the accepted out-of-order ranges,
placeholder bytes, approximate completion, or `DSCP_TRIMMABLE_RTX`. See the
[implementation-gap audit](loss-tolerant-rdma-audit.md) for the verified
detail and remaining gaps.

Do not enable a DBLP-scale $q$ of 60-90% by changing one global setting and
report the result as DBLP; the modeled mechanism is congestion-driven
trimming, not an injected Bernoulli loss probability, and an unvalidated
change can produce artifacts or liveness failures unrelated to the intended
mechanism.

## Unresolved research questions

No remedy is selected for the documented DBLP flaws. Before any future protocol
or experiment design is described as a direction, resolve the relevant
evidence gap:

1. Is exposed communication time still a material bottleneck once the intended
  workload's overlap behavior is modeled?
2. Is the target tail event loss, PFC pause propagation, retransmission,
  congestion control, or a combination of mechanisms?
3. Can the target fabric deliver the required control information during the
  same congestion episode, and what is its queueing behavior?
4. What application-visible delivery information is required to preserve the
  semantics of optimizer, compression, and residual state?
5. Which traffic domain and collective dependency can tolerate which logical or
  physical loss outcome, if any?
6. What phase signal is available, what does it cost, and how accurately does
  it predict the claimed sensitivity?

See the [known-flaws register](ring-3d-known-flaws.md) for the evidence status
and scope of each question. A completed simulation at a larger topology is not
by itself an answer to any of them.

## Required experimental controls

- Match workload trace, physical topology, microburst/loss schedule, policy
  selection seed, ns-3 RNG seed/run, and CLR mask within every pair.
- Use operation-span P99 (the episode's worst collective) and W (trimmed-payload
  bytes divided by offered bytes, from `transport_summary.csv`) as the primary
  estimands. Per-rank P99 is retired: its confidence interval spans zero in
  every wave measured so far. Use per-QP FCT only as a transport diagnostic.
- Gate congested runs on auditable raw signals: background/loss activity,
  nonzero queueing, trim/rejection counts on the best-effort fabric, completed
  PFC intervals on a lossless profile, rank completion, and complete telemetry
  joins.
- Retain exact profiles, generated ET traces, masks, experiment JSON, network
  configuration, execution controls, raw outputs, and reports.
- State invalid/unavailable outcomes instead of replacing them with proxy
  metrics or omitting failed seeds.

## Permitted conclusion language

Use language such as:

> In the specified packet-level ASTRA-sim/ns-3 model, across matched seeds and
> stated CLR/network conditions, the policy reduced modeled DP All-Reduce tail
> latency relative to the stated baseline.

Do not claim unmeasured model accuracy, exact reproduction of a production loss
process, or validated performance for hardware/topology sizes that did not
complete simulation.