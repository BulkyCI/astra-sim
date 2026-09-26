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

Per-seed, the fourteen records that carry a shedding partner (the
shedding-loss column of the per-seed rows below is the pre-audit reading;
the audited values, equal to the mask-weighted cap, are in the plot-point
table that follows and in docs/agents/paper-section-audit.md):

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
| 0.1 | on | 12.9 to 14.1 % | 6.75 to 6.89 % | 2.4 to 3.3 % | 8.1 % |
| 0.2 | on | 16.0 to 16.7 % | 11.1 to 12.2 % | 4.9 to 5.5 % | 16.1 % |
| 0.4 | on | 19.6 to 21.0 % | 21.3 to 21.8 % | 10.5 to 12.3 % | 31.7 to 32.3 % |
| 0.6 | on | 23.7 to 24.3 % | 37.7 to 38.6 % | 16.0 to 16.4 % | 48.0 to 48.2 % |
| 0.4 | off | 25.3 to 25.6 % | 25.6 to 26.0 % | 13.2 to 14.9 % | 40.0 to 40.2 % |

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

## 15. Run #127 (GitHub release #129, run 35180385479): the design of record, budget 0.1

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

---

## 16. Run #130 (run 35233809033): the healthy cell, `direct7` at 1:1

Eight spines per leaf, so the fabric is not oversubscribed; everything
else as the worst cell. Nine records, 18 arms, code main `65e98e7`, the
same three seeds; every arm certified locally (FORGIVE worst cell 0.916
to 0.948, coin 0.983 to 0.984). The control is each record's own
fixed-low baseline.

| arm | seed | control ms | arm ms | time recovered % | loss, % of DP bytes | bytes re-sent | bytes trimmed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vesting, budget 0.1 | 9550582 | 1247.713 | 1191.829 | 4.48 | 1.00 | 0.04 % | 0.27 % |
| vesting, budget 0.1 | 23172535 | 1253.119 | 1183.659 | 5.54 | 1.30 | 0.04 % | 0.34 % |
| vesting, budget 0.1 | 94081284 | 1260.232 | 1166.312 | 7.45 | 1.12 | 0.03 % | 0.29 % |
| vesting with the coin at 0.25 | 9550582 | 1247.713 | 1175.054 | 5.82 | 0.32 | 0.27 % | 0.32 % |
| vesting with the coin at 0.25 | 23172535 | 1253.119 | 1169.815 | 6.65 | 0.42 | 0.35 % | 0.42 % |
| vesting with the coin at 0.25 | 94081284 | 1260.232 | 1179.047 | 6.44 | 0.27 | 0.25 % | 0.28 % |
| zero tolerance | 9550582 | 1247.713 | 1252.296 | -0.37 | 0 | 0.05 % | 0.04 % |
| zero tolerance | 23172535 | 1253.119 | 1238.755 | 1.15 | 0 | 0.06 % | 0.05 % |
| zero tolerance | 94081284 | 1260.232 | 1240.412 | 1.57 | 0 | 0.04 % | 0.03 % |
| sender-side shedding, 0.1 | three seeds | | | 0.13 to 0.29 | 0 forgiven | 0.03 % | 0.02 to 0.03 % |
| loose baseline, 0.1 | three seeds | | | -0.36 to +0.70 | | 0.02 to 0.03 % | 0.02 % |

The control itself trims 0.02 to 0.04 % of bytes and re-sends 0.03 to
0.05 %.

Readings.

- The pre-registered kill test did not fire. The control's trim ratio is
  far below 0.5 %, and FORGIVE recovers 4.5 to 7.5 % rather than under 2
  points, so the claim is not scoped to degraded fabrics.
- The incast is at the last hop. Seven senders at 400 Gbps into one
  400 Gbps receiver link is a 7:1 incast whatever the spine ratio, DCQCN
  reacts to it on every step, and the exempt senders trim ten times more
  than the control and still finish sooner.
- The coin reads the same time as vesting alone within the seed spread
  (5.8 to 6.7 % against 4.5 to 7.5 %) for a quarter of the loss, as on
  the worst cell. It re-sends more (0.25 to 0.35 % against 0.04 %),
  because the trims it refuses are repaired.
