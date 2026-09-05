# Ring-3D policy implementation map

This guide describes the **current logical admission-suppression mechanism**.
Read [the paper brief](../../../docs/agents/ring-3d-paper-brief.md) and
[the ASTRA-sim pivot](../../../docs/agents/ring-3d-astra-pivot.md) first: this
code is not DBLP bitmap/retransmission transport.

For physical packet loss, control-plane priority, or RDMA recovery work, read
the [loss-tolerant RDMA decision](../../../docs/agents/loss-tolerant-rdma-decision.md)
first. This file documents neither a packet classifier nor loss isolation.

## Data flow

```text
profile.json + seed + CLR options
        |
        v
experiments/ring_3d/generate.py
  |- clr_mask.csv
  `- experiment.json
        |
        v
ExperimentConfig.hh
  |- validates JSON and parses integer thresholds
  |- validates static CLR mask
  |- sizes the ForgivenessLedger from scale.ranks x scale.steps
  `- deterministically selects eligible requests
        |
        v
entry.h::send_flow()
  |- selected: 64-byte protected provenance-control QP
  |- admitted: original foreground payload QP
  `- registers eligible bytes for the receiving rank and step
        |
        v
flow_events.csv + collective_events.csv
```

## Recovery domain

`selection_policy.domain: recovery` moves the same budget from admission to
recovery. `evaluate_shedding()` then never sheds, so the eligible population is
identical to the admission arm's and the two are matched; instead ns-3 asks the
frontend what to do with each range a switch trimmed.

```text
switch trims a data packet (UEC 1.0.3 section 4.1)
        |
        v
RdmaHw::ReceiveTrim -> ReceiveTrimmedData          [Forgiveness attribute on]
  |- range settled (received or already forgiven): ACK, no charge
  |- range pulled: repeat the PULL at the same priority
  `- range unknown: ask the verdict callback
        |
        v
entry.h::recovery_verdict()   resolves (src, dst, source_port) in the registry
        |
        v
ExperimentConfig.hh::evaluate_forgiveness()
  |- ineligible, unknown step, closed ledger, or exhausted budget -> Pull
  |     (PullPriority instead when the step is critical)
  `- inside budget -> charge the ledger, count the flow's bytes, Forgive
        |
        v
