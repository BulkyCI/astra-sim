# Run #130: the 1:1 fabric without the incast, every metric

The three-seed, four-arm run on the non-oversubscribed fabric (eight spines,
none failed) that gives the 1:1 FORGIVE result, plus the two reference arms
run beside it (DCQCN without any loss, and the no-congestion-control run
reused from the incast wave). Everything below is recomputed from the
release bundles by `r130-raw.py` (scratchpad copy; the same reads as
`docs/agents/figures/incast-with-forgive-no-incast.py`), per seed, nothing
averaged unless the column says mean. Numbers in `docs/agents/incast-figure-data.md`
section 3 and in `forgive/forgive.md` section 3.7 of the paper repository
agree with these.

## 1. Setup (profile.json of every arm)

64 ranks on eight leaves of eight hosts, tensor parallel 8 within a leaf,
data parallel 8 across leaves, 20 training steps, 5 376 us of compute per
step. Each step runs two tensor-parallel AllReduces per layer of 64 MiB and
one data-parallel AllReduce of 68 359 375 bytes per rank as `direct7`
(AllToAll with up to seven transfers in flight per rank per direction).
Fabric: two-tier Clos, 400 Gbps links, 4 096-byte payloads, 32 MB switch
buffers, no PFC, packet trimming (fast trim and deliver), selective repair,
retransmission timeout 1 ms. Congestion control DCQCN in every arm but the
last. Steps 1, 2, 3 and 20 are the loss-sensitive steps; the loss parameter
is 0.005 there and 0.1 elsewhere. A seven-flow background burst of 128 MiB
each lands on rank 8 at step 18 in every arm (the pre-registered 1:1 kill
test, which did not fire).

