# Task: fix the exemption revocation, then re-measure FORGIVE v1

Handoff document, written 2026-09-13. Nothing here is implemented yet.

An agent picking this up should be able to work from this file alone.
Sections 1 to 3 say what to do, section 4 says what not to touch, sections
5 to 8 are build, dispatch and read, and section 9 holds the reasoning
behind each decision in case you need to argue with it.

Background if you want it: [forgive-protocol.md](forgive-protocol.md) is
the protocol as built, [forgive-v2-design.md](forgive-v2-design.md) is the
next change after this one. Do not start v2 until this is merged and its wave
is read.

## 1. The defect, in one paragraph

`RecoverTrimmedQueue` clears `m_cc_exempt` at its top, before any other
check, on every repair request that reaches the sender. The receiver emits
an identical request from three sites and only one consulted the loss
allowance, so an exemption dies to events that say nothing about the
budget. The protocol claims the exemption ends when the receiver refuses
to forgive. It does not.

| site | condition | consulted the allowance |
| --- | --- | --- |
| `rdma-hw.cc:737` | the receive queue pair is gone, so a late trim gets a plain repair | no |
| `rdma-hw.cc:756` | `FindPulledRange` hits, so the range already has a repair outstanding and the request is replayed | no |
| `rdma-hw.cc:790` | the verdict refused | yes |

The middle site is the common one: under selective repeat with steady
congestion the same range is trimmed again while its repair is in flight.

Consequence for published results: runs #121 and #122 measured a protocol
whose exemption was weaker than the specification's. Their loss figures
are exact, since the ledger is untouched, and their baselines are
unaffected, since `m_cc_exempt` is false there. Only the exempt arm moves.

## 2. What to build

The receiver tells the sender one thing it cannot work out for itself:
this cell has no allowance left. The sender ends the exemption on that and
on nothing else.

```cpp
// ExperimentConfig.hh, mirrored by RdmaHw::RecoveryVerdict.
// Two bits. Repair is "not forgive"; room is "not spent".
enum : uint8_t {
    kForgive        = 1 << 0,
    kAllowanceSpent = 1 << 1,   // cap reached, no room for a further range
};
constexpr bool forgave(uint8_t v)           { return v & kForgive; }
constexpr bool revokes_exemption(uint8_t v) { return v & kAllowanceSpent; }
```

On the wire it is one bit. The kind is already the packet type, an
acknowledgement against a repair request, so only the allowance state
needs carrying. `kAllowanceSpent` means `remaining == 0` exactly; a one
byte remainder keeps the exemption alive one more event, which is
harmless.

Flags after the change, renumbered densely because nothing outside this
tree reads the header:

```cpp
enum {
    FLAG_CNP = 0,
    FLAG_TRIM_LASTHOP = 1,         // was 2
    FLAG_ALLOWANCE_EXHAUSTED = 2,  // was FLAG_PULL_PRIORITY at 3
};
```

And the fix itself:

```cpp
// rdma-hw.cc, RecoverTrimmedQueue and the equivalent in ReceiveAck
const bool spent = (ch.ack.flags >> qbbHeader::FLAG_ALLOWANCE_EXHAUSTED) & 1;
if (qp->m_cc_exempt && spent){
    qp->m_cc_exempt = false;
    qp->m_cc_rearmed_ns = Simulator::Now().GetNanoSeconds();
    ReportTransportEvent("cc_rearmed", 0);
}
```

Keep the placement above the stale check and above the rate cut. A stale
refusal is still a refusal, and the trim that caused it must take its own
congestion notification.

## 3. Edits, in dependency order

Debt removals first, because they make the fix smaller. Every one is
justified in section 9; do not skip them on the grounds that they are not
the bug.

