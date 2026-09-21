# FORGIVE: receiver-budgeted forgiveness with a bounded congestion-control exemption

Draft section for the revision of our May preprint (Ma, Qu, Yi, Lin,
Ganjali, arXiv 2605.01989), written 2026-09-18 for sharing. FORGIVE,
the vesting rule and the protocol are Joe Fang's, in collaboration with
Zechen Ma; the Bernoulli coin and the non-zero start are Yashar Ganjali's
suggestions. Every number below comes from a certified arm named in
section 7, and every number that was measured under a rule since replaced
says so where it appears. The vesting version is the design; the coin is
the secondary result.

## 1. The observation

Our May prototype tolerated a bounded share of lost gradient bytes on the
steps where training could afford it and recovered training time by
avoiding the retransmission round trips a lossless transport spends on the
tail of every collective. That prototype ran over UDP with a bitmap probe
and a stop message, and its speedup was the repair tail.

A modern training fabric does not have that tail. On a switch that trims a
congested packet to its header and forwards the header, a receiver learns
of every loss within one fabric transit and asks for exactly the missing
packet, so the repair costs one round trip rather than a timeout. We
measured this first. Across a map of eight cells (with and without a
congestion controller, fan-in 2 and 7, oversubscription 2:1 and 4:1, 64
ranks), the excess of the two burst steps over a steady step was 0.04 to
0.62 % of the training window in every cell, against a kill line of 5 %.
The repair-driven tail that MLT, LTP and OptiReduce shorten is already
gone on such a fabric.

What is not gone is the congestion controller's reaction. DCQCN divides
the trim ratio by 8 to 10 on the same map and lengthens the training
window by 18 to 24 %, through millions of rate cuts and thousands of
retransmission timeouts. The time a lossy transport can recover on a
trimming fabric is that reaction, and the question FORGIVE answers is how
a bounded loss tolerance can pay for turning it off safely.

The answer has one sentence. A receiver that is willing to lose at most a
fraction `p` of what it is owed in a step can license its senders to
ignore the controller for as long as the fabric has not already lost more
than that tolerance could absorb; the tolerance is the safety bound on the
licence, and forgiving trimmed bytes is how the receiver spends it. On the
worst cell of the map, at `p = 0.1`, the licence recovers 16.1 to 16.7 %
of the training window for 7.55 % of the data-parallel bytes, against a
ceiling of 20.1 to 20.3 % with no controller at all, which re-sends
25.4 % of every byte. On a healthy 1:1 fabric it recovers 4.5 to 7.5 %
for 1.0 to 1.3 %.

## 2. Design

### 2.1 Setting

The fabric trims packets under congestion (the payload is dropped and the
header is forwarded), the transport repairs selectively, and a congestion
controller runs at every sender. FORGIVE treats the controller as a black
box: no line inside it changes, and the only thing FORGIVE decides is
whether a congestion signal is handed to it. We evaluate with DCQCN
because it is what our fabric runs; nothing below depends on which
controller it is.

The job is data-parallel training. Each step, every rank all-reduces its
gradient with the other ranks of its group, as a reduce-scatter followed by
an all-gather. Only that traffic is ever forgiven or exempted; tensor-
parallel, pipeline and control traffic is delivered in full under the
controller. The collective library knows at the start of a step how many
bytes each peer will send to each rank; the receiver needs that table and
nothing else about the workload. The training side names the steps on
which loss is not affordable; we use steps 1, 2, 3 and 20 of a 20-step
window.

### 2.2 The budget

Each receiving rank holds one budget per training step, shared by every
sender into it. The budget is `p x owed`, where `owed` is the sum of what
the rank's peers will send it that step, and `p` is `p_low` (0.005) on a
critical step and `p_high` (0.1 in the headline) elsewhere. A byte the
receiver declines to have re-sent is charged to the budget and never
refunded.

The guarantee, certified by the simulator and again by the analyzer at
every step's last collective, is that every rank received at least
`1 - p` of what it was owed. A run that breaks it fails.

### 2.3 Vesting

The budget is not available at once. The receiver may forgive a trimmed
range only while

```
forgiven + range <= p x (received + forgiven),
```

equivalently `forgiven <= p/(1-p) x received`: at every prefix of the
step, of the bytes the receiver has accepted, at most `p` are forgiven.
The cap is a line through the origin in received-bytes space that reaches
`p x owed` exactly when `1 - p` of the step has arrived. It needs no state
beyond two counters the receiver already keeps, and it holds the hard
bound by construction under any trim profile the fabric produces.

