# FORGIVE v2: tagged revocation and proactive stop

Design for two changes to the receiver verdict. Goal A fixes the exemption
revocation, which currently fires on any repair rather than on budget
exhaustion. Goal B lets the receiver concede bytes the sender has not sent
yet, so the allowance can be spent on traffic the fabric never carries.

The two changes turn out to be one change. Both are concessions of bytes
against a single per-cell allowance, and both are answered by the same
verdict type.

Target: C++20, matching `astra-sim/network_frontend/ns3/ExperimentConfig.hh`.

## 1. Domain model

The central rename is `conceded`. A byte is conceded when the receiver has
agreed never to see it, whether the fabric already destroyed it, the
receiver stopped it before the sender sent it, or the sender suppressed it
at admission. One counter, charged by whichever mechanism the domain
allows.

Today `may_forgive` reads `cell->shed + cell->forgiven + bytes`, which
implies the two are separate resources competing for one cap. They never
compete. `evaluate_shedding` returns early whenever `forgives(domain)`
holds, so `shed` is identically zero in every FORGIVE run, and
`admission_shed_cell_count` is 0 in all 14 records of run #122. The sum is
a guard against a future domain that both sheds and forgives, and it costs
a reader the question of why an admission-domain counter appears in the
receiver's invariant. Charging one counter removes the question and keeps
the guard, because a domain that did both would charge the same counter
twice.

```cpp
// A cell is the allowance for one destination rank in one training step.
// `eligible` comes from the collective launch parameters, so it is exact
// before the step starts rather than estimated.
struct CellKey { uint32_t dst_rank; uint32_t training_step; };

class Cell {
  public:
    // The only constructor. Rejects p outside [0, kDecisionScale] and
    // eligible == 0, so an open cell always satisfies its invariants.
    static std::optional<Cell> open(CellKey, uint64_t eligible_bytes,
                                    uint64_t p_scaled);

    uint64_t remaining_allowance() const { return cap_ - conceded_; }
    uint64_t outstanding() const { return eligible_ - delivered_ - conceded_; }

  private:
    CellKey  key_;
    uint64_t eligible_;
    uint64_t cap_;            // p_scaled * eligible / kDecisionScale, fixed at open
    uint64_t delivered_ = 0;  // monotone non-decreasing
    uint64_t conceded_  = 0;  // monotone non-decreasing
};
```

Invariants, all checkable in one line each:

- `delivered_ + conceded_ + outstanding() == eligible_`
- `conceded_ <= cap_`, whichever mechanism charged it
- `delivered_` and `conceded_` never decrease
- `cap_` never changes after `open`

The last one matters. `eligible_` is known at launch, so the cap is a
constant for the life of the cell and no transition needs to recompute it.

## 2. The verdict, as a closed sum

```cpp
enum class ConcessionKind : uint8_t {
    Forgive,   // the fabric trimmed these bytes; do not ask for them again
    Stop,      // the sender has not sent these bytes; do not send them
};

enum class RefusalCause : uint8_t {
    BudgetExhausted,   // the allowance is spent
    StepProtected,     // a critical step, where p_low binds
    RangeIneligible,   // not data-parallel payload
};

struct Concede { ConcessionKind kind; ByteRange range; };
struct Refuse  { RefusalCause  cause; ByteRange range; };

using Verdict = std::variant<Concede, Refuse>;
```

Goal A becomes one total function over that sum, and the compiler enforces
it when a cause is added later:

```cpp
constexpr bool revokes_exemption(const Verdict& verdict) {
    if (const auto* refusal = std::get_if<Refuse>(&verdict)) {
        switch (refusal->cause) {
            case RefusalCause::BudgetExhausted: return true;
            case RefusalCause::StepProtected:   return false;
            case RefusalCause::RangeIneligible: return false;
        }
    }
    return false;
}
```

Today's behaviour is the degenerate case where every repair looks like
`BudgetExhausted`. That is why the mask-off arm re-arms 15,509 to 15,773
flows while issuing zero receiver refusals: those revocations came from
repairs the ledger never saw.

## 3. Transitions

```cpp
enum class EventKind : uint8_t { Arrived, Trimmed, TailIdle, Closed };
struct Event { EventKind kind; ByteRange range; uint64_t at_ns; };

// Total. Returns the new cell and the verdict to put on the wire, if any.
std::pair<Cell, std::optional<Verdict>> step(Cell, const Event&);
```

| state | event | guard | next | verdict |
| --- | --- | --- | --- | --- |
| open | Arrived | always | `delivered_ += len` | none |
| open | Trimmed | protected step | unchanged | `Refuse{StepProtected}` |
| open | Trimmed | not DP payload | unchanged | `Refuse{RangeIneligible}` |
| open | Trimmed | `len <= remaining_allowance()` | `conceded_ += len` | `Concede{Forgive}` |
| open | Trimmed | otherwise | unchanged | `Refuse{BudgetExhausted}` |
| open | TailIdle | `outstanding() <= remaining_allowance()` and `outstanding() > 0` | `conceded_ += outstanding()` | `Concede{Stop}` |
| open | TailIdle | otherwise | unchanged | none |
| open | Closed | always | cell retires | none |

