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

- **Source-reported:** described in the available paper summary or prior review;
  primary-paper verification remains pending because the attached archive is not
  readable in this workspace.
- **Repository-verified:** established by current ASTRA-sim code or checked-in
  experiment documentation.
- **Critical hypothesis:** a technically grounded failure path that requires a
  specific model, measurement, or source inspection before it becomes a result.

## 1. Naive baseline and missing communication-computation overlap

**Status: source-reported validity threat.** The original evaluation is reported
to use a centralized, strictly synchronous stop-and-wait schedule in which
communication begins only after the full backward pass. This differs from
modern DDP/FSDP-style bucketed execution, where gradient communication can
progress while later backward computation continues. The consequence is a
baseline confound: an end-to-end benefit measured with no overlap can include
network time that a production execution would hide. The reported 24.8% average
training-time reduction must therefore not be quoted here as a modern-framework
speedup or used to calibrate ASTRA-sim without checking the original benchmark
schedule and timing decomposition.

Current Ring-3D traces are also communication-focused workload abstractions.
They must not be described as evidence that an end-to-end training-time benefit
survives communication-computation overlap unless the trace explicitly models
that overlap and distinguishes exposed communication time from hidden time.

## 2. Opaque transport loss and the double-lossy-layer risk

**Status: source-reported behavior plus critical application-semantics threat.**
The supplied review states that DBLP discards delayed UDP gradient packets
without exposing the exact missing-coordinate or missing-chunk mask to the
optimizer. If correct, this creates a second uncontrolled lossy layer when
combined with application-level compression or sparsification that maintains an
error-feedback residual. The optimizer's residual state would not know which
network-delivery updates failed to arrive, so it cannot be assumed to satisfy
the assumptions of the compression/error-feedback method.

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

## 4. Lossless-fabric mismatch: RoCEv2, PFC, and head-of-line blocking

**Status: repository-verified model mismatch plus critical external-validity
threat.** The bundled ns-3 backend and current Ring-3D condition model reliable
RDMA with queue/PFC observability. The 70B-class incast uses zero configured
link-error injection, so its primary pressure signal is queue buildup and PFC,
not data-packet loss. This differs from a DBLP mechanism that makes a decision
in response to recoverable data loss.

On a PFC-enabled fabric, a buffer-pressure episode can pause traffic and create
head-of-line blocking rather than produce the data drops assumed by a
loss-tolerance protocol. Whether loss is absent, displaced, or still present is
a fabric- and configuration-specific question. Therefore no current result may
claim that DBLP tolerance prevents PFC tail latency, that DBLP is incompatible
with all RoCEv2 deployments, or that a lossless-fabric result validates a
lossy-Ethernet protocol. Those are distinct mechanisms requiring explicit
modeling and evidence.

**Decision boundary:** the project now requires a loss-tolerant RDMA simulation
path with independent data/control treatment. That direction does not resolve
this flaw by itself and does not make PFC behavior irrelevant. See the
[loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md) for the adopted
transport contract and the evidence required before a change can claim to meet
it.

## 5. Scale, topology, and collective-algorithm external validity

**Status: source-reported external-validity threat.** The supplied review
describes the original evaluation as a three-worker/one-server centralized
All-Reduce prototype using small models such as GPT-2-S. That hub-and-spoke
configuration centralizes pressure at a server NIC and does not establish
behavior for decentralized ring or tree collectives. It also does not establish
behavior for a large leaf-spine fabric, a physical switch ring, or NCCL-style
collective scheduling.

Modern large-model execution introduces TP, PP, and DP traffic with different
semantics and dependencies. A lost DP contribution, a tensor-parallel shard,
and a pipeline-parallel activation are not interchangeable “gradient noise.”
The current policy intentionally limits eligibility to typed DP All-Reduce
payloads, but this does not establish the safety or efficacy of discarding a
semantic shard. Any scale or topology conclusion must name the completed
workload, logical collective, physical fabric, and traffic domain.

## 6. CLR observability, detector cost, and proxy validity

**Status: source-reported and repository-verified limitation.** The paper
summary describes CLR as a relative gradient L2-norm-drop detector. Current
Ring-3D has no gradients and instead consumes a static seeded decay/spike CLR
mask. Its mask is an explicit phase proxy, not a measurement of a model's
learning state. With only three simulated steps in the 70B-class profile, it
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