- Zero tolerance reads -0.4 to +1.6 % of the control, so the control is a
  true zero on this cell too, with a wider seed spread than at 4:1.
- The seed spread on the vesting arm (4.5 to 7.5 %) is three points on a
  six-point effect; five seeds would be needed before quoting a single
  figure.

---

## 17. Goodput and completion-time distribution of the data-parallel all-reduce

Drawn 2026-09-22 from the local bundles of runs #123, #126 and #127,
worst configuration (`direct7`, 4:1, DCQCN unless stated), the three
seeds 9550582, 23172535 and 94081284. Files:
`figures/dp-allreduce-goodput-per-step.svg`,
`figures/dp-allreduce-goodput-summary.svg`,
`figures/dp-allreduce-time-cdf.svg`; script `figures/dp-allreduce-goodput.py` (run with the bundle root in
`SP`); numbers in `goodput.json` in the session scratchpad.

Definitions. For each (rank, step) the all-reduce completion time is the
end minus the start of that rank's data-parallel all-reduce collective
(`collective_events.csv`). The step span is the latest end minus the
earliest start over the 64 ranks. Delivered gradient bytes for a rank and
step are the algorithmic bucket size, 68 359 375 B, times the rank's
delivered share, `1 - forgiven / owed` from the flow telemetry (1 for the
arms that forgive nothing). Goodput per step is the sum over ranks of
delivered bytes divided by the step span, in GB/s; it nets out the loss,
so a forgiving arm is credited only for the bytes it delivered. The
summary goodput is the mean over the 16 non-critical steps, then the
mean and min to max over seeds. Sender-side shedding is not in these
figures because its per-flow telemetry is not in the local bundles.

| configuration | goodput, GB/s (3-seed mean; min to max) | relative to the p_low baseline | all-reduce time median | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| DCQCN baseline (no loss) | 118.1 (117.2 to 118.7) | -2 % | 32.5 ms | 43.2 ms | 46.7 ms |
| p_low baseline (0.5 % shed) | 120.1 (119.5 to 121.1) | 0 | 32.3 ms | 38.5 ms | 41.1 ms |
| forgiveness with congestion control on, p = 0.1 | 132.9 (132.0 to 133.8) | +11 % | 25.8 ms | 36.4 ms | 39.4 ms |
| FORGIVE, vesting and the exemption, p = 0.1 | 186.2 (184.2 to 187.8) | +55 % | 17.4 ms | 28.4 ms | 31.1 ms |
| no congestion control | 212.2 (one run) | +77 % | 18.4 ms | 23.0 ms | 23.8 ms |

The completion-time columns are over the 3 072 (rank, step) samples of
the non-critical steps pooled across the three seeds; p99 here is a
percentile of that pool, not a per-rank tail estimate with a confidence
interval.

Readings.

- Goodput rises more than the training time falls: FORGIVE's all-reduce
  goodput is 55 % above the p_low baseline's for a 16 % shorter training
  time, because the training time also contains compute and the
  tensor-parallel collectives, which FORGIVE does not touch.
- The goodput figure nets out the loss. FORGIVE delivers 92.4 % of the
  gradient bytes in 54 % of the all-reduce time of the baseline, which is
  the 55 %.
- FORGIVE's median all-reduce time is below the no-controller run's
  (17.4 against 18.4 ms) while its tail is longer (p99 28.4 against
  23.0 ms), which is the exemption's interruptions; the no-controller run
  has the shorter tail because it never reacts at all.
- On the critical steps the per-step figure shows FORGIVE at the
  baseline's goodput, which is the phase-aware schedule holding.

---

## 18. Five more metrics from the bundles in hand

Drawn 2026-09-22 from the local bundles of runs #123, #125, #126 and
#127, worst configuration (`direct7`, 4:1, DCQCN unless stated), budget
0.1 where a budget applies, seeds 9550582, 23172535 and 94081284 (five
at budget 0.4). Script `figures/forgive-metrics.py` (bundle root in
`SP`); numbers in `metrics2.json` in the session scratchpad. Every
summary counter the figures use (timeouts, CNPs, forgiven bytes,
retransmitted bytes) was recomputed from the per-flow telemetry of the
same bundle: 97 cross-checks, 0 mismatches; the minimum delivered share
recomputed from the flows equals the verified minimum (0.9001 on
non-critical steps, 0.9950 on critical steps).