| # | file | change |
| --- | --- | --- |
| 1 | `qbb-header.{h,cc}` | delete `FLAG_TRIM_FTD` and `FLAG_PULL_PRIORITY` with their accessors; renumber survivors; add `FLAG_ALLOWANCE_EXHAUSTED` with setter and getter |
| 2 | `rdma-hw.h` | replace the three `VERDICT_*` constants with the two-bit encoding from section 2 |
| 3 | `rdma-queue-pair.{h,cc}` | delete `PulledRange`, `m_pulled_ranges`, `RecordPulledRange`, `FindPulledRange`, `PruneSettledPulls`, `m_priority_pulls`, `m_trim_ftd_repairs`, `m_trim_bts_notifications`; rename `m_cnp_ignored` to `m_cc_signals_withheld` |
| 4 | `rdma-hw.cc:690` | drop the `m_priority_pulls` increment |
| 5 | `rdma-hw.cc` `SendTrimNack` | `bool priority` becomes `bool spent`; set `FLAG_ALLOWANCE_EXHAUSTED` from it |
| 6 | `rdma-hw.cc` `SendAck` at 784, `ReceiveAck` | carry the same bit on the forgiveness acknowledgement, and read it at the sender |
| 7 | `rdma-hw.cc` `ReceiveTrimmedData` | delete the `FindPulledRange` short-circuit and the `RecordPulledRange` call; pass `false` at 737, and the verdict's spent bit at 790 |
| 8 | `rdma-hw.cc` `ReceiveTrim`, `RecoverTrimmedQueue` | drop the `isFtdRepair` parameter and its unreachable branch |
| 9 | **`rdma-hw.cc` `RecoverTrimmedQueue` and `ReceiveAck`** | **gate the re-arm on the bit, on both arrival paths. This is the fix.** |
| 10 | `rdma-hw.{h,cc}` at 530, 571, 698 | move the exemption guard out of `cnp_received_mlx` into a new `DeliverCongestionSignal(qp)` applied at all three dispatch sites; see section 4 |
| 11 | `ExperimentConfig.hh` | the two-bit encoding; `evaluate_forgiveness` returns `kForgive` or 0 and ors in `kAllowanceSpent` when the cell has no room after the decision; drop the `priority_pulls`, `trim_ftd_repairs`, `trim_bts_notifications` fields and CSV columns; rename the `cnp_ignored` column to `cc_signal_withheld`; add `allowance_spent_signalled` |
| 12 | `entry.h` | drop the `priority_pulls` export; add `static_assert` lines pinning each frontend constant to its ns-3 counterpart |
| 13 | `analyze.py` | drop `priority_pulls` from the flow schema and the aggregate; follow the rename; add `allowance_spent_signalled` to `_HOST_TRANSPORT_EVENTS` |
| 14 | `report.py` | drop the "Priority pulls" row |
| 15 | `check_forgiveness.py` | assert `allowance_spent_signalled` equals `cc_rearmed` summed over exempt flows |
| 16 | tests | `test_analyze.py`, `test_report.py`, `test_compare.py` drop the column and follow the rename; the race fixture gains the assertions in section 6 |
| 17 | `forgive-protocol.md` | sections 8, 9 and 14 lose the priority language and gain the new counter names |

**If you are short of time**, edits 1, 5, 7, 9 and 16 are the minimum that
makes the measurement valid. The rest is debt removal and naming, and none
of it moves a number. Do not ship a partial set without recording which
edits landed.

**The risky edits are 11, 13 and 16.** They change the CSV schema, and a
mistake there fails silently: `analyze.py` drops any transport event not
listed in `_HOST_TRANSPORT_EVENTS`, so a missing entry produces a bundle
with no complaint and no data. Inspect a smoke bundle by hand before
dispatching a wave.

## 4. Do not touch the congestion controller

The one hard boundary. We use DCQCN for convenience, the approach must
hold for any controller, and congestion control is intricate enough that
we neither own it nor want to answer for its fidelity.

The transport hands a congestion observation to whichever controller is
configured at exactly three places, and the guard belongs at those, not
inside any handler:

| site | today |
| --- | --- |
| `rdma-hw.cc:530` | `if (cnp && m_cc_mode == 1) cnp_received_mlx(qp)` |
| `rdma-hw.cc:698` | `if (m_cc_mode == 1) cnp_received_mlx(qp)` |
| `rdma-hw.cc:571` | the `HandleAck*` dispatch for modes 3, 7, 8 and 10 |

```cpp
bool RdmaHw::DeliverCongestionSignal(Ptr<RdmaQueuePair> qp) {
    if (!qp->m_cc_exempt) return true;
    qp->m_cc_signals_withheld++;
    ReportTransportEvent("cc_signal_withheld", 0);
    return false;
}
```

After edit 10, **no line inside any congestion controller changes**. Check
that with `git diff` before pushing; the property is the answer to the
reviewer question we most want to avoid.

Do not "improve" this by guarding rate writes, consolidating
`ChangeRate`, or letting the controller run and discarding its output.
Each of those makes DCQCN's behaviour our claim to defend.

An exempt flow runs no controller at all, and that is complete for the
five modes in the tree. A controller lowers a rate only if the transport
calls it or if a timer it scheduled fires. All five are called from the
three sites above. DCQCN's `UpdateAlphaMlx` and `CheckRateDecreaseMlx`
bootstrap only inside the `m_first_cnp` block at lines 1199 and 1201,
which an exempt flow never reaches, and the three increase paths hang off
those timers. HPCC and TIMELY act from `HandleAck*` and schedule nothing
independent. When NSCC arrives, repeat that enumeration rather than
assuming it still holds.

## 5. Build and test

```bash
# ns-3 fork, from the repository root. See rootless-ephemeral-build.md if
# the toolchain is missing.
cd extern/network_backend/ns-3 && ./ns3 build && cd -

# Native fixtures for the recovery domain. Includes the range-algebra
# binary, the only thing that exercises the straddle branches.
experiments/ring_3d/forgiveness_smoke.sh

# Python suites.
uv run --locked python -m unittest discover -s experiments/ring_3d/tests -v
uv run --locked python -m unittest discover -s .github/scripts/tests -t .github/scripts -v
```

