# Figure data and readings

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
`rt4732ejzjqe2hkar2bturuv3qav6pv3`.

---

## 0. Setup facts every caption needs

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

Chart: two-band timeline, July 20 to September 9 2026. One band for what
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
| 2026-08-22 | anchor family scaled to sixteen pi-derived seeds |
| 2026-09-05 | DCQCN knob and rate-cut telemetry; receiver forgiveness verdict in the transport |
| 2026-09-07 | congestion exemption for a forgiven flow |

Cluster waves:

| Date | Run | Size | What it was |
| --- | --- | --- | --- |
| 2026-09-01 | #117 | 30 of 31 comparisons, about 90 arms | sixteen-seed anchor, sweeps, one selective-repeat control |
| 2026-09-06 | #120 | 8 cells | regime map |
| 2026-09-07 | #121 | 6 comparisons, 24 arms | forgiveness with congestion exemption |
| 2026-09-08 | #122 | 14 records, 56 arms | dose front and phase-mask ablation |

Readings. Six weeks of the seven went into the instrument, because the
backend ASTRA-sim ships with is lossless RoCEv2 and models none of the
fabric the questions are about. The four waves all land in the last nine
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

Aggregates, paired, Student t at 15 degrees of freedom:

| estimand | mean | 95 % CI | verdict |
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
  percent everywhere with no protection buys 9.42 %; the phase-aware
  schedule keeps 3.91 % of that and hands back the rest to protect steps
  1 to 3, where it costs 242 ms.

---

## 3. What explains the relief, run #117

Chart: two scatter panels, same vertical axis. Vertical axis is
milliseconds saved on the window, roughly -500 to 900. Panel A
horizontal axis is trims avoided in millions, roughly -40 to 80. Panel B
horizontal axis is data-parallel payload discarded in GB, roughly 1.85 to
2.45.

| seed | ms saved | trims avoided, millions | GB discarded | baseline W | policy W |
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
- The one-line model that comes out of it: relief equals trims avoided
  times the recovery scheme's amplification factor. It predicts the
  selective-repeat control on the next chart correctly, at 79x and at 1x.
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
| 16-rank anchor, seed 31415926 | go-back-N | 2:1 | 8.68 | 6795 ms | 246 ms | 935 ms | 294 ms | 423 to 933 ms |
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
- Consequence for the policy: the same mechanism, unchanged, buys 3.9 to
  11.1 % under go-back-N and 0.78 % under selective repeat. This is the
  boundary of the run #117 result and it should be its own slide rather
  than a footnote.
- Every published bounded-loss result sits on the left-hand side of this
  chart: MLT and OptiReduce against TCP or UDP with millisecond timeouts,
  our own May evaluation against its bitmap-and-probe rounds, deployed
  RoCEv2 NICs on go-back-N.

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

## 6. FORGIVE at one operating point, run #121

Chart: grouped table or a four-bar comparison. No axes needed.

Worst cell of the map (DCQCN, fan-in 7, 4:1), three seeds, budget 0.4.

| arm | training window | all-reduce, non-critical steps | all-reduce, critical steps | gradient lost | bytes re-sent after trims |
| --- | ---: | ---: | ---: | ---: | ---: |
| tight baseline | 1686 to 1690 ms | 36 ms | 37 ms | 0.5 % | 3 % |
| sender-side shedding, 0.4 | 1480 to 1509 ms | 24 to 26 ms | 35 to 37 ms | 32 % | 2 % |
| FORGIVE with exemption, 0.4 | 1459 to 1468 ms | 20 to 21 ms | 36 to 37 ms | 8.8 to 9.5 % | 1 % |
| loose baseline, 0.4 | 1433 to 1466 ms | 23 to 25 ms | 22 to 26 ms | 40 % | 1 % |

Per seed the exempt arm ignored 10.4 to 10.9 million rate cuts, acted on
6.0 to 6.4 million, and re-armed 12 to 13 thousand of its 71 680 exempt
flows. The budget rule held in every ledger entry.

Readings.

- FORGIVE reaches a shorter window than sender-side shedding while
  discarding about a third as much gradient.
