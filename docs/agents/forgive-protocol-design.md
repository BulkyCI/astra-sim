# Forgive protocol: design and build plan

Design for recovery-domain bounded loss ("forgiveness") on the trimming
transport, plus the side questions the regime map needs (congestion
control knob, tail telemetry, matched-sweep fixes). C++17 (root
CMakeLists), Python 3.11 (pyproject). Written 2026-09-05 from the BLT
plan of 2026-08-22 and the run #117 findings in
[next-steps-after-run-117.md](next-steps-after-run-117.md).

## 1. Domain model

Receiver side, ns-3 (semantics-blind):

```cpp
enum class RecoveryVerdict : uint8_t { Pull = 0, Forgive = 1, PullPriority = 2 };
// Callback set by the frontend. ns-3 never reads step, CLR, or budget.
using VerdictCallback = Callback<uint8_t, uint32_t /*sip*/, uint32_t /*dip*/,
    uint16_t /*sport*/, uint16_t /*dport*/, uint64_t /*seq*/, uint32_t /*len*/>;

struct RdmaRxQueuePair {            // existing, gains:
  std::map<uint64_t, uint64_t> m_pulled_ranges;  // [start,end) with a PULL outstanding; pruned below ReceiverNextExpectedSeq
  uint64_t m_forgiven_bytes;  uint32_t m_forgiven_ranges;
  bool m_pending_cnp;               // a forgiven non-last-hop trim owes CC one CNP
};
struct RdmaQueuePair {              // existing, gains counters only:
  uint32_t m_timeouts;              // cumulative RTO firings (m_recovery_retries resets on progress)
  uint32_t m_cnp_received;          // rate cuts taken (mode 1)
  uint32_t m_priority_pulls;
  uint64_t m_first_trim_ns, m_first_repair_ns;
};
```

Range state at the receiver, per trimmed [seq, seq+len):

| State | Meaning |
| --- | --- |
| Unknown | no decision yet |
| Pulled | PULL sent, repair expected; entry in m_pulled_ranges |
| Forgiven | absorbed into m_ooo_ranges as received; ledger charged |
| Received | data arrived (below ReceiverNextExpectedSeq or in m_ooo_ranges) |

Frontend, ExperimentConfig.hh:

```cpp
enum class SheddingDomain : uint8_t { Admission, Recovery };
struct StepLedger { uint64_t eligible = 0, shed = 0, forgiven = 0; bool closed = false; };
class ForgivenessLedger {           // dense: index = dst * step_count + (step - 1)
  std::vector<StepLedger> cells_;   // ranks <= 256, steps <= 200: 51200 cells, O(1) access
public:
  static ForgivenessLedger make(uint32_t ranks, uint32_t steps);
  void register_eligible(uint32_t dst, uint32_t step, uint64_t bytes);
  void register_shed(uint32_t dst, uint32_t step, uint64_t bytes);
  void close(uint32_t dst, uint32_t step);
  // Pure law: forgiven + shed + len <= threshold * eligible / kDecisionScale.
  bool may_forgive(uint32_t dst, uint32_t step, uint64_t len, uint64_t threshold) const;
  void charge(uint32_t dst, uint32_t step, uint64_t len);
};
```

Invariants: `forgiven` and `shed` only grow (absorbing, no refund);
`closed` ledgers never forgive; a cell is charged at most once per range
because the receiver's range state is sticky. Profile validation refuses
`domain: recovery` without `selective_repair: true` and
`packet_trimming.mode: ftd`.

Python (generate.py), frozen dataclasses parsed at one boundary:

```python
class SheddingDomain(StrEnum): ADMISSION = "admission"; RECOVERY = "recovery"
class CongestionControl(StrEnum): NONE = "none"; DCQCN = "dcqcn"
@dataclass(frozen=True, slots=True)
class SelectionPolicy: p_low: float; p_high: float; domain: SheddingDomain = ADMISSION
@dataclass(frozen=True, slots=True)
class CongestionControlConfig:
    mode: CongestionControl; rate_ai_fraction: float; rate_hai_fraction: float; min_rate_fraction: float
    # fractions of link rate; defaults 1/2000, 1/1000, 1/1000 = the HPCC 100G literals scaled
```

## 2. Transitions (pure core)

Receiver, on trim arrival for range r = [seq, seq+len), rxQp q:

| State of r | Event | Result |
| --- | --- | --- |
| Received | trim | ACK (duplicate); no ledger change |
| Pulled | trim | resend PULL with the same priority; idempotent |
| Forgiven | trim | ACK; no charge |
| Unknown | trim, verdict Pull / PullPriority | record in m_pulled_ranges; SendTrimNack(priority) |
| Unknown | trim, verdict Forgive | AddOutOfOrderRange(r); if seq == ReceiverNextExpectedSeq run the ReceiverCheckSeq advance; ACK now; m_pending_cnp |= !lastHop |
| Forgiven | data (RTO retransmit) | existing old-sequence branch: drop payload, ACK; no refund |
| Pulled | data | existing in-order or out-of-order accept; erase from m_pulled_ranges on advance |

