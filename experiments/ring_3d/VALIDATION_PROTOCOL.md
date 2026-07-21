# Predeclared empirical-validation protocol

This protocol determines whether the DBLP provenance policy has an empirically supported benefit. It is intentionally written before inspecting the native collective-completion results from the modified simulator.

## Scope and claim boundary

The packet-level claim is limited to ASTRA-sim 2.0's native Ring collectives and bundled ns-3/RDMA model. The policy is eligible only for typed `dp` + `CollectivePayload` + `All_Reduce` traffic. A selected logical payload uses a 64-byte protected provenance-control QP; it is not a packet drop. The results do not claim an exact framework replay, hardware measurement, or a performance benefit at 256-rank, full-resolution ns-3 scale.

## Pre-registered primary estimands

For each pair, use the same Chakra traces, topology, policy-selection seed, ns-3 RNG seed/run, and microburst schedule. The lossless baseline keeps all policy plumbing enabled but sets every selection threshold to zero.

1. **DP All-Reduce per-rank P99 completion latency**: native collective completion minus native collective issue for every DP All-Reduce rank event.
2. **DP All-Reduce all-rank-span P99**: $\max(end)-\min(start)$ for each `(training_step, workload_node_id)` population across ranks.
3. **Simulated makespan**: maximum rank completion time.

The comparison also records all-QP FCT only as a transport diagnostic and physical-byte reduction relative to foreground logical operations, DP All-Reduce traffic, and total offered traffic. It must not use a P99 of only admitted foreground QPs: selection changes that population and makes it a treatment-conditioned estimand.

Positive paired reductions favor the policy. The report must include the mean, all five paired values, and a two-sided 95% t confidence interval. A confidence interval containing zero is inconclusive, not evidence of a benefit or a regression.

## Required raw-signal validity checks

A run is eligible for the primary analysis only if all checks pass:

- all modeled ranks complete exactly once;
- every transport telemetry row joins one ns-3 FCT row by `(src, dst, source_port)`, including physical bytes, start time, and duration;
- every native collective row has nonnegative duration and no duplicate `(domain, collective type, step, workload node, rank)` completion;
- the incast condition records at least one PFC pause/resume interval and a nonzero queue peak;
- the no-incast negative control has no synthetic background-microburst rows and reports its PFC/queue state explicitly;
- selected traffic is exclusively DP CollectivePayload All-Reduce provenance control, with nonzero physical provenance bytes.

Failures are reported as invalid or unavailable data; they are never silently replaced by a QP-envelope proxy.

## Conditions

Run every condition with the five fixed paired seeds currently used by `compare.py`.

| Condition | Profile / parameterization | Purpose | Required interpretation |
| --- | --- | --- | --- |
| Negative control | `profiles/no_incast_8.json`, policy 0% versus policy | Detect policy overhead in the absence of synthetic incast | Primary reductions should be near zero; a material benefit here indicates a confound or implementation error. |
| Congested baseline | `profiles/incast_8.json`, 0% selection | Establish congestion | Require queue peak and at least one completed PFC pause interval. |
| Congested policy | `profiles/incast_8.json`, 5%, 10%, and 20% selection | Measure dose response under identical congestion input | Report the primary estimands and physical byte reductions at every rate; do not select a rate after looking at outcomes. |
| DP payload scale | 128 KiB, 1 MiB, 8 MiB, and 32 MiB DP All-Reduce payloads | Establish whether eligible traffic is large enough to relieve the bottleneck | Maintain topology and background schedule within each rate block. |
| Incast-load scale | 0, 2, 4, and 7 simultaneous sources; fixed 32 MiB source payload | Identify onset and severity of congestion | Report queue/PFC and primary outcomes at every point, including controls with no PFC. |

The checked-in no-incast profile is the executable negative-control configuration. The remaining grid must be materialized as explicitly named profile files or an immutable generated profile manifest before execution, and that manifest must be retained with the run artifacts.

## Causal-load criterion

A global random DP policy cannot substantially relieve an independent background incast if its maximum physical-byte reduction is negligible relative to the background bytes. Before claiming a latency benefit, calculate

$$
\frac{\text{baseline DP physical bytes} - \text{policy DP physical bytes}}
     {\text{background physical bytes}}.
$$

If this ratio is small at every rate, a null primary result is expected and valid. It is not evidence that the congestion generator failed. The current 32 MiB × 7 background incast is therefore a **stress-calibration** workload, not a proof that 10% global DP selection should improve tail latency.

To establish a causal policy effect, one of the following must hold:

1. scale eligible DP traffic so its selected-byte reduction is comparable to the bottleneck load; or
2. introduce a separately named, congestion-aware DP-only policy and compare it with both the global-hash DBLP policy and the lossless baseline.

The second option is a new policy, not a retroactive reinterpretation of the current global hash rule.

## Decision rules

- **Validated congestion only:** raw PFC/queue gates pass, but primary CIs span zero or byte relief is causally negligible. Report congestion calibration, not a policy benefit.
- **Supported policy benefit:** raw gates pass; the pre-registered primary logical-collective metric improves with a CI excluding zero at one or more predeclared scale/rate points; the byte-relief ratio makes the result causally plausible; and the no-incast control is near zero.
- **No supported benefit:** valid runs fail the preceding criterion. Preserve and publish the null result and all artifacts.

All output bundles must retain generated profiles, native collective events, flow events, FCT, PFC, queue traces, summary JSON, comparison JSON, and this protocol revision.
