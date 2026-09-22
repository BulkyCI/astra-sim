# FORGIVE: receiver-budgeted forgiveness with a bounded congestion-control exemption

Draft section for the revision of our May preprint (arXiv 2605.01989).
Every number below comes from a verified run named in section 7, and
every number that was measured under a rule since replaced says so where
it appears. The vesting version is the design; Bernoulli pacing is the
secondary result.

## 1. The observation

Our May prototype tolerated a bounded share of lost gradient bytes on the
steps where training could afford it and recovered training time by
avoiding the retransmission round trips a lossless transport incurs on the
tail of every collective. That prototype ran over UDP with a bitmap probe
and a stop message, and its speedup was the retransmission tail.

A modern training fabric does not have that tail. On a switch that trims a
congested packet to its header and forwards the header, a receiver learns
of every loss within one fabric transit and asks for exactly the missing
packet, so the retransmission costs one round trip rather than a timeout.
The configuration sweep measured that tail. Across eight configurations
(with and without congestion control, fan-in 2 and 7, oversubscription 2:1
and 4:1, 64 ranks), the excess of the two burst steps over a steady step
was 0.04 to 0.62 % of the training time in every configuration, against a
kill line of 5 %. The retransmission-driven tail that MLT, LTP and
OptiReduce shorten is already gone on such a fabric.

Congestion control's rate reduction remains. DCQCN divides the trim ratio
by 8 to 10 on the same sweep and lengthens the training time by 18 to
25 %, through millions of rate cuts and thousands of retransmission
timeouts. The time a lossy transport can recover on a trimming fabric is
that rate reduction, and FORGIVE recovers it by using a bounded loss
tolerance to make turning congestion control off safe.

A receiver that is willing to lose at most a fraction `p` of what it is
owed in a step can exempt its senders from reacting to congestion signals
for as long as the fabric has not already lost more than that tolerance
could absorb. The tolerance is the safety bound on the exemption. The
receiver consumes the tolerance by forgiving a trimmed range, which means
that the receiver declines retransmission of the range and acknowledges it
as delivered. On the most congested configuration, at `p = 0.1`, the
exemption reduces training time by 16.1 to 16.7 % for 7.55 % of the
data-parallel bytes, against a ceiling of 20.1 to 20.3 % with no
congestion control, which retransmits 25.4 % of every byte. On the
non-oversubscribed 1:1 fabric it reduces training time by 4.5 to 7.5 % for
1.0 to 1.3 %. The total time lost to congestion control there has not been
measured.

## 2. Design

### 2.1 Setting

The fabric trims packets under congestion (the payload is dropped and the
header is forwarded), the transport retransmits selectively, and
congestion control runs at every sender. FORGIVE treats the congestion
control algorithm as a black box. FORGIVE changes no line inside the
algorithm and decides only whether the sender hands a congestion signal to
it. The evaluation uses DCQCN because our fabric runs it. Nothing below
depends on which algorithm it is.

The job is data-parallel training. Each step, every rank all-reduces its
gradient with the other ranks of its group, as a reduce-scatter followed
by an all-gather. Only that traffic is ever forgiven or exempted; tensor-
parallel, pipeline and control traffic is delivered in full under
congestion control. The collective library knows at the start of a step
how many bytes each peer will send to each rank; the receiver needs that
table and nothing else about the workload. The training side names the
steps on which loss is not affordable. The evaluation uses steps 1, 2, 3
and 20 of a 20-step run.

### 2.2 The budget

Each receiving rank keeps one loss budget per training step, shared by
every sender into it. The budget is `p x owed`, where `owed` is the sum of
what the rank's peers will send it that step, and `p` is `p_low` (0.005)
on a critical step and `p_high` (0.1 in the headline) elsewhere. The
receiver counts a byte it declines to have retransmitted against the
budget and never returns it.

The guarantee is that every rank received at least `1 - p` of what it was
owed. The simulator asserts it at every step's last collective and the
analyzer recomputes it from the telemetry after the run. A run that breaks
it fails either check.

### 2.3 Vesting

The receiver releases the loss budget in proportion to bytes delivered
(vesting), so the whole budget is not available at once. The receiver may
forgive a trimmed range only while

```
forgiven + range <= p x (received + forgiven + range),
```

equivalently `forgiven + range <= p/(1-p) x received`, with the range
under decision counted on both sides. At every prefix of the step, of the
bytes the receiver has accepted or is about to forgive, at most `p` are
forgiven. The cap is a line through the origin in received-bytes space
that reaches `p x owed` exactly when `1 - p` of the step has arrived. The
cap needs two per-step counters, received and forgiven bytes, and it
satisfies the hard bound by construction under any trim profile the fabric
produces.

If the whole budget is available from the first byte, the opening incast
of a step consumes it in the first fifth, forgiven bytes never fall, and
the exemption of section 2.4 ends for the rest of the step. That
configuration reduces training time by 9.1 to 10.2 % against vesting's
16.1 to 16.7 % on the same seeds (section 3.4). Vesting keeps the
exemption in force by construction, because the cap reaches the line only
when the step is nearly complete.

The ordinary path retransmits a trimmed range that the cap refuses, and
the receiver decides afresh if the range is trimmed again. Every
acknowledgement of a forgiven range includes the congestion mark the trim
would have produced, so forgiving hides no congestion from a sender that
is still reacting to congestion signals.

### 2.4 The congestion-control exemption