The reason for vesting is what happens without it. If the whole budget is
available from the first byte, the opening incast of a step spends it in
the first fifth, forgiven bytes never fall, and the licence of section 2.4
ends for the rest of the step. That arm recovers 9.1 to 10.2 % against
vesting's 16.1 to 16.7 % on the same seeds (section 3.4). Vesting keeps
the licence alive by construction, because the cap reaches the line only
when the step is nearly complete.

A trimmed range that the cap refuses is repaired by the ordinary path and
gets a fresh decision if it is trimmed again. Every acknowledgement of a
forgiven range includes the congestion mark the trim would have produced,
so forgiving hides no congestion from a sender that is listening.

### 2.4 The licence

The receiver marks every acknowledgement of an eligible flow, on any step
with `p > 0`, with a bit saying the flow may be exempt, and with a second
bit that says whether the step's tolerance is gone:

```
gone  <=>  forgiven + holes + one packet > p x owed,
```

where `holes` are the bytes below the highest sequence the receiver has
seen on its open flows that are neither received nor forgiven. The
inequality reads: even if every byte now missing were forgiven, the step's
tolerance would be exceeded. Holes count each missing byte once and fall
as repairs land, so the report recovers on its own when the fabric does.

A sender obeys its controller until the first acknowledgement arrives with
the eligible bit set and the gone bit clear; from then on it withholds
every congestion signal from the controller. A later report with the gone
bit set makes it deliver signals again, and a report with the bit clear
lets it withhold again. There is no latch and no hysteresis: the sender is
exempt exactly when the last report it saw said so. A controller that
hears nothing raises its own rate on its own timers, so nothing inside it
is touched. A critical step runs the same rules with `p_low`; its pool is
gone after a few hundred kilobytes and the controller returns almost at
once.

The licence is the mechanism that recovers time. Forgiveness under the
controller, with no licence, recovers 5.5 to 6.6 % on the worst cell for
the same loss (section 3.3); the licence brings it to 16 %.

### 2.5 The coin

Yashar Ganjali suggested spending the budget probabilistically: a trim the
cap would forgive is forgiven with probability `P` and repaired otherwise,
with a fresh draw on every trimmed arrival so a range refused once has
another chance on its next trim. Coin refusals charge nothing and set no
bit.

Under vesting the coin does not move time. At `P = 0.25` it reads 15.8 to
16.9 % against 16.1 to 16.7 % without it, for 5.5 % of bytes instead of
7.55 %, and on the healthy fabric 5.8 to 6.7 % for 0.27 to 0.42 % against
4.5 to 7.5 % for 1.0 to 1.3 %. The coin is a loss dial at no time cost.
Its time effect in our earlier rounds belonged to a revocation rule since
replaced: when a spent pool ended the licence for good, slowing the spend
was what kept the licence, and vesting now does that by construction.
Measured against the up-front cap, the coin recovers 5 of the 6 to 7
points that vesting recovers, which is the same mechanism seen from the
other side.

### 2.6 The wire and the receiver

