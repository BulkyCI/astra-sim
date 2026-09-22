# Audit of `forgive-paper-section.md` against the code and the bundles

Every claim in the draft, in draft order, checked against the repository at
`9da844d` (ns-3 submodule `3e11ace49`) and against the release bundles under
the session scratchpad. Where a derived document (`figure-data.md`,
`results-ledger.md`, a run readout) and a bundle disagree, the bundle decides.
Run #120 and run #117 have no local bundle, so their rows say so.

Denominators used below, stated once because several draft rows change with
them:

- DP bytes offered per run: 191 406 208 000 B (`physical_traffic_bytes.
  dp_all_reduce.logical_bytes`, identical in every arm of the worst cell).
- Total offered payload: 793 641 153 536 B.
- Loss, gross: `forgiveness.forgiven_bytes` over 191.406 GB.
- Loss, net of late arrivals: `forgiveness.actual_loss_bytes` over 191.406 GB,
  which is what section 3.1b defines as "loss".
- Sender-side shedding loss: `shed_logical_bytes` over 191.406 GB.
- Time recovered: `(baseline - arm) / baseline` on `completion_time_ns_max`,
  the baseline being the `fixed_p_low_baseline` of the same seed in run #123.
- Per-step data-parallel span: latest `end_time_ns` minus earliest
  `start_time_ns` over the step's DP rows. Computed from `flow_events.csv`,
  which agrees with `collective_events.csv` to 0.01 ms wherever both exist.

## 1. Claim table