The exemption, by which the receiver frees a sender from reacting to
congestion signals, uses two flags. The receiver decides once, when a
flow's receive queue pair is created, whether the flow is
exemption-eligible (data-parallel all-reduce payload on a step with
`p > 0`), and every acknowledgement of that flow includes that flag. Every
acknowledgement also includes a second flag, the budget-exhausted flag,
which says whether the step's tolerance is exhausted:

```
exhausted  <=>  forgiven + outstanding + one packet > p x owed,
```

where `outstanding` counts the outstanding trimmed bytes, the bytes
trimmed and not yet retransmitted or forgiven: those below the highest
sequence the receiver has seen on its open flows that are neither received
nor forgiven. The inequality holds when the step's tolerance would be
exceeded even if the receiver forgave every byte now missing. Outstanding
trimmed bytes count each missing byte once and fall as retransmissions
arrive, so the flag clears on its own when the fabric recovers.

A sender runs congestion control normally until the first acknowledgement
arrives with the exemption-eligible flag set and the budget-exhausted flag
clear. From then on the sender withholds every congestion signal from the
congestion control algorithm. A later acknowledgement with the
budget-exhausted flag set makes the sender deliver signals again, and one
with that flag clear lets the sender withhold again. The design has no
latch and no hysteresis. The sender is exempt exactly when the last
acknowledgement it saw said so. A congestion control algorithm that
receives no signal raises its own rate on its own timers, and FORGIVE
changes nothing inside it. A critical step runs the same rules with
`p_low`. Its loss budget is exhausted after about three quarters of a
megabyte, and congestion control resumes almost at once.

The exemption is the mechanism that recovers time. Forgiveness under
congestion control, with no exemption, reduces training time by 5.5 to
6.6 % on the most congested configuration for 6.8 to 6.9 % of bytes
(section 3.3); the exemption brings that reduction to 16 % for 7.55 %.

### 2.5 Bernoulli pacing

Bernoulli pacing, which is probabilistic forgiveness with probability `P`,
consumes the budget gradually. A trim the cap would forgive is forgiven
with probability `P` and retransmitted otherwise, with a fresh draw on
every trimmed arrival so a range refused once has another chance on its
next trim. A pacing refusal consumes no budget; the refused range stays
outstanding until its retransmission arrives, as a cap refusal does, so it
counts in the budget-exhausted rule like any other missing byte.

Under vesting, pacing does not move training time. At P = 0.25 it reads
15.8 to 16.9 % against 16.1 to 16.7 % without it, for 5.5 % of bytes
instead of 7.55 %, and on the non-oversubscribed configuration 5.8 to
6.7 % for 0.27 to 0.42 % against 4.5 to 7.5 % for 1.0 to 1.3 %. Pacing is
a loss dial at no cost in training time. Its effect on training time in
our earlier rounds belonged to a revocation rule since replaced. Under
that rule an exhausted loss budget ended the exemption for good, so
slowing the consumption kept the exemption, and vesting now keeps it by
construction. Measured against the budget available in full at step start,
pacing recovers 5.1 to 5.5 of the 5.9 to 7.6 points that vesting recovers.

### 2.6 The wire and the receiver

