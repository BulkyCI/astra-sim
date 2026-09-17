# The forgive protocol

This is the specification of record for receiver-side bounded loss on a
packet-trimming RDMA fabric, written from the code as built and from the
runs that measured it. It is written for a reader with a computer
networks background. Terms are defined where they first appear. Results
are in [run-120-regime-map.md](run-120-regime-map.md) and
[run-123-readout.md](run-123-readout.md). The code is
C++17 under `extern/network_backend/ns-3` and
`astra-sim/network_frontend/ns3`, and Python 3.11 under
`experiments/ring_3d`.

## 1. What the protocol does

Distributed training synchronizes gradients with an all-reduce every
step. A training job can lose a small share of those gradient bytes
without harm, except during the critical learning period early in
training. The forgive protocol lets the network use that tolerance.

The mechanism has three parts.

- The switch trims instead of dropping. When a queue is full, the switch
  truncates the packet to its header and forwards the header on a
  lossless control queue. The receiver therefore learns exactly which
  bytes went missing. This is packet trimming as specified by the Ultra
  Ethernet Transport.
- The receiver decides what to do with each missing range. It either
  requests retransmission, as any selective-retransmission transport
  would, or it forgives the range: it acknowledges past the hole as if
  the bytes had arrived. A budget per receiving rank and per training
  step bounds how much may be forgiven. The budget is tight on critical
  steps and loose on the others.
- With congestion exemption enabled, a sender whose trims would be
  forgiven also stops reacting to congestion signals. It keeps its rate
  until the receiver reports that its budget entry has no allowance
  left. From then on it obeys congestion control again. The sender pays
  for congestion in bounded loss instead of in reduced rate.

The budget can be spent in three places. All three share one accounting
rule, so they can be compared at equal budget.

| where the budget is spent | configuration name | what happens | sender under congestion |
| --- | --- | --- | --- |
| at the sender, before sending | `admission` | a hash draw suppresses whole gradient messages; the receiver gets a 64-byte placeholder instead | obeys congestion control |
| at the receiver, after a trim | `recovery` | the receiver forgives trimmed ranges | obeys congestion control; a forgiven trim still triggers a rate cut |
| at the receiver, after a trim, with exemption | `recovery_exempt` | same as `recovery` | withholds every congestion signal until the receiver reports the allowance spent |

Sender-side suppression is the mechanism of the DBLP paper and serves as
the matched baseline. Receiver-side forgiveness is the forgive protocol.
Forgiveness with congestion exemption is the variant that produced a
measurable gain.

## 2. Why each piece exists

Each paragraph states a measurement and the design decision it forced.

**Trimming turns loss into a message.** A dropped packet leaves the
receiver waiting for a retransmission timeout. A trimmed packet delivers
its header on a lossless queue, so the receiver knows the missing range
at once. That is what makes a receiver-side decision possible. Without
trimming there is nothing to forgive, only a timeout to wait for.

**Tolerance depends on the training phase.** The DBLP and Accordion
papers show that a model cannot afford gradient loss during its critical
learning period and can afford substantial loss afterwards. The budget is
therefore a per-step probability. It is `p_low` on the critical steps,
which are pinned to steps 1, 2, 3 and 20 (see
[clr-schedule-evidence.md](clr-schedule-evidence.md)), and `p_high` on
every other step. The budget applies only to gradient all-reduce
payload. Tensor-parallel traffic, pipeline traffic, control packets and
background traffic are never eligible.

**The bound belongs to a rank and a step, not to a flow.** The claim
about tolerance is about one rank's gradient for one step. The budget is
therefore kept per (receiving rank, training step). Every eligible flow
registers its byte count when it is sent. Suppression at the sender and
forgiveness at the receiver both charge the same entry. The entry closes
when that rank's all-reduce for that step completes. The rule is:

```
forgiven_bytes(rank, step) + suppressed_bytes(rank, step) <= p(step) * eligible_bytes(rank, step)
```

Both counters only grow. Nothing is refunded. A closed entry forgives
nothing. The receiver enforces that rule in counters it owns, as
`forgiven <= p(step) x (delivered + forgiven)`, the soft cap; a step ends
with `delivered + forgiven = eligible`, so the two forms share one ceiling
and the analyzer certifies against the accumulated `eligible`. The step's
total `owed`, which the generator plans and `close` holds to the launches,
is the hard cap, and it is what revocation and the step stop read.

