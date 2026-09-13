# FORGIVE v2: the receiver's decision

Design of record for the next change to the receiver verdict. It replaces
nothing in [forgive-protocol.md](forgive-protocol.md), which specifies the
protocol as built and measured in runs #121 and #122. This document
specifies what changes, and gives the reason for each decision.

Target: C++20, matching `astra-sim/network_frontend/ns3/ExperimentConfig.hh`.

## 1. The principle

Only the receiver can forgive, because only the receiver knows both how
much it needs and how much it has. Every decision below follows from that
sentence.

v2 adds two capabilities and corrects one defect.

| # | change | reason |
| --- | --- | --- |
| A | The exemption revokes on a budget refusal, not on any repair | The receiver emits the same repair request from three sites and only one of them consults the ledger, so two thirds of the revocation paths mean nothing about the allowance. See section 3. |
| B | The receiver may forgive bytes the sender has not sent | A forgiven trimmed byte was already carried and destroyed, so forgiving it saves only the repair. Forgiving an unsent byte saves the transmission too. |
| C | `shed` leaves the receiver's budget law | `shed` is the sender deciding without knowing either quantity. It belongs to the admission domain, which is the thing this protocol is defined against. |

## 2. Domain model

```cpp
// One receiving rank's allowance for one training step.
struct StepLedger {
    uint64_t eligible  = 0;   // bytes this rank is owed for this step
    uint64_t delivered = 0;   // arrived and kept
    uint64_t forgiven  = 0;   // the receiver agreed never to see these
    bool     closed    = false;
};
```

Invariants:

- `delivered + forgiven + outstanding == eligible`, where
  `outstanding = eligible - delivered - forgiven`
- `forgiven * kDecisionScale <= eligible * threshold(step)`
- `delivered` and `forgiven` never decrease, and `closed` never unsets
- once `closed`, every query answers refuse and every update is a no-op

**Decision: `eligible` is fixed when the cell opens, not accumulated.**
Today `register_eligible` adds bytes as each message is admitted, so
`eligible` is final only once the step is over. Goal B needs `outstanding`
during the step, and `outstanding` means nothing while its denominator is
still growing. The collective library supplies the total in advance:
`ncclAllReduce` takes count and datatype at launch, DDP fixes bucket sizes
at bucket-formation time, and a ring or direct schedule makes the per-peer
split deterministic. So the receiver opens the cell with its final
`eligible`, and the accumulating path becomes a consistency check rather
than the source of truth.

**Decision: the table stays dense, indexed by `(dst, step)`.** Unchanged
from v1, and the measured sizes justify it: 1280 cells at 64 ranks and 20
steps, under a megabyte in total, one multiply-add per access.

## 3. The verdict

The wire enum must not drift from `RdmaHw::RecoveryVerdict`, so it keeps
its three cases and gains no fourth.

```cpp
enum class RecoveryVerdict : uint8_t { Pull = 0, Forgive = 1, PullPriority = 2 };
```

**Decision: the wire says acknowledge or repair, plus one bit on the
repair.** The sender does not need to know why the receiver forgave. Both kinds of
forgiveness produce the same sender action, which is to advance and send
nothing, and the sender can tell them apart itself by comparing the
acknowledged range against `snd_nxt`. The one question a sender must
answer is whether to re-engage congestion control, that question only
arises on a repair request, and section 3 shows why the receiver has to
answer it rather than leaving the sender to guess.

One receiver-side distinction earns its keep, and it never reaches a
header:

```cpp
enum class ForgiveKind : uint8_t {
    Trimmed,      // the fabric destroyed these bytes; do not ask again
    Outstanding,  // the sender has not sent these bytes; do not send them
};
```

It exists because the whole point of Goal B is bytes that never reach the
wire, and no existing counter can see them. Split the telemetry into
`forgiven_trimmed_bytes` and `forgiven_outstanding_bytes` and the saving
is readable; leave them merged and it is invisible.

A matching enum for the refusal side would earn nothing. The sender needs
one fact, whether the allowance is spent, and that is one bit. Naming its
complement adds a symbol without adding a decision.

