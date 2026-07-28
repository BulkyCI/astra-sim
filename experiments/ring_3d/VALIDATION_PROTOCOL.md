# Predeclared empirical-validation protocol

This protocol determines whether the DBLP provenance policy has an empirically supported benefit. It is intentionally written before inspecting the native collective-completion results from the modified simulator.

## Scope and claim boundary

The packet-level claim is limited to ASTRA-sim 2.0's native Ring collectives and bundled ns-3/RDMA model. The policy is eligible only for typed `dp` + `CollectivePayload` + `All_Reduce` traffic. A selected logical payload uses a 64-byte provenance-replacement QP on priority group 1; it is not a packet drop or a wire-control packet. The Llama 3 70B-class condition is a single-gradient-bucket microbenchmark, not an exact framework replay, hardware measurement, or a full-model synchronization result. The 100B 256-card topology studies are structural transformer workloads on two physical fabrics; they are descriptive single-policy runs and do not establish a DBLP effect without a matched baseline.

## Pre-registered primary estimands

For each pair, use the same Chakra traces, topology, policy-selection seed,
static CLR mask, ns-3 RNG seed/run, and microburst schedule. The fixed-low
baseline keeps all policy plumbing enabled but sets both phase selection
probabilities to `p_low`; the phase-aware policy uses `p_low` in CLR and
`p_high` outside CLR. This remains a logical-selection proxy, not a DBLP
residual-loss tolerance comparison.

1. **DP All-Reduce per-rank P99 completion latency**: native collective completion minus native collective issue for every DP All-Reduce rank event.
2. **DP All-Reduce all-rank-span P99**: $\max(end)-\min(start)$ for each `(training_step, workload_node_id)` population across ranks.
3. **Simulated makespan**: maximum rank completion time.

The comparison also records all-QP FCT only as a transport diagnostic and physical-byte reduction relative to foreground logical operations, DP All-Reduce traffic, and total offered traffic. It must not use a P99 of only admitted foreground QPs: selection changes that population and makes it a treatment-conditioned estimand.

Positive paired reductions favor the policy. The report must include the mean, all five paired values, and a two-sided 95% t confidence interval. A confidence interval containing zero is inconclusive, not evidence of a benefit or a regression.

## Required raw-signal validity checks

A run is eligible for the primary analysis only if all checks pass:

- all modeled ranks complete exactly once;
- every issued transport flow has exactly one explicit `completed` or `failed`
     terminal outcome; any failed flow is retained but excludes the run from the
     primary estimands;
- every transport telemetry row joins one ns-3 FCT row by `(src, dst, source_port)`, including physical bytes, start time, and duration;
- every native collective row has nonnegative duration and no duplicate `(domain, collective type, step, workload node, rank)` completion;
- the incast condition records at least one PFC pause/resume interval and a nonzero queue peak;
- the no-incast negative control has no synthetic background-microburst rows and reports its PFC/queue state explicitly;
- selected traffic is exclusively DP CollectivePayload All-Reduce provenance control, with nonzero physical provenance bytes.

An experiment that claims finite-buffer incast loss must additionally retain
`transport_events.csv`, show zero configured data-injection drops, and show at
least one `data_natural_buffer_drop_count` event caused by switch admission or
egress-queue rejection. PFC and a nonzero queue peak demonstrate pressure but
do not, by themselves, demonstrate physical packet loss. Control queue or
admission drops must remain separately reported; strict priority and zero
configured impairment loss do not imply infinite control capacity.

For a profile that enables `network.data_loss`, the run must additionally retain
`transport_events.csv` and establish that at least one in-scope data event was
injected as loss while the configured control-injection-drop count is zero. Any
control queue/admission drop must remain visible as a separate event; it is not
evidence of configured impairment isolation. A run with any failed outcome is
not eligible for the policy primary estimands, but is a valid transport
liveness observation when its raw telemetry is retained.

For a profile that enables `network.packet_trimming`, the run must retain
`transport_events.csv`, identify FTD or BTS mode, and show at least one trim
conversion caused by switch admission or egress-queue rejection. Each trim
conversion represents undelivered original payload bytes—not compact data
delivery—and completed QPs must show repair traffic and ACK-backed completion.
The conversion, recovery-control delivery or natural control drop, sender
recovery work, retransmitted bytes, and any `trim_retry_exhausted` outcome must
remain separately auditable. Trimming and `network.data_loss` are independent:
their counts must not be combined into one loss rate.

Failures are reported as invalid or unavailable data; they are never silently replaced by a QP-envelope proxy.

## Conditions

Run every primary condition with the five fixed paired seeds currently used by `compare.py`.
The historical Phase-1 native reference is the declared exception: it is one
fixed-seed transport-scaling/reproducibility pair, not a multi-seed primary
policy result. The always-on CI Llama condition schedules the five matched pairs
independently, then validates and aggregates their retained artifacts. Each pair
uses GitHub Actions' six-hour job limit, a 330-minute pair guard, and a
9,000-second cap for each of its two ns-3 simulator processes. The 30-minute
difference reserves job time for setup, artifact upload, and failure reporting.
The Llama matrix and the historical reference job have six concurrent jobs;
native integration and the two manual 100B topology studies bring the maximum
simultaneous evaluation count to nine, below the account-level concurrency limit
of ten. The structural studies run only through a manual CI dispatch that selects
**Run 100B structural topology studies**; each reserves a 16,200-second
simulator cap in a 320-minute wrapper budget, preserving 40 minutes of the
six-hour job for setup, reporting, and artifacts.

