# Loss-tolerant RDMA readiness audit

- **Audit date:** 2026-07-23
- **Method:** static read-only inspection of the pre-implementation
  project-owned Ring-3D/ns-3 bridge and bundled ns-3 QBB/RDMA backend; no loss
  experiment was run.
- **Decision assessed:** [loss-tolerant RDMA transport](loss-tolerant-rdma-decision.md)
- **Scope:** controlled lossy data-plane semantics with a clean, high-priority,
  zero-*configured-impairment-loss* control plane.

## Audited baseline

At audit time, the simulator did **not** support the adopted transport contract.
It can inject static, independent packet loss on QBB receive devices, and it
has partial control prioritization plus NACK-driven go-back-$N$ recovery. Those
pieces are not composable into loss-tolerant data plus isolated control:

- loss is decided before packet classification, so the same error model can
  drop data, ACK, NACK, PFC, and standalone CNP packets;
- Ring-3D exposes no typed data-loss configuration, trigger/window, direction,
  or packet-class policy, and emits topology error rates of zero;
- ACK/NACK priority is incomplete across hosts and switches; the checked-in
  Ring-3D network configuration sets `ACK_HIGH_PRIO 0`;
- recovery has no sender retransmission timeout, no receiver gap timer, no
  out-of-order buffer, and no selective acknowledgment state; a dropped tail
  data packet can leave a QP pending indefinitely;
- result telemetry covers completed QPs only. It does not account for packet
  attempts, injection drops, queue drops, recovery work, control delay, or a
  terminal failure reason.

The result is a valid lossless-incast/PFC model with an unsafe global loss knob,
not a clean loss-tolerant RDMA model. Do not enable `ERROR_RATE_PER_LINK` and
interpret the output as satisfying the adopted decision.

## Post-audit implementation update — native validation pending

The source tree now contains an initial model-level implementation of the
audited gaps. It is not a retroactive result claim: no loss-configured native
simulation has yet supplied the gate evidence below.

| Decision gate | Source implementation | Remaining evidence |
| --- | --- | --- |
| Classify before loss | QBB parses `CustomHeader` before invoking its new data-loss error model | Native trace proves only `0x11` reaches the configured loss branch |
| Zero configured control loss | ACK, NACK, PFC, and CNP bypass the configured data-loss model | Loss-configured run shows zero control injection drops |
| Priority control | Loss configuration propagates `ACK_HIGH_PRIO 1` to NIC and switch paths | Queue/drop trace confirms the actual modeled behavior under load |
| Scoped reproducible loss | Typed `network.data_loss` materializes window, direction scope, filters, and RNG stream | Deterministic two-run check verifies the retained schedule |
| Recovery/liveness | Timeout-driven go-back-$N$ retries yield completed or retry-exhausted QP outcomes | Recovery-success and retry-exhaustion scenarios run natively |
| Observability | Raw transport events and terminal/recovery flow fields are summarized and reported | Event counts reconcile with a native loss run |
| UEC-style trimming | Switch admission/egress rejections can become FTD/BTS explicit-loss metadata with bounded sender repair | Native congestion run proves no trim metadata advances receiver data state and every trimmed QP repairs or fails explicitly |

The rest of this document is the detailed **pre-implementation** evidence
record. Its source-line references intentionally document the former unsafe
path and should not be read as a description of the post-audit implementation.

## Gate assessment

| Decision gate | Current status | Static evidence |
| --- | --- | --- |
| Classify before loss | **Fail** | QBB checks `ReceiveErrorModel` before `CustomHeader` parsing |
| Zero configured control-loss | **Fail** | One `RateErrorModel` decides all receive packets before protocol dispatch |
| Separate high-priority control | **Partial / fail** | NIC control queue exists; switch ACK/NACK elevation is disabled by the generated configuration and not wired from that setting |
| Adjustable scoped data loss | **Fail** | Only static global/per-link rate; no typed scope, direction, trigger, or window |
| Recovery and liveness | **Fail** | NACK recovery exists, but no timeout can recover tail loss or a missing control signal |
| Plane-specific observability | **Fail** | PFC, aggregate queue, FCT, and completed-flow outputs lack per-plane loss/recovery accounting |
| Reproducible impairment | **Partial** | ns-3 seed/run are retained, but no named loss schedule or independent loss-process provenance exists |