Nothing new travels on the data path. Two flag bits on the existing
acknowledgement and repair request carry "budget gone" and "this flow may
be exempt". The receiver needs its own counters of received and forgiven
bytes per step, each flow's size (on the message descriptor), which step
a flow belongs to and whether the step is critical (one tag per collective
and one bit per step from the training side), and what each sender owes
it this step (the collective library's plan). The sender needs nothing; it
obeys two bits and computes nothing about the budget.

### 2.7 What the application does

Stated as assumptions, not built. The receiver hands the application, with
each completed message, the list of forgiven ranges. In the reduce-scatter
the application divides each element by the number of contributions that
arrived; in the all-gather it fills a missing element with its own local
gradient for that element, scaled the same way; and it may re-synchronise
parameters every K steps over a lossless transfer, which under tensor
parallelism of 8 costs about 17.5 GB per rank, four of our steps, 0.4 % of
time at K = 1000. With these, the pooled per-rank budget is sound for
i.i.d. shards: only the aggregate loss decides where training converges
and which sender lost is a variance term. Our May prototype did none of
the three, filled missing chunks with zero, and converged at 40 % loss on
non-critical steps on GPT-2; that is the tolerance evidence and its
conservative bound. Nothing in a network simulator can test it; the
injection experiment in section 5 is where it stops being an assumption.

## 3. Evaluation

### 3.1 Setup

**Simulator.** ASTRA-sim 2.0 drives the workload and the collective
schedule; a forked ns-3 RDMA back end (BTreeMap/astra-network-ns3,
branch `astra-sim`) moves the packets. The simulator computes no
gradient values; it moves bytes, so nothing in this section speaks to
model accuracy.

**Workload.** A Llama 3 70B-shaped gradient microbenchmark: 70 B
parameters in 2-byte precision, 80 layers, hidden size 8 192, sequence
4 096, tensor parallelism 8, pipeline 1, data parallelism 8, 64 ranks,
20 training steps, 5.4 ms of compute per node overlapped with the
communication window. Each step every rank runs a data-parallel all-reduce
of one 68 359 375-byte gradient bucket (the 256-bucket gradient sharded
eight ways) with its seven data-parallel peers, and two 64 MiB
tensor-parallel all-reduces per layer with the seven ranks of its
tensor-parallel group. ASTRA-sim's `direct7` all-reduce sends each
peer five streams of 17 089 843 bytes, each a reduce-scatter and an
all-gather phase, so a rank receives 70 data-parallel flows of
2 136 230 bytes (522 packets) per step and is owed 149 536 100 bytes per
step in all; the run offers 191.4 GB of data-parallel and 793.6 GB of
total payload.

**Topology and where the traffic goes.** A two-tier Clos: 8 hosts per
leaf at 400 Gbps, 4 spines by design (2:1 leaf-to-spine), 32 MB switch
buffers, PFC off. A tensor-parallel group is the 8 hosts of one leaf, so
tensor-parallel traffic stays on the leaf (a simplification: real
tensor-parallel traffic rides a scale-up domain). Data-parallel peers
are the same-position hosts on the other seven leaves, so every
data-parallel flow crosses a spine. The worst cell fails two of the four
spines (4:1), the healthy cell has eight (1:1); oversubscription here is
only that ratio.

**Where the incast is.** Under `direct7` all seven peers send to a rank
at once, so seven 400 Gbps senders converge on one 400 Gbps host link.
That last-hop incast exists at every spine ratio; the spine ratio adds a
second congestion point on the leaf-to-spine uplinks at 2:1 and 4:1.
The trim ratio without a controller, measured one seed per cell, is a
steady-state property of provisioning rather than of any burst: 2.4 % at
`direct2` 2:1, 6.3 % at `direct7` 2:1, 12.9 % at `direct2` 4:1, 24.1 %
at `direct7` 4:1, and identical over steps 1 to 17 and over the whole
run. Fan-in 2 to 7 multiplies it by about 2.7 and oversubscription 2:1
to 4:1 by about 5.5.

**The microburst.** Every run fires seven background RDMA flows of
128 MiB each at one downlink rank (rank 8) at step 18, with no offset
between them. Under selective repair this burst is a non-event: the
data-parallel span of steps 18 and 19 exceeds the median of steps 4 to
17 by 0.04 to 0.62 % of the window in every cell of the map, and the
burst drains in 30 to 37 ms without a controller and 63 to 146 ms under
DCQCN, which throttles the burst senders. Under go-back-N the same burst
cost 205 to 935 ms of data-parallel span in run #117. The stressor is
kept for comparability with that run; no FORGIVE result depends on it,
and the forgiven bytes spread 5 to 7 % per permissive step with step 18
not dominant.

**Transport.** RDMA-style flows, one queue pair per message, 4 096-byte
payload packets. The switch trims under congestion (UEC 1.0.3 style
"forward trimmed data": the payload is dropped, the header forwarded in
a class capped at 25 % of the link, trimmed-header queue 1 MiB against a
4 MiB data queue). The receiver repairs selectively (a NACK per trimmed
packet, retransmission of that packet only), with a 1 ms retransmission
timeout and no exponential backoff. The go-back-N variant, in which a
NACK rewinds the sender's window, is the transport of run #117 and of
our May setting.

**Congestion control.** DCQCN at every sender, as configured in the
repository: ECN marking at 400 Gbps between 800 KB and 3.2 MB of queue
with marking probability 0.2, EWMA gain 1/256, rate-decrease interval 4,
alpha-resume interval 1, and additive-increase constants
(`RATE_AI`, `RATE_HAI`, `MIN_RATE`) that are 100 Gbps-era literals not
rescaled to 400 Gbps. No tuning sweep has been run, so every DCQCN figure
is "DCQCN as configured". The no-controller arms run the same transport
with the controller off. No other controller is implemented.

**Load balancing.** Per-flow ECMP across spines; no per-packet spraying.
With seven data-parallel flows per rank and step, ECMP collisions on the
uplinks are one source of seed-to-seed variance.

**Seeds.** Three seeds, 9550582, 23172535 and 94081284, on every
FORGIVE arm; the zero-tolerance reference has five on the worst cell; run
#117 has sixteen. A seed sets the ECMP hashing and the shedding
selection stream; arms in one comparison share it, so their windows can
be subtracted.

### 3.1b Metrics

- **Training window (makespan).** Completion time of the last rank over
  the 20 steps; every "time recovered" is the paired difference against
  the fixed-low control on the same seed, as a share of the control.
- **Loss.** Forgiven bytes (less forgiven bytes that arrived late and
  were dropped) as a share of the 191.4 GB of data-parallel all-reduce
  bytes; for sender-side shedding, the bytes suppressed before the
  fabric.
- **Trim ratio W** (trimmed payload bytes over offered bytes) and
  **re-sent bytes** (retransmitted bytes over the 793.6 GB offered),
  which price what an arm costs the fabric.
- **Per-step data-parallel span**: for each step, the latest end minus
  the earliest start of the step's all-reduce over the 64 ranks; its
  excess at the burst steps over the median steady step is the tail
  metric of the regime map.
- **Worst all-reduce of the window**, in milliseconds, is the tail
  figure quoted for run #117 (1026 to 873 ms, 153 ms saved, CI 5 to
  302 ms over 16 seeds). Per-rank p99 completion time is not quoted
  anywhere: over the same 16 seeds it reads -4.9 % with a confidence
  interval from -19.6 to +9.8 %, because it is the top three of 320
  samples and one ECMP collision moves it by half.
