# Data behind `figures/forgive/incast-63-sources.pdf`

This page names the raw data for every line and bar of the incast figure in
the paper repository, says exactly how each number is computed from it, and
lists the numbers so a recomputation can be checked. All files are public
GitHub release assets of this repository.

## 1. What the figure shows

The figure has two panels. Both use the non-oversubscribed fabric (eight
spines, 1:1), the `direct7` data-parallel AllReduce, DCQCN where congestion
control is on, and the three seeds 9550582, 23172535 and 94081284.

- **Top panel.** For each of the 20 training steps, the time the
  data-parallel AllReduce of that step takes, measured across all 64 ranks
  (definition in section 3), log scale. Lines are the mean over the three
  seeds; the shaded band is the range over the seeds; the grey band marks
  step 10.
- **Bottom panel.** Job completion time of the same runs (definition in
  section 3). Bars are the mean over the three seeds; whiskers are the
  range.

"Incast" means the 63-source incast: at step 10, 63 ranks each send one
128 MiB flow to rank 8 at the same moment. These flows are not part of the
AllReduce, are not eligible for forgiveness, and run under whatever
congestion control the configuration has. "No incast" means these 63 flows
are absent. Every run, with or without the incast, also carries a small
background load that is not the incast: seven 128 MiB flows into rank 8 at
step 18. It is present in all seven configurations, so it cancels in every
comparison; the bump some lines show at step 18 comes from it.

The seven configurations, with the names used in the figure:

| name in the figure | congestion control | loss policy | 63-source incast at step 10 |
| --- | --- | --- | --- |
| Baseline, no incast | DCQCN | sender drops 0.5 % of data-parallel bytes on every step | no |
| No congestion control, no incast | none | none | no |
| No congestion control | none | none | yes |
| DCQCN, no loss | DCQCN | none | yes |
| Baseline | DCQCN | sender drops 0.5 % of data-parallel bytes on every step | yes |
| Phase-aware dropping (DBLP) | DCQCN | sender drops 0.5 % on steps 1, 2, 3, 20 and 10 % on the others | yes |
| FORGIVE | DCQCN, with the exemption | receiver forgives trimmed ranges within the budget: 0.5 % on steps 1, 2, 3, 20 and 10 % on the others | yes |

The top panel draws five of the seven (the two no-incast references and
three incast runs); the bottom panel draws all seven.

