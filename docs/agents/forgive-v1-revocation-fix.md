# Fix: revoke the exemption only when the allowance is spent

Implementation plan for the FORGIVE v1 defect found on 2026-09-12. Scope is
the revocation trigger and nothing else. Goal B of
[forgive-v2-design.md](forgive-v2-design.md) stays out.

## 1. The defect

`RecoverTrimmedQueue` clears `m_cc_exempt` at its top, before any other
check, on every repair request that reaches the sender. The receiver emits
that request from four sites and only two of them consulted the allowance.

| site | condition | allowance consulted | should revoke |
| --- | --- | --- | --- |
| `rdma-hw.cc:737` | the receive queue pair is gone, so a late trim gets a plain repair | no | no |
| `rdma-hw.cc:756` | `FindPulledRange` hits, so the range already has a repair outstanding and the request is replayed | inherits the original | only if the original did |
| `rdma-hw.cc:790` | the verdict was `Pull` after an early exit, meaning wrong flow kind, ineligible, or unknown step | no | no |
| `rdma-hw.cc:790` | the verdict was `Pull` or `PullPriority` after `may_forgive` refused | yes | yes |

The replay at line 756 is the common one. Under selective repeat with
steady congestion the same range is trimmed again while its repair is in
flight, and the receiver answers without asking anything.

The sender cannot separate these, because `SendTrimNack` builds an
identical packet for all four. The receiver has to say which it is.

## 2. Domain model

The verdict states two facts, urgency and cause, and the current enum
encodes only urgency. They are not independent: priority exists only
on the refusal path, so a flat sum states the invariant that a bitfield
would leave implicit.

```cpp
// Mirrored by RdmaHw::RecoveryVerdict. The numeric values of the three
// existing cases do not move, so the ABI is unchanged for them.
enum class RecoveryVerdict : uint8_t {
    // Repair. The receiver never consulted the allowance: the domain does
    // not forgive, the flow is not eligible payload, the step is unknown or
    // closed, or the receive queue pair is gone.
    Repair = 0,
    Forgive = 1,
    // The allowance for this (rank, step) is spent, and the step is
    // critical, so the repair also jumps the queue.
    RepairExhaustedPriority = 2,
    // The allowance is spent on an ordinary step.
    RepairExhausted = 3,
};

constexpr bool consulted_allowance(RecoveryVerdict v) {
    switch (v) {
        case RecoveryVerdict::Repair:                  return false;
        case RecoveryVerdict::Forgive:                 return true;
        case RecoveryVerdict::RepairExhausted:         return true;
        case RecoveryVerdict::RepairExhaustedPriority: return true;
    }
}

constexpr bool revokes_exemption(RecoveryVerdict v) {
    switch (v) {
        case RecoveryVerdict::Repair:                  return false;
        case RecoveryVerdict::Forgive:                 return false;
        case RecoveryVerdict::RepairExhausted:         return true;
        case RecoveryVerdict::RepairExhaustedPriority: return true;
    }
}
```

**Decision: a fourth enum case, not a flag bit beside the enum.** Priority
without exhaustion cannot occur, because `evaluate_forgiveness` sets
priority only after `may_forgive` refuses. A separate boolean would make
that combination representable and then rely on a comment to forbid it.
Four closed cases make it unrepresentable and give both switches above
their exhaustiveness check for free.

**Decision: keep 0, 1 and 2 at their current values.** The enum is
duplicated in `rdma-hw.h` as `VERDICT_PULL`, `VERDICT_FORGIVE` and
`VERDICT_PULL_PRIORITY`, and the callback passes a raw `uint8_t`. Holding
the values still means the only edit on the ns-3 side is the new case and
the two predicates.

**Decision: `PulledRange` stores the verdict, not a boolean.**

```cpp
struct PulledRange {
    uint64_t end;
    RecoveryVerdict verdict;   // replaces `bool priority`
};
```

The replay at line 756 must reproduce the request it already sent, which
is now two facts rather than one. Storing the verdict makes the replay a
copy rather than a reconstruction, and it costs nothing: `bool` and
`uint8_t` are the same size in that struct.

## 3. Wire format

One flag, in the bit already free beside the others.

```cpp
enum {
    FLAG_CNP = 0,
    FLAG_TRIM_FTD = 1,
    FLAG_TRIM_LASTHOP = 2,
    FLAG_PULL_PRIORITY = 3,
    // The receiver refused because this (rank, step) has spent its loss
    // allowance. The only signal that ends a congestion-control exemption.
    FLAG_ALLOWANCE_EXHAUSTED = 4,
};
```

`SendTrimNack` takes the verdict in place of `bool priority` and sets both
flags from it. No packet grows: the flags field already exists and the
repair is padded to the 60 byte minimum anyway.

## 4. Edits, in dependency order