- Its critical steps do not move, while the loose baseline's critical
  steps speed up by a third. That difference is the safety property being
  sold, visible in a single row.
- Context from the map: the same cell without congestion control runs in
  1367 ms, so DCQCN's bill here is about 320 ms and the exempt arm gives
  back 225 of them.

---

## 7. The dose front, run #122

Chart: scatter with two connected series. Horizontal axis is gradient
bytes lost as a share of all data-parallel bytes, 0 to 50 %. Vertical
axis is training time recovered, 0 to 18 %. Label each point with its
budget. Optionally shade 0.7 to 3.3 % and mark 10 % on the horizontal
axis, which are MLT's published tolerance bounds.

Worst cell of the map, three seeds per budget except 0.4 which has two
new seeds here and three more in run #121.

Per-seed, all fourteen records:

| profile | seed | budget | baseline ms | FORGIVE % | shedding % | loose baseline % | FORGIVE loss, % of DP bytes | shedding loss, % of DP bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p01 | 9550582 | 0.1 | 1697 | 10.39 | 3.12 | 3.93 | 6.34 | 7.65 |
| p01 | 23172535 | 0.1 | 1697 | 10.52 | 2.45 | 2.64 | 6.51 | 7.70 |
| p01 | 94081284 | 0.1 | 1701 | 10.90 | 3.28 | 3.06 | 6.46 | 7.68 |
| p02 | 9550582 | 0.2 | 1697 | 12.02 | 4.86 | 7.22 | 8.48 | 15.67 |
| p02 | 23172535 | 0.2 | 1697 | 12.61 | 5.52 | 7.20 | 8.64 | 15.77 |
| p02 | 94081284 | 0.2 | 1701 | 12.96 | 5.45 | 6.65 | 8.43 | 15.77 |
| base | 28410270 | 0.4 | 1688 | 13.05 | 10.97 | 12.99 | 9.40 | 31.42 |
| base | 81117450 | 0.4 | 1710 | 13.47 | 11.78 | 14.27 | 9.32 | 31.62 |
| p06 | 9550582 | 0.6 | 1697 | 12.82 | 16.23 | 20.18 | 9.15 | 47.77 |
| p06 | 23172535 | 0.6 | 1697 | 12.93 | 15.95 | 20.30 | 9.29 | 47.98 |
| p06 | 94081284 | 0.6 | 1701 | 13.17 | 16.38 | 20.77 | 9.28 | 47.76 |
| allsteps | 9550582 | 0.4 | 1697 | 16.33 | 14.90 | 14.90 | 11.69 | 39.76 |
| allsteps | 23172535 | 0.4 | 1697 | 16.62 | 14.42 | 14.42 | 11.68 | 39.88 |
| allsteps | 94081284 | 0.4 | 1701 | 16.48 | 13.15 | 13.15 | 11.64 | 39.66 |

Plot points, seed ranges:

| budget | mask | FORGIVE time | FORGIVE loss | shedding time | shedding loss |
| ---: | --- | --- | --- | --- | --- |
| 0.1 | on | 10.4 to 10.9 % | 6.3 to 6.5 % | 2.4 to 3.3 % | 7.7 % |
| 0.2 | on | 12.0 to 13.0 % | 8.4 to 8.6 % | 4.9 to 5.5 % | 15.7 % |
| 0.4 | on | 13.0 to 13.5 % | 9.3 to 9.4 % | 11.0 to 11.8 % | 31.5 % |
| 0.6 | on | 12.8 to 13.2 % | 9.2 to 9.3 % | 16.0 to 16.4 % | 47.9 % |
| 0.4 | off | 16.3 to 16.6 % | 11.6 to 11.7 % | 13.2 to 14.9 % | 39.8 % |

Efficiency, points of training time recovered per percent of gradient
lost:

| budget | FORGIVE | shedding |
| ---: | ---: | ---: |
| 0.1 | 1.6 to 1.7 | 0.3 to 0.4 |
| 0.2 | 1.4 to 1.5 | 0.3 |
| 0.4 | 1.4 | 0.3 to 0.4 |
| 0.6 | 1.4 | 0.3 |
| 0.4, mask off | 1.4 | 0.3 to 0.4 |

