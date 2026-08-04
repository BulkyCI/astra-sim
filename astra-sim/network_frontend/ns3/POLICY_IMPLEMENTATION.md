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
  `- deterministically selects eligible requests
        |
        v
entry.h::send_flow()
  |- selected: 64-byte protected provenance-control QP
  `- admitted: original foreground payload QP
        |
        v
flow_events.csv + collective_events.csv
```

## Eligibility and deterministic selection

`evaluate_shedding()` considers only operations recognized by
`AstraSim::is_dp_all_reduce_payload()`. In practice that requires the typed
combination `dp` + `CollectivePayload` + `All_Reduce`. Any other request is
ineligible and must use normal transport.

For an eligible request, `stable_operation_hash()` combines the configured
selection seed, run identifier, training step, workload node, message sequence,
source, destination, and tag. The decision is deterministic for the full set
of those values:

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
egress bandwidth while TC_low has traffic — the WDRR guard section 4.1
recommends at 25%, since an unrestricted trimmed class can drive congestion
collapse. Setting the weight to 100 restores strict priority.
A trimmed packet is re-admitted as a new DSCP_TRIMMED arrival, so a congested
TC_med drops it and records `switch_trimmed_queue_drop`; the specification is
explicit that trimmed delivery is not guaranteed.

### Trim size

`min_trim_size_bytes` (default 24, per Table 4-1 for UET over UDP/IP) is the
retained IP payload. The trimmed packet is never larger than the original, and a
packet whose payload is already at or below that bound is dropped instead of
trimmed — a MAY in section 4.1. The UDP length field is not rewritten, so the
destination still learns how many payload bytes were discarded.

### Destination and source behavior

`RdmaHw::Receive()` recognizes a trimmed packet by its DSCP before any protocol
dispatch, so it never reaches `ReceiverCheckSeq()`, never advances receiver
state, and never establishes flow state. The destination replies with a
`UET_TRIMMED` / `UET_TRIMMED_LASTHOP` NACK on the control class (Table 3-61),
and the sender repairs from its cumulative ACK point. A last-hop trim triggers
repair but is not fed to the congestion-control algorithm, because no alternate
path avoids destination incast. Completion still requires all original bytes to
be ACKed; a trim never substitutes for data.

`mode: "bts"` returns the notification directly to the sender. UEC 1.0.3
section 4.1 explicitly excludes that behavior from the specification, so it is a
research-only mode; the loader marks it `uec_conformant: false` and the ns-3
config validator warns. Only `mode: "ftd"` is UET trimming.

This remains a bounded go-back-$N$ repair model. It does not implement selective
retransmission, packet spraying, reorder buffering, or the optional
`DSCP_TRIMMABLE_RTX` codepoint for retransmitted data. Raw trim events and
sender trim counters stay separate from the independent receive-side
`network.data_loss` impairment.
