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

Priority pull goes first, because removing it makes everything after it
smaller.

**Decision: delete the priority pull.** Its intent was to repair a
critical step's data ahead of other repairs once that step's allowance was
spent. The reordering was never built, and `qbb-header.h` says so: the
flag is "advisory", and real ordering "would need the egress scheduler,
which is a hot path". Its whole consumer chain is a counter that reaches
one row of the report, so nothing branches on it. The receiver already
knows the step is critical, so the wire bit tells the sender nothing the
receiver could not count itself. This is a development tree with no
deployed readers, so it goes rather than gets deprecated.

That deletion pays for the fix exactly. `FLAG_PULL_PRIORITY` frees bit 3,
`FLAG_ALLOWANCE_EXHAUSTED` takes it, and the header gains no bit.

With priority gone, the verdict has two independent dimensions and every
combination of them is meaningful.

| dimension | values | what the sender does with it |
| --- | --- | --- |
| will these bytes be re-sent | forgive, repair | advance, or retransmit |
| does the allowance have room | room, spent | keep, or end the exemption |

**Decision: encode the two dimensions separately.** Exhaustion is a fact
about the cell, not about this decision, so binding it to `Repair` would
exclude the case that matters most. A flow spends its allowance by
forgiving, so the moment to learn the allowance is gone is the forgiveness
that empties it, not whatever unrelated trim arrives next. Bound to
repair, the exemption outlives its justification until an arbitrary later
event.

```cpp
// Mirrored by RdmaHw::RecoveryVerdict. Two bits, and no name for the
// absence of either: repair is "not forgive", room is "not spent".
enum : uint8_t {
    kForgive        = 1 << 0,
    kAllowanceSpent = 1 << 1,   // cap reached; no room for a further range
};

// Reads one dimension and ignores the other, which is the test that the
// two are genuinely independent.
constexpr bool revokes_exemption(uint8_t v) { return v & kAllowanceSpent; }
constexpr bool forgave(uint8_t v)           { return v & kForgive; }
```

On the wire it is one bit. The kind is already the packet type, an
acknowledgement against a repair request, so only the allowance state
needs carrying.

`kAllowanceSpent` means `remaining == 0`, which is exact and needs no
threshold. A one byte remainder keeps the exemption alive for one more
event, which is harmless.

**Decision: delete `m_pulled_ranges` and everything that serves it.** The
map exists to replay the request already sent for a range instead of
recomputing the verdict. Recomputation is deterministic, because the
allowance is monotone within a step and never frees, so a duplicate trim
on a pulled range gets the answer it got before. The double charge the
cache appears to prevent is already prevented one branch earlier, where
`UnsettledBytes` returns zero for a range the receiver has accepted and
`ReceiveTrimmedData` acknowledges without consulting the ledger. The cache
guards nothing, and recomputing is additionally correct when the first
request or its repair was lost, which the cache is not.

Out with it go `PulledRange`, `RecordPulledRange`, `FindPulledRange`,
`PruneSettledPulls`, the two pruning call sites, and a per-range map
allocation on the receive path.

**Decision: delete `FLAG_TRIM_FTD`.** `SetTrimFtd` is called twice, true
in `SendTrimNack` and false in the switch's trim header, and `GetTrimFtd`
is called nowhere in the tree. The distinction it encodes is the IP
protocol number, which is what `ReceiveTrim` already branches on.

**Decision: delete the back-to-sender path.** `isFtdRepair` is
`ch.l3Prot == kUecTrimRepairProtocol`, and `SendTrimNack` is the only
producer of that protocol number, so the condition is always true and the
other branch is unreachable. `m_trim_bts_notifications` is therefore
always zero and `m_trim_ftd_repairs` counts what `m_trim_notifications`
counts. The parameter, the branch and both counters go.

## 3. Where the exemption hooks the congestion controller

The one hard boundary in this design. We use DCQCN for convenience, the
approach must hold for any controller, and congestion control is intricate
enough that we neither own it nor want to answer for its fidelity.

**Decision: hook at the transport's dispatch, not inside any controller.**
The transport hands a congestion observation to whichever controller is
configured at exactly three places:

| site | today |
| --- | --- |
| `rdma-hw.cc:530` | `if (cnp && m_cc_mode == 1) cnp_received_mlx(qp)` |
| `rdma-hw.cc:698` | `if (m_cc_mode == 1) cnp_received_mlx(qp)` |
| `rdma-hw.cc:571` | the `HandleAck*` dispatch for modes 3, 7, 8 and 10 |

Each is `if (mode) call the controller`. That is the surface, and the
guard belongs there:

```cpp
// The transport observed congestion for this queue pair. An exempt flow
// does not run its controller at all, whichever controller that is.
bool RdmaHw::DeliverCongestionSignal(Ptr<RdmaQueuePair> qp) {
    if (!qp->m_cc_exempt) return true;
    qp->m_cc_signals_withheld++;
    ReportTransportEvent("cc_signal_withheld", 0);
    return false;
}
```

