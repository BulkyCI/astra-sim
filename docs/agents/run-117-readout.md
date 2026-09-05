# Run #117 readout

Run 33526691181, commit `414dc70c51ff`, release
`zuihrl5stp6ulacoogghyp4loy7xsjpj`, 30 of 31 comparisons collected
(pp2 still simulating). Three matched, nested arms per seed: fixed-low
(p = 0.005 every step), phase-aware policy (0.005 on critical steps
1, 2, 3, 20; 0.1 elsewhere), fixed-high (0.1 everywhere). Shedding at
admission: selected DP All-Reduce payload becomes 64-byte provenance
flow. Sixteen pi-chunk seeds on 16-rank 2:1 anchor; one seed each on
32-rank and 64-rank sweeps. Written 2026-09-05.

## Findings

**1. Relief comes from the recovery algorithm, not from the policy.**
One arm ran selective repair: 64-rank workload of the fan-in family on
the worse 2:1 fabric, same seven-source 128 MiB burst.

| | go-back-N arms | selective repair (sr2x) |
| --- | ---: | ---: |
| 20-step window | 4503 to 6795 ms | 1210 ms |
| DP span, steady step | 110 to 250 ms | 13.4 ms |
| DP span, burst step | 205 to 935 ms | 17.6 ms |
| burst drain (serialization floor 18.8 ms) | 423 to 1798 ms | 23 to 29 ms |
| retransmitted per offered byte, per DP flow | 7x to 25x | 0.08x to 0.13x |
| W, trimmed-payload bytes per offered byte | 2.2 to 10.4 | 0.02 |
| policy makespan relief | 3.9 to 11.1 % | 0.78 % |

Under go-back-N each trim re-carries a window; episode is a storm of
re-carried bytes; removing the marginal byte that feeds it saves 79 bytes
on the wire. Under selective repair a trim costs one repair round trip
(trimmed DP flows median 0.37 ms against 0.19 ms untrimmed, no RTO
cluster in the histogram) plus one re-carried packet, so the same
shedding saves about one byte. Policy works as designed; nothing left
for it to relieve.

**2. No arm ran sender congestion control.** Every generated config
wrote `CC_MODE 12`, which no handler implements; queue pairs send at
line rate inside a static window, get trimmed, repair. Same transport as
the origin paper by accident (UDP blasting, no CC) and same recovery as
deployed RoCEv2 NICs (go-back-N). Not UET or MRC, which repair
selectively under window-based CC that reacts to trims and delay. Every
positive number below holds only under "go-back-N, no CC".

**3. Worst collective of the episode shortens by a seventh; phase bound
costs nothing there.** Anchor, sixteen seeds:

| Estimand | Fixed-low | Policy | Delta | 95 % CI |
| --- | ---: | ---: | ---: | --- |
| makespan | 7145.1 ms | 6853.5 ms | 291.6 ms, 3.91 % | [1.13, 6.68] % |
| worst DP All-Reduce of the episode (span p99, always step 18 or 19) | 1026.0 ms | 872.7 ms | 153.4 ms, 14.9 % | [5.0, 301.7] ms |
| per-rank p99 | | | 4.5 ms | [-90.1, 81.0] ms |
| fixed-high makespan | | | 9.42 % | [500, 863] ms |
| fixed-high worst collective | | | 108.8 ms | spans zero |

Makespan gain is steady state: 84 % accrues over steps 4 to 17 at about
30 ms per permissive step; burst step plus aftermath improve 58 ms with
CI [-68, 184]; policy flattens worst seeds (four baselines above 1.3 s
drop 434 to 716 ms) and barely moves mild ones. Bound costs 242 ms in
steps 1 to 3 (fixed-high runs them at 203, 189, 247 ms against 345, 280,
256 ms), nearly the policy's whole 292 ms gain, and costs nothing
measurable at the tail. Per-rank p99 never carried signal in any wave:
top three of 320 samples, one ECMP collision moves it by half. The 50 %
swings in the 18 August notes are that noise floor.

**4. W predicts relief; shed bytes do not.** Across sixteen seeds
makespan relief correlates 0.94 with trim reduction, 13 ms per million
trims avoided; three seeds where policy added trims are the three
negative seeds; byte reduction per seed (7.1 to 8.7 %) predicts nothing.
Policy sheds 1.98 GiB of 166 GiB offered; fabric re-carries 156 GiB
less: marginal amplification 79x.

**5. Ceiling follows from three numbers.** DP All-Reduce is 15 to 24 %
of offered bytes in every profile, so at `p_high` 0.1 over 17 of 20
steps the policy sheds at most 2 % of bytes. Relief is roughly shed
fraction times amplification: 1.2 % became 3.9 % at 79x, 1.8 % became
0.78 % at 1x. Three levers only: dose, bounded by accuracy evidence
(Accordion shows compression tolerance; pure-drop evidence is a flat
1 %); DP share, which the one-bucket window holds an order of magnitude
below production gradient volume; amplification, which means a broken
recovery algorithm.

