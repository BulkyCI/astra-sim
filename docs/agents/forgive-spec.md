# FORGIVE: the protocol specification

The rules of FORGIVE as built at main `59cf16c` and ns-3 `3e11ace49`,
stated once. Every other document that describes the protocol defers to
this one; where another document disagrees, that document is wrong.
[forgive-design-plain.md](forgive-design-plain.md) says the same things
in plain words with the assumptions; this file is the reference.

Joe Fang's work in collaboration with Zechen Ma.

## 1. Terms

| term | meaning |
| --- | --- |
| rank | one GPU; the receiver in what follows |
| step | one training iteration |
| cell | the receiver's budget for one step, shared by every sender into it |
| sender | one peer rank sending part of the step's all-reduce to the receiver |
| flow | one message from one sender to the receiver, one RDMA queue pair |
| packet | 4 096 B of a flow's payload; the unit the switch trims |
| range | the bytes of one trimmed packet the receiver still lacks; the unit it decides on |
| hole | bytes below the highest sequence the receiver has seen on a flow, neither received nor forgiven |
| owed | the bytes a sender will send the receiver in a step, from the collective library's plan; summed over senders it is the cell's total |
| p | the step's tolerance: `p_low` on critical steps, `p_high` elsewhere |
| received | bytes the receiver has accepted for the cell, credited per packet |
| forgiven | bytes the receiver has declared it does not need, charged to the cell |

## 1b. Containment and counts, from the worst-cell profile

The numbers are those of the 64-rank `direct7` profile every #123 to
#127 arm ran (TP 8, DP 8, Llama 3 70B, 20 steps, 4 096 B packets);
other profiles change the counts, not the containment. `direct7` means
the all-to-all schedule with all 7 DP peers sending at once, the most
incast a group of 8 can produce; it is the stress case. NCCL's default
ring and tree schedules receive from 1 or 2 peers per channel, which the
`direct2` cell (fan-in 2) approximates, and that cell's figures are the
ones to map onto a production library.

| level | contains | count in the profile |
| --- | --- | --- |
| run | steps | 20 |
| step | one cell per rank | 64 cells per step, 1 280 per run |
| cell (receiver, step) | senders: the rank's DP peers | 7 |
| sender to receiver, per step | flows | 10: the step's all-reduce is 5 streams of 17 089 843 B, each a reduce-scatter and an all-gather phase, one flow per phase per peer |
| flow | packets | 2 136 230 B, 522 packets (521 full, one of 2 214 B) |
| packet | ranges | at most 1: a range is the part of one trimmed packet the receiver still lacks |

Totals that follow: `owed_from[sender]` = 21 362 300 B per step;
`owed` per cell = 149 536 100 B; 70 flows into each rank each step;
89 600 DP flows per run. TP traffic (the other 286 720 flows of a run)
and the 7 microburst flows are outside every rule.

What each rule acts on:

| rule | granularity |
| --- | --- |
| the budget, the gone report, certification | the cell |
| the stop | one sender's 10 flows into the cell |
| the coin, the soft cap, forgiveness | one range |
| holes, `highest_seen_end`, the eligible bit | one flow, summed to the cell for the report |
| the exemption | one flow at the sender, following that flow's reports |

## 2. Invariants

1. **Budget.** Per cell, `forgiven <= p x owed` at every moment, and at
   the step's completion the receiver has received at least `1 - p` of
   what it was owed. Certified by the simulator (a throw) and the
   analyzer (a failed arm).
2. **Monotone.** `received`, `forgiven` and `owed` never decrease within
   a step; nothing forgiven is refunded. Holes are the only quantity
   that falls.
3. **Exclusive.** A byte is received, forgiven, a hole, or not yet seen;
   never two of these. A forgiven range is absorbed as received, so it
   is not a hole; a late packet for a forgiven range is dropped.
4. **The receiver decides.** Forgiveness, the report, the grant and the
   stop are the receiver's; the sender obeys two bits and computes
   nothing about the budget.
