# CI run #117 wave readout

Run #117 (commit `414dc70c51ff`, workflow run 33526691181, ledger issue #64,
release `zuihrl5stp6ulacoogghyp4loy7xsjpj`) is the wave that the run #112
analysis designed: the anchor family scaled from five to sixteen pre-registered
pi-chunk seeds, a four-point p_high dose grid at the 7-source incast endpoint,
and the first wave running under hashed provenance instead of raw-log escrow.
This document reads the wave against what it was built to test. State as of
2026-09-05 01:30 UTC, before the run finished; 30 of 31 comparisons collected,
the 64-rank pp2 control still simulating (83 h elapsed, guard expires
2026-09-06 07:59 UTC), so the three aggregate jobs and the ledger close have
not run.

Sources: `gh api` over the run, its 194 jobs, the release, and issues #57-#64;
the 31 ledger comments on #64; `comparison.json` and every arm's
`ns3/transport_summary.csv` streamed from the 30 release bundles; local
re-execution of `compare.py --aggregate-inputs` and `fan_in_sweep.py` from
this tree. The programme context is the run #112 analysis
(`experiments/ring_3d/VALIDATION_PROTOCOL.md` for estimands and decision
rules; the regime taxonomy and ceiling algebra are restated below).

## What the wave was built to test

The run #112 analysis reduced the programme to a cost model and a set of
predictions. Communication-bound makespan is offered load plus a waste term
W(offered/capacity) - retransmission volume that is convex in load and explodes
past a knee. Admission shedding, the mechanism under test, removes
dose x dp_share of *offered* load (at p_high = 0.1 about 1.7 %), while the
measured pathology is the waste term at 5-19x the offered term. Regimes are
classified by amplification (wire volume / offered payload): Light below 1.2x
has nothing to relieve, the Knee at 1.5-3x has the steepest slope of W, and the
Storm above 5x is timing chaos with seed sd near 7 %. From that came the
predictions this wave tests:

1. The sixteen-seed anchor (Storm) buys a no-harm bound only: at sd 7.2 %
   the CI half-width is +/-3.8 %, and a ~1 % effect needs ~200 seeds.
2. Any relief above the ~1.7 % byte ceiling is the nonlinear channel: the
   mechanism relieves congestion (W), not bandwidth. Relief should track trim
   reduction, not byte reduction.
3. Dose (p_high 0.1 to 0.6) is not the amplifier: even dose 1.0 caps at
   dp_share of offered. Each grid point carried one falsifiable question.
4. The burst-count axis has weak leverage: burst0 already self-congests.
5. Restraint is functional: fixed-high, which sheds strictly more, loses in
   several conditions, so a dose-monotone story is false.
6. Critical steps are bit-identical across arms (clrburst 0.00 %).
7. The sr2x canary, if it completes, sits in the Light regime and reopens
   sustained oversubscription as an axis.
8. Determinism holds inside an envelope (source, toolchain, CPU family), so
   stream hashes can replace raw-log escrow.

## Regime placement of every arm

W is trimmed-payload bytes per offered byte (`trim_ftd_admission` plus
last-hop trims over `total_physical_bytes`), the hop-independent measure of
the waste term; wire/offered is `data_arrival` bytes over offered and counts
every hop. Fixed-low arms; 32- and 64-rank values are one seed each, the anchor
is the sixteen-seed range.

| Family | Regime | W (trim/offered) | wire/offered | Control packets | Policy makespan relief |
| --- | --- | ---: | ---: | ---: | ---: |
| 64-rank sr2x (selective repair, 2:1) | Light | 0.02 | 2.5x | 0.49 B | 0.78 % |
| 64-rank fan-in direct1 / 2 / 4 / 7 (degraded 1:1) | Knee | 1.34 / 2.22 / 2.53 / 2.58 | 5.1-7.7x | 2.4-4.1 B | 0.10 / 4.25 / 1.48 / 11.11 % |
| 32-rank burst 0 / 2 / 4 / 7 (healthy 1:1) | Knee | 2.23 / 2.07 / 2.28 / 3.02 | 6.4-9.1x | 1.7-2.2 B | 8.87 / 4.05 / 2.85 / 0.75 % |
| 32-rank 7-incast dose grid 0.2 / 0.4 / 0.6 | Knee | 2.79 / 2.94 / 2.80 | 8.5-8.8x | 2.1-2.2 B | -24.89 / 8.40 / 12.11 % |
| 16-rank anchor, 16 seeds (Clos, 7-source burst) | Storm | 8.68-10.37 | 18.6-21.6x | 3.0-3.5 B | +3.91 % mean |

