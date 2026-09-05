# CI run #117 wave readout

Run #117 is commit `414dc70c51ff`, workflow run 33526691181, ledger issue
#64, release `zuihrl5stp6ulacoogghyp4loy7xsjpj`. I wrote this on 2026-09-05
with the run still open: 30 of 31 comparisons collected, the 64-rank pp2
control still simulating (guard expires 2026-09-06 07:59 UTC), so the
aggregate jobs and the ledger close have not run. Sources: the ledger
comments on #64; `comparison.json`, `transport_summary.csv` and
`collective_events.csv` streamed from the 30 release bundles; local re-runs
of `compare.py --aggregate-inputs` and `fan_in_sweep.py`; the DBLP paper
(arXiv:2605.01989) as the origin of the idea; and this directory's records.
A referee pass over an earlier draft is in
[run-117-referee-pass.md](run-117-referee-pass.md); the objections that
carry over are cited by marker.

## What we are testing

DBLP is two known things put together. One is Accordion's observation that
a network being trained can lose a bounded fraction of its gradient data
and still converge, with the tolerable fraction depending on the training
phase: small in a critical learning regime, large outside it. The other is
a lossy transport, which is commonplace in networking. Combine any
implementation of the two and you have DBLP more or less; the paper's own
prototype, UDP chunks with TCP control on three workers, was one such
combination and is now outdated as a transport. Our transport is the
programme's own, a UEC-shaped trimming fabric, by decision made in July.

What this wave simulates is the Accordion half on that transport. A pinned
critical-step schedule (steps 1 to 3 and 20 of 20) stands in for the
gradient-norm detector, and a phase-aware policy applies a low tolerance
(0.5 %) inside it and a high tolerance (10 %, up to 60 % in the dose grid)
outside it, taking the loss at admission: a selected DP All-Reduce payload
is replaced by a 64-byte provenance flow and never enters the network. The
matched comparison holds everything else fixed: the fixed-low arm keeps the
low tolerance everywhere, the fixed-high arm keeps the high tolerance
everywhere including the critical steps, and all three arms of a seed share
traces, topology, burst, schedule and RNG stream. Within a profile the arms
are nested, a decision selected at 0.005 is selected at every higher
threshold, and the per-collective telemetry confirms it: the critical steps
1 to 3 are bit-identical between fixed-low and policy in 16 of 16 anchor
seeds.

The question is not whether we reproduce the paper's numbers. It is whether
phase-aware loss tolerance makes the network healthier, by how much, under
which conditions, and at what price.

## What was settled before this wave

Four of the objections a reader raises first were worked through in July
and are already in the design.

- Sparsification. Accordion and DBLP sit underneath whatever compression or
  error-feedback state the optimizer keeps (known-flaws register, item 2).
  We settled it by scope: this is a pure-drop study with no compression
  layer, the CLR evidence record separates pure-drop tolerance from
  compression-with-error-feedback tolerance explicitly, and no claim here
  touches optimizer semantics.
- Compute and transport interleaving. The paper's baseline is
  stop-and-wait, so its end-to-end gains include network time a framework
  hides (item 1). Our trace is a production-shaped overlapped window: TP=8
  all-reduces interleaved with 5.4 ms of compute per node, two accumulation
  steps, one representative DP gradient bucket of 256 per step. It does not
  replay a full backward pass, so every makespan here is a
  communication-window makespan and is labelled as such.
- CLR identification. Accordion detects the regime from a gradient-norm
  drop, which ASTRA-sim cannot compute. We pinned an explicit schedule
  derived from literature independent of DBLP (the circularity guard in the
  CLR evidence record); step 20 is the schedule's weakest-evidenced element
  and is stated as a hedge.
- Topology. The paper's prototype is three workers and one server, a
  hub-and-spoke that concentrates pressure at one NIC (item 5). We run
  decentralised ring and windowed direct collectives on rail-optimised Clos
  fabrics across a health spectrum, healthy 1:1, degraded 4:3 and designed
  2:1, with an explicit seven-source incast as the stressor.

## What network health means here, and where each arm sits

Queue peak is pegged at the 4 MiB data-queue limit in every arm and PFC is
off, so queue depth carries no information. The health signals that do are
the ones the trimming fabric produces: W, trimmed-payload bytes per offered
byte (how many times the fabric refused and re-carried each byte); wire
volume, `data_arrival` bytes over offered (the same thing counted per hop);
and control-plane load, the number of ACK, NACK and trim notifications the
end hosts had to process. All three are computable from
`transport_summary.csv` in every arm. Fixed-low arms, one seed per row
except the anchor:

| Family | W | wire/offered | Control packets | Regime |
| --- | ---: | ---: | ---: | --- |
| 64-rank sr2x (selective repair, 2:1) | 0.02 | 2.5x | 0.49 B | Light: healthy |
| 64-rank fan-in direct1 / 2 / 4 / 7 (degraded 1:1) | 1.34 / 2.22 / 2.53 / 2.58 | 5.1-7.7x | 2.4-4.1 B | Knee |
| 32-rank burst 0 / 2 / 4 / 7 (healthy 1:1) | 2.23 / 2.07 / 2.28 / 3.02 | 6.4-9.1x | 1.7-2.2 B | Knee |
| 32-rank 7-incast dose grid 0.2 / 0.4 / 0.6 | 2.79 / 2.94 / 2.80 | 8.5-8.8x | 2.1-2.2 B | Knee |
| 16-rank anchor, 16 seeds (2:1 Clos) | 8.68-10.37 | 18.6-21.6x | 3.0-3.5 B | Storm: every byte re-carried nine to ten times |

Two things about this table matter before any policy result. The 32-rank
"healthy" rail fabric is not healthy under go-back-N with no sender
congestion control: W is 2.2 with the
burst switched off entirely (burst0), because the direct2 DP fan-in plus
ECMP collisions congest it on their own, and the seven-source burst only
raises W to 3.0. And the one arm that runs selective repair on the worst
fabric (2:1, the anchor's design) has W of 0.02. The recovery algorithm,
not the topology or the burst, decides which regime a fabric is in.

## Does phase-aware tolerance improve health, and by how much

The direct answer, arm by arm. Delta is fixed-low minus policy, so
positive is healthier.

| Arm | W fixed-low | W policy | W fixed-high | Policy makespan | Note |
| --- | ---: | ---: | ---: | ---: | --- |
| anchor, 16 seeds | 9.52 | 9.11 | 8.45 | +3.91 % [1.13, 6.68] | trims -6 %, wire -156 GiB, control packets -0.18 B |
| 64 fan-in 7 (direct) | 2.58 | 2.14 | 2.23 | +11.11 % | largest single-arm health gain, 17 % |
| 64 fan-in 4 | 2.53 | 2.43 | 2.21 | +1.48 % | |
| 64 fan-in 2 | 2.22 | 2.13 | 2.05 | +4.25 % | |
| 64 fan-in 1 | 1.34 | 1.42 | 1.51 | +0.10 % | policy made the fabric less healthy |
| 32 burst 0 | 2.23 | 1.98 | 1.93 | +8.87 % | |
| 32 burst 2 | 2.07 | 1.96 | 2.14 | +4.05 % | |
| 32 burst 4 | 2.28 | 2.23 | 2.13 | +2.85 % | |
| 32 burst 7 (direct) | 3.02 | 2.82 | 2.91 | +0.75 % | |
| 32 dose 0.2 | 2.79 | 3.67 | 3.05 | -24.89 % | policy made the fabric much less healthy |
| 32 dose 0.4 | 2.94 | 2.68 | 2.39 | +8.40 % | |
| 32 dose 0.6 | 2.80 | 2.16 | 2.25 | +12.11 % | |
| 32 burst4 at 0.4 | 2.21 | 1.61 | 1.47 | +19.34 % | |
| 32 clrburst | 3.01 | 3.03 | 3.04 | +1.33 % | burst in a critical step: no health change at all |
| 64 sr2x | 0.02 | 0.02 | 0.02 | +0.78 % | nothing to improve |

Yes, it improves health, and the improvement is what makespan is made of.
In the anchor, the only family with a confidence interval, the policy
sheds 1.98 GiB of 166 GiB offered (1.19 %) and the fabric re-carries 156
GiB less, a marginal amplification of 79x; across the sixteen seeds the
makespan relief correlates 0.94 with the trim reduction, and the three seeds
where the policy left the fabric less healthy (+25.8 M, +0.9 M, +31.2 M
trims) are the three negative-makespan seeds. Byte reduction alone is flat
across seeds (7.1 to 8.7 %) and predicts nothing. Health, measured as W, is
the variable; makespan follows it at about 13 ms per million trims avoided.
This is consistent with, not proof of, the causal path [O2]; the
intervention that would prove it is in the last section.

How much health the tolerance buys is bounded and the bound is visible. The
unbounded arm, fixed-high, sheds through the critical steps too and buys
more of everything: W 8.45 against the policy's 9.11 in the anchor, makespan
9.42 % against 3.91 %. The difference is the price of Accordion's safety
bound, and it can be located exactly: in steps 1 to 3 fixed-high runs 203,
189 and 247 ms against the protected 345, 280 and 256 ms, a 242 ms cost for
protecting the regime, which is close to the whole of the policy's 292 ms
gain elsewhere. Phase awareness, then, spends about half of the health that
unbounded tolerance would buy, on the steps the schedule says it must.
Whether that is worth it is the accuracy question, and this simulator
cannot answer it; what it can say is what protection costs the network.

Where the improvement lands in time is the structural finding of the wave.
Decomposing the sixteen anchor seeds by training step:

| Steps | Fixed-low span | Policy span | Delta | Note |
| --- | ---: | ---: | ---: | --- |
| 1-3 (critical) | 345 / 280 / 256 ms | identical | 0.0 ms, 16/16 seeds | protected by design |
| 4-17 (permissive, no burst) | 191-305 ms | 176-295 ms | +239 ms summed, +20 to +54 ms per step | 84 % of the makespan gain |
| 18 (burst) | 771.8 ms | 656.0 ms | +115.8 ms, sd 430, CI +/-229 ms | per seed from +1080 to -485 ms |
| 19 (aftermath) | 734.8 ms | 792.6 ms | -57.8 ms, CI +/-185 ms | the storm outlives the burst |
| 20 (critical) | 283.1 ms | 296.8 ms | -13.7 ms | history differs by then |

The makespan gain is a steady-state gain. It accrues about 30 ms per
permissive step, wherever the fabric is congested and the policy happens
to be shedding. The congestion episode, the burst step and its aftermath
at three times the span of any other step, behaves differently, and the
per-step means hide it: relief moves between step 18 and step 19 from seed
to seed, so each step's mean is inside a 430 ms spread and the episode's
total duration (steps 18 plus 19) improves only 58 ms, CI [-68, 184]. But
the episode's *worst* collective, which is what the DP operation-span p99
measures (in all sixteen seeds the maximum span is at step 18 or 19),
improves reliably: 1026 ms to 873 ms, 153 ms, 14.9 %, CI [5.0, 301.7]. The
policy does it by flattening the worst seeds, the four baselines above
1.3 s drop by 434 to 716 ms, while barely moving the mild ones, and it
does it better than unbounded tolerance (fixed-high 109 ms, CI spanning
zero). So the tail of the episode gets healthier by about a seventh with
a CI that clears zero, and the episode as a whole does not measurably
shorten: the tolerance compresses the peak rather than draining the
storm. clrburst is the same finding from the other direction: put the burst in a critical step,
where the policy sheds nothing, and W does not move (3.01 to 3.03) even
though the policy is still shedding 10 % in every permissive step. The
tolerance improves health only where its shedding and the congestion
coincide in time, and admission-time shedding cannot make them coincide,
because it decides before the network has said anything.

Dose says the same thing with a caveat. Raising the tolerance from 10 % to
60 % at the 7-source point lowers W from 2.80 to 2.16 and raises makespan
relief to 12.1 %, while span p99 is negative at every dose above 0.1 and
fixed-high at 0.6 loses 84 % on both tails; more blind shedding buys
steady-state health and sells the tail. The caveat is that the four grid
profiles share a seed but not a selection stream (the profile name is
hashed into every decision, so their fixed-low baselines differ) and each
is one seed, so the 0.2 point's reversal (W 2.79 to 3.67) and the
cross-dose ordering are noise-limited until the grid is rerun matched [O4].

## Under what conditions

- The fabric has to be unhealthy to begin with, and unhealthy in a
  specific way: re-carrying bytes. On the Light fabric (sr2x) the policy
  changes nothing at any step (every per-step delta within +/-4 ms). The
  tolerance is a lever on W, and where W is near zero there is nothing to
  pull.
- The unhealthiness in every family with a result is produced by go-back-N
  recovery with no sender congestion control, which the programme's own
  selective-repair mode removes [O6].
  That is a condition on every number here and belongs in the same sentence
  as the result. It is not a mismatch with anyone's paper; both recovery
  modes are ours, and the roadmap already treats selective repair as the
  mode under which sustained oversubscription becomes a sweepable axis.
- The makespan gain is steady-state, proportional to how much of the
  offered load is shed while the fabric is congested. The tail gain is at
  the episode: the worst collective of the burst episode shortens by about
  15 % with a CI clearing zero, while the episode's total duration does
  not measurably change.
- The bound costs about half the available health gain and protects tails;
  unbounded tolerance wins makespan in the Storm (9.4 % against 3.9 %) and
  loses on every tail metric there and in six other conditions. Per metric,
  the bound costs makespan and protects tails [O7].

## What went well

The harness held for the first time: every cluster arm outlived the
24-hour runner-token wall that ended #116, 30 of 30 arms passed the
congestion gate with attested complete streams (about 43 TB hashed and
discarded), and four arms that also ran in #116 reproduced to the printed
digit on rebuilt binaries. The pre-registered pi-chunk seeds, the nested
arms and the bit-identical critical steps make the matched comparison
tighter than anything in the origin paper. The transport counters turned an
unexplained 4 % into a health mechanism with a size, and the sr2x canary
completed and showed what selective repair does to the regime. The
sixteen-seed anchor came in at sd 5.21 %, better than the 7.19 % it was
sized on, and cleared zero on makespan and on DP operation-span p99
(153.4 ms of 1026 ms, CI [5.0, 301.7]), which is the episode's
worst collective, the tail that a training step actually waits on.

## The two points from the last meeting

The collaborator's notes on 18 August were "10 % incast: increase incast"
and "mean reduction 50 % anomaly".

Increasing the incast was the burst-source sweep and the dose grid. More
burst sources gave less health improvement, not more (8.9, 4.1, 2.9, 0.8 %
makespan at 0, 2, 4, 7 sources), because under go-back-N with no sender
congestion control the fabric is already at W 2.2 with no burst at all and
the burst is a perturbation on
top; raising the dose instead bought steady-state health and sold the tail.
The suggestion assumed the incast was the unhealthiness. The counters say
the recovery algorithm is.

The 50 % anomaly is the per-rank p99 estimand. It is the top three of 320
samples, so one extra ECMP collision moves it by half. With sixteen seeds
its paired deltas run from -395 ms to +278 ms on a 756 ms base, -52 % to
+37 %, with a CI spanning zero; the single-seed values of -108 % and +73 %
in the 32-rank arms are draws from that spread. It is the noise floor of an
estimand this design cannot resolve, not an anomaly of the mechanism [O8].

## What went wrong, in the order it matters

1. The pre-registered primary estimand, per-rank p99, has never produced a
   signal in any regime or wave; it measures ECMP timing at this scale
   [O8]. Health (W) and the per-step span are the estimands that carry
   information, and the protocol does not name them.
2. Every health result is conditional on go-back-N recovery with no sender
   congestion control, and there is no selective-repair arm in any family
   that has a burst [O6].
3. The wave has no true negative control. burst0, which the matrix calls
   one, is a Knee fabric at W 2.23 with no burst; the protocol's
   `no_incast_8.json` did not run [O9]. The "supported policy benefit"
   verdict is conditional on it and on go-back-N with no sender congestion
   control and should say so in the same sentence [O5].
4. The dose grid and the burst4 pair are unmatched across profiles because
   `run_id` enters the selection hash (`ExperimentConfig.hh`); a one-line
   fix, but the grid's cross-dose readings are noise-limited until rerun
   [O4].
5. The pp2 arm, the only carrier of non-sheddable pipeline traffic, has
   never completed in three waves [O11].
6. The sixteen-seed aggregate job will fail on an absolute-profile-path
   equality check in `compare.py` when pp2 ends, so the run will conclude
   failure with 31 clean arms; the numbers above are what it would have
   produced.

## Can it withstand review

The referee pass was run on an earlier draft that graded the wave against
the origin paper's burst-latency claim; that framing is retired here, and
its objection O1 (burst step untested) is now the steady-state finding
above rather than a gap. What carries over is what a reviewer of the
health claim will still say: the mechanism is argued from a correlation
between two outputs of one simulation [O2]; the strongest number is
conditional on a recovery mode the programme intends to retire [O6]; the
claims that generalise, no channel under selective repair [O3] and dose is
not the amplifier [O4], rest on one seed each; the verdict sentence is not
conditional on the missing control [O5, O9]; and the pre-registered tail
estimand is dead [O8]. Two go to the premise: every result assumes
Accordion's tolerance holds for a 70B-class model, which nothing here can
test, so every claim must be conditional on a tolerance oracle [O10]; and
the 3D-parallel realism argument rests on pipeline traffic that has never
completed [O11].

None of these is a flaw in the harness or the statistics. They are the
same gap seen from five sides: the wave established that phase-aware tolerance improves steady-state
health in proportion to what it sheds and compresses the episode's worst
collective by about 15 %, under go-back-N with no sender congestion
control, and it has not yet tested the
lossy-transport half, taking the loss when the network signals it.

## How to frame the contribution

The framing the programme has carried, "phase-aware admission shedding
relieves congestion by 4 to 11 % on a UEC fabric", is true and thin. It
survives as a number but not as a contribution, because a reviewer will ask
what the mechanism is and the answer is bandwidth with a convex payoff on a
recovery algorithm we intend to retire.

The framing the data supports is a health study: what Accordion-style
phase-adaptive tolerance does to a trimming fabric, measured in the
fabric's own currency. Its findings are already in hand. A single
hop-independent ratio, W, places any fabric in one of three regimes and
predicts whether tolerance has anything to improve. Under go-back-N with
no sender congestion control the tolerance improves steady-state health in
proportion to what it sheds
while the fabric is congested, with a 79x marginal amplification, and
makespan follows W at 13 ms per million trims. The safety bound costs about half of the available health and buys tail
protection. The tail result is the one worth leading with: the worst
collective of the congestion episode shortens by 15 % with a CI clearing
zero, and the bounded policy does this better than unbounded tolerance.
Admission-time tolerance compresses the episode's peak but does not drain
the episode, because it decides before the network speaks, and clrburst
shows the same thing with W unmoved.

Why the tail number is the one that matters is a cost argument, and it
should be made in those terms. A training step waits on its slowest
collective, and while it waits the accelerators idle; every second of
communication the network cannot deliver is a second of GPU time paid for
and not used. What the wave shows is that phase-aware tolerance lets the
job recover from a disastrous episode faster: the worst collective of the
burst shortens by about a seventh, and it shortens most in the seeds where
the episode was worst. That is the shape of a training-time saving, with
one conversion the simulation cannot make. The window here is
communication-only, so the 292 ms of makespan and the 153 ms off the worst
collective become wall-clock training time only through the fraction of
communication a real framework leaves exposed after overlap, which the
July interleaving settlement fixed as a design parameter rather than
measured. The claim to make is therefore "faster recovery from congestion
episodes, measured in the fabric's own currency", with the GPU-hour
translation stated as the reader's arithmetic on their own exposed
fraction, not ours.
Under selective repair there is nothing to improve, and the recovery
algorithm rather than topology or burst intensity decides the regime.
That last finding is the one a fabric designer would want to know.

The framing worth the next six months follows from it. Accordion answers
how much and when; the lossy-transport half answers where in the network
the loss is taken. Taking it at admission gives steady-state health.
Taking it at recovery, declining the repair of a trimmed range outside the
critical regime under the same byte budget, is the only variant that can
act during the episode, because the trim notification is the network
saying which bytes it could not carry. Whether that variant makes the
episode healthier is the open empirical question, and the anchor bounds
the prize: the burst step and its aftermath are 1.5 s of a 7.1 s window.

I would write the health study now and build the recovery-domain variant
next. The first is honest about what the admission variant is, and it is
the argument that makes the second necessary rather than incremental.

## The decisive experiment

This section is superseded. The selective-repair canary (`llama3_70b_64_sr2x`)
ran before the wave planned here and made the planned 32-rank comparison
null by construction: on that fabric W is already near zero under selective
repair, so there is no unhealthiness left for a recovery-domain arm to
relieve. See [next-steps-after-run-117.md](next-steps-after-run-117.md) for
the canary's numbers and the revised order of work: a regime map across
congestion control and oversubscription settings, run before any
recovery-domain build.

## Integrity of the record

- 30 of 30 arms passed the congestion gate; 30 of 30 streams attested
  complete (332 to 665 segments, 356 to 2057 GiB per arm).
- 70 release assets, 1.17 GB; every bundle carries `attestation.json` with
  the binary sha256, ISA level, node, and stream digests. Three arms ran on
  the x86-64-v3 binary, the rest on x86-64-v4; the anchor mixes two of
  sixteen seeds from the other build.
- Simulator wall hours: 64-rank fan-in 45 to 56 h, anchor seeds 37 to 49 h,
  32-rank arms 23 to 38 h, sr2x 11 h, pp2 still open past 83 h.