5. **The controller is untouched.** The sender withholds or delivers
   congestion signals at the three places the transport hands them to
   whichever controller is configured; no line inside a controller
   changes.
6. **Nothing new on the wire.** Two flag bits on the existing
   acknowledgement and repair request: "budget gone" and "this flow may
   be exempt". The stop is an ordinary acknowledgement at the flow's
   size.
7. **Eligibility.** Only DP all-reduce payload is ever forgiven,
   exempted or stopped. Everything else is delivered in full under the
   controller.
8. **Coins are the receiver's own.** A coin refusal charges nothing,
   counts in no rule, and never sets a bit.

## 3. The scheme

Training on a fabric that trims packets loses most of its network time to
the congestion controller's rate cuts, not to repairs. The receiver
knows what it needs and what it has. It tolerates losing at most `p` of a
step's bytes, and while that tolerance lasts it licenses its senders to
ignore the controller. Forgiveness is the currency; the licence is what
the currency pays for; pacing spends the currency slowly so the licence lasts
the step. When the tolerance is exhausted, or the fabric has already lost
more than the tolerance could ever absorb, the licence ends for the rest
of the step. Once the receiver has enough from a sender, it tells that
sender to stop. Every rank is certified, every step, to have received at
least `1 - p`.

## 4. State

Per cell (receiver, step): `owed`, `owed_from[sender]`, `received`,
`received_from[sender]`, `forgiven`, `holes` (the sum over open flows),
`collectives_total`, `collectives_completed`.

Per flow at the receiver: the accepted set (received and forgiven ranges,
exclusive), `next_expected`, `highest_seen_end`, and the eligibility
flag.

Per flow at the sender: `exempt` (a bool), the last report seen, the
count of report transitions, and the time spent obeying.

Parameters per profile: `p_low`, `p_high`, the critical-step set,
`pacing = none | bernoulli{P}`, `step_stop`, and the two ablation
switches `cap_base = accounted | owed` and `reengage`.

## 5. Stages, per receiver and per step

A cell passes through these stages; a sender's flows follow their cell.

| stage | the sender | the receiver | leaves when |
| --- | --- | --- | --- |
| **Opening** | obeys its controller | forgives under the rules of section 6; marks its acknowledgements eligible on any step with `p > 0` | the sender's first acknowledgement arrives with the eligible bit set and the gone bit clear: the sender enters Forgiving |
| **Forgiving** | withholds every congestion signal from its controller | forgives, repairs, reports | a report with the gone bit set: the sender enters Controlled |
| **Controlled** | delivers every congestion signal to its controller | forgives under the same rules, repairs, reports | a report with the gone bit clear: the sender returns to Forgiving |
| **Stopped** (per sender) | has nothing left to send to this receiver this step | has told the sender to stop | the step ends |
| **Certified** | | checks the invariant at the step's last collective completion | the next step opens a fresh cell |

The transition standard is one inequality, evaluated when each
acknowledgement or repair request is emitted:

```
gone  <=>  forgiven + holes + 4096 > p x owed
```

Red means the step's tolerance is used up, or the fabric has already
lost more than the tolerance could ever absorb (holes count each missing
byte once and fall as repairs arrive, so the count recovers by itself).
Green is the same inequality false. There is no latch and no
hysteresis: the sender is exempt exactly when the last report it received
said green. Under `reengage = false` (arm D) the sender ignores red.

Critical steps are not a separate stage: they run the same stages with
`p_low`, so the gone line is crossed after a few hundred kilobytes and
the controller returns almost at once.

## 6. Rules per event

**A packet arrives.** The receiver credits the newly accepted bytes to
`received` and `received_from[sender]`, advances `highest_seen_end`, and,
if `step_stop` is on, asks whether the sender may be stopped (rule
"Stop" below). Every acknowledgement it sends includes the eligible bit
(if the flow is eligible and the step's `p > 0`) and the gone bit (the
inequality of section 5).

**A trim header arrives.** The receiver advances `highest_seen_end`,
computes the range it still lacks, and decides in this order:

