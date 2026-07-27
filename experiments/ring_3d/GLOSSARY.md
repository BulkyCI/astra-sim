# Ring-3D glossary and configuration map

Read the [DBLP paper brief](../../docs/agents/ring-3d-paper-brief.md) and
[ASTRA-sim pivot](../../docs/agents/ring-3d-astra-pivot.md) before reusing a
paper term in a profile, report, or code symbol.

## Core terms

| Term | Meaning in this repository | Current 70B condition | Configuration / code | Measured artifact |
| --- | --- | --- | --- | --- |
| `clr_mask` | Immutable step-to-phase input, not simulator-detected gradients | Generated from a seeded decay/spike proxy | `generate_clr_schedule.py` to `clr_mask.csv` | `clr_mask.csv`, `manifest.json` |
| CLR | `is_clr=1` selects the strict policy threshold | Step-dependent | `ExperimentConfig.hh` | `experiment.json`, flow rows |
| `selection_policy.p_low` | Logical-payload selection probability in CLR; **not paper $P_\mathrm{low}$ residual loss** | 0.5% | Profile and generated `experiment.json` | `decision`, `decision_hash` |
| `selection_policy.p_high` | Logical-payload selection probability outside CLR; **not paper $P_\mathrm{high}$ residual loss** | 10% | Profile and generated `experiment.json` | `decision`, `decision_hash` |
| $q$ | Packet-loss probability for `network.data_loss` data-plane impairment | 0 unless a profile explicitly enables `network.data_loss` | `network.data_loss.probability` | `transport_events.csv` injected data drops |
| $D$ | Duration of the configured data-loss window | Unset unless a profile explicitly enables `network.data_loss` | `network.data_loss.start_ns`, `.duration_ns` | `manifest.json`, `network_config.txt` |
| control plane | ACK (`0xFC`), NACK (`0xFD`), congestion notification (`0xFF`), PFC (`0xFE`), and named protocol/recovery control | No configured packet impairment in a lossless profile | Parsed before the QBB data-loss model; generated profiles set strict ACK/NACK priority at hosts and switches | Control attempts/delivery plus queue/drop events in `transport_events.csv` |
| data plane | RDMA UDP payload (`0x11`) subject to the explicit scoped impairment | No loss experiment is active | `network.data_loss` applies only after this wire classification | Data attempts, injected drops, retransmission bytes, and terminal flow telemetry |
| `microburst_bytes` | Bytes required by one synthetic background RDMA flow | 128 MiB | Profile JSON | Background `flow_events.csv` row |
| `microburst_flow_count` | Number of background flows | 7 | Profile JSON | Background flow rows |
| `microburst_offset_spacing_ns` | Start offset increment among background flows | 0 ns | Profile JSON | `start_time_ns` |
| `provenance_control_bytes` | Physical payload for a selected logical payload's reliable control QP | 64 B | Generated `experiment.json` | `physical_bytes` |
| natural buffer drop | Switch MMU-admission or egress-queue rejection under offered load | Native calibration pending | `switch_admission_drop` or `switch_egress_queue_drop` in ns-3 | `data_natural_buffer_drop_count` and control counterpart |
| `decision_hash` | Stable selection hash over seed, run, operation, endpoints, and tag | Deterministic | `ExperimentConfig.hh` | `flow_events.csv` |
| `kDecisionScale` | Integer probability scale for deterministic selection | 1,000,000 | `ExperimentConfig.hh` | N/A |
| logical bytes | Original ASTRA payload size | 1 GiB DP bucket | Trace/request | `logical_bytes` |
| physical bytes | Bytes of the QP modeled by ns-3 | 64 B if selected; full payload otherwise | `entry.h` | `physical_bytes` |

## Profile fields

Profiles are strict JSON input validated by `generate.py`; unknown fields fail.

| Field | Meaning | 70B example | Notes |
| --- | --- | --- | --- |
| `parallelism.tp`, `.pp`, `.dp` | Logical parallel dimensions | 8, 1, 2 | Ranks equal $TP\times PP\times DP$ |
| `steps` | Simulated training steps | 3 | Too short to establish an empirical CLR distribution |
| `compute_duration_us` | Synthetic compute between generated operations | 500 | Workload abstraction, not measured framework time |
| `tp_all_reduce_bytes`, `pp_bytes`, `dp_all_reduce_bytes` | Logical collective payloads | 16 MiB, 0, 1 GiB | Separate from physical transport overhead |
| `seed` | Selection and CLR-mask seed unless overridden | 314159265 | Pair treatment must retain it |
| `network` | Typed Clos/ring topology and packet settings | 400 Gb/s Clos | Network schema is validated in `topology.py` |
| `network.data_loss` | Optional physical data-only impairment plus bounded go-back-$N$ recovery | Absent | Requires probability, time window, scope, RNG stream, retransmission timeout, and retry budget; separate from logical selection thresholds |
| `selection_policy` | Typed low/high logical-admission selection knobs | `p_low=0.005`, `p_high=0.1` | Profile, manifest, and `experiment.json` | Materialized selection probabilities |
| `microburst_enabled` | Enables synthetic background flows | `true` | `false` is the no-incast control |
| `microburst_bytes` | Per-flow offered background bytes | 128 MiB | Required even when disabled |
| `microburst_flow_count` | Background source count | 7 | Must leave a destination rank |
| `microburst_destination_rank` | Shared background destination | 8 | Creates an incast |
| `microburst_offset_spacing_ns` | Flow start staggering | 0 | Zero means simultaneous scheduling |
| `model` | Structural or bucket-sample metadata | 70B FP16 sample | Validated against trace shape |

`selection_policy` is a strict profile object. `compare.py` holds the fixed-low
baseline at `p_low` for both phases, then compares it with a policy that uses
`p_low` in CLR and `p_high` outside CLR. The low value must be in $(0, 1\%]$.

## Background microburst

The generator derives a source/destination list, assigns every flow
`size_bytes=microburst_bytes`, and starts flow $i$ at:

$$
\text{trigger time}+i\times\texttt{microburst\_offset\_spacing\_ns}.
$$

The trigger is the first eligible step-2 DP All-Reduce request. This defines
offered background bytes and alignment, not a fixed burst lifetime. Flow end
time is an ns-3 result affected by queueing, PFC, congestion control, and path
contention.

## Naming rules

- Say **selection probability** for the current `selection_policy.p_low` and
  `selection_policy.p_high` fields.
- Reserve **packet loss** for transport-level data delivery failures.
- `network.data_loss` is physical data-plane impairment. It never changes
  `selection_policy.p_low` or `selection_policy.p_high`, which remain logical
  payload-selection inputs.
- Configured control-impaired loss is always zero, but controls can still be
  delayed or dropped by modeled queue/admission behavior; use
  `transport_events.csv` to distinguish those cases.
- A provenance replacement QP is UDP data on priority group 1, not an ACK,
  NACK, PFC, CNP, or a queue-0 wire-control packet.
- Reserve **residual-loss tolerance** for a future DBLP-like stop condition.
- Say **incast** for the finite background RDMA stressor.
- Never call a 64-byte provenance control QP a “dropped packet.”
- Do not call the existing priority-group mapping a general loss-protected
  control plane; see the [loss-tolerant RDMA decision](../../docs/agents/loss-tolerant-rdma-decision.md).