Every offered byte in the anchor is trimmed and re-sent between nine and ten
times; the 32- and 64-rank families sit two to three times over, and sr2x
does not trim at all. The wave's own placement is therefore exactly the
taxonomy's: one Storm family, two Knee families, one Light canary.

## Scorecard

### 1. The anchor did better than the no-harm bound

Sixteen paired seeds, ring all-reduce, three arms per seed. Aggregated with
the same `compare.py` code the CI job runs:

| Estimand | Fixed-low | Policy | Reduction | 95 % CI | % |
| --- | ---: | ---: | ---: | ---: | ---: |
| makespan | 7145.1 ms | 6853.5 ms | 291.6 ms | [91.0, 492.3] | 3.91 |
| DP all-reduce operation-span p99 | 1026.0 ms | 872.7 ms | 153.4 ms | [5.0, 301.7] | 10.80 |
| DP all-reduce per-rank p99 | 755.6 ms | 760.1 ms | -4.5 ms | [-90.1, 81.0] | -4.90 |
| DP physical bytes | 25.34 GiB | 23.36 GiB | 1.98 GiB | [1.92, 2.05] | 7.82 |

The paired makespan deltas in percent have sd 5.21, not the 7.19 the design
was sized on, so the half-width came in at +/-2.78 % instead of +/-3.83 %, and
the mean of +3.91 % clears it: CI [1.13, 6.68] %. Three of sixteen seeds are
negative (31415926, 33832795, 70679821). Per-rank p99 is where the Storm
regime's chaos lives: its per-seed deltas run from -395 ms to +278 ms and the
CI spans zero. Headroom: fixed-high makespan -9.42 % [500, 863 ms], span p99
6.06 % (CI spans zero), per-rank p99 negative. The policy captured 43 % of the
unbounded makespan headroom without shedding inside CLR and beats fixed-high
on span p99.

Per-seed table (ms, positive is relief; ISA marks the two seeds that ran on
the x86-64-v3 binary on cpunode4):

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

### 2. The relief is the waste term, and nothing else

This is the wave's central result. The policy removed 1.98 GiB of 166 GiB
offered (1.19 %) and makespan fell 3.91 %, 3.3x the linear byte ceiling. The
mechanism is visible in the transport counters, averaged over the sixteen
seeds:

| Arm | Offered | Wire volume | Trimmed payload | Trims | W | Control packets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed-low | 166.2 GiB | 3342 GiB | 1582 GiB | 401.7 M | 9.52 | 3.22 B |
| policy | 164.2 GiB | 3186 GiB | 1496 GiB | 377.0 M | 9.11 | 3.04 B |
| fixed-high | 163.8 GiB | 3014 GiB | 1384 GiB | 348.2 M | 8.45 | 2.82 B |

Marginal amplification: 156 GiB of wire volume per 1.98 GiB shed (79x) for
the policy, 327 GiB per 2.46 GiB (133x) for fixed-high. Across seeds the
policy's makespan relief correlates 0.94 with its trim reduction, at 13 ms per
million trims avoided, and the three seeds where the policy *added* trims
(+25.8 M, +0.9 M, +31.2 M) are exactly the three negative seeds. Byte
reduction is nearly constant across seeds (7.1-8.7 %) and predicts nothing.
Prediction 2 holds in the strongest form the data allows: admission shedding
works only through the retransmission chains it happens to delete, which is
the term recovery-domain shedding attacks directly.

### 3. The dose grid: dose buys makespan, not tails - and the grid is not matched

Each point at seed 314159265 on the 7-source 32-rank fabric:

| p_high | Question | DP bytes shed | Makespan | Span p99 | W base / policy | Fixed-high tails |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0.1 (32-direct) | origin | 8.16 % | 0.75 % | 7.68 % | 3.02 / 2.82 | +1.75 / +2.60 % |
| 0.2 | does doubling move relief? | 15.74 % | -24.89 % | -100.28 % | 2.79 / 3.67 | -55.7 / -49.4 % |
| 0.4 | curvature: scale or saturate? | 31.76 % | 8.40 % | -72.83 % | 2.94 / 2.68 | -11.5 / -14.6 % |
| 0.6 | ceiling: can any dose restore relief? | 47.53 % | 12.11 % | -4.53 % | 2.80 / 2.16 | -83.9 / -83.9 % |
| burst4 at 0.4 | dose x burst interaction | 32.04 % | 19.34 % | -1.81 % | 2.21 / 1.61 | +13.6 / +11.6 % |