Nothing new travels on the data path. Two flag bits on the existing
acknowledgement and retransmission request encode "budget exhausted" and
"this flow may be exempt". The receiver needs its own counters of received
and forgiven bytes per step, each flow's size (on the message descriptor),
which step a flow belongs to and whether the step is critical (one tag per
collective and one bit per step from the training side), and what each
sender owes it this step (the collective library's plan). The sender needs
nothing. The sender acts on two flag bits and computes nothing about the
budget.

### 2.7 What the application does

This subsection states assumptions, and none of what it describes is
built. The receiver hands the application, with each completed message,
the list of forgiven ranges. In the reduce-scatter the application divides
each element by the number of contributions that arrived; in the
all-gather it fills a missing element with its own local gradient for that
element, scaled the same way; and it may re-synchronise parameters every K
steps over a lossless transfer, which under tensor parallelism of 8 costs
about 17.5 GB per rank, four of our steps, 0.4 % of training time at K =
1000. With these, the pooled per-rank budget is sound for i.i.d. shards,
because only the aggregate loss decides where training converges and which
sender lost is a variance term. Our May prototype did none of the three,
filled missing chunks with zero, and converged at 40 % loss on
non-critical steps on GPT-2. That is the tolerance evidence and its
conservative bound. Nothing in a network simulator can test it, and the
injection experiment in section 5 is the test.

## 3. Evaluation

### 3.1 Setup

**Simulator.** ASTRA-sim 2.0 drives the workload and the collective
schedule; a forked ns-3 RDMA back end (BTreeMap/astra-network-ns3, branch
`astra-sim`) moves the packets. The simulator computes no gradient values
and only moves bytes, so nothing in this section measures model accuracy.

**Workload.** A Llama 3 70B-shaped gradient microbenchmark: 70 B
parameters in 2-byte precision, 80 layers, hidden size 8 192, sequence
4 096, tensor parallelism 8, pipeline 1, data parallelism 8, 64 ranks, 20
training steps, 5.4 ms of compute per node overlapped with the
communication phase. Each step every rank runs a data-parallel all-reduce
of one 68 359 375-byte gradient bucket (the 256-bucket gradient sharded
eight ways) with its seven data-parallel peers, and two 64 MiB
tensor-parallel all-reduces per layer with the seven ranks of its
tensor-parallel group. ASTRA-sim's `direct7` all-reduce sends each peer
five streams of 17 089 843 bytes, each a reduce-scatter and an all-gather
phase, so a rank receives 70 data-parallel flows of 2 136 230 bytes (522
packets) per step and is owed 149 536 100 bytes per step in all. That is
25 % more than the `2 x 7/8` of the bucket a direct all-reduce would move,
because ASTRA-sim gives the fifth stream a full chunk rather than the
remainder. Every per-byte figure in this section is against the bytes the
simulator moved. The run offers 191.4 GB of data-parallel and 793.6 GB of
total payload.

**Topology and where the traffic goes.** A two-tier Clos: 8 hosts per leaf
at 400 Gbps, 4 spines by design (2:1 leaf-to-spine), 32 MB switch buffers,
PFC off. A tensor-parallel group is the 8 hosts of one leaf, so
tensor-parallel traffic stays on the leaf (a simplification, since real
tensor-parallel traffic runs on a scale-up domain). Data-parallel peers
are the same-position hosts on the other seven leaves, so every
data-parallel flow crosses a spine. The most congested configuration (4:1)
fails two of the four spines, and the non-oversubscribed configuration
(1:1) has eight. Oversubscription here is only that ratio.

**Where the incast is.** Under `direct7` all seven peers send to a rank at
once, so seven 400 Gbps senders converge on one 400 Gbps host link. That
last-hop incast exists at every oversubscription ratio; the
oversubscription ratio adds a second congestion point on the leaf-to-spine
uplinks at 2:1 and 4:1. The trim ratio without congestion control,
measured one seed per configuration, is a steady-state property of
provisioning rather than of any burst: 2.4 % at `direct2` 2:1, 6.3 % at
`direct7` 2:1, 12.9 % at `direct2` 4:1, 24.1 % at `direct7` 4:1, and
identical over steps 1 to 17 and over the whole run. Fan-in 2 to 7
multiplies it by 2.6 at 2:1 and 1.9 at 4:1, and oversubscription 2:1 to
4:1 multiplies it by 5.4 at fan-in 2 and 3.8 at fan-in 7. The two axes do
not compound.

**The background burst.** Every run fires seven background RDMA flows of
128 MiB each at one downlink rank (rank 8) at step 18, with no offset
between them. Under selective retransmission the burst changes little. The
data-parallel span of steps 18 and 19 exceeds the median of steps 4 to 17
by 0.04 to 0.62 % of the training time in every configuration of the
sweep, and the burst drains in 30 to 37 ms without congestion control and
63 to 146 ms under DCQCN, which throttles the burst senders. Under
go-back-N the same burst cost 205 to 935 ms of data-parallel span in run
#117. The evaluation keeps the background burst for comparability with
that run. No FORGIVE result depends on it, and the forgiven bytes spread 5
to 7 % per permissive step with step 18 not dominant.

**Transport.** RDMA-style flows, one queue pair per message, 4 096-byte
payload packets. The switch trims under congestion (UEC 1.0.3 style
"forward trimmed data": the payload is dropped, the header forwarded in
a class capped at 25 % of the link, trimmed-header queue 1 MiB against a
4 MiB data queue). The receiver requests selective retransmission (a NACK
per trimmed packet, retransmission of that packet only), with a 1 ms
retransmission timeout and no exponential backoff. The go-back-N variant,
in which a NACK rewinds the sender's window, is the transport of run #117
and of our May setting.

**Congestion control.** DCQCN at every sender, as configured in the
repository: ECN marking at 400 Gbps between 800 KB and 3.2 MB of queue
with marking probability 0.2, EWMA gain 1/256, rate-decrease interval 4,
alpha-resume interval 1, and additive-increase constants scaled with the
link rate (`RATE_AI` 200 Mb/s, `RATE_HAI` and `MIN_RATE` 400 Mb/s at
400 Gbps, the same fractions of the link as the 100 Gbps-era defaults).
No tuning sweep has been run, so every DCQCN figure is "DCQCN as
configured". The runs without congestion control use the same transport
with DCQCN off. No other congestion control algorithm is implemented.

**Load balancing.** Per-flow ECMP across spines; no per-packet spraying.
The hash is seeded by the switch's own identity and source ports are
allocated deterministically, so path assignment is the same in every
seed of a run whose flows are the same.

**Seeds.** Three seeds, 9550582, 23172535 and 94081284, on every
FORGIVE run; the DCQCN baseline has five on the most congested
configuration; run #117 has sixteen. A seed sets the ECN marking draw and
the hash behind the shedding selection and Bernoulli pacing; it does not
move path selection, so the three runs without congestion control in the
reference are one run (identical to the nanosecond), and the spread quoted
for any run without shedding or pacing is the spread of the baseline.
Runs in one comparison share the seed, so their training times can be
subtracted.

**The two baselines.** Every paired record includes the *p_low baseline*:
DCQCN with sender-side shedding at `p_low = 0.005` on every step, which
discards 0.5 % of data-parallel bytes. Every training-time reduction in
this section is measured against it, on the same seed. The *DCQCN
baseline* is DCQCN with no shedding and no forgiveness, run as an unpaired
reference; it reads within -1.1 to +0.8 % of the p_low baseline on the
most congested configuration over five seeds and within -0.4 to +1.6 % on
the non-oversubscribed one, so the two are the same reference within the
seed spread, and the reductions hold against DCQCN with no loss tolerance.
Where "the baseline" appears alone below, it is the p_low baseline.

### 3.1b Metrics

- **Training time (makespan).** Completion time of the last rank over the
  20 steps; every training-time reduction is the paired difference against
  the baseline on the same seed, as a share of the baseline.
- **Loss.** Forgiven bytes as a share of the 191.4 GB of data-parallel
  all-reduce bytes the run offers (gross); where a net figure is given it
  subtracts forgiven bytes that arrived late and were dropped. For
  sender-side shedding, the bytes suppressed before the fabric. Sections
  3.1c and 3.6 come from the run #123 readout, which divides by the
  baseline's post-shed 190.4 GB, 0.5 % higher in relative terms.
- **All-reduce goodput.** Per step, the sum over the 64 ranks of the
  algorithmic bucket size (68 359 375 B) times each rank's delivered
  share, divided by the step's span (latest end minus earliest start of
  the step's data-parallel all-reduce over the ranks), in GB/s. It credits
  a forgiving configuration only for the bytes it delivered.
- **All-reduce completion time per (rank, step)**, whose distribution
  over the non-critical steps is the latency figure.
- **Trim ratio W** (trimmed payload bytes over offered bytes) and
  **retransmitted bytes** (retransmitted bytes over the 793.6 GB offered),
  which measure what a configuration costs the fabric.
- **Per-step data-parallel span**: for each step, the latest end minus the
  earliest start of the step's all-reduce over the 64 ranks; its excess at
  the burst steps over the median steady step is the tail metric of the
  configuration sweep.
- **Worst all-reduce of the run**, in milliseconds, is the tail figure
  quoted for run #117 (1026 to 873 ms, 153 ms saved, CI 5 to 302 ms over
  16 seeds). This section never quotes per-rank p99 completion time, which
  over the same 16 seeds reads -4.9 % with a confidence interval from
  -19.6 to +9.8 %, because it is the top three of 320 samples and one ECMP
  collision moves it by half.