Budget utilisation. The eligible share of DP bytes is 0.79, so the cap is
79 x budget, in percent of DP bytes:

| budget | cap | FORGIVE spends | utilisation |
| ---: | ---: | ---: | ---: |
| 0.1 | 7.9 % | 6.4 % | 81 % |
| 0.2 | 15.8 % | 8.5 % | 54 % |
| 0.4 | 31.6 % | 9.4 % | 30 % |
| 0.6 | 47.4 % | 9.2 % | 19 % |

Readings.

- The curve saturates above budget 0.2. Budget 0.1 already buys 80 % of
  the gain at two thirds of the loss, so the headline dose should be 0.1,
  not 0.4. That also puts the spent loss inside the range MLT profiles as
  tolerable.
- Aimed loss self-limits; blind loss does not. Sender-side shedding
  discards 0.79 x budget at every setting, exactly what its hash was told
  to do. FORGIVE converges to about 9.3 % and stops, because the fabric
  stops trimming.
- Efficiency is a flat constant across the whole front: four to five
  times, whatever the dose and whether or not the mask is on.
- Shedding only overtakes on time past a budget of about 0.45, where it
  is discarding a third of every gradient. No published tolerance result
  reaches there.
- Run #121's three seeds at budget 0.4 read 12.9, 13.1 and 13.5 %, so
  that point now rests on five seeds spanning 12.9 to 13.5.

---

## 8. What the phase mask costs and whether it holds, run #122

Chart: two panels, or a table. Panel A is the cost, panel B is the
integrity check.

Cost of the mask, budget 0.4, three seeds each:

| arm | training time recovered | gradient lost |
| --- | ---: | ---: |
| mask on, protects steps 1, 2, 3, 20 | 13.0 to 13.5 % | 9.3 to 9.4 % |
| mask off, budget 0.4 everywhere | 16.3 to 16.6 % | 11.6 to 11.7 % |
| difference | 3.2 points | 2.3 points |

Integrity, share of forgiven bytes placed on the four critical steps.
A uniform policy would place 4/20, that is 20 %, there:

| profile | budget | critical-step share of forgiven bytes | ledger violations |
| --- | ---: | ---: | ---: |
| p01 | 0.1 | 1.45 to 1.53 % | 0 |
| p02 | 0.2 | 1.11 to 1.14 % | 0 |
| base | 0.4 | 1.02 to 1.03 % | 0 |
| p06 | 0.6 | 1.02 to 1.04 % | 0 |
| allsteps | 0.4 | 19.28 to 20.80 % | 0 |

The budget law verified with zero violations in all fourteen records,
1280 ledger cells each.

Per-step all-reduce span, seed 9550582, budget 0.1, milliseconds. Steps
1, 2, 3 and 20 are the protected ones:

| step | baseline | FORGIVE | shedding | FORGIVE % | shedding % |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 34.5 | 35.1 | 34.5 | -1.7 | 0.0 |
| 2 | 34.9 | 36.4 | 34.9 | -4.2 | 0.0 |
| 3 | 37.4 | 38.8 | 37.4 | -3.8 | 0.0 |
| 4 | 39.3 | 21.1 | 33.5 | 46.2 | 14.7 |
| 5 | 40.0 | 23.9 | 35.1 | 40.3 | 12.3 |
| 6 | 36.7 | 21.2 | 32.2 | 42.3 | 12.3 |
| 7 | 36.1 | 27.6 | 30.9 | 23.3 | 14.3 |
| 8 | 37.3 | 24.2 | 35.3 | 35.1 | 5.5 |
| 9 | 32.7 | 24.5 | 32.6 | 25.0 | 0.2 |
| 10 | 35.8 | 23.0 | 33.7 | 35.8 | 6.0 |
| 11 | 39.3 | 24.9 | 31.7 | 36.8 | 19.4 |
| 12 | 36.5 | 29.3 | 31.0 | 19.8 | 15.1 |
| 13 | 39.0 | 23.7 | 33.5 | 39.2 | 14.1 |
| 14 | 34.3 | 23.3 | 35.0 | 31.9 | -2.2 |
| 15 | 39.4 | 24.4 | 32.6 | 38.1 | 17.2 |
| 16 | 35.6 | 23.8 | 33.2 | 33.2 | 6.7 |
| 17 | 35.8 | 20.7 | 33.5 | 42.2 | 6.4 |
| 18 | 33.7 | 24.0 | 32.5 | 28.7 | 3.4 |
| 19 | 36.5 | 32.4 | 40.8 | 11.3 | -11.7 |
| 20 | 37.6 | 34.1 | 37.9 | 9.3 | -0.6 |