The byte lever is delivered exactly as dosed (8, 16, 32, 48 %), and at 0.4
and 0.6 the policy's W falls with it, so makespan relief rises to 8.4 % and
12.1 %. Tails do not follow: span p99 is negative at every dose above 0.1,
and fixed-high at 0.6 loses 84 % on both tail metrics. The 0.2 point is an
outlier in the wrong direction on every axis (policy W 3.67 against a 2.79
baseline). Reading per question: doubling the dose did not move relief the
right way (Q1); relief is still rising at 0.6 on makespan, so no saturation
was located (Q2); the "no dose restores relief" falsifier did not fire for
makespan but did for tails (Q3); burst-4 keeps its advantage at equal dose,
so the sweet spot reads as a fabric property (Q4). Prediction 3 stands:
dose is a makespan lever with a tail-latency cost, not the amplifier.

Two caveats, one of them structural. The single-seed caveat is the declared
one. The structural one was found while checking determinism: the four grid
profiles differ from the origin only in `name` and `p_high`, and their
fixed-low baselines should therefore be the same simulation. They are not
(makespan 4508 / 4428 / 4514 / 4237 ms, four distinct stream hashes, two of
them on the same node and binary). The cause is
`astra-sim/network_frontend/ns3/ExperimentConfig.hh`: the selection decision
hashes the seed, `run_hash = stable_string_hash(run_id)`, and the operation
coordinates, and `run_id` is the profile name. Within one profile the arms are
nested (a decision selected at 0.005 is selected at every higher threshold),
which is what makes the three arms bit-matched. Across profiles that differ
only by name the selection streams are unrelated, so the dose grid and the
burst4 / burst4-ph40 pair compare unmatched baselines: cross-dose differences
carry selection-stream noise of unknown size on top of ECMP noise. The
same-profile pairs (policy versus its own baseline) are unaffected, as is the
anchor family (one name, sixteen seeds).

### 4. The burst0 paradox is the same run as in #112

burst0, burst4, burst4-ph40 and sr2x completed in both #116 and #117 and every
reported metric is identical to the printed digit, so the burst0 result
(zero burst sources, 138 M trims, the sweep's largest relief at 8.87 %
makespan) is reproduced, not re-observed. What #117 adds is the placement:
W is 2.23 at zero sources, 2.07 and 2.28 at two and four, and only the
7-source point rises to 3.02. The burst axis moves the waste term by at most
35 %, while rank scale and fan-in move it fourfold. Prediction 4 holds, and the
earlier readout's framing of burst0 as an unexplained protocol confound was
wrong: the "negative control" is a Knee-regime fabric that self-congests,
and the sweep's x-axis is the weak lever the #112 analysis said it was.

### 5. Restraint is functional on tails, not on makespan

Fixed-high makespan is negative in four conditions again (burst2 -3.63 %,
fan-in direct1 -4.10 %, 32-direct -0.78 %, sr2x -0.57 %) and its per-rank p99
is negative in the anchor (-4.4 %), clrburst (-13.7 %), burst2 (-20.5 %),
direct1 (-80.5 %), direct2 (-28.9 %) and the 0.6 dose point (-83.9 %). In the
Storm regime fixed-high does win on makespan (9.4 % against the policy's
3.9 %), because there the waste term dominates everything and more deletion
is more relief; it pays for it in tails. The bound is doing work; it is not
merely safe.

### 6. Critical steps are bit-identical

clrburst: span p99 and per-rank p99 deltas of exactly 0.00 % between policy
and fixed-low, makespan 1.33 %. The burst fires at step 1, which the schedule
holds in CLR under every seed, and the policy shed nothing there. Fixed-high,
which does shed into that step, lost 13.7 % per-rank p99. Prediction 6
reproduced.

### 7. The Light regime has nothing to relieve

