# CI run #117 wave readout

Run #117 is commit `414dc70c51ff`, workflow run 33526691181, ledger issue
#64, release `zuihrl5stp6ulacoogghyp4loy7xsjpj`. I wrote this on 2026-09-05
with the run still open: 30 of 31 comparisons collected, the 64-rank pp2
control still simulating (guard expires 2026-09-06 07:59 UTC), so the
aggregate jobs and the ledger close have not run. The sources are the ledger
comments on #64, `comparison.json`, `transport_summary.csv` and
`collective_events.csv` streamed from the 30 release bundles, local re-runs
of `compare.py --aggregate-inputs` and `fan_in_sweep.py`, the DBLP paper
(arXiv:2605.01989), and this directory's records. A referee pass over an
earlier draft of this document is in
[run-117-referee-pass.md](run-117-referee-pass.md); the objections it raised
are folded in below and cited by marker.

This is not a data readout. The numbers are here, but the questions I am
answering are the ones a reviewer will ask: does this approach offer
relief, how much, under what condition, and what is the contribution.

## What the paper claims and what we actually built

DBLP's claim is about the burst. A fixed small loss tolerance forces many
retransmission rounds during a loss burst; a receiver that knows the step
is not critical stops recovery once enough has arrived, and the burst
iteration finishes 4 to 6 times sooner (Tables II to VI in the paper), with
17 to 34 % less training time overall because 40 % of every non-critical
gradient never has to arrive at all. The evidence is three workers and one
server over UDP with TCP control, loss injected at 60 to 90 % on chosen
iterations, CIFAR-scale CNNs and GPT-2-S. The paper was conceived for a
commodity fabric where loss is silent and recovery is expensive.

The fabric we simulate is neither. UEC trimming signals every loss with a
64-byte header and the transport repairs it; there is no silent loss and no
unacknowledged byte. And the policy we built is not the paper's: it
substitutes a 64-byte provenance flow for a random 0.5 % or 10 % of DP
All-Reduce payloads at admission, before the network has seen them. It
never declines a repair. So the experiment tests the paper's *phase signal*
(protect critical steps, relax elsewhere) attached to the paper's *bandwidth
half* (never send some of the gradient), on a fabric where the paper's
*recovery half* (stop retransmitting early) has no analogue yet. That
distinction is the whole reading of this wave.

The matched design is as tight as claimed. Every arm of a seed shares
traces, topology, burst, CLR mask and RNG stream; within one profile the
three arms are nested, a decision selected at 0.005 is selected at every
higher threshold; and the per-collective telemetry shows steps 1 to 3, the
CLR steps where all three arms hold the strict bound, bit-identical between
fixed-low and policy in 16 of 16 anchor seeds. When the arms diverge, it is
the treatment.

## What was settled before this wave

Four of the objections a reader of the paper raises first were worked
through in July and are already in the design, and the wave inherits them
rather than re-litigating them.

- Sparsification. The paper's transport drops gradient chunks silently
  underneath whatever compression or error-feedback state the optimizer
  keeps (known-flaws register, item 2). We settled it by scope: this is a
  pure-drop study with no compression layer, the CLR evidence record
  separates pure-drop tolerance from compression-with-error-feedback
  tolerance explicitly, and no claim here touches optimizer semantics.
- Compute and transport interleaving. The paper's baseline is
  stop-and-wait, so its end-to-end gains include network time that a real
  framework hides (item 1). Our trace is a production-shaped overlapped
  window: TP=8 all-reduces interleaved with 5.4 ms of compute per node,
  two accumulation steps, one representative DP gradient bucket of 256 per
  step. What it does not replay is a full backward pass, so exposed
  communication is a design parameter of the window rather than a
  measurement of a framework. Every makespan number here is a
  communication-window makespan and is labelled as such.
- CLR identification. The paper detects the critical regime from a
  gradient-norm drop, which ASTRA-sim cannot compute. We pinned an
  explicit schedule, steps 1 to 3 and 20 of 20, derived from literature
  independent of DBLP (the circularity guard in the CLR evidence record),
  and the phase-aware policy reads that mask. Step 20 is the schedule's
  weakest-evidenced element and is stated as a hedge.
- Topology. The paper's prototype is three workers and one server, a
  hub-and-spoke that concentrates pressure at one NIC (item 5). We run
  decentralised ring and windowed direct collectives on rail-optimised Clos
  fabrics across a health spectrum, healthy 1:1, degraded 4:3 and designed
  2:1, and the microburst is an explicit seven-source incast rather than an
  injected loss rate.

Those four are why the comparison is a matched three-arm design on a modern
fabric at all. What they do not settle, and what this wave was for, is
whether the mechanism survives the move.

