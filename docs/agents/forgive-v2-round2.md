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
