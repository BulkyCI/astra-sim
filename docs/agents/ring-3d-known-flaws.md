# DBLP known flaws and open validity threats

This register makes the current DBLP critiques visible to every agent before it
changes a baseline, transport abstraction, experiment label, or conclusion. It
records problems and evidence gaps only. **It does not choose a solution,
implementation, architecture, or experiment plan.**

## How to use this register

Treat each item as a claim-boundary check, not as a proven universal failure of
all bounded-loss methods. Preserve its evidence status in design notes and
reports. Do not silently turn a conditional concern into a fact, and do not
claim that a future implementation fixes an item until it has its own measured
evidence.

### Evidence labels

- **Paper-verified:** confirmed against the full paper text in
  [dblp-paper-detailed-read.md](dblp-paper-detailed-read.md), page-cited.
- **Repository-verified:** established by current ASTRA-sim code or checked-in
  experiment documentation.
- **Critical hypothesis:** a technically grounded failure path that requires a
  specific model, measurement, or source inspection before it becomes a result.

## 1. Naive baseline and missing communication-computation overlap

**Status: paper-verified validity threat** (dblp-paper-detailed-read.md D13,
p.12 Algorithm 4). The paper's own worker loop is fully synchronous and
blocking: forward/backward pass, then blocking send, then blocking receive,
then parameter update, with no computation/communication overlap. This differs
from modern DDP/FSDP-style bucketed execution, where gradient communication can
progress while later backward computation continues. The consequence is a
baseline confound: an end-to-end benefit measured with no overlap can include
network time that a production execution would hide. The reported 24.8% average
training-time reduction (p.1-2) must therefore not be quoted here as a
modern-framework speedup or used to calibrate ASTRA-sim without checking the
original benchmark schedule and timing decomposition.

Current Ring-3D traces are also communication-focused workload abstractions.
They must not be described as evidence that an end-to-end training-time benefit
survives communication-computation overlap unless the trace explicitly models
that overlap and distinguishes exposed communication time from hidden time.

## 2. Opaque transport loss and the double-lossy-layer risk

**Status: paper-verified behavior plus critical application-semantics threat**
(dblp-paper-detailed-read.md A5, p.12 Algorithm 2). DBLP zero-fills unreceived
chunks and passes no masking metadata to the optimizer beyond that; the paper
never mentions error feedback or interplay with compression. This creates a
second uncontrolled lossy layer when combined with application-level
compression or sparsification that maintains an error-feedback residual. The
optimizer's residual state would not know which network-delivery updates
failed to arrive, so it cannot be assumed to satisfy the assumptions of the
compression/error-feedback method.

This is not merely an accounting issue. It is a semantic gap between a
transport-level “round complete at residual loss bound” and the optimizer's
notion of which parameter coordinates contributed to an update. No current
ASTRA-sim Ring-3D result models gradients, optimizer residuals, compression
state, convergence, or accuracy. It cannot validate or dismiss this risk.

## 3. TCP/UDP control-plane collision and starvation

**Status: critical hypothesis; original queueing details require verification.**
DBLP depends on small reliable control messages such as Probe and Stop to end a
data burst once its tolerance condition is reached. In a shared FIFO datapath
without strict priority, those control packets can queue behind a large UDP
incast or be tail-dropped with it. A delayed Stop weakens or eliminates the
intended early-stop effect because the sender may already have emitted the
remaining data.

Do not infer reliable low latency from control-message size alone. The relevant
property is end-to-end control delivery during the same congestion episode,
including queue class, scheduling, loss behavior, and sender reaction time.
The current Ring-3D provenance-control QP is a modeled 64-byte reliable flow;
it is not evidence that the paper's TCP control traffic avoids starvation on a
commodity FIFO fabric.

## 4. Lossless-fabric mismatch, and the best-effort fabric's own gap

**Status: repository-verified model mismatch; evidence scope depends on the
profile.** A profile that leaves `pfc_enabled` at its default (`true`, e.g.
`smoke_8.json`, `model_100b_256_clos.json`) models reliable RDMA with PFC: its
primary pressure signal is queue buildup and pause propagation, not
data-packet loss. That differs from a DBLP mechanism that reacts to
recoverable data loss, and on such a profile a buffer-pressure episode pauses
traffic and can create head-of-line blocking rather than the data drops a
loss-tolerance protocol assumes.

The flagship comparison profiles (`llama3_70b_*`, `uec_trim_ftd_8`,
`besteffort_baseline_8`, `bts_trim_8`) set `pfc_enabled: false` and model a
UEC-shaped best-effort fabric instead: packet trimming forward-to-destination
removes a congested packet's payload at the switch, and the host recovers with
go-back-N retransmission and no sender congestion control (see
[loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md)). Real data loss
occurs on this fabric, but the recovery model is whole-window go-back-N, not
DBLP's own per-chunk bitmap, and no run models optimizer state, error
feedback, or accuracy. Therefore no current result may claim that DBLP
tolerance prevents PFC tail latency, that DBLP is incompatible with all
RoCEv2 deployments, or that a best-effort-fabric result validates DBLP's own
transport mechanism. Those are distinct mechanisms requiring explicit modeling
and evidence.