| # | file | change |
| --- | --- | --- |
| 1 | `qbb-header.h` | add `FLAG_ALLOWANCE_EXHAUSTED`, plus its setter and getter beside the pull-priority pair |
| 2 | `rdma-hw.h` | add `VERDICT_PULL_EXHAUSTED = 3`; rename the three existing constants to match the frontend names, values unchanged |
| 3 | `rdma-queue-pair.h` | `PulledRange::priority` becomes `PulledRange::verdict` |
| 4 | `rdma-hw.cc` `SendTrimNack` | take `RecoveryVerdict` instead of `bool priority`; set both flags |
| 5 | `rdma-hw.cc` `ReceiveTrimmedData` | pass `Repair` at 737 and 790's early-exit path, the stored verdict at 756, and the verdict at 790 |
| 6 | `rdma-hw.cc` `RecoverTrimmedQueue` | gate the re-arm on the header flag |
| 7 | `ExperimentConfig.hh` | `evaluate_forgiveness` returns the new cases; `RecoveryVerdict` gains its fourth |
| 8 | `entry.h` | the early return at line 220 becomes `Repair`, which is the same value |

Edit 6 is the fix. Edits 1 to 5, 7 and 8 exist to give it something true to
test.

```cpp
// rdma-hw.cc, RecoverTrimmedQueue
const bool exhausted =
    (ch.ack.flags >> qbbHeader::FLAG_ALLOWANCE_EXHAUSTED) & 1;
if (qp->m_cc_exempt && exhausted){
    qp->m_cc_exempt = false;
    qp->m_cc_rearmed_ns = Simulator::Now().GetNanoSeconds();
    ReportTransportEvent("cc_rearmed", 0);
}
```

The placement stays above the stale check and above the rate cut, for the
reason the existing comment gives: a stale refusal is still a refusal, and
the trim that caused it must take its own congestion notification.

## 5. Telemetry

Today a reader cannot tell a replayed request from a refusal. Three
counters on the queue pair, reported like the others:

| counter | incremented at |
| --- | --- |
| `trim_repair_unconsulted` | a request with neither flag set |
| `trim_repair_replayed` | a request whose range was already pulled |
| `trim_repair_exhausted` | a request with `FLAG_ALLOWANCE_EXHAUSTED` |

`trim_repair_exhausted` and `cc_rearmed` should agree to within the flows
that were never exempt. That equality is the fix's own regression test.

## 6. Fixtures

The repository already runs `forgiveness_smoke_8`, `forgiveness_race_8` and
`exempt_smoke_8`. Two assertions are new, and both belong in the race
fixture because it already drives duplicate trims:

1. A replayed request for an already-pulled range leaves `m_cc_exempt`
   set, when the original verdict was not an exhaustion.
2. A request that sets `FLAG_ALLOWANCE_EXHAUSTED` clears it, and
   `cc_rearmed` increments exactly once however many replays follow.

A third belongs in `exempt_smoke_8`: with a budget large enough never to
refuse, `cc_rearmed` is zero. Under today's code that assertion fails,
which is the cleanest demonstration that the defect is real.

## 7. Complexity and risk

Every change is O(1) on the packet path: one shift and mask at the sender,
one enum copy at the receiver. No allocation, no new state, and
`PulledRange` does not grow. The exhaustive switches make edits 2 and 7
compiler-guided, so a missed case is a build failure rather than a silent
default.

The one risk worth naming is the duplicated enum. It lives in
`rdma-hw.h` and `ExperimentConfig.hh` and the callback erases it to
`uint8_t`, so a mismatch compiles and misbehaves. Mitigation: a
`static_assert` in `entry.h` pinning each frontend value to its ns-3
constant, which is four lines and turns the hazard into a build error.

## 8. Re-run plan

The fix changes the exempt arm only. Baselines and admission arms never
execute the re-arm block, because `m_cc_exempt` is false for them, so their
results are unchanged by construction.

**Re-run the exempt arm of every published comparison, and one baseline arm
as a control.** That is 6 exempt arms from run #121 and 14 from run #122,
plus one `fixed_p_low_baseline` re-run whose output must match its archived
bundle byte for byte. Twenty one arms is about a cluster day, against three
days for re-running all eighty.

The control arm is not ceremony. If it does not reproduce, something other
than this fix moved between the runs, and joining new treatment arms against
archived baselines would be invalid.

**Restate, do not adjust.** The corrected numbers replace the published ones
outright. Do not describe the old figures as a lower bound that the new ones
confirm, and do not keep both. The comparison to report is corrected against
corrected: exempt against fixed-low, and exempt against admission, at every
budget already run.

Estimands, unchanged from run #122 so the tables line up: training window
against fixed-low and against admission at each budget; forgiven bytes as a
share of data-parallel bytes; the critical-step share of forgiven bytes; and
`cc_rearmed` per exempt flow, which should collapse from 15 to 29 % toward
the refusal rate alone.

**Expected direction, stated in advance so the result can contradict it.**
Exempt flows keep their exemption longer, so the window should shorten and
the gain should rise above 10.4 to 13.5 %. It may not. A longer exemption
produces more trims, which produce more repairs, so the mechanism partly
undoes itself, and the published numbers may already sit near the peak. A
gain that moves by less than the seed spread of about 0.5 points is a null
result and should be reported as one.
