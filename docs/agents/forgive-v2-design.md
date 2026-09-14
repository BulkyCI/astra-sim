# FORGIVE v2: pacing and the straggler stop

Design of record, revised 2026-09-14. It assumes the v1 revocation fix in
[forgive-v1-revocation-fix.md](forgive-v1-revocation-fix.md) is merged:
two-bit verdict, `FLAG_ALLOWANCE_EXHAUSTED`, `DeliverCongestionSignal`,
no priority pulls, no pulled-range cache. v2 adds two receiver policies on
top of that and changes no sender logic.

Target: C++20 in `astra-sim/network_frontend/ns3/ExperimentConfig.hh`,
C++17 in the ns-3 fork.

## 1. Principle and the two changes

Only the receiver can forgive, because only the receiver knows how much it
needs and how much it has.

| change | what | why |
| --- | --- | --- |
| P | pacing: the receiver may decline a forgivable trim so that allowance remains for later in the step | the cap binds at the headline budget, utilisation 81 % at 0.1, and first come first served spends it on the first burst |
| S | straggler stop: the receiver forgives a flow's unsent remainder once the flow has gone quiet | a forgiven trimmed byte saves its repair; a forgiven unsent byte saves its transmission too |

Both spend the same allowance under the same law. P reserves it, S is
what the reserve is for.

## 2. Domain model

```cpp
// One receiving rank's allowance for one step. Dense table by (dst, step),
// unchanged from v1. eligible accumulates as messages launch, which is
// itself a weak pacing and stays.
struct StepLedger {
    uint64_t eligible  = 0;   // bytes launched toward this rank this step
    uint64_t shed      = 0;   // admission domain only; zero here
    uint64_t forgiven  = 0;   // trimmed and remainder bytes together
    uint64_t delivered = 0;   // bytes of completed messages, less their forgiven bytes
    bool     closed    = false;
};
// Invariants: every counter is monotone; forgiven + delivered <= eligible;
// closed never unsets; a closed cell refuses every query.

// The pacing rule is a closed sum. A Bernoulli probability is meaningful only
// under Bernoulli, so it lives inside that alternative and nowhere else.
struct NoPacing {};
struct Bernoulli { uint64_t threshold; };   // p * kDecisionScale
struct Vesting   {};
using Pacing = std::variant<NoPacing, Bernoulli, Vesting>;

// Straggler stop. idle_ns == 0 means ask at every arrival, which is MLT's
// stop-at-(1-p) contract as the degenerate point of ours.
struct Straggler { std::optional<uint64_t> idle_ns; };  // nullopt: disabled
```

**Cap under each rule.** With `t` the step's threshold in `kDecisionScale`
units, a forgiveness of `b` bytes is affordable when

| rule | condition |
| --- | --- |
| NoPacing | `(forgiven + b) * S <= eligible * t` |
| Bernoulli | the NoPacing condition, and `coin(flow, start) < threshold` |
| Vesting | `(forgiven + b) * S <= delivered * t` |

Vesting is strictly tighter than NoPacing because `delivered <= eligible`,
so the ceiling is unchanged and only its availability moves. The remainder
forgiveness of change S uses the same condition without the coin: the coin
reserves, the stop consumes the reserve.

**The coin.** `coin(flow, start) = hash_combine(flow.decision_hash, start)
% kDecisionScale`. Deterministic per range, so a range the coin refuses
stays refused on re-trim and "forgive a fraction `p` of trimmed ranges" is
exact rather than geometric. No ns-3 random stream is consumed, so paired
arms stay paired.

**Profile shape.**

```json
"selection_policy": {
  "p_low": 0.005, "p_high": 0.1, "domain": "recovery_exempt",
  "pacing": {"kind": "bernoulli", "p": 0.5},
  "straggler_idle_ns": 250000
}
```

`pacing` defaults to `{"kind": "none"}`, `straggler_idle_ns` absent means
disabled. The parser is the one smart constructor: `p` outside `(0, 1)`,
`p` given with a kind other than `bernoulli`, or a negative idle are
rejected at load.

## 3. Transitions

The pure core is two functions on a cell. Neither reads a clock or the
network; the timestamp that decides idleness is the shell's business.

