# Figure data and readings

Prepared by Joe Fang, in collaboration with Zechen Ma.

Every number behind the figures in the two September 2026 progress decks,
in plain text, so the charts can be rebuilt in any tool. No styling here:
each section gives what the chart shows, the axes and units, the data,
and the readings worth putting on the slide.

Decks: `slides-2026-09-progress.md` (FORGIVE at the centre) and
`slides-2026-09-results-first.md` (run #117 at the centre, FORGIVE as
future work). This file is a superset of both.

Sources are release bundles in `BulkyCI/astra-sim`: run #117
`zuihrl5stp6ulacoogghyp4loy7xsjpj`, #120
`uwlaookzhemmwabtbwfe2yhyxepupnmw`, #121
`b363b3rri7pbgbaudfh3tbnysiranl66`, #122
`rt4732ejzjqe2hkar2bturuv3qav6pv3`. Run #123 is workflow run
`34867374086`, and every v1 exempt-arm number in this file comes from it.
Run #124 is main `55d5767`, #125 is main `8213401` and #126 is main
`a1b30b0`; sections 11 and 12 read their certified per-arm summaries.

---

## 0. Setup facts every caption needs

Vocabulary, so captions stay consistent. An *arm* is one simulated
configuration. A *comparison* is a set of arms sharing a seed and a
random selection stream, so their results can be subtracted. A *run* is
one dispatch of many comparisons to the cluster, numbered #117, #120,
#121, #122, #123, #124, #125 and #126. A *cell* is one point of the eight-point fabric map.
The two sender-side arms are both shedding: *phase-aware shedding*
protects the critical steps, *unmasked shedding* does not. Quantities marked
**derived** below were computed from measured counters under a stated
assumption; everything else is read directly from a bundle.

- Simulator: ASTRA-sim 2.0 with Chakra execution traces over a forked
  ns-3 RDMA backend. The simulator computes no gradients, so nothing here
  speaks to model accuracy.
- Workload: Llama-3-70B-shaped gradient-bucket microbenchmark. Tensor
  parallel 8, pipeline 1, data parallel 8 at 64 ranks. One representative
  1 GiB typed data-parallel all-reduce bucket per rank per step, 20
  steps, 5.4 ms of compute per node overlapped with the communication
  window.
- Fabric: rail-optimised Clos, 400 Gb/s links, PFC off, UEC 1.0.3 packet
  trimming (a congested switch replaces the payload and forwards the
  header), trimmed-header class capped at 25 % of the link. Path
  selection is per-flow ECMP, not per-packet spraying.
- Stressor: seven background RDMA flows of 128 MiB each, aimed at one
  downlink rank, fired at step 18.
- Policy arms, matched off one random selection stream so the messages
  the baseline suppresses are exactly the ones the policy considers:
  tight baseline (`p_low` on every step), phase-aware policy (`p_low` on
  critical steps 1, 2, 3, 20 and `p_high` elsewhere), loose baseline
  (`p_high` on every step), and where applicable a forgiveness arm at the
  same budget as the phase-aware policy.
- W is the trim ratio: trimmed payload bytes divided by offered bytes.
  W' is W minus the forgiven share, that is, the load the transport still
  had to re-send.
- Do not quote `wire_per_offered` from any bundle. It counts bytes per
  hop rather than bytes a receiver saw, and reads 2.5 to 2.76 everywhere.
  The correct repair-inclusive ratio is (offered + retransmitted) /
  offered.

---

## 1. Timeline of the work

Chart: two-band timeline, July 20 to September 15 2026. One band for what
was built, one for what was run.

Fork point: upstream ASTRA-sim commit `518bd51`, 26 March 2026. First
commit of ours: `f31d865`, 20 July 2026. 184 commits to 8 September.

Build events:

| Date | Event |
| --- | --- |
| 2026-07-20 | fork ASTRA-sim, adopt uv for the Python toolchain |
| 2026-07-23 | phase-aware critical-step masks; register written of the gaps in our own May evaluation |
| 2026-07-27 | first UEC packet-trimming profiles |
| 2026-08-04 | trimming aligned to UEC 1.0.3; best-effort fabric controls |
| 2026-08-06 | selective repeat for trimmed and missing ranges; direct all-reduce to form an organic incast |
| 2026-08-09 | heavy comparisons moved to just-in-time SLURM runners on the UofT DCS cluster |
| 2026-08-17 | critical-step schedule `[1, 2, 3, 20]` pinned from literature independent of our own preprint |
| 2026-08-22 | the 16-rank configuration scaled to sixteen pi-derived seeds |
| 2026-09-05 | DCQCN knob and rate-cut telemetry; receiver forgiveness verdict in the transport |
| 2026-09-07 | congestion exemption for a forgiven flow |
| 2026-09-14 | report a spent allowance and revoke the exemption on it |

Cluster waves:

| Date | Run | Size | What it was |
| --- | --- | --- | --- |
| 2026-09-01 | #117 | 30 of 31 comparisons, about 90 arms | sixteen-seed 16-rank configuration, sweeps, one selective-repeat control |
| 2026-09-06 | #120 | 8 cells | regime map |
| 2026-09-07 | #121 | 6 comparisons, 24 arms | forgiveness with congestion exemption |
| 2026-09-08 | #122 | 14 comparisons, 56 arms | loss-budget sweep and phase-mask ablation |
| 2026-09-14 | #123 | 21 comparisons, 84 arms | the same front with the revocation corrected |
| 2026-09-15 | #124 | 18 single arms | Bernoulli pacing at 0.5 and 0.25 |
| 2026-09-16 | #125 | 24 arms | budget 0.05, and the coin below 0.25 |
| 2026-09-16 | #126 | 15 single arms | zero tolerance, forgiveness without the exemption, no controller |

Readings. Six weeks of the seven went into the instrument, because the
backend ASTRA-sim ships with is lossless RoCEv2 and models none of the
fabric the questions are about. The first four waves all land inside nine
days, which is what a working cluster path bought.

---

## 2. Sixteen matched seeds, run #117

Chart: paired dumbbell, one row per seed, sorted by relief. Horizontal
axis is the 20-step training window in milliseconds, roughly 6500 to
7850. Two points per row joined by a line.

Setup: 16 ranks, 2:1 fabric, go-back-N recovery, no sender congestion
control, `p_low` 0.005 and `p_high` 0.1. Seeds are eight-digit chunks of
pi, fixed before the wave.

