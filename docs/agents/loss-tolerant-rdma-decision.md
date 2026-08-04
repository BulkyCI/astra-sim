# Decision: model loss-tolerant RDMA transport

- **Status:** adopted research-direction requirement
- **Decision date:** 2026-07-23
- **Owner:** ASTRA-sim Ring-3D research direction
- **Applies to:** future packet-loss and transport experiments; it does not
  retroactively change the meaning of existing lossless-incast results.

## Decision

ASTRA-sim must support a first-class **loss-tolerant RDMA transport** experiment
path. “Lossy transport” in this project means this capability: controlled,
observable data-plane loss plus recovery/liveness semantics, not arbitrary
unclassified packet dropping. The modeled transport boundary must classify
packets before applying an impairment, then give control and data planes
independent queueing and loss semantics:

- **Control plane:** protocol-control packets use a separate high-priority
  queue/class and have zero *configured impairment loss*.
- **Data plane:** payload packets use an independently configurable loss model,
  including a documented loss probability or process, scope, timing, and seed.

“Zero configured impairment loss” is a simulator contract, not a claim that a
physical control packet can never be delayed or dropped by every real fabric.
The simulator must continue to observe and report control-plane queue delay,
drop reasons, and liveness. A high-priority class is likewise a modeled
scheduling contract; it is not proof of a hardware QoS guarantee outside the
specified model.

This is a transport-model decision. It does not select a DBLP implementation,
a recovery algorithm, a packet-spraying design, an optimizer interface, or a
particular UEC/Falcon-compatible NIC behavior.

## Why this decision exists

The supplied July 2026 industry report identifies a strategic shift from
loss-avoidance through PFC toward loss-tolerant Ethernet transports that use
class-aware recovery, selective delivery evidence, and multipath techniques.
It names Ultra Ethernet Transport and Google Falcon as motivating examples.
The report also identifies PFC head-of-line blocking, pause propagation,
deadlock risk, and go-back-$N$ recovery cost as scaling concerns.

That external narrative is **context supplied by the project stakeholder**, not
an independently verified repository source. It motivates the requirement but
does not establish a universal industry adoption claim, a fixed GPU-scale limit,
or an exact UEC/Falcon behavior in this simulator. Any paper, specification, or
hardware claim must cite and verify its primary source separately.

