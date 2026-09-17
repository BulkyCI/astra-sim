# FORGIVE, the whole design in plain words

Written 2026-09-16 for Joe. Every rule the protocol follows and every
assumption it rests on, with nothing left implicit. Where something is
not yet decided or not yet built, it says so.

Joe Fang's work in collaboration with Zechen Ma.

## 1. What we are trying to do

Training a large model on many GPUs spends a lot of its time sending
gradients between them over the network. When the network is congested,
the congestion controller (DCQCN here) slows every sender down, and that
slowdown is most of the time lost to the network. We know from the May
work that training can survive losing a bounded share of gradient bytes
on most steps. FORGIVE uses that tolerance to buy time: the receiver
declines to have some lost bytes re-sent, and while it still has
tolerance to spend, the sender is allowed to ignore the congestion
controller.

## 2. The setting the design assumes

- The network trims packets under congestion instead of pausing senders:
  the payload is dropped, the header still reaches the receiver, and the
  receiver normally asks for a re-send of just that packet (selective
  repeat). No PFC.
- A congestion controller runs at each sender. We use DCQCN and treat it
  as a black box: FORGIVE never changes a line inside it, it only decides
  when the controller gets to hear about congestion.
- The training job is data-parallel: each step, every rank all-reduces
  its gradient with the other ranks of its group. The all-reduce has two
  halves, reduce-scatter (each rank collects its shard's contributions
  from every peer) and all-gather (each rank collects every peer's reduced
  shard). Only this traffic is ever forgiven or exempted; everything else
  (tensor-parallel, pipeline, control) is delivered in full and obeys the
  controller.

## 3. The budget

- One budget per receiving rank per training step, shared across all the
  senders into that rank ("pooled").
- The budget is a fraction `p` of the bytes the rank is owed that step.
  `p` is small (`p_low`, 0.5 %) on steps the training side marks
  critical (steps 1, 2, 3 and 20 in our runs) and larger (`p_high`, 0.1
  to 0.4) on the rest. The list of critical steps comes from the
  training side.
- Every byte the receiver declines to have re-sent is charged to the
  budget. Nothing is ever refunded.
- Guarantee, checked when the step's all-reduce completes, by the
  simulator and again by the analyzer: every rank received at least
  `1 - p` of what it was owed that step. A run that breaks it fails. (An
  earlier "closed" flag on the cell, refusing trims after completion, is
  redundant: a completed step has no open flow to be trimmed, and the
  flow lookup already refuses. It is pruned at the next build.)

## 4. What the receiver does with a trimmed packet

The receiver knows how many bytes of that packet it still lacks (it may
already have some of the range from an earlier attempt). It decides, in
this order:

1. If the flow is not eligible: ask for a re-send.
2. Otherwise flip a coin (see section 5); if the coin says no: ask for a
   re-send.
3. Otherwise check the **soft cap**: may these bytes be forgiven given
   what has vested so far? The vested budget is `p/(1-p)` times the bytes
   the rank has received so far this step, which is the same as `p` times
   (received + forgiven). If the bytes fit: forgive them. The receiver
   marks the range as if it had arrived, acknowledges it, and the sender
   never re-sends it. If they do not fit: ask for a re-send, and note
   nothing about the future, because the vested budget grows as more
   bytes arrive.
4. Whatever the answer, check whether the step's budget is **gone**: it
   is gone when the bytes already forgiven plus the bytes currently
   missing (the receiver's holes: below the highest sequence it has seen,
   not received, not forgiven) plus one packet exceed `p` times the
   step's total. In words: even if every byte now missing were forgiven,
   this step's tolerance would be exceeded. A range trimmed three times
   is one hole, so nothing is counted twice; a hole disappears when its
   repair arrives, so the count falls by itself when the network recovers;
   forgiven bytes and holes are exclusive by construction, because a
   forgiven range is absorbed as received. If gone, the answer includes a
   one-bit report saying so; when the holes drain and the sum falls back
   under the line, the next report says so again, and the sender follows
   whatever the latest report said.