Same seed with the mask removed, for contrast:

| step | baseline | FORGIVE | FORGIVE % |
| ---: | ---: | ---: | ---: |
| 1 | 34.5 | 20.5 | 40.6 |
| 2 | 34.9 | 26.8 | 23.2 |
| 3 | 37.4 | 19.1 | 49.0 |
| 20 | 37.6 | 22.0 | 41.7 |

Readings.

- The mask costs 3.2 points of training time and buys back 2.3 points of
  gradient loss on four steps out of twenty. That is the price of the
  safety property, and it is now a number rather than an assertion.
- Prove the mask with the ledger, not with the clock. Masked runs place
  1.0 to 1.5 % of forgiven bytes on the protected steps against the 19 to
  21 % a uniform policy puts there.
- Per-step timings carry a noise floor of roughly plus or minus 13 % at
  one seed. Within a seed, steps 1 to 3 read identically at budgets 0.1,
  0.2 and 0.6, which shows the scatter is arm-level randomness rather
  than a budget effect. The one signal well above that floor is the
  mask-off run's 23 to 49 % on those same steps.
- Sanity check worth mentioning if anyone doubts the mask is wired up:
  the exempt flow count is 71 680 with the mask and 89 600 without, a
  ratio of exactly 20/16.

---

## 9. Why sender-side shedding cannot relieve a controlled fabric

Chart: two bar panels. Panel A is time to finish the same payload. Panel
B is rate achieved on the wire. Four bars each.

All four arms owe the same 70.0 GB of all-reduce payload across the 16
non-critical steps. Worst cell of the map, budget 0.1, seed 9550582.

| arm | time for that payload | physical bytes moved | wire rate | peak switch queue |
| --- | ---: | ---: | ---: | ---: |
| baseline, 0.5 % everywhere | 588 ms | 152.3 GB | 259 GB/s | 4 194 316 B |
| sender-side shedding at 0.1 | 537 ms | 137.8 GB | 257 GB/s | 4 194 316 B |
| loose baseline at 0.1 | 525 ms | 134.1 GB | 255 GB/s | 4 194 316 B |
| FORGIVE with exemption | 392 ms | 153.3 GB | 391 GB/s | 4 194 268 B |

Control-plane counters for the same four arms:

| arm | congestion notifications generated | acted on | ignored | per GB offered | trimmed GB | re-sent GB | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 12.99 M | 12.99 M | 0 | 16 382 | 23.8 | 23.8 | 10 110 |
| shedding at 0.1 | 11.53 M | 11.53 M | 0 | 14 822 | 21.0 | 21.0 | 8 964 |
| loose baseline | 11.56 M | 11.56 M | 0 | 14 926 | 20.2 | 20.2 | 8 041 |
| FORGIVE | 15.81 M | 7.89 M | 7.92 M | 9 944 | 25.3 | 13.2 | 5 415 |

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
  wire, provokes 22 % more notifications than the baseline, acts on 39 %
  fewer, and moves the same payload 51 % faster. It also halves the
  timeouts, because a forgiven byte range never waits for a repair.
- Structural version of the same point: the load is a seven-way fan-in,
  and congestion at an incast is set by how many senders arrive at once.
  Uniform shedding removes bytes from all seven senders and never removes
  a sender. Seven-to-one becomes 6.3-to-one.
- The makespan arithmetic closes with no residue. The all-reduce is about
  42 % of an 85 ms step and 16 of 20 steps are eligible, so shedding's
  8.7 % span cut predicts 2.9 % of makespan against 3.1 % measured, and
  FORGIVE's 33 % predicts 11 % against 10.4 % measured.

