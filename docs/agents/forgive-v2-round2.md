# FORGIVE v2, round 2: the analyzer law and the Bernoulli front

Design of record, 2026-09-16, after run #124 (35007858082). It assumes
main `d95d17e` and ns-3 `16d7c9d4d`. Nothing in the simulator changes.

## 1. What run #124 showed

Nine of eighteen arms failed in `analyze.py`, not in the simulator. Each
completed, wrote full telemetry, and then tripped `analyze.py:1263`,
"completed flow cannot deliver more bytes than attempted", whose law is
`data_attempted_bytes >= physical_bytes` for a completed flow with trims.
That law assumes a completed flow sent every byte, and a remainder
forgiveness completes flows that did not.

The law that does hold, on all 376 327 flows of all 9 arms:

```
data_attempted_bytes + forgiven_remainder_bytes >= physical_bytes
```

Joined by seed against run #123's recovery arm at budget 0.1:

| arm | training time | loss, % of DP bytes | exempt flows re-armed |
| --- | --- | --- | --- |
| v1, run #123 | 12.9 to 14.1 % | 6.75 to 6.89 % | 35 to 37 % |
| B25 | 16.0 to 16.2 % | 5.5 to 5.9 % | 7 to 8 % |
| B50 | 13.9 to 14.8 % | 6.3 to 6.6 % | 18 to 20 % |

Bernoulli pacing wins on both axes and monotonically in `p`: B25 gains 2.5
points of time over v1 for 1 point less loss, and B50 falls between them.
The re-arm column is the mechanism, because the coin keeps the cap unspent,
the exemption survives, and the exemption is what recovers time. Whether
the curve keeps rising below 0.25 is the next question.

## 2. Changes

**A. The analyzer law.** `analyze.py`: for every completed flow,
`data_attempted_bytes + forgiven_remainder_bytes >= physical_bytes`,
regardless of trims; message "completed flow must attempt or be forgiven
every byte". The trim precondition goes: a flow with no trims and no
remainder must have attempted everything, and the new law says so.

**B. A derived reading, not a counter.** `forgiven_remainder_unsent_bytes
= sum over completed flows of max(0, physical - attempted)` is the part
of the remainder that was never on the wire; the rest was attempted and
lost to trims. Summary key and report row "Remainder never sent". Nothing
in the simulator counts it, because the two existing counters already
determine it.

**C. Regenerate, do not re-run.** The 9 remainder-forgiving bundles are
complete.
Run the corrected analyzer on each locally and produce their
`summary.json`; the join table above is then reproducible from summaries
rather than from my telemetry scan.

**D. Round 2 wave, gate `forgive_r2`, workflow input `run_forgive_r2`.**

| record | kind | arms | answers |
| --- | --- | --- | --- |
| `regime_64_dcqcn_direct7_4to1_exempt_p005`, 3 seeds | comparison | 12 | the v1 reference at budget 0.05; also the missing dose point |
| `..._p01_b10`, 3 seeds | single | 3 | does the Bernoulli curve keep rising below 0.25 |
| `..._p01_b05`, 3 seeds | single | 3 | where it turns |
| `..._p005_b25`, 3 seeds | single | 3 | B25 at the small budget, against the p005 comparison |
| `..._p02_b25`, 3 seeds | single | 3 | B25 at 0.2, against run #123's p02 recovery arm |

24 arms, one cluster round. Seeds 9550582, 23172535, 94081284. The 18
round-1 records keep gate `forgive_v2` and are not re-run.

Stated in advance: B10 should beat B25 on time by less than B25 beat B50,
with loss below 5 %; B05 should be the first to lose time, because three
quarters of forgivable trims already go to repair at 0.25 and the repair
cost under selective repeat is small but not zero. At budget 0.05, v1
should re-arm more than half its exempt flows and B25 should recover most
of the gap.

## 3. Out of scope

