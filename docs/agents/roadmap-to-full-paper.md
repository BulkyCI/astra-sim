# Roadmap: from the forgive protocol to an NSDI or SIGCOMM paper

Plan of record, written 2026-09-08 after runs #117, #120 and #121 and the
literature reviews in [forgive-related-work.md](forgive-related-work.md).
The spec is [forgive-protocol.md](forgive-protocol.md). This document
lists what the paper will promise, what is still unanswered, and the
phases that turn each unanswered question into a number, in the order
their dependencies and their power to kill the claim dictate. A future
agent picks up at the first phase whose "done when" is not met.

## 1. Target

The finished paper shows, on a fabric shaped like Ultra Ethernet and MRC
(packet spraying, packet trimming, selective retransmission, a
window-based congestion control), that a training job can pay for
congestion in bounded, phase-placed gradient loss instead of in
retransmitted bytes or in reduced rate; that this recovers a stated share
of the congestion-control time penalty at a stated fraction of the bytes
blind shedding spends; that a neighbouring job pays a stated and bounded
price; and that a current model trained with that loss injected reaches
the same accuracy. Pattern: a Tweak of the congestion-control reaction,
ablated against the controller in its best configuration and against
blind shedding at equal budget, plus the Negative result that motivates
it.

## 2. Promises the paper makes