**6. Recovery algorithm decides the regime; incast and dose do not.**
The 1:1 rail fabric sits at W 2.2 with burst off under go-back-N; seven
sources raise it to 3.0. More burst sources bought less relief (8.9,
4.1, 2.9, 0.8 % at 0, 2, 4, 7 sources); burst inside a protected step
leaves W unmoved (3.01 to 3.03) while policy still sheds 10 % elsewhere.
Dose 0.6 buys 12 % makespan and sells tails (span p99 negative at every
dose above 0.1; fixed-high at 0.6 loses 84 % on both). Admission-time
shedding decides before the network speaks: it compresses the episode's
peak, cannot drain it.

## Evidence

Fixed-low health by family (W; wire bytes per offered byte):

| Family | W | Wire / offered | Regime |
| --- | ---: | ---: | --- |
| sr2x, 64 ranks, 2:1, selective repair | 0.02 | 2.5x | light |
| fan-in 1 / 2 / 4 / 7, 64 ranks, 4:3 | 1.34 / 2.22 / 2.53 / 2.58 | 5.1 to 7.7x | knee |
| burst 0 / 2 / 4 / 7 sources, 32 ranks, 1:1 | 2.23 / 2.07 / 2.28 / 3.02 | 6.4 to 9.1x | knee |
| dose 0.2 / 0.4 / 0.6, 32 ranks, 1:1 | 2.79 / 2.94 / 2.80 | 8.5 to 8.8x | knee |
| anchor, 16 ranks, 2:1, 16 seeds | 8.68 to 10.37 | 18.6 to 21.6x | storm |

Single-seed policy results (W fixed-low to policy; makespan relief):

| Arm | W | Relief |
| --- | ---: | ---: |
| fan-in 1 / 2 / 4 / 7 | 1.34 to 1.42, 2.22 to 2.13, 2.53 to 2.43, 2.58 to 2.14 | 0.10 / 4.25 / 1.48 / 11.11 % |
| burst 0 / 2 / 4 / 7 | 2.23 to 1.98, 2.07 to 1.96, 2.28 to 2.23, 3.02 to 2.82 | 8.87 / 4.05 / 2.85 / 0.75 % |
| dose 0.2 / 0.4 / 0.6 | 2.79 to 3.67, 2.94 to 2.68, 2.80 to 2.16 | -24.89 / 8.40 / 12.11 % |
| burst4 at dose 0.4 | 2.21 to 1.61 | 19.34 % |
| clrburst | 3.01 to 3.03 | 1.33 % |
| sr2x | 0.02 to 0.02 | 0.78 % |

Dose grid ran unmatched (profile name entered the selection hash; fixed
in 63ef7c2), so cross-dose ordering is noise-limited until rerun. Open
objections a reviewer will still raise: mechanism rests on a correlation
between two outputs of one simulation (the matched CC arm is the
intervention); sweeps are one seed each; no negative control ran;
tolerance oracle assumed; pipeline-traffic control unfinished after
three waves.

## Built, gated, waiting

On main, unpushed: matched sweeps (selection hash without profile name,
repo-relative aggregate check); `network.congestion_control` knob (DCQCN
or none, rates scaled to link speed, last-hop trims reach CC as UEC
v1.0.3 p. 356 requires without receiver credit); per-flow RTO, CNP and
trim-to-repair counters, with W, burst drain and per-step spans in every
report; receiver-owned forgive protocol with per-destination, per-step
ledger and carried CNP, passing native smoke and race fixtures. Eight
regime-map profiles (selective repair; CC none or DCQCN; direct2 or
direct7; 2:1 or 4:1; 64 ranks; single fixed-low arm) sit behind dispatch
input `run_regime_map`; forgive family behind `run_forgive_studies`. On
the 8-rank fixture, DCQCN alone takes W from 25.9 to 0.117.

## Decisions needed

1. Selective repair becomes default transport from here; go-back-N
   results stay as the named "recovery amplification" regime with the
   anchor as its statistical result.
2. Congestion control is a named axis in every claim; DCQCN first, NSCC
   only if a residual cost survives it.
3. DP share becomes a swept design parameter.
4. Per-rank p99 retired; W, per-step DP span at burst and aftermath
   steps, and the episode's worst collective are the estimands.
5. Dispatch the regime map (eight arms, about 11 h each). Operating
   region exists if any point shows W at or above 0.5 or burst-plus-
   aftermath excess of at least 20 % of the window with a repair-driven
   tail. If the worst point's excess over serialization is under 5 %,
   bounded loss has no purchase on this transport; paper is then the
   regime table plus the negative result.
6. After the map: matched dose by DP-share wave at its worst point, then
   forgive comparison there if the tail is repair-driven.