| seed | baseline ms | policy ms | relief % | loose baseline ms | loose relief % |
| --- | ---: | ---: | ---: | ---: | ---: |
| 53589793 | 7526.6 | 6646.6 | 11.69 | 6877.5 | 8.62 |
| 16939937 | 7400.5 | 6649.0 | 10.15 | 6901.0 | 6.75 |
| 74944592 | 7723.0 | 7003.8 | 9.31 | 6280.7 | 18.68 |
| 62862089 | 7268.5 | 6692.9 | 7.92 | 6294.5 | 13.40 |
| 98628034 | 7414.9 | 6858.9 | 7.50 | 6672.3 | 10.01 |
| 48086513 | 7192.9 | 6816.3 | 5.23 | 6542.1 | 9.05 |
| 30781640 | 6995.2 | 6710.4 | 4.07 | 6083.6 | 13.03 |
| 23846264 | 7011.9 | 6727.2 | 4.06 | 6163.0 | 12.11 |
| 70938446 | 7376.3 | 7087.6 | 3.91 | 6470.4 | 12.28 |
| 82534211 | 6834.8 | 6583.8 | 3.67 | 6137.3 | 10.20 |
| 2884197 | 7333.6 | 7071.3 | 3.58 | 6498.7 | 11.38 |
| 28230664 | 7079.6 | 6847.0 | 3.29 | 6297.9 | 11.04 |
| 51058209 | 6856.9 | 6691.8 | 2.41 | 6567.4 | 4.22 |
| 33832795 | 6872.0 | 6969.6 | -1.42 | 6404.2 | 6.81 |
| 31415926 | 6800.6 | 7170.3 | -5.44 | 6762.8 | 0.56 |
| 70679821 | 6634.4 | 7128.8 | -7.45 | 6459.2 | 2.64 |

Aggregates, paired, Student t at 15 degrees of freedom. Level rows are
means over seeds; relief rows are means over seeds of the per-seed
difference or ratio, so a relief percentage will not equal the ratio of
the two level rows above it:

| quantity | mean | 95 % CI | verdict |
| --- | ---: | --- | --- |
| training window, baseline | 7145.1 ms | | |
| training window, policy | 6853.5 ms | | |
| relief | 3.91 % | [1.13, 6.68] % | excludes zero |
| relief in ms | 291.7 ms | [91.0, 492.3] ms | excludes zero |
| loose baseline relief | 9.42 % | [7.03, 11.82] % | excludes zero |
| worst all-reduce of the episode, baseline | 1026.0 ms | | |
| worst all-reduce of the episode, policy | 872.7 ms | | |
| that relief in ms | 153.4 ms | [5.0, 301.7] ms | excludes zero, barely |
| that relief in percent | 10.80 % | [-0.60, 22.20] % | **spans zero** |
| per-rank p99 relief | -4.90 % | [-19.6, +9.8] % | **spans zero, wrong sign** |

Readings.

- Thirteen of sixteen seeds improve and three regress. Show all sixteen;
  the spread is the honest picture and it is what the mechanism chart
  explains.
- The policy flattens the worst seeds and barely moves the mild ones.
  The four seeds whose baseline worst-collective exceeds 1.3 s drop by
  434, 497, 649 and 716 ms.
- Report the worst-collective result in milliseconds, never in percent.
  The percentage form spans zero because the baseline varies by seed.
- **Per-rank p99 is not a result.** It is the top three of 320 samples
  and one ECMP path collision moves it by half. Do not put it on a slide.
- The loose baseline row is the price list for the phase bound. Ten
  percent everywhere with no protection gains 9.42 %; the phase-aware
  schedule keeps 3.91 % of that and hands back the rest to protect steps
  1 to 3, where it costs 242 ms.

---

## 3. What explains the relief, run #117

Chart: two scatter panels, same vertical axis. Vertical axis is
milliseconds saved on the window, roughly -500 to 900. Panel A
horizontal axis is trims avoided in millions, roughly -40 to 80. Panel B
horizontal axis is data-parallel payload discarded in GB, roughly 1.85 to
2.45.

| seed | ms saved | trims avoided, millions | GB discarded (10^9 bytes) | baseline W | policy W |
| --- | ---: | ---: | ---: | ---: | ---: |
| 53589793 | 880.0 | 76.17 | 2.19 | 10.37 | 8.73 |
| 16939937 | 751.5 | 40.62 | 2.14 | 9.64 | 8.81 |
| 74944592 | 719.2 | 55.17 | 1.97 | 10.30 | 9.13 |
| 62862089 | 575.6 | 36.38 | 2.10 | 9.50 | 8.77 |
| 98628034 | 556.0 | 32.90 | 2.35 | 9.89 | 9.26 |
| 48086513 | 376.6 | 37.12 | 2.10 | 10.05 | 9.31 |
| 30781640 | 284.8 | 27.82 | 2.20 | 9.05 | 8.52 |
| 23846264 | 284.7 | 24.39 | 2.25 | 9.16 | 8.71 |
| 70938446 | 288.7 | 21.18 | 1.99 | 9.79 | 9.41 |
| 82534211 | 251.0 | 46.34 | 2.23 | 9.61 | 8.65 |
| 2884197 | 262.3 | 4.54 | 2.15 | 9.46 | 9.47 |
| 28230664 | 232.6 | 20.19 | 2.03 | 9.43 | 9.07 |
| 51058209 | 165.1 | 14.15 | 1.95 | 9.39 | 9.17 |
| 33832795 | -97.6 | -3.27 | 1.93 | 9.21 | 9.39 |
| 31415926 | -369.7 | -37.54 | 2.36 | 8.68 | 9.67 |
| 70679821 | -494.4 | -32.91 | 2.10 | 8.79 | 9.66 |

Correlations against milliseconds saved:

| predictor | correlation | slope |
| --- | ---: | --- |
| trims avoided | **0.93** | 11.9 ms per million trims |
| gradient bytes discarded | **-0.01** | none |
| baseline W | 0.84 | |

Readings.

- This is the strongest slide in either deck. Every seed discards about
  the same two gigabytes and that number predicts nothing. What predicts
  the saving is how many packet trims the discard prevented.
- The three negative seeds are exactly the three where the policy *added*
  trims. Nothing else distinguishes them.
- What comes out of it is a direction to look in, not a formula. The
  saving is proportional to the trims a policy prevents, and what one
  prevented trim is worth is set by the recovery scheme. Do not multiply
  the two numbers together; they have different denominators, and the
  product is meaningless. What the reasoning did do is correctly predict
  that the selective-repeat arm on the next chart would show nothing.
- Marginal amplification: the policy shed 1.98 GiB and the fabric
  re-carried 156 GiB less, so a discarded byte is worth about 79 bytes on
  the wire under this transport.

---

## 4. The recovery scheme sets the regime, run #117

Chart: horizontal bar on a log axis, one bar per metric, showing the
go-back-N cost as a multiple of the selective-repeat cost. Range 1x to
1000x.

Same 64 ranks, same 2:1 fabric, same seven-source 128 MiB burst. Only the
loss-recovery scheme differs.