| Arm (name in Table IV of the paper) | What the sender or receiver does with the data-parallel bytes |
| --- | --- |
| Baseline | DCQCN; the sender drops 0.5 % of the messages of every step before sending them (fixed p_low) |
| DCQCN, 10 % dropping | DCQCN; the sender drops 10 % of the messages of every step (fixed p_high) |
| DBLP dropping | DCQCN; the sender drops 0.5 % on the loss-sensitive steps and 10 % elsewhere, no exemption |
| FORGIVE | DCQCN; nothing dropped at the sender; the receiver forgives trimmed ranges within the step budget (0.005 or 0.1 of its bytes), P = 0.1, senders exempt from the congestion response while the budget holds |
| DCQCN, no loss | DCQCN; every byte delivered |
| No CC | no congestion control; every byte delivered (run #131 bundle, the same profile with the burst disabled; seed-invariant) |

Sender-side dropping works on whole 2 136 230-byte messages, so a "0.5 %"
drop is 456 of 89 600 messages over the run and up to 4 of the 70 messages
one rank expects in one step (a 5.7 % hole in that (rank, step) cell).
FORGIVE's loss is per 4 KB range and is bounded per cell by the budget.

## 2. Completion time

Job completion time is the last rank's completion. "Reduction" is against the baseline of the same seed. Data-parallel AllReduce time per step is the span from the first data-parallel flow start to the last flow end of that step over all ranks; the sum is over the 20 steps, the mean over the 16 non-critical steps. Tensor-parallel figures are per collective event (5 120 per run).

| Arm | Seed | Job completion (ms) | Reduction vs baseline | DP AllReduce, sum of 20 steps (ms) | DP AllReduce, non-critical mean (ms) | DP AllReduce, worst step (ms) | TP AllReduce mean (ms) | TP AllReduce p99 (ms) | TP AllReduce max (ms) |
|---|---|---|---|---|---|---|---|---|---|
| Baseline | 9550582 | 1247.7 | 0.0 % | 284.9 | 13.82 | 19.0 | 6.03 | 13.62 | 19.59 |
| Baseline | 23172535 | 1253.1 | 0.0 % | 274.1 | 14.02 | 21.3 | 6.15 | 11.07 | 13.85 |
| Baseline | 94081284 | 1260.2 | 0.0 % | 294.1 | 14.72 | 25.2 | 6.12 | 11.36 | 14.81 |
| DCQCN, 10 % dropping | 9550582 | 1252.2 | -0.4 % | 285.7 | 14.49 | 25.1 | 6.16 | 11.37 | 15.11 |
| DCQCN, 10 % dropping | 23172535 | 1249.5 | 0.3 % | 296.6 | 14.99 | 21.4 | 6.10 | 11.61 | 14.36 |
| DCQCN, 10 % dropping | 94081284 | 1251.4 | 0.7 % | 289.4 | 15.00 | 19.5 | 6.24 | 11.59 | 14.94 |
| DBLP dropping | 9550582 | 1244.0 | 0.3 % | 289.7 | 14.36 | 19.3 | 5.98 | 11.35 | 15.80 |
| DBLP dropping | 23172535 | 1251.5 | 0.1 % | 295.9 | 15.10 | 20.0 | 6.11 | 11.72 | 13.07 |
| DBLP dropping | 94081284 | 1257.2 | 0.2 % | 290.5 | 14.39 | 19.2 | 6.17 | 11.89 | 14.45 |
| FORGIVE | 9550582 | 1191.8 | 4.5 % | 178.0 | 8.83 | 21.0 | 6.42 | 11.60 | 13.94 |
| FORGIVE | 23172535 | 1183.7 | 5.5 % | 189.1 | 9.06 | 17.2 | 6.24 | 11.30 | 14.10 |
| FORGIVE | 94081284 | 1166.3 | 7.5 % | 178.0 | 8.52 | 12.9 | 6.12 | 11.90 | 12.45 |
| DCQCN, no loss | 9550582 | 1252.3 | -0.4 % | 277.9 | 14.08 | 19.2 | 6.10 | 11.55 | 14.80 |
| DCQCN, no loss | 23172535 | 1238.8 | 1.1 % | 284.6 | 14.47 | 20.7 | 5.93 | 11.09 | 14.71 |
| DCQCN, no loss | 94081284 | 1240.4 | 1.6 % | 277.6 | 13.80 | 21.1 | 6.03 | 11.15 | 13.02 |
| No CC | 9550582 | 1126.3 | 9.7 % | 179.9 | 9.24 | 12.3 | 5.65 | 11.43 | 13.17 |
| No CC | 23172535 | 1126.3 | 10.1 % | 179.9 | 9.24 | 12.3 | 5.65 | 11.43 | 13.17 |
| No CC | 94081284 | 1126.3 | 10.6 % | 179.9 | 9.24 | 12.3 | 5.65 | 11.43 | 13.17 |

Seed means: Baseline 1253.7 ms; DCQCN, 10 % dropping 1251.1 ms; DBLP dropping 1250.9 ms; FORGIVE 1180.6 ms; DCQCN, no loss 1243.8 ms; No CC 1126.3 ms.

## 3. Loss and fabric cost of the data-parallel traffic

Expected bytes = the bytes the 89 600 data-parallel messages of a run carry (about 191.4 GB). Loss = 1 - delivered / expected, where delivered counts bytes the receiver accepted; for the dropping arms it is the dropped messages, for FORGIVE the forgiven ranges (no byte is both). Retransmitted is re-sent bytes as a share of expected; trimmed is trimmed bytes that were repaired (forgiven ranges are not in it), as a share of expected. Switch trims are the fabric's count of trimmed data packets (`trim_ftd_admission`) over all traffic. CNPs are congestion notification packets received by data-parallel senders. Worst cell = the lowest delivered share of any (destination rank, step).

| Arm | Seed | Loss (% of expected) | Dropped at sender (%) | Forgiven (%) | Retransmitted (%) | Trimmed (%) | Switch trims (count) | Last-hop trims (count) | Timeouts (DP) | CNPs (DP) | Worst cell delivered share | Worst non-critical cell | Worst critical cell |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | 9550582 | 0.509 | 0.509 | 0.000 | 0.184 | 0.142 | 64,143 | 5,956 | 179 | 593,246 | 0.9429 (rank 4, step 6) | 0.9429 | 0.9571 |
| Baseline | 23172535 | 0.499 | 0.499 | 0.000 | 0.147 | 0.111 | 49,846 | 9,365 | 170 | 587,513 | 0.9429 (rank 15, step 9) | 0.9429 | 0.9571 |
| Baseline | 94081284 | 0.484 | 0.484 | 0.000 | 0.114 | 0.090 | 42,075 | 2,970 | 117 | 511,055 | 0.9429 (rank 42, step 3) | 0.9571 | 0.9429 |
| DCQCN, 10 % dropping | 9550582 | 10.050 | 10.050 | 0.000 | 0.087 | 0.067 | 31,178 | 5,804 | 132 | 449,065 | 0.7571 (rank 52, step 15) | 0.7571 | 0.7857 |
| DCQCN, 10 % dropping | 23172535 | 10.172 | 10.172 | 0.000 | 0.072 | 0.052 | 24,141 | 6,233 | 113 | 381,259 | 0.7714 (rank 39, step 14) | 0.7714 | 0.7714 |
| DCQCN, 10 % dropping | 94081284 | 10.021 | 10.021 | 0.000 | 0.082 | 0.062 | 28,824 | 3,020 | 110 | 383,240 | 0.7714 (rank 8, step 13) | 0.7714 | 0.7857 |
| DBLP dropping | 9550582 | 8.119 | 8.119 | 0.000 | 0.129 | 0.100 | 45,981 | 4,897 | 150 | 474,811 | 0.7571 (rank 52, step 15) | 0.7571 | 0.9571 |
| DBLP dropping | 23172535 | 8.163 | 8.163 | 0.000 | 0.102 | 0.079 | 38,168 | 2,036 | 111 | 441,801 | 0.7714 (rank 39, step 14) | 0.7714 | 0.9571 |
| DBLP dropping | 94081284 | 8.128 | 8.128 | 0.000 | 0.131 | 0.095 | 44,373 | 4,733 | 164 | 460,492 | 0.7714 (rank 8, step 13) | 0.7714 | 0.9429 |
| FORGIVE | 9550582 | 1.004 | 0.000 | 1.004 | 0.146 | 0.095 | 513,737 | 5,434 | 234 | 158,200 | 0.9454 (rank 10, step 7) | 0.9454 | 0.9950 |
| FORGIVE | 23172535 | 1.302 | 0.000 | 1.302 | 0.135 | 0.092 | 652,086 | 4,950 | 183 | 145,750 | 0.9156 (rank 21, step 7) | 0.9156 | 0.9951 |
| FORGIVE | 94081284 | 1.115 | 0.000 | 1.115 | 0.112 | 0.077 | 557,854 | 5,310 | 154 | 97,469 | 0.9477 (rank 12, step 8) | 0.9477 | 0.9951 |
| DCQCN, no loss | 9550582 | 0.000 | 0.000 | 0.000 | 0.182 | 0.144 | 67,303 | 5,490 | 157 | 647,833 | 1.0000 (rank 0, step 1) | 1.0000 | 1.0000 |
| DCQCN, no loss | 23172535 | 0.000 | 0.000 | 0.000 | 0.228 | 0.178 | 85,399 | 5,159 | 175 | 599,084 | 1.0000 (rank 0, step 1) | 1.0000 | 1.0000 |
| DCQCN, no loss | 94081284 | 0.000 | 0.000 | 0.000 | 0.149 | 0.116 | 51,698 | 9,234 | 142 | 544,537 | 1.0000 (rank 0, step 1) | 1.0000 | 1.0000 |
| No CC | 9550582 | 0.000 | 0.000 | 0.000 | 3.023 | 2.893 | 1,323,296 | 240,543 | 0 | 0 | 1.0000 (rank 0, step 1) | 1.0000 | 1.0000 |
| No CC | 23172535 | 0.000 | 0.000 | 0.000 | 3.023 | 2.893 | 1,323,296 | 240,543 | 0 | 0 | 1.0000 (rank 0, step 1) | 1.0000 | 1.0000 |
| No CC | 94081284 | 0.000 | 0.000 | 0.000 | 3.023 | 2.893 | 1,323,296 | 240,543 | 0 | 0 | 1.0000 (rank 0, step 1) | 1.0000 | 1.0000 |

Every FORGIVE cell is at or above its bound (0.900 on non-critical steps,
0.995 on critical ones). The dropping arms have no per-cell bound, which is
why their worst cells sit at 0.943 (baseline) and 0.757 (10 % dropping).
The no-CC run retransmits 3.0 % of the data-parallel bytes against 0.07 to
0.23 % under DCQCN; FORGIVE keeps retransmission at the DCQCN level because
the forgiven ranges are never re-sent.

Tensor-parallel traffic (286 720 flows per run) loses nothing in any arm;
its retransmitted share is below 0.001 % under DCQCN and 0.011 % without
congestion control.

## 4. Exemption counters (FORGIVE only)

From the per-flow telemetry: exempt = data-parallel flows granted the exemption at creation; withheld = congestion notifications the sender did not pass to DCQCN; budget-exhausted reports = receiver reports that outstanding trims exceeded the budget; transitions = sender switches between exempt and obeying; duty cycle = share of data-parallel flow time spent exempt; soft refusals = the `soft_refusals` column, bytes the receiver declined to forgive because the vesting cap was reached at that moment.

| Seed | Exempt flows (of 89 600) | Signals withheld | Budget-exhausted reports | Transitions | Exemption duty cycle | Soft refusals (MB) | Forgiven ranges | Forgiven bytes (MB) |
|---|---|---|---|---|---|---|---|---|
| 9550582 | 89,261 | 3,651,915 | 602,494 | 6,823 | 97.8 % | 130.0 | 469,513 | 1921.1 |
| 23172535 | 89,224 | 4,107,656 | 617,147 | 5,694 | 97.7 % | 144.4 | 609,201 | 2492.8 |
| 94081284 | 89,423 | 3,829,420 | 364,803 | 4,882 | 98.6 % | 107.0 | 521,771 | 2134.9 |

## 5. Flow completion time

Per flow, from start to the receiver's last byte or forgiveness decision, in microseconds; data-parallel flows are 2 136 230 bytes, tensor-parallel flows 2 097 152 bytes.

| Arm | Seed | DP p50 | DP p95 | DP p99 | DP max | TP p50 | TP p95 | TP p99 | TP max |
|---|---|---|---|---|---|---|---|---|---|
| Baseline | 9550582 | 376 | 1368 | 1501 | 3803 | 88 | 203 | 289 | 2078 |
| Baseline | 23172535 | 376 | 1366 | 1472 | 3718 | 89 | 218 | 303 | 3396 |
| Baseline | 94081284 | 376 | 1359 | 1470 | 2921 | 89 | 220 | 307 | 1767 |
| DCQCN, 10 % dropping | 9550582 | 373 | 1330 | 1444 | 2974 | 90 | 220 | 312 | 2346 |
| DCQCN, 10 % dropping | 23172535 | 373 | 1315 | 1433 | 2644 | 85 | 217 | 306 | 2527 |
| DCQCN, 10 % dropping | 94081284 | 373 | 1305 | 1436 | 2740 | 88 | 238 | 316 | 1842 |
| DBLP dropping | 9550582 | 374 | 1336 | 1462 | 2864 | 88 | 203 | 295 | 2595 |
| DBLP dropping | 23172535 | 374 | 1326 | 1450 | 3669 | 88 | 217 | 306 | 1491 |
| DBLP dropping | 94081284 | 374 | 1332 | 1453 | 3906 | 87 | 222 | 307 | 2203 |
| FORGIVE | 9550582 | 377 | 487 | 1368 | 2375 | 92 | 254 | 319 | 2323 |
| FORGIVE | 23172535 | 378 | 493 | 1350 | 2499 | 87 | 248 | 317 | 1516 |
| FORGIVE | 94081284 | 377 | 487 | 792 | 2145 | 89 | 210 | 306 | 2689 |
| DCQCN, no loss | 9550582 | 376 | 1374 | 1495 | 3726 | 88 | 214 | 296 | 2360 |
| DCQCN, no loss | 23172535 | 376 | 1367 | 1500 | 4178 | 89 | 191 | 289 | 3502 |
| DCQCN, no loss | 94081284 | 376 | 1357 | 1476 | 3826 | 87 | 206 | 293 | 1287 |
| No CC | 9550582 | 384 | 594 | 746 | 1471 | 84 | 182 | 286 | 1884 |
| No CC | 23172535 | 384 | 594 | 746 | 1471 | 84 | 182 | 286 | 1884 |
| No CC | 94081284 | 384 | 594 | 746 | 1471 | 84 | 182 | 286 | 1884 |

The data-parallel p95 is where the arms separate: 1 305 to 1 374 us under
every DCQCN arm that obeys the controller, 487 to 493 us under FORGIVE,
594 us without congestion control. The medians are within about 3 % of one
another because most flows never see a trim.

## 6. Per-step data-parallel AllReduce time (ms)

| Arm | Seed | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | 9550582 | 10.4 | 18.1 | 18.7 | 12.2 | 17.1 | 16.5 | 13.2 | 11.7 | 10.8 | 12.1 | 12.9 | 12.2 | 12.5 | 13.9 | 16.5 | 13.0 | 12.0 | 15.4 | 19.0 | 16.5 |
| Baseline | 23172535 | 11.3 | 12.9 | 14.9 | 11.2 | 15.3 | 11.0 | 11.8 | 11.2 | 14.7 | 14.7 | 11.5 | 13.4 | 15.0 | 17.6 | 11.9 | 12.8 | 14.6 | 21.3 | 16.4 | 10.8 |
| Baseline | 94081284 | 12.5 | 14.2 | 18.4 | 13.7 | 12.5 | 14.8 | 14.9 | 12.1 | 10.5 | 16.5 | 15.2 | 17.2 | 11.3 | 19.8 | 11.6 | 13.5 | 12.3 | 14.4 | 25.2 | 13.5 |
| DCQCN, 10 % dropping | 9550582 | 11.6 | 17.2 | 15.5 | 15.6 | 15.5 | 11.5 | 10.2 | 13.4 | 13.0 | 12.9 | 15.1 | 14.9 | 10.9 | 15.3 | 17.8 | 14.9 | 12.8 | 13.0 | 25.1 | 9.6 |
| DCQCN, 10 % dropping | 23172535 | 10.9 | 15.1 | 15.0 | 14.4 | 13.7 | 14.4 | 15.0 | 17.4 | 13.2 | 18.5 | 13.9 | 11.7 | 13.9 | 13.4 | 10.4 | 15.2 | 15.5 | 18.0 | 21.4 | 15.8 |
| DCQCN, 10 % dropping | 94081284 | 10.3 | 15.5 | 13.5 | 16.7 | 15.3 | 12.5 | 14.6 | 16.1 | 13.8 | 13.8 | 17.4 | 13.6 | 14.0 | 16.9 | 11.0 | 15.9 | 14.8 | 14.1 | 19.5 | 10.1 |
| DBLP dropping | 9550582 | 10.4 | 18.1 | 18.7 | 11.9 | 13.4 | 16.6 | 10.0 | 14.8 | 15.6 | 13.3 | 14.0 | 14.9 | 16.2 | 11.8 | 11.3 | 16.0 | 14.0 | 16.6 | 19.3 | 12.7 |
| DBLP dropping | 23172535 | 11.3 | 12.9 | 14.9 | 11.2 | 13.2 | 16.8 | 14.1 | 18.0 | 11.3 | 14.5 | 17.6 | 15.0 | 13.5 | 12.3 | 15.7 | 17.8 | 19.2 | 11.3 | 20.0 | 15.2 |
| DBLP dropping | 94081284 | 12.5 | 14.2 | 18.4 | 14.8 | 10.3 | 11.4 | 16.9 | 17.0 | 19.1 | 11.3 | 13.4 | 12.7 | 16.8 | 19.2 | 10.9 | 10.4 | 14.0 | 17.7 | 14.3 | 15.3 |
| FORGIVE | 9550582 | 9.3 | 8.8 | 10.3 | 13.9 | 6.9 | 7.5 | 6.4 | 6.8 | 6.3 | 7.8 | 6.0 | 7.5 | 8.9 | 8.9 | 7.1 | 5.6 | 10.8 | 10.0 | 21.0 | 8.3 |
| FORGIVE | 23172535 | 8.9 | 17.2 | 9.1 | 10.1 | 9.1 | 10.0 | 5.0 | 15.7 | 10.4 | 6.3 | 6.6 | 7.3 | 6.0 | 5.6 | 13.2 | 8.6 | 7.4 | 9.4 | 14.2 | 9.0 |
| FORGIVE | 94081284 | 8.6 | 9.2 | 12.1 | 12.7 | 8.3 | 6.3 | 8.1 | 6.3 | 6.7 | 5.9 | 6.7 | 7.4 | 9.3 | 5.6 | 9.7 | 9.9 | 8.2 | 12.4 | 12.9 | 11.7 |
| DCQCN, no loss | 9550582 | 10.8 | 15.8 | 11.1 | 15.8 | 16.3 | 15.2 | 12.1 | 14.4 | 12.6 | 14.4 | 14.1 | 11.1 | 13.1 | 19.2 | 12.0 | 13.2 | 12.3 | 14.8 | 14.7 | 14.8 |
| DCQCN, no loss | 23172535 | 11.5 | 13.1 | 13.7 | 15.5 | 13.9 | 20.7 | 14.4 | 12.5 | 12.5 | 13.9 | 12.1 | 14.8 | 12.5 | 12.2 | 17.8 | 15.3 | 10.4 | 19.4 | 13.6 | 14.7 |
| DCQCN, no loss | 94081284 | 10.6 | 14.1 | 15.8 | 14.0 | 11.6 | 13.5 | 14.7 | 15.2 | 11.7 | 18.2 | 14.6 | 14.4 | 10.0 | 12.3 | 13.7 | 11.5 | 11.2 | 13.2 | 21.1 | 16.3 |
| No CC | 9550582 | 6.0 | 8.2 | 9.0 | 11.3 | 6.2 | 10.3 | 11.9 | 9.0 | 9.5 | 8.5 | 8.0 | 6.5 | 8.1 | 9.1 | 9.1 | 10.5 | 8.4 | 12.3 | 9.2 | 8.7 |
| No CC | 23172535 | 6.0 | 8.2 | 9.0 | 11.3 | 6.2 | 10.3 | 11.9 | 9.0 | 9.5 | 8.5 | 8.0 | 6.5 | 8.1 | 9.1 | 9.1 | 10.5 | 8.4 | 12.3 | 9.2 | 8.7 |
| No CC | 94081284 | 6.0 | 8.2 | 9.0 | 11.3 | 6.2 | 10.3 | 11.9 | 9.0 | 9.5 | 8.5 | 8.0 | 6.5 | 8.1 | 9.1 | 9.1 | 10.5 | 8.4 | 12.3 | 9.2 | 8.7 |

Steps 1, 2, 3 and 20 are the loss-sensitive steps; step 18 carries the seven-flow burst.

## 7. Per-step data-parallel loss (% of that step's expected bytes)

| Arm | Seed | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | 9550582 | 0.69 | 0.36 | 0.67 | 0.33 | 0.47 | 0.69 | 0.45 | 0.49 | 0.49 | 0.51 | 0.47 | 0.56 | 0.62 | 0.54 | 0.38 | 0.36 | 0.54 | 0.51 | 0.40 | 0.65 |
| Baseline | 23172535 | 0.54 | 0.51 | 0.49 | 0.51 | 0.62 | 0.42 | 0.49 | 0.71 | 0.58 | 0.42 | 0.45 | 0.42 | 0.47 | 0.51 | 0.54 | 0.58 | 0.33 | 0.47 | 0.49 | 0.40 |
| Baseline | 94081284 | 0.54 | 0.47 | 0.62 | 0.54 | 0.42 | 0.54 | 0.31 | 0.42 | 0.45 | 0.40 | 0.47 | 0.38 | 0.47 | 0.56 | 0.58 | 0.54 | 0.49 | 0.49 | 0.47 | 0.54 |
| DCQCN, 10 % dropping | 9550582 | 10.69 | 10.74 | 9.69 | 10.42 | 9.46 | 10.18 | 9.82 | 10.31 | 10.16 | 9.60 | 10.18 | 9.51 | 10.00 | 10.20 | 10.33 | 9.44 | 10.22 | 10.38 | 9.80 | 9.87 |
| DCQCN, 10 % dropping | 23172535 | 10.83 | 10.27 | 10.92 | 10.20 | 9.84 | 9.58 | 10.18 | 9.64 | 9.58 | 10.00 | 10.56 | 9.87 | 10.29 | 10.33 | 10.65 | 10.31 | 10.11 | 9.93 | 10.25 | 10.11 |
| DCQCN, 10 % dropping | 94081284 | 9.75 | 10.13 | 10.76 | 10.11 | 10.18 | 10.04 | 10.11 | 10.62 | 10.11 | 9.29 | 9.64 | 9.67 | 9.93 | 10.00 | 10.07 | 10.31 | 10.47 | 10.45 | 9.40 | 9.38 |
| DBLP dropping | 9550582 | 0.69 | 0.36 | 0.67 | 10.42 | 9.46 | 10.18 | 9.82 | 10.31 | 10.16 | 9.60 | 10.18 | 9.51 | 10.00 | 10.20 | 10.33 | 9.44 | 10.22 | 10.38 | 9.80 | 0.65 |
| DBLP dropping | 23172535 | 0.54 | 0.51 | 0.49 | 10.20 | 9.84 | 9.58 | 10.18 | 9.64 | 9.58 | 10.00 | 10.56 | 9.87 | 10.29 | 10.33 | 10.65 | 10.31 | 10.11 | 9.93 | 10.25 | 0.40 |
| DBLP dropping | 94081284 | 0.54 | 0.47 | 0.62 | 10.11 | 10.18 | 10.04 | 10.11 | 10.62 | 10.11 | 9.29 | 9.64 | 9.67 | 9.93 | 10.00 | 10.07 | 10.31 | 10.47 | 10.45 | 9.40 | 0.54 |
| FORGIVE | 9550582 | 0.19 | 0.16 | 0.34 | 0.29 | 1.16 | 2.11 | 2.45 | 0.98 | 0.86 | 0.70 | 1.10 | 0.51 | 1.89 | 0.75 | 1.32 | 2.25 | 1.95 | 0.53 | 0.30 | 0.23 |
| FORGIVE | 23172535 | 0.20 | 0.20 | 0.29 | 0.39 | 0.43 | 0.37 | 4.65 | 0.32 | 0.97 | 2.23 | 0.93 | 2.07 | 2.47 | 2.89 | 0.30 | 2.95 | 2.84 | 0.31 | 1.01 | 0.24 |
| FORGIVE | 94081284 | 0.12 | 0.25 | 0.17 | 1.16 | 0.98 | 2.26 | 1.45 | 2.48 | 1.32 | 1.64 | 1.17 | 0.36 | 0.81 | 2.72 | 0.29 | 0.95 | 2.51 | 0.70 | 0.79 | 0.19 |

The two reference arms lose nothing on any step. FORGIVE's loss on the
critical steps is 0.12 to 0.34 %, within the 0.5 % budget, and on the
non-critical steps 0.29 to 4.65 %, within the 10 % budget; the step
figure is a run total over 64 ranks, so the per-cell bound in section 3 is
the tighter statement.

## 8. Where the files are

Release `ueophamgwbrmpp4hm3bzgelfr3a3yhxp` of BulkyCI/astra-sim (run #130,
2026-09-17, main 65e98e7): `ring-3d-regime-64-dcqcn-direct7-1to1-exempt-p01-seed-<seed>.part000.tar.gz`
holds `seed_<seed>/{fixed_p_low_baseline,fixed_p_high_baseline,dblp_policy,recovery_policy}`
(the four arms in the table order Baseline, DCQCN 10 % dropping, DBLP
dropping, FORGIVE); `ring-3d-regime-64-dcqcn-direct7-1to1-zero-seed-<seed>.part000.tar.gz`
is DCQCN without loss. Release `miiav5rlagazhvmyhwpiw4c5dlxyxmx5` (run
#131, the incast wave) holds `ring-3d-regime-64-none-direct7-1to1-zero-seed-<seed>.part000.tar.gz`,
the no-CC reference. In each arm directory: `summary.json` (completion
times, flow-completion percentiles), `telemetry/collective_events.csv`
(per rank, domain, step: start and end), `telemetry/flow_events.csv` (one
row per flow with the byte and counter columns used above),
`telemetry/rank_completion.csv`, `ns3/transport_summary.csv` (fabric
counters), `ns3/fct.txt`, `profile.json`, `clr_mask.csv`.