```cpp
// Trim verdict. Total. Returns the verdict bits and the cell to store.
// Two bits: kForgive, kAllowanceSpent (set when no further range could
// be afforded after this decision, under the rule's own condition).
std::pair<uint8_t, StepLedger>
trim_verdict(StepLedger, uint64_t threshold, const Pacing&, uint64_t coin, uint64_t bytes);

// Remainder verdict. Total. Returns the bytes to forgive, zero to refuse.
// Whole remainder or nothing: the receiver knows the byte count and not
// which gradient elements matter, so it does not choose among them.
std::pair<uint64_t, StepLedger>
remainder_verdict(StepLedger, uint64_t threshold, const Pacing&, uint64_t remainder);
```

| event | guard | effect | result |
| --- | --- | --- | --- |
| trim | cell missing, closed, or flow ineligible | none | repair, spent bit clear |
| trim | Bernoulli and coin refuses | `pacing_refusals++` on the flow | repair, spent bit as on every repair: set when the cap has no room |
| trim | affordable under the rule | `forgiven += b` | forgive |
| trim | otherwise | none | repair, spent bit set |
| remainder | affordable under the rule and `remainder > 0` | `forgiven += remainder` | forgive `remainder` |
| remainder | otherwise | none | refuse, nothing sent |
| message complete | always | `delivered += size - flow.forgiven_bytes` | none |
| collective complete | always | `closed = true` | none |

A refused remainder emits nothing. The exemption revokes only on a repair
request with the spent bit, and no repair is requested here; the next trim
will carry the bit if the cap is spent.

**Decision: the coin never applies to the remainder.** Pacing exists to
keep allowance for the end of the step. Applying it at the end of the step
would defeat its own purpose.

## 4. The receiver's side of change S

The rx queue pair does not know the flow's size; the frontend's
`FlowRecord` does. So the transport asks, and the answer is the end
offset.

```cpp
// ns-3 side, beside the existing verdict callback. Asked when the rx queue
// pair has been idle with a gap. Returns the end offset to absorb from
// `next_expected`, or 0 to refuse. Not a struct on the trim path: the trim
// verdict never needs an end, and the remainder verdict never needs bits.
typedef Callback<uint64_t, uint32_t, uint32_t, uint16_t, uint16_t, uint64_t>
    RemainderVerdictCallback;
```

On a nonzero answer the receiver does exactly what a forgiven trim does:
`AddOutOfOrderRange(next_expected, end)`, advance the cumulative sequence,
send the ACK. The ACK's sequence is the flow size, so the sender's existing
`Acknowledge` completes the flow through `IsFinished`. No new packet type
and no new sender state.

**Idle detection.** One `uint64_t m_last_arrival_ns` and one `EventId` on
`RdmaRxQueuePair`. Each accepted data packet writes the timestamp and schedules the
event only if none is pending. The event fires at `last_arrival + idle`;
on firing, if `now - last_arrival < idle` it reschedules to
`last_arrival + idle`, otherwise it asks the remainder verdict and does not
re-arm; the next arrival will. That is O(1) per packet and at most one
scheduler entry per open rx queue pair. Cancel the
event where the rx queue pair is deleted. With `idle_ns == 0` there is no
timer and the question is asked at every arrival.

**Late data.** After a remainder forgiveness the sender may still have
packets in flight, and they arrive for a five-tuple whose rx queue pair is
gone. `ReceiveUdp` calls `GetRxQp(..., create = true)`, so today a late
duplicate repair already resurrects an empty rx queue pair, which NACKs a
sender that no longer exists and is ignored at `if (!qp) return 0`. v2
adds nothing to that path and keeps the resurrected pair inert: the idle
event is not re-armed after a refusal, an arrival arms it only when none is
pending, and the frontend refuses because the flow is no longer registered.
No new state, and the pre-existing leak stays pre-existing.

## 5. Effect boundary

| shell effect | idempotency and scope |
| --- | --- |
| ledger mutation | monotone counters; a duplicate forgiveness of a settled range is a no-op because `UnsettledBytes` is zero and no verdict is asked |
| `register_delivered` at message completion | once per message, from the queue-pair completion callback that already has `q->m_size` and `flow.forgiven_bytes` |
| idle event | one per open rx queue pair, lazily rescheduled, cancelled at deletion |
| remainder ACK | the ordinary ACK primitive; the sender tolerates it because `IsFinished` is `snd_una >= m_size` |
| telemetry | `forgiven_remainder_bytes` (a subset of `forgiven_bytes`, which the remainder also increments) and `pacing_refusals` on the flow record; transport events `remainder_forgiven` (bytes) beside `trim_forgiven` |