**Forgiveness alone saves no time.** Run #117 measured 4 to 11 % shorter
training under go-back-N recovery. A control run with selective
retransmission showed why: under go-back-N every trim caused the sender
to resend its whole window, up to 79 bytes on the wire for every byte the
policy removed. Under selective retransmission a trim costs one repair
packet and one round trip, overlapped with the rest of the flow. Run #120
confirmed this across eight fabric configurations: the congestion episode
cost under 1 % of the training time in every one. Forgiveness that only
skips the repair round can save at most one round trip per flow, which is
under 0.2 % of an all-reduce. So receiver-side forgiveness by itself is
not a performance mechanism. It needed a second half.

**The cost of congestion control is what can be bought back.** On the
same eight configurations, DCQCN cut the trim rate tenfold and lengthened
the training time by 18 to 24 %. It did so through millions of rate cuts.
That time was spent avoiding trims the model could have afforded. So an
eligible flow on a non-critical step is exempted: it ignores rate cuts
while its budget entry has room.

**The exemption must cover ECN marks, not only trims.** In the DCQCN
configuration used here, switches start ECN-marking packets at 800 KB of
queue at 400 Gbps and trim only when the 4 MiB data queue is full. Marks
arrive long before trims. On the most congested configuration at least
74 % of rate cuts came from ECN marks, which a forgiven trim never
touches. Exempting the flow only from trim-triggered cuts would leave
three cuts in four in place. So an exempt sender ignores every congestion
notification packet, whatever caused it.

**A spent allowance ends the exemption.** The budget entry is shared by
every sender that talks to one rank, so no sender can read it. The
receiver therefore reports the one thing a sender cannot work out for
itself: this entry has no allowance left. The report is one header bit,
it rides an existing repair request or forgiveness acknowledgement, and
the first one to reach an exempt flow puts that flow back under
congestion control with the rate cut the same packet carries. A repair
request on its own does not end an exemption: the receiver replays one
whenever a range it is already repairing is trimmed again, which says
nothing about the budget.

**What it measured.** On the most congested configuration, over three
seeds at budget 0.4, forgiveness with exemption shortened training by 20
to 21 % relative to DCQCN alone, and its critical steps stayed within
2.4 ms of DCQCN's. It lost 21.3 to 21.5 % of the gradient bytes, against
32 % for sender-side suppression at the same budget, and its training
time was shorter. At budget 0.1, the budget we publish, it shortened
training by 12.9 to 14.1 % for 6.75 to 6.89 % of the gradient bytes.
Section 8 has the table.

## 3. Who decides what

| role | knows | decides |
| --- | --- | --- |
| switch | its queue depth | trim or forward; it never decides acceptance |
| receiver NIC model (ns-3 `RdmaHw`) | which ranges are missing and which it already holds | asks the experiment layer per unsettled range, then absorbs or requests |
| experiment layer (`ExperimentConfig.hh`) | flow identity, training step, critical-step mask, the budget entries | the verdict per range; the exemption per flow at creation |
| sender NIC model (ns-3 `RdmaHw`) | its own rate and window | nothing new; it delivers or withholds congestion signals according to its exemption flag, and re-arms on the receiver's allowance report |

The transport carries no application semantics. The ns-3 code passes a
five-tuple and a byte range across two callbacks. It never learns what a
step or a budget is.

## 4. The receiver's decision

A trimmed packet arrives at its destination carrying the original
sequence number and payload length. The receiver first computes how many
of those bytes it does not already hold. Bytes below its cumulative
acknowledgement point, or inside its set of accepted out-of-order ranges,
are already held. A retransmission can be re-segmented so that a trimmed
range straddles the cumulative point or overlaps an accepted range;
charging the full length in that case would spend budget on bytes the
receiver already has. The unsettled length is what the verdict is asked
about.

Each range is in one of three states.

| state of the range | on a trimmed packet | on a data packet (a retransmission after timeout) |
| --- | --- | --- |
| held, nothing unsettled | send a duplicate ACK; no charge | accept as today |
| requested | recompute the verdict and send the answer again | accept |
| forgiven | send an ACK; no charge | discard the payload and ACK; no refund |
| unsettled | ask for a verdict | cannot happen: data never precedes a verdict on the same range |

The verdict function is total. Anything it cannot place is answered with
a retransmission request.