Late data arriving for a forgiven flow is discarded and is not counted;
its upper bound is the "already attempted" share of the remainder. A
counter would need the transport to remember completed five-tuples, which
is state for one number, so the bound stands in for it.

## 4. The contract as a hard guarantee

Added 2026-09-16 after Joe's review of change A. Relaxing the per-flow
law was right, because the contract is not per flow: it is that every
receiving rank gets at least `(1 - p(step))` of what it is owed for every
step, `shed + forgiven <= p(step) x eligible` per (rank, step), with the
remainder counted inside `forgiven`. The analyzer computes that law today
and only reports it, so a violated or unverifiable arm still yields a
summary and a report. Three changes make it a guarantee.

**E. The analyzer fails on the law.** In a forgiving domain, `violated`
raises and so does `not_available` (a forgiving run whose mask or policy
cannot be read is not a result); `not_applicable` stays for admission, and
`no_eligible_traffic` stays for runs with no DP payload. The ledger law
joins `primary_analysis_eligibility` for forgiving domains. The
`ledger_law` result gains `min_delivered_share`, the smallest
`1 - (shed + forgiven) / eligible` over cells with eligible bytes, so a
reader sees "every rank received at least X % of every step" as one
number, and `worst_cell` names its rank and step.

**F. The simulator asserts it at close.** `ForgivenessLedger::close`
throws `std::runtime_error` naming the rank, step, and the three counters
when `(shed + forgiven) x kDecisionScale > eligible x threshold(step)`.
`affords` makes this unreachable, because `eligible` only grows and every
charge was checked against it; the throw is the guarantee that a future
change to `affords`, to the remainder path, or to the ledger cannot ship a
run that breaks the contract. The threshold comes from the same
`clr_mask_by_step` and `p_*_threshold` the verdicts use; a step outside
the mask has no cell to close.

**G. Certify the bundles already in hand.** Run the strengthened analyzer
locally over the 18 arms of run #124 and the 21 recovery arms of run
#123, with each bundle's own `clr_mask.csv`; record `min_delivered_share`
per arm. A single violation retires the arm from every table. When round 2
arrives, the same pass runs before any number is read.

## 5. Certification of runs #123 and #124

Run 2026-09-16 with the analyzer of change E over all 39 forgiving arms in
hand, each against its own `clr_mask.csv`. No arm raised. The worst cell's
delivered share is the contract's floor to four decimals wherever the cap
binds: 0.9000 at budget 0.1 (v1, B25, B50), 0.8000 at 0.2, 0.600 to 0.622
at 0.4, 0.415 to 0.444 at 0.6, 0.611 to 0.620 with the mask off. The
`direct2` cell keeps 0.928 to 0.940 and the no-incast control 1.000. Every
rank received at least `1 - p(step)` of every step in every arm published
so far.

## 6. The two references never run

Yashar's second suggestion, a baseline with no loss tolerance, and the
congestion-neutral recovery arm were planned for the v1 re-run and not
added to the matrix. Every published delta is
against the fixed-low control at `p = 0.005`, which sheds 0.5 % of
data-parallel bytes at admission.

**H. Zero is a legal threshold.** `generate.py` and the C++ parser refuse
`p_low = 0`. They stop refusing it. A zero threshold already means "refuse
every forgiveness, shed nothing" on every verdict path, and `close` with
zero spent passes, so no verdict code changes. One predicate does:
`exemption_eligible` requires `p_high_threshold > 0`, because a step whose
permissive threshold is zero forgives nothing and its acknowledgements
would otherwise grant an exemption against an empty budget. The C++ comment that calls zero "free as a sentinel
because the parser refuses it" is rewritten to say that the sentinel and
the legal zero coincide in meaning.