Trimmed-forgiven bytes are `forgiven_bytes - forgiven_remainder_bytes`,
derived rather than counted. Cap refusals are `allowance_spent_signalled`
from the v1 fix; coin refusals are counted because nothing else can see
them.

## 6. Complexity budget

| operation | n | bound | structure |
| --- | --- | --- | --- |
| trim verdict | per trim, about 10^5 per run | O(1) | dense table, one hash_combine |
| remainder verdict | per idle event, at most once per idle period per rx qp | O(1) plus O(log k) absorb | existing `std::map` of out-of-order ranges, k small |
| delivered update | per message, about 10^4 per run | O(1) | one add |
| idle timer | per packet, about 10^7 per run | O(1) write; O(log E) per fire | timestamp plus lazy reschedule |

Nothing here is on a hot path that was not already there.

## 7. Rejected alternatives

**Fix `eligible` when the cell opens, from the collective library.** The
earlier draft wanted this so that cell-level `outstanding` existed during
the step. Once the remainder is flow-scoped, the transport supplies
`next_expected` and the frontend supplies the size, and no cell-level
outstanding is needed. Fixing `eligible` would also remove the pacing that
accumulation provides, making the burn-out problem strictly worse. Killed
by having no consumer.

**One callback returning a struct for both questions.** Every trim verdict
would carry an end it never uses. Two callbacks, two questions.

**A fresh coin per trim attempt.** Turns Bernoulli into a geometric delay
of a few round trips rather than a reservation. Killed by not being a
pacing rule.

**Stop at `(1 - p)` delivered unconditionally, as MLT.** Converts the cap
from ceiling to target so the loss is exactly `p` whether or not the fabric
is busy, which is what pins MLT's tolerable `p` to 0.7 to 3.3 %. Retained
only as the `idle_ns = 0` arm, so its price is measured rather than argued.

**Adaptive idle from the observed inter-arrival distribution.** A running
median per queue pair for one knob. One number, swept, is enough until a
result says otherwise.

## 8. Arms

Receiver-policy variants only, at the worst cell (`direct7`, 4:1, DCQCN),
3 seeds, budget 0.1 where the cap binds. Each variant is a `single` record
running only the recovery arm, joined at the seed against the corrected v1
wave's baselines. The harness pairs by seed, so a single arm and a
comparison arm at the same seed and profile are the same simulation.

| arm | pacing | straggler | answers |
| --- | --- | --- | --- |
| v1 | none | off | the reference, from the v1 wave, not re-run |
| B50 | Bernoulli 0.5 | off | Yashar's suggestion as stated |
| B25 | Bernoulli 0.25 | off | whether the effect is monotone in `p` |
| V | vesting | off | the deterministic reservation |
| S | none | 250 µs | change S alone |
| S0 | none | 0 | MLT's contract, priced |
| VS | vesting | 250 µs | the composed design |

7 variants, 6 new, 3 seeds, 18 arms, about 3 cluster hours.

**Fixture before any variant runs:** a `single` recovery arm at the base
profile must reproduce the comparison's `recovery_policy` bundle at the
same seed to the byte. If it does not, the join is invalid and the
variants run as full comparisons at 4 arms each instead.

Report per arm: 20-step window against fixed-low, forgiven share of
data-parallel bytes split trimmed and remainder, coin and cap refusals,
cells that reached the cap, and `cc_rearmed` per exempt flow.

Stated in advance: V and B50 should lower cap refusals at budget 0.1 and
cost a little time each, because a declined trim is a repair. S should
recover time on the seeds whose worst all-reduce has a long tail and do
nothing elsewhere. S0 should forgive close to `p` on every step and is the
arm we expect to lose. If VS does not beat S, vesting is not worth its
field.

## 9. Open questions

1. Idle threshold. Default 250 µs, a quarter of the 1 ms retransmission
   timeout and far above the fabric's round trip. Sweep 100 µs only if S
   is null.
2. Headline budget, 0.1 or 0.4. At 0.4 utilisation is 30 %, the cap never
   binds, and the pacing arms are dead by construction. Default 0.1.
3. Whether the 18-arm single-record join is valid. Default yes, gated by the
   fixture above.