- **Tensor-parallel collective time** against the baseline, to show the
  exempt senders do not slow the traffic that shares their leaf.
- **Verification**: per (rank, step) delivered share, worst (rank, step)
  pair named; every FORGIVE run must read at least `1 - p`.

### 3.1c The configurations, by name

| name in this section | also called | what it does |
| --- | --- | --- |
| p_low baseline | tight baseline, fixed-low | DCQCN, `p_low = 0.005` every step; sheds 0.5 % of DP bytes at the sender; the paired reference for every reduction |
| DCQCN baseline | zero tolerance, raw DCQCN | DCQCN, no shedding and no forgiveness; unpaired; within -1.1 to +0.8 % of the p_low baseline on the most congested configuration over 5 seeds |
| loose baseline | fixed tolerance | DCQCN, `p_high` on every step, sender-side shedding; the unmasked reference |
| sender-side shedding | dynamic tolerance, phase-aware shedding, our May mechanism | DCQCN, `p_low` on critical steps and `p_high` elsewhere, bytes suppressed at the sender before the fabric |
| forgive, congestion control on | | receiver-side forgiveness under the budget, no exemption |
| FORGIVE | | receiver-side forgiveness, vesting, the exemption |
| no congestion control | | the same transport with DCQCN off |
| never re-engage (D) | | FORGIVE with the exemption never withdrawn |

The four-configuration comparison, the most congested configuration,
budget 0.4, three seeds (run #123):

| configuration | training time | all-reduce, non-critical steps | all-reduce, critical steps | gradient lost | retransmitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| p_low baseline | 1697 to 1701 ms | 36 to 37 ms | 36 to 37 ms | 0.5 % | 3.5 to 3.7 % |
| fixed tolerance (loose baseline, 0.4) | 1444 to 1477 ms | 23 to 25 ms | 22 to 26 ms | 40 % | 1.5 to 1.7 % |
| dynamic tolerance (phase-aware shedding, 0.4) | 1491 to 1519 ms | 25 to 26 ms | 35 to 37 ms | 32 % | 2.1 % |
| FORGIVE, 0.4 | 1340 to 1360 ms | 11.8 to 12.6 ms | 33.7 to 35.7 ms | 21.3 to 21.5 % | 2.7 to 3.0 % |

FORGIVE's critical steps stay within 2.5 ms of the baseline's while the
loose baseline's speed up by a third (the loose-baseline spans are from
the run #123 readout; that run's telemetry is not in the local bundle).
The same configuration without congestion control runs in 1367 ms (one
seed), so the time lost to congestion control here is about 330 ms and
FORGIVE at 0.4 returns nearly all of it.

### 3.2 The headline

The most congested configuration, budget 0.1, the design of section 2
without pacing, three seeds against p_low baselines of 1696.7, 1696.9 and
1700.6 ms:

| seed | training-time reduction % | loss, % of DP bytes (gross / net of late arrivals) | retransmitted bytes | timeouts (baseline) | TP collective time vs baseline |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 9550582 | 16.66 % | 7.55 / 7.49 % | 5.88 % | 4 177 (10 110) | -4.3 % |
| 23172535 | 16.06 % | 7.57 / 7.51 % | 5.61 % | 4 145 (10 482) | +4.4 % |
| 94081284 | 16.66 % | 7.56 / 7.50 % | 5.22 % | 4 348 (10 430) | -1.3 % |

The tensor-parallel collectives, which share the leaf with the exempt
senders and run congestion control normally throughout, are never slower
than in the baseline beyond the seed spread. The critical steps forgive
1.25 to 1.26 % of the forgiven bytes in this run, and at budget 0.4 under
the earlier rule set their all-reduce time stays within 2.5 ms of the
baseline's. The exempt senders trim 2.4 times as much as the baseline (W
0.067 to 0.076 against 0.030 to 0.031) and receive a third of its
congestion notifications (4.4 to 4.6 million against 13.0 to 13.4
million). In the run the receivers granted the exemption to 96 % of the
89 600 data-parallel flows at some point, the budget-exhausted flag
changed about 0.5 times per exempt flow, and 19 % of the exempt flows
reacted to congestion signals after a grant, for 0.17 ms each on average.

