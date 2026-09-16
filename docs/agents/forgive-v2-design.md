# FORGIVE v2: pacing, the cap's base, and the step stop

Design of record, revised 2026-09-14. It assumes the v1 exemption
revocation fix merged at `c6855f0`: two-bit verdict,
`FLAG_ALLOWANCE_EXHAUSTED`, `DeliverCongestionSignal`, no priority pulls,
no pulled-range cache. v2 adds two receiver policies on top of that and
changes no sender logic.

Target: C++20 in `astra-sim/network_frontend/ns3/ExperimentConfig.hh`,
C++17 in the ns-3 fork.

## 1. Principle and the two changes

Only the receiver can forgive, because only the receiver knows how much it
needs and how much it has.

| change | what | why |
| --- | --- | --- |
| P | pacing: the receiver may decline a forgivable trim so that allowance remains for later in the step | the cap binds at the headline budget, utilisation 81 % at 0.1, and first come first served spends it on the first burst |
| S | the step stop: the receiver ends a sender's step once `1 - p` of what that sender owes it has arrived, and takes the holes that sender left | at that point nothing new is coming from it, so the exemption has nothing left to protect and every microsecond spent on repairs is tail |

Both spend the same allowance under the same law. P reserves it, S spends
what is left at the end of a sender's step. Change S is specified in
[forgive-v2-round2.md](forgive-v2-round2.md) section 8, with the `owed`
base it reads.

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
// The budget law reads delivered and forgiven; eligible is the denominator
// close and analyze.py certify against.
// Invariants: every counter is monotone; forgiven + delivered <= eligible;
// closed never unsets; a closed cell refuses every query.

// The pacing rule is a closed sum. A Bernoulli probability is meaningful only
// under Bernoulli, so it lives inside that alternative and nowhere else.
struct NoPacing {};
struct Bernoulli { uint64_t threshold; };   // p * kDecisionScale
using Pacing = std::variant<NoPacing, Bernoulli>;

// The step stop. One bool, legal only on the owed base, because the rule
// reads what each sender still owes this rank for the step.
```

**Cap under each rule.** With `t` the step's threshold in `kDecisionScale`
units, a forgiveness of `b` bytes is affordable when

| rule | condition |
| --- | --- |
| both | `(forgiven + b) * S <= (delivered + forgiven + b) * t`, and under Bernoulli also `coin(flow, start) < threshold` |

The receiver measures the budget against the bytes it has accounted for,
kept or forgiven, so the law is `forgiven <= p x (delivered + forgiven)`,
equivalently `forgiven <= p / (1 - p) x delivered`, and a receiving NIC
holds both counters while it never sees what a sender launched. A step ends
with `delivered + forgiven = eligible`, so the ceiling is `p x eligible`,
which is v1's law; `eligible` stays as the denominator `close` and
`analyze.py` certify against, and the cap becomes available as the rank
receives rather than as senders launch. The remainder forgiveness of change
S uses the same condition without the coin: the coin reserves, the stop
consumes the reserve.

**The coin.** `coin(flow, start, attempt) =
hash_combine(flow.decision_hash, start, attempt) % kDecisionScale`, with
`attempt` the flow's count of verdicts asked. Every trimmed arrival draws,
so a range the coin refuses is asked again on its next trim and meets the
cap as it stands then, which has grown with delivery in the meantime.
Nothing about a range is remembered between trims. No ns-3 random stream is
consumed and the attempt counter is deterministic, so paired arms draw the
same sequence.

**Profile shape.**

```json
"selection_policy": {
  "p_low": 0.005, "p_high": 0.1, "domain": "recovery_exempt",
  "pacing": {"kind": "bernoulli", "p": 0.5},
  "cap_base": "owed", "step_stop": true
}
```

`pacing` defaults to `{"kind": "none"}`, `cap_base` to `"accounted"`, and
`step_stop` to false. The parser is the one smart constructor: `p` outside
`(0, 1)`, `p` given with a kind other than `bernoulli`, a `cap_base` that
is neither base, and `step_stop` without the owed base are rejected at
load.

## 3. Transitions

The pure core is two functions on a cell. Neither reads a clock or the
network; resolving the flow and the cell is the shell's business.

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
remainder_verdict(StepLedger, uint64_t threshold, uint64_t remainder,
                  uint32_t src, bool step_stop);
```

| event | guard | effect | result |
| --- | --- | --- | --- |
| trim | cell missing, closed, or flow ineligible | none | repair, spent bit clear |
| trim | Bernoulli and coin refuses | `pacing_refusals++` on the flow | repair, spent bit from the hard cap; the coin's refusal counts nowhere else |
| trim | affordable under the cap in force | `forgiven += b` | forgive |
| trim | otherwise | `refused_soft += b` under the soft cap | repair, spent bit from the hard cap |
| remainder | affordable, `remainder > 0`, and under the step stop the sender past `1 - p` of its share | `forgiven += remainder` | forgive `remainder` |
| remainder | otherwise | none | refuse, nothing sent |
| payload accepted | always | `delivered += bytes` on the cell and on the sender's share | the crossing arrival stops that sender's open flows |
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
// ns-3 side, beside the existing verdict callback. Asked at every accepted
// arrival. Returns the end offset to absorb from `next_expected`, or 0 to
// refuse. Not a struct on the trim path: the trim verdict never needs an
// end, and the remainder verdict never needs bits.
typedef Callback<uint64_t, uint32_t, uint32_t, uint16_t, uint16_t, uint64_t>
    RemainderVerdictCallback;
