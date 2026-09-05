# CI run #117 wave readout

Run #117 is commit `414dc70c51ff`, workflow run 33526691181, ledger issue
#64, release `zuihrl5stp6ulacoogghyp4loy7xsjpj`. I wrote this on 2026-09-05
at 01:30 UTC with the run still open: 30 of 31 comparisons collected, the
64-rank pp2 control still simulating (83 h elapsed, guard expires 2026-09-06
07:59 UTC), so the three aggregate jobs and the ledger close have not run.
This is my own account of the wave: what I bet on, what came back, what I got
wrong, where that leaves the programme, and what I do next.

What I read: `gh api` over the run, its 194 jobs, the release, and issues #57
to #64; the 31 ledger comments on #64; `comparison.json` and every arm's
`ns3/transport_summary.csv` streamed out of the 30 release bundles; a local
re-run of `compare.py --aggregate-inputs` and `fan_in_sweep.py` from this
tree; and the programme's own records in this directory, which I lean on
below.

## The bet

The idea under test is DBLP's: a training job does not need every gradient
byte in every step, and a transport that knows which steps are critical can
accept bounded loss outside them and buy tail latency with it. ASTRA-sim
cannot say anything about accuracy, so the pivot document limits this project
to mechanism-level evidence: under a specified, reproducible modeled network
condition, does a phase-aware policy improve DP All-Reduce tail latency and
makespan against a matched baseline. The evidence ladder in that document
runs mechanism validity, causal comparison, robustness, scale, and then the
external-validity boundary.

Getting to a wave that could climb that ladder took most of August. The
Phase-1 reference livelocked on port exhaustion, then ran 93 times slow after
a hot-path regression, then the hosted runners could not hold a six-hour
job. I moved the heavy arms to the DCS SLURM cluster behind just-in-time
runners, split each comparison into its own job with its own guard, and
discovered that the runner's token dies at 24 hours, which killed every
64-rank arm in #116 at about 26.5 h. Run #112 was the first wave with enough
surviving arms to read, and my reading of it is what shaped #117.

That reading reduced the programme to a cost model. When the workload is
communication-bound, makespan is offered load plus a waste term
W(offered/capacity): retransmission volume, convex in load, exploding past a
knee. Admission shedding, the mechanism we have today, removes
dose x dp_share of the *offered* load, which at p_high = 0.1 is about 1.7 %.
The pathology I measured in the #112 bundles was the waste term, at 5 to 19
times the offered term. I classify regimes by amplification (wire volume
over offered payload): Light below 1.2x has nothing to relieve, the Knee at
1.5 to 3x is where W is steepest, and the Storm above 5x is timing chaos with
a seed standard deviation near 7 %. The publishable contribution I named
then was recovery-domain shedding: let the trim notification itself trigger
bounded forgiveness, so each forgiven range deletes a retransmission chain
and the mechanism attacks W directly.

#117 was built to test that reading before I build the new protocol. It
carried three changes from #112: the anchor family grew from five seeds to
sixteen pre-registered pi-chunk seeds, a four-point p_high dose grid went in
at the 7-source incast endpoint, and raw-log escrow gave way to hashed
provenance. I wrote down eight predictions:

1. The sixteen-seed anchor (Storm) buys a no-harm bound and no more. At sd
   7.2 % the CI half-width is +/-3.8 %, and resolving a ~1 % effect would
   take ~200 seeds.
2. Any relief above the ~1.7 % byte ceiling comes through the nonlinear
   channel: the mechanism relieves congestion, W, and does not relieve
   bandwidth, so relief should track trim reduction and should not track
   byte reduction.
3. Dose (p_high from 0.1 to 0.6) is not the amplifier, because even dose
   1.0 caps at dp_share of offered. Each grid point carried one falsifiable
   question.
4. The burst-count axis has weak leverage; burst0 already self-congests.
5. Restraint does work: fixed-high sheds strictly more and loses in several
   conditions, which falsifies a dose-monotone story.
6. Critical steps are bit-identical across arms (clrburst at 0.00 %).
7. If the sr2x canary completes, it lands in the Light regime and reopens
   sustained oversubscription as an axis.
8. Determinism holds inside an envelope of source, toolchain, and CPU
   family, which is what lets stream hashes replace raw-log escrow.

## Where every arm landed on the regime axis