**I. Nine zero-tolerance singles, gate `forgive_ref`, input
`run_forgive_ref`.** Profiles `regime_64_dcqcn_direct7_4to1_zero.json`,
`regime_64_dcqcn_direct2_2to1_zero.json` and `no_incast_8_zero.json`,
each its exempt sibling with `p_low = p_high = 0` and
`domain = admission`, no pacing, no stop. Records: direct7 at seeds
9550582, 23172535, 94081284, 81117450, 28410270; direct2 at the first
three; no-incast at its own. One arm serves every budget of the dose front
at a given seed, because zero makes `p_high` and the mask inert.

**J. Three congestion-neutral singles, same gate.** Profile
`regime_64_dcqcn_direct7_4to1_recovery_p01.json`, the exempt p01 profile
with `domain = recovery`, at the three seeds. The join is against run
#123's p01 recovery arm and fixed-low baseline.

Stated in advance: the zero reference should be within 0.5 points of
training time of the fixed-low control, so FORGIVE's relief reads about
0.1 points higher against true zero. The congestion-neutral arm should
recover well under half of the exempt arm's 12.9 to 14.1 %, because the
re-arm column of run #124 says the exemption is what the time comes from.
If it recovers most of it, the exemption is unnecessary and the protocol
shrinks.

**K. Three no-controller singles, same gate.** Profile
`regime_64_none_direct7_4to1_zero.json`, the regime map's no-CC profile
(`CC_MODE 12`) with the zero policy, at the three seeds. Run #120 gave the
one-seed figure of 1367 ms; this puts the brute-force row of the table on
paired seeds beside the DCQCN baseline, FORGIVE and the zero reference.

Fifteen records in the gate.

## 7. One budget law

**L. The receiver-local law, for every rule.** At tolerance `p` the cap is
`forgiven <= p x (delivered + forgiven)`, equivalently
`forgiven <= p/(1-p) x delivered`: the receiver measures the budget against
the bytes it has accounted for, kept or forgiven, both of which are its own
counters, while a receiving NIC never sees the sender's launches. At the
end of a step `delivered + forgiven = eligible`, so the ceiling is
`p x eligible`, which is v1's law, and the only difference is when the cap
becomes available, which is whatever is in flight. The simulator keeps one
rule rather than a family: `affords` computes `spent = shed + forgiven + b`
and tests `spent x S <= (delivered + spent) x t` whatever the pacing rule,
and the parser refuses any `pacing.kind` but `none` and `bernoulli`. Pacing
names the coin alone, which declines a range the budget affords rather than
changing what it affords. `eligible`, `register_eligible`, `close`'s throw
and `min_delivered_share` stand unchanged, because the accumulated
denominator is what certifies the contract. `RdmaRangeAlgebra` asserts three
laws of it: a cell that has accounted for every byte it does not spend
affords exactly `0.1 x eligible` at `t = 0.1 S`, and not the `eligible/11` a
delivered-only denominator would give; the rule is monotone in `delivered`
and in `forgiven`; and a cell with `delivered = forgiven = 0` affords a
first range only when `t >= S`, which is the floor the delivered term
creates.

**R. Delivered is per byte, not per message.** A receiving NIC credits a
byte when it accepts it, so `delivered` advances on every accepted payload
range rather than at message completion. `RdmaHw::ReceiveUdp` measures what
one arrival added before the receive state moves, which is what
`AddOutOfOrderRange` would absorb, and reports it through one callback,
`DataAcceptedCallback(sip, dip, sport, dport, bytes)`; a duplicate reports
zero and a forgiven range was absorbed without data, so neither is counted
twice. The frontend credits the cell and the sending rank, and at queue-pair
completion asserts that the flow's accepted bytes equal `q->m_size` less its
forgiven bytes, naming the flow if they do not. Under message-granular
crediting a step whose rank receives one message per peer released no budget
until the step was over, which is a property of the accounting rather than of
the law.

**M. Dispatch by record, not by gate.** The workflow gains an input
`record_filter`, a regular expression tested against `ledger_key` and
applied on top of the gate selection, so a subset of any gate can be
dispatched without a new gate. Empty means no filter.