### 3.3 What the deltas are against

Three references on the same seeds and configuration, budget 0.1 where a
budget applies:

| reference | training-time reduction % | what it costs |
| --- | ---: | --- |
| DCQCN baseline (zero tolerance) | -1.1 to +0.8 % (5 seeds) | nothing |
| forgive but react to congestion signals | 5.5 to 6.6 % | 6.8 to 7.0 % of DP bytes, 1.7 to 1.9 % retransmitted |
| no congestion control at all | 20.1 to 20.3 % (one run; the band is the p_low baseline's spread, since the seed moves nothing in this run) | 25.4 % of all bytes retransmitted, 93 timeouts against the p_low baseline's 10 110 to 10 482 |
| congestion control never resumes (exemption never ends) | 18.7 to 19.0 % | 7.6 % of DP bytes, 6.5 to 6.8 % retransmitted |

The total time lost to congestion control on this configuration is about
20 %. The exemption recovers 16 of it while the fabric keeps congestion
control, and it retransmits a quarter of what the run without congestion
control does. Forgiveness alone, under congestion control, recovers 5.5 to
6.6 points through the reduction in retransmission load, and the exemption
multiplies that reduction by 2.4 to 3.0. The 2.0 to 2.9 points to the run
in which congestion control never resumes, paired by seed, are the
interruptions of the exemption and the one round trip in which each flow
reacts to congestion signals at its start.

### 3.3b Goodput and completion-time distribution

Worst configuration, three seeds, the 16 non-critical steps
(figures `dp-allreduce-goodput-summary.svg`,
`dp-allreduce-goodput-per-step.svg`, `dp-allreduce-time-cdf.svg`):

| configuration | all-reduce goodput, GB/s | relative to the p_low baseline | completion time median | p99 (pooled samples) |
| --- | ---: | ---: | ---: | ---: |
| DCQCN baseline | 117.2 to 118.7 | -2 % | 32.5 ms | 43.2 ms |
| p_low baseline | 119.5 to 121.1 | 0 | 32.3 ms | 38.5 ms |
| forgiveness, congestion control on, p = 0.1 | 132.0 to 133.8 | +11 % | 25.8 ms | 36.4 ms |
| FORGIVE, p = 0.1 | 184.2 to 187.8 | +55 % | 17.4 ms | 28.4 ms |
| no congestion control | 212.2 (one run) | +77 % | 18.4 ms | 23.0 ms |

Goodput nets out the loss: FORGIVE delivers 92.4 % of the gradient bytes
in 54 % of the baseline's all-reduce time. The goodput gain exceeds the
training-time reduction because the training time also contains compute
and the tensor-parallel collectives, which FORGIVE leaves unchanged. The
p99 is a percentile of the 3 072 pooled (rank, step) samples, not a
per-rank tail estimate with a confidence interval. FORGIVE's median
completion time is below the no-congestion-control run's and its tail is
longer, which is the cost of the exemption's interruptions. Sender-side
shedding is absent from this table because its per-flow telemetry is not
in the local bundles.

### 3.4 Which piece produces the reduction

The most congested configuration, budget 0.1, three seeds each, seed
ranges:

| configuration | training-time reduction % | loss | retransmitted |
| --- | ---: | ---: | ---: |
| vesting, no pacing (section 3.2) | 16.1 to 16.7 % | 7.55 to 7.57 % | 5.2 to 5.9 % |
| vesting with pacing at P = 0.25 | 15.8 to 16.9 % | 5.5 to 5.6 % | 6.5 to 6.6 % |
| budget available in full from the first byte, no pacing | 9.1 to 10.2 % | 7.9 to 8.1 % | 1.9 to 2.1 % |
| budget in full from the first byte, pacing at P = 0.25 | 14.6 to 15.3 % | 6.2 to 6.4 % | 6.0 to 6.3 % |
| vesting with a receiver-initiated early stop (as in MLT) at `1 - p` | 15.8 to 16.6 % | 8.10 % gross, 7.25 to 7.28 % net | 5.5 to 5.8 % |

Vesting produces the training-time reduction. A budget available in full
at step start is consumed in the first part of the step, forgiven bytes
never fall, the budget-exhausted flag stays set, and the sender reacts to
congestion signals for the rest of the step. Its low retransmission figure
indicates a sender under rate cuts. Pacing under vesting changes loss and
not training time. A receiver-initiated early stop that ends a sender once
`1 - p` of its share has arrived, charging the rest to the budget,
consumes every per-(rank, step) budget to its cap and recovers nothing, so
it is not part of the design.

On seed 9550582, bucketing data-parallel flows by where they start in
their receiver's step, of the trimmed bytes the cap is asked about (a
range trimmed again is asked again), it forgives 18 % in the first fifth
of a step and 60 % in the last fifth; the first fifth is also where the
most trimming happens (12.3 GB against 1.8 GB in the last). The line
through the origin is biased toward the end of the step. Under pacing the
shares are 65 % to 100 %, because at a quarter of the consumption rate the
cap binds only at the opening. Whether the bias costs anything is an open
question (section 5), because forgiving early converts an outstanding
trimmed byte that would clear when its retransmission arrives into loss
that never clears.