Every acknowledgement of a forgiven range also includes the congestion
mark the trim would have produced, so forgiving never hides congestion
from a sender that is listening.

## 5. The coin (Yashar's pacing)

With Bernoulli pacing at probability `P` (we ran 0.5 and 0.25), a
forgivable trim is forgiven with probability `P` and re-sent otherwise. A
new coin is flipped on every trimmed arrival, so a range refused once gets
another chance on its next trim, against whatever budget has vested by
then. Coin refusals are the receiver's own choice: they count nowhere and
never set the "budget gone" report. Without pacing every affordable trim
is forgiven. The point of the coin is section 6: spending the budget
slowly keeps the exemption alive longer.

## 6. The exemption (ignoring the congestion controller)

- The receiver grants it. On every acknowledgement it sends for an
  eligible flow on a non-critical step, the receiver sets a bit saying
  "this flow may be exempt". The sender obeys its controller until the
  first acknowledgement carrying that bit with the "budget gone" report
  clear; from then on it withholds every congestion signal from the
  controller. One round trip is spent obeying at the start of each flow.
- It follows the latest report. A report that the budget is gone makes
  the sender obey its controller; a later report that it is not gone lets
  it withhold signals again, and the controller raises its own rate on
  its own timers when it hears nothing, so nothing inside it is touched.
  Flapping is not a concern under the holes rule: turning red needs
  `p x owed` of bytes missing at once and turning green needs their
  repairs to have arrived, a real congestion episode each time, not a
  per-packet flicker. Telemetry counts the transitions and the time spent
  obeying per flow.
- A critical step grants it like any other; its small `p` means the pool
  is gone after a few hundred kilobytes and the controller returns almost
  at once. The strict budget does the protecting; there is no separate
  rule.
- The temporal shape, per rank and per step: ignore the controller while
  there is still budget to forgive; when there is almost nothing left to
  forgive, switch to the controller for the rest of the step; the next
  step starts fresh.
- A reference arm ("D") never ends the exemption; it shows the ceiling of
  what ignoring the controller could buy and what it costs the rest of
  the fabric.

## 7. The step stop (Joe's rule)

The receiver counts what it has received from each sender this step. The
moment that reaches `1 - p` of what that sender owes it for the step, it
stops that sender: every open flow from that sender is acknowledged to its
end, the unreceived rest is charged to the budget, and the sender sends
nothing more. It is a budget decision at the receiver and nothing else:
no timer, no view of the line, no check that the sender has finished. It
fires near the end of the step because that is when `1 - p` arrives.

## 8. What travels on the wire

Nothing new on the data path. Two bits on existing acknowledgements and
re-send requests: "budget gone" and "this flow may be exempt". The stop
uses an ordinary acknowledgement whose sequence number is the flow's
size.

## 9. What the receiver has to know, and where it gets it

| it needs | for | source |
| --- | --- | --- |
| how many bytes it has received and forgiven, per step and per sender | the soft cap, the stop | its own counters |
| each flow's size | forgiving a flow's remainder, the stop | the message descriptor, already on the wire |
| which step a flow belongs to and whether the step is critical | choosing the budget and `p` | the training side, one tag per message or per collective and one bit per step |
| what each sender owes it this step | the hard cap, the stop | the training side's bucket table at step start (see 11, item 4) |

The sender needs nothing. It obeys bits.

## 10. What the simulator does that a real system would not

- It keeps a sender-side count of bytes launched toward each rank each
  step (`eligible`) purely to certify at the end of the step that the
  guarantee in section 3 held and that the owed table matched reality.
  No decision reads it.
- The coin is a hash of the flow's identity, the range and an attempt
  counter, seeded per run, so that paired experiments draw the same
  coins. A real receiver would use any random source.
- The simulator has no gradient values. It moves bytes. Every statement
  about training surviving the loss is inherited from the May GPT-2 runs,
  never measured here.

## 11. Every assumption, in one list