## Does it offer relief, and how much

Three regimes, one measure. W is trimmed-payload bytes per offered byte,
computable from `transport_summary.csv` in every arm, and it separates the
families cleanly.

| Family | W (fixed-low) | Policy makespan relief | Burst-step relief |
| --- | ---: | ---: | --- |
| 16-rank anchor, 16 seeds, 2:1 Clos, go-back-N (Storm) | 8.7-10.4 | +3.91 %, CI [1.13, 6.68] % | 116 ms mean, CI +/-229 ms |
| 32-rank burst sweep 0/2/4/7, healthy 1:1, go-back-N (Knee) | 2.1-3.0 | 8.9 / 4.1 / 2.9 / 0.8 %, one seed | shifts between steps 18 and 19 |
| 64-rank fan-in 1/2/4/7, degraded 1:1, go-back-N (Knee) | 1.3-2.6 | 0.1 / 4.3 / 1.5 / 11.1 %, one seed | not resolvable, one seed |
| 64-rank sr2x, 2:1, selective repair (Light) | 0.02 | 0.78 % | every per-step delta within +/-4 ms |

The anchor is the only family with a confidence interval, and it clears
zero on makespan (291.6 ms of 7145 ms) and on DP operation-span p99
(153.4 ms of 1026 ms, CI [5.0, 301.7]); per-rank p99 spans zero. Fixed-high,
which sheds through the critical steps, gets 9.42 % on makespan and loses on
every tail metric. The sixteen seeds came in at sd 5.21 %, better than the
7.19 % I sized for.

Now the question the paper actually asks. Decomposing the same sixteen
seeds by training step:

| Steps | Fixed-low span | Policy span | Delta | Note |
| --- | ---: | ---: | ---: | --- |
| 1-3 (CLR) | 345 / 280 / 256 ms | identical | 0.0 ms, 16/16 seeds | fixed-high: 203 / 189 / 247 ms |
| 4-17 (permissive, no burst) | 191-305 ms | 176-295 ms | +239 ms summed; per step +20 to +54 ms, each CI spanning zero | 84 % of the makespan relief |
| 18 (burst) | 771.8 ms | 656.0 ms | +115.8 ms, sd 430, CI +/-229 ms | per-seed from +1080 to -485 ms |
| 19 (aftermath) | 734.8 ms | 792.6 ms | -57.8 ms, CI +/-185 ms | the storm outlives the burst |
| 20 (CLR) | 283.1 ms | 296.8 ms | -13.7 ms | history differs by then |

So the answer to "how much" is in two parts. The admission policy relieves
the steady state: about 30 ms per permissive step, accumulated over fourteen
steps, on a fabric whose go-back-N recovery re-sends every offered byte nine
to ten times. At the burst episode, the one place DBLP claims to act, the
policy's effect is not resolvable with sixteen seeds; resolving a 116 ms
effect against a 430 ms seed spread would take about 60 seeds, and the
aftermath step moves the other way. In the Knee families the burst-step
delta is a single seed and flips sign between steps 18 and 19 (32-direct:
-525 ms then +769 ms), which is timing, not relief. Under selective repair
there is nothing at any step.

The extent, then: single-digit percent on makespan, only where the recovery
algorithm has manufactured a retransmission storm, and no demonstrated
relief of the burst tail anywhere. That is the honest number, and it is
smaller than the paper's for a reason I can now name.

## Why: the mechanism gap and the fabric gap

The relief we do measure has a mechanism I can point at, and it is not the
paper's. Shedding 1.98 GiB of the anchor's 166 GiB offered load took 156 GiB
off the wire, a marginal amplification of 79x; across seeds the makespan
relief correlates 0.94 with the policy's trim reduction, and the three seeds
where the policy added trims are the three negative seeds. Byte reduction is
flat across seeds and predicts nothing. This is consistent with, though not
proof of [O2], relief flowing entirely through avoided retransmission
chains: the policy lowers offered load a little, and go-back-N turns a
little less load into a lot less waste. It is a bandwidth lever with a
convex payoff, acting in the steady state.

The paper's lever is different. DBLP does not lower offered load before the
burst; it declines recovery during the burst, when the network has already
said which packets it could not carry. That is evidence-informed loss at
the moment the tail is being formed. Our admission policy sheds blind,
before the burst, uniformly over the step, so it cannot concentrate its
relief where the tail is. The per-step table is what that looks like:
relief everywhere except the one step that matters.