### 3.5 Pacing as a loss dial

Under vesting, pacing at P = 0.25 reads the same training time as no
pacing for two points less loss (section 3.4). Below 0.25 pacing was
measured only under the earlier rule set (a sticky draw, a one-way
revocation and no exemption on critical steps), where it read 15.3 to
16.7 % for 2.6 to 2.9 % at `P = 0.1` and 15.0 to 16.6 % for 1.2 to 1.3 %
at `P = 0.05`, the latter inside the 0.7 to 3.3 % band MLT profiles as
tolerable. Those two points are not yet re-measured under vesting and are
quoted here as the trend, not the result. A configuration that forgives
nothing and keeps the exemption (not a pacing setting, since the parser
refuses `P = 0`; a verdict that always retransmits while the
exemption-eligible flag stays set) decides whether forgiveness recovers
any training time at all on this fabric or whether the tolerance is purely
the bound on the exemption. It has not been built.

### 3.6 The budget as a dial

The earlier rule set ran the budget sweep on the most congested
configuration, against sender-side shedding at the same budgets, which is
our May prototype's mechanism re-implemented in the simulator (the sender
discards a hashed share of its eligible bytes before they enter the
fabric). Seed ranges:

| budget | FORGIVE training-time reduction | FORGIVE loss | shedding training-time reduction | shedding loss |
| ---: | --- | --- | --- | --- |
| 0.05 | 8.0 to 8.6 % | 3.7 to 3.8 % | 0.1 to 1.3 % | 4.1 % |
| 0.1 | 12.9 to 14.1 % | 6.75 to 6.89 % | 2.4 to 3.3 % | 8.1 % |
| 0.2 | 16.0 to 16.7 % | 11.1 to 12.2 % | 4.9 to 5.5 % | 16.1 % |
| 0.4 | 19.6 to 21.0 % | 21.3 to 21.8 % | 10.5 to 12.3 % | 31.7 to 32.3 % |
| 0.6 | 23.7 to 24.3 % | 37.7 to 38.6 % | 16.0 to 16.4 % | 48.0 to 48.2 % |
| 0.4, phase-aware schedule off | 25.3 to 25.6 % | 25.6 to 26.0 % | 13.2 to 14.9 % | 40.0 to 40.2 % |

The training-time reduction per point of gradient lost falls from 2.1 to
2.3 at budget 0.05 and 1.9 to 2.1 at 0.1 to 0.6 at 0.6 for FORGIVE while
shedding stays at 0.3 to 0.4 from 0.1 upward (0.02 to 0.33 at 0.05, where
it recovers almost nothing). The two are furthest apart at the smallest
budgets. Shedding discards exactly its cap; FORGIVE consumes 67 to 84 % of
the same cap and the loss is congestion-proportional. Shedding cannot
relieve a fabric under congestion control. The data queue stays at its
4 MiB ceiling in every configuration, because removing bytes from all
seven senders never removes a sender, and congestion control reacts to the
incast either way. The phase-aware schedule, which protects the critical
steps 1, 2, 3 and 20 at `p_low`, costs 5.1 points of training time and 4.4
points of loss at budget 0.4, and the ledger shows 0.44 to 0.45 % of
forgiven bytes on the protected steps at that budget against 19.2 to
20.5 % without the schedule (1.25 to 1.26 % in the budget-0.1 headline
run, whose `p_low` loss budget is the same size against a smaller `p_high`
loss budget). These points are the v1 rule set. Under vesting the point at
0.1 moves from 12.9 to 14.1 % to 16.1 to 16.7 %, and the rest of the
budget sweep has not been re-run.

### 3.7 Across fabrics

| configuration | p_low baseline training time | p_low baseline trim ratio W | FORGIVE | budget | loss | rules |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `direct7` at 4:1, DCQCN (most congested) | 1697 to 1701 ms | 3.0 to 3.1 % | 16.1 to 16.7 % | 0.1 | 7.55 % | vesting |
| `direct2` at 2:1, DCQCN (ring-like) | 1409 to 1429 ms | | 10.5 to 12.5 % | 0.4 | 2.37 to 2.50 % | v1 |
| `direct7` at 1:1, DCQCN (non-oversubscribed) | 1248 to 1260 ms | 0.02 to 0.04 % | 4.5 to 7.5 % | 0.1 | 1.0 to 1.3 % | vesting |
| `direct7` at 1:1, with pacing at P = 0.25 | | | 5.8 to 6.7 % | 0.1 | 0.27 to 0.42 % | vesting |
| 16 ranks, go-back-N, no congestion control | 7145 ms | | 3.9 % (sender-side shedding, 16 seeds) | 0.1 | 10 % cap | May mechanism |

The configuration sweep (run #120, one seed per configuration, the p_low
baseline, selective retransmission) is the context for the table:

| configuration | training time | trim ratio W | DP flows trimmed | step 18 + 19 excess, % of training time |
| --- | ---: | ---: | ---: | ---: |
| no congestion control, `direct2`, 2:1 | 1201 ms | 0.024 | 24 % | 0.08 |
| no congestion control, `direct7`, 2:1 | 1200 ms | 0.063 | 53 % | 0.04 |
| no congestion control, `direct2`, 4:1 | 1373 ms | 0.129 | 58 % | 0.62 |
| no congestion control, `direct7`, 4:1 | 1367 ms | 0.241 | 75 % | 0.55 |
| DCQCN, `direct2`, 2:1 | 1421 ms | 0.002 | 7 % | 0.23 |
| DCQCN, `direct7`, 2:1 | 1422 ms | | | 0.34 |
| DCQCN, `direct2`, 4:1 | 1719 ms | | | 0.60 |
| DCQCN, `direct7`, 4:1 | 1696 ms | | | 0.10 |