- **Tensor-parallel collective time** against the control, to show the
  exempt senders do not slow the traffic that shares their leaf.
- **Certification**: per (rank, step) delivered share, worst cell named;
  every FORGIVE arm must read at least `1 - p`.

### 3.1c The arms, by name

| name in this section | also called | what it does |
| --- | --- | --- |
| control, fixed-low baseline | raw DCQCN, tight baseline | DCQCN, `p_low = 0.005` every step; sheds 0.5 % of DP bytes at the sender |
| zero tolerance | raw DCQCN, strict | DCQCN, no shedding and no forgiveness; within -1.1 to +0.8 % of the control on the worst cell over 5 seeds |
| loose baseline | fixed tolerance | DCQCN, `p_high` on every step, sender-side shedding; the unmasked reference |
| sender-side shedding | dynamic tolerance, phase-aware shedding, our May mechanism | DCQCN, `p_low` on critical steps and `p_high` elsewhere, bytes suppressed at the sender before the fabric |
| forgive, obey the controller | | receiver-side forgiveness under the budget, no licence |
| FORGIVE | | receiver-side forgiveness, vesting, the licence |
| no controller | | the same transport with the controller off |
| never re-engage (D) | | FORGIVE with the licence never withdrawn |

The four-arm comparison in Zechen's terms, worst cell, budget 0.4, three
seeds (run #123):

| arm | training window | all-reduce, non-critical steps | all-reduce, critical steps | gradient lost | re-sent |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw DCQCN (control) | 1697 to 1701 ms | 36 to 37 ms | 36 to 37 ms | 0.5 % | 3.5 to 3.7 % |
| fixed tolerance (loose baseline, 0.4) | 1444 to 1477 ms | 23 to 25 ms | 22 to 26 ms | 40 % | 1.5 to 1.6 % |
| dynamic tolerance (phase-aware shedding, 0.4) | 1491 to 1519 ms | 25 to 26 ms | 35 to 37 ms | 32 % | 2.1 % |
| FORGIVE, 0.4 | 1340 to 1360 ms | 12 to 13 ms | 34 to 36 ms | 21.3 to 21.5 % | 2.7 to 3.0 % |

FORGIVE's critical steps stay within 2.4 ms of the control's while the
loose baseline's speed up by a third, which is the safety property in one
row; the same cell without a controller runs in 1367 ms (one seed), so the
controller's bill here is about 330 ms and FORGIVE at 0.4 returns nearly
all of it.

### 3.2 The headline

Worst cell, budget 0.1, the design of section 2 without the coin, three
seeds against controls of 1696.7, 1696.9 and 1700.6 ms:

| seed | training time recovered | loss, % of DP bytes | re-sent bytes | TP collective time vs control |
| ---: | ---: | ---: | ---: | ---: |
| 9550582 | 16.66 % | 7.55 % | 5.88 % | -4.3 % |
| 23172535 | 16.06 % | 7.57 % | 5.61 % | +4.4 % |
| 94081284 | 16.66 % | 7.56 % | 5.22 % | -1.3 % |

The tensor-parallel collectives, which share the leaf with the exempt
senders and obey the controller throughout, are never slower than in the
control beyond the seed spread. The critical steps forgive 1.4 % of the
forgiven bytes at this budget, and at budget 0.4 their all-reduce time
stays within 2.4 ms of the control's while the loose baseline's speeds up
by a third (both measured on the earlier rule set, whose mask is
unchanged).

### 3.3 What the deltas are against

Three references on the same seeds and cell, budget 0.1 where a budget
applies:

| reference | training time recovered | what it pays |
| --- | ---: | --- |
| zero tolerance | -1.1 to +0.8 % (5 seeds) | nothing |
| forgive but obey the controller | 5.5 to 6.6 % | 6.8 to 7.0 % of DP bytes, 1.7 to 1.9 % re-sent |
| no controller at all | 20.1 to 20.3 % | 25.4 % of all bytes re-sent, 93 timeouts against the control's 10 042 to 10 622 |
| never return to the controller (licence never ends) | 18.7 to 19.0 % | 7.6 % of DP bytes, 6.5 to 6.8 % re-sent |

The controller's whole bill on this cell is about 20 %; the licence
recovers 16 of it while the fabric keeps its controller, and re-sends a
quarter of what the no-controller arm does. Forgiveness alone, under the
controller, is worth 6 points, through the load it removes; the licence
roughly triples it. The last 3 points to the never-return arm are the
interruptions of the licence and the one round trip each flow spends
obeying at its start.

### 3.4 Which piece earns the time

Worst cell, budget 0.1, three seeds each, seed ranges:

| arm | training time recovered | loss | re-sent |
| --- | ---: | ---: | ---: |
| vesting, no coin (section 3.2) | 16.1 to 16.7 % | 7.55 to 7.57 % | 5.2 to 5.9 % |
| vesting with the coin at 0.25 | 15.8 to 16.9 % | 5.5 to 5.6 % | 6.5 to 6.6 % |
| budget available in full from the first byte, no coin | 9.1 to 10.2 % | 7.9 to 8.1 % | 1.9 to 2.1 % |
| budget in full from the first byte, coin at 0.25 | 14.6 to 15.3 % | 6.2 to 6.4 % | 6.0 to 6.3 % |
| vesting with a per-sender stop at `1 - p` | 15.8 to 16.6 % | 8.10 % | 5.5 to 5.8 % |

Vesting earns the time. The up-front budget is spent in the first part of
the step, forgiven bytes never fall, the report stays red and the sender
obeys the controller for the rest of the step; its low re-send figure is
the signature of a sender under rate cuts. The coin under vesting changes
loss and not time. A stop that ends a sender once `1 - p` of its share
has arrived, charging the rest to the budget, spends every cell to its cap
and recovers nothing, so it is not part of the design.

Where the vested cap spends its budget within a step is measurable. On
seed 9550582, bucketing data-parallel flows by where they start in their
receiver's step window, the cap forgives 18 % of the trimmed bytes that
arrive in the first fifth of a step and 60 % of those in the last fifth;
the first fifth is also where the most trimming happens. The line through
the origin is biased toward the end of the step. Under the coin the
shares are 65 % to 100 %, because at a quarter of the spend rate the cap
binds only at the opening. Whether the bias costs anything is an open
question (section 5): forgiving early converts a hole that would drain
when its repair lands into spend that never does.

### 3.5 The coin as a loss dial

Under vesting the coin at 0.25 reads the same time as no coin for two
points less loss (section 3.4). Below 0.25 the coin was measured only
under the earlier rule set (a sticky coin, a one-way revocation and no
licence on critical steps), where it read 15.3 to 16.7 % for 2.6 to 2.9 %
at `P = 0.1` and 15.0 to 16.6 % for 1.2 to 1.3 % at `P = 0.05`, the
latter inside the 0.7 to 3.3 % band MLT profiles as tolerable. Those two
points are not yet re-measured under vesting and are quoted here as the
trend, not the result. The arm at `P = 0`, which forgives nothing and
keeps the licence, decides whether forgiveness buys any time at all on
this fabric or whether the tolerance is purely the bound on the licence.

### 3.6 The budget as a dial

The earlier rule set ran the front of budgets on the worst cell, against
sender-side shedding at the same budgets, which is our May prototype's
mechanism re-implemented in the simulator (the sender discards a hashed
share of its eligible bytes before they enter the fabric). Seed ranges:

| budget | FORGIVE time | FORGIVE loss | shedding time | shedding loss |
| ---: | --- | --- | --- | --- |
| 0.05 | 8.0 to 8.6 % | 3.7 to 3.8 % | 0.1 to 1.3 % | 4.1 % |
| 0.1 | 12.9 to 14.1 % | 6.75 to 6.89 % | 2.4 to 3.3 % | 7.7 % |
| 0.2 | 16.0 to 16.7 % | 11.1 to 12.2 % | 4.9 to 5.5 % | 15.7 % |
| 0.4 | 19.6 to 21.0 % | 21.3 to 21.8 % | 11.0 to 11.8 % | 31.5 % |
| 0.6 | 23.7 to 24.3 % | 37.7 to 38.6 % | 16.0 to 16.4 % | 47.9 % |
| 0.4, mask off | 25.3 to 25.6 % | 25.6 to 26.0 % | 13.2 to 14.9 % | 39.8 % |

Time recovered per point of gradient lost falls from 2.1 to 2.3 at budget
0.05 and 1.9 to 2.1 at 0.1 to 0.6 at 0.6 for FORGIVE while shedding stays
at 0.3 to 0.4; the two are furthest apart at the smallest budget. Shedding discards
exactly its cap; FORGIVE spends 67 to 84 % of the same cap and the loss
is congestion-proportional. Shedding cannot relieve a controlled fabric:
peak queue occupancy is identical in the two arms, because removing bytes
from all seven senders never removes a sender, and the controller reacts
to the incast either way. The mask, protecting steps 1, 2, 3 and 20 at
`p_low`, costs 5.1 points of time and 4.4 points of loss at budget 0.4,
and the ledger shows 1.0 to 1.5 % of forgiven bytes on the protected
steps against 19 to 21 % without it. These points are the v1 rule set;
under vesting the point at 0.1 moves from 12.9 to 14.1 % to 16.1 to
16.7 %, and the rest of the front has not been re-run.

### 3.7 Across fabrics

| cell | control window | control trim ratio | FORGIVE, budget 0.1 | loss | rules |
| --- | ---: | ---: | ---: | ---: | --- |
| `direct7` at 4:1, DCQCN (worst) | 1697 to 1701 ms | 3.5 to 3.7 % re-sent | 16.1 to 16.7 % | 7.55 % | vesting |
| `direct2` at 2:1, DCQCN (ring-like) | about 1410 to 1420 ms | | 10.5 to 12.5 % | 2.37 to 2.50 % | v1 |
| `direct7` at 1:1, DCQCN (healthy) | 1248 to 1260 ms | 0.02 to 0.04 % of bytes trimmed | 4.5 to 7.5 % | 1.0 to 1.3 % | vesting |
| `direct7` at 1:1, with the coin at 0.25 | | | 5.8 to 6.7 % | 0.27 to 0.42 % | vesting |
| 16 ranks, go-back-N, no controller | 7145 ms | | 3.9 % (sender-side shedding, 16 seeds) | 10 % cap | May mechanism |

The regime map (run #120, one seed per cell, fixed-low arm, selective
repair) is the frame for the table:

| cell | window | trim ratio W | DP flows trimmed | step 18 + 19 excess, % of window |
| --- | ---: | ---: | ---: | ---: |
| no controller, `direct2`, 2:1 | 1201 ms | 0.024 | 24 % | 0.08 |
| no controller, `direct7`, 2:1 | 1200 ms | 0.063 | 53 % | 0.04 |
| no controller, `direct2`, 4:1 | 1373 ms | 0.129 | 58 % | 0.62 |
| no controller, `direct7`, 4:1 | 1367 ms | 0.241 | 75 % | 0.55 |
| DCQCN, `direct2`, 2:1 | 1421 ms | 0.002 | 7 % | 0.23 |
| DCQCN, `direct7`, 2:1 | 1422 ms | | | 0.34 |
| DCQCN, `direct2`, 4:1 | 1719 ms | | | 0.60 |
| DCQCN, `direct7`, 4:1 | 1696 ms | | | 0.10 |

DCQCN divides the trim ratio by 8 to 10 and lengthens the window by 18
to 24 % in every column; the burst steps never exceed a steady step by
1 % of the window anywhere. On the go-back-N fabric of run #117 (16
ranks, no controller, 16 matched seeds) phase-aware shedding at budget
0.1 shortened the window from 7145 to 6854 ms (3.91 %, CI 1.13 to
6.68 %), the worst all-reduce of the window from 1026 to 873 ms (CI 5 to
302 ms), and the relief correlated 0.93 with trims avoided at 11.9 ms per
million and -0.01 with bytes discarded; the loose baseline recovered
9.42 % (CI 7.03 to 11.82 %) for 40 % loss. That relief is repair
amplification under go-back-N, and the same policy recovers 0.78 % under
selective repeat.