**Decision: the refusal bit means "the allowance is spent", and nothing
narrower.** A critical step is not a prohibition. It sets `p_low` rather than `p_high`, and forgiveness
does happen there: masked runs place 1.0 to 1.5 % of their forgiven bytes
on steps 1, 2, 3 and 20. A refusal on a critical step is therefore
`BudgetExhausted` against a lower cap. The step's only distinct effect is
that its refusal escalates to `PullPriority` so the repair jumps the queue,
which `evaluate_forgiveness` already does and which stays.

**Decision: revocation keys on `BudgetExhausted` alone.**

```cpp
constexpr bool revokes_exemption(uint8_t verdict) {
    return !forgave(verdict) && (verdict & kRepairExhausted);
}
```

The reason is that a repair request does not mean what the sender assumes.
`SendTrimNack` always stamps `kUecTrimRepairProtocol` and only the
destination calls it, so every entry to `RecoverTrimmedQueue` is a
destination repair request and the back-to-sender branch its comment
mentions is dead in this build. Three receiver sites emit that request,
and two of them never reach the ledger.

| site | condition | consults the ledger |
| --- | --- | --- |
| `rdma-hw.cc:737` | the receive queue pair is gone, so a late trim gets a plain pull | no |
| `rdma-hw.cc:756` | `FindPulledRange` hits, so the range already has a repair outstanding and the request is re-sent | no |
| `rdma-hw.cc:790` | the verdict was `Pull` or `PullPriority` | yes |

The middle row is the common one. Under selective repeat with steady
congestion the same range is trimmed again while its repair is still in
flight, the receiver re-sends the request without asking anything, and the
sender revokes. That is why the mask-off arm re-arms 15,509 to 15,773
flows of 89,600 while its allowance sits at 37 % utilisation and almost
never refuses.

Note on evidence: `priority_pull_count` is not a refusal count. It
increments only on `FLAG_PULL_PRIORITY`, which `evaluate_forgiveness` sets
only on a critical step, so a profile with no critical steps reports zero
regardless of how often the receiver refused. An earlier draft of this
document read that zero as a measurement.

**Decision: the repair request carries one bit, and the sender re-arms on
that bit alone.** The sender cannot infer the cause, because all three
sites produce an identical packet, so the receiver has to say which one it
is. One flag beside `FLAG_PULL_PRIORITY` in the existing header is enough,
set only at `rdma-hw.cc:790` and only when the verdict refused for want of
allowance.

This is the smallest change that restores the stated semantics. Leaving
the other two sites silent is not an option, since a lost repair must be
re-requestable and a late trim must still be answered.

**Decision: count the three sites separately in telemetry.** The flow
record carries `priority_pulls` but no refusal total, so today a reader
cannot tell a duplicate re-request from a real refusal. Add one counter
per site. It costs three increments and it is what makes arm 2 in section
9 readable.

## 4. Transitions

```cpp
enum class EventKind : uint8_t { Arrived, Trimmed, Idle, Close };
struct Event { EventKind kind; ByteRange range; uint64_t at_ns; };

// Total. Returns the updated cell and the verdict to emit, if any.
std::pair<StepLedger, std::optional<Verdict>> step(StepLedger, const Event&);
```

| event | guard | effect | verdict |
| --- | --- | --- | --- |
| Arrived | always | `delivered += len` | none |
| Trimmed | flow ineligible, step unknown, or cell closed | none | repair, exhausted bit clear |
| Trimmed | `forgiven + len` within the cap | `forgiven += len` | `Forgive`, kind `Trimmed` |
| Trimmed | otherwise, critical step | none | repair, priority and exhausted bits set |
| Trimmed | otherwise | none | repair, exhausted bit set |
| Idle | `0 < outstanding <= cap - forgiven` | `forgiven += outstanding` | `Forgive`, kind `Outstanding` |
| Idle | otherwise | none | none |
| Close | always | `closed = true` | none |

**Decision: the `Idle` guard requires the whole remainder to fit.** A
partial stop would make the receiver choose which outstanding bytes to
sacrifice, and it has no basis for that choice: it knows the byte count but
not which gradient elements matter. Requiring the whole remainder to fit
keeps the stop one atomic decision and keeps the cap hard.

**Decision: `Idle` fires on a straggler, not on reaching `(1 - p)`.** The
reason is in section 6.