DCQCN divides the trim ratio by 8 to 10 and lengthens the training time by
18 to 24 % in every column. The burst steps never exceed a steady step by
1 % of the training time anywhere. On the go-back-N fabric of run #117 (16
ranks, no congestion control, 16 matched seeds) phase-aware shedding at
budget 0.1 shortened the training time from 7145 to 6854 ms (3.91 %, CI
1.13 to 6.68 %), the worst all-reduce of the run from 1026 to 873 ms (CI 5
to 302 ms), and the relief correlated 0.93 with trims avoided at 11.9 ms
per million and not with bytes discarded. The loose baseline recovered
9.42 % (CI 7.03 to 11.82 %) for 40 % loss. That relief is retransmission
amplification under go-back-N, and the same policy recovers 0.78 % under
selective repeat.

With eight spines the fabric is not oversubscribed and the baseline trims
0.02 to 0.04 % of bytes, so the pre-registered kill test ("if the 1:1
baseline's trim ratio is below 0.5 % and FORGIVE recovers under 2 points,
the claim is scoped to degraded fabrics") did not fire, because FORGIVE
recovers 4.5 to 7.5 % for 1.0 to 1.3 % of bytes, and pacing 5.8 to 6.7 %
for 0.27 to 0.42 %. The incast is at the last hop. Seven senders at
400 Gbps into one 400 Gbps receiver link is a 7:1 incast whatever the
oversubscription ratio, DCQCN reacts to it with rate cuts on every step,
and the exempt senders trim ten times more than the baseline (0.27 to
0.34 % of bytes) and still complete sooner. Sender-side shedding recovers
0.1 to 0.3 % on the same configuration and the loose baseline -0.4 to
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
| loss accepted from a trimming switch without retransmission | trimmable gradients (Chen, Vargaftik, Ben Basat, HotNets 2024) | tweaked: bounded by the budget, retransmitted otherwise |
| a flow allowed a weaker congestion response by class | D3, D2TCP, PDQ, Karuna, pFabric | transferred: per flow, bounded by a receiver's budget, ended and restored by the receiver's budget-exhausted flag |
| declared partial reliability | PR-SCTP, QUIC DATAGRAM, Ultra Ethernet's unreliable mode | as-is in spirit; the mode is chosen per range at the receiver, not per stream at setup |

FORGIVE combines MLT's bounded-loss receiver (per range), our May
phase-aware schedule (as-is), a vested byte budget per rank and step
(new), and a per-flow congestion-control exemption bounded by that budget
(transferred from deadline-aware transports, with revocation and
restoration added). The patterns it fits are composition and transfer, and
it must show that the whole beats each origin alone on a fabric the field
runs now. Section 3.3 measures that comparison.

MLT stops a tensor once `1 - p` has arrived and loses whichever bytes
arrive last, keeps one bound per model for all of training, and weakens
rate control globally because loss is tolerated; its tolerated fractions
at equal rounds are 0.7 to 3.3 % across sixteen CNN and RNN models, 10 %
at a quality target. LTP closes rounds early with an adaptive threshold in
a parameter-server setting. OptiReduce bounds each stage by a timeout and
makes the loss harmless with a Hadamard mixing, on TCP in the cloud.
Trimmable gradients lay packets out so a trimmed packet is a compressed
gradient, with no bound and no retransmission, and its authors ask for a
congestion control that over-sends and lets the switch trim the excess,
which the exemption provides with a budget that paper does not have. None
decides per trimmed range at the time the switch rejects it, none keeps a
budget in bytes per rank and step, and none exempts an RDMA flow from
reacting to its own congestion signal under a receiver's budget and
resumes congestion control on the receiver's word. Those three are the
claim.

The tail those systems shorten is not there under trimming with selective
retransmission (section 1), and a bounded loss can instead recover
congestion control's rate reduction, which is 18 to 25 % of the training
time under DCQCN on the oversubscribed configurations and at least 4.5 to
7.5 % on a fabric that is not, the latter being what the exemption
recovers there. The configuration without congestion control has not been
run there.

The budget rule itself is an instance of a problem the online-allocation
literature states as a theorem, the allocation of a fixed supply
irrevocably to arrivals whose total is unknown. Sinclair, Jain, Banerjee
and Yu prove that fairness across arrivals and full allocation trade off,
Manshadi, Niazadeh and Rodilitz give the near-optimal proportional policy,
and Balseiro, Lu and Mirrokni the dual-price form. Our line through the
origin is none of these. It gives the first arrival nothing and the last
the full remaining budget, and the appendix to our budget-shape review
records the mapping. That literature does not model the exemption. In
every one of those problems the good has the same value whenever it is
granted, and ours does not, because a forgiven byte never clears while an
outstanding trimmed byte does.

## 5. What this section does not show

- **Tolerance.** The simulator moves bytes and has no gradient; every
  statement about training surviving the loss rests on our May GPT-2 runs
  at 40 % with zero-fill, on MLT's 0.7 to 3.3 % at equal rounds, and on
  Weintraub, Banner and Orda's Llama 2 7B at 10 % i.i.d. loss for 1.17 %
  worse perplexity. The headline's 7.55 % is above MLT's band and inside
  Weintraub's; pacing at a small `P` would put it inside MLT's band at no
  cost in training time. No paper measures the bursty loss correlated
  across senders that a trimming fabric produces, and the theory says the
  pooled budget is sound only with the rescaling of section 2.7. The
  instrument is an injection experiment: export the forgiven ranges, zero
  or rescale those elements in a DDP hook, and train a GPT-2-class model
  against an unmodified run, with even against uneven loss at equal
  aggregate as one of its configurations.
- **One congestion control algorithm, as configured.** The time lost to
  DCQCN is quoted as measured with the repository's parameters; no tuning
  sweep separates its inherent cost from its defaults, and no paper does
  either. Meta runs its 400 Gbps training fabric with DCQCN off; where
  there is no congestion control, the exemption has nothing to act on and
  only the reduction in retransmission load remains.
- **Three seeds, one workload, per-flow ECMP.** No packet spraying, no
  NSCC, no second workload, no multi-tenant fairness measurement; the
  bound and the receiver's budget-exhausted flag are the only answer to
  the objection Floyd and Fall raise against unresponsive flows, and a
  two-tenant experiment is the instrument.
- **Whether forgiveness reduces training time at all on this fabric.**
  Under vesting the marginal training time of a forgiven byte measured
  zero between 7.55 % and 5.5 % loss. A configuration that forgives
  nothing but keeps the exemption (to be built; the pacing parser refuses
  `P = 0`) decides whether the tolerance itself recovers training time or
  is purely the bound on the exemption; if the latter, the design loses
  nothing and the paper's claim becomes more precise.
- **The shape of the vesting line.** It is biased toward the end of the
  step (section 3.4). Candidate shapes exist (a burst-sized initial
  allowance, a concave release, crediting outstanding trimmed bytes, a
  release gated on the fabric's current trim rate) and none is measured;
  the objective for choosing among them is training time per byte lost
  with the prefix bound kept as a constraint, not fairness across
  arrivals.
- **Scale.** 64 ranks with tensor parallelism on the leaf. The simulator
  models the ranks as NICs, and tensor-parallel traffic runs on the leaf
  rather than a scale-up domain. Pipeline parallelism is not simulated.

## 6. Figures and data in hand

Current, drawn 2026-09-22 from the bundles of runs #123, #126 and #127
and named in section 3.3b: `dp-allreduce-goodput-per-step.svg`,
`dp-allreduce-goodput-summary.svg`, `dp-allreduce-time-cdf.svg`.

Not yet drawn, from data in hand: the per-(rank, step) delivered-share
histogram (the loss bound at every rank and step, worst 0.900 to 0.909);
retransmitted bytes, trim ratio, timeouts and CNPs per configuration as
one grouped chart; tensor-parallel collective time against the baseline;
the budget sweep as goodput against loss; and the exemption's duty cycle
per step from the transition counters.

Older, from the go-back-N and v1 eras, to be redrawn before use, in
`docs/agents/figures/`: `regime-map.svg` (the eight
configurations), `run117-paired-seeds.svg` and `run117-mechanism.svg` (the
go-back-N result and its correlation with trims avoided),
`recovery-amplification.svg` (go-back-N against selective repeat),
`dose-front.svg` (the v1 budget sweep, needs the vesting point added),
`rate-versus-volume.svg` (why sender-side shedding cannot relieve a fabric
under congestion control), `forgive-mechanism.svg` (the protocol diagram,
needs the exemption and the outstanding-trimmed-bytes rule),
`progress-timeline.svg`.

Tabulated and not yet drawn, with the per-seed rows in
`docs/agents/figure-data.md`: the design-of-record ablation (section 15
there), the three references (12), the pacing sweep (11), the phase-aware
schedule's cost and integrity (8), the exemption counters across the
budget sweep (10), the non-oversubscribed configuration (16), and the
within-step bias split by fifth of the step (in `headline-is-vesting` and
section 3.4 above). Every figure recomputes from a release bundle named in
section 7.

## 7. Provenance

| number | run | code | configurations |
| --- | --- | --- | --- |
| the configuration sweep (section 1) | #120, 2026-09-06 | map-only rerun 34055188995 | 8 unpaired runs, one seed |
| the v1 budget sweep, the phase-aware schedule, the ring-like configuration (3.6, 3.7) | #123, 2026-09-14 | main c6855f0, ns-3 9717200cc | 21 records, 84 runs, all verified |
| pacing below P = 0.25 and budget 0.05 (3.5, 3.6) | #125, 2026-09-16 | main 8213401 | 24 runs, all verified, earlier rule set |
| the references (3.3) | #126, 2026-09-16 | main a1b30b0 | 15 runs, all verified |
| the design of record and its ablations (3.2, 3.4) | #127, 2026-09-17 | main 59cf16c, ns-3 3e11ace49 | 21 runs, all verified, worst (rank, step) pair 0.900 to 0.909 |
| the non-oversubscribed configuration (3.7) | #130, 2026-09-17 | main 65e98e7 | 18 runs; the FORGIVE and pacing runs verified locally, worst (rank, step) pair 0.916 to 0.948 and 0.983 to 0.984 |
| go-back-N (3.7) | #117, 2026-09-03 | go-back-N era | 16 matched seeds |

The committed analyzer re-analysed every FORGIVE run against its own
bundle, and it fails a run whose ledger breaks the bound.