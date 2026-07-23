# Ring-3D research context and claim boundaries

## Purpose

This project uses ASTRA-sim 2.0, Chakra execution traces, and the bundled ns-3
RDMA backend to study the **mechanism-level** effect of phase-aware
communication policy on collective tail latency. It is not a framework training
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

The CI-scale 70B-class profile is a **16-rank gradient-bucket
microbenchmark**, not a full Llama/Megatron/DeepSpeed replay:

- TP=8, PP=1, DP=2; three simulated steps; a two-leaf, four-spine 400 Gb/s
  Clos; and one representative 1 GiB typed DP All-Reduce bucket per rank per
  step.
- Seven 128 MiB background RDMA flows target rank 8 at zero start-offset
  spacing when the first step-2 DP All-Reduce is issued. This is a synchronized
  incast stressor with 0.875 GiB total offered background data.
- Link error injection is currently zero. The microburst is competing reliable
  RDMA background traffic, not a packet-loss impairment.
- A flow has a configured byte size and start offset, but no configured fixed
  lifetime. Its observed completion time is determined by simulated queueing,
  PFC, congestion control, and RDMA recovery. `bytes / link_rate` is only an
  uncongested serialization lower bound.

See [experiments/ring_3d/README.md](../../experiments/ring_3d/README.md) and
[experiments/ring_3d/VALIDATION_PROTOCOL.md](../../experiments/ring_3d/VALIDATION_PROTOCOL.md)
for executable setup and predeclared estimands.

## Current CLR proxy

CLR is exogenous to ASTRA-sim. The generator currently emits a static,
seeded, immutable mask before a run, with an early-training exponential decay
and optional Gaussian epoch-boundary spikes:

$$
P(\mathrm{CLR}\mid t)=\min\left(1,e^{-\lambda t}+
\sum_k A\exp\left(-\frac{(t-kT)^2}{2\sigma^2}\right)\right).
$$

The simulator reads that mask; it does not sample CLR state at runtime. This
replaces a uniform runtime model, but the current three-step profile is too
short to validate an empirical early-training distribution. A stronger study
uses a mask derived from real gradient-norm traces. If traces are unavailable,
the decay/spike schedule is a sensitivity assumption: test early-heavy,
uniform, late-heavy, and misclassified masks with matched seeds.

Never describe this proxy as simulator-derived gradient behavior.

## Current policy semantics

Only requests typed as `dp`, `CollectivePayload`, and `All_Reduce` are policy
eligible. A deterministic hash selects a whole eligible logical payload.
Selected payloads use a reliable protected 64-byte provenance-control QP on
priority group 1; its completion resolves the original logical sender and
receiver. Telemetry records logical and physical bytes separately.

Therefore the current policy is **phase-aware logical admission suppression**:

- Current lossless baseline: $P_\mathrm{low}=P_\mathrm{high}=0$.
- Current policy: $P_\mathrm{low}=0$ in CLR and
  $P_\mathrm{high}=0.1$ in stable steps.
- These values are whole-payload selection probabilities, not packet-loss
  rates or DBLP residual-loss tolerances.

The current study is a useful congestion-relief ablation, but it must be
called DBLP-inspired rather than a reproduction of DBLP bounded-loss
transport. Do not imply that its 64-byte replacement models partial gradient
delivery, receiver bitmaps, or selective retransmission.

## Separate the three quantities

Use distinct terms and fields for:

| Quantity | Meaning | Current status |
| --- | --- | --- |
| $q$ | Data-plane packet-loss probability during a network impairment | $q=0$; not modeled in Ring-3D runs |
| $D$ | Duration of the packet-loss window or sender injection window | No loss window; background-flow completion is observed, not configured |
| $P$ | Residual missing-data tolerance at which a DBLP round stops recovery | Not modeled; current values are admission-selection probabilities |

Do not label $P$ as “loss rate” in reports. Do not infer $D$ from background
flow bytes without stating that it is a lower bound rather than an input.

## Bundled backend: what it can and cannot support now

The ns-3 backend contains a static `ERROR_RATE_PER_LINK` and a per-topology
link error-rate field. It attaches a packet-level independent Bernoulli
`RateErrorModel` to QBB receivers. RDMA detects received sequence gaps and
uses ACK/NACK-driven resend from the last acknowledgement.

This is not yet a safe high-loss DBLP model:

- the receive error model runs before traffic-class handling, so it can drop
  data, ACK, NACK, CNP, and PFC packets;
- loss is static, not a directed time-bounded window tied to a workload event;
- sender-side retransmission timeouts are absent, so a lost tail packet,
  acknowledgement, or NACK can stall progress;
- recovery is gap/NACK based rather than a per-chunk receiver bitmap and
  selective retransmission;
- current experiment telemetry records requested QP bytes, not explicit
  retransmission bytes or a residual-loss fraction.

Do not enable $q=60\%-90\%$ by changing one global setting and report the
result as DBLP. That can produce artifacts or liveness failures unrelated to
the intended paper mechanism.

## Roadmap to stronger empirical evidence

1. **Keep the current incast study as a separate ablation.** It validates the
   queue/PFC mechanism under a controlled congestion stressor.
2. **Add a minimal lossy-RDMA condition.** Implement a seeded, directed,
   time-bounded, data-plane-only loss window. Keep ACK/NACK/CNP/PFC control
   traffic lossless for this first condition.
3. **Add sender timeout recovery and observability.** Record injected drops,
   retransmitted packets/bytes, completion failures, queue/PFC signals, and
   loss-window boundaries. Validate low loss before high loss.
4. **If making a DBLP transport claim, add an explicit abstraction.** Model
   chunk delivery state, a reliable probe/bitmap/stop control path, a round
   identifier, and stop when missing fraction is at most $P$.
5. **Use a paper-aligned comparison.** The baseline fixes
   $P=P_\mathrm{low}$ for every phase; policy uses $P_\mathrm{low}$ in CLR and
   $P_\mathrm{high}$ outside CLR. This differs from the current lossless
   suppression baseline.
6. **Scale only as far as completed simulations allow.** Label 16-rank
   results mechanism validation. Report a completed scaling sweep; do not
   extrapolate a timed-out 256-node condition as measured evidence.

## Required experimental controls

- Match workload trace, physical topology, microburst/loss schedule, policy
  selection seed, ns-3 RNG seed/run, and CLR mask within every pair.
- Use native DP All-Reduce issue-to-completion P99 and all-rank-span P99 as
  primary latency estimands; use per-QP FCT only as a transport diagnostic.
- Gate congested runs on auditable raw signals: background/loss activity,
  nonzero queueing, completed PFC intervals where relevant, rank completion,
  and complete telemetry joins.
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