W is trimmed-payload bytes per offered byte (`trim_ftd_admission` plus
last-hop trims, over `total_physical_bytes`), my hop-independent measure of
the waste term. wire/offered is `data_arrival` over offered and counts every
hop. Fixed-low arms; the 32- and 64-rank rows are one seed each, the anchor
row is the range across sixteen seeds.

| Family | Regime | W (trim/offered) | wire/offered | Control packets | Policy makespan relief |
| --- | --- | ---: | ---: | ---: | ---: |
| 64-rank sr2x (selective repair, 2:1) | Light | 0.02 | 2.5x | 0.49 B | 0.78 % |
| 64-rank fan-in direct1 / 2 / 4 / 7 (degraded 1:1) | Knee | 1.34 / 2.22 / 2.53 / 2.58 | 5.1-7.7x | 2.4-4.1 B | 0.10 / 4.25 / 1.48 / 11.11 % |
| 32-rank burst 0 / 2 / 4 / 7 (healthy 1:1) | Knee | 2.23 / 2.07 / 2.28 / 3.02 | 6.4-9.1x | 1.7-2.2 B | 8.87 / 4.05 / 2.85 / 0.75 % |
| 32-rank 7-incast dose grid 0.2 / 0.4 / 0.6 | Knee | 2.79 / 2.94 / 2.80 | 8.5-8.8x | 2.1-2.2 B | -24.89 / 8.40 / 12.11 % |
| 16-rank anchor, 16 seeds (Clos, 7-source burst) | Storm | 8.68-10.37 | 18.6-21.6x | 3.0-3.5 B | +3.91 % mean |

In the anchor, every offered byte is trimmed and re-sent between nine and
ten times. The 32- and 64-rank families run two to three times over, and
sr2x barely trims. The wave sorted itself the way the taxonomy said it would:
one Storm family, two Knee families, one Light canary.

## What went well

The harness finally held. Every one of the 31 cluster arms outlived the
24-hour token wall that ended #116; the sealed runtime store, the courier and
outbox path, and the attestation step all worked on their first full wave.
Thirty arms passed the congestion gate, thirty streams were attested
complete (332 to 665 segments, 356 to 2057 GiB per arm, about 43 TB hashed
and discarded), and every bundle reached the release with its
`attestation.json`. Four arms that also completed in #116 came back identical
to the printed digit, on binaries rebuilt from the compiler cache, which is
the cross-wave half of the determinism envelope holding at the same ISA
level. I can now say a stream hash is a commitment.

The anchor did better than the no-harm bound I sized it for. Sixteen paired
seeds, ring all-reduce, three arms per seed, aggregated with the same
`compare.py` code the CI job runs:

| Estimand | Fixed-low | Policy | Reduction | 95 % CI | % |
| --- | ---: | ---: | ---: | ---: | ---: |
| makespan | 7145.1 ms | 6853.5 ms | 291.6 ms | [91.0, 492.3] | 3.91 |
| DP all-reduce operation-span p99 | 1026.0 ms | 872.7 ms | 153.4 ms | [5.0, 301.7] | 10.80 |
| DP all-reduce per-rank p99 | 755.6 ms | 760.1 ms | -4.5 ms | [-90.1, 81.0] | -4.90 |
| DP physical bytes | 25.34 GiB | 23.36 GiB | 1.98 GiB | [1.92, 2.05] | 7.82 |

The paired makespan deltas came in at sd 5.21 %, so the half-width is
+/-2.78 % instead of the +/-3.83 % I planned for, and a mean of +3.91 %
clears it: CI [1.13, 6.68] %. Three of the sixteen seeds are negative
(31415926, 33832795, 70679821). Headroom: fixed-high makespan -9.42 %
[500, 863 ms], span p99 6.06 % with a CI spanning zero, per-rank p99
negative. The policy captured 43 % of the unbounded makespan headroom without
shedding inside CLR, and it beats fixed-high on span p99.

Per-seed deltas in ms, positive is relief; ISA marks the two seeds that ran
on the x86-64-v3 binary on cpunode4.