| § | claim | evidence | verdict |
| --- | --- | --- | --- |
| 1 | May prototype ran over UDP with a bitmap probe and a stop message | arXiv 2605.01989, not in the repository | UNVERIFIABLE (preprint not local) |
| 1 | burst excess is 0.04 to 0.62 % of the window in every cell of eight, against a 5 % kill line | `docs/agents/run-120-regime-map.md:17,36-43` | CONFIRMED (readout, bundle not local) |
| 1 | DCQCN divides the trim ratio by 8 to 10 | `run-120-regime-map.md:66` and its W table lines 56-63 | CONFIRMED (readout) |
| 1 | DCQCN lengthens the training window by 18 to 24 % | same table: 1201 to 1421 (+18.3 %), 1200 to 1422 (+18.5 %), 1373 to 1719 (+25.2 %), 1367 to 1696 (+24.1 %) | IMPRECISE: 18 to 25 %; the `direct2` 4:1 column is +25.2 % |
| 1 | millions of rate cuts and thousands of retransmission timeouts | `run-120-regime-map.md:83-86`: 3 298 919 to 13 535 668 CNPs, 1 949 to 10 547 RTOs | CONFIRMED (readout) |
| 1 | at `p = 0.1` the licence recovers 16.1 to 16.7 % of the window | r127 `*-single-*`: 16.66, 16.06, 16.66 % | CONFIRMED |
| 1 | for 7.55 % of the data-parallel bytes | `forgiven_bytes` 14.450, 14.492, 14.470 GB over 191.406 GB: 7.55, 7.57, 7.56 % | CONFIRMED as gross; IMPRECISE against 3.1b, which subtracts late arrivals and gives 7.49 to 7.51 % |
| 1 | ceiling of 20.1 to 20.3 % with no controller | r126 `none-direct7-4to1-zero`: 20.10, 20.11, 20.28 % | CONFIRMED |
| 1 | the no-controller arm re-sends 25.4 % of every byte | r126: 25.35 % in all three runs | CONFIRMED |
| 1 | healthy 1:1 recovers 4.5 to 7.5 % for 1.0 to 1.3 % | r130: 4.48, 5.54, 7.45 %; 1.00, 1.30, 1.12 % | CONFIRMED |
| 2.1 | no line inside the controller changes; FORGIVE decides only whether a signal is handed to it | `rdma-hw.cc:579,624,770-776,815`; `m_cc_exempt` is read nowhere but `DeliverCongestionSignal` and `FollowAllowanceReport` | CONFIRMED |
| 2.1 | only data-parallel all-reduce traffic is forgiven or exempted | `ExperimentConfig.hh:982-986` (`forgivable` requires `ForegroundPayload` and `admission_eligible`), `:1150-1153` (`exemption_eligible` requires `forgivable`) | CONFIRMED |
| 2.1 | the receiver needs the per-peer byte table and nothing else about the workload | `ExperimentConfig.hh:371-379,600-618`; the cell also carries `collectives`, used by the certification | CONFIRMED |
| 2.1 | critical steps are 1, 2, 3 and 20 of 20 | `profiles/regime_64_dcqcn_direct7_4to1_exempt_p01.json` `clr_schedule` | CONFIRMED |
| 2.2 | budget is `p x owed`, `p_low` 0.005, `p_high` 0.1 in the headline | same profile `selection_policy`; `ExperimentConfig.hh:907-914` | CONFIRMED |
| 2.2 | a forgiven byte is charged and never refunded | `ExperimentConfig.hh:256-259` (`cell.forgiven += bytes`, monotone); a late arrival is counted in `late_forgiven_bytes` and dropped, `:554-558` | CONFIRMED |
| 2.2 | the guarantee is certified by the simulator and again by the analyzer at every step's last collective | simulator: `ExperimentConfig.hh:940-979`, at the last collective of the step; analyzer: `analyze.py:434-531`, once over the whole telemetry after the run | IMPRECISE: the analyzer certifies post hoc, not at each step's last collective |
| 2.3 | `forgiven + range <= p x (received + forgiven)` | `affords_soft`, `ExperimentConfig.hh:203-212`: `spent = shed + forgiven + bytes` and `base = delivered + spent` | WRONG as written. The base includes the range being decided: `forgiven + range <= p x (received + forgiven + range)` |
| 2.3 | equivalently `forgiven <= p/(1-p) x received` | the code form rearranges to exactly this with `forgiven` meaning the post-decision total | CONFIRMED |
| 2.3 | "received" is what the receiver has accepted | `register_delivered` is called per accepted arrival, `ExperimentConfig.hh:357-367,988-1007`, so the base is received-bytes space, not completed-message space | CONFIRMED |
| 2.3 | it needs no state beyond two counters the receiver already keeps | the cap reads `delivered` and `forgiven` (and `shed`, always zero in this domain), but both are new per (rank, step) counters, not counters a NIC already holds | IMPRECISE |
| 2.3 | it holds the hard bound by construction under any trim profile | `spent <= p(delivered + spent)` with `delivered + spent <= eligible` gives `spent <= p x eligible` | CONFIRMED |
| 2.3 | the cap reaches `p x owed` exactly when `1 - p` of the step has arrived | at `delivered = (1-p) x owed` the cap is `p/(1-p) x (1-p) x owed = p x owed` | CONFIRMED |
| 2.3 | the up-front arm recovers 9.1 to 10.2 % against vesting's 16.1 to 16.7 % | r127 `owed`: 9.10, 10.18, 9.39 %; `single`: 16.66, 16.06, 16.66 % | CONFIRMED |
| 2.3 | a refused range is repaired by the ordinary path and gets a fresh decision if trimmed again | `rdma-hw.cc:900-908`; `flow.verdicts_asked` increments per verdict, `ExperimentConfig.hh:1072` | CONFIRMED |
| 2.3 | every acknowledgement of a forgiven range carries the congestion mark | `rdma-hw.cc:897-899`: `SendAck(..., nack=false, cnp=true, ...)`; `qbb-header.cc` sets `FLAG_CNP` | CONFIRMED |
| 2.4 | the receiver marks every acknowledgement of an eligible flow, on any step with `p > 0`, with the eligible bit | `exemption_eligible` requires `step_threshold(flow) > 0`, `ExperimentConfig.hh:1150-1153`; `rdma-hw.cc:493`, with eligibility fixed at queue-pair creation, `rdma-hw.cc:368-369` | CONFIRMED |
| 2.4 | `gone <=> forgiven + holes + one packet > p x owed` | `budget_gone`, `ExperimentConfig.hh:237-240`; `kPacketPayload = 4096`, `:38` | CONFIRMED |
| 2.4 | holes are bytes below the highest sequence seen that are neither received nor forgiven | `rdma-queue-pair.cc:429-438`, `rdma-queue-pair.h:200-233` | CONFIRMED |
| 2.4 | holes count each missing byte once and fall as repairs land | `UnsettledBytes` over merged ranges; `NoteForgiven` then `AddOutOfOrderRange` remove a forgiven range from the hole set | CONFIRMED |
| 2.4 | a sender obeys until the first acknowledgement with the eligible bit set and the gone bit clear, then withholds every congestion signal | `rdma-hw.cc:718-757`, `:770-776`; for CC_MODE 1 the only dispatch sites are `:579` (CNP on ACK) and `:815` (trim notification) | CONFIRMED |
| 2.4 | a gone report restores delivery, a clear report withholds again, no latch and no hysteresis | `rdma-hw.cc:741-757` | CONFIRMED |
| 2.4 | a controller that hears nothing raises its own rate on its own timers | the mlx rate timers in `rdma-hw.cc` are untouched by the exemption | CONFIRMED |
| 2.4 | on a critical step the pool is gone after a few hundred kilobytes | `0.005 x 149 536 100 = 747 680` B | IMPRECISE: about three quarters of a megabyte |
| 2.4 | forgiveness under the controller recovers 5.5 to 6.6 % for the same loss | r126 `recovery-p01`: 6.56, 5.50, 6.61 % for 6.81, 6.92, 6.91 % of DP bytes, against the licence's 7.55 to 7.57 % | CONFIRMED on time; IMPRECISE on "the same loss" (6.8 to 6.9 % against 7.55 to 7.57 %) |
| 2.5 | a trim the cap would forgive is forgiven with probability `P` | `trim_verdict` forgives when `affords_soft && !paces_out`; `paces_out` is `coin >= P x scale` with `coin` uniform on `[0, scale)`, `ExperimentConfig.hh:168-176,219-230,248-260` | CONFIRMED |
| 2.5 | a fresh draw on every trimmed arrival | `range_coin(decision_hash, start, verdicts_asked)` with `verdicts_asked` incremented per verdict, `:1072-1074` | CONFIRMED |
| 2.5 | coin refusals charge nothing and set no bit | charge: CONFIRMED, `trim_verdict` returns the cell unchanged. Bit: the gone bit is a property of the cell's `holes`, and a coin refusal leaves the range a hole, so it can turn the report red exactly as a cap refusal does | IMPRECISE |
| 2.5 | at `P = 0.25`, 15.8 to 16.9 % against 16.1 to 16.7 %, for 5.5 % instead of 7.55 % | r127 `b25`: 15.97, 15.84, 16.91 % for 5.64, 5.51, 5.55 % | CONFIRMED |
| 2.5 | healthy fabric, 5.8 to 6.7 % for 0.27 to 0.42 % against 4.5 to 7.5 % for 1.0 to 1.3 % | r130 coin25: 5.82, 6.65, 6.44 % for 0.315, 0.418, 0.271 % | CONFIRMED |
| 2.5 | the coin recovers 5 of the 6 to 7 points that vesting recovers | coin over up-front: 5.54, 5.10, 5.50 points. Vesting over up-front: 7.56, 5.88, 7.27 points | IMPRECISE: vesting recovers 5.9 to 7.6 points |
| 2.6 | nothing new travels on the data path; two flag bits on the existing acknowledgement and repair request | `qbb-header.h:32,38`; set in `SendAck` (`rdma-hw.cc:489,493`) and `SendTrimNack` (`:678,682`) inside the existing `flags` byte | CONFIRMED |
| 2.6 | the sender needs nothing and computes nothing about the budget | `FollowAllowanceReport` reads the two bits and keeps telemetry counters only | CONFIRMED |
| 2.7 | re-synchronisation costs about 17.5 GB per rank under TP 8 | `70e9 x 2 / 8 = 17.5` GB | CONFIRMED |
| 2.7 | four of our steps, 0.4 % of time at `K = 1000` | 17.5 GB at 400 Gbps is 350 ms; a step is `1697/20 = 84.9` ms, so 4.1 steps; `4/1000 = 0.4 %` | CONFIRMED |
| 2.7 | the May prototype converged at 40 % loss on GPT-2 with zero-fill | preprint, not in the repository | UNVERIFIABLE |
| 3.1 | ASTRA-sim 2.0 with a forked ns-3 RDMA back end | repository layout, `extern/network_backend/ns-3` | CONFIRMED |
| 3.1 | 70 B parameters, 2-byte, 80 layers, hidden 8192, sequence 4096, TP 8, PP 1, DP 8, 64 ranks, 20 steps | profile `model` and `parallelism` blocks | CONFIRMED |
| 3.1 | 5.4 ms of compute per node | `compute_duration_us: 5376` | CONFIRMED |
| 3.1 | one 68 359 375-byte bucket, the 256-bucket gradient sharded eight ways | `70e9 x 2 / 256 / 8 = 68 359 375`; `dp_all_reduce_bytes` matches | CONFIRMED |
| 3.1 | two 64 MiB tensor-parallel all-reduces per layer | `tp_all_reduce_bytes: 67108864`, `tensor_parallel_all_reduces_per_layer: 2` | CONFIRMED |
| 3.1 | `direct7` sends each peer five streams of 17 089 843 bytes | `system.json` `preferred-dataset-splits: 4` gives a chunk of 17 089 843 B; `Sys.cc:957-962` records that the loop leaves the last stream a full chunk rather than the remainder, so five streams run | CONFIRMED, with the omission noted in section 4 below |
| 3.1 | a rank receives 70 DP flows of 2 136 230 bytes (522 packets) per step | `dp_all_reduce.flow_count` 89 600 over `64 x 20` is 70; `191 406 208 000 / 89 600 = 2 136 230`; `2 136 230 / 4096 = 521.5`, so 522 | CONFIRMED |
| 3.1 | owed 149 536 100 bytes per cell | `ledger_law.worst_cell.eligible_bytes` = 149 536 100 in every #127 arm; `70 x 2 136 230` | CONFIRMED |
| 3.1 | the run offers 191.4 GB of DP and 793.6 GB of total payload | `physical_traffic_bytes` | CONFIRMED |
| 3.1 | two-tier Clos, 8 hosts per leaf at 400 Gbps, 4 spines by design, 32 MB buffers, PFC off | profile `network`; `network_config.txt:77-81` (`BUFFER_SIZE 32`, `ENABLE_PFC 0`) | CONFIRMED |
| 3.1 | a TP group is the 8 hosts of one leaf; DP peers are the same-position hosts on the other seven leaves | `topology.py:851` attaches host `h` to leaf `h // hosts_per_leaf`; with TP the fastest-varying rank dimension the TP group is one leaf | CONFIRMED |
| 3.1 | the worst cell fails two of the four spines (4:1); the healthy cell has eight (1:1) | `regime_64_dcqcn_direct7_4to1_exempt_p01.json` `spine_count 4`, `failed_spine_count 2`; `..._1to1_...` `spine_count 8`, `failed_spine_count 0`; manifest `live_spine_count: 2` | CONFIRMED |
| 3.1 | seven 400 Gbps senders converge on one 400 Gbps host link at every spine ratio | `direct7` with 8 DP peers and one NIC per rank | CONFIRMED |
| 3.1 | trim ratio without a controller 2.4 / 6.3 / 12.9 / 24.1 % | `run-120-regime-map.md:56-59`: 0.0235, 0.0625, 0.1289, 0.2406 | CONFIRMED (readout) |
| 3.1 | identical over steps 1 to 17 and over the whole run | same table, `W steps 1-17` column | CONFIRMED (readout) |
| 3.1 | fan-in 2 to 7 multiplies it by about 2.7 and oversubscription by about 5.5 | the readout's own W values give 2.63 (at 2:1) and 1.87 (at 4:1) for fan-in, 5.38 (`direct2`) and 3.83 (`direct7`) for oversubscription; the product of the two stated factors is 33.9 % against the measured 24.1 % | IMPRECISE: the two factors hold on one arm of each axis only, and the model is not multiplicative |
| 3.1 | seven background flows of 128 MiB at rank 8 at step 18, no offset | profile `microburst_*` fields | CONFIRMED |
| 3.1 | the burst exceeds the steady median by 0.04 to 0.62 % of the window in every cell | `run-120-regime-map.md:36-43` | CONFIRMED (readout) |
| 3.1 | the burst drains in 30 to 37 ms without a controller and 63 to 146 ms under DCQCN | `run-120-regime-map.md:83-86`: 30.4 to 37.0 ms, 63.4 to 146.4 ms | CONFIRMED (readout) |
| 3.1 | under go-back-N the same burst cost 205 to 935 ms of DP span in run #117 | `run-120-regime-map.md:31` | CONFIRMED (readout) |
| 3.1 | the forgiven bytes spread 5 to 7 % per permissive step with step 18 not dominant | r127 `single` seed 9550582 `forgiven_bytes_by_training_step`: permissive steps carry 6.04 to 6.36 % of the forgiven total, step 18 carries 6.09 % | CONFIRMED |
| 3.1 | one queue pair per message, 4096-byte payload packets | `flow_count` 376 327 against 376 320 foreground messages plus 7 burst flows; `PACKET_PAYLOAD_SIZE 4096` | CONFIRMED |
| 3.1 | trimmed class capped at 25 % of the link, trimmed queue 1 MiB against a 4 MiB data queue | `network_config.txt:52` `PACKET_TRIM_QUEUE_WEIGHT 25`, `:80-81` 4 194 304 and 1 048 576 | CONFIRMED |
| 3.1 | a NACK per trimmed packet, retransmission of that packet only, 1 ms RTO, no exponential backoff | `rdma-hw.cc:809-820` (exact range repair), `:1121-1129` (`ArmRetransmissionTimeout` schedules a fixed `m_retransmission_timeout_ns`); `RETRANSMISSION_TIMEOUT_NS 1000000` | CONFIRMED |
| 3.1 | ECN at 400 Gbps between 800 KB and 3.2 MB with marking probability 0.2, EWMA gain 1/256, rate-decrease interval 4, alpha-resume 1 | `generate.py:1448-1463`: `KMIN_MAP ... 400000000000 800`, `KMAX_MAP ... 400000000000 3200`, `PMAX 0.2`, `EWMA_GAIN 0.00390625`, `RATE_DECREASE_INTERVAL 4`, `ALPHA_RESUME_INTERVAL 1` | CONFIRMED |
| 3.1 | `RATE_AI`, `RATE_HAI`, `MIN_RATE` are 100 Gbps-era literals not rescaled to 400 Gbps | `topology.py:31-36` makes them fractions of the link rate (1/2000, 1/1000, 1/1000) and `:113-121` resolves them against it; `network_config.txt:23-25` carries `RATE_AI 200000000bps`, `RATE_HAI 400000000bps`, `MIN_RATE 400000000bps` | WRONG. They are derived from the 100 Gbps-era literals but are rescaled with the link rate; at 400 Gbps they are 200, 400 and 400 Mb/s |
| 3.1 | no tuning sweep; no other controller implemented | `topology.py:91-108`: the only modes are `none` (CC_MODE 12) and `dcqcn` (CC_MODE 1) | CONFIRMED |
| 3.1 | per-flow ECMP across spines, no per-packet spraying | `switch-node.cc:110-138`: one next hop per five-tuple hash, computed once per packet from invariant fields | CONFIRMED |
| 3.1 | three seeds on every FORGIVE arm; the zero-tolerance reference has five; run #117 has sixteen | r127 and r130 carry 9550582, 23172535, 94081284; r126 `dcqcn-direct7-4to1-zero` carries five seeds; `run-117-readout.md:48` | CONFIRMED |
| 3.1 | a seed sets the ECMP hashing and the shedding selection stream | `switch-node.cc:90` sets `m_ecmpSeed = m_id` and `:137` hashes only sip, dip, sport, dport; `entry.h:107-128` allocates source ports deterministically. The seed reaches `switch-mmu.cc:111` (the ECN marking draw) and `ExperimentConfig.hh:844` (the shedding and coin decision hash). The three r126 no-controller runs are bit-identical across seeds (1 355 708 699 ns, 48 462 610 trims, 201 185 054 144 re-sent bytes in all three) | WRONG on ECMP: the seed does not move path selection; it moves the ECN marking draw and the selection hash |
| 3.1 | arms in one comparison share the seed, so their windows can be subtracted | `comparison.json` `per_seed` runs all four arms at one `ns3_rng_run` | CONFIRMED |
| 3.1b | makespan is the last rank's completion time, differenced against the fixed-low control on the same seed | `summary.completion_time_ns_max`; `r127/read.py` | CONFIRMED |
| 3.1b | loss is forgiven bytes less those that arrived late and were dropped | `forgiveness.actual_loss_bytes` is exactly that quantity, but the draft's tables quote `forgiven_bytes` | see the loss rows below |
| 3.1b | W is trimmed payload over offered; re-sent is retransmitted over 793.6 GB | `network_health.W`, `transport_recovery.retransmitted_bytes / total_physical_bytes` | CONFIRMED |
| 3.1b | worst all-reduce of #117: 1026 to 873 ms, 153 ms saved, CI 5 to 302 ms over 16 seeds | `run-117-readout.md:50`: 1026.0, 872.7, 153.4 ms, CI [5.0, 301.7] ms | CONFIRMED (readout) |
| 3.1b | per-rank p99 reads -4.9 % with CI -19.6 to +9.8 % | `figure-data.md:156` carries exactly these; `run-117-readout.md:51` instead carries 4.5 ms with CI [-90.1, 81.0] ms | UNVERIFIABLE: the two derived documents disagree and the #117 bundle is not local |
| 3.1b | per-rank p99 is not quoted anywhere | the draft does not quote it as a result; `comparison.json` still emits `dp_all_reduce_collective_per_rank_p99_ns` | CONFIRMED |
| 3.1b | certification is a per (rank, step) delivered share with the worst cell named | `analyze.py:420-431,503-522` | CONFIRMED |
| 3.1c | the control sheds 0.5 % of DP bytes at the sender | budget-0.4 bundles: 0.51, 0.50, 0.48 % | CONFIRMED |
| 3.1c | zero tolerance is within -1.1 to +0.8 % of the control over 5 seeds | r126 against the matching r123 baselines: -1.06, +0.09, -0.63, -0.50, +0.76 % | CONFIRMED |
| 3.1c | control window 1697 to 1701 ms | 1696.69, 1696.90, 1700.56 ms | CONFIRMED |
| 3.1c | control all-reduce 36 to 37 ms on both step classes | non-critical medians 36.49, 36.74, 35.86 ms; critical medians 36.13, 37.15, 36.97 ms | CONFIRMED |
| 3.1c | control loss 0.5 %, re-sent 3.5 to 3.7 % | 0.48 to 0.51 %; 3.53, 3.67, 3.62 % | CONFIRMED |
| 3.1c | loose baseline window 1444 to 1477 ms | 1444.0, 1452.2, 1476.9 ms | CONFIRMED |
| 3.1c | loose baseline all-reduce 23 to 25 and 22 to 26 ms | the local bundle carries no telemetry for `fixed_p_high_baseline` | UNVERIFIABLE (telemetry not in the local bundle) |
| 3.1c | loose baseline loss 40 % | 40.07, 40.18, 39.96 % | CONFIRMED |
| 3.1c | loose baseline re-sent 1.5 to 1.6 % | 1.46, 1.54, 1.65 % | IMPRECISE: 1.5 to 1.7 % |
| 3.1c | dynamic tolerance window 1491 to 1519 ms | 1500.4, 1519.4, 1491.2 ms | CONFIRMED |
| 3.1c | dynamic tolerance all-reduce 25 to 26 and 35 to 37 ms | no telemetry for `dblp_policy` in the local bundle | UNVERIFIABLE |
| 3.1c | dynamic tolerance loss 32 %, re-sent 2.1 % | 32.08, 32.31, 32.12 %; 2.11, 2.12, 2.08 % | CONFIRMED |
| 3.1c | FORGIVE 0.4 window 1340 to 1360 ms | 1340.4, 1357.5, 1359.9 ms | CONFIRMED |
| 3.1c | FORGIVE 0.4 all-reduce 12 to 13 ms on non-critical steps | medians 11.80, 12.30, 12.55 ms | IMPRECISE: 11.8 to 12.6 ms |
| 3.1c | FORGIVE 0.4 all-reduce 34 to 36 ms on critical steps | medians 33.70, 35.71, 35.00 ms | IMPRECISE: 33.7 to 35.7 ms |
| 3.1c | FORGIVE 0.4 loss 21.3 to 21.5 % | 21.36, 21.24, 21.28 % on the 191.406 GB denominator of 3.1b; 21.47, 21.35, 21.38 % on the control's post-shed 190.43 GB | IMPRECISE: the row uses a different denominator from 3.2 and 3.4 |
| 3.1c | FORGIVE 0.4 re-sent 2.7 to 3.0 % | 2.75, 2.98, 2.80 % | CONFIRMED |
| 3.1c | FORGIVE's critical steps stay within 2.4 ms of the control's | differences 2.43, 1.44, 1.97 ms | IMPRECISE: within 2.5 ms |
| 3.1c | the loose baseline's critical steps speed up by a third | depends on the unverifiable loose-baseline spans above | UNVERIFIABLE |
| 3.1c | the same cell without a controller runs in 1367 ms (one seed), so the controller's bill is about 330 ms | `run-120-regime-map.md:39`; `1696.7 - 1367 = 330` ms. Run #126 puts the same cell at 1355.7 ms under later code, which would make the bill 341 ms | CONFIRMED (readout) |
| 3.1c | FORGIVE at 0.4 returns nearly all of it | `1696.7 - 1340.4 = 356` ms, more than the map's 330 ms | CONFIRMED |
| 3.2 | controls of 1696.7, 1696.9 and 1700.6 ms | r123 `base_ms` | CONFIRMED |
| 3.2 | seed 9550582: 16.66 %, 7.55 %, 5.88 %, TP -4.3 % | r127 `single`; TP 783.0 ms against the control's 818.0 ms, -4.28 % | CONFIRMED |
| 3.2 | seed 23172535: 16.06 %, 7.57 %, 5.61 %, TP +4.4 % | TP 814.5 against 780.4 ms, +4.37 % | CONFIRMED |
| 3.2 | seed 94081284: 16.66 %, 7.56 %, 5.22 %, TP -1.3 % | TP 795.3 against 805.4 ms, -1.25 % | CONFIRMED |
| 3.2 | the TP collectives are never slower than in the control beyond the seed spread | the control's own TP spans range 780.4 to 818.0 ms, a 4.8 % band, and the one positive arm reads +4.4 % | CONFIRMED as stated, but the margin is the whole seed band |
| 3.2 | the critical steps forgive 1.4 % of the forgiven bytes at this budget | r127 `single`: 1.26, 1.26, 1.25 %. The 1.39 to 1.44 % figure belongs to the v1 arm of run #123 at the same budget | WRONG for the headline arm: 1.25 to 1.26 % |
| 3.3 | zero tolerance: -1.1 to +0.8 %, pays nothing | as above | CONFIRMED |
| 3.3 | forgive but obey: 5.5 to 6.6 % for 6.8 to 7.0 % of DP bytes, 1.7 to 1.9 % re-sent | r126 `recovery-p01`: 6.56, 5.50, 6.61 %; 6.81, 6.92, 6.91 %; 1.84, 1.89, 1.74 % | CONFIRMED |
| 3.3 | no controller: 20.1 to 20.3 %, 25.4 % re-sent, 93 timeouts against the control's 10 042 to 10 622 | r126: 20.10, 20.11, 20.28 %; 25.35 %; 93; control 10 110, 10 042, 10 622 (and 10 029, 10 039 on the other two seeds) | CONFIRMED |
| 3.3 | never re-engage: 18.7 to 19.0 % for 7.6 % of DP bytes, 6.5 to 6.8 % re-sent | r127 `noreengage`: 18.68, 18.95, 18.98 %; 7.65, 7.56, 7.58 %; 6.52, 6.75, 6.57 % | CONFIRMED |
| 3.3 | the controller's whole bill is about 20 % and the licence recovers 16 of it | 20.1 to 20.3 % against 16.1 to 16.7 % | CONFIRMED |
| 3.3 | it re-sends a quarter of what the no-controller arm does | 5.22 to 5.88 % against 25.35 %, a ratio of 0.21 to 0.23 | CONFIRMED |
| 3.3 | forgiveness alone is worth 6 points and the licence roughly triples it | 5.50 to 6.61 becomes 16.06 to 16.66, a ratio of 2.4 to 3.0 | IMPRECISE: the multiple is 2.4 to 3.0 |
| 3.3 | the last 3 points to the never-return arm | 18.68 to 18.98 against 16.06 to 16.66, paired per seed: 2.02, 2.89, 2.32 points | IMPRECISE: 2.0 to 2.9 points |
| 3.4 | vesting, no coin: 16.1 to 16.7 %, 7.55 to 7.57 %, 5.2 to 5.9 % | r127 `single` | CONFIRMED |
| 3.4 | vesting with the coin at 0.25: 15.8 to 16.9 %, 5.5 to 5.6 %, 6.5 to 6.6 % | r127 `b25`: 15.97, 15.84, 16.91; 5.64, 5.51, 5.55; 6.57, 6.48, 6.55 | CONFIRMED |
| 3.4 | up-front, no coin: 9.1 to 10.2 %, 7.9 to 8.1 %, 1.9 to 2.1 % | r127 `owed`: 9.10, 10.18, 9.39; 8.05, 7.94, 8.00; 2.05, 1.93, 2.09 | CONFIRMED |
| 3.4 | up-front with the coin: 14.6 to 15.3 %, 6.2 to 6.4 %, 6.0 to 6.3 % | r127 `owed-b25`: 14.64, 15.28, 14.89; 6.43, 6.19, 6.24; 6.33, 6.03, 6.11 | CONFIRMED |
| 3.4 | vesting with a per-sender stop: 15.8 to 16.6 %, 8.10 %, 5.5 to 5.8 % | r127 `stepstop`: 16.55, 16.11, 15.84; gross 8.10 % in all three; 5.46, 5.76, 5.72 | CONFIRMED on time and re-sent. The 8.10 % is the gross charge; 0.78 to 0.83 points of it arrived late, so the net loss is 7.25 to 7.28 % |
| 3.4 | the up-front budget is spent early, the report stays red and the sender obeys for the rest of the step | r127 counters: exempt flows 41 903 to 43 554 against 86 059 to 86 172; allowance-gone reports 26.7 to 27.4 M against 6.7 to 6.8 M; signals withheld 8.9 to 9.3 M against 18.9 to 19.9 M; CNPs taken 7.7 to 8.2 M against 4.4 to 4.6 M | CONFIRMED |
| 3.4 | a low re-send figure is the signature of a sender under rate cuts | `owed` re-sends 1.93 to 2.09 % against the control's 3.53 to 3.67 % and vesting's 5.22 to 5.88 % | CONFIRMED |
| 3.4 | the stop spends every cell to its cap and recovers nothing | gross 8.10 % equals the 8.1 % cap; paired time against `single`: -0.11, +0.05, -0.82 points | CONFIRMED |
| 3.4 | the cap forgives 18 % of the trimmed bytes in the first fifth and 60 % in the last fifth | `frontbias.py` on r127 `single` seed 9550582: 0.180 and 0.603. The ratio is forgiven over (forgiven plus soft-refused) bytes, which is the share of the bytes the cap was asked about, not of the trimmed bytes (12 345 MB were trimmed in the first bucket against 13 440 MB asked, because a re-trimmed range is asked again) | IMPRECISE in wording, correct in value |
| 3.4 | the first fifth is also where the most trimming happens | bucket totals 12 345, 8 556, 8 141, 7 072, 1 840 MB | CONFIRMED |
| 3.4 | under the coin the shares are 65 % to 100 % | `b25` seed 9550582: 0.646, 0.881, 0.980, 0.992, 1.000 | CONFIRMED |
| 3.5 | the coin at 0.25 reads the same time for two points less loss | 7.55 to 7.57 % against 5.51 to 5.64 %, a gap of 1.9 to 2.1 points, at 15.8 to 16.9 % against 16.1 to 16.7 % | CONFIRMED |
| 3.5 | `P = 0.1` read 15.3 to 16.7 % for 2.6 to 2.9 % | r125 `p01-b10`: 15.30, 16.70, 15.96 %; 2.61, 2.92, 2.64 % | CONFIRMED |
| 3.5 | `P = 0.05` read 15.0 to 16.6 % for 1.2 to 1.3 % | r125 `p01-b05`: 14.95, 16.09, 16.61 %; 1.22, 1.32, 1.28 % | CONFIRMED |
| 3.5 | the arm at `P = 0` forgives nothing and keeps the licence | `parse_pacing`, `ExperimentConfig.hh:1260-1264`, refuses a Bernoulli `p` that is not strictly between 0 and 1, so this arm cannot be configured as written | WRONG as an arm: it needs a new rule, not `pacing.p = 0` |
| 3.6 | sender-side shedding discards a hashed share of eligible bytes before the fabric | `ExperimentConfig.hh:844-850,889` | CONFIRMED |
| 3.6 | budget 0.05: 8.0 to 8.6 % / 3.7 to 3.8 % / 0.1 to 1.3 % / 4.1 % | r125 `p005`: 8.58, 8.34, 7.95 %; 3.76, 3.74, 3.77 %; 0.13, 0.08, 1.32 %; 4.09, 4.09, 4.06 % | CONFIRMED |
| 3.6 | budget 0.1: 12.9 to 14.1 % / 6.75 to 6.89 % / 2.4 to 3.3 % / 7.7 % | r123: time 12.90, 14.10, 13.23 %; FORGIVE loss 6.71, 6.85, 6.81 % on the 191.406 GB denominator; shedding time 3.12, 2.45, 3.28 %; shedding loss 8.12, 8.16, 8.13 % | FORGIVE loss IMPRECISE (denominator); shedding loss WRONG: 8.1 %, which is the cap |
| 3.6 | budget 0.2: shedding loss 15.7 % | 16.10, 16.20, 16.18 % against a 16.1 % cap | WRONG: 16.1 % |
| 3.6 | budget 0.4: shedding time 11.0 to 11.8 % | 11.57, 10.46, 10.97, 11.78, 12.31 % over the same five seeds the FORGIVE column uses; `run-123-readout.md:59` already reads 10.5 to 12.3 % | WRONG: 10.5 to 12.3 % |
| 3.6 | budget 0.4: shedding loss 31.5 % | 32.08, 32.31, 31.74, 32.00, 32.12 % against a 32.1 % cap | WRONG: 31.7 to 32.3 % |
| 3.6 | budget 0.6: shedding loss 47.9 % | 48.04, 48.24, 48.02 % against a 48.1 % cap | IMPRECISE: 48.0 to 48.2 % |
| 3.6 | 0.4 mask off: shedding loss 39.8 % | 40.07, 40.18, 39.96 % against a 40.0 % cap | IMPRECISE: 40.0 to 40.2 % |
| 3.6 | FORGIVE time and loss at 0.2, 0.4, 0.6 and 0.4 mask off | 15.95 to 16.73 % for 11.07 to 12.19 %; 19.55 to 21.00 % for 21.20 to 21.66 %; 23.72 to 24.26 % for 37.47 to 38.40 %; 25.27 to 25.56 % for 25.47 to 25.90 % | CONFIRMED |
| 3.6 | efficiency falls from 2.1 to 2.3 at 0.05, 1.9 to 2.1 at 0.1, to 0.6 at 0.6 | 2.11 to 2.28; 1.92 to 2.06; 0.62 to 0.64 | CONFIRMED |
| 3.6 | shedding efficiency stays at 0.3 to 0.4 | at 0.1 it is 0.30 to 0.40, at 0.4 it is 0.33 to 0.38, at 0.6 it is 0.33 to 0.34, but at 0.05 it is 0.02 to 0.33 | IMPRECISE: at the smallest budget shedding reads 0.02 to 0.33 |
| 3.6 | shedding discards exactly its cap | shed share lands within 0.4 points of the mask-weighted cap at every budget | CONFIRMED |
| 3.6 | FORGIVE spends 67 to 84 % of the same cap | utilisation 83 to 85 % at 0.1, 68 to 75 % at 0.2, 66 to 68 % at 0.4, 78 to 80 % at 0.6, 64 to 65 % mask off | CONFIRMED over the mask-on points; the mask-off point is 64 % |
| 3.6 | peak queue occupancy is identical in the two arms | `comparison.json` `max_queue_bytes` reads 4 194 316, 4 194 224, 4 194 316 and 4 194 268 for the four arms, all within 92 B of the 4 MiB `DATA_QUEUE_BYTES` limit | IMPRECISE: every arm is pinned at the queue's configured ceiling, so the equality is the cap and not a measured occupancy |
| 3.6 | the mask costs 5.1 points of time and 4.4 points of loss at 0.4 | mask on at the three shared seeds 21.00, 20.00, 20.03 against mask off 25.43, 25.27, 25.56; loss 21.36, 21.24, 21.28 against 25.75, 25.90, 25.47; means differ by 5.08 and 4.42 points | CONFIRMED |
| 3.6 | the ledger shows 1.0 to 1.5 % of forgiven bytes on the protected steps against 19 to 21 % without it | at budget 0.4 the protected-step share is 0.45, 0.45, 0.45, 0.45, 0.44 %; mask off is 20.28, 19.16, 20.45 %. The 1.39 to 1.44 % figure is the budget-0.1 arm | WRONG for budget 0.4: 0.44 to 0.45 % |
| 3.6 | under vesting the point at 0.1 moves from 12.9 to 14.1 % to 16.1 to 16.7 % | r123 against r127 | CONFIRMED |
| 3.7 | worst cell row: 1697 to 1701 ms, 3.5 to 3.7 % re-sent, 16.1 to 16.7 %, 7.55 %, vesting | as above. The column is headed "control trim ratio" but the entry is a re-sent share; the control's W is 0.0300 to 0.0312 | IMPRECISE: the column head does not match the entry |
| 3.7 | `direct2` 2:1 row: about 1410 to 1420 ms, 10.5 to 12.5 %, 2.37 to 2.50 %, under the heading "FORGIVE, budget 0.1" | r123 `direct2-2to1-exempt`: baselines 1428.60, 1417.73, 1408.88 ms; time 12.53, 11.73, 10.45 %; loss 2.50, 2.37, 2.37 %. `profiles/regime_64_dcqcn_direct2_2to1_exempt.json` sets `p_high: 0.4` | WRONG twice: the control windows are 1409 to 1429 ms, and the arm ran at budget 0.4, not 0.1 |
| 3.7 | healthy row: 1248 to 1260 ms, 0.02 to 0.04 % trimmed, 4.5 to 7.5 %, 1.0 to 1.3 % | r130 baselines 1247.71, 1253.12, 1260.23 ms; control W 0.000362, 0.000305, 0.000232 | CONFIRMED |
| 3.7 | healthy coin row: 5.8 to 6.7 % for 0.27 to 0.42 % | r130 coin25 | CONFIRMED |
| 3.7 | 16 ranks, go-back-N: 7145 ms, 3.9 % for a 10 % cap over 16 seeds | `run-117-readout.md:49` | CONFIRMED (readout) |
| 3.7 | the regime map table | `run-120-regime-map.md:36-43,56-63` | CONFIRMED (readout); the three empty DCQCN cells are 0.0077, 0.0187, 0.0317 and 21 %, 29 %, 48 % in the readout |
| 3.7 | the burst steps never exceed a steady step by 1 % of the window anywhere | maximum 0.62 % | CONFIRMED (readout) |
| 3.7 | #117 window 7145 to 6854 ms, 3.91 %, CI 1.13 to 6.68 % | `run-117-readout.md:49` | CONFIRMED (readout) |
| 3.7 | worst all-reduce 1026 to 873 ms, CI 5 to 302 ms | `run-117-readout.md:50` | CONFIRMED (readout) |
| 3.7 | the relief correlated 0.93 with trims avoided at 11.9 ms per million and -0.01 with bytes discarded | `figure-data.md:208` carries 0.93 and 11.9 ms; `run-117-readout.md:71-74` carries 0.94 and 13 ms per million. Neither document carries a -0.01 correlation for discarded bytes | UNVERIFIABLE: the two derived documents disagree and the -0.01 figure has no source in either |
| 3.7 | the loose baseline recovered 9.42 % (CI 7.03 to 11.82 %) for 40 % loss | 9.42 % is `run-117-readout.md:52`; the percentage CI comes from `figure-data.md:151`, while the readout gives [500, 863] ms | CONFIRMED on the point estimate; the CI is derived, bundle not local |
| 3.7 | the same policy recovers 0.78 % under selective repeat | `run-117-readout.md:26,113` | CONFIRMED (readout) |
| 3.7 | with four spines per leaf the fabric is not oversubscribed | `profiles/regime_64_dcqcn_direct7_1to1_exempt_p01.json` sets `spine_count: 8`, `failed_spine_count: 0`; eight hosts at 400 Gbps against eight uplinks at 400 Gbps is what makes it 1:1 | WRONG: eight spines |
| 3.7 | the kill test did not fire | control trim 0.023 to 0.036 % is below 0.5 % and FORGIVE recovers 4.5 to 7.5 %, above 2 points | CONFIRMED |
| 3.7 | the exempt senders trim ten times more than the control (0.27 to 0.34 % of bytes) and still complete sooner | FORGIVE W 0.002677, 0.003388, 0.002904 against control 0.000362, 0.000305, 0.000232, ratios 7.4, 11.1, 12.5 | CONFIRMED on the band; the multiple is 7 to 13 |
| 3.7 | sender-side shedding recovers 0.1 to 0.3 % and the loose baseline -0.4 to +0.7 % on the healthy cell | r130 `dblp_policy` 0.29, 0.13, 0.24 %; `fixed_p_high_baseline` -0.36, +0.29, +0.70 % | CONFIRMED |
| 3.7 | on the go-back-N fabric sender-side shedding alone recovers 3.9 % over 16 seeds; FORGIVE has not been run there | `run-117-readout.md:49`; no go-back-N FORGIVE arm exists in any bundle | CONFIRMED |
| 4 | the six-row origin table and the one-line composition | attribution claims about outside literature | UNVERIFIABLE (no retrieval in this audit) |
| 4 | MLT's tolerated fractions are 0.7 to 3.3 % across sixteen models, 10 % at a quality target | `docs/agents/forgive-related-work.md` and the memory note carry the same figures; the paper is not in the repository | UNVERIFIABLE |
| 4 | the controller's reaction is 18 to 24 % of the window under DCQCN and about 6 % on a fabric that is not oversubscribed | the 1:1 cell has no no-controller arm in any local bundle, so the healthy fabric's controller bill is not measured; 4.5 to 7.5 % is what the licence recovers there, which is a lower bound on the bill | IMPRECISE: "about 6 %" is the licence's recovery, not a measured controller bill |
| 4 | the online-allocation citations and the mapping in the budget-shape review | `docs/agents/lit-review-budget-shape.md` exists | UNVERIFIABLE (not re-read here) |
| 5 | the simulator has no gradient | `ExperimentConfig.hh` and the ns-3 back end move byte counts only | CONFIRMED |
| 5 | under vesting the marginal time of a forgiven byte measured zero between 7.55 % and 5.5 % loss | 16.1 to 16.7 % against 15.8 to 16.9 % | CONFIRMED |
| 5 | DCQCN's bill is quoted as measured with the repository's parameters and no sweep exists | `topology.py:91-121`; no sweep profile in `experiments/ring_3d/profiles/` | CONFIRMED |
| 5 | three seeds, one workload, per-flow ECMP, no spraying, no NSCC, no second workload | profile set and `switch-node.cc:110-138` | CONFIRMED |
| 6 | eight named figures are drawn in `docs/agents/figures/` | all eight files exist; the directory also holds `run-117-p-high-grid.svg`, which the list omits | CONFIRMED |
| 6 | the per-seed rows are in `figure-data.md` sections 8, 10, 11, 12, 13, 15 | all exist, but `figure-data.md` numbers two sections 13 (line 762 "Mechanism diagram" and line 810 "Run #127"), so "section 13 there" is ambiguous | IMPRECISE |
| 7 | #120 is run 34055188995, 8 cells, one seed | `run-120-regime-map.md:1-10` | CONFIRMED (readout) |
| 7 | #123 is 21 records, 84 arms, all certified | 21 record directories each with four arm directories | CONFIRMED |
| 7 | #125 is 24 arms, all certified, earlier rule set | 12 standalone plus 3 records of four arms | CONFIRMED |
| 7 | #126 is 15 arms, all certified | 15 record directories | CONFIRMED |
| 7 | #127 is 21 arms, all certified, worst cell 0.900 to 0.909 | 21 bundles, every `ledger_law.status` is `verified`, `min_delivered_share` spans 0.90000 to 0.90938 | CONFIRMED |
| 7 | #130 is 18 arms, FORGIVE and coin arms certified locally, worst cell 0.916 to 0.948 and 0.983 to 0.984 | 3 records of four arms plus 6 standalone; FORGIVE 0.9454, 0.9156, 0.9477; coin 0.9840, 0.9826, 0.9827 | CONFIRMED |
| 7 | the commits named for each run (`main c6855f0`, `59cf16c`, `65e98e7`, and the ns-3 hashes) | `attestation.json` and `manifest.json` in the local bundles carry no commit fields | UNVERIFIABLE |
| 7 | every FORGIVE arm was re-analysed with the committed analyzer and the analyzer fails a broken ledger | `analyze.py:533-560` (`_require_lawful_ledger`); every local bundle carries `summary_certified.json` | CONFIRMED |