| metric | go-back-N | selective repeat | ratio |
| --- | ---: | ---: | ---: |
| W, trimmed bytes per offered byte | 2.2 to 10.4 | 0.02 | 110 to 520 |
| retransmitted per offered byte, per DP flow | 7x to 25x | 0.08x to 0.13x | 54 to 312 |
| burst drain, serialisation floor 18.8 ms | 423 to 1798 ms | 23 to 29 ms | 15 to 78 |
| all-reduce span, burst step | 205 to 935 ms | 17.6 ms | 12 to 53 |
| all-reduce span, steady step | 110 to 250 ms | 13.4 ms | 8 to 19 |
| 20-step window | 4503 to 6795 ms | 1210 ms | 3.7 to 5.6 |
| policy relief | 3.9 to 11.1 % | 0.78 % | |

Per-family detail, fixed-low arms, one seed each:

| family | recovery | fabric | W | window | span steps 4-17 | span step 18 | span step 19 | burst drain |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 16-rank, seed 31415926 | go-back-N | 2:1 | 8.68 | 6795 ms | 246 ms | 935 ms | 294 ms | 423 to 933 ms |
| 32-rank direct, burst 7 | go-back-N | 1:1 | 3.02 | 4503 ms | 110 ms | 451 ms | 1057 ms | 838 to 1497 ms |
| 64-rank fan-in 7 | go-back-N | 4:3 | 2.58 | 5173 ms | 130 ms | 205 ms | 1330 ms | 809 to 1798 ms |
| 64-rank selective repeat | selective | 2:1 | 0.02 | 1210 ms | 13.4 ms | 17.6 ms | 12.7 ms | 23 to 29 ms |

Readings.

- Under go-back-N one trimmed packet rewinds a whole window, and with no
  congestion control the queue is still full when the sender rewinds, so
  the re-sent bytes are trimmed again. Under selective repeat a trim
  costs one repair packet and one round trip.
- The selective-repeat arm runs on a *worse* fabric (2:1 against 4:3) and
  still finishes 4.3 times sooner.
- Consequence for the policy: the same mechanism, unchanged, gains 3.9 to
  11.1 % under go-back-N and 0.78 % under selective repeat. This is the
  boundary of the run #117 result and it should be its own slide rather
  than a footnote.
- Every bounded-loss result our literature reviews turned up rests on the
  left-hand side of this chart: MLT and OptiReduce against TCP or UDP with
  millisecond timeouts, our own May evaluation against its bitmap-and-probe
  rounds. Classic RoCEv2 recovery is go-back-N and a large installed base
  still runs it, though current NICs increasingly offer selective repeat.

---

## 5. The regime map, run #120

Chart: scatter. Horizontal axis W on a log scale, roughly 0.002 to 0.35.
Vertical axis the 20-step window in ms, 1150 to 1780. Two marker classes
for congestion control off and DCQCN. Optionally draw an arrow from each
no-CC point to its DCQCN partner on the same fabric.

64 ranks, 20 steps, selective repeat throughout, one seed per cell.

| congestion control | DP fan-in | oversubscription | W | window ms | span median steps 4-17 | step 18 | step 19 | burst excess, % of window |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| none | 2 | 2:1 | 0.0235 | 1201 | 13.8 | 15.4 | 13.2 | 0.08 |
| none | 7 | 2:1 | 0.0625 | 1200 | 12.6 | 13.3 | 12.5 | 0.04 |
| none | 2 | 4:1 | 0.1289 | 1373 | 22.0 | 29.6 | 23.0 | 0.62 |
| none | 7 | 4:1 | 0.2406 | 1367 | 21.0 | 29.8 | 19.7 | 0.55 |
| DCQCN | 2 | 2:1 | 0.0023 | 1421 | 23.3 | 19.0 | 30.7 | 0.23 |
| DCQCN | 7 | 2:1 | 0.0077 | 1422 | 23.5 | 19.3 | 32.5 | 0.34 |
| DCQCN | 2 | 4:1 | 0.0187 | 1719 | 37.1 | 37.6 | 46.9 | 0.60 |
| DCQCN | 7 | 4:1 | 0.0317 | 1696 | 36.6 | 39.4 | 35.5 | 0.10 |

Transport detail per cell:

| cell | DP flows trimmed | (offered + retransmitted) / offered | trimmed vs untrimmed DP flow-completion median | rate cuts (CNP) | RTOs fired | burst drain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| none, 2, 2:1 | 24 % | 1.024 | 1.98x | 0 | 96 | 30.4 ms |
| none, 7, 2:1 | 53 % | 1.064 | 1.68x | 0 | 85 | 31.4 ms |
| none, 2, 4:1 | 58 % | 1.130 | 2.63x | 0 | 98 | 35.2 ms |
| none, 7, 4:1 | 75 % | 1.243 | 2.65x | 0 | 109 | 37.0 ms |
| DCQCN, 2, 2:1 | 7 % | 1.004 | 7.34x | 3 298 919 | 1 949 | 63.4 ms |
| DCQCN, 7, 2:1 | 21 % | 1.009 | 3.99x | 5 279 161 | 2 349 | 80.3 ms |
| DCQCN, 2, 4:1 | 29 % | 1.030 | 7.32x | 11 224 453 | 10 547 | 115.5 ms |
| DCQCN, 7, 4:1 | 48 % | 1.037 | 6.55x | 13 535 668 | 10 166 | 146.4 ms |

Pre-registered decision rule, written before the run: an operating region
exists if some cell reaches W of 0.5 or a burst excess of at least 20 %
of the window. Bounded loss has no purchase if the worst cell's excess is
under 5 %. Observed worst: W 0.24, excess 0.62 %. The rule returned the
negative branch.

Readings.

- The burst is a non-event under selective repeat in all eight cells. It
  drains in 30 to 37 ms without congestion control and 63 to 146 ms with
  it, against an 18.8 ms serialisation floor.
- Trimming is a steady-state property of how the fabric is provisioned,
  not of the burst. W over steps 1 to 17 equals W over the whole run in
  every cell. Fan-in multiplies it about 2.7x, oversubscription about
  5.5x.
- DCQCN cuts W by eight to ten times and lengthens the window by 18 to
  24 %. That penalty, not the burst, is the only large cost on the map.
- Its tail is the rate cut, not the repair: a trimmed flow takes four to
  seven times as long as an untrimmed one under DCQCN, against 1.7 to
  2.7 times without, and it fires 2 000 to 10 500 timeouts where the
  no-CC cells fire about 100.

---

## 6. FORGIVE at one operating point, run #123

Chart: grouped table or a four-bar comparison. No axes needed.

Worst cell of the map (DCQCN, fan-in 7, 4:1), budget 0.4, the three seeds
run #121 used. Run #123 re-measured all four arms on the corrected code,
so every row below comes from the one wave.

| arm | training window | all-reduce, non-critical steps | all-reduce, critical steps | gradient lost | bytes re-sent after trims |
| --- | ---: | ---: | ---: | ---: | ---: |
| tight baseline | 1697 to 1701 ms | 36 to 37 ms | 36 to 37 ms | 0.5 % | 3.5 to 3.7 % |
| sender-side shedding, 0.4 | 1491 to 1519 ms | 25 to 26 ms | 35 to 37 ms | 32 % | 2.1 % |
| FORGIVE with exemption, 0.4 | 1340 to 1360 ms | 12 to 13 ms | 34 to 36 ms | 21.3 to 21.5 % | 2.7 to 3.0 % |
| loose baseline, 0.4 | 1444 to 1477 ms | 23 to 25 ms | 22 to 26 ms | 40 % | 1.5 to 1.6 % |