| Seed | ISA | Makespan | Span p99 | Per-rank p99 | Policy trim change |
| --- | --- | ---: | ---: | ---: | ---: |
| 2884197 | v4 | 262.3 | 434.2 | -394.7 | -14.7 M |
| 16939937 | v4 | 751.5 | 716.3 | 146.2 | -47.9 M |
| 23846264 | v4 | 284.7 | 496.7 | -102.4 | -27.7 M |
| 28230664 | v3 | 232.7 | -43.5 | -86.8 | -20.9 M |
| 30781640 | v4 | 284.8 | 160.3 | 154.0 | -40.6 M |
| 31415926 | v4 | -369.7 | 143.4 | -123.1 | +25.8 M |
| 33832795 | v4 | -97.6 | 205.3 | -12.5 | +0.9 M |
| 48086513 | v4 | 376.5 | -140.0 | 137.8 | -36.3 M |
| 51058209 | v4 | 165.1 | -56.1 | -93.9 | -13.3 M |
| 53589793 | v4 | 880.1 | 16.0 | 59.9 | -74.1 M |
| 62862089 | v3 | 575.6 | -101.1 | -143.3 | -40.5 M |
| 70679821 | v4 | -494.5 | 16.8 | 61.8 | +31.2 M |
| 70938446 | v4 | 288.8 | 158.1 | -5.4 | -16.9 M |
| 74944592 | v4 | 719.2 | -103.6 | 121.8 | -49.4 M |
| 82534211 | v4 | 251.0 | -98.3 | -70.3 | -42.5 M |
| 98628034 | v4 | 555.9 | 649.1 | 278.4 | -27.9 M |

The result I care most about is that the relief has a mechanism I can point
at. The policy removed 1.98 GiB of 166 GiB offered, 1.19 %, and makespan
fell 3.91 %, 3.3 times the linear byte ceiling. The transport counters,
averaged over the sixteen seeds, show where the rest came from:

| Arm | Offered | Wire volume | Trimmed payload | Trims | W | Control packets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed-low | 166.2 GiB | 3342 GiB | 1582 GiB | 401.7 M | 9.52 | 3.22 B |
| policy | 164.2 GiB | 3186 GiB | 1496 GiB | 377.0 M | 9.11 | 3.04 B |
| fixed-high | 163.8 GiB | 3014 GiB | 1384 GiB | 348.2 M | 8.45 | 2.82 B |

Shedding 1.98 GiB took 156 GiB off the wire, a marginal amplification of
79x; fixed-high's 2.46 GiB took off 327 GiB, 133x. Across seeds the policy's
makespan relief correlates 0.94 with its trim reduction, at 13 ms per
million trims avoided, and the three seeds where the policy added trims
(+25.8 M, +0.9 M, +31.2 M) are the three negative seeds. Byte reduction
hardly varies across seeds (7.1 to 8.7 %) and predicts nothing. Prediction 2
held in the strongest form the data allows. Admission shedding helps only
through the retransmission chains it happens to delete, and those chains are
what the forgiveness protocol would target on purpose.

Three smaller confirmations. clrburst reproduced the 0.00 % span and
per-rank p99 deltas between policy and fixed-low, with makespan 1.33 %: the
burst fires at step 1, which is CLR under every seed, the policy shed
nothing there, and fixed-high, which did shed into it, lost 13.7 % per-rank
p99. The bound is doing work. Fixed-high makespan is negative in four
conditions again (burst2 -3.63 %, fan-in direct1 -4.10 %, 32-direct
-0.78 %, sr2x -0.57 %), and its per-rank p99 is negative in the anchor
(-4.4 %), clrburst (-13.7 %), burst2 (-20.5 %), direct1 (-80.5 %), direct2
(-28.9 %) and the 0.6 dose point (-83.9 %); it wins on Storm makespan (9.4 %
against 3.9 %) because there more deletion is more relief, and pays in tails.
And sr2x completed in 11 h with W = 0.02, 4.4 M trims against roughly 300 M
for go-back-N on the same fabric, and relief of 0.78 %: selective repair
collapses the waste term by 70x, and once the waste is gone the admission
policy has no channel left. Sustained oversubscription is back as an axis I
can sweep, and the go-back-N contrast is a result on its own.

## What went wrong