sr2x completed in 11 h with W = 0.02 (4.4 M trims against roughly 300 M for
go-back-N on the same fabric) and relief of 0.78 %. Both halves of prediction
7 hold: selective repair collapses the waste term by 70x, and once it is gone
the admission policy has no channel left. Sustained oversubscription is back
as a sweepable axis, with the go-back-N contrast as a finding of its own.

### 8. Determinism inside the envelope, and one input that was not pinned

Identical numbers across #116 and #117 for four arms, on rebuilt binaries
from the compiler cache, is the cross-wave half of the envelope holding for
the same ISA level. Three arms ran on the x86-64-v3 build (cpunode4, EPYC
7453), the rest on x86-64-v4 (EPYC 9634 and 9754); the attestation records
this, and the anchor aggregate mixes two of sixteen seeds from the other
binary. The run_id finding in section 3 is not a determinism failure - same
inputs did give same outputs - but it shows the determinism envelope has an
input nobody listed: the profile name.

## Against the protocol's decision rules

Raw gates pass in all 30 arms. Two primary estimands improve at the anchor
with CIs excluding zero. The causal-load ratio (DP byte relief over background
bytes) is 2.27. The remaining condition, a near-zero no-incast control,
cannot be evaluated by burst0, which is not an uncongested condition; the
protocol's actual negative control (`profiles/no_incast_8.json`) was not in
this wave. Under the rules as written this is "supported policy benefit" on
makespan and span p99 at one predeclared point, with the control pending, and
the mechanism analysis says why the magnitude is what it is.

## What this means for the programme

- The admission mechanism has been characterised to its ceiling. Its whole
  effect is second-order relief of the waste term (section 2), its dose axis
  trades tails for makespan (section 3), and its burst axis is weak (section
  4). The next lever is the one the #112 analysis named: recovery-domain
  shedding, where the trim notification itself triggers bounded forgiveness
  and each forgiven range deletes a retransmission chain. The #117 counters
  size the target: 1.5 TB of trimmed payload per anchor arm against 25 GiB
  of DP bytes the admission policy can touch.
- The next wave should follow the plan already laid out: TP-off plus
  capacity-knee calibration (two arms), forgiveness versus admission at equal
  shed budget (two to three arms), then pi-chunk seeds 17 onward on the
  winning 32-rank point. The anchor has done its job and does not need more
  seeds.
- Two harness fixes before that wave. First, `run_id` must not vary across
  profiles that are meant to share a baseline: either drop `run_hash` from
  `stable_operation_hash` (the seed already keys the stream) or make `run_id`
  an explicit profile field that sweep families share, and add a test that
  two profiles differing only in `p_high` produce a byte-identical fixed-low
  arm. Second, the aggregate profile check below.
- Report the regime indicator. W (trimmed payload over offered) is computable
  from `transport_summary.csv` in every arm and separates the three regimes
  cleanly; `compare.py` should print it next to the trim counts.

## What will happen when pp2 finishes

The sixteen-seed aggregate job will fail. `aggregate_comparison_artifacts`
in `experiments/ring_3d/compare.py` requires every artifact's `profile`
string to be identical, but each arm writes `profile.resolve().as_posix()`,
which on the cluster is `/w/nobackup/.../astra-sim/<SLURM job id>/_work/...`,
and the sixteen archived files carry sixteen distinct strings. Every earlier
wave lost at least one seed arm and failed the count gate first, so this
check has never been reached; #117 is the first run that will hit it. The two
sweep aggregations expect differing profiles and are unaffected. The aggregate
section will publish as failure, `ledger-close` will keep #64 open, and the run
will conclude failure despite 31 clean arms. A fix cannot rescue this run
(the workflow is pinned to 414dc70); the numbers in section 1 are what the
job would have produced. Fix: compare by workspace-relative path or content
hash.

## Integrity of the record

- 30 of 30 arms: congestion gate passed, transport stream attested complete
  (332-665 segments, 356-2057 GiB per arm, about 43 TB hashed and discarded).
- 70 release assets, 1.17 GB; every bundle carries `attestation.json` with the
  binary sha256, ISA level, node, and the uncompressed stream digests.
- Simulator wall hours: 64-rank fan-in 45-56 h, anchor seeds 37-49 h,
  32-rank arms 23-38 h, sr2x 11 h, pp2 open. In #116 every 64-rank arm died at
  about 26.5 h; the courier and outbox design in 414dc70 is what got this wave
  past that wall.