Per seed the exempt arm withheld 25.4 to 25.7 million rate cuts, acted on
3.58 to 3.69 million, and re-armed 5 049 to 5 447 of its 71 680 exempt
flows. The flows that received an allowance report are the flows that
re-armed, to the flow, in all three seeds, and the budget rule held in
every ledger entry.

Readings.

- FORGIVE reaches a shorter window than sender-side shedding while
  discarding two thirds as much gradient.
- FORGIVE's critical steps stay within 2.4 ms of the tight baseline,
  while the loose baseline's critical steps speed up by a third. That
  difference is the safety property being sold, visible in a single row.
- Context from the map: the same cell without congestion control runs in
  1367 ms, so DCQCN's bill here is about 330 ms and the exempt arm gives
  back all of it. That comparison crosses two runs and the
  no-congestion-control figure is a single seed, so quote it as a scale
  rather than a measurement.

---

## 7. The loss-budget sweep, run #123

Chart: scatter with two connected series. Horizontal axis is gradient
bytes lost as a share of all data-parallel bytes, 0 to 50 %. Vertical
axis is training time recovered, 0 to 18 %. Label each point with its
budget. Optionally shade 0.7 to 3.3 % and mark 10 % on the horizontal
axis, which are MLT's published tolerance bounds.

Worst cell of the map, three seeds per budget except 0.4, which has two
seeds in this table and three more at the same cell in section 6.

Per-seed, the fourteen records that carry a shedding partner:

| profile | seed | budget | baseline ms | FORGIVE % | shedding % | loose baseline % | FORGIVE loss, % of DP bytes | shedding loss, % of DP bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p01 | 9550582 | 0.1 | 1697 | 12.90 | 3.12 | 3.93 | 6.75 | 7.65 |
| p01 | 23172535 | 0.1 | 1697 | 14.10 | 2.45 | 2.64 | 6.89 | 7.70 |
| p01 | 94081284 | 0.1 | 1701 | 13.23 | 3.28 | 3.06 | 6.84 | 7.68 |
| p02 | 9550582 | 0.2 | 1697 | 16.67 | 4.86 | 7.22 | 12.19 | 15.67 |
| p02 | 23172535 | 0.2 | 1697 | 16.73 | 5.52 | 7.20 | 11.80 | 15.77 |
| p02 | 94081284 | 0.2 | 1701 | 15.95 | 5.45 | 6.65 | 11.07 | 15.77 |
| base | 28410270 | 0.4 | 1688 | 19.55 | 10.97 | 12.99 | 21.30 | 31.42 |
| base | 81117450 | 0.4 | 1710 | 20.96 | 11.78 | 14.27 | 21.78 | 31.62 |
| p06 | 9550582 | 0.6 | 1697 | 24.26 | 16.23 | 20.18 | 38.11 | 47.77 |
| p06 | 23172535 | 0.6 | 1697 | 23.99 | 15.95 | 20.30 | 38.59 | 47.98 |
| p06 | 94081284 | 0.6 | 1701 | 23.72 | 16.38 | 20.77 | 37.65 | 47.76 |
| allsteps | 9550582 | 0.4 | 1697 | 25.43 | 14.90 | 14.90 | 25.88 | 39.76 |
| allsteps | 23172535 | 0.4 | 1697 | 25.27 | 14.42 | 14.42 | 26.03 | 39.88 |
| allsteps | 94081284 | 0.4 | 1701 | 25.56 | 13.15 | 13.15 | 25.60 | 39.66 |

Plot points, seed ranges:

| budget | mask | FORGIVE time | FORGIVE loss | shedding time | shedding loss |
| ---: | --- | --- | --- | --- | --- |
| 0.1 | on | 12.9 to 14.1 % | 6.75 to 6.89 % | 2.4 to 3.3 % | 7.7 % |
| 0.2 | on | 16.0 to 16.7 % | 11.1 to 12.2 % | 4.9 to 5.5 % | 15.7 % |
| 0.4 | on | 19.6 to 21.0 % | 21.3 to 21.8 % | 11.0 to 11.8 % | 31.5 % |
| 0.6 | on | 23.7 to 24.3 % | 37.7 to 38.6 % | 16.0 to 16.4 % | 47.9 % |
| 0.4 | off | 25.3 to 25.6 % | 25.6 to 26.0 % | 13.2 to 14.9 % | 39.8 % |

Efficiency, points of training time recovered per percent of gradient
lost:

| budget | FORGIVE | shedding |
| ---: | ---: | ---: |
| 0.1 | 1.9 to 2.1 | 0.3 to 0.4 |
| 0.2 | 1.4 | 0.3 |
| 0.4 | 0.9 to 1.0 | 0.3 to 0.4 |
| 0.6 | 0.6 | 0.3 |
| 0.4, mask off | 1.0 | 0.3 to 0.4 |