```
verdict(flow, unsettled_bytes):
  flow unknown, or not gradient payload, or not eligible,
    or the configuration does not forgive                    -> request
  step not in the critical-step mask                         -> request
  threshold = p_low if step is critical else p_high
  budget entry (rank, step) cannot cover unsettled_bytes     -> request
  charge the entry; add unsettled_bytes to the flow's total  -> forgive
  entry has no room for one further byte                     -> report the allowance spent
```

On forgive, the range is added to the accepted out-of-order set as if it
had arrived. If it was at the head of the sequence, the cumulative
acknowledgement point advances over it and over any accepted ranges
behind it. An acknowledgement is sent immediately. That acknowledgement
carries the congestion flag, so that in the `recovery` configuration a
forgiven trim costs the sender the same rate cut a requested one would.
Forgiving must not hide congestion.

On request, the existing trim NACK is sent. The verdict is recomputed on
every request rather than remembered, because the allowance only shrinks
within a step, so a repeated question answers the same way or refuses,
and recomputing is also right when the first request was lost.

Two edge cases are covered by the state table. First, a trimmed packet
can arrive for a flow whose receive state is already gone, because the
flow completed and its port number was reused. Such a packet is answered
with a plain retransmission request. Creating receive state for it would
leave a stale cumulative point for the next flow on that port. Second, a
retransmission timeout can resend a range after the receiver forgave it.
That data takes the old-sequence path and is discarded. A race between
forgiveness and the timeout can therefore neither deliver the bytes
twice nor refund the budget.

## 5. The sender

In the `recovery` configuration the sender is unchanged. Its cumulative
acknowledgement point advances over forgiven holes, and the transfer
completes when that point reaches the message size.

In the `recovery_exempt` configuration each queue pair carries one flag.
The receiver sets it and the receiver clears it, once each: the sender
reads neither a budget nor a step.

| state | event | result |
| --- | --- | --- |
| creation | queue pair created | obeying its controller, at line rate as always |
| obeying | an acknowledgement arrives marked eligible with no allowance report | exempt from that acknowledgement on, and the time recorded; one round trip of every flow is spent obeying |
| exempt | congestion signal arrives (from an ECN-marked ACK, a forgiveness ACK, or a trim notification) | withheld from the controller and counted; the DCQCN rate and its alpha state are untouched |
| exempt | allowance report arrives, on a repair request or a forgiveness ACK | flag cleared, time recorded, then the normal path runs, including this packet's own rate cut |
| re-armed | anything, including a later eligible acknowledgement | DCQCN as today; the grant is one way, so the exemption cannot flap |

The re-arm happens before the sender checks whether the request is stale.
A stale report still describes a spent entry. The receiver code is
identical in the two configurations. An exempt sender withholds the
congestion flag on a forgiveness ACK; a re-armed sender acts on it. The
transport reaches its congestion controller at three call sites and the
exemption is checked at those, so an exempt flow runs no controller code
at all.

The experiment layer's answer, asked by the receiver once per receive
queue pair and carried on every acknowledgement that queue pair emits:

```
eligible(flow):
  configuration is not recovery_exempt, or not gradient payload,
    or not eligible                                          -> no
  step is critical, or not in the mask                       -> no
  the permissive threshold is zero                           -> no
  otherwise                                                  -> yes
```

The grant is that mark on an acknowledgement whose allowance report is
clear, so the sender learns both halves from one packet and reads no cell.
The exemption spends no budget. Only forgiveness does. A flow whose budget
entry is later used up by other flows is re-armed by its own next trim,
because the receiver reports the spent entry on the answer to that trim. A
flow that is never trimmed again stays exempt until it completes. It is not
the flow causing trims.

## 6. Invariants

- The forgiven and suppressed byte counts of an entry only grow. The
  budget rule holds at every charge. A closed entry forgives nothing.
  `analyze.py` re-checks the rule per run from the integer thresholds
  the generator wrote.
- A range is charged at most once, because forgiving it absorbs it and an
  absorbed range has no unsettled bytes left to charge.
- Delivered bytes exclude forgiven bytes. The `physical_bytes` column
  keeps counting forgiven bytes as offered, because it is the denominator
  of the trim ratio and is joined against the ns-3 flow-completion
  records. The `delivered_bytes` column excludes them.