The fabric gap is worse for us than the mechanism gap. The Storm regime
that gives the anchor its confidence interval is produced by go-back-N: the
same 2:1 fabric family under selective repair shows W of 0.02, seventy
times fewer trims, and the policy relieves nothing [O6]. UEC pairs trimming
with selective retransmission; go-back-N on a trimming fabric is a
recovery algorithm the specification does not intend. Every number in this
programme's anchor family is therefore conditional on a baseline transport a
modern fabric does not run, and a reviewer who knows the fabric will say so
first. What survives under selective repair is only the burst episode
itself: a queue that overflows, trims, and repairs once. That is the paper's
regime, and it is the one regime our mechanism cannot reach.

The dose grid says the same thing from the other side, with the caveat that
its four points share a seed but not a selection stream (the profile name is
hashed into every decision, so their fixed-low baselines differ), and each
is one seed [O4]. The byte lever arrives as dosed (8, 16, 32, 48 % of DP
bytes shed) and makespan relief rises to 8.4 % and 12.1 % at 0.4 and 0.6,
while span p99 is negative at every dose above 0.1 and fixed-high at 0.6
loses 84 % on both tails. More blind shedding buys steady-state makespan and
sells the tail. That is what a bandwidth lever does.

## The two points from the last meeting

The collaborator's notes on 18 August were "10 % incast: increase incast"
and "mean reduction 50 % anomaly". The wave answers both.

Increasing the incast was the burst-source sweep and the dose grid. More
burst sources gave less relief, not more (8.9, 4.1, 2.9, 0.8 % makespan at
0, 2, 4, 7 sources), because the fabric self-congests under go-back-N
before any burst arrives and the burst is a small perturbation on top; and
raising the dose from 10 % to 60 % bought makespan and sold the tail. The
suggestion assumed the incast was the congestion. The counters say the
recovery algorithm is.

The 50 % anomaly is the per-rank p99 estimand. It is the top three of 320
samples, so one extra ECMP collision moves it by half. With sixteen seeds
its paired deltas run from -395 ms to +278 ms on a 756 ms base, which is
-52 % to +37 %, with a CI spanning zero; the single-seed values of -108 %
and +73 % in the 32-rank arms are draws from that same spread. It is not an
anomaly of the mechanism. It is the noise floor of an estimand this design
cannot resolve, which is why the decisive experiment below moves the
primary estimand to the burst step.

## What went well

The harness held for the first time. Every cluster arm outlived the 24-hour
runner-token wall that ended #116; 30 of 30 arms passed the congestion gate
with attested complete streams (about 43 TB hashed and discarded); four arms
that also completed in #116 reproduced to the printed digit on rebuilt
binaries. The pre-registered pi-chunk seeds, the nested arms, and the
bit-identical CLR steps make the matched comparison stronger than anything
in the source paper. The waste-term counters turned an unexplained 4 % into
a mechanism with a size, and the sr2x canary completed and showed what
selective repair does to that mechanism. Those two facts are the wave's
contribution to the programme, and they are worth more than the confidence
interval.

## What went wrong, in the order it matters

1. The pre-registered primary estimand has never produced a signal. Per-rank
   p99 spans zero in every regime and every wave; it is dominated by ECMP
   timing at this scale and the design cannot resolve it [O8]. The burst-step
   and aftermath-step span are the estimands the paper's claim needs and the
   protocol does not name.
2. The anchor's baseline transport is not the fabric's transport. Go-back-N
   makes the Storm; selective repair removes it [O6]. There is no
   selective-repair arm in any family with a burst.
3. The wave has no negative control. burst0, which the matrix calls one, is
   a Knee-regime fabric that congests itself (W 2.23 with no burst); the
   protocol's `no_incast_8.json` did not run [O9]. The "supported policy
   benefit" verdict is conditional on it and on go-back-N, and should say so
   in the same sentence [O5].
4. The dose grid and the burst4 pair are unmatched across profiles because
   `run_id` enters the selection hash (`ExperimentConfig.hh`). A one-line
   fix, but the grid's cross-dose readings are noise-limited until it is
   rerun with a shared identifier and seeds [O4].
5. The pp2 arm, the only carrier of non-sheddable pipeline traffic and hence
   of the 3D-parallel realism argument, has never completed in three waves
   [O11].
6. The sixteen-seed aggregate job will fail on an absolute-profile-path
   equality check in `compare.py` when pp2 ends, so the run will conclude
   failure with 31 clean arms; the numbers above are what it would have
   produced.

## Can it withstand review

The referee pass returned major revision: no fatal objection, six major.
Read as a whole they say one thing. The document, and the programme behind
it, claims tail relief and measures steady-state relief; the mechanism is
argued from correlation; the strongest result is conditional on a recovery
algorithm the fabric does not use; and the claims that generalise (no
channel under selective repair, dose is not the amplifier) rest on one seed
each. None of these is a flaw in the harness or the statistics. They are
all the same gap: the experiment has not yet put the paper's mechanism on
the modern wire.