The dose grid is not the matched experiment I wrote into the matrix. I found
this by accident while checking determinism. The four grid profiles differ
from the origin only in `name` and `p_high`, so their fixed-low baselines
should be the same simulation. They are not: makespan 4508 / 4428 / 4514 /
4237 ms, four distinct stream hashes, two of them on the same node and
binary. The cause is in
`astra-sim/network_frontend/ns3/ExperimentConfig.hh`: the selection decision
hashes the seed, `run_hash = stable_string_hash(run_id)`, and the operation
coordinates, and `run_id` is the profile name. Within one profile the arms
are nested (a decision selected at 0.005 is selected at every higher
threshold), which is why the three arms of a pair are bit-matched. Across
profiles that differ only by name the selection streams are unrelated. So
the dose grid and the burst4 / burst4-ph40 pair compare unmatched
baselines, and any cross-dose difference carries selection-stream noise of a
size I cannot estimate on top of the ECMP noise. When I wrote "matching the
existing burst-sweep origin so the p_high=0.1 runs need no rerun" into the
matrix notes, I believed the seed was the whole stream. It was not, and the
grid's answers below have to be read with that in mind.

What the grid does say, per point at seed 314159265 on the 7-source 32-rank
fabric:

| p_high | Question | DP bytes shed | Makespan | Span p99 | W base / policy | Fixed-high tails |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0.1 (32-direct) | origin | 8.16 % | 0.75 % | 7.68 % | 3.02 / 2.82 | +1.75 / +2.60 % |
| 0.2 | does doubling move relief? | 15.74 % | -24.89 % | -100.28 % | 2.79 / 3.67 | -55.7 / -49.4 % |
| 0.4 | curvature: scale or saturate? | 31.76 % | 8.40 % | -72.83 % | 2.94 / 2.68 | -11.5 / -14.6 % |
| 0.6 | ceiling: can any dose restore relief? | 47.53 % | 12.11 % | -4.53 % | 2.80 / 2.16 | -83.9 / -83.9 % |
| burst4 at 0.4 | dose x burst interaction | 32.04 % | 19.34 % | -1.81 % | 2.21 / 1.61 | +13.6 / +11.6 % |

The byte lever arrived exactly as dosed (8, 16, 32, 48 %). At 0.4 and 0.6 the
policy's W fell with it and makespan relief rose to 8.4 % and 12.1 %. Tails
went the other way: span p99 is negative at every dose above 0.1, and
fixed-high at 0.6 loses 84 % on both tail metrics. The 0.2 point is an
outlier in the wrong direction on every axis, with policy W at 3.67 against
a 2.79 baseline. Per question: doubling the dose did not move relief the
right way (Q1); makespan relief is still rising at 0.6, so I did not locate
a saturation point (Q2); the "no dose restores relief" falsifier did not
fire for makespan but did fire for tails (Q3); burst-4 keeps its advantage at
equal dose, so the sweet spot reads as a property of the fabric (Q4).
Prediction 3 stands as far as one unmatched seed can carry it: dose is a
makespan lever with a tail-latency price, and it is not the amplifier.

The run will end in failure on paper. `aggregate_comparison_artifacts` in
`experiments/ring_3d/compare.py` requires every artifact's `profile` string
to be identical, but each arm writes `profile.resolve().as_posix()`, which on
the cluster is `/w/nobackup/.../astra-sim/<SLURM job id>/_work/...`, and the
sixteen archived files carry sixteen distinct strings. Every earlier wave
lost at least one seed arm and failed the count gate first, so this check
was never reached; #117 will be the first run to hit it. The two sweep
aggregations expect differing profiles and are unaffected. The aggregate
section will publish as failure, `ledger-close` will keep #64 open, and the
run will conclude failure despite 31 clean arms. A fix cannot rescue this
run, because the workflow is pinned to 414dc70; the numbers above are what
the job would have produced.

I misread burst0 in my first draft of this document and called it an
unexplained protocol confound. burst0, burst4, burst4-ph40 and sr2x
completed in both #116 and #117 with every metric identical, so the burst0
result (zero burst sources, 138 M trims, the sweep's largest relief at 8.87 %
makespan) is reproduced, not observed a second time. What #117 adds is
placement: W is 2.23 at zero sources, 2.07 and 2.28 at two and four, and the
7-source point rises to 3.02. The burst axis moves the waste term by at most
35 %, while rank scale and fan-in move it fourfold. Prediction 4 held. burst0
is a Knee-regime fabric that congests itself, which is what I had already
concluded from #112, and the wave has no true negative control: the
protocol's no-incast profile, `profiles/no_incast_8.json`, was not in it.