**N. The v1 point under the unified law.** Three `p01_single` records: the
base exempt profile at seeds 9550582, 23172535 and 94081284, `kind` single,
gate `forgive_v2`,
dispatched with `run_forgive_v2=true` and
`record_filter=exempt-p01-single-seed`. Stated in advance: the arm should
match run #123's p01 recovery arm within the seed spread on both time and
loss, because the in-flight gap is a few hundred KB against a 15 MB cap.
If it does, the receiver-local form replaces the sender-side one in the
specification with nothing lost; if the arm forgives measurably less, the
gap is the price of measuring the budget where the receiver can.

## 8. The cap's base: accounted or owed

Joe's question, 2026-09-16: does the receiver-local law, whose cap grows
only as bytes are accounted for, underperform a cap that is available in
full from the first packet of the step? Nothing measured so far answers
it; the pacing arms speak to the spend rate, not to availability.

**O. A two-case base.** `selection_policy.cap_base` is `"accounted"`
(default, the law of record: `spent x S <= (delivered + spent) x t`) or
`"owed"` (`spent x S <= owed x t`, where `owed` is the bytes the step
will send toward this rank, known at step start). In the ledger it is one
`bool` and one `uint64_t owed` per cell; `affords` picks the base on the
bool; nothing else branches. Bernoulli composes with either.

**P. Where `owed` comes from.** The DP buckets and the all-reduce
schedule are fixed, so the bytes each rank is owed in each step are a
function of the profile alone. `generate.py` computes
`owed_bytes[rank][step]` from the same message sizing it uses to write the
traces and emits it into `experiment.json`; the frontend opens each cell
with it. At `close`, when the base is owed, `eligible == owed` or the run
throws: the hint was exact or the run is not a result. That is the
certification that the collective hint is the accumulated total and not
an approximation of it.

**Q. Six arms, gate `forgive_v2`, filter `owed`.** `p01_owed` (no
pacing) and `p01_owed_b25`, 3 seeds each, joined against #123's p01
recovery arm and #124's B25 respectively. The keys read
`...-exempt-p01-owed-seed-<seed>` and `...-exempt-p01-owed-b25-seed-<seed>`,
so one filter selects every owed arm.

Stated in advance: owed should be within the seed spread of accounted on
time and slightly higher on loss and re-arm share, because it makes the
cap spendable earlier and spending the cap is what ends exemptions. If
owed is faster by more than the spread, the receiver-local law is leaving
time on the table and the specification gains a size hint from the
collective library; if it is within the spread, the law needs no coupling
to the collective library and the paper says so with the number; if it is
slower, the re-arm column says why.

**S. The step stop.** The receiver counts what it has received from a
sender in this step. The moment that reaches `1 - p` of what the sender
owes it for the step, it tells the sender to stop: everything still to
come is inside the budget and would be wasted bandwidth. It is a budget
decision at the receiver and nothing else, not a timer, not a view of
the line, not a check that the sender has finished. It fires near the end
of the step by construction, because that is when `1 - p` has arrived.

Run #124's stop-at-every-arrival arm was not this. It stopped a flow
whenever that one flow's remainder fitted the cap, which for a 2 MB flow against a 15 MB cap is
early in the step, so it spent the exemption while senders were still
sending. The rule here does not look at one flow; it looks at the
sender's whole share of the step.

What it needs. `owed` per (sender, receiver, step), which `generate.py`
derives from the same per-peer message sizing as the per-rank total (the
cell's `owed` is its sum over senders), and `delivered` per (sender,
receiver, step), which the per-byte arrival accounting of change R
already provides once it is keyed by sender. With
`selection_policy.step_stop = true` (legal only with `cap_base = owed`,
and the transport asks at every accepted arrival),
`evaluate_remainder` answers forgive for a flow only when
`delivered_from(src) >= (1 - p) x owed_from(src)`; the remainder is then
forgiven whole, bounded by the cap as always. Flows from that sender still
receiving are stopped at their next packet; a flow waiting on a repair is
left to its repair, which is cheap.