```

On a nonzero answer the receiver does exactly what a forgiven trim does:
`AddOutOfOrderRange(next_expected, end)`, advance the cumulative sequence,
send the ACK. The ACK's sequence is the flow size, so the sender's existing
`Acknowledge` completes the flow through `IsFinished`. No new packet type
and no new sender state.

**When the question is asked.** At every accepted arrival, with no timer
and no threshold in the transport: the frontend holds the budget and the
step's plan, so it is what decides, and it refuses until the arriving
sender has delivered `1 - p` of what it owes. That is one hash find per
data packet and no scheduler entry at all. The arrival that crosses `1 - p`
does not wait for the next packet of every other flow from that sender: the
frontend calls `RdmaHw::StopFlow` on each of them there and then, which is
what reaches a flow that is waiting on a repair.

**Late data.** After a remainder forgiveness the sender may still have
packets in flight, and they arrive for a five-tuple whose rx queue pair is
gone. `ReceiveUdp` calls `GetRxQp(..., create = true)`, so today a late
duplicate repair already resurrects an empty rx queue pair, which NACKs a
sender that no longer exists and is ignored at `if (!qp) return 0`. v2 adds
nothing to that path and keeps the resurrected pair inert, because the
frontend refuses a flow it no longer holds. No new state, and the
pre-existing leak stays pre-existing.

## 5. Effect boundary

| shell effect | idempotency and scope |
| --- | --- |
| ledger mutation | monotone counters; a duplicate forgiveness of a settled range is a no-op because `UnsettledBytes` is zero and no verdict is asked |
| `register_delivered` at every accepted arrival | once per newly accepted payload range, credited to the cell and to the sender that sent it; completion asserts the total against `q->m_size` less the forgiven bytes |
| the step stop's question | one hash find per accepted data packet, answered by the frontend; the arrival that crosses `1 - p` walks the registry once and stops that sender's open flows |
| remainder ACK | the ordinary ACK primitive; the sender tolerates it because `IsFinished` is `snd_una >= m_size` |
| telemetry | `forgiven_remainder_bytes` (a subset of `forgiven_bytes`, which the remainder also increments) and `pacing_refusals` on the flow record; transport events `remainder_forgiven` (bytes) beside `trim_forgiven` |

Trimmed-forgiven bytes are `forgiven_bytes - forgiven_remainder_bytes`,
derived rather than counted. Hard-cap reports are
`allowance_spent_signalled` from the v1 fix; soft-cap refusals and coin
refusals are counted because nothing else can see them.

## 6. Complexity budget

| operation | n | bound | structure |
| --- | --- | --- | --- |
| trim verdict | per trim, about 10^5 per run | O(1) | dense table, one hash_combine |
| remainder verdict | per accepted data packet under the step stop | O(1) plus O(log k) absorb | existing `std::map` of out-of-order ranges, k small |
| delivered update | per accepted data packet, about 10^7 per run | O(1) | one add to the cell and one to the sender's entry |

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

**Stop at `(1 - p)` delivered.** No longer an alternative: it is change S,
the design of record, specified in
[forgive-v2-round2.md](forgive-v2-round2.md) section 8. Whether making the
ceiling reachable costs anything is what run #127 measures, so the argument
is not settled here.

## 8. Arms

The arms that price these policies are in
[forgive-v2-round2.md](forgive-v2-round2.md) section 8, with their profiles,
seeds and ledger keys. Each is a `single` record running only the recovery
arm at the worst cell (`direct7`, 4:1, DCQCN) with the budget at 0.1, joined
at the seed against the comparison wave's baselines, because the harness
pairs by seed and a single arm and a comparison arm at the same seed and
profile are the same simulation.

**Fixture before any variant runs:** a `single` recovery arm at the base
profile must reproduce the comparison's `recovery_policy` bundle at the
same seed to the byte. If it does not, the join is invalid and the
variants run as full comparisons at 4 arms each instead.

Report per arm: 20-step window against fixed-low, forgiven share of
data-parallel bytes split trimmed and remainder, coin and cap refusals,
cells that reached the cap, and `cc_rearmed` per exempt flow.

Stated in advance: a Bernoulli arm should lower cap refusals at budget 0.1
and cost a little time, because a declined trim is a repair.

## 9. Open questions

1. Headline budget, 0.1 or 0.4. At 0.4 utilisation is 30 %, the cap never
   binds, and the pacing arms are dead by construction. Default 0.1.
2. Whether the single-record join is valid. Default yes, gated by the
   fixture above.