Budget utilisation, **derived**. Every DP all-reduce byte is eligible;
the cap over 20 steps is the mask average, 16 steps at the budget and 4
critical steps at 0.005, so `0.8 x budget + 0.001` in percent of DP
bytes (the shedding arm's 8.1 % at budget 0.1 is exactly this):

| budget | cap | FORGIVE spends | utilisation |
| ---: | ---: | ---: | ---: |
| 0.1 | 8.1 % | 6.8 % | 84 % |
| 0.2 | 16.1 % | 11.7 % | 73 % |
| 0.4 | 32.1 % | 21.5 % | 67 % |
| 0.6 | 48.1 % | 38.1 % | 79 % |

Readings.

- Forgiven loss is roughly proportional to the cap. Sender-side shedding
  discards exactly the mask average at every setting, what its hash was
  told to do; the exempt arm spends 67 to 84 % of the same cap, with no
  ceiling anywhere on the front.
- FORGIVE's efficiency falls with the budget, 1.96 at 0.1 to 0.63 at 0.6,
  while shedding's stays at 0.33 to 0.45. The two are furthest apart at
  the smallest budget, 5.3 times at 0.1, and closest at the largest, 1.9
  times at 0.6.
- The headline budget for v1 is 0.1: 12.9 to 14.1 % of training time for
  6.75 to 6.89 % of gradient bytes.
- Loss at 0.1 is above the 0.7 to 3.3 % that MLT profiles as tolerable
  for its workloads. Run #125 added budget 0.05 and the coin, and section
  11 has the points that land inside that band.
- Shedding does not overtake on time anywhere on the front. At budget 0.6
  it recovers 16.0 to 16.4 % against FORGIVE's 23.7 to 24.3 %, and it
  discards 47.4 % of data-parallel bytes against FORGIVE's 37.7 to
  38.6 %.
- Budget 0.4 rests on five seeds. The two in the table read 19.55 and
  20.96 %, the three in section 6 read 20.00, 20.03 and 21.00 %, so the
  point spans 19.6 to 21.0 %.

---

## 8. What the phase mask costs and whether it works, run #123

Chart: two panels, or a table. Panel A is the cost, panel B is the
integrity check.

Cost of the mask, budget 0.4, three seeds each:

| arm | training time recovered | gradient lost |
| --- | ---: | ---: |
| mask on, protects steps 1, 2, 3, 20 | 19.6 to 21.0 % | 21.3 to 21.8 % |
| mask off, budget 0.4 everywhere | 25.3 to 25.6 % | 25.6 to 26.0 % |
| difference, paired on the three shared seeds | 5.1 points | 4.4 points |

Integrity, share of forgiven bytes placed on the four critical steps.
A uniform policy would place 4/20, that is 20 %, there:

| profile | budget | critical-step share of forgiven bytes | ledger violations |
| --- | ---: | ---: | ---: |
| p01 | 0.1 | 1.39 to 1.44 % | 0 |
| p02 | 0.2 | 0.80 to 0.85 % | 0 |
| base | 0.4 | 0.44 to 0.45 % | 0 |
| p06 | 0.6 | 0.25 % | 0 |
| allsteps | 0.4 | 19.16 to 20.45 % | 0 |

The budget law verified with zero violations in all 21 records of run
#123, 1280 ledger cells in each of the 20 congested ones.

Per-step all-reduce span, seed 9550582, budget 0.1, milliseconds. Steps
1, 2, 3 and 20 are the protected ones:

| step | baseline | FORGIVE | shedding | FORGIVE % | shedding % |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 34.5 | 33.1 | 34.5 | 4.0 | 0.0 |
| 2 | 34.9 | 38.3 | 34.9 | -9.8 | 0.0 |
| 3 | 37.4 | 33.9 | 37.4 | 9.4 | 0.0 |
| 4 | 39.3 | 24.6 | 33.5 | 37.3 | 14.7 |
| 5 | 40.0 | 17.6 | 35.1 | 55.9 | 12.3 |
| 6 | 36.7 | 19.5 | 32.2 | 46.8 | 12.3 |
| 7 | 36.1 | 19.1 | 30.9 | 47.2 | 14.3 |
| 8 | 37.3 | 19.4 | 35.3 | 47.9 | 5.5 |
| 9 | 32.7 | 19.5 | 32.6 | 40.3 | 0.2 |
| 10 | 35.8 | 22.0 | 33.7 | 38.7 | 6.0 |
| 11 | 39.3 | 21.6 | 31.7 | 45.1 | 19.4 |
| 12 | 36.5 | 21.8 | 31.0 | 40.4 | 15.1 |
| 13 | 39.0 | 19.7 | 33.5 | 49.5 | 14.1 |
| 14 | 34.3 | 22.2 | 35.0 | 35.2 | -2.2 |
| 15 | 39.4 | 22.5 | 32.6 | 42.8 | 17.2 |
| 16 | 35.6 | 19.3 | 33.2 | 45.9 | 6.7 |
| 17 | 35.8 | 21.5 | 33.5 | 40.0 | 6.4 |
| 18 | 33.7 | 19.6 | 32.5 | 41.7 | 3.4 |
| 19 | 36.5 | 26.4 | 40.8 | 27.5 | -11.7 |
| 20 | 37.6 | 35.8 | 37.9 | 4.9 | -0.6 |

Same seed with the mask removed, for contrast:

| step | baseline | FORGIVE | FORGIVE % |
| ---: | ---: | ---: | ---: |
| 1 | 34.5 | 12.8 | 63.0 |
| 2 | 34.9 | 13.2 | 62.2 |
| 3 | 37.4 | 11.4 | 69.4 |
| 20 | 37.6 | 11.1 | 70.6 |

Readings.

- The mask costs 5.1 points of training time and returns 4.4 points of
  gradient loss on four steps out of twenty. That is the price of the
  safety property, and it is now a number rather than an assertion.
- Prove the mask with the ledger, not with the clock. Masked runs place
  0.25 to 1.44 % of forgiven bytes on the protected steps against the 19
  to 20 % a uniform policy puts there.
- Per-step timings carry a noise floor of roughly plus or minus 13 % at
  one seed. Within a seed, steps 1 to 3 read identically at budgets 0.1,
  0.2 and 0.6, which shows the scatter is arm-level randomness rather
  than a budget effect. The one signal well above that floor is the
  mask-off run's 62 to 71 % on those same steps.
- Forgiven bytes spread evenly over the permissive steps, 5 to 7 % of the
  total on each, and the microburst step 18 takes 5 to 7 % like any
  other, so the fabric is congested throughout rather than only during
  the burst.
- Sanity check worth mentioning if anyone doubts the mask is wired up:
  the exempt flow count is 71 680 with the mask and 89 600 without, a
  ratio of exactly 20/16.

---

## 9. Why sender-side shedding cannot relieve a controlled fabric

Chart: two bar panels. Panel A is time to finish the same payload. Panel
B is rate achieved on the wire. Four bars each.

All four arms owe the same 70.0 GB of all-reduce payload across the 16
non-critical steps. Worst cell of the map, budget 0.1, seed 9550582.

| arm | time for that payload | physical bytes moved (derived) | wire rate (derived) | peak switch queue |
| --- | ---: | ---: | ---: | ---: |
| baseline, 0.5 % everywhere | 588 ms | 152.3 GB | 259 GB/s | 4 194 316 B |
| sender-side shedding at 0.1 | 537 ms | 137.8 GB | 257 GB/s | 4 194 316 B |
| loose baseline at 0.1 | 525 ms | 134.1 GB | 255 GB/s | 4 194 316 B |
| FORGIVE with exemption | 336 ms | 153.3 GB | 456 GB/s | 4 194 268 B |

Control-plane counters for the same four arms:

| arm | congestion notifications generated | acted on | ignored | per GB offered | trimmed GB | re-sent GB | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 12.99 M | 12.99 M | 0 | 16 382 | 23.8 | 23.8 | 10 110 |
| shedding at 0.1 | 11.53 M | 11.53 M | 0 | 14 822 | 21.0 | 21.0 | 8 964 |
| loose baseline | 11.56 M | 11.56 M | 0 | 14 926 | 20.2 | 20.2 | 8 041 |
| FORGIVE | 18.57 M | 8.37 M | 10.20 M | 10 548 | 33.1 | 20.3 | 7 279 |

Readings.

- The peak queue is the 4 MiB trim threshold, to the byte, in all four
  arms. The queue never gets shorter, because a closed-loop controller
  hands back as rate whatever load you remove until the queue returns to
  its marking point. Acted-on notifications per GB fall 9.5 % for a 10 %
  load cut.
- Time is bytes over rate. Shedding attacks the numerator and the
  controller pins the denominator, so it moves fewer bytes at the
  baseline's rate, one percent slower if anything.
- FORGIVE attacks the denominator. It puts 0.6 % *more* bytes on the
  wire, provokes 43 % more notifications than the baseline, acts on 36 %
  fewer, and moves the same payload 75 % faster. It also cuts the
  timeouts by 28 %, because a forgiven byte range never waits for a
  repair.
- Structural version of the same point: the load is a seven-way fan-in,
  and congestion at an incast is set by how many senders arrive at once.
  Uniform shedding removes bytes from all seven senders and never removes
  a sender. Seven-to-one becomes 6.3-to-one.
- The window arithmetic almost closes. The all-reduce is about 42 % of an
  85 ms step and 16 of 20 steps are eligible, so shedding's 8.7 % span
  cut predicts 2.9 % of the window against 3.1 % measured, while
  FORGIVE's 42.8 % predicts 14.4 % against 12.9 % measured. The 1.5-point
  residue on the FORGIVE side is the exempt arm's slower critical steps,
  which the arithmetic assumes untouched.

---

## 10. Exemption counters across the front, run #123

Chart: line or bar against budget. Useful as a backup slide when someone
asks how much congestion control the exemption actually suppresses.

| profile | budget | seeds | forgiven GB | notifications ignored, M | acted on, M | ignored share | flows re-armed | timeouts | flows given an allowance report |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p01 | 0.1 | 3 | 12.8 to 13.1 | 10.20 to 10.44 | 7.92 to 8.37 | 54.9 to 56.8 % | 25 212 to 26 153 | 6 430 to 7 279 | 25 212 to 26 153 |
| p02 | 0.2 | 3 | 21.1 to 23.2 | 16.26 to 16.73 | 5.58 to 5.81 | 74.1 to 74.5 % | 14 156 to 15 863 | 5 142 to 5 306 | 14 156 to 15 863 |
| base | 0.4 | 5 | 40.6 to 41.5 | 25.38 to 25.82 | 3.47 to 3.75 | 87.3 to 88.1 % | 4 907 to 5 447 | 3 073 to 3 419 | 4 907 to 5 447 |
| p06 | 0.6 | 3 | 71.7 to 73.5 | 36.70 to 37.27 | 2.80 to 2.93 | 92.6 to 92.9 % | 177 to 246 | 2 461 to 2 552 | 177 to 246 |
| allsteps | 0.4 | 3 | 48.8 to 49.6 | 31.41 to 31.87 | 1.08 to 1.13 | 96.5 to 96.7 % | 6 552 to 6 727 | 1 179 to 1 259 | 6 552 to 6 727 |

Readings.

- The share of rate cuts a sender can ignore rises with the budget, from
  55 % at 0.1 to 93 % at 0.6, and reaches no ceiling.
- Timeouts fall monotonically as the budget rises, from 7 279 at 0.1 to
  2 461 at 0.6, and to about 1 200 with the mask off. Forgiveness removes
  the repairs that were waiting to time out.
- The re-arm column is the pacing question in one number. At budget 0.1,
  35 to 37 % of exempt flows reached a spent cell and lost their
  exemption; at 0.6 almost none did, so the cap binds exactly where we
  intend to operate.
- The last two columns are equal profile by profile and seed by seed.
  Every flow that received an allowance report re-armed and no other flow
  did, which is how run #123 verifies that the exemption ends on the
  receiver's report and on nothing else. `pacing_refusal_count` reads zero
  in all 21 records, because v1 refuses on a spent cell rather than on a
  draw.

---

## 11. The coin and the small budget, run #125

Chart: the same time-against-loss scatter as section 7, with a second
series for the coin. Horizontal axis is gradient bytes forgiven as a
share of all data-parallel bytes, 0 to 40 %. Vertical axis is training
time recovered, 0 to 25 %. Shade 0.7 to 3.3 %, which is the band MLT
profiles as tolerable.

Worst cell of the map, `direct7` at 4:1, DCQCN, 64 ranks, three seeds per
arm, the same seeds as run #123. The coin is Bernoulli pacing at
probability P: a forgivable trim is forgiven with probability P and
repaired otherwise. Loss is forgiven bytes over the 191.406 GB of
data-parallel all-reduce bytes every run offers.

Per-seed, v1 at budget 0.05 and the coin arms:

| arm | seed | baseline ms | arm ms | time recovered % | forgiven bytes | loss, % of DP bytes | exempt flows re-armed |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v1, budget 0.05 | 9550582 | 1696.686 | 1551.126 | 8.58 | 7 204 777 484 | 3.764 | 33 455 |
| v1, budget 0.05 | 23172535 | 1696.904 | 1555.305 | 8.35 | 7 157 748 556 | 3.740 | 33 466 |
| v1, budget 0.05 | 94081284 | 1700.562 | 1565.323 | 7.95 | 7 222 088 734 | 3.773 | 35 123 |
| P = 0.05, budget 0.1 | 9550582 | 1696.686 | 1442.968 | 14.95 | 2 340 175 808 | 1.223 | 0 |
| P = 0.05, budget 0.1 | 23172535 | 1696.904 | 1423.858 | 16.09 | 2 524 663 516 | 1.319 | 0 |
| P = 0.05, budget 0.1 | 94081284 | 1700.562 | 1418.140 | 16.61 | 2 457 022 172 | 1.284 | 0 |
| P = 0.1, budget 0.1 | 9550582 | 1696.686 | 1437.038 | 15.30 | 4 988 812 508 | 2.606 | 3 |
| P = 0.1, budget 0.1 | 23172535 | 1696.904 | 1413.479 | 16.70 | 5 588 347 452 | 2.920 | 1 |
| P = 0.1, budget 0.1 | 94081284 | 1700.562 | 1429.070 | 15.96 | 5 046 657 774 | 2.637 | 0 |
| P = 0.25, budget 0.2 | 9550582 | 1696.686 | 1395.609 | 17.75 | 13 760 422 954 | 7.189 | 15 |
| P = 0.25, budget 0.2 | 23172535 | 1696.904 | 1398.132 | 17.61 | 14 519 837 176 | 7.586 | 11 |
| P = 0.25, budget 0.2 | 94081284 | 1700.562 | 1394.943 | 17.97 | 14 150 179 262 | 7.393 | 6 |
| P = 0.25, budget 0.05 | 9550582 | 1696.686 | 1453.651 | 14.32 | 6 208 910 776 | 3.244 | 11 922 |
| P = 0.25, budget 0.05 | 23172535 | 1696.904 | 1467.639 | 13.51 | 5 849 444 394 | 3.056 | 11 557 |
| P = 0.25, budget 0.05 | 94081284 | 1700.562 | 1448.326 | 14.83 | 6 192 469 436 | 3.235 | 12 053 |

Each arm has 71 680 exempt flows, so the last column reads against that
denominator. The sender-side arms of the budget 0.05 comparison
recover 0.1 to 1.3 % for admission and 1.1 to 2.2 % for the loose
baseline.

Plot points at budget 0.1, the coin front, three seeds each. The v1 row
comes from run #123 and the P = 0.5 and P = 0.25 rows from run #124, both
joined by seed on the same simulator:

| arm | time recovered | loss, % of DP bytes | exempt flows re-armed |
| --- | --- | --- | --- |
| v1, no coin | 12.9 to 14.1 % | 6.75 to 6.89 % | 35 to 37 % |
| P = 0.5 | 13.9 to 14.8 % | 6.3 to 6.6 % | 18 to 20 % |
| P = 0.25 | 16.0 to 16.2 % | 5.5 to 5.9 % | 7 to 8 % |
| P = 0.1 | 15.3 to 16.7 % | 2.6 to 2.9 % | 0 to 3 flows |
| P = 0.05 | 15.0 to 16.6 % | 1.2 to 1.3 % | none |

Plot points across budgets, v1 against the coin at P = 0.25:

| budget | v1 time | v1 loss | P = 0.25 time | P = 0.25 loss |
| ---: | --- | --- | --- | --- |
| 0.05 | 8.0 to 8.6 % | 3.74 to 3.77 % | 13.5 to 14.8 % | 3.1 to 3.2 % |
| 0.1 | 12.9 to 14.1 % | 6.75 to 6.89 % | 16.0 to 16.2 % | 5.5 to 5.9 % |
| 0.2 | 16.0 to 16.7 % | 11.1 to 12.2 % | 17.6 to 18.0 % | 7.2 to 7.6 % |

Readings.

- The headline candidate is P = 0.05 at budget 0.1: about 16 % of
  training time for 1.2 to 1.3 % of gradient bytes, which is inside the
  0.7 to 3.3 % band MLT profiles as tolerable.
- Time is flat from P = 0.25 down to P = 0.05 while loss falls by a
  factor of four, so the coin moves the operating point left and not
  down.
- Lowering the budget instead of slowing the spend costs time: v1 at
  budget 0.05 recovers 8.0 to 8.6 % for 3.74 to 3.77 %, half the time
  the coin recovers for three times the loss.
- The re-arm column is the mechanism. At budget 0.05 v1 loses the
  exemption on 47 to 49 % of its exempt flows; at budget 0.1 the coin at
  P = 0.1 loses it on at most 3 flows of 71 680 and at P = 0.05 on none.
- The coin at P = 0.25 dominates v1 at every budget it was run at, on
  both axes.

---

## 12. The three references, run #126

Chart: a four-bar panel, training time recovered against the fixed-low
control, with the loss each reference pays printed under its bar. Worst
cell of the map unless a row says otherwise.

Zero tolerance, the arm that forgives nothing and sheds nothing, against
the fixed-low control that sheds 0.5 %:

| fabric | seed | control ms | zero ms | difference % |
| --- | --- | ---: | ---: | ---: |
| direct7 4:1 | 9550582 | 1696.686 | 1714.643 | -1.06 |
| direct7 4:1 | 23172535 | 1696.904 | 1695.433 | +0.09 |
| direct7 4:1 | 94081284 | 1700.562 | 1711.225 | -0.63 |
| direct7 4:1 | 28410270 | 1688.397 | 1696.758 | -0.50 |
| direct7 4:1 | 81117450 | 1709.850 | 1696.880 | +0.76 |
| direct2 2:1 | 9550582 | 1428.604 | 1443.694 | -1.06 |
| direct2 2:1 | 23172535 | 1417.726 | 1423.993 | -0.44 |
| direct2 2:1 | 94081284 | 1408.884 | 1439.198 | -2.15 |
| no incast | 31415926 | 4.200 | 4.200 | 0.00 |

Forgiveness without the exemption, budget 0.1, and no controller at all:

| arm | seed | baseline ms | arm ms | time recovered % | loss, % of DP bytes | bytes re-sent |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| forgive, obey DCQCN | 9550582 | 1696.686 | 1585.384 | 6.56 | 6.805 | 1.84 % |
| forgive, obey DCQCN | 23172535 | 1696.904 | 1603.612 | 5.50 | 6.922 | 1.89 % |
| forgive, obey DCQCN | 94081284 | 1700.562 | 1588.077 | 6.61 | 6.910 | 1.74 % |
| no controller | 9550582 | 1696.686 | 1355.709 | 20.10 | 0 | 25.35 % |
| no controller | 23172535 | 1696.904 | 1355.709 | 20.11 | 0 | 25.35 % |
| no controller | 94081284 | 1700.562 | 1355.709 | 20.28 | 0 | 25.35 % |

Bytes re-sent is retransmitted bytes over the 793.641 GB every run
offers. The fixed-low control re-sends 3.48 to 3.73 % of that on the same
cell and times out 10 042 to 10 622 times; the no-controller arm times
out 93 times.

Readings.

- Zero tolerance reads -1.1 to +0.8 % of the fixed-low control on
  `direct7` over 5 seeds and -2.2 to -0.4 % on `direct2`, so the control
  is a true zero within the seed spread and every delta in this file
  stands against DCQCN with no loss tolerance.
- Forgiveness that obeys the controller recovers 5.5 to 6.6 % for 6.8 to
  7.0 % of gradient bytes, against FORGIVE v1's 12.9 to 14.1 % for the
  same budget and the same loss, so the exemption is about half of the
  gain.
- Turning the controller off entirely recovers 20.1 to 20.3 % and puts
  25.4 % of all bytes back on the wire as repairs. FORGIVE v1 at budget
  0.4 reaches the same 20 %, so the exemption recovers the whole of what
  the controller costs.

---

## 13. Mechanism diagram, no data

Three boxes left to right: sender NIC, switch, receiver NIC. Data flows
left to right; the switch trims a payload and forwards the header; the
receiver returns either a repair request or an acknowledgement of a range
that never arrived.

Three numbered points beside it.

1. The receiver, not the sender, decides. On each trimmed range it asks
   whether this (rank, step) still has budget. If it does, the receiver
   acknowledges the range as if it had been delivered and those bytes are
   gone for good. If it does not, it sends the ordinary repair request.
2. The budget is a ledger, not a coin flip. Forgiven plus shed bytes for
   a (destination, step) are bounded by the budget times the eligible
   bytes for that pair. Counters only grow, and the simulator certifies
   the cell when that rank's last all-reduce of the step completes.
   Critical steps carry a tighter budget.
3. An eligible flow ignores rate cuts while the receiver still has
   allowance to forgive. The receiver grants the exemption on the
   acknowledgements it already sends, and one bit reports that forgiving
   every byte the rank is missing would exceed the step's tolerance; the
   sender obeys its controller while that report stands and withholds
   signals again once repairs bring the cell back under the line.

Supporting fact for the design choice, worth a line on the slide: the ECN
marking threshold is 800 KB at 400 Gb/s and the trim point is 4 MiB, so
most marks fire long before anything is trimmed. At the worst cell the
run takes 13.5 million rate cuts and records 3.4 million trims, and since
a trim can provoke at most one mark, at least 74 % of the marks are
ECN-originated. Suppressing only the notification our own forgiveness
provoked could not move the window.

---

## 14. Numbers that should not be plotted

Keep these out of the deck, and be ready to say why.

| number | why not |
| --- | --- |
| per-rank p99 improvement | -4.9 % mean across sixteen seeds, CI [-19.6, +9.8]. Top three of 320 samples; one path collision moves it by half |
| worst-collective relief as a percentage | 10.8 % mean, CI [-0.60, 22.20], spans zero. Report the 153 ms with CI [5, 302] instead |
| the run #117 budget grid | ran unmatched, because the profile name entered the selection hash. Fixed in commit `63ef7c2`, not yet re-run |
| `wire_per_offered` | hop-weighted, not bytes a receiver saw |
| the 24.8 % from our own May preprint | measured with a fully blocking worker loop, so it includes network time a modern framework hides. It is our earlier number rather than a rival's, and nothing in this file is comparable with it |
| single-seed sweeps, fan-in and burst-source counts | directional only, no error bars |

## 13. Run #127 (GitHub release #129, run 35180385479): the design of record, budget 0.1

Twenty-one single arms on the worst cell at budget 0.1, joined by seed
against run #123's fixed-low baseline (1696.7, 1696.9 and 1700.6 ms).
Code main `59cf16c`, ns-3 `3e11ace49`: the soft vested cap, the fresh
coin, the holes rule for "budget gone", the exemption granted by the
receiver and following its latest report on every step, the stop at
`1 - p` of a sender's share, the up-front cap as an ablation. Every arm
certified locally; worst cell 0.900 to 0.909.

| arm | seed | training time recovered | loss, % of DP bytes | actual loss after late arrivals | re-sent bytes | TP collective time vs baseline | obeying, ms per exempt flow |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| the law, no coin, no stop (v1 point) | 9550582 | 16.66 % | 7.55 % | 7.49 % | 5.88 % | -4.3 % | 0.17 |
| the law, no coin, no stop (v1 point) | 23172535 | 16.06 % | 7.57 % | 7.51 % | 5.61 % | +4.4 % | 0.17 |
| the law, no coin, no stop (v1 point) | 94081284 | 16.66 % | 7.56 % | 7.50 % | 5.22 % | -1.3 % | 0.18 |
| the coin, P = 0.25 | 9550582 | 15.97 % | 5.64 % | 5.59 % | 6.57 % | -7.6 % | 0.13 |
| the coin, P = 0.25 | 23172535 | 15.84 % | 5.51 % | 5.46 % | 6.48 % | -1.2 % | 0.13 |
| the coin, P = 0.25 | 94081284 | 16.91 % | 5.55 % | 5.50 % | 6.55 % | -5.7 % | 0.14 |
| the stop | 9550582 | 16.55 % | 8.10 % | 7.72 % | 5.46 % | -2.5 % | 0.19 |
| the stop | 23172535 | 16.11 % | 8.10 % | 7.71 % | 5.76 % | +4.0 % | 0.19 |
| the stop | 94081284 | 15.84 % | 8.10 % | 7.69 % | 5.72 % | +3.2 % | 0.20 |
| the coin and the stop (design of record) | 9550582 | 16.55 % | 8.10 % | 7.26 % | 6.55 % | -1.9 % | 0.14 |
| the coin and the stop (design of record) | 23172535 | 16.19 % | 8.10 % | 7.28 % | 6.94 % | +5.1 % | 0.14 |
| the coin and the stop (design of record) | 94081284 | 16.38 % | 8.10 % | 7.25 % | 6.58 % | -1.8 % | 0.15 |
| up-front cap, no coin (ablation) | 9550582 | 9.10 % | 8.05 % | 8.02 % | 2.05 % | +4.6 % | 0.19 |
| up-front cap, no coin (ablation) | 23172535 | 10.18 % | 7.94 % | 7.91 % | 1.93 % | +6.1 % | 0.20 |
| up-front cap, no coin (ablation) | 94081284 | 9.39 % | 8.00 % | 7.98 % | 2.09 % | +4.1 % | 0.19 |
| up-front cap with the coin (ablation) | 9550582 | 14.64 % | 6.43 % | 6.36 % | 6.33 % | -9.6 % | 0.08 |
| up-front cap with the coin (ablation) | 23172535 | 15.28 % | 6.19 % | 6.12 % | 6.03 % | -0.4 % | 0.08 |
| up-front cap with the coin (ablation) | 94081284 | 14.89 % | 6.24 % | 6.17 % | 6.11 % | -3.2 % | 0.07 |
| never re-engage (reference D) | 9550582 | 18.68 % | 7.65 % | 7.61 % | 6.52 % | -4.7 % | 0.00 |
| never re-engage (reference D) | 23172535 | 18.95 % | 7.56 % | 7.52 % | 6.75 % | -2.6 % | 0.00 |
| never re-engage (reference D) | 94081284 | 18.98 % | 7.58 % | 7.53 % | 6.57 % | -9.0 % | 0.00 |

Readings.

- The law's v1 point moves from 12.9 to 14.1 % (run #123, old rules) to
  16.1 to 16.7 %, for 7.55 to 7.57 % loss, with 86 000 exempt flows
  instead of 71 680 because critical steps now grant the exemption too.
- The coin at 0.25 reads 15.8 to 16.9 % for 5.5 to 5.6 %, the same as run
  #124 measured under the old rules, so the rule changes did not move the
  coin arm.
- The stop spends the cell to its cap on every step (8.10 % on all three
  seeds) and recovers no time over the arm without it; late arrivals give
  it back 0.4 points of actual loss. Under selective repeat the stop is
  not worth its loss.
- The up-front cap is far worse than the vested one: 9.1 to 10.2 % for
  8.0 % loss, half the exempt flows, TP collectives 4 to 6 % slower. The
  budget is spent early, the controller returns, and the exemption is
  lost. Vesting is the right law.
- Never re-engaging reads 18.7 to 19.0 % for 7.6 % loss and 6.5 to 6.8 %
  re-sent, against the no-controller ceiling of 20.1 to 20.3 % for 25.4 %
  re-sent. Revocation costs about 2.3 points of time and saves about a
  point of re-sent bytes.
- TP collective time is never worse than the baseline in any vested arm
  (-9.6 to +5.1 % across seeds, most negative; the v1 point's seed 23172535 is +4.4 %), so the exempt DP flows do
  not slow the job's own tensor-parallel traffic; only the up-front-cap
  arms are slower there.
- Exempt flows see 0.3 to 0.5 report transitions each and spend 0.1 to
  0.2 ms per flow obeying the controller.
