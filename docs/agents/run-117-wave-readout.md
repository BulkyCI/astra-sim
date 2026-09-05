# CI run #117 wave readout

Record of the state of CI run #117 (commit `414dc70c51ff`, workflow run
33526691181, ledger issue #64, release tag `zuihrl5stp6ulacoogghyp4loy7xsjpj`)
as read on 2026-09-04 23:23 UTC, before the run finished. It exists because
this is the first wave in which every cluster arm outlived the 24-hour
runner-token ceiling, so it is the first with a complete sixteen-seed anchor
family and complete fan-in and burst sweeps - and because the run's own
aggregate job will not be able to say so (see "What will happen when pp2
finishes").

Sources: GitHub REST (run, 194 jobs, release, issues #57-#64), the 31 ledger
comments on issue #64, 16 + 8 `comparison.json` files streamed from the
release, and local re-execution of `compare.py --aggregate-inputs` and
`fan_in_sweep.py` from this tree. All wall-hour figures are the "Run the full
paired comparison" step only.

## Where the run stands

| Field | Value |
| --- | --- |
| Run state | in progress; 193 of 194 jobs completed, 0 failed, 31 skipped (hosted-path steps) |
| Comparisons collected | 30 of 31; every courier and archive job succeeded |
| Open job | `Llama 3 70B 64-rank pp2 non-sheddable control pair / Cluster comparison` |
| pp2 simulator step | started 2026-09-01 15:58:58 UTC; 79.4 h elapsed; 6720-min guard expires 2026-09-06 07:59 UTC |
| Release | 70 assets, 1.17 GB: 30 comparison bundles (16-56 MB each, with `.contents.txt` manifests), smoke/retry/trace bundles, two runtime tarballs (215 MB each); no aggregate bundles yet |
| Blocked on pp2 | the three aggregate jobs and `ledger-close` |

Simulator wall hours per completed arm: 64-rank fan-in direct4 56.0, direct
55.5, direct2 49.7, direct1 45.2; the sixteen seed arms 37.1-49.1; the 32-rank
arms 23.3-37.8; the sr2x canary 11.0. pp2 is 23 h past the longest completed
sibling. It carries pipeline activations on top of the same degraded fabric,
so a longer arm is expected, but no completed pp2 exists to calibrate against
(#115 and #116 both cancelled it early, #116 at 26.5 h with every other
64-rank arm - the token-death failure). GitHub does not serve an in-progress
job's log, so the liveness checkpoints (`wall_ms_delta`, `events_delta`)
cannot be read until it ends; classify before touching any budget, per
[simulation-liveness-and-performance.md](simulation-liveness-and-performance.md).

## Anchor family: sixteen paired seeds

Profile `llama3_70b_16.json`, ring all-reduce, 7-source step-18 microburst,
best-effort UEC-trimming fabric, three arms per seed (fixed-low 0.5 %,
phase-aware 0.5 %/10 %, fixed-high 10 %). Reproduced locally from the sixteen
archived `comparison.json` files with the `profile` field normalized (see
below); the numbers are what the CI job would compute.

Policy relief over fixed-low (positive favors the policy; 95 % two-sided t CI):

| Estimand | Fixed-low mean | Policy mean | Mean reduction | 95 % CI | % | Reading |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| makespan | 7145.1 ms | 6853.5 ms | 291.6 ms | [91.0, 492.3] | 3.91 | excludes zero |
| DP all-reduce operation-span p99 | 1026.0 ms | 872.7 ms | 153.4 ms | [5.0, 301.7] | 10.80 | excludes zero |
| DP all-reduce per-rank p99 | 755.6 ms | 760.1 ms | -4.5 ms | [-90.1, 81.0] | -4.90 | inconclusive |
| all-QP FCT p99 (diagnostic) | 11.25 ms | 11.19 ms | 0.06 ms | [-2.79, 2.92] | - | spans zero |
| DP all-reduce physical bytes | 25.34 GiB | 23.36 GiB | 1.98 GiB | [1.92, 2.05] | 7.82 | causal-load ratio 2.27 against the 0.875 GiB background burst |

Per-seed paired reductions (ms), policy versus fixed-low:

| Seed | ISA | Makespan | Span p99 | Per-rank p99 |
| --- | --- | ---: | ---: | ---: |
| 2884197 | v4 | 262.3 | 434.2 | -394.7 |
| 16939937 | v4 | 751.5 | 716.3 | 146.2 |
| 23846264 | v4 | 284.7 | 496.7 | -102.4 |
| 28230664 | v3 | 232.7 | -43.5 | -86.8 |
| 30781640 | v4 | 284.8 | 160.3 | 154.0 |
| 31415926 | v4 | -369.7 | 143.4 | -123.1 |
| 33832795 | v4 | -97.6 | 205.3 | -12.5 |
| 48086513 | v4 | 376.5 | -140.0 | 137.8 |
| 51058209 | v4 | 165.1 | -56.1 | -93.9 |
| 53589793 | v4 | 880.1 | 16.0 | 59.9 |
| 62862089 | v3 | 575.6 | -101.1 | -143.3 |
| 70679821 | v4 | -494.5 | 16.8 | 61.8 |
| 70938446 | v4 | 288.8 | 158.1 | -5.4 |
| 74944592 | v4 | 719.2 | -103.6 | 121.8 |
| 82534211 | v4 | 251.0 | -98.3 | -70.3 |
| 98628034 | v4 | 555.9 | 649.1 | 278.4 |

Headroom (fixed-high over fixed-low): makespan 681.8 ms [500.4, 863.2]
(9.42 %), span p99 108.8 ms [-46.3, 263.9] (6.06 %), per-rank p99 -12.9 ms
[-88.9, 63.0]. The phase-aware policy captured about 43 % of the unbounded
makespan headroom without shedding inside CLR, and beats fixed-high on span
p99. Mean trims per arm: fixed-low 304.8 M, policy 287.9 M, fixed-high
262.1 M.

Protocol reading (`experiments/ring_3d/VALIDATION_PROTOCOL.md`): raw gates
pass in every arm; two of three primary estimands improve with a CI excluding
zero; the causal-load ratio makes the effect plausible. The remaining
condition - the no-incast control near zero - is not clean (next section).
Read this as supported at the anchor point pending the control, not as a
settled benefit.

## The two sweeps, complete for the first time

Both are single-seed (314159265): read direction and trim counters only.

| Sweep point | Baseline trims | Policy trims | Makespan | Span p99 | Per-rank p99 | DP bytes | Wall h |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fan-in 1, direct1 (v3) | 166.9 M | 174.7 M | 0.10 % | -8.86 % | -52.35 % | 7.65 % | 45.2 |
| fan-in 2, direct2 | 277.0 M | 259.0 M | 4.25 % | -15.98 % | -19.30 % | 7.65 % | 49.7 |
| fan-in 4, direct4 | 308.6 M | 294.7 M | 1.48 % | 5.88 % | 6.70 % | 7.78 % | 56.0 |
| fan-in 7, direct | 313.8 M | 256.4 M | 11.11 % | 16.43 % | 15.75 % | 7.66 % | 55.5 |
| burst 0 (control) | 137.7 M | 121.4 M | 8.87 % | 15.64 % | 14.87 % | 7.64 % | 23.3 |
| burst 2 | 129.4 M | 119.5 M | 4.05 % | 3.61 % | 0.96 % | 7.75 % | 23.3 |
| burst 4 | 143.8 M | 138.4 M | 2.85 % | 17.02 % | 13.95 % | 7.72 % | 24.8 |
| burst 7 (32-direct) | 187.4 M | 171.8 M | 0.75 % | 7.68 % | 72.61 % | 8.16 % | 30.5 |

Fan-in: relief is non-monotone in the window (0.1, 4.3, 1.5, 11.1 % makespan)
while baseline trims rise 167 M to 314 M and flatten between 4 and 7 - the
knee. Burst sources: relief shrinks as the burst grows (8.9, 4.1, 2.9, 0.8 %
makespan).

**The negative control is not near zero.** The matrix note for
`llama3-70b-32-burst0` says relief "should be near zero"; it measured 8.87 %
makespan and 15.64 % span-p99 relief with 137.7 M baseline trims and no burst.
Under the protocol, a material benefit in the no-incast condition "indicates a
confound or implementation error". The likelier reading is that direct2 DP
traffic congests this fabric organically (run #110 saw the unwindowed form
collapse it), so burst0 is not an uncongested control - but that must be
shown before the anchor result is called supported.

## Screening arms

| Arm | Makespan | Span p99 | DP bytes | Policy trims | Reading |
| --- | ---: | ---: | ---: | ---: | --- |
| incast7 p_high 0.2 | -24.89 % | -100.28 % | 15.74 % | 227.2 M | worse on every axis; policy trims 32 % above baseline |
| incast7 p_high 0.4 | 8.40 % | -72.83 % | 31.76 % | 151.6 M | makespan recovers, tails do not |
| incast7 p_high 0.6 | 12.11 % | -4.53 % | 47.53 % | 123.2 M | largest makespan relief; fixed-high at 0.6 loses 83.9 % on both tails |
| burst4 p_high 0.4 | 19.34 % | -1.81 % | 32.04 % | 91.4 M | burst-4 keeps its advantage over 7-incast at equal dose |
| clrburst | 1.33 % | 0.00 % | 7.76 % | 180.1 M | span and per-rank p99 identical to baseline: the policy shed nothing in CLR, as designed |
| sr2x canary | 0.78 % | -14.09 % | 7.60 % | 3.7 M | completed in 11 h with 4.4 M baseline trims versus ~300 M under go-back-N (70x fewer) |

Dose is non-monotone on one seed (0.1, 0.2, 0.4, 0.6 at 7 sources); every
7-incast dose point shows the same shape: makespan can be bought, tail latency
cannot. The sr2x completion reopens sustained oversubscription as a swept
axis, per its matrix note.

## Integrity of the record

- Congestion gate: 30 of 30 arms passed (background bytes present, 4.00 MiB
  peak queue, trims > 0, zero natural drops, zero PFC on best-effort).
- Transport streams: 30 of 30 attested complete; 332-665 segments and
  356-2057 GiB uncompressed per arm, about 43 TB hashed and discarded.
- Binary: one `x86-64-v4` build (`sha256:ac669087fefe...`) on 27 arms; seeds
  28230664 and 62862089 and fan-in direct1 ran on cpunode4 with the
  `x86-64-v3` build. The attestation states cross-ISA divergence is
  expected, so the anchor aggregate mixes two binaries; carry the ISA column
  in any write-up.
- Cross-run reproducibility: burst0, burst4, burst4-ph40 and sr2x completed
  in both #116 (405073b) and #117; every reported metric is identical to the
  printed digit. 414dc70 touched only CI plumbing, so this is the expected
  result and the first time it was checkable.

## What will happen when pp2 finishes

The sixteen-seed aggregate job will fail on a profile-path check.
`aggregate_comparison_artifacts` in `experiments/ring_3d/compare.py` requires
every artifact's `profile` string to be identical, but each arm writes
`profile.resolve().as_posix()`, which on the cluster is
`/w/nobackup/.../astra-sim/<SLURM job id>/_work/.../llama3_70b_16.json`. The
sixteen archived files carry sixteen distinct strings (job ids 64890-64908).
The check was never reached before: every earlier wave (#110-#116) lost at
least one seed arm and failed the `expected_count == 16` gate first, so the
aggregate has published as `missing` in every ledger. The two sweep
aggregations are unaffected (`fan_in_sweep.py` expects differing profiles).

Consequences: the aggregate ledger section publishes as failure,
`ledger-close` keeps issue #64 open, and the run concludes failure despite 31
clean arms. A fix pushed now cannot rescue this run (the workflow is pinned to
414dc70) and "re-run failed jobs" re-runs the same code. The numbers above are
what that job would have produced. Fix for a later push: compare profiles by
workspace-relative path or content hash, with a unit test.