## 6. Fixture assertions to add

Two in `forgiveness_race_8`, which already drives duplicate trims:

1. A replayed request for an already-pulled range leaves `m_cc_exempt`
   set. Under today's code this fails, which is the demonstration that the
   defect is real, so write it before the fix and watch it go red.
2. A request that sets `FLAG_ALLOWANCE_EXHAUSTED` clears it, and
   `cc_rearmed` increments exactly once however many further requests
   arrive.

One in `exempt_smoke_8`: with a budget large enough never to refuse,
`cc_rearmed` is zero.

## 7. Dispatch the re-run

The harness runs whole comparisons, not single arms, so re-running the
exempt arms means re-running the two gates that contain them. That also
re-runs their baselines, which is better than a spot check: if a baseline
does not reproduce its archived bundle, something other than this fix
moved.

7 records under gate `forgive` and 14 under `forgive_dose`, so 21
comparisons at 4 arms each, 84 arms. Run #122 did 56 arms in 15.6 hours,
so budget about a day.

```bash
gh workflow run <workflow> -R BulkyCI/astra-sim \
  -f run_always=false \
  -f run_forgive_studies=true \
  -f run_forgive_dose=true
```

Leave `run_always=false`. The three aggregate jobs need the `always`
family and will fail without it; that is a known harness footnote, not a
result, and every experiment job still succeeds.

Do not push to `main` to trigger this. A plain push fires the full wave.
Use the dispatch, and put `[skip ci]` in the head commit if you commit the
code before you are ready to run.

## 8. How to read it

Same estimands as run #122, so the tables line up.

| quantity | against |
| --- | --- |
| training window | fixed-low, and admission, at each budget |
| gradient forgiven, share of data-parallel bytes | the same |
| critical-step share of forgiven bytes | should stay at 1.0 to 1.5 % masked |
| `cc_rearmed` per exempt flow | should collapse from the published 15 to 29 % |
| `allowance_spent_signalled` against `cc_rearmed` | must agree over exempt flows |
| one `fixed_p_low_baseline` against its archived bundle | must match, or the join is invalid |

**Stated in advance so the result can contradict it.** Exempt flows keep
their exemption longer, so the window should shorten and the gain should
rise above the published 10.4 to 13.5 %. It may not: a longer exemption
produces more trims, which produce more repairs, so the mechanism partly
undoes itself and the published points may already sit near the peak. A
move smaller than the seed spread of about 0.5 points is a null result and
should be reported as one.

**Restate, do not adjust.** The corrected numbers replace the published
ones. Do not describe the old figures as a lower bound the new ones
confirm, and do not keep both.

Then update, in this order: `run-121-cc-exempt-readout.md`,
`figure-data.md`, and the two slide decks.

## 9. Why each decision, if you need to argue with it

**Two bits, not three.** A named constant for repair would be a name for
zero. The kind and the allowance state are independent, and
`revokes_exemption` reading one while ignoring the other is the test that
they are.

**The bit rides on the acknowledgement too.** The closest call here. A
flow spends its allowance by forgiving, so the event that empties a cell
is a forgiveness, and signalling only on refusal leaves that flow exempt
with nothing behind it until some later unrelated trim. Against that, the
cell is shared by every sender to the rank, so the acknowledgement reaches
only the flow that emptied it. It costs no bandwidth, so the price is one
argument on `SendAck` and one read in `ReceiveAck`.

**Delete the priority pull.** Its intent was to repair a critical step's
data ahead of others. The reordering was never built, and `qbb-header.h`
says so: the flag is advisory and real ordering "would need the egress
scheduler, which is a hot path". Its consumer chain ends at one row of the
report. Deleting it frees the bit the fix needs, so the removal pays for
the addition exactly.

**Delete `m_pulled_ranges`.** It replays a request instead of recomputing
the verdict, and recomputation is deterministic because the allowance is
monotone within a step and never frees. The double charge it appears to
prevent is already prevented where `UnsettledBytes` returns zero for an
accepted range. It guards nothing, and recomputing is also correct when
the first request was lost, which the cache is not.

**Delete `FLAG_TRIM_FTD` and the back-to-sender path.** `GetTrimFtd` has
no callers in the tree. `isFtdRepair` is
`ch.l3Prot == kUecTrimRepairProtocol` and `SendTrimNack` is that
protocol's only producer, so the condition is always true, the other
branch is unreachable, and `m_trim_bts_notifications` is a column of zeros
in every bundle shipped so far.

**No backward compatibility is owed.** Nothing is deployed and nothing
external reads this wire format. Renumber the flags, rename the counters,
and delete what a designer starting fresh would not have written.
