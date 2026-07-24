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

Every completed QP records one `FlowRecord` in `flow_events.csv`. Important
fields are:

| Field | Meaning |
| --- | --- |
| `flow_kind` | `foreground_payload`, `provenance_control`, or `background_microburst` |
| `decision` / `admission_eligible` | Selection outcome and whether selection was applicable |
| `logical_bytes` | Original ASTRA payload bytes |
| `physical_bytes` | QP payload modeled by ns-3; not a retransmission-byte counter |
| `decision_hash` | Reproducibility audit key for eligible decisions |
| `start_time_ns`, `end_time_ns` | Simulated QP interval |

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