Six arms in #127, seeds 9550582, 23172535, 94081284: `p01_stepstop`, the
stop on the law of record, ledger keys
`...-exempt-p01-stepstop-seed-<seed>`, and `p01_b25_stepstop`, the design
of record entire, keys `...-exempt-p01-b25-stepstop-seed-<seed>`. The stop
reads the step's plan, which every forgiving domain carries, so it needs
no cap base of its own and the owed base stays the separate ablation it
was.

Stated in advance: loss settles at `p` on every permissive step, as any
stop that uses its budget must; the re-arm share stays near v1's, because
the cap is spent only after `1 - p` has arrived from each sender; time
should be at or above v1, the difference being the bandwidth the last
`p` of every sender's share no longer occupies. If the gain is inside the
seed spread, the stop is the completeness item it was meant to be and the
paper says so with the number.

## 9. The coin is drawn per trimmed arrival, and a stopped sender stops at once

Joe, 2026-09-16. Two corrections to how the receiver decides.

**T. A fresh coin per trim.** The coin is `hash(flow, range start,
attempt)` with `attempt` the flow's count of verdicts asked so far, so
every trim of a range draws again; a range the coin refused is re-tried
on its next trim against the cap as it stands then, which under the
receiver-local law has grown with delivery in the meantime. Nothing about
a range is remembered between trims. Paired arms still draw the same coins
because the attempt counter is deterministic. Runs #124 and #125 measured
a coin fixed per range; B25 and B50 re-run under this rule in #127, and
#125's Bernoulli arms re-run only if the two rules differ by more than
the seed spread.

**U. A stopped sender stops at once.** When a sender crosses `1 - p` of
its share, every open flow from that sender into the rank is stopped at
that moment, not at each flow's next arrival: the frontend asks the
transport to run the remainder path on each of those queue pairs. One
call into the transport keyed by the flow's five-tuple; the remainder
verdict, the acknowledgement and the accounting are unchanged.

## 10. When the controller re-engages

Joe, 2026-09-16. The temporal shape of FORGIVE, per receiving rank and per
step: the sender ignores the controller while the receiver still has
allowance to forgive; when there is almost nothing left to forgive, the
sender switches to the controller for the rest of the step; the next step
opens a fresh allowance. Two rules that were considered and rejected:
a spent report against the receiver-local cap, which is near zero at
step start and so fires on the first burst; and a symmetric rule (obey
while the last report says spent, withhold while it says room), which
flips with every report and sets the flow's rate by the flap frequency.
A third, revocation against the step total while affording under the
receiver-local cap, was rejected because under real congestion the
receiver-local cap refuses trims for want of vested budget, `forgiven`
never grows, and the controller never returns while the fabric throws
everything away.

**V. Two "cannot afford", kept distinct.** Joe's rule. The soft one is
the vesting cap, `forgiven + b > p x (delivered + forgiven)`: the
allowance has not vested yet, the trim is repaired, no bit is set,
because the cap will grow and this refusal says nothing about the future.
The hard one is the step's total, `forgiven + 4096 > p x owed` (one
packet's payload being the largest range): no further range will ever be
affordable this step, the bit is set, and the controller returns for the
rest of the step. `owed` per (sender, receiver, step) comes from the
collective library's hint, one table per step, and is the only external
number the receiver needs.

The soft cap alone would let a congested sender flood forever: delivery
stalls, the soft cap stalls, every trim is refused softly, `forgiven`
never grows and the hard line is never reached. So the soft side keeps
one count, `refused_soft`, the bytes it declined for want of vested
allowance, and the hard condition has a second clause: when
`refused_soft > p x owed - forgiven`, the receiver is repairing more than
it could ever be allowed to absorb this step, which is congestion beyond
tolerance rather than vesting lag, and the bit is set. No window, no
threshold beyond `p`, nothing an estimator would add.

