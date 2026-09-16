# Run #123: FORGIVE v1 with the revocation corrected

Run 34867374086, dispatched 2026-09-14, read 2026-09-15. Gates `forgive`
and `forgive_dose`, 21 records, 84 arms, every experiment job green. The
code is main `c6855f0` with ns-3 `9717200cc`, which corrects the
exemption revocation: a spent allowance ends the exemption through the
receiver's report rather than through every repair request. Every
exempt-arm figure below comes from this run; the other three arms are
unchanged and reproduce exactly.

Joe Fang's work in collaboration with Zechen Ma.

## 1. The join is valid

The fixed-low baseline's makespan matches its run #122 bundle to the
microsecond in all 14 records the two runs share (1696.6857, 1696.9044,
1700.5622, 1688.3970 and 1709.8503 ms by seed). The exempt arm is the only
arm the fix could move, and it is the only arm that moved.

The new counter agrees with the old one everywhere: over 21 records the
share of exempt flows that received an allowance report equals the share
that re-armed, to the flow. The exemption now ends on the receiver's report
and on nothing else.

## 2. The ceiling was the defect

Run #122 reported that discarded gradient bytes level off near 9.3 % of
data-parallel bytes because trimming stops before the budget is spent. With
the revocation corrected, the exempt arm at budget 0.4 forgives 21.3 to
21.8 % of data-parallel bytes, and at 0.6 it forgives 37.7 to 38.6 %. The
kill test stated in advance was a move outside 9.2 to 9.4 % by more than
the seed spread of 0.5 points; the move is 12 points at 0.4 and 29 at 0.6.

The alternative cause we named before the run is the mechanism. Under the
defect a sender re-engaged DCQCN on almost every repair request, slowed
down, and stopped causing trims; the ceiling was the sender giving up its
exemption, not the fabric running out of congestion. The sentence given to
Zechen is withdrawn.

What replaces it: forgiven loss is now roughly proportional to the cap.
With the eligible share of data-parallel bytes at 0.79, the cap is
79 x budget in percent, and the exempt arm spends 68 to 86 % of it at every
budget.

## 3. The result at the worst cell

`direct7`, 4:1 oversubscription, 2 failed spines, DCQCN, 64 ranks, three
seeds unless stated. Training time is the 20-step makespan against the
fixed-low baseline of about 1697 ms; loss is forgiven bytes as a share of
data-parallel bytes; efficiency is points of training time per percent of
gradient lost.

| budget | FORGIVE time | FORGIVE loss | cap | utilisation | efficiency | shedding time | shedding loss | efficiency | exempt flows re-armed |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| 0.1 | 12.9 to 14.1 % | 6.75 to 6.89 % | 7.9 % | 86 % | 1.96 | 2.5 to 3.3 % | 7.9 % | 0.37 | 35 to 37 % |
| 0.2 | 16.0 to 16.7 % | 11.1 to 12.2 % | 15.8 % | 74 % | 1.41 | 4.9 to 5.5 % | 15.8 % | 0.33 | 20 to 22 % |
| 0.4, 5 seeds | 19.6 to 21.0 % | 21.3 to 21.8 % | 31.6 % | 68 % | 0.95 | 10.5 to 12.3 % | 31.6 % | 0.36 | 6.8 to 7.6 % |
| 0.6 | 23.7 to 24.3 % | 37.7 to 38.6 % | 47.4 % | 80 % | 0.63 | 16.0 to 16.4 % | 47.4 % | 0.34 | 0.2 to 0.3 % |
| 0.4, mask off | 25.3 to 25.6 % | 25.6 to 26.0 % | 31.6 % | 82 % | 0.98 | 13.2 to 14.9 % | 31.6 % | 0.45 | 7.3 to 7.5 % |

Readings.

- FORGIVE's efficiency falls with the budget, 1.96 at 0.1 to 0.63 at 0.6,
  while shedding's stays at 0.33 to 0.45. The two are furthest apart at
  the smallest budget, 5.3 times at 0.1, and closest at the largest, 1.9
  times at 0.6.
- The headline budget stays 0.1: 12.9 to 14.1 % of training time for
  6.75 to 6.89 % of gradient bytes. Run #122 put the same budget at 10.4
  to 10.9 % for 6.3 to 6.5 %, so the fix adds about 3 points of time for
  0.4 points of loss.
- Loss at 0.1 is above the 0.7 to 3.3 % that MLT profiles as tolerable
  for its workloads. A budget of 0.05 has not been run; it is the cheapest
  addition to the front and the point most likely to land inside that
  range.
- The re-arm column is the pacing question in one number. At 0.1, 35 to
  37 % of exempt flows reached a spent cell and lost their exemption; at
  0.6 almost none did. Yashar's concern applies exactly where we operate.
- Forgiven bytes spread evenly over the permissive steps, 5 to 7 % of the
  total on each, and the microburst step 18 takes 5 to 7 % like any other.
  The fabric is congested throughout, not only during the burst.
- The critical-step share of forgiven bytes is 1.39 to 1.44 % at budget
  0.1, 0.45 % at 0.4, 0.25 % at 0.6, and 19 to 20 % with the mask off, so
  the mask works and the predicted 1.0 to 1.5 % is confirmed.

## 4. The mild cell and the control

`direct2`, 2:1 oversubscription, budget 0.4, three seeds: FORGIVE recovers
10.5 to 12.5 % of training time for 2.37 to 2.50 % of data-parallel
bytes, efficiency 4.8, against shedding's 6.1 to 7.4 % for 31.6 %. Only
7 to 9 of 71 680 exempt flows re-armed, because the cap almost never
bound: the cell's trims fit inside 8 % of the allowance. That loss is inside MLT's tolerable range,
and this cell is the candidate headline if the paper needs one number
inside it.

The no-incast control forgives nothing and moves nothing, as before.

## 5. What this means for the stated claims

| claim | before #123 | after #123 |
| --- | --- | --- |
| aimed loss self-limits | 9.3 % ceiling at every budget above 0.2 | withdrawn; loss is 68 to 86 % of the cap |
| FORGIVE beats shedding per byte lost | 4 to 5 times, flat across the front | 5.3 times at 0.1, falling to 1.9 times at 0.6 |
| the mask protects critical steps | 1.0 to 1.5 % of forgiven bytes | unchanged, 1.4 % at 0.1 |
| the exemption ends on a refusal | measured under a defect | ends on the allowance report, verified by the counter identity on 21 records |

The number we lead with changes from "13 % for 9 % loss at budget 0.4"
to "13 to 14 % for 6.8 % loss at budget 0.1", and the sentence about the
fabric limiting the loss is gone.

## 6. Next

The v2 wave, run 35007858082, was dispatched 2026-09-15 on gate
`forgive_v2`: 18 single arms at budget 0.1 on this cell, joined by seed
against the recovery arm of this run. It answers whether pacing recovers
the 35 to 37 % of exempt flows that hit a spent cell.

Then, in this order: update `figure-data.md` and the two slide decks to
these numbers, and add a budget 0.05 record to the dose front.