The healthy cell answers the question the worst cell raises. With four
spines per leaf the fabric is not oversubscribed and the control trims
0.02 to 0.04 % of bytes, so the pre-registered kill test ("if the 1:1
control's trim ratio is below 0.5 % and FORGIVE recovers under 2 points,
the claim is scoped to degraded fabrics") did not fire: FORGIVE recovers
4.5 to 7.5 % for 1.0 to 1.3 % of bytes, and the coin 5.8 to 6.7 % for
0.27 to 0.42 %. The reason is that the incast is at the last hop. Seven
senders at 400 Gbps into one 400 Gbps receiver link is a 7:1 incast
whatever the spine ratio, DCQCN reacts to it with rate cuts on every
step, and the exempt senders trim ten times more than the control
(0.27 to 0.34 % of bytes) and still complete sooner. Sender-side shedding
recovers 0.1 to 0.3 % on the same cell and the loose baseline -0.4 to
+0.7 %. On the go-back-N fabric of our May setting the tail exists and
sender-side shedding alone recovers 3.9 % over 16 seeds; FORGIVE has not
been run there.

## 4. Prior work

The composition, mechanism by mechanism, with its origin:

| mechanism | origin | relation |
| --- | --- | --- |
| a receiver that tolerates a bounded share of lost gradient bytes | MLT (Wang et al., NSDI 2024), DLCP (2020) | tweaked: per trimmed range as the switch reports it, not one stop per tensor at the end |
| a tolerance that changes with the training phase | our May preprint, Accordion (MLSys 2021), critical learning periods (ICLR 2019) | as-is |
| a per-(rank, step) budget in bytes, vested with delivery | no cited origin | new |
| loss accepted from a trimming switch without retransmission | trimmable gradients (Chen, Vargaftik, Ben Basat, HotNets 2024) | tweaked: bounded by the budget, repaired otherwise |
| a flow allowed a weaker congestion response by class | D3, D2TCP, PDQ, Karuna, pFabric | transferred: per flow, bounded by a receiver's budget, ended and restored by the receiver's report |
| declared partial reliability | PR-SCTP, QUIC DATAGRAM, Ultra Ethernet's unreliable mode | as-is in spirit; the mode is chosen per range at the receiver, not per stream at setup |

In one line: MLT's bounded-loss receiver (per range) + our May phase mask
(as-is) + a vested byte budget per rank and step (new) + a per-flow
congestion-control exemption bounded by that budget (transferred from
deadline-aware controllers, with revocation and restoration added). The
patterns it fits are composition and transfer, and what it has to show is
that the whole beats each origin alone on a fabric the field runs now,
which is what section 3.3 measures against.

What the nearest systems do and do not have. MLT stops a tensor once
`1 - p` has arrived and loses whichever bytes arrive last, keeps one bound
per model for all of training, and weakens rate control globally because
loss is tolerated; its tolerated fractions at equal rounds are 0.7 to
3.3 % across sixteen CNN and RNN models, 10 % at a quality target. LTP
closes rounds early with an adaptive threshold in a parameter-server
setting. OptiReduce bounds each stage by a timeout and makes the loss
harmless with a Hadamard mixing, on TCP in the cloud. Trimmable gradients
lay packets out so a trimmed packet is a compressed gradient, with no
bound and no retransmission, and its authors ask for a congestion control
that over-sends and lets the switch trim the excess, which is what the
licence does with a budget that paper does not have. None decides per
trimmed range at the time the switch rejects it, none keeps a budget in
bytes per rank and step, and none exempts an RDMA flow from its
controller's own signal under a receiver's budget and restores the
controller on the receiver's word; those three are the claim.

Two findings reframe those systems on a modern fabric. The tail they
shorten is not there under trimming with selective repair (section 1),
and what a bounded loss can buy back instead is the controller's
reaction, which is 18 to 24 % of the window under DCQCN and about 6 % on
a fabric that is not oversubscribed.

The budget rule itself is an instance of a problem the online-allocation
literature states as a theorem: a fixed supply spent irrevocably on
arrivals whose total is unknown. Sinclair, Jain, Banerjee and Yu prove
that fairness across arrivals and full spend trade off, Manshadi,
Niazadeh and Rodilitz give the near-optimal proportional policy, and
Balseiro, Lu and Mirrokni the dual-price form. Our line through the
origin is none of these; it funds the first arrival at zero and the last
at the full remaining budget, and the appendix to our budget-shape review
records the mapping. What that literature cannot price is the licence:
in every one of those problems the good has the same value whenever it is
granted, and ours does not, because a forgiven byte never drains while a
hole does.

## 5. What this section does not show

- **Tolerance.** The simulator moves bytes and has no gradient; every
  statement about training surviving the loss rests on our May GPT-2
  runs at 40 % with zero-fill, on MLT's 0.7 to 3.3 % at equal rounds,
  and on Weintraub, Banner and Orda's Llama 2 7B at 10 % i.i.d. loss for
  1.17 % worse perplexity. The headline's 7.55 % is above MLT's band and
  inside Weintraub's; the coin at a small `P` would put it inside MLT's
  band at no time cost. No paper measures loss that is bursty and
  correlated across senders, which is what a trimming fabric produces,
  and the theory says the pooled budget is sound only with the rescaling
  of section 2.7. The instrument is an injection experiment: export the
  forgiven ranges, zero or rescale those elements in a DDP hook, and
  train a GPT-2-class model against an unmodified run, with even against
  uneven loss at equal aggregate as one of its arms.
- **One controller, as configured.** DCQCN's bill is quoted as measured
  with the repository's parameters; no tuning sweep separates its
  inherent cost from its defaults, and no paper does either. Meta runs
  its 400 Gbps training fabric with DCQCN off; where there is no
  controller, the licence has nothing to act on and only the load channel
  remains.
- **Three seeds, one workload, per-flow ECMP.** No packet spraying, no
  NSCC, no second workload, no multi-tenant fairness measurement; the
  objection Floyd and Fall raise against unresponsive flows is answered
  only by the bound and the receiver's report, and a two-tenant
  experiment is the instrument.
- **Whether forgiveness buys time at all on this fabric.** Under vesting
  the marginal time of a forgiven byte measured zero between 7.55 % and
  5.5 % loss. The arm at `P = 0` decides whether the tolerance is a
  currency or purely the bound on the licence; if the latter, the design
  loses nothing and the paper's claim sharpens.
- **The shape of the vested line.** It is biased toward the end of the
  step (section 3.4). Candidate shapes exist (a burst-sized initial
  allowance, a concave release, crediting outstanding holes, a spend gated
  on the fabric's current trim rate) and none is measured; the objective
  for choosing among them is time per byte lost with the prefix bound
  kept as a constraint, not fairness across arrivals.
- **Scale.** 64 ranks with tensor parallelism on the leaf; the ranks are
  modelled as NICs, and tensor-parallel traffic rides the leaf rather than
  a scale-up domain. Pipeline parallelism is not simulated.

## 6. Figures and data in hand

Drawn, in `docs/agents/figures/`: `regime-map.svg` (the eight cells),
`run117-paired-seeds.svg` and `run117-mechanism.svg` (the go-back-N
result and its correlation with trims avoided), `recovery-amplification.svg`
(go-back-N against selective repeat), `dose-front.svg` (the v1 budget
front, needs the vesting point added), `rate-versus-volume.svg` (why
sender-side shedding cannot relieve a controlled fabric),
`forgive-mechanism.svg` (the protocol diagram, needs the licence and the
holes rule), `progress-timeline.svg`.

Tabulated and not yet drawn, with the per-seed rows in
`docs/agents/figure-data.md`: the design-of-record ablation (section 13
there), the three references (12), the coin front (11), the mask's cost
and integrity (8), the exemption counters across the front (10), the
healthy cell (15), and the front-bias split by fifth of the step (in
`headline-is-vesting` and section 3.4 above). Every figure recomputes
from a release bundle named in section 7.

## 7. Provenance

| number | run | code | arms |
| --- | --- | --- | --- |
| the regime map (section 1) | #120, 2026-09-06 | map-only rerun 34055188995 | 8 single cells, one seed |
| the v1 front, the mask, the mild cell (3.6, 3.7) | #123, 2026-09-14 | main c6855f0, ns-3 9717200cc | 21 records, 84 arms, all certified |
| the coin below 0.25 and budget 0.05 (3.5, 3.6) | #125, 2026-09-16 | main 8213401 | 24 arms, all certified, earlier rule set |
| the references (3.3) | #126, 2026-09-16 | main a1b30b0 | 15 arms, all certified |
| the design of record and its ablations (3.2, 3.4) | #127, 2026-09-17 | main 59cf16c, ns-3 3e11ace49 | 21 arms, all certified, worst cell 0.900 to 0.909 |
| the healthy cell (3.7) | #130, 2026-09-17 | main 65e98e7 | 18 arms; FORGIVE and coin arms certified locally, worst cell 0.916 to 0.948 and 0.983 to 0.984 |
| go-back-N (3.7) | #117, 2026-09-03 | go-back-N era | 16 matched seeds |

Every FORGIVE arm was re-analysed with the committed analyzer against its
own bundle; the analyzer fails an arm whose ledger breaks the bound.