**`dp-delivered-share-cdf.svg`.** CDF of the share of owed gradient bytes
delivered per (rank, step) under FORGIVE, 3 072 non-critical and 768
critical samples. Non-critical steps run from 0.9001 to about 0.925,
median 0.9056: the vesting cap spends the budget almost to the bound on
nearly every rank and step. Critical steps sit at 0.9950 to 0.9958, so
the 0.5 % budget is spent in full there too. No sample falls below its
bound.

**`fabric-cost-per-configuration.svg`.** Four panels, 3-seed mean with
min to max:

| configuration | retransmitted, % of bytes offered | trim ratio W, % | retransmission timeouts | CNPs received, millions |
| --- | ---: | ---: | ---: | ---: |
| DCQCN baseline | 3.48 to 3.73 | 2.97 to 3.18 | 10 042 to 10 622 | 12.70 to 13.51 |
| p_low baseline | 3.53 to 3.67 | 3.00 to 3.12 | 10 110 to 10 482 | 12.99 to 13.40 |
| forgiveness, congestion control on | 1.74 to 1.89 | 3.19 to 3.32 | 4 362 to 4 673 | 15.11 to 15.51 |
| FORGIVE | 5.22 to 5.88 | 6.71 to 7.36 | 4 145 to 4 348 | 4.43 to 4.59 |
| FORGIVE with pacing at 0.25 | 6.48 to 6.57 | 7.47 to 7.58 | 3 477 to 3 726 | 3.69 to 3.90 |
| budget in full at step start | 1.93 to 2.09 | 3.57 to 3.72 | 5 197 to 5 564 | 7.73 to 8.16 |
| exemption never withdrawn | 6.52 to 6.75 | 8.10 to 8.32 | 2 102 to 2 187 | 2.10 to 2.20 |
| no congestion control | 25.35 | 25.09 | 93 | 0 |

Exempt senders trim 2.2 to 2.4 times as much as the baseline and
retransmit 1.5 times as much, and they receive a third of the CNPs and
time out 40 % as often, because they finish sooner. Forgiveness without
the exemption receives more CNPs than the baseline (15.1 to 15.5 million
against 13.0 to 13.4), since every forgiven range's acknowledgement
carries the congestion mark the trim would have produced. The
up-front-budget configuration is the one with a low retransmission share
and a high timeout count, the signature of senders under rate cuts for
most of the step.