**FORGIVE without the incast is not in the figure.** Its runs exist (the
same fabric, seeds and settings, from the earlier run #130) and are listed
in section 2 and section 4 because they were asked for.

## 2. Where the raw data is

Two GitHub releases hold the runs. Each release asset is one
`tar.gz` bundle per seed. The asset name below is the file to download;
the directory column is where the run's files are inside the extracted
bundle.

Release A, run #130 (no incast):
<https://github.com/BulkyCI/astra-sim/releases/tag/ueophamgwbrmpp4hm3bzgelfr3a3yhxp>

Release B, run #131 (the incast wave):
<https://github.com/BulkyCI/astra-sim/releases/tag/miiav5rlagazhvmyhwpiw4c5dlxyxmx5>

| configuration | release | asset (`<seed>` is one of 9550582, 23172535, 94081284) | directory inside the bundle |
| --- | --- | --- | --- |
| Baseline, no incast | A | `ring-3d-regime-64-dcqcn-direct7-1to1-exempt-p01-seed-<seed>.part000.tar.gz` | `seed_<seed>/fixed_p_low_baseline/` |
| FORGIVE, no incast (not in the figure) | A | same asset | `seed_<seed>/recovery_policy/` |
| No congestion control, no incast | B | `ring-3d-regime-64-none-direct7-1to1-zero-seed-<seed>.part000.tar.gz` | top level of the bundle |
| No congestion control | B | `ring-3d-regime-64-none-direct7-1to1-zero-burst63-seed-<seed>.part000.tar.gz` | top level |
| DCQCN, no loss | B | `ring-3d-regime-64-dcqcn-direct7-1to1-zero-burst63-seed-<seed>.part000.tar.gz` | top level |
| Baseline | B | `ring-3d-regime-64-dcqcn-direct7-1to1-exempt-p01-burst63-seed-<seed>.part000.tar.gz` | `seed_<seed>/fixed_p_low_baseline/` |
| Phase-aware dropping (DBLP) | B | same asset | `seed_<seed>/dblp_policy/` |
| FORGIVE | B | same asset | `seed_<seed>/recovery_policy/` |

Direct download links follow the pattern
`https://github.com/BulkyCI/astra-sim/releases/download/<release tag>/<asset>`,
for example
<https://github.com/BulkyCI/astra-sim/releases/download/ueophamgwbrmpp4hm3bzgelfr3a3yhxp/ring-3d-regime-64-dcqcn-direct7-1to1-exempt-p01-seed-9550582.part000.tar.gz>.

The directory names inside the four-arm bundles are historical and do not
say what they hold, so here is how to tell them apart from the data itself.
In `telemetry/flow_events.csv` of each directory, over the rows with
`parallelism_domain` equal to `dp`: `fixed_p_low_baseline` has about 450 of
89 600 flows with `decision` other than `admitted` (the 0.5 % dropped at the
sender) and zero `forgiven_bytes`; `dblp_policy` has about 7 300 such flows
and zero `forgiven_bytes`; `recovery_policy` has none dropped, about 2 GB of
`forgiven_bytes`, and `cc_exempt` true on almost every flow. The fourth
directory, `fixed_p_high_baseline` (10 % dropped on every step), is not
used in the figure.

## 3. How each number is computed

Every run directory holds `telemetry/collective_events.csv`,
`telemetry/rank_completion.csv`, `telemetry/flow_events.csv` and
`summary.json`. Times are in nanoseconds from the start of the simulation.

**Top panel: data-parallel AllReduce time of a step.** In
`collective_events.csv` every row is one collective on one rank, with the
columns `rank`, `parallelism_domain` (`dp` or `tp`), `training_step`,
`start_time_ns` and `end_time_ns`. For a step, take every row with
`parallelism_domain` equal to `dp` and that `training_step` (there are 64,
one per rank), and compute

    span(step) = max(end_time_ns) - min(start_time_ns)

over those 64 rows. This is the time from the first rank starting the step's
data-parallel AllReduce to the last rank finishing it. It is not the
duration on any single rank and not an average of per-rank durations. The
plotted value is `span / 1e6` in milliseconds.

**Bottom panel: job completion time.** `summary.json` has the field
`completion_time_ns_max`, which equals the largest `completion_time_ns` in
`rank_completion.csv` (64 rows, one per rank): the moment the last rank
finishes its twentieth step. The plotted value is that divided by 1e6, in
milliseconds. It is the whole 20-step run, including compute and the
tensor-parallel traffic, not the sum of the top panel's spans.

**Mean and range.** For each configuration, the three per-seed values are
averaged for the line or bar; the band or whisker runs from the smallest to
the largest of the three. Without DCQCN nothing in the simulation depends on
the seed (the seed changes the ECN marking draw and the receiver's
selection hash, not the paths), so the three "no congestion control" runs
are identical and their range is zero.

**Reproduction.** With one run directory extracted:

```python
import csv, json, sys
d = sys.argv[1]  # e.g. .../seed_9550582/recovery_policy
span = {}
for r in csv.DictReader(open(d + '/telemetry/collective_events.csv')):
    if r['parallelism_domain'] != 'dp':
        continue
    s, e, k = int(r['start_time_ns']), int(r['end_time_ns']), int(r['training_step'])
    lo, hi = span.get(k, (s, e)); span[k] = (min(lo, s), max(hi, e))
print('DP AllReduce time per step (ms):', [round((hi - lo) / 1e6, 1) for k, (lo, hi) in sorted(span.items())])
print('job completion time (ms):', json.load(open(d + '/summary.json'))['completion_time_ns_max'] / 1e6)
```

## 4. The numbers

Job completion time in ms, per seed, as read from `completion_time_ns_max`:

| configuration | 9550582 | 23172535 | 94081284 | mean (bar) |
| --- | ---: | ---: | ---: | ---: |
| Baseline, no incast | 1247.7 | 1253.1 | 1260.2 | 1253.7 |
| FORGIVE, no incast (not in the figure) | 1191.8 | 1183.7 | 1166.3 | 1180.6 |
| No congestion control, no incast | 1126.3 | 1126.3 | 1126.3 | 1126.3 |
| No congestion control | 1751.2 | 1751.2 | 1751.2 | 1751.2 |
| DCQCN, no loss | 1322.0 | 1325.3 | 1304.4 | 1317.2 |
| Baseline | 1303.4 | 1323.7 | 1311.9 | 1313.0 |
| Phase-aware dropping (DBLP) | 1312.6 | 1315.9 | 1321.3 | 1316.6 |
| FORGIVE | 1246.2 | 1242.1 | 1242.3 | 1243.5 |

Data-parallel AllReduce time per step in ms, steps 9 to 14 (the incast is
at step 10; its effect on the AllReduce lasts into the following steps),
per seed in the order 9550582 / 23172535 / 94081284:

| configuration | step 9 | step 10 | step 11 | step 12 | step 13 | step 14 |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline, no incast | 10.8 / 14.7 / 10.5 | 12.1 / 14.7 / 16.5 | 12.9 / 11.5 / 15.2 | 12.2 / 13.4 / 17.2 | 12.5 / 15.0 / 11.3 | 13.9 / 17.6 / 19.8 |
| FORGIVE, no incast (not in the figure) | 6.3 / 10.4 / 6.7 | 7.8 / 6.3 / 5.9 | 6.0 / 6.6 / 6.7 | 7.5 / 7.3 / 7.4 | 8.9 / 6.0 / 9.3 | 8.9 / 5.6 / 5.6 |
| No congestion control, no incast | 9.5 (all seeds) | 8.5 | 8.0 | 6.5 | 8.1 | 9.1 |
| No congestion control | 9.5 (all seeds) | 100.0 | 231.6 | 183.9 | 118.1 | 57.5 |
| DCQCN, no loss | 12.6 / 12.5 / 11.7 | 25.3 / 32.2 / 21.7 | 39.4 / 45.3 / 43.7 | 41.4 / 40.4 / 39.7 | 15.2 / 13.0 / 15.0 | 13.2 / 14.3 / 14.0 |
| Baseline | 10.8 / 14.7 / 10.5 | 21.3 / 29.3 / 21.9 | 44.3 / 44.1 / 41.8 | 42.5 / 38.8 / 38.8 | 11.8 / 12.2 / 15.2 | 13.6 / 14.8 / 16.1 |
| Phase-aware dropping (DBLP) | 15.6 / 11.3 / 19.1 | 21.3 / 32.4 / 20.4 | 42.8 / 42.1 / 42.9 | 40.8 / 35.4 / 37.3 | 14.4 / 13.6 / 13.9 | 13.7 / 10.4 / 15.4 |
| FORGIVE | 6.3 / 10.4 / 6.7 | 12.9 / 10.7 / 13.2 | 35.1 / 36.9 / 36.9 | 41.6 / 36.7 / 39.3 | 10.9 / 13.2 / 12.2 | 7.2 / 9.8 / 6.9 |

Steps 1 to 8 and 15 to 20 of the incast runs match the corresponding
no-incast runs to within the seed spread; the reproduction script prints all
twenty.

## 4b. Per-flow completion times (not plotted)

Each run directory also holds per-flow completion times, in two places
that agree with each other:

- `telemetry/flow_events.csv`: one row per flow, `start_time_ns`,
  `end_time_ns`, `parallelism_domain` (`dp` or `tp`), `flow_kind`
  (`foreground_payload` for collective traffic), `src`, `dst`,
  `logical_bytes`, `forgiven_bytes`, `retransmitted_bytes`. Flow completion
  time is `end_time_ns - start_time_ns`.
- `ns3/fct.txt`: the ns-3 backend's own record, one line per flow, columns
  source IP, destination IP, source port, destination port, size in bytes,
  start time in ns, completion time in ns, standalone completion time in
  ns. IPs encode the rank: `0x0b000001 + rank x 0x100`.

A data-parallel flow is one 2 097 152-byte message from one rank to one
peer; there are 89 600 per run (70 per rank per step). Under FORGIVE a flow
completes when every byte has arrived or been forgiven, so its completion
time includes no repair of the forgiven ranges; under the baseline the
sender never sends the dropped 0.5 % of flows, which is why it has about
89 150 flows instead of 89 600.

FORGIVE without the incast (run #130, `recovery_policy`), data-parallel
flows, three seeds: median 377 to 378 us, 99th percentile 792 to 1 369 us,
maximum 2 145 to 2 499 us. The paired baseline without the incast
(`fixed_p_low_baseline`): median 376 us, 99th percentile 1 470 to 1 501 us,
maximum 2 921 to 3 803 us. Tensor-parallel flows (286 720 per run) are
unchanged: median 87 to 92 us and 99th percentile 289 to 319 us in both.
The medians match because a 2 MiB flow at 400 Gbps takes about 42 us on
the wire plus queueing behind its six sibling flows into the same receiver;
FORGIVE shortens the tail, not the body.

## 5. Two readings that the figure supports, and one it does not

- Without congestion control the incast raises job completion time from
  1126.3 to 1751.2 ms (+55 %) and the AllReduce of steps 10 to 14 takes
  100 to 232 ms instead of 6 to 9 ms. With DCQCN, with or without any loss
  policy, the incast costs 3.5 to 6 % of job completion time and the
  AllReduce recovers by step 13.
- FORGIVE under the incast (1242 to 1246 ms) is faster than the baseline
  under the incast (1303 to 1324 ms) by 4.4 to 6.2 %, and as fast as the
  baseline without the incast (1248 to 1260 ms).
- The figure does not show that FORGIVE is unaffected by the incast: against
  its own no-incast runs (1166 to 1192 ms) FORGIVE pays 4.6 to 6.5 %, about
  what DCQCN pays. The incast flows themselves are not eligible for
  forgiveness and drain under DCQCN in 219 to 235 ms in every DCQCN
  configuration.

## 6. Provenance

Figure drawn by `docs/agents/figures/paper-figures.py` (section 10 of the
script) on 2026-09-27 from the bundles above; the per-seed table in section
4 was recomputed from the same bundles on 2026-09-28. Run #130 is the
non-oversubscribed configuration under the design-of-record rules (main
`65e98e7`); run #131 is the incast wave (main `7f787ba`). The wider context
is `figure-data.md` sections 16 and 20 and `forgive-paper-section.md`
section 3.8.