1. Not eligible: repair.
2. Pacing is Bernoulli and a fresh coin, `hash(flow, range, attempt)`,
   falls above `P`: repair. The readout counts it as a pacing refusal
   when the cap could have afforded it; no rule reads that count.
3. The soft cap: forgive if `forgiven + range <= p x (received + forgiven)`,
   i.e. `forgiven + range <= p/(1-p) x received`. The range is absorbed
   as received, charged to `forgiven`, and acknowledged; the
   acknowledgement includes the congestion mark the trim would have
   produced, so forgiving hides no congestion from a sender that is
   listening. Otherwise: repair, and say nothing, because the cap grows
   as bytes arrive.

Under the ablation `cap_base = owed` step 3 reads
`forgiven + range <= p x owed` instead.

**Stop.** With `step_stop` on, when `received_from[sender] >= (1 - p) x owed_from[sender]`,
the receiver acknowledges each of that sender's open flows to its end,
charges each flow's remaining hole to `forgiven` if it fits the step's
pool, `forgiven + remainder <= p x owed`, and the sender completes those
flows without sending more. A remainder that does not fit is not
stopped; the sender keeps sending and is stopped when it fits. The stop
never sets a bit of its own; the gone bit on its acknowledgement is
whatever the inequality says, and the stopped sender has nothing left
that depends on it.

**A report arrives at the sender.** The sender reads the gone bit on
every acknowledgement and repair request that includes the eligible bit.
Red and exempt: deliver signals from now on, count a transition. Green
and not exempt: withhold from now on, count a transition (the first
green is the grant). Otherwise nothing.

**A late packet arrives for a forgiven range.** Dropped; the bytes are
counted as `late_forgiven_bytes`, and the reported loss is
`forgiven - late_forgiven_bytes`. The charge to the cell stands.

**The step's last collective completes.** Certify: `forgiven <= p x owed`
and the launches equal the plan, else the run fails.

## 7. What the application does

Assumed, not built, stated in the specification:

1. It receives, with each completed message, the list of forgiven
   ranges (the receiver keeps them as the absorbed set).
2. In the reduce-scatter it divides each element by the number of
   contributions that arrived.
3. In the all-gather it fills a missing element with its own local
   gradient for that element, scaled the same way.
4. It may re-synchronise parameters every K steps over a lossless
   transfer; between syncs the replicas drift within the local-SGD
   regime. About 17.5 GB per rank under TP 8, four of our steps, 0.4 %
   at K = 1 000.

With these the pooled budget is sound for IID shards: only the aggregate
loss matters for where training converges, and which sender lost is a
variance term. DBLP's May runs converged at 40 % loss on non-critical
steps with none of the four, on GPT-2; that is the tolerance evidence and
its conservative bound.

## 8. What the simulator does that a NIC would not

- `owed` is computed by ASTRA-sim's own collective code before the run
  (a real receiver gets the same table from the collective library at
  step start).
- A sender-side launch count, `eligible`, exists only so the certification
  can check the plan against the launches. No decision reads it.
- The coin is a seeded hash so paired arms draw the same coins.
- No gradient value exists anywhere; every training claim rests on the
  GPT-2 runs.

## 9. Telemetry

Per flow: `forgiven_bytes`, `forgiven_remainder_bytes`,
`late_forgiven_bytes`, `soft_refusals`, `pacing_refusals`,
`allowance_gone_reports`, `cc_exempt`, `cc_exempt_granted_ns`,
`cc_transitions`, `cc_obeying_ns`, `cc_signal_withheld`. Transport
events: `trim_forgiven`, `remainder_forgiven`, `cc_exempt_granted`,
`cc_transition`, `cc_signal_withheld`, `allowance_gone_reports`. Per
cell, from the analyzer: the ledger law with `min_delivered_share` and
its worst cell. Derived, never counted: trimmed-forgiven bytes
(`forgiven - remainder`), actual loss (`forgiven - late`).
