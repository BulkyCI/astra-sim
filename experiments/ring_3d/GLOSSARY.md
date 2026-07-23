# Ring-3D glossary and configuration map

Read the [DBLP paper brief](../../docs/agents/ring-3d-paper-brief.md) and
[ASTRA-sim pivot](../../docs/agents/ring-3d-astra-pivot.md) before reusing a
paper term in a profile, report, or code symbol.

## Core terms

| Term | Meaning in this repository | Current 70B condition | Configuration / code | Measured artifact |
| --- | --- | --- | --- | --- |
| `clr_mask` | Immutable step-to-phase input, not simulator-detected gradients | Generated from a seeded decay/spike proxy | `generate_clr_schedule.py` to `clr_mask.csv` | `clr_mask.csv`, `manifest.json` |
| CLR | `is_clr=1` selects the strict policy threshold | Step-dependent | `ExperimentConfig.hh` | `experiment.json`, flow rows |
| `clr_drop_probability` | Current logical-payload selection probability in CLR; **not paper $P_\mathrm{low}$ residual loss** | 0.0 | Generated `experiment.json` | `decision`, `decision_hash` |
| `stable_drop_probability` | Current logical-payload selection probability outside CLR; **not paper $P_\mathrm{high}$ residual loss** | 0.1 | Generated `experiment.json` | `decision`, `decision_hash` |
| $q$ | Packet-loss probability during a proposed data-plane impairment | 0; no loss experiment is active | Would require a transport-loss configuration | Drop/retransmission telemetry, not present |
| $D$ | Duration of a proposed loss/injection window | Unset | Would require a time-window configuration | Window begin/end, not present |
| `microburst_bytes` | Bytes required by one synthetic background RDMA flow | 128 MiB | Profile JSON | Background `flow_events.csv` row |
| `microburst_flow_count` | Number of background flows | 7 | Profile JSON | Background flow rows |
| `microburst_offset_spacing_ns` | Start offset increment among background flows | 0 ns | Profile JSON | `start_time_ns` |
| `provenance_control_bytes` | Physical payload for a selected logical payload's reliable control QP | 64 B | Generated `experiment.json` | `physical_bytes` |
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
| `microburst_enabled` | Enables synthetic background flows | `true` | `false` is the no-incast control |
| `microburst_bytes` | Per-flow offered background bytes | 128 MiB | Required even when disabled |
| `microburst_flow_count` | Background source count | 7 | Must leave a destination rank |
| `microburst_destination_rank` | Shared background destination | 8 | Creates an incast |
| `microburst_offset_spacing_ns` | Flow start staggering | 0 | Zero means simultaneous scheduling |
| `model` | Structural or bucket-sample metadata | 70B FP16 sample | Validated against trace shape |

Policy thresholds are not profile fields. `generate.py` creates them in
`experiment.json`; `run.py --lossless-baseline` replaces all current selection
thresholds with zero for the existing ablation.

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

- Say **selection probability** for the current `clr_drop_probability` and
  `stable_drop_probability` fields.
- Reserve **packet loss** for transport-level data delivery failures.
- Reserve **residual-loss tolerance** for a future DBLP-like stop condition.
- Say **incast** for the finite background RDMA stressor.
- Never call a 64-byte provenance control QP a “dropped packet.”