**`tp-collective-time-vs-baseline.svg`.** Tensor-parallel all-reduce time
(each collective's span across its 8 ranks, summed over steps) against
the p_low baseline on the same seed: DCQCN baseline +0.3 to +3.6 %,
forgiveness with congestion control on -3.8 to +4.5 %, FORGIVE -4.3 to
+4.4 %, pacing at 0.25 -7.6 to -1.2 %, budget in full at step start +4.1
to +6.1 %, exemption never withdrawn -9.0 to -2.6 %, no congestion
control -22.0 to -18.2 %. The seed spread of this metric is about
8 points, so only the up-front-budget (slower) and the never-withdrawn
and no-controller (faster) configurations are outside it.

**`goodput-vs-loss-sweep.svg`.** Goodput (section 17's definition) against
loss for the budget sweep. v1 rules (run #123): budget 0.05 153.7 to
155.7 GB/s at 3.74 to 3.77 % loss; 0.1 181.3 to 192.9 at 6.71 to 6.85 %;
0.2 213.4 to 226.6 at 11.0 to 12.1 %; 0.4 242.3 to 257.5 at 21.2 to
21.7 % (5 seeds); 0.6 238.1 to 249.6 at 37.5 to 38.4 %; 0.4 without the
phase-aware schedule 252.0 to 261.0 at 25.5 to 25.9 %. Vesting (run
#127): 184.2 to 187.8 at 7.55 to 7.57 %; with pacing at 0.25, 195.5 to
198.5 at 5.51 to 5.64 %. Pacing under the old rules (run #125): P = 0.1
202.7 to 211.5 at 2.61 to 2.92 %, P = 0.05 204.4 to 209.9 at 1.22 to
1.32 %. The p_low baseline is 119.5 to 121.1 and no congestion control
212.2.

Readings.

- Goodput saturates at budget 0.4 (242 to 258 GB/s) and falls at 0.6,
  because goodput nets out the loss and the extra loss at 0.6 no longer
  shortens the all-reduce.
- Pacing raises goodput at equal training time, because it lowers the
  loss: 195 to 199 against 184 to 188 under vesting at 0.25, and 203 to
  212 at P = 0.1 and 0.05 under the old rules, which is above the
  no-congestion-control run's 212 at a fortieth of its retransmission.
- v1 at 0.1 and vesting at 0.1 have the same DP all-reduce goodput
  (181 to 193 against 184 to 188) although their training-time
  reductions differ (12.9 to 14.1 % against 16.1 to 16.7 %). On seed
  9550582 the two configurations' DP all-reduce spans sum to 477.5 and
  473.1 ms while the training times differ by 64 ms, and the difference
  is in the tensor-parallel windows (994 against 900 ms, baseline 962).
  The residual between the two rule sets is therefore outside the DP
  all-reduce and not yet explained; it is an open item.

**`exemption-duty-cycle-per-step.svg`.** Share of data-parallel flow time
during which the sender is exempt (per exempt flow, time from the grant
to the flow's end less the time spent reacting to congestion signals;
summed over flows and divided by the total DP flow time of the step).
On non-critical steps FORGIVE is exempt 77 to 83 % of flow time (mean
81 %), pacing at 0.25 86 to 88 %, the up-front budget 30 to 38 %, and the
never-withdrawn configuration 85 to 87 % (its remainder is the one round
trip each flow spends before the grant). On critical steps FORGIVE is
exempt 15 to 25 % of flow time, the never-withdrawn configuration 52 to
55 %, and the up-front budget 0 to 1 %.

---

## 19. The fabric and the meaning of `direct<w>`

`figures/fabric-topology.svg`, drawn 2026-09-24 by `figures/fabric-topology.py`
from the code, not from memory. Facts, with their source:

- Two-tier leaf-spine Clos, 64 ranks, one host per rank, 8 hosts per leaf,
  8 leaves (`topology.py`: `leaf_count = host_count // hosts_per_leaf`).
- One 400 Gbps link from each host to its leaf and one 400 Gbps link from
  each leaf to every live spine (`_build_clos_topology`: one `TopologyLink`
  per host and one per (leaf, live spine) pair, all at `link_rate`). The
  leaf tier is fully connected to the live spine tier.
- One-way delays: host to leaf 5 us, leaf to spine 12.5 us
  (`HOST_TO_SWITCH_DELAY`, `SWITCH_TO_SWITCH_DELAY`).
- Oversubscription is the leaf ratio 8 x 400 Gbps in against live spines
  x 400 Gbps out: 1:1 = `spine_count 8, failed_spine_count 0`; 2:1 =
  `spine_count 4`; 4:1 = `spine_count 4, failed_spine_count 2`. A failed
  spine is absent from the built fabric and terminates no link; the
  manifest keeps the designed count.
- Rank layout (`rank_for`, TP fastest): rank = dp_rank x 8 + tp_rank, so a
  tensor-parallel group is the 8 hosts of one leaf and a data-parallel
  group is the same host position on every leaf; every DP flow crosses a
  spine.
- Per-flow ECMP across the live spines, seeded by the switch's node id
  (`switch-node.cc`), no spraying; PFC off; trimming in forward-trimmed-data
  mode with the trimmed class at 25 % WDRR weight and a 1 MiB queue.

`direct<w>` (`generate.py` `dp_fan_in`, ASTRA-sim `AllToAll.cc`): the DP
all-reduce runs ASTRA-sim's AllToAll collective with
`parallel_reduce = min(w, dp - 1)`. Each rank sends its shard to each of
its 7 peers and keeps `parallel_reduce` transfers in flight at once, to
distinct peers in ring order (`curr_receiver` advances after each
message); by symmetry it receives from as many peers at once. The number
bounds each direction separately: `direct7` is fan-out 7 and fan-in 7 at
the same time, `direct2` two and two, `ring` one. It is not a bound on the
sum of inbound and outbound transfers. `direct2` is not a ring: a ring
receives from one predecessor and sends to one successor (fan-in 1,
ASTRA-sim's `ring` implementation, not run in any FORGIVE wave; `direct1`
would be its direct analogue and has not been run); fan-in 2 is a tree or
a ring over two channels. Because each sender divides its
NIC among the peers it is sending to, the sustained aggregate into any
receiver is about one link's worth; the queue at the host link is
burstiness and finish-time imbalance, and the leaf-to-spine hop is the
second congestion point under oversubscription.

Checked against what was remembered: fully connected leaf-spine, yes;
the ideal case 8 leaves and 8 spines, yes (`*_1to1_*`); 8 GPUs per leaf,
yes; the stressed case 4:1, yes, and it is 4 designed spines with 2 failed
rather than 8 with 6 failed; `direct7` as "incast 7", yes for fan-in, and
also fan-out 7, not a sum of the two.

---

## 20. Run #131 (run 35956943724): the 63-source incast on the 1:1 fabric

Twelve records, main `7f787ba`, `direct7` at 1:1 (8 spines), the three
seeds, read 2026-09-25 from release tag `miiav5rlagazhvmyhwpiw4c5dlxyxmx5`
(local r131); all 21 arms re-analysed, the three FORGIVE arms verified
(worst delivered share 0.905, 0.916, 0.940). The burst is 63 sources of
128 MiB each into rank 8 at step 10 (8 GB, 160 ms at line rate),
priority group 3, outside every FORGIVE rule. "vs no-burst baseline" is
against the 1:1 p_low baselines without the burst (1247.7, 1253.1,
1260.2 ms); "vs own baseline" is against the paired p_low baseline that
ran with the burst.

| configuration | seed | training time | vs no-burst p_low baseline | vs own baseline | timeouts | retransmitted, % of bytes | trim ratio W, % | loss, % of DP bytes | burst drain at rank 8 | DP span, steps 10 / 11 / 12 / 13 / 14, ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| no congestion control, no burst | all three | 1126.3 ms | +9.7 to +10.6 % | | 96 | 0.87 | 0.81 | 0 | 30.8 ms (7 flows) | 8.5 / 8.0 / 6.5 / 8.1 / 9.1 |
| no congestion control, burst | all three | 1751.2 ms | -39.0 to -40.4 % | | 28 887 | 64.86 | 61.70 | 0 | 845.8 ms | 100.0 / 231.6 / 183.9 / 118.1 / 57.5 |
| DCQCN baseline (zero tolerance), burst | 9550582 | 1322.0 ms | -5.95 % | | 467 | 0.11 | 0.093 | 0 | 235.0 ms | 25.3 / 39.4 / 41.4 / 15.2 / 13.2 |
| | 23172535 | 1325.3 ms | -5.76 % | | 505 | 0.12 | 0.101 | 0 | 227.4 ms | 32.2 / 45.3 / 40.4 / 13.0 / 14.3 |
| | 94081284 | 1304.4 ms | -3.51 % | | 439 | 0.10 | 0.088 | 0 | 226.4 ms | 21.7 / 43.7 / 39.7 / 15.0 / 14.0 |
| p_low baseline, burst | 9550582 | 1303.4 ms | -4.46 % | 0 | 319 | 0.09 | 0.075 | 0.5 (shed) | 226.2 ms | 21.3 / 44.3 / 42.5 / 11.8 / 13.6 |
| | 23172535 | 1323.7 ms | -5.63 % | 0 | 304 | 0.08 | 0.071 | 0.5 (shed) | 227.4 ms | 29.3 / 44.1 / 38.8 / 12.2 / 14.8 |
| | 94081284 | 1311.9 ms | -4.10 % | 0 | 367 | 0.09 | 0.082 | 0.5 (shed) | 224.8 ms | 21.9 / 41.8 / 38.8 / 15.2 / 16.1 |
| sender-side shedding 0.1, burst | 9550582 | 1312.6 ms | -5.20 % | -0.70 % | 330 | 0.08 | 0.072 | 8.1 (shed) | 221.5 ms | 21.3 / 42.8 / 40.8 / 14.4 / 13.7 |
| | 23172535 | 1315.9 ms | -5.01 % | +0.59 % | 264 | 0.08 | 0.070 | 8.1 (shed) | 221.5 ms | 32.4 / 42.1 / 35.4 / 13.6 / 10.4 |
| | 94081284 | 1321.3 ms | -4.85 % | -0.72 % | 312 | 0.08 | 0.066 | 8.1 (shed) | 221.2 ms | 20.4 / 42.9 / 37.3 / 13.9 / 15.4 |
| loose baseline 0.1, burst | 9550582 | 1317.9 ms | -5.63 % | -1.11 % | 398 | 0.08 | 0.066 | 10 (shed) | 219.7 ms | 28.5 / 45.7 / 38.3 / 13.7 / 12.0 |
| | 23172535 | 1316.1 ms | -5.03 % | +0.57 % | 314 | 0.08 | 0.072 | 10 (shed) | 222.9 ms | 30.7 / 43.5 / 33.7 / 12.4 / 16.1 |
| | 94081284 | 1315.1 ms | -4.35 % | -0.25 % | 335 | 0.08 | 0.072 | 10 (shed) | 223.5 ms | 25.7 / 45.2 / 38.6 / 9.4 / 14.9 |
| FORGIVE 0.1, burst | 9550582 | 1246.2 ms | +0.12 % | +4.39 % | 422 | 0.09 | 0.399 | 1.38 | 221.6 ms | 12.9 / 35.1 / 41.6 / 10.9 / 7.2 |
| | 23172535 | 1242.1 ms | +0.88 % | +6.16 % | 322 | 0.07 | 0.312 | 1.05 | 218.6 ms | 10.7 / 36.9 / 36.7 / 13.2 / 9.8 |
| | 94081284 | 1242.3 ms | +1.42 % | +5.30 % | 367 | 0.08 | 0.385 | 1.32 | 220.9 ms | 13.2 / 36.9 / 39.3 / 12.2 / 6.9 |

Switch counters, seed 9550582: the no-congestion-control run with the
burst sent 119.5 million trim notifications (57.7 million at the last
hop) and 119.5 million retransmissions, and the switches dropped 1 945
trimmed headers; the DCQCN run with the burst sent 181 114 trim
notifications and dropped no trimmed header; the no-congestion-control
run without the burst sent 1.55 million.

Readings.

- The no-congestion-control runs are one run each (the seed moves
  nothing in them), so their two figures have no spread and the kill
  test's "within the seed spread" is a difference of 625 ms.
- Naive trimming with selective retransmission and no congestion control
  fails at this incast, and not by the predicted mechanism. The trimmed
  class overflowed only 1 945 times; the failure is retransmission
  amplification: 63 senders at line rate into one link have 62 of every
  63 packets trimmed, every trimmed packet is retransmitted at once, and
  the retransmission is trimmed again, so 65 % of all bytes on the fabric
  are retransmissions, the 8 GB burst takes 846 ms to drain (5.3 times
  line rate), 28 887 flows time out, and the flood on every leaf's
  uplinks slows the data-parallel all-reduce of every rank by 7 to 29
  times for five steps. Training time rises 55 % over the same transport
  without the burst.
- DCQCN absorbs the burst: the incast senders are rate-cut, the burst
  drains in 226 to 235 ms (1.4 times line rate), and training time rises
  3.5 to 6.0 % over the no-burst baseline.
- FORGIVE under the burst runs as fast as the baseline without any burst
  (1242 to 1246 ms against 1247.7 to 1260.2 ms), 4.4 to 6.2 % faster than
  its own paired baseline with the burst, for 1.05 to 1.38 % of DP bytes.
  The burst flows themselves run under DCQCN and drain in the same 219
  to 227 ms as in every DCQCN configuration; what FORGIVE recovers is the
  data-parallel time around the burst (steps 10, 13 and 14 return to
  their no-burst spans).
- Sender-side shedding and the loose baseline move within -1.1 to +0.6 %
  of their own baseline under the burst.
- The whole time lost to DCQCN on the 1:1 fabric without a burst is 9.7
  to 10.6 % (the no-congestion-control run at 1126.3 ms against the
  p_low baselines); FORGIVE recovered 4.5 to 7.5 of those points in run
  #130.

---

## 21. Run #132 (run 36093633307): the sweep, the references and P = 0 under the design of record

Twenty-six single FORGIVE runs at main `b6b81a5` (rules of `59cf16c`),
each joined by seed against the p_low baseline of the paired record that
already exists for its profile and seed (runs #123 and #125), read
2026-09-26 from release tag `luvt3kt6cduyzd7lqounyprr3uplta7t` (local
r132; baselines in scratchpad/base); every run re-analysed and verified.
One run pending at the time of writing: `direct2` seed 23172535 (courier
re-run after the run completed).

| profile | seed | training time | p_low baseline | reduction | loss gross / net, % of DP bytes | retransmitted | W | worst delivered share | timeouts | exempt share of DP flow time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| budget 0.05 | 9550582 | 1456.5 ms | 1696.7 ms | 14.16 % | 3.86 / 3.80 | 6.78 % | 7.32 % | 0.9500 | 4 473 | 74 % |
| budget 0.05 | 23172535 | 1443.7 ms | 1696.9 ms | 14.92 % | 3.84 / 3.79 | 6.60 % | 7.14 % | 0.9500 | 4 508 | 73 % |
| budget 0.05 | 94081284 | 1438.4 ms | 1700.6 ms | 15.42 % | 3.86 / 3.81 | 6.60 % | 7.15 % | 0.9500 | 4 761 | 72 % |
| budget 0.1 | 28410270 | 1422.9 ms | 1688.4 ms | 15.72 % | 7.50 / 7.44 | 5.64 % | 7.11 % | 0.9002 | 4 296 | 81 % |
| budget 0.1 | 81117450 | 1420.4 ms | 1709.9 ms | 16.93 % | 7.64 / 7.58 | 5.91 % | 7.40 % | 0.9001 | 4 430 | 80 % |
| budget 0.1, P = 0 | 9550582 | 1432.5 ms | 1696.7 ms | 15.57 % | 0 / 0 | 9.86 % | 9.53 % | 1.000 | 3 130 | 88 % |
| budget 0.1, P = 0 | 23172535 | 1442.5 ms | 1696.9 ms | 15.00 % | 0 / 0 | 10.47 % | 10.12 % | 1.000 | 3 312 | 89 % |
| budget 0.1, P = 0 | 94081284 | 1434.0 ms | 1700.6 ms | 15.67 % | 0 / 0 | 9.50 % | 9.16 % | 1.000 | 3 304 | 88 % |
| budget 0.2 | 9550582 | 1381.2 ms | 1696.7 ms | 18.60 % | 13.29 / 13.24 | 3.18 % | 6.11 % | 0.8004 | 4 022 | 85 % |
| budget 0.2 | 23172535 | 1396.5 ms | 1696.9 ms | 17.70 % | 13.50 / 13.44 | 3.02 % | 6.01 % | 0.8007 | 4 090 | 85 % |
| budget 0.2 | 94081284 | 1397.6 ms | 1700.6 ms | 17.81 % | 13.50 / 13.44 | 3.04 % | 6.02 % | 0.8004 | 4 374 | 85 % |
| budget 0.4 | 9550582 | 1384.4 ms | 1696.7 ms | 18.40 % | 16.38 / 16.32 | 1.90 % | 5.61 % | 0.674 | 4 232 | 85 % |
| budget 0.4 | 23172535 | 1386.0 ms | 1696.9 ms | 18.32 % | 16.08 / 16.02 | 1.82 % | 5.47 % | 0.683 | 4 140 | 85 % |
| budget 0.4 | 94081284 | 1387.6 ms | 1700.6 ms | 18.40 % | 16.15 / 16.09 | 1.84 % | 5.51 % | 0.637 | 4 324 | 85 % |
| budget 0.6 | 9550582 | 1384.1 ms | 1696.7 ms | 18.42 % | 17.21 / 17.15 | 1.85 % | 5.77 % | 0.569 | 4 221 | 86 % |
| budget 0.6 | 23172535 | 1389.3 ms | 1696.9 ms | 18.13 % | 16.81 / 16.75 | 1.80 % | 5.63 % | 0.684 | 4 119 | 85 % |
| budget 0.6 | 94081284 | 1402.3 ms | 1700.6 ms | 17.54 % | 16.10 / 16.04 | 1.81 % | 5.46 % | 0.670 | 4 519 | 85 % |
| budget 0.4, schedule off | 9550582 | 1352.7 ms | 1696.7 ms | 20.27 % | 20.84 / 20.77 | 1.61 % | 6.49 % | 0.656 | 2 559 | 85 % |
| budget 0.4, schedule off | 23172535 | 1315.0 ms | 1696.9 ms | 22.50 % | 20.34 / 20.27 | 1.47 % | 6.24 % | 0.651 | 2 313 | 85 % |
| budget 0.4, schedule off | 94081284 | 1320.5 ms | 1700.6 ms | 22.35 % | 20.01 / 19.94 | 1.54 % | 6.22 % | 0.694 | 2 473 | 85 % |
| forgive only, congestion control on, 0.1 | 9550582 | 1599.2 ms | 1696.7 ms | 5.75 % | 6.85 / 6.78 | 2.13 % | 3.52 % | 0.9001 | 4 938 | 0 |
| forgive only, congestion control on, 0.1 | 23172535 | 1575.7 ms | 1696.9 ms | 7.14 % | 6.27 / 6.22 | 1.84 % | 3.13 % | 0.9001 | 4 340 | 0 |
| forgive only, congestion control on, 0.1 | 94081284 | 1573.9 ms | 1700.6 ms | 7.45 % | 6.79 / 6.74 | 1.88 % | 3.29 % | 0.9002 | 4 449 | 0 |
| `direct2` 2:1, budget 0.1 | 9550582 | 1346.0 ms | 1428.6 ms | 5.78 % | 0.93 / 0.90 | 0.60 % | 0.53 % | 0.967 | 1 994 | 68 % |
| `direct2` 2:1, budget 0.1 | 94081284 | 1317.7 ms | 1408.9 ms | 6.47 % | 0.89 / 0.88 | 0.56 % | 0.49 % | 0.969 | 1 795 | 67 % |

Readings.

- P = 0 recovers 15.0 to 15.7 % at zero loss against 16.1 to 16.7 % for
  vesting on the same seeds (paired differences 1.0, 1.1, 1.1 points),
  with 9.5 to 10.5 % of bytes retransmitted against 5.2 to 5.9 %.
  Forgiveness is worth about one point of training time and half the
  retransmission load; the exemption is the other fifteen points.
- The vested sweep spends to its bound at 0.05, 0.1 and 0.2 (worst share
  equal to 1 - p) and not above: at 0.4 and 0.6 the loss stops at 16 to
  17 % because the fabric's trim ratio (5.5 to 5.8 %) no longer feeds
  the cap, and the two budgets read the same 17.5 to 18.4 %. Budget 0.05
  under vesting (14.2 to 15.4 % for 3.8 %) matches what the earlier rule
  set needed budget 0.2 for.
- Turning the schedule off at 0.4 adds 2 to 4 points of time (20.3 to
  22.5 % against 18.3 to 18.4 %) for 4 points of loss; the exempt share of flow time on critical steps rises from 15 to
  25 % to the non-critical 85 %.
- Forgive-only under the vested cap reads 5.8 to 7.5 % for 6.3 to 6.9 %
  (the earlier cap gave 5.5 to 6.6 % for 6.8 to 7.0 %).
- `direct2` at 2:1 and budget 0.1 recovers 5.8 to 6.5 % for 0.89 to
  0.93 % of DP bytes with the exemption held 67 to 68 % of flow time; at
  fan-in 2 the baseline trims 0.2 % and there is less for the exemption
  to recover.
