# Run #121: bounded loss as a third congestion response

Run 34156878678, commit `8dc9275`, release `b363b3rri7pbgbaudfh3tbnysiranl66`,
six of six comparisons collected, three seeds per cell. The protocol as built is in
[forgive-protocol.md](forgive-protocol.md); the map that pointed here in
[run-120-regime-map.md](run-120-regime-map.md).
Written 2026-09-08.

This wave measured the exempt arm before the revocation fix at commit
`c6855f0`, where any repair request ended an exemption rather than only a
spent allowance. Run #123 re-measured the same cells on the corrected
code, and [run-123-readout.md](run-123-readout.md) carries the figures
that replace every exempt-arm number below. The body is kept as the
record of what run #121 measured.

## The claim

An overloaded fabric makes a sender pay one way or another. Without
congestion control it pays in re-carried bytes: on the map's worst cell
one offered byte in four was trimmed and sent again. With DCQCN it pays in
time: the same cell ran 24 % longer while trims fell tenfold. This wave
adds a third currency. A flow whose bytes the model can afford to lose,
on a step where it can afford to lose them, keeps sending through the
congestion signal; the fabric trims what does not fit, the receiver
forgives those bytes up to a per-step budget, and the first trim the
receiver refuses to forgive puts the flow back under congestion control.
The flow pays in bounded, phase-placed loss. It gets back about half the
time DCQCN costs and keeps DCQCN's re-carry.