| Condition | Profile / parameterization | Purpose | Required interpretation |
| --- | --- | --- | --- |
| Negative control | `profiles/no_incast_8.json`, fixed 0.5% versus phase-aware 0.5%/10% selection | Detect policy overhead in the absence of synthetic incast | Primary reductions should be near zero; a material benefit here indicates a confound or implementation error. |
| Congested baseline | `profiles/llama3_70b_16.json`, fixed 0.5% selection | Establish congestion in the CI-scale Llama 3 70B-class condition | Require background traffic, a nonzero queue peak, and at least one completed PFC pause interval. This calibrates pressure, not finite-buffer loss, until natural data drops are observed. |
| Congested policy | `profiles/llama3_70b_16.json`, 0.5% CLR and 10% stable-convergence selection under the fixed decay-and-spike mask | Measure the phase-aware selection proxy under identical congestion input | Run five matched seeds and retain every primary estimand and physical-byte reduction. |
| Historical Phase-1 native reference | `profiles/dblp_phase1_effnet_64dp.json`, fixed 0.8% versus phase-aware 0.8%/40.8% logical selection with the imported four-step CLR mask | Reproduce the old 64-rank, 186-round communication-only trace shape through the native packet/RDMA path | One fixed-seed pair; no microburst, packet loss, or congestion gate. It is not a DBLP residual-loss or accuracy result. |
| 100B Clos topology study | `profiles/model_100b_256_clos.json`, one two-step 256-card structural policy run with the shared step-two incast | Characterize the supplied 100B TP/PP/DP workload on a 16-leaf × 16-spine Clos | Publish the full Markdown report and raw telemetry; interpret as topology/workload characterization, not a policy comparison. |
| 100B physical-ring topology study | `profiles/model_100b_256_ring.json`, the identical two-step workload and incast schedule | Characterize the same workload on the host-attached 256-switch bidirectional ring | Publish the full Markdown report and raw telemetry; do not confuse physical Ring routing with the logical Ring collective or claim a policy comparison. |
| DP payload scale | 128 MiB, 256 MiB, 512 MiB, and 1 GiB representative buckets | Establish whether eligible traffic is large enough to relieve the bottleneck | Maintain topology and background schedule within each rate block. |
| Incast-load scale | 0, 2, 4, and 7 simultaneous sources; fixed 128 MiB source payload | Identify onset and severity of congestion | Report queue/PFC and primary outcomes at every point, including controls with no PFC. |

The checked-in no-incast profile is the executable negative-control configuration. The checked-in Llama 3 70B-class profile is the always-on two-step congested CI event window: its step-two incast is an exogenous stressor, not framework-derived traffic. Its 10 μs queue-sampling cadence is a bounded observability control, not a transport timing parameter. The remaining grid must be materialized as explicitly named profile files or an immutable generated profile manifest before execution, and that manifest must be retained with the run artifacts.

## Causal-load criterion

A global random DP policy cannot substantially relieve an independent background incast if its maximum physical-byte reduction is negligible relative to the background bytes. Before claiming a latency benefit, calculate

$$
\frac{\text{baseline DP physical bytes} - \text{policy DP physical bytes}}
     {\text{background physical bytes}}.
$$

If this ratio is small at every rate, a null primary result is expected and valid. It is not evidence that the congestion generator failed. The CI condition's 128 MiB × 7 background incast establishes real congestion only after its raw queue/PFC gate passes; it is not, by itself, proof that 10% global DP selection improves tail latency.

To establish a causal policy effect, one of the following must hold:

1. scale eligible DP traffic so its selected-byte reduction is comparable to the bottleneck load; or
2. introduce a separately named, congestion-aware DP-only policy and compare it
     with both the global-hash policy and the fixed-low baseline.

The second option is a new policy, not a retroactive reinterpretation of the current global hash rule.

## Decision rules

- **Validated congestion only:** raw PFC/queue gates pass, but primary CIs span zero or byte relief is causally negligible. Report congestion calibration, not a policy benefit.
- **Pressure without finite-buffer loss:** PFC/queue gates pass but no natural
     data-buffer drop is observed. Report a lossless-incast pressure result; do
     not call it a finite-buffer-loss result.
- **Supported policy benefit:** raw gates pass; the pre-registered primary logical-collective metric improves with a CI excluding zero at one or more predeclared scale/rate points; the byte-relief ratio makes the result causally plausible; and the no-incast control is near zero.
- **No supported benefit:** valid runs fail the preceding criterion. Preserve and publish the null result and all artifacts.

All output bundles must retain generated profiles, native collective events, flow events, FCT, PFC, queue traces, summary JSON, comparison JSON, and this protocol revision.