1. **Tolerance.** Training survives losing up to `p` of each rank's
   gradient bytes on non-critical steps. Evidence: DBLP's May runs, 40 %
   on non-critical steps, GPT-2 scale, no evidence for larger models.
2. **Critical steps are known.** The training side can name them. We use
   steps 1, 2, 3 and 20.
3. **The application repairs the holes it is told about.** The receiver
   hands the application the forgiven ranges of every completed message
   (it already keeps them). The application then does three things, each
   a few lines in a training framework: in the reduce-scatter it divides
   each element by the number of contributions that arrived; in the
   all-gather it fills a missing summed value with its own local gradient
   for that element, scaled the same way; and it may re-synchronise
   parameters across the group every K steps with a lossless broadcast
   or average, which cancels the small per-rank differences the
   all-gather fills leave behind. The drift between syncs is the local
   SGD regime, where convergence with tens to hundreds of steps between
   syncs is established (Stich 2019, Lin et al. 2020, FedAvg), so the
   sync is a safety margin rather than a requirement; it costs about
   17.5 GB per rank under TP 8, roughly four of our steps, 0.4 % at
   K = 1 000, never falls inside a 20-step window, and is a written
   sentence here with K a parameter of the GPT-2 injection experiment.
   What the May code did with a missing all-gather value is not known. With these three, the
   pooled budget is sound: only the aggregate loss matters for where
   training converges, which sender lost is a variance term, and the two
   halves of the all-reduce need no separate budget. The May code did
   none of the three, so its 40 % is a conservative bound.
4. **The step's totals per sender are known at step start.** In a real
   system the bucket table is fixed after the first step and the
   collective library has it. In the simulator the flat formula for
   ASTRA-sim's schedule was wrong at 64 ranks (it sends `5 x B/16` per
   peer, not `2 x B/8`); how the simulator supplies the table is not yet
   decided (a pre-pass over ASTRA-sim's own collective code, or the
   previous step's counts). This is the one open item that blocks the
   next wave.
5. **Data shards are IID across ranks.** This is what makes assumption 3
   enough: with heterogeneous shards, uneven loss across senders biases
   the result in proportion to the heterogeneity even with rescaling.
6. **Both halves of the all-reduce share one budget.** FORGIVE does not
   tell reduce-scatter from all-gather; on the literature's assurance
   about bounded drift (assumption 3) one `p` covers both. Measured only
   by the GPT-2 injection experiment.
7. **The congestion controller is a black box** and any controller would
   do; we chose DCQCN for convenience. The exemption only withholds
   signals at the three places the transport hands them over.
8. **The fabric trims and repairs selectively.** Under go-back-N the
   costs change (a re-send rewinds a window) and the stop would matter
   more; not measured under v2.
9. **Sizes are the same every step.** Needed by assumption 4 in either
   form, and by the certification.
10. **Flow sizes are known to the receiver.** True for RDMA and UEC
    message descriptors.

## 12. What is measured, what is not, and what is next

- Measured and standing: v1 at budget 0.1 (12.9 to 14.1 % of training
  time for 6.75 to 6.89 % of gradient bytes); the coin at 0.25 (16.0 to
  16.2 % for 5.5 to 5.9 %, with far fewer flows losing the exemption);
  the mask keeping critical-step loss at 1.4 %; the mild cell; the
  go-back-N result.
- Not yet measured: the v1 point under the full package above (soft and
  hard caps, receiver-granted exemption, fresh coin); the stop; arm D;
  the coin on the hard-cap-only ablation; budget 0.05 and the coin at
  0.1 and 0.05 (#125, running); the zero-tolerance, obey-DCQCN and
  no-controller references (#126, running).
- Next, in order: decide item 4, re-dispatch #127; read #125, #126, #127
  together with TP-collective time and re-sent bytes per arm; then the
  GPT-2 injection experiment, which is where assumptions 1, 3, 5 and 6
  stop being assumptions, with K as one of its parameters.