| decision | reads | sets the bit |
| --- | --- | --- |
| forgive now | the soft cap, then the coin | no |
| repair, soft | the soft cap refused; `refused_soft += b` | no |
| spent | `forgiven + 4096 > p x owed` or `refused_soft > p x owed - forgiven` | yes, once, monotone within the step |

Coin refusals set nothing and count in neither. The step stop reads the
hard side, `1 - p` of `owed` from a sender. `cap_base = owed`, the hard
cap used for affordability too (full allowance from the first packet), is
the ablation.

A receiver-side congestion estimator (trim fraction over a window with a
threshold) was considered and set aside: it is a second controller with a
set point, re-deriving the signal the sender already receives and
discards. Whether budget-based revocation bounds the exempt flows'
aggression enough is read from #127's TP all-reduce spans and re-sent
bytes against the fixed-low baseline, with arm D as the extreme.

**W. The exemption is granted by the receiver.** The sender obeys its
controller until the first acknowledgement from the receiver arrives with
the spent bit clear on a permissive step; from then it withholds signals
until a report with the bit set. The sender never reads the receiver's
cell. One round trip is spent obeying at the start of every flow.

**X. Reference arm D.** `p01_noreengage`: the exemption never ends on a
permissive step, the budget bounds loss only. Three seeds. It is the
exemption's ceiling and prices what revocation costs us in time against
what it saves the fabric in re-sent bytes and TP collective time.

#127, budget 0.1, gate `forgive_v2`, filter
`exempt-p01-(single|owed|b25|stepstop|noreengage)`: the design of record
is the soft law with the coin and the stop (`p01_b25_stepstop`, 3), and
every other arm removes one piece of it. The law's v1 point
(`p01_single`, 3) drops both, the coin alone (`p01_b25`, 3) and the stop
alone (`p01_stepstop`, 3) drop one each, the owed ablation (`p01_owed`,
3) and the same under the coin (`p01_owed_b25`, 3) replace the vesting
cap with the plan, and D (3) never re-engages. Twenty-one arms. Read with
two extra columns per arm: TP all-reduce span and re-sent bytes against
the fixed-low baseline.

## 11. Pooling and the application's rescale

Joe, 2026-09-16. The budget stays pooled per (receiving rank, step): the
fabric decides which sender's bytes are lost, and a rank may receive 80 %
of one peer's contribution and 40 % of another's against a 60 % average.
Two facts from [lit-review-uneven-loss.md](lit-review-uneven-loss.md)
decide how that is stated.

**Assumption, stated in the specification.** The application divides
each element of the reduce-scatter by the number of contributions that
arrived for it, and the receiver hands the application the forgiven
ranges of every completed message; the receiver already keeps them as the
absorbed out-of-order set, so this is an interface sentence and not a
mechanism. With that division an element averaged over fewer workers is
an unbiased estimate from a smaller batch, and the per-sender
distribution of loss stops mattering for the fixed point; what remains is
a variance term. The DBLP evidence of 40 % on GPT-2 was sender-side
shedding without rescale, so it is a conservative bound for the rescaled
reduce-scatter.

**What the assumption does not cover.** The all-gather half. A missing
reduced value has no local substitute, dividing by anything does not help,
and the replica that missed it diverges from the others on those elements.
Every system in the review that touched both halves bounded the second
tighter and none quantified a separate tolerance. Our budget does not
distinguish the halves; whether the simulator's operation context can
identify a DP message's half decides whether a per-half `p` is a knob or
a stated limitation, and that check has not been made.

**What settles it.** The GPT-2 injection experiment on the May rig: the
per-(sender, receiver, step) loss pattern from a bundle, uneven as
measured against the same total spread evenly, with and without the
rescale, both halves separately.