## 5. Effect boundary

The pure core is the transition function and `revokes_exemption`. Neither
reads a clock, allocates, or touches the network, and `Idle` passes its
timestamp as data, so the core stays testable without a simulator.

| shell effect | idempotency and scope |
| --- | --- |
| the idle timer that emits `Idle` | one armed timer per open cell, rearmed on `Arrived`, cancelled on `Close` |
| emitting a forgiveness | an acknowledgement of a range the receiver never got, which is the primitive v1 already uses |
| the sender cancelling outstanding bytes | must tolerate an acknowledgement past `snd_nxt`; the fork has precedent in the cumulative-acknowledgement clamp |
| clearing the exemption flag | the only write, and only when `revokes_exemption` holds |

**Decision: forgiving outstanding bytes adds no packet type, but it does
add a trigger.** The acknowledgement already exists and already covers
ranges the receiver never received. What is new is that the receiver sends
one unprompted rather than in response to an arrival. That changes when the
receiver speaks, not what it says, so the claim that survives is the one
that matters for hardware: no new header, and no new sender state beyond
accepting an acknowledgement it did not expect.

Idempotency falls out of monotonicity. A duplicate forgiveness for a range
already forgiven is a no-op, because `forgiven` only grows and the range
set is a set. Forgiving bytes already in flight is harmless: they arrive,
the receiver discards them, and `delivered` does not move because the range
is already forgiven.

## 6. Rejected alternative: stop at `(1 - p)` delivered

The obvious reading of Goal B is MLT's contract, where the receiver stops
as soon as `(1 - p)` of the collective has arrived, so the allowance is
always spent in full. Rejected, for a measured reason.

Under v1 the loss is congestion-proportional. Run #122 spends 6.4 %, 8.5 %,
9.4 % and 9.2 % of data-parallel bytes at budgets of 0.1, 0.2, 0.4 and 0.6,
because the fabric stops trimming before the budget is spent, and an
uncongested run forgives almost nothing. Stopping unconditionally converts
the cap from a ceiling into a target, so the loss becomes exactly `p`
whether or not the fabric is busy. That contract is also what holds MLT's
tolerable `p` to 0.7 to 3.3 %, so adopting it would drag our headline
budget into the same range and cost us the self-limiting result.

Forgiving on a straggler keeps both properties. The receiver forgives only
once the remaining bytes have gone quiet, which is when they sit on the
collective's critical path, so the wire saving arrives where it is worth
something and an uncongested step still forgives nothing.

## 7. Out of scope

Pacing the allowance across a step, so one congestion event cannot consume
a cell early, is a separate change. Neither goal here causes or prevents
it. Goal A does remove one of its consequences: with tagged revocation, a
burst can no longer revoke exemptions through repairs that were never
budget refusals.

## 8. Open questions

1. **How quiet is idle?** Default: twice the cell's observed inter-arrival
   median, floored at one estimated round trip and capped at a quarter of
   the retransmission timeout. One profile knob, cheap to sweep.
2. **Do the two forgiveness kinds share one cap?** Default: yes, one cap
   and one counter, which keeps the invariant list at four lines. A
   reserved slice for stragglers would guarantee a tail forgiveness is
   always affordable, at the cost of a second cap and a second exhaustion
   path.
3. **Can the collective library's `eligible` disagree with the accumulated
   total?** Default: assume not, assert equality at `Close`, and fail the
   run loudly on a mismatch, because a wrong denominator silently changes
   every budget in that step.

## 9. Arms

Four arms at the worst cell of the regime map, budget 0.1, three seeds,
isolating each change.

| arm | revocation | outstanding forgiveness | answers |
| --- | --- | --- | --- |
| 1 | any repair, as in v1, with the three sites counted separately | none | the baseline, and how the revocations split |
| 2 | budget refusals only | none | what Goal A is worth |
| 3 | budget refusals only | on a straggler | what A and B are worth together |
| 4 | budget refusals only | at `(1 - p)` delivered | prices the contract change in section 6 |


Report for each: training time recovered, gradient forgiven as a share of
data-parallel bytes, physical bytes on the wire, and whether the forgiven
share still rises with congestion rather than with the budget. Arm 4
decides whether the self-limiting property is worth defending.