| # | promise | status today | phase that discharges it |
| --- | --- | --- | --- |
| P1 | On a trimming fabric with selective retransmission the incast episode costs under 1 % of training time; prior relief numbers measured go-back-N | shown (runs #117, #120), per-flow ECMP only | 2 confirms it under spraying |
| P2 | Congestion control's time penalty is the cost tolerance can buy back, and it is large | shown for DCQCN as configured (18 to 24 %) | 1 (tuned DCQCN), 3 (NSCC) |
| P3 | Budgeted exemption recovers a large share of that penalty with critical steps untouched | shown at one cell, 3 seeds, DCQCN, ECMP (13 %) | 0 (front), 2, 3 |
| P4 | Loss targeted by the fabric's trim signal costs a fraction of the bytes blind shedding costs for the same or better time | shown (9 % vs 32 %) | 0 |
| P5 | The mechanism is minimal and controller-agnostic: sender flag at birth, receiver's existing retransmission request as the re-arm, no wire change | shown for DCQCN; argued for NSCC | 3 |
| P6 | A neighbouring job that obeys congestion control pays a bounded price | unmeasured | 5 |
| P7 | A current model survives the loss actually spent, at the budgets used | assumed from DBLP and Weintraub 2025 | 6 |
| P8 | The result holds on a fabric that carries only DP and PP traffic, at 128 ranks or more | unmeasured; 64 ranks with TP on the fabric | 4 |
| P9 | The numbers are stable across seeds and not artefacts of RTO, ECN thresholds or burst shape | 3 seeds at headline points | 7 |

## 3. Unanswered questions, each with the experiment that answers it

1. Is the 24 % DCQCN penalty inherent or mistuned? Phase 1.
2. How much of the fan-in effect and the penalty is per-flow ECMP hash collision, which sprayed fabrics do not have? Phase 2.
3. Does the exemption transfer to a window-based, trim-reactive controller, and is NSCC's penalty larger or smaller than DCQCN's? Phase 3.
4. Under receiver credit (RCCC), does the exemption become a receiver-side credit policy with no sender change? Phase 3b.
5. What does the gain become when the fabric carries DP and PP only, and at 128 ranks? Phase 4.
6. What does an exempt job cost a CC-obeying tenant, and does the budget bound it? Phase 5.
7. Does a current model tolerate the loss the exempt arm actually spends, at budgets 0.1 to 0.4, with the loss placed where the fabric placed it rather than i.i.d.? Phase 6.
8. What does the critical-step mask cost in time, and what does the loss-versus-time front look like? Phase 0, running.
9. Does a persistent burst change the answer? Phase 7.
10. Could a NIC host the sender side and a UET receiver host the verdict? Section 6, argued not measured.

## 4. Phases

Costs are in cluster arms (a 64-rank four-arm comparison is one record of
four arms, about 5 h per arm on the DCS cluster, six to eight arms in
parallel) and engineering weeks for one person. Each phase names what
ends it.

| # | phase | answers | instrument | done when | kill test | cost |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | Dose front and mask ablation (running, run 34260936239) | Q8 | worst DCQCN cell, budgets 0.1, 0.2, 0.6 at 3 seeds, 2 more seeds at 0.4, no-critical-steps at 3 seeds | front plotted: bytes lost vs time recovered, exempt and admission, with seed bars | front flat above 0.2, or exempt loses to admission on both axes at 0.1 | 56 arms, 2 days |
| 1 | DCQCN in its best configuration | Q1 | worst cell, fixed-low single arms: RATE_AI and RATE_HAI at x1, x4, x16 of the scaled literals; ECN KMIN/KMAX at x1 and x2; alpha gain at x1 and x4; 1 seed | a tuned setting chosen by shortest window; all later DCQCN arms use it | tuned DCQCN within 5 % of the no-CC window: the penalty was mistuning, P2 and P3 shrink to what survives | 10 arms, 1 day |
| 2 | Per-packet spraying | Q2, P1 | switch hashes a per-packet entropy (`load_balancing: per_packet`); rerun the 8 map cells as single arms; then the worst-cell comparison at the tuned DCQCN, 3 seeds; then adaptive spraying in the REPS style if oblivious spraying leaves collision-shaped hot spots | map redrawn under spraying; P3 restated on the sprayed fabric | the exempt gain under spraying falls below 5 window-percent | 20 arms, 1 week engineering for oblivious, 2 more for adaptive |
| 3 | NSCC | Q3, P2, P5 | new CC mode in `rdma-hw.cc`: per-connection window and in-flight, ACK-carried received bytes, ECN plus delay four-case update, `quick_adapt` from achieved goodput, per-trim window decrement, BDP-scaled parameters per UET 1.0.3 pp. 384 to 393; fixtures: single-flow convergence to target delay, N-to-1 fairness, reaction to a trim burst; then the exemption guard in the update; rerun the 4 CC-on map cells and the worst-cell comparison, 3 seeds | NSCC arms pass the fixtures; P2 and P3 have an NSCC row beside the DCQCN row | exempt gain under NSCC under 5 window-percent | 24 arms, 3 to 4 weeks engineering |
| 3b | RCCC (receiver credit) | Q4 | destination-paced credit per source; exemption expressed as credit issued at line rate to eligible non-critical sources while their budget lasts | one comparison at the worst cell | none; a design result | 12 arms, 2 weeks |
| 4 | Workload currency and scale | Q5, P8 | TP off the fabric (`tp_all_reduce_bytes` 0 or an NVLink dimension), FSDP reduce-scatter and all-gather bytes with only reduce-scatter forgivable (needs a collective-phase field in `AstraSim::OperationContext`), oversubscription re-sized so fixed-low's trim ratio is near 0.03; then 128 ranks | the headline comparison at 128 ranks on the DP-only fabric, 3 seeds | gain per eligible byte falls as the eligible share rises | 30 arms, 2 weeks engineering |
| 5 | Fairness | Q6, P6 | a second, CC-obeying tenant on the same spines (long-lived background flows through the microburst machinery), exempt job beside it, 3 seeds; report the tenant's all-reduce and flow-completion slowdown against the exempt job's gain; sweep the budget as the knob | a fairness paragraph with a number and the budget that bounds it | the tenant's slowdown exceeds the exempt job's gain at every budget | 24 arms, 1 to 2 weeks |
| 6 | Tolerance on real training | Q7, P7 | export per-(rank, step) forgiven byte ranges from the exempt arm; map them to gradient-bucket elements; zero those elements in a PyTorch DDP communication hook (the transcript-replay method the HotNets 2024 paper proposes); train a small current model (1B-class transformer) at budgets 0.1, 0.2, 0.4 against an unmodified run; compare loss curves and final evaluation | accuracy delta within seed noise at the budget the paper claims | loss curve diverges at that budget: lower the budget or drop the claim | 8 GPUs for 1 to 2 weeks; needs a collaborator |
| 7 | Robustness | P9 | 5 seeds at every headline point; RTO at 0.5 and 2 ms; ECN thresholds at spec defaults; burst every step and 7 x 1 GiB once | every headline number carries a seed bar and a sensitivity row | any headline sign flips under a sensitivity row | 40 arms, 1 week |
| 8 | Paper | all | claims table with one number each, threats to validity, artifact: the ns-3 fork, profiles, CI ledger and release bundles are already a reproducibility package | draft with every promise discharged or scoped out | none | 3 weeks writing |

Order and calendar. Phase 0 is running. Phases 1 and 2 next, in parallel:
1 is one day of cluster and no code; 2 is a week of code then a day of
cluster. Phase 3 starts as soon as 2's oblivious spraying is in, since
NSCC without spraying is not the fabric the claim is about. Phase 6 runs
whenever GPUs appear and depends on nothing but phase 0's budgets. Phases
4, 5 and 7 follow 3. Total: about three months of engineering and cluster
time to a draft, if GPUs are found by the middle of it.

## 5. Venue questions and where the plan answers them

| reviewer asks | answer from |
| --- | --- |
| Is the baseline tuned? | phase 1 for DCQCN; phase 3 uses the UET spec defaults for NSCC |
| Is this the fabric modern training runs on? | phases 2 and 3 (spraying, NSCC), phase 4 (DP-only, 128 ranks) |
| Does the model actually survive this? | phase 6, with loss placed as the fabric placed it |
| What about other tenants? | phase 5 |
| Variance? | phase 7, 5 seeds |
| What is new over MLT, trimmable gradients, OptiReduce? | related-work document, three named elements |
| Can hardware do this? | section 6 below |

## 6. Deployability argument, to be written not measured

Sender side: one flag per queue pair and a conditional in the congestion
notification handler. Programmable congestion control on ConnectX-7
class NICs exposes exactly that handler. Receiver side: a UET receiver
already tracks received ranges for selective retransmission; forgiveness
is "acknowledge a range without its data", one bitmap write plus the
ordinary cumulative acknowledgement. The budget ledger is per (rank,
step), a few thousand counters, in the NIC or in the collective library.
MLT's authors judged RDMA NICs unable to host their semi-reliable
transport; this design asks for less than MLT did.

## 7. Deferred and out of scope

Deferred until phase 3: any statement about NSCC. Deferred until phase 6:
any statement that the loss is safe. Deferred until phases 4 and 7: a
submission. Out of scope for this paper: a hardware prototype; scales
above 128 ranks (simulator time); cross-datacenter links; MRC's
source-routed path set as such (adaptive spraying stands in for it).

## 8. Stop doing

No comparisons against run #117's relief numbers. No "tail" or "episode"
framing. No claim about a congestion control the simulator does not
model. No budget above 0.4 in a headline: MLT's profiled bounds are 0.7
to 3.3 % of gradient bytes at equal rounds and 10 % at a quality target,
and the exempt arm at 0.4 already spends 9 %.