Counts over the 186 claim rows above, taking the strongest verdict where a
row carries two: CONFIRMED 138, WRONG 12, IMPRECISE 24, UNVERIFIABLE 11. One
row, the loss definition of section 3.1b, carries no verdict of its own
because the rows that use it carry theirs.

## 2. Claims the code contradicts or does not support as written

1. **The vesting cap is not in the space the draft states.** `affords_soft`
   (`ExperimentConfig.hh:203-212`) measures `shed + forgiven + range` against
   `p x (delivered + shed + forgiven + range)`. The range under decision is on
   both sides. The draft's first form, `forgiven + range <= p x (received +
   forgiven)`, is a different inequality; only the draft's second form,
   `forgiven <= p/(1-p) x received`, matches the code. The base is
   received-bytes space, as the draft says, because `register_delivered` is
   called per accepted arrival rather than per completed message.

2. **`RATE_AI`, `RATE_HAI` and `MIN_RATE` are rescaled.** `topology.py:31-36`
   converts the 100 Gbps-era literals to fractions of the link rate and
   `:113-121` resolves them against it, so the worst cell runs 200, 400 and
   400 Mb/s and not 50, 100 and 100 Mb/s. The draft's caveat is the opposite
   of what the generator does. The defensible caveat is that the fractions
   were chosen to reproduce the 100 Gbps-era ratios and have never been tuned.

3. **The seed does not set the ECMP hashing.** `switch-node.cc:90` seeds the
   hash with the switch's own node id and `:137` hashes only the five-tuple,
   whose source ports `entry.h:107-128` allocates deterministically. The three
   no-controller runs of run #126 are bit-identical across the three seeds
   (same makespan to the nanosecond, same trim count, same retransmitted
   bytes), which is what a deterministic path assignment predicts. What the
   seed reaches is the ECN marking draw (`switch-mmu.cc:111`) and the shedding
   and coin decision hash (`ExperimentConfig.hh:844`). The related sentence in
   "Load balancing", that ECMP collisions are a source of seed-to-seed
   variance, holds only in arms whose shedding changes which flows launch.

4. **The `P = 0` arm cannot be configured.** `parse_pacing`
   (`ExperimentConfig.hh:1260-1264`) refuses a Bernoulli probability that is
   not strictly between 0 and 1, with the comment that zero forgives nothing
   and is the admission domain. Section 3.5 proposes the arm as if it were a
   parameter setting; it needs a new rule, or a `recovery_exempt` domain whose
   trim verdict always refuses while the eligible bit stays set.

5. **"Coin refusals set no bit" is true only of the charge.** The gone bit is
   computed from the cell in `budget_gone`, whose `holes` term rises with any
   range the receiver did not absorb. A coin refusal leaves the range a hole
   exactly as a cap refusal does, so it can turn the report red. What is true
   is that a coin refusal leaves `forgiven` untouched.

6. **The eligible bit is fixed at queue-pair creation.** `rdma-hw.cc:368-369`
   asks the experiment layer once, when the receive queue pair is created, and
   every acknowledgement carries the stored answer. The draft's "marks every
   acknowledgement of an eligible flow" is right in effect, but the design
   claim that eligibility is a per-acknowledgement decision is not what the
   code does, and a flow that spans a phase boundary would carry a stale bit.

7. **The headline's loss is gross, not net.** Section 3.1b defines loss as
   forgiven bytes less those that arrived late and were dropped. The headline
   table quotes 7.55, 7.57, 7.56 %, which are `forgiven_bytes`;
   `actual_loss_bytes` gives 7.49, 7.51, 7.50 %. The gap is small in the
   headline arm and large in the step-stop arm, where gross 8.10 % against
   net 7.25 to 7.28 % is a 0.85-point difference carried entirely by the
   remainder path.

8. **Two denominators are in use.** Sections 3.2 and 3.4 divide by the arm's
   own 191.406 GB of offered DP bytes; sections 3.1c and 3.6 divide by the
   fixed-low control's post-shed 190.432 GB, which raises every figure by
   0.5 % relative. Section 3.1b names only the first.

9. **The step stop exists in the code and is off in the headline arm.**
   `sender_stopped` and `remainder_verdict` (`ExperimentConfig.hh:267-306`)
   are reachable only when `selection_policy.step_stop` is true, which
   `regime_64_dcqcn_direct7_4to1_exempt_p01.json` does not set, so the
   headline arm runs without it. The draft is right to keep it out of the
   design, and section 3.4's row is the arm that turns it on.

10. **The protected-step ledger figure in 3.6 belongs to another budget.** At
    budget 0.4 the mask holds the critical steps to 0.44 to 0.45 % of the
    forgiven bytes, not 1.0 to 1.5 %. The 1.4 % band is the budget-0.1 v1
    arm, and the headline vesting arm reads 1.25 to 1.26 %.

11. **The mild cell is a budget-0.4 point.** The `direct2` 2:1 row of section
    3.7 sits under a column headed "FORGIVE, budget 0.1", but
    `regime_64_dcqcn_direct2_2to1_exempt.json` sets `p_high: 0.4`. Its control
    windows are 1409 to 1429 ms, not "about 1410 to 1420".

12. **The healthy cell has eight spines.** Section 3.7's explanatory sentence
    says four. The profile sets `spine_count: 8`, `failed_spine_count: 0`, and
    eight uplinks at 400 Gbps against eight hosts at 400 Gbps is what makes
    the ratio 1:1.

## 3. Recomputed key numbers

### 3.1 Run #127 `p01_single`, three seeds

Formulas: time recovered is `100 x (base - mk) / base` with `base` the
`completion_time_ns_max` of the run #123 `fixed_p_low_baseline` of the same
seed and `mk` the arm's own; forgiven share is `100 x forgiveness.
forgiven_bytes / 191 406 208 000`; actual loss substitutes
`forgiveness.actual_loss_bytes`; re-sent is `100 x transport_recovery.
retransmitted_bytes / total_physical_bytes`; TP collective time is the sum
over (step, workload node) of the widest TP collective span in
`collective_events.csv`, compared against the same sum for the baseline.

| seed | base, ms | arm, ms | time recovered | forgiven | actual loss | re-sent | W | TP, ms | TP base, ms | TP delta |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 9550582 | 1696.69 | 1414.04 | 16.66 % | 7.55 % | 7.49 % | 5.88 % | 0.0736 | 783.0 | 818.0 | -4.28 % |
| 23172535 | 1696.90 | 1424.35 | 16.06 % | 7.57 % | 7.51 % | 5.61 % | 0.0709 | 814.5 | 780.4 | +4.37 % |
| 94081284 | 1700.56 | 1417.28 | 16.66 % | 7.56 % | 7.50 % | 5.22 % | 0.0671 | 795.3 | 805.4 | -1.25 % |

### 3.2 Run #126 references, worst cell

Same formulas. The zero-tolerance row adds the two extra seeds whose r123
baselines are 1688.40 and 1709.85 ms.

| arm | time recovered | loss | re-sent | timeouts | W |
| --- | ---: | ---: | ---: | ---: | ---: |
| zero tolerance, DCQCN (5 seeds) | -1.06 to +0.76 % | 0 | 3.48 to 3.73 % | 10 029 to 10 622 | 0.0297 to 0.0318 |
| forgive, obey the controller (`recovery`, 0.1) | 5.50, 6.56, 6.61 % | 6.81 to 6.92 % | 1.74 to 1.89 % | 4 362 to 4 673 | 0.0319 to 0.0332 |
| no controller | 20.10, 20.11, 20.28 % | 0 | 25.35 % | 93 | 0.2509 |
| `direct2` 2:1 zero tolerance | 14.91, 15.37, 16.08 % | 0 | 0.46 to 0.49 % | 2 106 to 2 281 | 0.0026 to 0.0028 |

The three no-controller runs are identical to the nanosecond, so the 20.1 to
20.3 % spread is the spread of the three baselines and not of that arm.

### 3.3 Run #123, budget 0.4, four arms, worst cell

Loss uses the 191.406 GB denominator of section 3.1b; sender-side arms charge
`shed_logical_bytes`, the recovery arm charges `forgiven_bytes`. The per-step
DP span is the latest end minus the earliest start over the step's DP rows,
and the table reports the median over the sixteen non-critical steps and over
the four critical steps.

| arm | window, ms | non-critical span, ms | critical span, ms | loss | re-sent | timeouts | W |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| control (fixed low) | 1696.7, 1696.9, 1700.6 | 36.49, 36.74, 35.86 | 36.13, 37.15, 36.97 | 0.51, 0.50, 0.48 % | 3.53, 3.67, 3.62 % | 10 110, 10 482, 10 430 | 0.0300, 0.0312, 0.0308 |
| dynamic tolerance (`dblp`) | 1500.4, 1519.4, 1491.2 | not in the local bundle | not in the local bundle | 32.08, 32.31, 32.12 % | 2.11, 2.12, 2.08 % | 5 790, 5 834, 5 659 | 0.0174, 0.0175, 0.0171 |
| loose baseline (fixed high) | 1444.0, 1452.2, 1476.9 | not in the local bundle | not in the local bundle | 40.07, 40.18, 39.96 % | 1.46, 1.54, 1.65 % | 3 843, 4 013, 4 313 | 0.0118, 0.0124, 0.0133 |
| FORGIVE 0.4 | 1340.4, 1357.5, 1359.9 | 11.80, 12.30, 12.55 | 33.70, 35.71, 35.00 | 21.36, 21.24, 21.28 % | 2.75, 2.98, 2.80 % | 3 178, 3 210, 3 359 | 0.0768, 0.0787, 0.0770 |

### 3.4 Run #130, healthy 1:1 cell

| arm | window, ms | time recovered | loss | re-sent | W | min delivered share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| control (fixed low) | 1247.71, 1253.12, 1260.23 | 0 | 0 | 0.047, 0.040, 0.030 % | 0.000362, 0.000305, 0.000232 | not applicable |
| zero tolerance | 1252.30, 1238.75, 1240.41 | -0.37, +1.15, +1.57 % | 0 | 0.048, 0.059, 0.046 % | 0.000375, 0.000467, 0.000363 | not applicable |
| dynamic tolerance | 1244.04, 1251.48, 1257.21 | 0.29, 0.13, 0.24 % | 0 | 0.034, 0.028, 0.035 % | 0.000267, 0.000211, 0.000258 | not applicable |
| loose baseline | 1252.20, 1249.54, 1251.44 | -0.36, +0.29, +0.70 % | 0 | 0.025, 0.022, 0.022 % | 0.000195, 0.000160, 0.000168 | not applicable |
| FORGIVE 0.1 | 1191.83, 1183.66, 1166.31 | 4.48, 5.54, 7.45 % | 1.00, 1.30, 1.12 % | 0.039, 0.036, 0.031 % | 0.00268, 0.00339, 0.00290 | 0.9454, 0.9156, 0.9477 |
| FORGIVE with the coin at 0.25 | 1175.05, 1169.81, 1179.05 | 5.82, 6.65, 6.44 % | 0.315, 0.418, 0.271 % | 0.274, 0.354, 0.245 % | 0.00319, 0.00418, 0.00280 | 0.9840, 0.9826, 0.9827 |

### 3.5 Run #123, mild cell, `direct2` at 2:1

The profile runs `p_high = 0.4`, not 0.1.

| seed | control, ms | FORGIVE time | loss | control W | FORGIVE W | exempt flows | re-armed |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 9550582 | 1428.60 | 12.53 % | 2.50 % | 0.0026 | 0.0160 | 71 680 | 9 |
| 23172535 | 1417.73 | 11.73 % | 2.37 % | 0.0024 | 0.0155 | 71 680 | 9 |
| 94081284 | 1408.88 | 10.45 % | 2.37 % | 0.0027 | 0.0158 | 71 680 | 7 |

## 4. What the bundles show and the draft omits

1. **The simulator moves 25 % more data-parallel bytes than the algorithm
   asks for.** ASTRA-sim splits the 68 359 375-byte bucket into chunks of
   17 089 843 B and, as `Sys.cc:957-962` records, gives the last stream a full
   chunk rather than the remainder, so five full streams run and a rank is
   owed 149 536 100 B per step instead of the `2 x 7/8 x 68 359 375 =
   119 628 906` B a direct all-reduce would move. Every per-byte figure in
   the paper is against the larger number. The draft states both numbers but
   never reconciles them, and a reviewer who divides will ask.

2. **The no-controller reference is one run, not three seeds.** All three
   run #126 no-controller bundles finish at 1 355 708 699 ns with 48 462 610
   trim notifications and 201 185 054 144 retransmitted bytes. The reported
   20.1 to 20.3 % band is baseline spread. The same is true of the seed
   story generally: path selection is deterministic given the five-tuple.

3. **Timeouts are a clean second axis and are quoted only for the
   no-controller arm.** At budget 0.1 on the worst cell the control fires
   10 110 to 10 482 retransmission timeouts, FORGIVE 4 145 to 4 348, the
   never-re-engage arm 2 102 to 2 187, the up-front arm 5 197 to 5 564, and
   the no-controller arm 93. The CNP counts move the same way: 12.99 to
   13.40 M for the control against 4.43 to 4.59 M for FORGIVE.

4. **W of the exempt arms is not in the paper.** FORGIVE at budget 0.1 runs
   W 0.067 to 0.076 against the control's 0.030, that is, it trims about
   2.4 times as much, and `W_prime` (trims net of forgiveness) is 0.0554 on
   seed 9550582. The healthy cell is quoted this way in 3.7 but the worst
   cell is not.

5. **The exemption's reach and its interruptions are measured and unquoted.**
   In the headline arm 86 059 to 86 172 of the 89 600 data-parallel flows
   (96 %) were granted an exemption at some point; the receiver sent 6.72 to
   6.84 million allowance-gone reports; the bit changed 44 020 to 44 792
   times, about 0.52 transitions per exempt flow; 15 966 to 16 230 flows
   (19 %) spent time obeying after a grant, averaging 0.17 ms each. The coin
   arm halves the transitions (0.32 to 0.35 per flow) and the up-front arm
   grants only 41 903 to 43 554 flows.

6. **The step-stop arm's real loss is 7.3 %, not 8.1 %.** Of the 8.10 % it
   charges, 0.78 to 0.83 points arrive late and are dropped at the receiver,
   which the `forgiven_remainder_bytes` column separates. The draft reports
   the charge.

7. **The `P = 0.05` and `P = 0.1` points quoted in 3.5 ran with a fabric cost
   the draft does not mention.** Under the earlier rule set those arms re-sent
   17.8 to 21.3 % of all bytes at W 0.18 to 0.22, close to the no-controller
   ceiling of 25.4 % at W 0.25, against the vesting coin arm's 6.5 % at
   W 0.075. Quoting them as "the trend" for loss without the fabric cost
   understates what changed between the rule sets.

8. **The never-re-engage arm sits exactly on the bound.** Its
   `min_delivered_share` is 0.9000 on all three seeds, against 0.9001 for the
   headline arm and 0.9069 to 0.9094 for the coin arm. An arm that never
   returns the controller spends its cap to the last byte, which is the
   safety argument for re-engagement stated as a number.

9. **The healthy cell's zero-tolerance arm is faster than the control on two
   of three seeds** (+1.15 % and +1.57 %), which is larger than the 0.1 to
   0.3 % that sender-side shedding recovers there. Section 3.7 quotes the
   shedding and loose-baseline references but not this one.

10. **`late_forgiven_bytes` is 85 to 144 MB per arm** and is the quantity that
    separates the two loss definitions. It is largest in the up-front coin
    arm (127 to 144 MB) and smallest in the up-front arm without the coin
    (45 to 51 MB).