**Decision boundary:** the project now requires a loss-tolerant RDMA simulation
path with independent data/control treatment. That direction does not resolve
this flaw by itself and does not make PFC behavior irrelevant. See the
[loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md) for the adopted
transport contract and the evidence required before a change can claim to meet
it.

## 5. Scale, topology, and collective-algorithm external validity

**Status: paper-verified external-validity threat** (dblp-paper-detailed-read.md
A4, p.4). The original evaluation is a three-worker/one-server centralized
All-Reduce prototype using models up to GPT-2-S (125M parameters). That
hub-and-spoke configuration centralizes pressure at a server NIC and does not
establish behavior for decentralized ring or tree collectives. It also does not
establish behavior for a large leaf-spine fabric, a physical switch ring, or
NCCL-style collective scheduling.

Modern large-model execution introduces TP, PP, and DP traffic with different
semantics and dependencies. A lost DP contribution, a tensor-parallel shard,
and a pipeline-parallel activation are not interchangeable “gradient noise.”
The current policy intentionally limits eligibility to typed DP All-Reduce
payloads, but this does not establish the safety or efficacy of discarding a
semantic shard. Any scale or topology conclusion must name the completed
workload, logical collective, physical fabric, and traffic domain.

## 6. CLR observability, detector cost, and proxy validity

**Status: paper-verified and repository-verified limitation** (dblp-paper-
detailed-read.md B6, p.3-4, Eq. 1 and Algorithm 3). The paper detects CLR from
a relative gradient L2-norm drop, checked once per epoch, not continuously.
Current Ring-3D has no gradients. The flagship comparison profiles instead
consume the pinned explicit critical-step schedule `[1, 2, 3, 20]` (see
[CLR schedule evidence](clr-schedule-evidence.md)); a profile that omits
`clr_schedule` falls back to the seeded decay/spike proxy. Either form is an
explicit phase proxy, not a measurement of a model's learning state, and
cannot support claims about the distribution, latency, cost, or prediction
quality of a real-time CLR detector.

The supplied 7/17 note raises a further unresolved concern: online gradient
statistics may not be free or may not generalize across workloads. This is an
open validity question. Do not represent any detector, schedule, or offline
signal as selected or validated by this repository.

## 7. Current ASTRA-sim abstraction cannot adjudicate the application flaws

**Status: repository-verified.** Current Ring-3D selects whole eligible logical
DP All-Reduce payloads with a deterministic hash. A selected payload is replaced
by a reliable 64-byte provenance-control QP whose completion resolves the
original logical callbacks. The model records logical and physical bytes but no
partial chunk delivery, loss mask, retransmission round, residual missing-data
fraction, optimizer state, or accuracy outcome.

This abstraction is suitable only for the stated logical-substitution/incast
question. It cannot establish that DBLP's transport semantics preserve an
optimizer's update, that error feedback remains correct, or that phase-aware
loss is safe for model quality. It also cannot convert a selection probability
into packet loss $q$, loss-window duration $D$, or residual-loss tolerance $P$.

## Unresolved questions, not solution commitments

The following questions remain open and must not be treated as an implementation
roadmap:

- Does the relevant baseline overlap communication and computation, and what
  portion of its reported time is actually exposed network latency?
- What exact loss information reaches the optimizer, and how does it interact
  with any residual/error-feedback state?
- What control-plane queueing and delivery behavior occurs during the target
  congestion episode?
- Which mechanisms dominate tail latency on the target PFC/RoCEv2 configuration:
  pause propagation, data loss, retransmission, congestion control, or another
  effect?
- Which collective domain can tolerate which semantic loss, and under what
  model-quality evidence?
- Can a phase signal be observed at acceptable cost and with predictive value on
  the selected workload?

## Reference materials

These are context sources, not endorsements or selected dependencies:

- [CLR detection working note](https://docs.google.com/document/d/1gcAzBQnbjhj-c_wmEP8kljBrOJlq1WZdoHfXNV1PV5A/edit?tab=t.x12b9brzlcp)
- [Megatron-LM](https://github.com/nvidia/megatron-lm)
- [NCCL](https://github.com/nvidia/nccl)

For original-paper vocabulary, read the [DBLP paper brief](ring-3d-paper-brief.md).
For the current ASTRA-sim mechanism and its supported claims, read the
[research context](ring-3d-research-context.md).
