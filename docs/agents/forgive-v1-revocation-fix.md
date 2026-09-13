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

The verdict states two independent facts about a repair, urgency and
cause, and the byte encodes only urgency today. Priority means the step is
critical. Exhaustion means the allowance is spent. They co-occur in the
current code only because `evaluate_forgiveness` computes priority inside
the refusal branch, which is incidental rather than essential.

The callback returns one `uint8_t`, so both facts share it. Encode them as
a kind plus two orthogonal flags, which is what the wire already does.

```cpp
// Mirrored by RdmaHw::RecoveryVerdict. Bit 0 is the kind; bits 1 and 2 are
// attributes of a repair. Pull (0), Forgive (1) and PullPriority (2) keep
// their present values, so no existing arm changes behaviour.
enum : uint8_t {
    kVerdictRepair    = 0,       // bit 0 clear
    kVerdictForgive   = 1,       // bit 0 set
    kRepairPriority   = 1 << 1,  // the step is critical, so repair it first
    kRepairExhausted  = 1 << 2,  // the allowance for this (rank, step) is spent
};

constexpr bool forgave(uint8_t v)      { return (v & 1) == kVerdictForgive; }
constexpr bool is_priority(uint8_t v)  { return !forgave(v) && (v & kRepairPriority); }
constexpr bool revokes_exemption(uint8_t v) {
    return !forgave(v) && (v & kRepairExhausted);
}
```

**Decision: two orthogonal flags, not a fourth enum case.** A case named
`RepairExhaustedPriority` would encode today's coupling as a type-level
invariant, so a later choice to prioritise critical-step repairs whatever
their cause would need a new case and a new wire mapping. The flags cost
nothing and match the header, which has carried `FLAG_PULL_PRIORITY` and
will carry `FLAG_ALLOWANCE_EXHAUSTED` as separate bits regardless.

**Decision: keep 0, 1 and 2 at their present values.** `PullPriority` is
`kVerdictRepair | kRepairPriority`, which is 2, so the three constants in
`rdma-hw.h` need no renumbering and no arm that never exhausts its
allowance changes behaviour.

**The one illegal state left is a forgiveness with flags set.** Nothing
constructs it, and `forgave` masks it out, so a stray flag on a
forgiveness is inert rather than harmful. Assert it once in
`evaluate_forgiveness` rather than modelling around it.

**Decision: `PulledRange` stores the verdict byte, not a boolean.**

```cpp
struct PulledRange {
    uint64_t end;
    uint8_t  verdict;   // replaces `bool priority`
};
```

The replay at line 756 must reproduce the request it already sent. It
matters only when the original request or its repair was lost, since
otherwise the exemption is already gone and a second revocation is a no-op.
Control packets take the high-priority queue and no control drop occurs in
these runs, so this is correctness under a case the simulation does not
currently produce. Storing the byte costs nothing over the bool it
replaces.

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
| 2 | `rdma-hw.h` | add the two flag constants beside the three verdict values, which keep their numbers |
| 3 | `rdma-queue-pair.h` | `PulledRange::priority` becomes `PulledRange::verdict` |
| 4 | `rdma-hw.cc` `SendTrimNack` | take the verdict byte instead of `bool priority`; set both flags from it |
| 4b | `rdma-hw.cc:765, 788` | `verdict == VERDICT_FORGIVE` becomes `forgave(verdict)`, and `verdict == VERDICT_PULL_PRIORITY` becomes `is_priority(verdict)`. Equality breaks once flags ride in the byte, and this is the one place a missed edit compiles and misbehaves |
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

One counter, `trim_repair_exhausted`, incremented when a repair request
arrives with `FLAG_ALLOWANCE_EXHAUSTED` set.

Everything else is derivable. `m_trim_notifications` already counts every
repair request the sender receives, so requests that did not consult the
allowance are the difference. Splitting those further, into replays and
missing-queue-pair cases, would answer a question we asked once while
finding this defect and will not ask again.

`trim_repair_exhausted` and `cc_rearmed` must agree, to within flows that
were never exempt. That equality is the fix's own regression test, and
`check_forgiveness.py` should assert it.

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

## 7. Blast radius, checked against the tree

Every consumer of the things this touches, and what happens to it.

| surface | finding |
| --- | --- |
| `qbbHeader::flags` and `CustomHeader::ack.flags` | both `uint16_t`, written and read whole with `WriteU16`/`ReadU16`. Bit 4 is unused, so the packet does not grow and no parser changes |
| `FLAG_PULL_PRIORITY` | read at exactly one site, `rdma-hw.cc:690`, which counts `m_priority_pulls`. Untouched |
| `PulledRange` | three consumers. `FindPulledRange` and `RecordPulledRange` change; `PruneSettledPulls` reads only `end` |
| `RecoveryVerdict` | five sites in `ExperimentConfig.hh`, one in `entry.h`, three constants in `rdma-hw.h`. The callback erases to `uint8_t`, so the two enums are pinned by `static_assert` |
| the two equality tests in `rdma-hw.cc` | `verdict == VERDICT_FORGIVE` and `verdict == VERDICT_PULL_PRIORITY` must become mask tests. This is the only edit that compiles and misbehaves if missed |
| `analyze.py` `_HOST_TRANSPORT_EVENTS` | a frozenset of five names. `trim_repair_exhausted` must be added there or the reporter drops it without complaint |
| `check_forgiveness.py` | its re-arm assertions are conditional, of the form "if a flow re-armed then it was exempt and took a rate cut". Fewer re-arms, or none, keeps them satisfied |
| `exempt_smoke_8` gate | requires that some flow be exempted and that some exempt flow ignore a rate cut. Both stay true; only the revocations fall |
| CNP path | shares the flags word through `FLAG_CNP` at bit 0. Bit 4 is free there too |
| admission domain, ledger law, DCQCN, trimming, ECMP | untouched. `m_cc_exempt` is false in every non-exempt arm, so `RecoverTrimmedQueue` never enters the block at all |

The last row is what makes the re-run cheap: the baselines cannot move.

## 8. Complexity and risk

Every change is O(1) on the packet path: one shift and mask at the sender,
one enum copy at the receiver. No allocation, no new state, and
`PulledRange` does not grow. The exhaustive switches make edits 2 and 7
compiler-guided, so a missed case is a build failure rather than a silent
default.

Two risks, both turned into build failures rather than silent drift.

The enum is duplicated across `rdma-hw.h` and `ExperimentConfig.hh` and the
callback erases it to `uint8_t`, so a mismatch compiles and misbehaves.
A `static_assert` in `entry.h` pins each frontend value and flag to its
ns-3 constant, which is five lines.

The equality tests at `rdma-hw.cc:765` and `788` are correct today and
wrong the moment flags share the byte. Deleting `VERDICT_PULL_PRIORITY`
from the header after the mask helpers land makes any surviving comparison
a compile error.

## 9. Re-run plan

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