- Nothing is forgiven, exempted or suppressed on a placeholder flow, a
  background flow, a tensor-parallel flow or a pipeline flow, nor on a
  critical step beyond `p_low`.
- The `recovery` configuration does not change the sender's reaction to
  congestion. It takes exactly the rate cuts that its trims and ECN marks
  would cause without forgiveness.
- The exemption flag is set only in the `recovery_exempt` configuration.
  A recorded re-arm time implies the flow was told its allowance was
  spent, and that it took at least one rate cut afterwards.
- Two runs of one profile with one seed produce identical telemetry.
- The switch never decides acceptance. Every trim is a question to the
  receiver, never an answer.

## 7. Configuration and refusals

Profile keys, in `experiments/ring_3d/profiles/*.json`:

```json
"selection_policy": { "p_low": 0.005, "p_high": 0.4, "domain": "recovery_exempt" },
"clr_schedule": { "kind": "explicit_critical_steps", "critical_steps": [1, 2, 3, 20] },
"network": {
  "packet_trimming": { "mode": "ftd" },
  "transport_recovery": { "selective_repair": true, "retransmission_timeout_ns": 1000000 },
  "congestion_control": { "mode": "dcqcn" }
}
```

The generator refuses an inconsistent profile by name, and the simulator
refuses it again when it reads the generated configuration.

| configuration | requires |
| --- | --- |
| `recovery` | selective retransmission (`selective_repair: true`), packet trimming (`ftd`), a critical-step mask covering every step |
| `recovery_exempt` | all of the above, plus DCQCN (`congestion_control.mode: dcqcn`) |

Selective retransmission is required because a forgiven range is stored
as an accepted out-of-order range, and go-back-N never consults that
set. Trimming is required because a dropped packet reaches no receiver.
A mask is required because the verdict answers "request" for any step it
cannot find, and a run that forgives nothing by omission would look like
a null result. DCQCN is required because without congestion control
there is nothing to be exempt from.

The generator writes the configuration name, a semantics string
(`recovery_forgiveness` or `recovery_forgiveness_cc_exempt`) and the
transport requirements into `experiment.json`. The simulator checks all
of them against the transport it was built with. `run.py --domain`
overrides the profile's configuration, which is how `compare.py` builds
the matched runs.

## 8. Matched runs and what they measured

For a profile that forgives, `compare.py` runs four configurations per
seed. All four draw from one random selection stream, so the set of
messages suppressed by the sender-side baseline is the same set the
receiver-side runs treat as forgivable.

| run | where the budget is spent | budget |
| --- | --- | --- |
| tight baseline (`fixed_p_low_baseline`) | sender | `p_low` on every step |
| phase-aware suppression (`dblp_policy`) | sender | `p_low` on critical steps, `p_high` elsewhere |
| forgiveness (`recovery_policy`) | receiver, per the profile | same as phase-aware suppression |
| loose baseline (`fixed_p_high_baseline`) | sender | `p_high` on every step |

Run #123 used the most congested fabric of the regime map: DCQCN,
direct all-reduce with seven-way fan-in, and a spine oversubscribed 4:1.
Three seeds. "Training time" is the makespan of 20 training steps.
"All-reduce time" is measured from the first rank's start to the last
rank's completion.

| run | training time | all-reduce time, non-critical steps | all-reduce time, critical steps | gradient bytes lost | bytes re-sent after trims |
| --- | ---: | ---: | ---: | ---: | ---: |
| tight baseline | 1697 to 1701 ms | 36 to 37 ms | 36 to 37 ms | 0.5 % | 3.5 to 3.7 % |
| phase-aware suppression, 0.4 | 1491 to 1519 ms | 25 to 26 ms | 35 to 37 ms | 32 % | 2.1 % |
| forgiveness with exemption, 0.4 | 1340 to 1360 ms | 12 to 13 ms | 34 to 36 ms | 21.3 to 21.5 % | 2.7 to 3.0 % |
| loose baseline, 0.4 | 1444 to 1477 ms | 23 to 25 ms | 22 to 26 ms | 40 % | 1.5 to 1.6 % |