The repository-level motivation is verified: current Ring-3D studies lossless
RDMA incast/PFC pressure with $q=0$, whereas the DBLP research hypothesis
requires an explicit data-loss impairment. The current global receive error
model drops packets before traffic-class handling, so it cannot express
“data-loss adjustable, control-loss zero.” See
[the current backend boundary](ring-3d-research-context.md#bundled-backend-what-it-can-and-cannot-support-now).

## Target transport contract

The clean target is a simulator transport capability with these non-negotiable
properties:

| Contract | Required meaning | Not sufficient |
| --- | --- | --- |
| Pre-loss classification | Every modeled packet is classified as data or a named control type before loss injection | Assigning a priority only after a global error model has already decided to drop it |
| Control isolation | ACK, NACK, recovery, congestion-feedback, PFC, and protocol-control packets have a documented high-priority class and zero configured impairment loss | Assuming a small packet cannot queue or be dropped |
| Data-loss scope | Loss injection applies only to an explicit data-plane class and specifies direction, link/path scope, time window, and deterministic seed | A global static error rate that also affects control traffic |
| Recovery/liveness | A loss experiment records successful recovery, explicit failure, or a bounded timeout outcome | Silently completing an incomplete logical payload |
| Plane-specific observability | Telemetry distinguishes data/control attempts, injected and observed drops, retransmissions, queue delay, and terminal reason | A single flow-completion time with no loss accounting |
| Reproducibility | Profile, generated configuration, loss schedule, classification policy, and RNG inputs are retained | A loss experiment whose only provenance is a command-line override |

The initial control taxonomy must be explicit rather than inferred from byte
size. At minimum it must separately name ACK, NACK, congestion notification,
PFC, and simulator/protocol recovery control. New control types must declare
both their queue/class and loss treatment. Whether a given future protocol uses
all of those types is an experiment-specific fact, not an assumption.

### Packet trimming mode (UEC 1.0.3 section 4.1)

The transport models congestion-induced packet trimming as an explicit
loss-notification mechanism. A switch trims a packet only when switch admission
or egress queue capacity rejects it, and only when the packet carries
`DSCP_TRIMMABLE`. Trimming truncates the payload to `MIN_TRIM_SIZE` and rewrites
the outer IP header only; the retained prefix names the original flow, priority
group, and byte sequence, and the unmodified UDP length reports the discarded
payload size. A trimmed packet never represents delivered payload bytes.

Trimmed packets ride TC_med, a distinct traffic class from both TC_low data and
TC_high control, and they are re-admitted against that queue's threshold, so
they can still be dropped. TC_med is drained ahead of data but is limited to a
configured share of the link (default 25%), so a trimmed-header flood cannot
starve payload. In `ftd` mode — the specified behavior — the trimmed
packet reaches the destination, which returns a `UET_TRIMMED` NACK. `bts` mode
returns the notification directly to the sender; UEC 1.0.3 section 4.1
explicitly excludes back-to-sender from the specification, so it is research
only. Both paths require recovery before cumulative-ACK completion, and RTO
remains the backstop when a trimmed packet is itself lost.

The model uses bounded go-back-$N$ repair and treats a non-last-hop trim as
congestion evidence where the configured control algorithm supports that signal;
a last-hop trim drives repair only. It does not model selective retransmission,
packet spraying, reorder buffering, placeholder bytes, approximate completion,
or the optional `DSCP_TRIMMABLE_RTX` codepoint.
Configured `network.data_loss` remains an independent receive-side impairment;
its counts must never be merged with congestion-triggered trimming.

For data loss, use $q$ only for an explicitly defined data-plane loss
probability or process, and $D$ only for an explicit impairment time window.
Neither is the current whole-payload selection probability, and neither is a
DBLP residual-loss tolerance $P$.

## Initial implementation status

The initial model-level implementation provides the narrow contract below. It
is source-implemented and unit-tested at the profile/generator/analyzer layer,
but it remains **unvalidated as a native loss experiment** until the gate tests
in this decision run successfully:

- `network.data_loss` is typed profile input that materializes the probability,
  time window, link direction scope, endpoint filters, independent RNG stream,
  bounded retransmission timeout/retry budget, and raw transport-event path;
- `QbbNetDevice::Receive()` parses `CustomHeader` before selecting configured
  impairment. Only RDMA UDP payload (`0x11`) can invoke the configured
  data-loss `RateErrorModel`; ACK (`0xFC`), NACK (`0xFD`), PFC (`0xFE`), and CNP
  (`0xFF`) bypass it;
- generated profiles set `ACK_HIGH_PRIO 1` for hosts and switches independently
  of configured impairment, while control queue/admission events are still
  emitted and may reveal non-impairment drops;
- sender timeout recovery reuses the existing go-back-$N$ path. Retry-budget
  exhaustion creates a failed QP telemetry row and terminates the simulation
  instead of manufacturing logical completion; and
- `flow_events.csv`, `transport_events.csv`, analyzer summaries, and reports
  retain recovery counters and terminal outcomes.

This is not selective retransmission, a reorder-buffer transport, per-packet
spraying, or an implementation of UET/Falcon behavior. The legacy global
`ERROR_RATE_PER_LINK` and per-topology error rate are rejected to avoid a
compatibility path that violates classification-before-loss semantics.

## Pre-implementation gap record

The checked-in backend is not yet this target:

1. `ERROR_RATE_PER_LINK` and the topology error-rate field attach ns-3
   `RateErrorModel` instances at QBB receive devices.
2. `QbbNetDevice::Receive()` calls `IsCorrupt(packet)` before it parses the
   `CustomHeader` and determines whether the packet is PFC or another traffic
   type.
3. A configured rate can therefore drop data, ACK, NACK, CNP, and PFC alike.
4. The loss model is static/per-link rather than an explicitly scoped,
   time-bounded data-plane impairment.
5. The RDMA recovery model is gap/NACK based and lacks sender-side timeout
   recovery; a lost tail packet or control packet can stall progress.
6. Ring-3D telemetry has logical/physical QP bytes and completion events, but
   does not yet record per-plane injected drops, retransmitted data bytes,
   control delay, or a terminal recovery reason.

The existing 64-byte provenance-control QP on priority group 1 is not a
solution to this gap. It models logical payload substitution and has a priority
setting, but it is not a general transport-control classifier and does not
shield ACK/NACK/CNP/PFC from the receive error model.

The repository-verified packet path, existing queue/recovery foundations, and
granular configuration, telemetry, liveness, and test gaps are recorded in the
[loss-tolerant RDMA implementation-gap audit](loss-tolerant-rdma-audit.md).
That audit describes current state; it does not choose an implementation.

## Scope and claim boundaries

This decision enables research questions such as:

- how a defined data-plane loss event changes modeled collective tail latency;
- whether a model's recovery/liveness behavior survives that event while its
  control packets receive the configured isolation; and
- how the result differs from an explicitly configured PFC/queue-pressure
  condition.

This decision does **not** establish:

- equivalence to UET, Falcon, RoCEv2, NCCL, or any physical NIC;
- correctness of a future selective-retransmission or packet-spraying design;
- preservation of optimizer/error-feedback semantics or model quality;
- that PFC is obsolete, that all modern fabrics are lossy, or that a control
  priority class eliminates all control-plane latency; or
- a DBLP bounded-loss claim without separately modeling and measuring its
  residual-delivery semantics.

Existing 70B-class Ring-3D results remain a lossless incast plus logical
payload-substitution ablation. They must continue to state $q=0$ and must not
be relabeled as a loss-tolerant transport result.

## Research requirements for future use

Any experiment using this capability must make the following independently
auditable before drawing a result:

1. **Classification:** exact packet/control taxonomy and each class's queue and
   loss treatment.
2. **Impairment:** data-plane $q$ or named process, $D$ or named trigger/window,
   direction/path scope, and deterministic RNG inputs.
3. **Recovery:** modeled sender/receiver state transitions, retry behavior, and
   every terminal completion or failure state.
4. **Telemetry:** attempted, injected-drop, received, retransmitted, and
   terminal counts/bytes by plane and packet type; queue/PFC observations stay
   separate from loss observations.
5. **Comparison:** baseline and treatment retain identical trace, topology,
   phase mask, traffic schedule, and RNG inputs unless the changed item is the
   declared treatment.

A test that merely shows nonzero packet drops is not sufficient. The first
valid demonstration must show that configured loss reaches data packets only,
control injection loss remains zero, and every issued operation has an auditable
terminal outcome. It must also expose any control delay or non-injection drop
rather than treating the class as magically reliable.

## What must not happen

- Do not turn on the current global `ERROR_RATE_PER_LINK` and call the run
  loss-tolerant transport; it violates the plane-separation contract.
- Do not overload logical-selection `p_low`, `p_high`, or the
  provenance-control flow to represent physical loss.
- Do not hide an unresolved recovery stall with a fabricated completion,
  synthetic latency, or omitted seed.
- Do not make UET/Falcon behavior claims from a generic loss model without
  modeling and validating the specific behavior being claimed.
- Do not remove the lossless/PFC condition merely because it is no longer the
  primary loss-tolerant transport direction; it remains a distinct causal
  condition and a required comparison boundary.

## Evidence and review gates

The decision itself is explicit stakeholder direction. Its implementation and
external-validity claims remain conditional. Before a change can be described
as implementing this decision, review must establish:

| Gate | Evidence needed | Falsifies the claimed implementation |
| --- | --- | --- |
| Classification gate | Trace/test proves classification occurs before loss injection | Control packets can be selected by the data loss model |
| Control-isolation gate | Test shows zero configured control impairment loss and records queueing/drops separately | A control packet disappears through the configured loss path |
| Data-loss gate | Seeded test shows only in-scope data packets receive the configured impairment | Out-of-scope data or any control class receives injected loss |
| Liveness gate | Every issued operation reaches a recorded completion or explicit failure | A lost tail/control event leaves unreported pending work |
| Telemetry gate | Raw counters reconcile packet/byte attempts, drops, recovery, and terminal states | Summary metrics cannot explain the terminal outcome |
| Trim semantics gate | A trace shows a trimmed packet carries a missing range, never payload delivery; completed QPs retransmit then ACK all original bytes | A trim advances receiver data state, is counted as delivered bytes, or permits completion without repair |
| Trim class gate | Trimmed packets appear on TC_med, are drained ahead of data and behind control, and lost ones are recorded as `switch_trimmed_queue_drop` | Trimmed packets share the control queue or bypass buffer admission |
| Trim collapse gate | Under sustained incast, TC_med bytes stay within `trimmed_queue_weight` of the link and data goodput does not go to zero | Trimmed headers consume the link while payload starves |

No NIC, switch, UET, Falcon, or DBLP protocol implementation is selected before
these model-level gates pass.

## Related context

- [Current backend limits and valid claims](ring-3d-research-context.md)
- [Verified transport implementation-gap audit](loss-tolerant-rdma-audit.md)
- [DBLP known flaws and validity threats](ring-3d-known-flaws.md)
- [Ring-3D configuration vocabulary](../../experiments/ring_3d/GLOSSARY.md)
- [Current policy implementation map](../../astra-sim/network_frontend/ns3/POLICY_IMPLEMENTATION.md)
- [Ring-3D validation protocol](../../experiments/ring_3d/VALIDATION_PROTOCOL.md)