The `TailIdle` guard is the whole of Goal B, and it is deliberately
conservative. The receiver stops only when the entire remainder fits inside
what is left of the allowance, so a stop is one atomic decision and the cap
stays hard. A partial stop would need the receiver to choose which bytes to
sacrifice, which is a policy the receiver has no basis to decide.

## 4. Effect boundary

The pure core is `open`, `step` and `revokes_exemption`. None of them read a
clock, allocate, or touch the network; `TailIdle` passes its timestamp as
data, so the core stays testable by construction.

The shell holds four things.

| effect | notes |
| --- | --- |
| the idle timer that emits `TailIdle` | one armed timer per live cell, rearmed on `Arrived` |
| transmitting a `Concede` | it is an acknowledgement of a range the receiver never got, which is the primitive forgiveness already uses, so `Stop` needs no new message type |
| the sender cancelling outstanding bytes | must tolerate an acknowledgement past `snd_nxt`, for which the fork already has precedent in the cumulative-acknowledgement clamp |
| the exemption flag | cleared when `revokes_exemption` holds, which is the only write |

Idempotency falls out of monotonicity. A duplicate `Concede` for a range
already conceded is a no-op, because `conceded_` only grows and the range
set is a set. A `Stop` that races bytes already in flight is harmless: they
arrive, the receiver discards them, and `delivered_` does not move because
the range is already conceded.

## 5. Complexity budget

| operation | expected n per run | bound | structure |
| --- | ---: | --- | --- |
| `open` | 1280 cells, 64 ranks by 20 steps | O(1) | value type, 40 bytes |
| `step` on Trimmed | 4.2 to 6.7 M verdicts | O(1) | three comparisons, one add |
| `step` on Arrived | one per delivered range | O(1) | one add, one timer rearm |
| `revokes_exemption` | once per verdict | O(1) | switch over 3 variants |
| live idle timers | one per open cell, so one per rank at a time | O(ranks) | existing ns-3 event queue |

Space is 40 bytes per cell, and a real receiver holds one cell per step in
flight rather than all 1280, so the ledger is a few hundred bytes per rank.
The range bookkeeping `Stop` needs already exists for selective repeat, so
Goal B adds no new index.

## 6. Rejected alternative: stop unconditionally at `(1 - p)` delivered

The obvious reading of Goal B is MLT's contract: the receiver stops as soon
as `(1 - p)` of the collective has arrived, so the allowance is always spent
in full. I reject it, and the reason is measured rather than aesthetic.

Under the current design, loss is congestion-proportional. Run #122 spends
6.4 %, 8.5 %, 9.4 % and 9.2 % of data-parallel bytes at budgets of 0.1, 0.2,
0.4 and 0.6, because the fabric stops trimming before the budget is spent.
An uncongested run concedes almost nothing. Stopping unconditionally
converts the cap from a ceiling into a target, so loss becomes exactly `p`
whether or not the fabric is busy, and the self-limiting result disappears.

That contract is also what forces MLT's tolerable `p` down to 0.7 to 3.3 %.
Adopting it would move our headline budget into the same range and cost us
the argument that the mechanism spends only what congestion demands.

The tail-triggered version keeps both properties. It concedes only when a
straggler exists, which is exactly when the outstanding bytes sit on the
collective's critical path, so it captures the wire saving where the saving
is worth something.

## 7. What this does not fix

The pacing question is orthogonal and stays open. A single congestion event
can still consume a cell's whole allowance early, and the two changes here
neither cause nor prevent that. Goal A does reduce one consequence: with
tagged revocation, an exemption survives repairs that are not budget
refusals, so a burst no longer revokes exemptions through the side door.

## 8. Open questions

1. **How long is idle?** Default: twice the cell's observed
   inter-arrival median, floored at one estimated round trip and capped at
   a quarter of the retransmission timeout. It is one profile knob and the
   sweep is cheap.
2. **Do `Forgive` and `Stop` draw on one pool or two?** Default: one pool
   and one cap, which keeps the invariant list at four lines. A reserved
   stop pool would guarantee a tail concession is always affordable, at the
   cost of a second cap and a second exhaustion path.
3. **Does `Stop` need its own telemetry column?** Default: yes, a
   `stopped_bytes` counter beside `forgiven_bytes`, because the whole point
   of Goal B is bytes that never reach the wire and the existing counters
   cannot see them.

## 9. Arms to run

Four arms at the worst cell, budget 0.1, three seeds, isolating each change.

| arm | revocation | stop | answers |
| --- | --- | --- | --- |
| 1 | any repair, as today | none | the current baseline |
| 2 | tagged | none | what Goal A alone is worth |
| 3 | tagged | tail-triggered | what Goal A and B are worth together |
| 4 | tagged | unconditional at `(1 - p)` | prices the contract change in section 6 |

Report for each: training time recovered, gradient conceded as a share of
data-parallel bytes, physical bytes on the wire, and whether loss still
rises with congestion rather than with the budget. Arm 4 is the one that
tells us whether the self-limiting property is worth defending.