Per seed, the exempt run withheld 25.4 to 25.7 million congestion
signals, delivered 3.58 to 3.69 million, and re-armed 5 049 to 5 447 of
its 71 680 exempt flows. The flows that received an allowance report are
the flows that re-armed, to the flow, which is the invariant of section 6
measured rather than assumed. The budget rule held in every entry. The
same fabric without any congestion control ran in 1367 ms and re-sent
24 % of its bytes after trims (run #120, one seed). The exemption is
therefore a third way to pay for an overloaded fabric: it finishes below
the no-congestion-control result, its re-sent bytes stay near DCQCN's,
and it loses 5.1 % of all bytes.

## 9. Telemetry

Per flow, in `telemetry/flow_events.csv`, the columns added by this
protocol in order: `timeouts`, `cnp_received`, `first_trim_ns`,
`first_repair_ns`, `forgiven_bytes`, `forgiven_ranges`,
`forgiven_remainder_bytes`, `pacing_refusals`, `soft_refusals`,
`late_forgiven_bytes`, `delivered_bytes`, `cc_exempt`,
`cc_exempt_granted_ns`, `cc_signal_withheld`, `allowance_gone_reports`,
`cc_transitions`, `cc_obeying_ns`.

Per run, in `ns3/transport_summary.csv`, the events: `trim_ftd_admission`
and `trim_ftd_lasthop_admission` (data plane, bytes trimmed),
`trim_forgiven` and `remainder_forgiven` (data plane, bytes forgiven),
and the control-plane counts `rto_fired`, `cnp_taken`,
`cc_signal_withheld`, `allowance_gone_reports`, `cc_exempt_granted`,
`cc_transition`, `clipped_trim`.

`summary.json` and the report derive from these: the trim ratio W
(trimmed bytes divided by offered bytes), the net trim ratio W' (W minus
the forgiven share, which is the load the transport still re-sent),
forgiven bytes per step, the exemption counters, and the budget-rule
verdict. Do not quote `wire_per_offered`; it counts bytes per hop, not
per receiver (see the run #120 readout).

## 10. What the test gate proves

`experiments/ring_3d/forgiveness_smoke.sh` runs on every push.

- `RdmaRangeAlgebra` exercises the receiver's range clipping and pruning,
  including the straddle and partial-overlap branches that no fabric run
  can reach because every packet starts on a packet boundary.
- `forgiveness_smoke_8` in the `recovery` configuration, against the same
  profile in the `admission` configuration: every flow completes;
  forgiven bytes appear only on gradient payload and only within the
  budget rule; bytes charged equal bytes absorbed; delivered bytes
  exclude forgiven bytes; the net trim ratio is below the trim ratio;
  two same-seed runs are identical.
- `forgiveness_race_8` sets the retransmission timeout an order of
  magnitude below the round-trip time, so retransmitted data races the
  forgiveness that made it redundant: forgiven bytes stay monotone,
  duplicates are discarded, every flow completes.
- `forgiveness_dcqcn_8` checks that under DCQCN a forgiven trim still
  costs a rate cut.
- `exempt_smoke_8` in the `recovery_exempt` configuration: only eligible
  gradient flows on non-critical steps are exempt; at least one
  congestion signal is withheld; no non-exempt flow withholds any; the
  exempt flows told their allowance was spent are exactly those that
  re-armed; every re-armed flow was exempt and took a rate cut
  afterwards; the budget rule holds.
- `bernoulli_smoke_8` and `stepstop_smoke_8` carry one v2 policy each,
  checked in section 15.
- `check_refusals.py` breaks each required field in turn and checks that
  the run is refused by name and leaves no telemetry.

Unit tests cover the profile parser's refusals, the construction of the
four matched runs, the counters reaching the summary and the report, and
the CI matrix's run counts.

## 11. Cost

The verdict per trim is one lookup in a map of at most about ten
thousand active flows, plus constant-time access into a dense array of
ranks by steps. The exemption is asked once per queue pair. The
congestion-notification check is one boolean test. Measured on the
32-rank profile with the `admission` and `recovery` configurations on the
same build, the receiver-side path costs 0.56 % more wall time per
simulated event, within run-to-run spread, and the run has fewer events
overall because forgiven ranges are never retransmitted.

## 12. Limits and open items

- Tolerance is assumed, not demonstrated. That a current model survives
  losing 6.8 % of its gradient bytes on non-critical steps rests on the
  DBLP paper (EfficientNet, ResNet) and on Weintraub et al. 2025 (10 %
  uniform loss on Llama 2 7B, with no phase dependence tested). A real
  training run is needed.
- DCQCN only. The exemption discards DCQCN's congestion notification
  packets. The Ultra Ethernet default congestion control (NSCC) is
  window-based with a trim-triggered fast adaptation and has no model
  here. Meta runs its 400 Gbps training fabrics with DCQCN off; there the
  exemption has nothing to act on, and receiver-side forgiveness alone is
  the open question.
- One tenant. The exempt flows shared the fabric only with their own
  job's tensor-parallel traffic and one background burst. Against another
  job's flows that obey congestion control, the cost of the exemption
  lands on that job. The budget bounds it; nothing here measures it.
- Eligibility covers the gradient all-reduce as a whole. Treating its
  reduce-scatter half as forgivable and its all-gather half as never
  forgivable needs a collective-phase field in
  `AstraSim::OperationContext`.
- The receiver never acknowledges beyond what the sender has sent.
  Without evidence of congestion, such skip-ahead would degenerate into
  suppression at the receiver.
- The switch has no steering role. Drop-precedence steering would only be
  an efficiency option, with no authority over acceptance.

## 13. Relation to prior work

Receiver-side bounded loss for gradient traffic exists: MLT (NSDI 2024)
stops retransmission once a fixed fraction of a tensor has arrived, LTP
(2023) closes a round early on network conditions, OptiReduce (NSDI 2025)
bounds a round by a timeout, and trimmable gradients (HotNets 2024) make a
trimmed packet a compressed gradient with no retransmission at all. What
this protocol adds over them is the per-range verdict driven by the
switch's trim report, the budget per rank and step with the critical
steps held tight, and the per-flow, budget-bounded, self-revoking
congestion-control exemption. The comparison table, the null searches
that support the "not found" claims, and what the literature says about
the tolerance and DCQCN assumptions are in
[forgive-related-work.md](forgive-related-work.md).

## 14. Where the code lives

| piece | file |
| --- | --- |
| receiver fork, verdict callback, sender exemption and re-arm | `extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc` |
| range algebra, per-queue-pair counters | `extern/network_backend/ns-3/src/point-to-point/model/rdma-queue-pair.{h,cc}` |
| allowance report and eligibility mark on the repair request and the acknowledgement | `extern/network_backend/ns-3/src/point-to-point/model/qbb-header.{h,cc}` |
| attribute wiring, transport events | `extern/network_backend/ns-3/scratch/common.h` |
| configurations, budget entries, verdict, exemption predicate, telemetry columns | `astra-sim/network_frontend/ns3/ExperimentConfig.hh` |
| callbacks, eligibility registration, counter copy at completion | `astra-sim/network_frontend/ns3/entry.h` |
| profile parsing, refusals, `experiment.json` | `experiments/ring_3d/generate.py` |
| matched runs | `experiments/ring_3d/compare.py` |
| budget-rule check, trim ratios, counters | `experiments/ring_3d/analyze.py`, `report.py` |
| test gate | `experiments/ring_3d/forgiveness_smoke.sh`, `check_forgiveness.py`, `check_refusals.py` |
| profiles | `experiments/ring_3d/profiles/forgiveness_*_8.json`, `exempt_smoke_8.json`, `regime_64_dcqcn_*_exempt.json`, `no_incast_8_forgive.json` |
| v2 pure core, pacing sum, remainder verdict | `astra-sim/network_frontend/ns3/ExperimentConfig.hh` |
| v2 step stop, arrival accounting, remainder callback | `extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc` |
| v2 core law fixtures | `extern/network_backend/ns-3/scratch/rdma-range-algebra.cc` |
| v2 single-arm join fixture | `experiments/ring_3d/check_single_arm_join.py` |

## 15. Version 2: pacing, the cap's base, and the step stop

**Built, unmeasured.** The mechanisms below are implemented and gated by
the smoke suite; no wave has run them, so this section states what they
do and states no result. The design and its pre-registered estimands are
in [forgive-v2-design.md](forgive-v2-design.md); the arms wait behind the
`forgive_v2` dispatch input.

Only the receiver can forgive, because only the receiver knows how much
it needs and how much it has. v2 adds two receiver policies on top of the
v1 verdict and changes no sender logic.

**Pacing (change P).** The cap binds at the headline budget, and first
come first served spends it on the first burst, so the receiver may
decline a forgivable trim to keep allowance for later in the step.
`selection_policy.pacing` is a closed sum of two rules. Both spend the one
cap `(forgiven + b) * 1000000 <= (delivered + forgiven + b) * t`, which is
the receiver-local form of the v1 law: the rank weighs the budget against
the bytes it has accounted for, kept or forgiven, so the cap becomes
available as it receives rather than as senders launch, and a step whose
delivered and forgiven bytes exhaust the eligible ones reaches the same
`p x eligible` ceiling. Under `bernoulli` the range is additionally
declined when `hash_combine(flow.decision_hash, range start) % 1000000 >=
p * 1000000`, where the flow's count of verdicts asked enters the hash as
the attempt number. Every trimmed arrival draws, so a declined range is
asked again on its next trim and meets the cap as it stands then; nothing
about a range is remembered between trims. No ns-3 random stream is
consumed and the attempt number is deterministic, so paired arms draw the
same sequence. A declined range is repaired, so pacing costs time and buys
allowance. `pacing_refusals` counts only the ranges the coin declined that
the cap could have afforded, so coin and cap refusals decompose without
overlap.

**The cap's base (change O).** `selection_policy.cap_base` is
`"accounted"`, the law above, or `"owed"`, under which the denominator is
the bytes the step's plan says this rank will receive. The plan is
`owed_bytes` per (receiving rank, step, sender) in `experiment.json`,
which `generate.py` derives from the same DP All-Reduce sizing it wrote the
traces from: a direct All-Reduce over a group of `G` sends every peer
`2 x B / G` bytes per collective. `close` refuses a run whose launches
disagree with the plan, so the hint is exact or the run is not a result.

**The step stop (change S).** With `selection_policy.step_stop`, legal only
on the owed base, the receiver ends one sender's step once `1 - p` of what
that sender owes it has arrived, and takes the holes that sender left. At
that point nothing new is coming from it, so the exemption has nothing left
to protect and what remains is repair tail. The crossing arrival stops every
open flow from that sender into the rank at once, through
`RdmaHw::StopFlow`, because a flow waiting on a repair receives nothing and
would otherwise wait for its own timeout; the transport also asks at every
accepted arrival, which covers the flows that start after the crossing. The
question carries the cumulative sequence and the bytes already accepted
above it, because under selective repeat a stalled flow keeps taking packets
past the gap; the hole is the size less both, and
charging the whole span above the cumulative sequence would spend the
budget on bytes the receiver already holds. A grant absorbs everything from
the cumulative sequence to the flow size and acknowledges it, so the sender
completes through the `IsFinished` it already had, with no new packet type
and no new sender state. The answer is the whole remainder or nothing,
because the receiver knows the byte count and not which gradient elements
matter, and it is bounded by the cap like every other forgiveness. A
refusal emits nothing, so no exemption ends on it.

Every policy spends the same allowance under the same law, and all are
refused outside a forgiving domain. The coin never applies to the
remainder: pacing exists to keep allowance for the end of the step, and the
stop fires at the end of the step.

**The pure core.** `trim_verdict` and `remainder_verdict` in
`ExperimentConfig.hh` are total functions of a budget entry, a threshold,
and either a pacing rule with a coin or a remainder; they return the
answer and the entry to store. `evaluate_forgiveness` and
`evaluate_remainder` are shells that eliminate a missing or closed entry,
draw the coin, store the answer back and count. `RdmaRangeAlgebra` asserts
the laws directly: an entry that has accounted for everything it does not
spend affords exactly `t / 1000000` of its eligible bytes, the law is
monotone in delivered and in forgiven, an entry that has received nothing
forgives nothing, the coin repeats per (flow, range start), the remainder
is whole or nothing, a coin refusal reports no spent allowance, and a
closed entry is eliminated before any verdict is computed.

**What the gate proves.** `bernoulli_smoke_8` must record a coin refusal
of a range the cap could have afforded, or the rule never cost the arm a
forgiveness. `stepstop_smoke_8` must forgive a remainder, its charged
remainder bytes must equal the transport's `remainder_forgiven` bytes, and
its worst cell must hold the contract's floor. All of them also assert `pacing_refusals == 0` wherever no
Bernoulli rule is in force, and
`forgiven_remainder_bytes <= forgiven_bytes` on every flow.
`check_single_arm_join.py` asserts that one `run.py` arm at a seed
reproduces `compare.py`'s recovery arm at the same profile and seed, byte
for byte in the flow telemetry, which is what makes the single-arm records
joinable against the v1 wave's baselines.
