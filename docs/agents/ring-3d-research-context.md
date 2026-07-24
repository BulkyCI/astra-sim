# Ring-3D current claims and roadmap

## Read this after the mechanism documents

This document is the current-state boundary, not the explanation of the
original paper or a code-path guide. Read documents in this order:

1. [DBLP paper brief](ring-3d-paper-brief.md): original transport concepts.
2. [DBLP known flaws](ring-3d-known-flaws.md): evidence-labeled baseline,
  transport, PFC, topology, and CLR validity threats.
3. [Loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md): adopted
  future transport contract and implementation evidence gates.
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

Therefore the current policy is **phase-aware logical admission suppression**.
Call its thresholds selection probabilities, for example
$s_\mathrm{CLR}=0$ and $s_\mathrm{stable}=0.1$ in the 70B-class condition:

- Current fixed-low baseline: both selection probabilities are 0.5%.
- Current policy: CLR selection probability is 0.5% and stable-step selection
  probability is 10%.
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
| $q$ | Data-plane packet-loss probability during a network impairment | $q=0$; not modeled in Ring-3D runs |
| $D$ | Duration of the packet-loss window or sender injection window | No loss window; background-flow completion is observed, not configured |
| $P$ | Residual missing-data tolerance at which a DBLP round stops recovery | Not modeled; current values are admission-selection probabilities |

Do not label $P$ as “loss rate” in reports. Do not infer $D$ from background
flow bytes without stating that it is a lower bound rather than an input.
The [glossary](../../experiments/ring_3d/GLOSSARY.md) is the canonical mapping
from these terms to current profile/configuration fields.

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

## Adopted loss-tolerant transport direction

Future packet-loss research must follow the
[loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md): classify packets
before impairment, place named control packets in a separate high-priority
class with zero configured impairment loss, and apply loss only to explicitly
scoped data traffic. This is an adopted requirement, not a statement that the
current backend satisfies it. Current Ring-3D remains the lossless-incast
ablation described above.

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