# FORGIVE v2, round 2: the analyzer law and the Bernoulli front

Design of record, 2026-09-16, after run #124 (35007858082). It assumes
main `d95d17e` and ns-3 `16d7c9d4d`. Nothing in the simulator changes.

## 1. What run #124 showed

Nine of eighteen arms failed in `analyze.py`, not in the simulator. Every
S, S0 and VS arm completed, wrote full telemetry, and then tripped
`analyze.py:1263`, "completed flow cannot deliver more bytes than
attempted", whose law is `data_attempted_bytes >= physical_bytes` for a
completed flow with trims. That law assumes a completed flow sent every
byte, and the straggler stop exists to complete flows that did not.

The law that does hold, on all 376 327 flows of all 9 arms:

```
data_attempted_bytes + forgiven_remainder_bytes >= physical_bytes
```

Joined by seed against run #123's recovery arm at budget 0.1:

| arm | training time | loss, % of DP bytes | remainder, % of DP | exempt flows re-armed |
| --- | --- | --- | ---: | --- |
| v1, run #123 | 12.9 to 14.1 % | 6.75 to 6.89 % | 0 | 35 to 37 % |
| B25 | 16.0 to 16.2 % | 5.5 to 5.9 % | 0 | 7 to 8 % |
| B50 | 13.9 to 14.8 % | 6.3 to 6.6 % | 0 | 18 to 20 % |
| V | 13.2 to 13.8 % | 5.9 to 6.0 % | 0 | 35 to 40 % |
| S, 250 us | 13.3 to 14.1 % | 6.8 to 7.0 % | 0.25 | 33 to 34 % |
| S0 | 7.7 to 8.7 % | 8.1 % | 4.2 to 4.4 | 56 to 58 % |
| VS | 13.7 to 14.4 % | 5.8 to 6.2 % | 0.40 to 0.45 | 36 to 37 % |

Readings.

- Bernoulli pacing wins on both axes and monotonically in `p`: B25 gains
  2.5 points of time over v1 for 1 point less loss, B50 falls between them. The
  re-arm column is the mechanism: the coin keeps the cap unspent, the
  exemption survives, and the exemption is what recovers time. Whether the
  curve keeps rising below 0.25 is the next question.
- Vesting saves 0.8 points of loss and no time. Not worth its field unless
  round 2 changes that.
- The straggler stop at 250 us is null. Of its forgiven remainder, 83 %
  had already been attempted, trimmed and awaiting repair; only 16 to 18 %
  was never sent. "Saves transmission too" is one sixth true.
- S0, MLT's stop-at-(1-p), loses 5 points against v1 and spends the cap
  to the byte on every permissive step (956.96 MB per step, exactly
  `0.1 x eligible`). The ceiling became a target, as predicted.

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

**C. Regenerate, do not re-run.** The 9 straggler bundles are complete.
Run the corrected analyzer on each locally and produce their
`summary.json`; the join table above is then reproducible from summaries
rather than from my telemetry scan.

**D. Round 2 wave, gate `forgive_r2`, workflow input `run_forgive_r2`.**

| record | kind | arms | answers |
| --- | --- | --- | --- |
| `regime_64_dcqcn_direct7_4to1_exempt_p005`, 3 seeds | comparison | 12 | the v1 reference at budget 0.05, inside MLT's tolerable range; also the missing dose point |
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
binds: 0.9000 at budget 0.1 (v1, B25, B50, S, S0), 0.8000 at 0.2, 0.600 to
0.622 at 0.4, 0.415 to 0.444 at 0.6, 0.611 to 0.620 with the mask off.
Vesting and the vesting-plus-straggler arms leave 1.0 to 1.1 points
unspent at their worst cell (0.910 to 0.911), the `direct2` cell 0.928 to
0.940, and the no-incast control 1.000. Every rank received at least
`1 - p(step)` of every step in every arm published so far.

## 6. The two references never run

Yashar's second suggestion, a baseline with no loss tolerance, and the
congestion-neutral recovery arm from phase 3 of
[next-steps-after-v1-fix.md](next-steps-after-v1-fix.md) were planned for
the v1 re-run and not added to the matrix. Every published delta is
against the fixed-low control at `p = 0.005`, which sheds about 0.4 % of
data-parallel bytes at admission.

**H. Zero is a legal threshold.** `generate.py` and the C++ parser refuse
`p_low = 0`. They stop refusing it. A zero threshold already means "refuse
every forgiveness, shed nothing" on every verdict path, and `close` with
zero spent passes, so no verdict code changes. One predicate does:
`evaluate_congestion_exemption` requires `p_high_threshold > 0`, because
`affords(cell, 0, pacing, 0)` is true and would grant an exemption against
an empty budget. The C++ comment that calls zero "free as a sentinel
because the parser refuses it" is rewritten to say that the sentinel and
the legal zero coincide in meaning.

**I. Nine zero-tolerance singles, gate `forgive_ref`, input
`run_forgive_ref`.** Profiles `regime_64_dcqcn_direct7_4to1_zero.json`,
`regime_64_dcqcn_direct2_2to1_zero.json` and `no_incast_8_zero.json`,
each its exempt sibling with `p_low = p_high = 0` and
`domain = admission`, no pacing, no straggler. Records: direct7 at seeds
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