## Current packet path

### Loss is applied before classification

For every QBB receive event,
[`QbbNetDevice::Receive()`](../../extern/network_backend/ns-3/src/point-to-point/model/qbb-net-device.cc#L357-L392)
first calls `m_receiveErrorModel->IsCorrupt(packet)`. Only after a packet
survives does it parse `CustomHeader`, recognize PFC (`0xFE`), or dispatch the
remaining packet to RDMA. Therefore a configured error model cannot distinguish
payload from control traffic at the point where it makes the drop decision.

The backend constructs ns-3 `RateErrorModel` instances in
[`SetupNetwork()`](../../extern/network_backend/ns-3/scratch/common.h#L616-L647)
using `ERROR_UNIT_PACKET`. The rate comes from the global
`ERROR_RATE_PER_LINK` or the fifth field of a topology-link declaration. This
is a receive-side impairment on each installed QBB device; it is not a
packet-class-aware or workload-event-aware loss process.

[`QbbNetDevice::TransmitStart()`](../../extern/network_backend/ns-3/src/point-to-point/model/qbb-net-device.cc#L467-L510)
does not apply an equivalent configurable egress-loss process. A channel send
can report failure, but the current `QbbChannel` schedules every transmission
to its peer and returns `true`; see
[`QbbChannel::TransmitStart()`](../../extern/network_backend/ns-3/src/point-to-point/model/qbb-channel.cc#L80-L107).

### Current wire taxonomy

The backend already recognizes protocol values after a packet survives the
error model:

| Wire type | Protocol | Receive destination | Current loss treatment |
| --- | --- | --- | --- |
| RDMA payload | `0x11` UDP | `RdmaHw::ReceiveUdp()` | Same global/per-link receive model as every other type |
| ACK | `0xFC` | `RdmaHw::ReceiveAck()` | Same model |
| NACK | `0xFD` | `RdmaHw::ReceiveAck()` | Same model |
| PFC | `0xFE` | QBB pause/resume state | Same model, before PFC parsing |
| Standalone CNP | `0xFF` | `RdmaHw::ReceiveCnp()` | Same model |

The dispatch occurs in
[`RdmaHw::Receive()`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc#L486-L498).
The protocol information needed for a future classifier is present, but no
packet-class object, class-to-loss policy, or class-to-telemetry mapping exists.

The Ring-3D `ProvenanceControl` flow is not a wire-level ACK/NACK/PFC class. It
is a 64-byte ASTRA-sim logical-substitution QP that becomes ordinary RDMA UDP
payload on the wire. Its priority group does not make it a general lossless
transport control signal; see
[`send_flow()`](../../astra-sim/network_frontend/ns3/entry.h#L214-L253).

## Control-plane queue and pause behavior

### NIC behavior is useful but insufficient

The NIC has a dedicated `m_ackQ` in
[`RdmaEgressQueue`](../../extern/network_backend/ns-3/src/point-to-point/model/qbb-net-device.cc#L70-L168).
It is chosen before data QPs whenever nonempty, and generated ACK/NACK packets
are enqueued through `RdmaEnqueueHighPrioQ()` in
[`RdmaHw::ReceiveUdp()`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc#L341-L391).
NIC-generated PFC also uses that queue.

This priority is conditional, not a clean control-plane contract:

- `RdmaEgressQueue::ack_q_idx` selects the pause bit that can block `m_ackQ`.
  The default generated configuration writes `ACK_HIGH_PRIO 0`, and setup maps
  that to queue/priority group 3; see
  [`write_network_config()`](../../experiments/ring_3d/generate.py#L780-L803)
  and [`SetupNetwork()`](../../extern/network_backend/ns-3/scratch/common.h#L799-L806).
  Thus a pause of group 3 can block host control transmission despite the
  separate queue being scheduled before data when unpaused.
- `m_ackQ` is a shared high-priority queue for generated ACK/NACK and NIC PFC,
  not an explicit taxonomy with separate capacity, delay, or drop reporting by
  control type.
- RX impairment still precedes this transmit priority. A high-priority control
  packet can be dropped when it reaches the next QBB receiver.

### Switch behavior does not complete the control guarantee

Switch queue 0 is strict priority in
[`BEgressQueue::DoDequeueRR()`](../../extern/network_backend/ns-3/src/network/utils/broadcom-egress-queue.cc#L170-L221).
[`SwitchNode::SendToDev()`](../../extern/network_backend/ns-3/src/point-to-point/model/switch-node.cc#L107-L139)
always assigns PFC and standalone CNP to queue 0, but assigns ACK/NACK to queue
0 only when its `AckHighPrio` attribute is true.

The generated `ACK_HIGH_PRIO` network setting is parsed and used only to select
the **host** `RdmaEgressQueue::ack_q_idx`; no inspected `common.h` call binds
it to each switch's `AckHighPrio` attribute. That switch attribute defaults to
zero in
[`SwitchNode::GetTypeId()`](../../extern/network_backend/ns-3/src/point-to-point/model/switch-node.cc#L18-L42).
Consequently, the current Ring-3D configuration provides no verified
end-to-end strict-priority path for ACK/NACK across switches.

Queue 0 is not automatically non-dropping. Switch admission accounting excludes
queue 0, but the underlying `BEgressQueue` still has an aggregate byte limit and
can reject an enqueue; see
[`BEgressQueue::DoEnqueue()`](../../extern/network_backend/ns-3/src/network/utils/broadcom-egress-queue.cc#L152-L168).
`SwitchNode::SendToDev()` does not check the boolean returned by `SwitchSend()`.
No current experiment artifact attributes a queue rejection to packet type,
priority, or terminal QP outcome.

## Data-loss scope and configuration gaps

### No profile-to-backend loss contract

Ring-3D profile parsing accepts only topology, payload, and queue-monitor
settings in the network object; unknown network keys fail in
[`load_network()`](../../experiments/ring_3d/topology.py#L131-L194).
Topology serialization writes a hard-coded fifth-field link error rate of zero
for every link in
[`TopologyLayout::write()`](../../experiments/ring_3d/topology.py#L89-L101).
The generated network configuration separately hard-codes
`ERROR_RATE_PER_LINK 0.0000`.

There is therefore no profile or generated experiment artifact that owns:

- data-plane loss probability/process $q$;
- impairment duration $D$, start/end time, workload trigger, or phase binding;
- directionality or asymmetric per-direction behavior;
- link, path, rank-pair, operation, or packet-class scope;
- control-class policy or priority mapping; or
- a loss-process identifier and independent RNG-stream provenance.

The global/per-link error rate can express only an always-active, packet-level
Bernoulli-like receive impairment. It is insufficient to distinguish a
transient loss episode from a background loss rate or queue overflow.

### Configuration order blocks simple ownership

The executable sets ns-3 RNG seed/run, then calls `setup_ns3_simulation()`;
only afterward does it load `experiment.json` through `configure_experiment()`.
See
[`AstraSimNetwork::main()`](../../astra-sim/network_frontend/ns3/AstraSimNetwork.cc#L354-L399).
QBB error models and devices are therefore created before the current
experiment-policy JSON exists. A future data/control loss contract cannot be
implemented merely by adding a field to the existing experiment JSON without
also defining how the backend receives it before device construction.

The ns-3 seed and run are recorded by
[`run.py`](../../experiments/ring_3d/run.py#L57-L103) and installed with
`RngSeedManager` before setup. `RateErrorModel` also pins a random-variable
stream in
[`SetupNetwork()`](../../extern/network_backend/ns-3/scratch/common.h#L612-L644).
Thus packet loss is not unseeded; it is tied to the run-level ns-3 RNG state.
What is missing is named loss-process configuration and provenance separate
from generic ns-3 randomness, not a seed entirely.

## Recovery, ordering, and liveness gaps

### Present recovery behavior

A receiver accepts only the next expected payload sequence. It sends ACKs at
configured milestones/chunk boundaries and sends a NACK when it later observes
an out-of-order sequence beyond the first gap; see
[`ReceiverCheckSeq()`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc#L502-L530).
`ReceiveAck()` processes both ACK and NACK, and NACK recovery resets
`snd_nxt` to `snd_una` in
[`RecoverQueue()`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc#L438-L485)
and
[`RecoverQueue()`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc#L544-L546).
This is go-back-$N$ retransmission from the last cumulative acknowledgement.

The model includes a NACK **suppression** interval, not a retransmission
**timeout**. It has no QP field for unacknowledged-packet deadline, retry budget,
recovery reason, or terminal failure state; the QP state is visible in
[`RdmaQueuePair`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-queue-pair.h#L14-L105)
and
[`RdmaRxQueuePair`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-queue-pair.h#L107-L135).

### Loss cases that cannot terminate cleanly

| Event | Current result | Why it blocks loss-tolerant semantics |
| --- | --- | --- |
| Interior data packet lost, later packet arrives | Receiver can NACK; sender can go back to `snd_una` | May recover, but retransmits the outstanding suffix rather than missing data only |
| Final data packet lost | Receiver sees no later sequence, so it emits no NACK | No receiver gap timer or sender timeout detects the missing tail |
| ACK/NACK lost | Sender has no timeout/duplicate-ACK fallback | QP can wait without an explicit terminal failure |
| Out-of-order delivery from multipath | Receiver discards the out-of-order packet and requests first gap | No reorder buffer or selective acknowledgement preserves received data |
| Queue-overflow/PFC-control loss | No per-type terminal state or source attribution | Cannot tell data impairment from control/queue pathology |

Completion is ACK-driven: `RdmaQueuePair::IsFinished()` requires
`snd_una >= m_size` in
[`RdmaQueuePair`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-queue-pair.cc#L150-L189).
The frontend records a flow only from `qp_finish()`, after a completed QP. A
stalled QP remains in `active_flow_registry`; see
[`entry.h`](../../astra-sim/network_frontend/ns3/entry.h#L330-L379).

The process-wide tracker logs periodic liveness checkpoints but keeps scheduling
them while work remains. It reports noncompletion only after the simulator
returns; see
[`NS3BackendCompletionTracker`](../../astra-sim/network_frontend/ns3/AstraSimNetwork.cc#L35-L112)
and
[`main()`](../../astra-sim/network_frontend/ns3/AstraSimNetwork.cc#L400-L410).
With a stalled packet flow, an external wall-clock timeout may terminate the
runner before telemetry finalization. This is not an explicit simulated
transport failure state.

### Multipath fidelity is absent

The switch chooses one next hop by hashing the flow's addresses and ports in
[`SwitchNode::GetOutDev()`](../../extern/network_backend/ns-3/src/point-to-point/model/switch-node.cc#L65-L91).
Packets of a QP retain that tuple, so the current model is flow-pinned ECMP.
There is no per-packet spraying, receiver reorder buffer, or selective recovery
state. These features are not required to meet the minimal data/control
separation decision, but their absence limits any future claim about UET/Falcon
multipath or out-of-order transport behavior.

### Congestion-notification nuance

The backend does not have a clean standalone CNP pipeline. `ReceiveCnp()` can
consume protocol `0xFF`, while `CheckandSendQCN()` is declared in
[`rdma-hw.h`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.h#L60-L77)
but has no inspected implementation or call site. In the active data path,
receiver-side ECN information is piggybacked into generated ACK/NACK headers
through `seqh.SetCnp()` in
[`ReceiveUdp()`](../../extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc#L341-L391).
That ACK-borne control is still subject to the global receive error model and
the switch-priority gap above.

## Telemetry and analysis gaps

### Signals that exist but are not retained as plane-aware evidence

QBB devices expose drop and queue trace sources, including `QbbDrop` and PHY RX
loss; see
[`QbbNetDevice::GetTypeId()`](../../extern/network_backend/ns-3/src/point-to-point/model/qbb-net-device.cc#L200-L227)
and the loss branch in
[`Receive()`](../../extern/network_backend/ns-3/src/point-to-point/model/qbb-net-device.cc#L357-L375).
The inspected setup connects only PFC callbacks for the experiment artifacts;
see
[`SetupNetwork()`](../../extern/network_backend/ns-3/scratch/common.h#L690-L705).
The existing signals are not connected to a packet-type-aware loss ledger.

The available outputs are:

| Artifact | What it records | Missing for the adopted contract |
| --- | --- | --- |
| `flow_events.csv` | Completed logical QP kind, configured priority group, logical/physical QP bytes, and end time | Packet/control type, attempts, injected drops, queue drops, retransmit bytes, recovery reason, failure outcome |
| `fct.txt` | Completed QP size/start/duration | Retransmission work and missing/failed QPs |
| `pfc.txt` | Pause/resume event, node, interface, type | Packet/control causality and priority-group identity |
| `qlen.txt` | Sampled aggregate switch-port queue bytes | Per-priority occupancy and control queue delay |
| completion tracker logs | Pending count / rank progress | A typed QP terminal failure and causal loss history |

`qp_finish()` overwrites `FlowRecord::physical_bytes` with `q->m_size` at
completion; see
[`entry.h`](../../astra-sim/network_frontend/ns3/entry.h#L342-L379).
That is the original QP payload, not total transmitted bytes after go-back-$N$
recovery. The analyzer's FCT join intentionally validates this completed-QP
view; see
[`analyze.py`](../../experiments/ring_3d/analyze.py#L229-L280). It cannot
reconcile loss and recovery because neither appears in the source artifacts.

The queue monitor sums all eight priority groups on a switch port before
writing a sample; see
[`monitor_buffer()`](../../extern/network_backend/ns-3/scratch/common.h#L158-L207).
It cannot establish whether a high-priority control class was delayed, isolated,
or congested. The PFC callback signature has only pause/resume type, so the
checked-in `pfc.txt` format also lacks an affected priority-group identifier.

## Tests and ownership gaps

The project-owned Python tests validate profile materialization, completed-flow
analysis, reports, and paired congestion gates. They do not exercise physical
loss. The checked-in generator fixes loss rates at zero, and no inspected
Ring-3D test config enables or asserts `ERROR_RATE_PER_LINK`, control isolation,
packet classification, retry behavior, tail loss, or deterministic loss traces.

No focused QBB/RDMA loss-recovery test was found under the bundled backend's
point-to-point test paths during this audit. The backend's generic P2P tests do
not substitute for a data-plane-loss/control-plane-isolation test.

The code ownership boundary is currently split:

| Area | Current owner/path | Missing owned contract |
| --- | --- | --- |
| Profile and artifacts | `experiments/ring_3d/` | Typed loss scenario, deterministic schedule/provenance, paired-treatment controls |
| Experiment policy and logical flow telemetry | `astra-sim/network_frontend/ns3/` | Plane-aware terminal/recovery accounting and clear handoff to backend setup |
| Packet classification, loss, queues, PFC, recovery | `extern/network_backend/ns-3/` | Class-before-loss semantics, control policy, loss scope, recovery/liveness state, packet evidence |
| Analysis and reporting | `experiments/ring_3d/analyze.py` | Reconciliation of packet attempts, drop causes, recovery, failures, and per-plane delay |

No implementation should paper over one missing owner by overloading the current
logical suppression fields or provenance-control QP.

## Missing semantics checklist

The audit identifies these required semantics as absent, incomplete, or
unmeasured. This is a gap list, not an implementation prescription.

1. A packet classification decision made before any configurable loss decision.
2. A named control taxonomy whose queue class, pause behavior, configured-loss
   treatment, and non-injection-drop observation are explicit.
3. A data-plane impairment definition with $q$, $D$, scope, direction, trigger,
   seed/provenance, and interaction with queue/PFC loss stated separately.
4. Control priority that holds end-to-end across host and switch queues, rather
   than only in an unpaused NIC queue.
5. A recovery/liveness state machine that can terminate tail loss, missing
   acknowledgements, retry exhaustion, and simulator stop without fabricating a
   successful QP.
6. An ordering model appropriate to any claimed routing model; current recovery
   assumes in-order flow delivery and discards out-of-order data.
7. Packet-level evidence that distinguishes configured impairment drops,
   queue/admission drops, control delay, retransmission work, and terminal
   outcome by plane and type.
8. Profile/configuration timing that supplies the loss contract before backend
   devices and error models are instantiated.
9. Deterministic tests that prove all prior items, including control zero
   configured impairment loss and data-only loss under identical seeds.

## Claims this audit supports

This audit supports only code-level statements about the checked-in ASTRA-sim
and bundled ns-3 model. It does not prove a physical RoCEv2, UET, Falcon, or
NCCL behavior, and it does not choose a recovery algorithm or hardware design.

For the adopted requirement and its model-level evidence gates, read the
[loss-tolerant RDMA decision](loss-tolerant-rdma-decision.md). For the current
research claim boundary, read the
[Ring-3D research context](ring-3d-research-context.md).