Verdict function (frontend), total:

```
verdict(sip, dip, sport, dport, seq, len):
  flow = registry[(src, dst, sport)]           -- absent -> Pull
  if flow.kind != ForegroundPayload or !flow.admission_eligible -> Pull
  if domain != Recovery -> Pull
  step = flow.operation.training_step; clr = clr_mask[step]
  threshold = clr ? p_low : p_high
  if !ledger.may_forgive(dst, step, len, threshold) -> clr ? PullPriority : Pull
  ledger.charge(dst, step, len); flow.forgiven_bytes += len; -> Forgive
```

CC neutrality: the next ACK from q carries FLAG_CNP when m_pending_cnp,
so `ReceiveAck` runs `cnp_received_mlx` exactly as a pulled non-last-hop
trim would. Without this a forgiven trim hides congestion. Only mode 1
reacts; under `CC_MODE 12` the flag is inert and harmless.

Sender: unchanged. The cumulative ACK advances snd_una past forgiven
holes; completion stays `snd_una == m_size`. `RecoverTrimmedQueue` reads
`FLAG_PULL_PRIORITY` and counts it (v0). No new verb, no header growth:
the receiver resolves step and eligibility from its own flow registry,
so the step tag in the 2026-08-22 plan is dropped.

## 3. Effect boundary

| Effect | Where | Notes |
| --- | --- | --- |
| Packet emission (ACK, NACK, PULL) | RdmaHw | idempotent per range; retries via existing RTO |
| Ledger mutation | frontend, single-threaded sim | one charge per range; no rollback needed |
| Telemetry | flow_events.csv at flow end; transport_summary.csv at exit | new columns: forgiven_bytes, forgiven_ranges, priority_pulls, timeouts, cnp_received, first_trim_ns, first_repair_ns; new events trim_forgiven, rto_fired, cnp_taken |
| Config | experiment.json, network_config.txt | new keys validated at parse; unknown keys rejected as today |
| Python run/analyze | files only | no network, no randomness beyond seeds already recorded |

## 4. Complexity budget

| Operation | n | Bound | Structure |
| --- | --- | --- | --- |
| Verdict per trim | 4e6 (SR) to 4e8 (GBN) per run | O(log a) registry lookup, a <= 1e4 active flows; O(1) ledger | std::map registry (existing), dense vector ledger |
| Sticky range test | per trim | O(log p), p = outstanding pulled ranges per rxQp, pruned each advance | std::map per rxQp; empty-check first |
| ACK emission | per packet | +1 branch (m_pending_cnp) | bool |
| GetNextQindex | per dequeue, hot | unchanged in v0 | priority pulls deferred to v1 |
| Ledger memory | ranks x steps | 51200 cells x 32 B = 1.6 MB | vector |
| analyze per-step spans | 4e5 flows | O(n) single pass | dict by (step, node) |

Hot-path rule: only trims and ACK emission are touched; measure one
liveness checkpoint of `llama3_70b_32_direct` before and after on the
same binary recipe and report `wall_ms_delta` at equal simulated time.

## 5. Rejected alternative

Sender-side forgiveness (sender ignores the trim NACK). The receiver
keeps NACKing the gap forever, so the sender must also fake `snd_una`
and the receiver must learn the hole is closed, which needs a forward
FORGIVE verb and a second reconciliation path. Receiver-owned
forgiveness needs zero sender change and one bit on the reverse path.

## 6. Side questions in the same build

- CC knob: `network.congestion_control` writes `CC_MODE 1` or `12` and
  the three rate literals as fractions of link rate. Mode 1 gets the
  last-hop guard at rdma-hw.cc:635 removed (no RCCC exists to cover the
  last hop). Manifest records the resolved values.
- Telemetry: the counters above; W, wire-per-offered, burst drain
  (microburst end minus start) and per-step DP span in summary.json and
  the report; per-rank p99 reported as diagnostic.
- Matched sweeps: `run_hash` leaves `stable_operation_hash`; `run_id`
  stays as provenance. Aggregate equality compares repo-relative profile
  paths.
- Profiles and matrix: eight regime-map profiles (SR, cc none/dcqcn x
  direct2/direct7 x 2:1/4:1, 64 ranks), gate `regime_map`, single arm;
  `forgiveness_smoke_8`, gate `always`; `llama3_70b_32_direct_forgive`
  and the `no_incast_8` SR variant, gate `forgive`.

## 7. Open questions, defaults assumed

1. When a step ledger closes: when the receiving rank writes its
   collective_events row for that step's DP All-Reduce. Default: yes.
2. Whether shed bytes (admission) and forgiven bytes share one budget in
   the recovery arm: yes, the law sums them, and the recovery arm sheds
   nothing at admission, so the whole budget is available to forgiveness.
3. Priority pulls cross-QP in the egress queue: v1, after a pace A/B.