| response, same fabric (DCQCN, direct7, 4:1) | window | bytes re-carried | bytes lost | seeds |
| --- | ---: | ---: | ---: | ---: |
| no congestion control, repair everything | 1367 ms | 24 % of offered | none | 1 (run #120) |
| DCQCN | 1686 to 1690 ms | 3 % | none | 3 |
| DCQCN + exempt forgiveness, budget 0.4 | 1459 to 1468 ms | 1 % | 2.2 % of offered: 9 % of DP, none on critical steps | 3 |
| DCQCN + blind shedding, budget 0.4 | 1480 to 1509 ms | 2 % | 7.7 % of offered: 32 % of DP | 3 |

The last row is the comparison that decides whether the mechanism is
worth having. Phase-aware shedding at admission, DBLP's own move, spends
its whole budget by a blind draw whether or not the fabric is congested.
The exemption spends only what the fabric actually trims. At the same
budget it loses 3.4x fewer bytes, its window is shorter in every seed,
and it never touches a critical step, which the fixed-high arm does. That
is the contribution: bounded loss targeted by the fabric's own signal,
with the budget as the safety law, on top of a congestion control that
stays in charge the moment the budget is refused.

## How the line got here

The programme set out to show that phase-aware bounded loss shortens
congestion episodes. Three waves said otherwise, each for a reason worth
keeping.

Run #117 found relief of 4 to 11 % of makespan under go-back-N. The
selective-repair canary then showed the same burst costing 29 ms instead
of 1.8 s, and the relief was the transport re-carrying up to 79 bytes for
every byte the policy removed. Go-back-N with no congestion control is a
combination nobody deploys, and every relief number in that family
measures it, not the policy.

Run #120 mapped fan-in, oversubscription and congestion control under
selective repair. The burst episode cost under 1 % of the window at every
one of eight cells, so admission-time tolerance had nothing to shorten,
and forgiveness as a saver of repair rounds had an arithmetic ceiling
under 0.2 %. The map's one finding with teeth was DCQCN's price: 18 to
24 % of the window for a tenfold cut in trims, from millions of rate
cuts.

The exemption is the design that takes that finding at its word. Its one
non-obvious choice comes from the generator's own DCQCN table: ECN marks
begin at 800 KB of queue and trims at 4 MiB, so at the worst cell at
least 74 % of rate cuts come from marks a forgiven trim never touches.
Exempting only the trim-originated cut would have built in the null.
Exempting every cut, bounded by the budget and ended by the receiver's
refusal, is what moved the window.

## What the wave shows

### Worst cell: DCQCN, direct7, 4:1

Four matched arms per seed at the same budget: fixed-low (p = 0.005 every
step), admission (sheds 40 % of eligible DP payloads outside critical
steps), exempt (forgives up to 40 % of eligible bytes per (rank, step)
outside critical steps and ignores every rate cut until refused),
fixed-high (sheds 40 % on every step).

| seed | arm | window | DP span, steps 4-17 | DP span, CLR steps | TP span | burst drain | W | W' | DP bytes lost | CNPs taken | CNPs ignored | RTOs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 23172535 | fixed-low | 1686 ms | 36.7 ms | 37.2 ms | 9.03 ms | 104 ms | 0.031 | 0.031 | 0.5 % | 13.4 M | 0 | 10482 |
| 23172535 | admission | 1509 ms | 25.8 ms | 35.8 ms | 9.97 ms | 78 ms | 0.018 | 0.018 | 32.3 % | 7.9 M | 0 | 5834 |
| 23172535 | exempt | 1468 ms | 21.1 ms | 37.4 ms | 8.30 ms | 116 ms | 0.034 | 0.011 | 9.5 % | 6.4 M | 10.8 M | 3330 |
| 23172535 | fixed-high | 1441 ms | 25.0 ms | 24.6 ms | 9.72 ms | 77 ms | 0.012 | 0.012 | 40.2 % | 6.2 M | 0 | 4013 |
| 94081284 | fixed-low | 1690 ms | 35.9 ms | 37.0 ms | 9.15 ms | 140 ms | 0.031 | 0.031 | 0.5 % | 13.1 M | 0 | 10430 |
| 94081284 | admission | 1480 ms | 24.0 ms | 37.0 ms | 9.10 ms | 90 ms | 0.017 | 0.017 | 32.1 % | 7.7 M | 0 | 5659 |
| 94081284 | exempt | 1468 ms | 20.4 ms | 36.1 ms | 8.00 ms | 119 ms | 0.032 | 0.010 | 9.4 % | 6.0 M | 10.9 M | 3100 |
| 94081284 | fixed-high | 1466 ms | 24.5 ms | 25.8 ms | 10.15 ms | 116 ms | 0.013 | 0.013 | 40.0 % | 6.4 M | 0 | 4313 |
| 9550582 | fixed-low | 1686 ms | 36.6 ms | 36.1 ms | 9.59 ms | 141 ms | 0.030 | 0.030 | 0.5 % | 13.0 M | 0 | 10110 |
| 9550582 | admission | 1490 ms | 24.3 ms | 34.7 ms | 9.19 ms | 102 ms | 0.017 | 0.017 | 32.1 % | 7.8 M | 0 | 5790 |
| 9550582 | exempt | 1459 ms | 20.3 ms | 36.8 ms | 7.14 ms | 114 ms | 0.032 | 0.011 | 8.8 % | 6.1 M | 10.4 M | 3334 |
| 9550582 | fixed-high | 1433 ms | 22.7 ms | 22.1 ms | 9.19 ms | 96 ms | 0.012 | 0.012 | 40.1 % | 6.1 M | 0 | 3843 |

The pre-registered rule asked for 5 window-percent against fixed-low
with critical steps unmoved and the burst drain under 2x. It got 12.9,
13.1 and 13.5 %, critical-step spans within 0.9 ms of fixed-low, and
burst drain at 1.12x, 0.85x and 0.81x.

The mechanism acts exactly where it was aimed. Non-critical DP span falls
from 36 ms to 21 ms while critical-step span stays at 37 ms; the window
gain (218 ms) is the 16 non-critical steps at 15 ms each, with the
critical steps, the burst step and compute untouched. Exempt flows push
into the queue, so W rises slightly (0.033 against 0.031), two thirds of
those trims are forgiven (W' 0.010), and the rest are pulled and re-arm
their flow: 12 to 13 thousand of the 71 680 exempt flows per seed. The
transport ends calmer, not wilder: timeouts fall by two thirds, taken
rate cuts by half. TP spans fall because DP flows leave the leaf sooner.
The burst drains slower in one seed and faster in two, inside fixed-low's
own 37 ms seed spread. The budget law held in every one of the 1280
ledger cells per arm.

Against admission the window edge is 2.7, 0.8 and 2.1 %, the same sign
every time and about the size of admission's own seed spread. The
headline against admission is not the window. It is that the exempt arm
reached it while losing 9 % of the DP bytes instead of 32 %.

### Light cell: DCQCN, direct2, 2:1

| seed | arm | window | DP span, steps 4-17 | DP span, CLR steps | burst drain | W | W' | DP bytes lost | CNPs taken | CNPs ignored |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 23172535 | fixed-low | 1407 ms | 22.9 ms | 22.8 ms | 63 ms | 0.0024 | 0.0024 | 0.5 % | 3.3 M | 0 |
| 23172535 | admission | 1310 ms | 16.3 ms | 22.8 ms | 54 ms | 0.0015 | 0.0015 | 32.3 % | 2.1 M | 0 |
| 23172535 | exempt | 1354 ms | 18.6 ms | 21.9 ms | 67 ms | 0.0045 | 0.0025 | 0.8 % | 1.7 M | 3.7 M |
| 23172535 | fixed-high | 1277 ms | 15.5 ms | 16.8 ms | 45 ms | 0.0011 | 0.0011 | 40.2 % | 1.7 M | 0 |
| 94081284 | fixed-low | 1398 ms | 22.9 ms | 19.7 ms | 61 ms | 0.0027 | 0.0027 | 0.5 % | 3.5 M | 0 |
| 94081284 | admission | 1313 ms | 16.3 ms | 19.9 ms | 64 ms | 0.0015 | 0.0015 | 32.1 % | 2.0 M | 0 |
| 94081284 | exempt | 1343 ms | 18.0 ms | 19.4 ms | 69 ms | 0.0046 | 0.0026 | 0.8 % | 1.7 M | 3.7 M |
| 94081284 | fixed-high | 1284 ms | 15.2 ms | 18.6 ms | 41 ms | 0.0012 | 0.0012 | 40.0 % | 1.7 M | 0 |
| 9550582 | fixed-low | 1418 ms | 22.4 ms | 21.6 ms | 64 ms | 0.0026 | 0.0026 | 0.5 % | 3.5 M | 0 |
| 9550582 | admission | 1312 ms | 16.2 ms | 19.6 ms | 48 ms | 0.0015 | 0.0015 | 32.1 % | 2.0 M | 0 |
| 9550582 | exempt | 1343 ms | 18.7 ms | 21.6 ms | 78 ms | 0.0049 | 0.0025 | 1.0 % | 1.7 M | 3.9 M |
| 9550582 | fixed-high | 1280 ms | 16.4 ms | 13.0 ms | 42 ms | 0.0011 | 0.0011 | 40.1 % | 1.7 M | 0 |

The pre-registration said this cell "must not move", on the reasoning that a fabric
that barely trims gives the mechanism nothing to act on. That reasoning
was wrong and the rule is withdrawn, not reinterpreted: DCQCN takes 3.3
million rate cuts here from ECN marks alone, and the protocol's own
reasoning (ECN marks precede trims) says the exemption acts on those. It did. The
window moved 4 %, trims doubled (all of the increase forgiven), and the
burst drained 5 to 22 % slower. The lesson is the honest shape of the
mechanism: where the fabric is barely congested the exemption's price is
low and its return is low, and blind shedding's 7 % here is bought by
removing a third of the DP bytes from a fabric that did not need them
removed. Where the fabric is overloaded, the exemption is the better
buy; where it is not, neither policy should be on.

## What the claim rests on

Every number above is conditioned on four things this wave did not test.

- **Tolerance.** That a current model survives 9 % loss of its DP
  gradient bytes on non-critical steps is assumed, from DBLP's evidence
  on EfficientNet and ResNet and from Weintraub 2025's 10 % uniform loss
  on Llama2 7B, which tested no phase dependence. Until a real training
  run says so, the claim reads "at a budget the model is assumed to
  tolerate". This needs GPUs and is the only stage this cluster cannot
  run.
- **Which congestion control.** DCQCN is what the model has. Meta runs
  its 400G fabrics with DCQCN off; UEC's default is NSCC, window-based
  with a trim-triggered quick_adapt. The idea transfers to any control
  that reacts to marks and trims, and nothing here measures that.
- **One tenant.** Exempt flows shared the fabric with their own TP and
  one burst. Against another tenant's CC-obeying flows the price of the
  exemption lands on the tenant. The budget bounds it; nothing here
  measures it.
- **A toy shape.** 64 ranks with TP on the fabric, so DP is 24 % of the
  bytes and the mechanism's ceiling is a quarter of what it would be on
  a fabric that carries DP and PP alone, which is what NVLink-scale TP
  leaves to it.

## The road

The paper is the claim above with its four conditions stated. The next
work either sharpens the claim or discharges a condition, in this order.

| stage | question | instrument | cost | ends the stage if |
| --- | --- | --- | --- | --- |
| 1. Dose front | How does the loss-versus-time trade move with the budget? | worst cell, p_high {0.1, 0.2, 0.4, 0.6}, exempt and admission arms, 3 seeds, 24 arms | one cluster day | the window is flat above p 0.2 |
| 2. No-CC cell | Does forgiveness buy back re-carry where there is no CC to exempt? | none/direct7/4:1, CC-neutral recovery domain, 3 seeds, 12 arms | half a cluster day | W' is within seed noise of W |
| 3. Fairness | What does an exempt job cost a CC-obeying neighbour? | a second tenant's flows on the same spines, 3 seeds, 12 arms | a day of generator work plus a wave | the tenant's DP span grows by more than the exempt job's shrinks |
| 4. Workload shape | Does the ceiling rise when the fabric carries DP only? | TP in NVLink, FSDP reduce-scatter and all-gather bytes, oversubscription re-sized so the fabric stays the bottleneck | generator work, one map, one wave | the gain does not scale with the eligible share |
| 5. NSCC | Does the idea survive a window-based CC with quick_adapt? | an NSCC model in rdma-hw.cc against the UEC 1.0 defaults | weeks | exempt gain under 5 % of window |
| 6. Tolerance | Does a current model survive 9 % non-critical DP loss? | real training of a small current model with injected bucket loss under the ledger law | GPUs | the loss curve diverges |

Stages 1 and 2 sharpen one figure, the front of bytes lost against time
recovered with the three responses on it, and are the next wave. Stages
3 and 4 answer the two objections a reviewer raises first. Stage 5 decides
whether the claim may say more than "DCQCN". Stage 6 is what the whole
line stands on.

Retired by this wave and the two before it: any claim that tolerance
shortens tails or episodes, the 32-rank decisive wave, and comparisons
against run #117's numbers.

## The courier that was re-minted

The arm for seed 9550582 at the worst cell completed on the cluster at
10:03 UTC and placed its outbox. Its courier runner was provisioned at
10:03:19 and the collect job sat queued from 10:03:32 with no runner;
`squeue` showed no job. The runner job script tears a JIT runner down
after 1800 s without an assigned job (`DCS_IDLE_GRACE_SECONDS`), and three
couriers were provisioned inside five minutes; the one GitHub did not
assign within the grace window was killed by its own guard at about
10:33, and the job it was minted for could match no other runner. The log
on the cluster is `~/astra-ci/jobs/runner-<slurm job id>.log`.

Recovery, as run on 2026-09-08 16:35 to 16:40 UTC. Cancelling the run and
re-running its failed jobs is not enough: the courier's provision job had
succeeded, so a failed-jobs rerun re-queued the collect job with no
runner behind it. Re-running from the provision job mints a new courier
for that key and runs its dependents; the outbox on scratch was intact
and the collect and record steps finished inside two minutes.

```
gh run cancel 34156878678 -R BulkyCI/astra-sim
gh run rerun -R BulkyCI/astra-sim --job <id of "Provision the courier runner" for that key>
```