Two objections go to the premise rather than the data. The phase-tolerance
premise (40 % additional loss outside the critical regime is harmless)
comes from CIFAR-scale CNNs on three workers and cannot be tested in
ASTRA-sim [O10]; every claim here must be conditional on a tolerance
oracle, and none should depend on the premise holding for a 70B-class
model. And "the bound is doing work" conflates metrics [O7]: fixed-high wins
makespan in the Storm and loses tails everywhere; per metric, the bound
costs makespan and protects tails, which is the trade it was designed to
make.

## How to frame the contribution

Three framings are on the table.

The one the programme has been carrying, "phase-aware admission shedding
relieves congestion by 4 to 11 % on a UEC fabric", does not survive O1, O5
and O6. It measures the wrong step, on the wrong recovery algorithm, and
its best number is a bandwidth effect.

The one the data supports today is a regime paper: where can a bounded-loss
transport help on a modern lossy-Ethernet fabric, and where can it not. Its
findings are already in hand and each is a real result. Relief from
admission-time shedding is a property of the recovery algorithm, not of the
training phase, and it vanishes when repair is selective. Admission-time
shedding cannot reach the burst episode, because it acts before the
network has said anything. The waste ratio W places any fabric in one of
three regimes and predicts whether there is anything to relieve. And the
paper's own headline, relief at the burst iteration, is the one estimand
the mechanism leaves untouched. This reframes DBLP for the fabric it was
not designed for: the phase signal is still the interesting idea, but on a
wire that signals and repairs every loss the only decision left for it to
inform is whether to repair, so bounded loss on a modern fabric must be a
recovery-time decision or it is a bandwidth trick.

The one worth the next six months is the protocol paper that follows from
that: recovery-domain bounded loss on UEC, where the trim notification
itself is the trigger and the receiver, which owns the phase signal,
declines the repair of trimmed DP ranges outside the critical regime under
the same byte budget the admission policy had. Its claim is the paper's
claim, tail relief at the burst, tested on the paper's own estimand with a
selective-repair baseline. Whether it holds is an open empirical question,
and the anchor's counters bound the prize: the burst step and its aftermath
are 1.5 s of a 7.1 s run, three times the span of any other step.

My recommendation is to write the second and build the third. The second is
honest about what the admission mechanism is, and it is the argument that
makes the third necessary rather than incremental.

## The decisive experiment

One wave, designed around the objections rather than around more seeds.

- Fabric: the 32-rank 1:1 rail fabric with the 7-source step-18 burst, run
  under selective repair, so W starts near zero and the only congestion is
  the episode itself. This answers O3 and O6 at once.
- Arms, matched and nested as now: no shedding; admission shedding at the
  current bound; recovery-domain forgiveness at the same byte budget. The
  third arm is the intervention O2 asks for, fixing shed bytes and varying
  where the decision is made.
- Estimands, pre-registered: span and per-rank p99 of the burst step and of
  the aftermath step, then makespan. Per-rank p99 over the whole run is
  demoted to a diagnostic [O8].
- Control: `no_incast_8.json` in the same wave [O9].
- Seeds: pi chunks 17 onward, eight per arm; the Knee's seed spread is
  unknown and eight is the minimum that gives a CI at all.
- Harness before the wave: `run_id` out of the selection hash or shared per
  family, the aggregate profile check by relative path, and W printed next
  to the trim counts in every report.

If forgiveness relieves the burst step under selective repair with a CI
that clears zero, the programme has the paper's result on the modern wire
and the protocol paper writes itself. If it does not, the regime paper's
conclusion stands as the finding: bounded loss has no purchase on a fabric
that repairs cheaply, and the phase signal belongs in scheduling rather
than in transport, which is where the source paper's own future-work
section already points.

## Integrity of the record

- 30 of 30 arms passed the congestion gate; 30 of 30 streams attested
  complete (332 to 665 segments, 356 to 2057 GiB per arm).
- 70 release assets, 1.17 GB; every bundle carries `attestation.json` with
  the binary sha256, ISA level, node, and stream digests. Three arms ran on
  the x86-64-v3 binary, the rest on x86-64-v4; the anchor mixes two of
  sixteen seeds from the other build.
- Simulator wall hours: 64-rank fan-in 45 to 56 h, anchor seeds 37 to 49 h,
  32-rank arms 23 to 38 h, sr2x 11 h, pp2 still open past 83 h.