---

## 10. Exemption counters across the front, run #122

Chart: line or bar against budget. Useful as a backup slide when someone
asks why the front saturates.

| profile | budget | seeds | forgiven GB | notifications ignored, M | acted on, M | ignored share | flows re-armed | timeouts | receiver refusals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p01 | 0.1 | 3 | 12.1 to 12.5 | 7.84 to 7.92 | 7.89 to 8.41 | 48.4 to 50.1 % | 19 442 to 20 644 | 5 415 to 6 104 | 1.09 to 1.19 M |
| p02 | 0.2 | 3 | 16.1 to 16.5 | 9.63 to 10.01 | 6.79 to 7.08 | 58.2 to 59.2 % | 15 392 to 15 888 | 3 899 to 4 100 | 1.04 to 1.20 M |
| base | 0.4 | 2 | 17.8 to 18.0 | 10.78 to 10.94 | 6.10 to 6.37 | 62.9 to 64.2 % | 12 185 to 12 291 | 3 112 to 3 466 | 1.07 to 1.26 M |
| p06 | 0.6 | 3 | 17.5 to 17.8 | 10.76 to 11.00 | 5.70 to 5.99 | 64.2 to 65.5 % | 10 900 to 11 532 | 2 955 to 3 267 | 1.00 to 1.23 M |
| allsteps | 0.4 | 3 | 22.3 to 22.4 | 13.74 to 13.77 | 4.15 to 4.31 | 76.1 to 76.8 % | 15 509 to 15 773 | 1 182 to 1 257 | 0 |

Readings.

- The share of rate cuts a sender can ignore ceilings at 64 to 65 % from
  budget 0.4 upward. That ceiling is the mechanical reason the time curve
  saturates, and it also caps the loss.
- Timeouts fall monotonically as the budget rises, from 6 104 at 0.1 to
  2 955 at 0.6, and to about 1 200 with the mask off. Forgiveness removes
  the repairs that were waiting to time out.
- With the mask off the receiver never refuses a single range: the budget
  is never exhausted anywhere, so the refusal counter is exactly zero in
  all three seeds. That is the cleanest evidence that the budget, not the
  policy, is what binds in the masked runs.
- Flows re-arm on the first repair of any kind, not only on a refusal,
  which is why the mask-off runs still show about 15 500 re-arms with
  zero refusals.

---

## 11. Mechanism diagram, no data

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
   bytes for that pair. Counters only grow, and the entry closes when
   that rank finishes the step. Critical steps carry a tighter budget.
3. An eligible flow ignores rate cuts until the receiver refuses it.
   While exempt, the sender discards every congestion notification. The
   receiver's first repair request re-arms it, so an exemption cannot
   outlive the budget that justified it.

Supporting fact for the design choice, worth a line on the slide: the ECN
marking threshold is 800 KB at 400 Gb/s and the trim point is 4 MiB, so
at least 74 % of notifications at the worst cell are ECN-marked rather
than trim-caused, 13.5 million against 3.4 million. Suppressing only the
notification our own forgiveness provoked would not move the window.

---

## 12. Numbers that should not be plotted

Keep these out of the deck, and be ready to say why.

| number | why not |
| --- | --- |
| per-rank p99 improvement | -4.9 % mean across sixteen seeds, CI [-19.6, +9.8]. Top three of 320 samples; one path collision moves it by half |
| worst-collective relief as a percentage | 10.8 % mean, CI [-0.60, 22.20], spans zero. Report the 153 ms with CI [5, 302] instead |
| the run #117 dose grid | ran unmatched, because the profile name entered the selection hash. Fixed in commit `63ef7c2`, not yet re-run |
| `wire_per_offered` | hop-weighted, not bytes a receiver saw |
| the 24.8 % from our own May preprint | measured with a fully blocking worker loop, so it includes network time a modern framework hides. It is our earlier number rather than a rival's, and nothing in this file is comparable with it |
| single-seed sweeps, fan-in and burst-source counts | directional only, no error bars |