Two smaller things. Per-rank p99 in the anchor is still chaos, with per-seed
deltas from -395 ms to +278 ms and a CI spanning zero; the Storm regime does
not give up tail evidence at sixteen seeds, as I expected. And three arms
ran on the x86-64-v3 build (cpunode4, EPYC 7453) while the rest ran on
x86-64-v4 (EPYC 9634 and 9754), so the anchor aggregate mixes two of sixteen
seeds from the other binary. The attestation records it, and it is not a
determinism failure, since the same inputs gave the same outputs. What the
run_id finding shows is that the envelope has an input I never wrote down:
the profile name.

pp2 remains unknown. It has never completed in three waves (#115 and #116
cancelled it early), it is now 27 h past the longest completed sibling
(direct4 at 56.0 h), and GitHub does not serve an in-progress job's log, so I
cannot read its liveness checkpoints until it ends.

## Where we are

On the evidence ladder: mechanism validity is established in every arm, the
causal comparison is established at one predeclared point with two of three
primary estimands clearing zero and a causal-load ratio of 2.27, robustness
is partial (both sweeps complete but single-seed, the dose grid unmatched),
and scale evidence now exists for 64 ranks on a degraded fabric for the
first time. The near-zero no-incast control the protocol asks for is still
owed. By the rules as written this is "supported policy benefit" on makespan
and span p99, with the control pending, and the waste-term counters say why
the magnitude is what it is.

Against the paper, the position is narrower than the project's name. What
we have is a phase-aware admission policy on a UEC trimming fabric where
every trimmed packet is repaired: the transport still tolerates zero actual
loss, and the DBLP idea of accepting residual loss has not been exercised.
What #117 proves is that the admission policy's relief is exactly the
retransmission volume it removes as a side effect. That is the strongest
possible argument for moving the loss-acceptance point into the recovery
path, and it is the argument I wanted before building it. The anchor has
done its job. It sized the seed noise, it produced the one confidence
interval the programme has, and it is the wrong regime for a headline, as I
said after #112.

## What I do next

1. Harness fixes before any push, all small. Make `run_id` an explicit
   profile field that a sweep family shares, or drop `run_hash` from
   `stable_operation_hash` since the seed already keys the stream, and add a
   test that two profiles differing only in `p_high` produce a byte-identical
   fixed-low arm. Compare profiles in the aggregate by workspace-relative
   path or content hash. Print W next to the trim counts in `compare.py`,
   since it separates the regimes cleanly and every arm already has it.
2. Build the forgiveness protocol. The design is written: push-first,
   pull-repair, the receiver owns acceptance, forgiven ranges are marked
   received so the ordinary cumulative ACK advances the sender, a batched
   forgiveness bitmap rides on the ACK, and the safety law is shed plus
   forgiven at most p(s) times eligible(s), checked synchronously. One design
   question is still open from the last session: whether a separate FORGIVE
   verb is needed at all, or an ACK that advances past forgiven ranges is
   enough, and whether acknowledging bytes ahead of delivery is a safe
   fast-path in a permissive regime. I owe that answer before the code.
3. The next wave, in this order: TP-off plus a capacity-knee calibration
   (two arms); forgiveness against admission at equal shed budget (two to
   three arms); the real no-incast control; then pi-chunk seeds 17 onward on
   the winning 32-rank point, about eight of them. The anchor moves from
   always-on to a single canary so the cluster budget goes to the Knee.
4. Real hardware waits. The accuracy half of DBLP can only be shown on a
   real model, and the collaborator's question about paying for GPU time
   gets a yes only after forgiveness shows a Knee-regime effect with a
   confidence interval behind it.

## Integrity of the record

- 30 of 30 arms passed the congestion gate; 30 of 30 streams attested
  complete.
- 70 release assets, 1.17 GB; every bundle carries `attestation.json` with
  the binary sha256, ISA level, node, and the uncompressed stream digests.
- Simulator wall hours: 64-rank fan-in 45 to 56 h, anchor seeds 37 to 49 h,
  32-rank arms 23 to 38 h, sr2x 11 h, pp2 still open. In #116 every 64-rank
  arm died at about 26.5 h; the courier and outbox design in 414dc70 is what
  carried this wave past that wall.