RdmaRxQueuePair absorbs the range; the cumulative ACK carries the sender past
the hole and the next ACK carries FLAG_CNP so the rate cut is still taken
```

The ledger is dense over (receiving rank, step). Its law is
`shed + forgiven <= p(step) * eligible`, with `p` the strict CLR threshold on a
critical step and the permissive one otherwise. Both terms only grow: a range
charged once is never refunded, and a duplicate arriving later takes the
existing old-sequence branch. A step closes when its rank writes its DP
All-Reduce `collective_events` row, after which the step can only be pulled.

The transport is semantics-blind. It supplies a five-tuple, a sequence, and a
length, and learns a verdict; it never reads a step, a phase label, or a
budget. `Forgiveness` requires `SelectiveRetransmission`, because a forgiven
range is absorbed as an accepted out-of-order range, and `RdmaHw::Setup`
aborts otherwise. The generator asserts both that and ftd trimming in
`experiment.json`, and `setup_ns3_simulation` checks the assertion against the
transport ns-3 actually built.

## Eligibility and deterministic selection

`evaluate_shedding()` considers only operations recognized by
`AstraSim::is_dp_all_reduce_payload()`. In practice that requires the typed
combination `dp` + `CollectivePayload` + `All_Reduce`. Any other request is
ineligible and must use normal transport.

For an eligible request, `stable_operation_hash()` combines the configured
selection seed, training step, workload node, message sequence, source,
destination, and tag. `run_id` is parsed and written to the manifest as
provenance but is excluded from the hash: two profiles that differ only by
name must draw the same selection stream, otherwise a renamed profile is
silently unmatched against the arm it is compared with. The decision is
deterministic for the full set of the hashed values:

$$
\texttt{selected} \iff
\texttt{decision\_hash}\bmod1{,}000{,}000 < \texttt{threshold}.
$$

`parse_probability_threshold()` validates a number in $[0,1]$ and converts it
with `llround(probability * kDecisionScale)`. When a CLR mask is configured,
`selection_policy.p_low` is selected in CLR and `selection_policy.p_high` is
selected outside CLR. Profiles require $0 < p_\mathrm{low} \le 1\%$ and
$p_\mathrm{high} \ge p_\mathrm{low}$; paired comparisons use a fixed-low
baseline with both values set to $p_\mathrm{low}$. These are logical-selection
parameters, not DBLP residual-loss bounds. Without a CLR mask, the materialized
per-step selection map is used. Missing CLR rows for an issued step are a hard
configuration error, never a default phase.

## Selected-flow completion contract

`entry.h::send_flow()` always registers the original logical sender callback.
For a selected eligible payload it creates a `ProvenanceControl` flow with:

- physical payload `provenance_control_bytes` (64 B in generated runs);
- priority group `provenance_priority_group` (1);
- original logical payload byte count retained in `FlowRecord`.

This is a logical priority group, not the wire-control queue used by ACK/NACK,
PFC, or CNP. On the wire, the provenance replacement is RDMA UDP data and must
not be described as a transport-control packet or a loss-proof queue class.

When that QP completes, `complete_logical_shed_sender()` resolves the original
send and the receive callback is notified with the original logical byte count
without counting those bytes as physically sent. An admitted foreground flow
instead sends the full original payload on the vnet-mapped priority group
(foreground vnet 0 maps to group 3 in generated configurations).

This preserves ASTRA-sim liveness while modeling logical substitution. It does
not represent partially delivered data, a residual loss fraction, or a
transport failure. Do not alter this contract without designing an explicit
success/failure/residual-data state and updating all callers.

## Telemetry contract

Every issued QP records one terminal `FlowRecord` in `flow_events.csv`: either
`completed`, or `failed` with a terminal reason. Important
fields are:

| Field | Meaning |
| --- | --- |
| `flow_kind` | `foreground_payload`, `provenance_control`, or `background_microburst` |
| `decision` / `admission_eligible` | Selection outcome and whether selection was applicable |
| `logical_bytes` | Original ASTRA payload bytes |
| `physical_bytes` | QP payload modeled by ns-3; not a retransmission-byte counter |
| `decision_hash` | Reproducibility audit key for eligible decisions |
| `start_time_ns`, `end_time_ns` | Simulated QP interval |
| `terminal_outcome` / `failure_reason` | Explicit transport terminal state; failures invalidate primary latency analysis |
| `timeouts` / `cnp_received` | Retransmission-timeout firings that rescheduled data, and rate cuts taken. `cnp_received` is zero unless the profile sets `network.congestion_control.mode: dcqcn` |
| `first_trim_ns` / `first_repair_ns` | Simulated times of the first trim notification received and the first repair packet sent; zero means never |
| `forgiven_bytes` / `forgiven_ranges` | Bytes and trimmed ranges a receiver accepted without ever seeing them. Zero in every admission arm |
| `priority_pulls` | Repairs the receiver asked for ahead of the rest, on a critical step whose budget was exhausted |
| `delivered_bytes` | `physical_bytes` minus `forgiven_bytes`. `physical_bytes` stays the offered figure, because it joins `fct.txt` and denominates W |

`source_port` identifies a live five-tuple, not a flow. ns-3 owns only the
range `[10000, 65535]` per ordered host pair, so the bridge returns a port to
that pair once its queue pair terminates and reuses it later in the run. Join
flow telemetry against `fct.txt` on `(src, dst, source_port, start_time_ns)`.

Reuse is audited, not assumed. A run that models no loss mechanism (no data
loss, no timeout recovery, no trimming, PFC on) has nothing that can drop,
reorder, or resend a packet, so `retransmitted_bytes` and `recovery_events`
must be zero across every flow. A nonzero counter means a packet reached a
queue pair it does not belong to, which is what a source port reused while a
straggler was still in the network would look like. The analyzer rejects the
run rather than reporting it.

`collective_events.csv` is the source for native logical collective latency.
Do not substitute P99 of only admitted QPs: treatment changes that population.

## Change checklist

For a policy, CLR, or completion change, update together:

1. profile/experiment configuration schema and validation;
2. deterministic seeds and generated manifest provenance;
3. runtime state transition and completion/failure semantics;
4. flow and collective telemetry schemas plus analyzer joins;
5. unit tests and a native smoke run where applicable;
6. glossary, research context, validation protocol, and claim language.

For a packet-loss feature, do **not** overload current selection fields. Follow
the [loss-tolerant RDMA decision](../../../docs/agents/loss-tolerant-rdma-decision.md):
classify before loss injection, isolate named control traffic from configured
impairment loss, and use separate typed fields for $q$, $D$, direction/scope,
recovery policy, and recorded terminal outcome.

## Packet trimming (UEC 1.0.3 section 4.1)

The optional `network.packet_trimming` profile object belongs to the physical
transport path, not this logical selection policy. It requires the shared
`network.transport_recovery` timeout/retry budget. A switch trims a packet only
when switch admission or egress queue capacity would reject it. Route failures
remain drops.

### Codepoints and traffic classes

Data packets are marked `DSCP_TRIMMABLE` (CS1) at the NIC and ACKs, NACKs, and
trim NACKs are marked `DSCP_CONTROL` (EF), per Table 3-76. A switch only trims
packets it knows to be trimmable. Trimming rewrites the outer IP header only:
the DSCP becomes `DSCP_TRIMMED` (CS2), or `DSCP_TRIMMED_LAST_HOP` (AF21) when
the egress port is a downlink to a directly attached host, and the IP length is
reduced. ECN bits and TTL are carried through unchanged, and a switch does not
ECN-mark a trimmed packet (section 4.1.1).

The three traffic classes required by section 4.1.4.1 are realized in the
egress scheduler: queue 0 is TC_high, `packet_trimming.trimmed_queue`
(default 2) is TC_med, and data priority groups 1 and 3 are TC_low. TC_med is
drained ahead of TC_low but is capped at `trimmed_queue_weight` percent of the
egress bandwidth while TC_low has traffic: the WDRR guard section 4.1
recommends at 25%, since an unrestricted trimmed class can drive congestion
collapse. Setting the weight to 100 restores strict priority.
A trimmed packet is re-admitted as a new DSCP_TRIMMED arrival, so a congested
TC_med drops it and records `switch_trimmed_queue_drop`; the specification is
explicit that trimmed delivery is not guaranteed.

### Fabric regime

Trimming only fires when a queue can reject a packet, so `network.fabric` is
mandatory alongside `network.packet_trimming` and must disable PFC. UEC 1.0.3
section 3.6.4.5 excludes PFC from best-effort networks, and trimming exists to
replace lossless operation. Disabling PFC also forces `headroom_factor` to 0:
PFC headroom only absorbs packets already in flight when a PAUSE is sent, so
without PFC it is buffer that nothing drains but that still has to fill before
anything can drop.

`data_queue_bytes` and `trimmed_queue_bytes` are the `queue_trimmable` and
`queue_trimmed` drop thresholds of the section 4.1 pseudocode, enforced by
`SwitchMmu::CheckEgressAdmission`. Before this they did not exist; the egress
check was a stub returning true, so the only drop path was the shared ingress
pool and no per-queue threshold was expressible.

A best-effort fabric can drop data whether or not trimming is enabled, so it
also requires `network.transport_recovery`.

### Trim size

`min_trim_size_bytes` (default 24, per Table 4-1 for UET over UDP/IP) is the
retained IP payload. The trimmed packet is never larger than the original, and a
packet whose payload is already at or below that bound is dropped instead of
trimmed (a MAY in section 4.1). The UDP length field is not rewritten, so the
destination still learns how many payload bytes were discarded.

### Destination and source behavior

`RdmaHw::Receive()` recognizes a trimmed packet by its DSCP before any protocol
dispatch, so it never reaches `ReceiverCheckSeq()`, never advances receiver
state, and never establishes flow state. The destination replies with a
`UET_TRIMMED` / `UET_TRIMMED_LASTHOP` NACK on the control class (Table 3-61),
and the sender repairs from its cumulative ACK point (go-back-$N$) by default,
or retransmits only the reported byte ranges when the profile sets
`network.transport_recovery.selective_repair`. A last-hop trim triggers
repair but is not fed to the congestion-control algorithm, because no alternate
path avoids destination incast. Completion still requires all original bytes to
be ACKed; a trim never substitutes for data.

`mode: "bts"` returns the notification directly to the sender. UEC 1.0.3
section 4.1 explicitly excludes that behavior from the specification, so it is a
research-only mode; the loader marks it `uec_conformant: false` and the ns-3
config validator warns. Only `mode: "ftd"` is UET trimming.

The default repair model is bounded go-back-$N$. Setting
`network.transport_recovery.selective_repair` switches to range-based repair
(`SELECTIVE_RETRANSMISSION` in ns-3) with out-of-order acceptance; this is not
a SACK bitmap. Neither mode implements packet spraying, reorder buffering
beyond the accepted out-of-order ranges, or the optional `DSCP_TRIMMABLE_RTX`
codepoint for retransmitted data. Raw trim events and sender trim counters
stay separate from the independent receive-side `network.data_loss`
impairment.