Today's guard sits at the first line of `cnp_received_mlx`, under the
file's `Mellanox's version of DCQCN` banner. First line or not, that is
inside the box. Moving it out buys a property that can be checked by diff
rather than argued: no line inside any congestion controller changes.

**It also makes the generality claim true.** The present guard covers mode
1 alone, so an exempt flow under HPCC, TIMELY or DCTCP would run its
controller normally. No arm uses those modes, so no measured result is
wrong, but "the approach works with any congestion control" is not
currently true of the code. One predicate at the dispatch makes it true
for all five modes and for NSCC when it arrives, with no per-controller
work.

**The hook is complete for the modes in the tree, and here is how to
re-check it.** A controller can only lower a rate if the transport calls
it or if a timer it scheduled fires. All five current modes are called
from the three sites above. DCQCN's timers, `UpdateAlphaMlx` and
`CheckRateDecreaseMlx`, bootstrap only inside the `m_first_cnp` block of
`cnp_received_mlx`, at lines 1199 and 1201, which an exempt flow never
reaches; the three increase paths hang off those same timers. HPCC and
TIMELY act from `HandleAck*` and schedule nothing independent. When adding
NSCC, repeat this check: enumerate its entry points and its timers, and
confirm every one is downstream of the dispatch.

**Semantics that follow.** An exemption means this queue pair's controller
is not running, and re-arming starts it. A controller beginning from its
initial state is correct rather than stale, and an exempt flow sends at
the rate `AddQueuePair` gave it, still bounded by the link and the static
window, which are transport concerns rather than controller concerns.

**Counter naming.** `cnp_ignored` names a DCQCN artifact.
`cc_signal_withheld` means the same thing under any controller, so the
headline statistic survives a controller change without a rename.

**Behaviour is unchanged for every arm we have run.** For mode 1 the guard
moves from the callee's first line to its call sites, which is the same
test at the same moments. Non-exempt flows never evaluate it. So this
refactor does not invalidate the re-run comparison in section 10.

## 4. Wire format

Two of the four flags are debt, one is live, and the fix needs one. The
result is denser than what it replaces:

```cpp
enum {
    FLAG_CNP = 0,                  // a CNP piggybacked on an ACK; read at two sites
    FLAG_TRIM_LASTHOP = 1,         // was 2
    FLAG_ALLOWANCE_EXHAUSTED = 2,  // was FLAG_PULL_PRIORITY at 3
};
```

`FLAG_TRIM_FTD` and `FLAG_PULL_PRIORITY` go, and the survivors renumber
densely because nothing outside this tree reads the header.

**Decision, and the closest call in this document: the flag rides on the
acknowledgement as well as the repair request.** Revocation is
event-driven, so a flow that forgives the last byte of a cell and then
sees no further trims keeps its exemption, backed by no allowance, until
the step ends. Signalling only on refusal never reaches it. The counter
argument is that the cell is shared by every sender to that rank, so the
acknowledgement reaches only the flow that emptied it and the rest still
learn by refusal, which makes this a partial fix to an unbounded case.

It costs no bandwidth, since the bit exists either way, so the price is one
argument on `SendAck` and one read in `ReceiveAck`. Revisit it if that
code proves awkward.

So `SendTrimNack` takes `bool spent` in place of `bool priority`, and
`SendAck` gains the same argument on the forgiveness path at
`rdma-hw.cc:784`. The field is a `uint16_t` written and read whole, so no
packet changes size and no parser changes.

At the sender, `ReceiveAck` and `RecoverTrimmedQueue` read the same bit
and take the same action, which is the second half of the orthogonality
test: one condition, two arrival paths, no special case.

## 5. Edits, in dependency order

Removals first, then the fix.

| # | file | change |
| --- | --- | --- |
| 1 | `qbb-header.{h,cc}` | delete `FLAG_TRIM_FTD` and `FLAG_PULL_PRIORITY` with their accessors; renumber the survivors densely; add `FLAG_ALLOWANCE_EXHAUSTED` with its setter and getter |
| 2 | `rdma-hw.h` | `VERDICT_PULL_PRIORITY` becomes `VERDICT_REPAIR_EXHAUSTED`, value 2 unchanged |
| 3 | `rdma-queue-pair.{h,cc}` | delete `PulledRange`, `m_pulled_ranges`, `RecordPulledRange`, `FindPulledRange`, `PruneSettledPulls`, `m_priority_pulls`, `m_trim_ftd_repairs`, `m_trim_bts_notifications` |
| 4 | `rdma-hw.cc:690` | drop the `m_priority_pulls` increment |
| 5 | `rdma-hw.cc` `SendTrimNack` | `bool priority` becomes `bool spent`; set the flag |
| 5b | `rdma-hw.cc` `SendAck`, `ReceiveAck` | carry the flag on the forgiveness acknowledgement at 784, and read it at the sender so an acknowledgement can end the exemption |
| 6 | `rdma-hw.cc:788` | `verdict == VERDICT_PULL_PRIORITY` becomes `verdict == VERDICT_REPAIR_EXHAUSTED`. `verdict == VERDICT_FORGIVE` at 765 is unchanged, since no flags share the byte |
| 7 | `rdma-hw.cc` `ReceiveTrimmedData` | delete the `FindPulledRange` short-circuit and the `RecordPulledRange` call; pass `false` at 737, and the verdict at 790 |
| 7b | `rdma-hw.cc` `ReceiveTrim`, `RecoverTrimmedQueue` | drop the `isFtdRepair` parameter and its dead branch; drop `SetTrimFtd` |
| 8 | **`rdma-hw.cc` `RecoverTrimmedQueue` and `ReceiveAck`** | **gate the re-arm on the flag, on both arrival paths. This is the fix.** |
| 8b | `rdma-hw.cc` three dispatch sites, `rdma-queue-pair.h` | move the exemption guard out of `cnp_received_mlx` into `DeliverCongestionSignal`, applied at lines 530, 571 and 698; rename `m_cnp_ignored` to `m_cc_signals_withheld` and the event to `cc_signal_withheld` |
| 9 | `ExperimentConfig.hh` | replace the three-case `RecoveryVerdict` with the two-bit encoding; `evaluate_forgiveness` returns `kForgive` or `kRepair`, and sets `kAllowanceSpent` whenever the cell has no room after the decision; drop the `priority_pulls`, `trim_ftd_repairs` and `trim_bts_notifications` fields and their CSV columns; add `allowance_spent_signalled`; rename the `cnp_ignored` column |
| 10 | `entry.h` | drop the `priority_pulls` export; add four `static_assert` lines pinning each verdict value to its ns-3 constant |
| 11 | `analyze.py` | drop `priority_pulls` from the flow schema and the aggregate; add `allowance_spent_signalled` to `_HOST_TRANSPORT_EVENTS` |
| 12 | `report.py` | drop the "Priority pulls" row |
| 13 | `check_forgiveness.py` | assert `allowance_spent_signalled` equals `cc_rearmed` over exempt flows |
| 14 | tests | `test_analyze.py`, `test_report.py`, `test_compare.py` drop the column; the race fixture gains the two assertions in section 6 |
| 15 | `forgive-protocol.md` | sections 8, 9 and 14 lose the priority language |

Edit 8 is the fix. Everything above it is either the debt removal or what
gives the fix something true to test.

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

## 6. Telemetry

One counter, `allowance_spent_signalled`, incremented when either an
acknowledgement or a repair request arrives with `FLAG_ALLOWANCE_EXHAUSTED`
set.

Everything else is derivable. `m_trim_notifications` already counts every
repair request the sender receives, so requests that did not consult the
allowance are the difference. Splitting those further, into replays and
missing-queue-pair cases, would answer a question we asked once while
finding this defect and will not ask again.

`allowance_spent_signalled` and `cc_rearmed` must agree, to within flows that
were never exempt. That equality is the fix's own regression test, and
`check_forgiveness.py` should assert it.

## 7. Fixtures

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

## 8. Blast radius, checked against the tree

Every consumer of the things this touches, and what happens to it.

| surface | finding |
| --- | --- |
| `qbbHeader::flags` and `CustomHeader::ack.flags` | both `uint16_t`, written and read whole with `WriteU16`/`ReadU16`. Bit 4 is unused, so the packet does not grow and no parser changes |
| `FLAG_PULL_PRIORITY` | read at exactly one site, `rdma-hw.cc:690`, which counts `m_priority_pulls`. Deleted, and its bit reused |
| `priority_pulls` | flows to a CSV column, an `analyze.py` aggregate, one `report.py` row and four test files. Nothing branches on it, so all of it goes |
| `PulledRange` | three consumers. `FindPulledRange` and `RecordPulledRange` change; `PruneSettledPulls` reads only `end` |
| `RecoveryVerdict` | five sites in `ExperimentConfig.hh`, one in `entry.h`, three constants in `rdma-hw.h`. The callback erases to `uint8_t`, so the two enums are pinned by `static_assert` |
| the two equality tests in `rdma-hw.cc` | both stay equality tests, because the verdict keeps three distinct values and no flags share the byte. Renaming `VERDICT_PULL_PRIORITY` makes a missed site a compile error |
| `analyze.py` `_HOST_TRANSPORT_EVENTS` | a frozenset of five names. `allowance_spent_signalled` must be added there or the reporter drops it without complaint |
| `check_forgiveness.py` | its re-arm assertions are conditional, of the form "if a flow re-armed then it was exempt and took a rate cut". Fewer re-arms, or none, keeps them satisfied |
| `exempt_smoke_8` gate | requires that some flow be exempted and that some exempt flow ignore a rate cut. Both stay true; only the revocations fall |
| CNP path | shares the flags word through `FLAG_CNP` at bit 0. Bit 4 is free there too |
| admission domain, ledger law, DCQCN, trimming, ECMP | untouched. `m_cc_exempt` is false in every non-exempt arm, so `RecoverTrimmedQueue` never enters the block at all |

The last row is what makes the re-run cheap: the baselines cannot move.

## 9. Complexity and risk

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

The second risk is the rename. `VERDICT_PULL_PRIORITY` and
`VERDICT_REPAIR_EXHAUSTED` share the value 2, so a site left unrenamed
would still compile if the old constant survived. Delete the old name in
the same commit and every survivor becomes a build failure.

## 10. Re-run plan

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
