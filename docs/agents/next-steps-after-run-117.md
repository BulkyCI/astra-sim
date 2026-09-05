# Next steps after run #117: what the canary and the code say

Written 2026-09-05 from the run #117 release bundles
(`zuihrl5stp6ulacoogghyp4loy7xsjpj`) and a read of the transport and
harness code. It follows the [wave readout](run-117-wave-readout.md) and
supersedes its "decisive experiment" section. The readout graded the
phase-aware policy on network health and found relief under go-back-N. This
memo asks the researcher's next question: is that relief a property of the
idea, or of the recovery algorithm it happened to run on, and what should
the next wave be.

## 1. The canary reorders the programme

Run #117 carried one arm with selective repair, the 64-rank 2:1 canary
(`llama3_70b_64_sr2x`). It ran the same 20-step workload as the 64-rank
fan-in family, on a worse fabric (2:1 against 4:3), with the same 7-source
128 MiB burst at step 18. Fixed-low arms, one seed each:

| Family | Recovery | Fabric | W | 20-step window | DP span, steps 4-17 median | DP span, step 18 | Step 19 | Burst drain (floor 18.8 ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 16-rank anchor (seed 31415926) | go-back-N | 2:1 | 8.68 | 6795 ms | 246 ms | 935 ms | 294 ms | 423-933 ms |
| 32-rank direct (burst 7) | go-back-N | 1:1 | 3.02 | 4503 ms | 110 ms | 451 ms | 1057 ms | 838-1497 ms |
| 64-rank fan-in 7 | go-back-N | 4:3 | 2.58 | 5173 ms | 130 ms | 205 ms | 1330 ms | 809-1798 ms |
| 64-rank sr2x | selective | 2:1 | 0.02 | 1210 ms | 13.4 ms | 17.6 ms | 12.7 ms | 23-29 ms |

Under selective repair the same workload finishes 4.3x sooner on the worse
fabric, the burst drains in 29 ms against a 18.8 ms serialization floor,
and the DP collective at the burst step is 4 ms longer than its steady
state. Per DP flow, retransmitted bytes per offered byte are 7x to 25x
under go-back-N (32-rank arm) and 0.08x to 0.13x under selective repair.
The "Storm" and "Knee" regimes of the readout, the 3.9 % to 11 % makespan
relief, the 15 % tail result, and the 79x marginal amplification are all
properties of go-back-N re-carrying whole windows on a trimming fabric.
They are not properties of phase-aware tolerance.

Under selective repair the policy still sheds its 10 % and buys 0.78 %
makespan (9.5 ms), with span p99 and per-rank p99 both slightly negative.
The mechanism is intact; there is nothing for it to relieve.

### There is no end-host congestion control in any arm

Every generated network configuration writes `CC_MODE 12`
(`experiments/ring_3d/generate.py`, since the first CI commit on
2026-07-21). The host transport handles modes 1 (DCQCN), 3, 7, 8 and 10
only; a queue pair's rate is set to link rate at creation and changed only
inside those handlers, and the trim-as-congestion-signal path
(`RecoverTrimmedQueue`, `cnp_received_mlx`) fires only for mode 1. So no
sender in any wave has ever slowed down: each queue pair blasts at 400 Gb/s
inside a static window, is trimmed, and repairs.

This matters twice. It is faithful to the origin paper by accident, whose
transport was UDP blasting with TCP control. It is not UEC, which mandates
sender congestion control, and the programme's transport is UEC by the July
decision. The go-back-N storm is the textbook collapse of a CC-less window
transport on a lossy link, and it is the regime in which every positive
number to date was measured.

UEC's own congestion control, NSCC, is window-based, not rate-based; DCQCN
with trims mapped to CNPs is a legitimate first sender-reactive arm but is
not UEC behaviour. Turning it on requires dropping the last-hop CNP guard
at `rdma-hw.cc:635` (correct only when RCCC, which we don't have, is
enabled) and rescaling `RATE_AI`/`RATE_HAI`/`MIN_RATE` off their 100G-era
literals for 400 Gb/s links, per the UEC transport brief. The spec's
fire-and-forget primitive is UUD, not RUDI: RUDI still repairs everything
it just drops ordering and duplicate suppression.

### The decisive experiment as planned is null by construction

The readout proposed a 32-rank 1:1 fabric with the 7-source burst under
selective repair, arms none / admission / recovery-domain. The canary says
what that fabric will look like: W near zero, the burst at 1.2x to 1.5x its
serialization floor, a few milliseconds of DP-span excess in a window of
about a second. Recovery-domain forgiveness can remove at most the
re-carried bytes (2 % of offered) and one repair round trip per forgiven
range, and by its own design it leaves congestion control untouched. Its
other conceivable prize, avoiding retransmission-timeout waits, does not
exist in this model either: control is lossless (control arrivals equal
deliveries in every arm), repair is NACK-driven, and the trimmed-flow
duration histogram in the canary is smooth from 0.2 ms to 1.6 ms with no
cluster at the 1 ms RTO. Trimmed DP flows run at a median of 0.37 ms
against 0.19 ms untrimmed; that is the whole cost of loss under selective
repair here.

Building forgiveness now would produce a well-engineered null. The build
plan stays valid; its sequencing changes (section 5).

## 2. What the Accordion half can buy on a healthy fabric

The ceiling is arithmetic. DP All-Reduce is 15 % to 24 % of offered bytes
in every profile (TP is 76 % to 84 %). At `p_high` 0.1 over 17 of 20 steps
the policy can shed at most 1.6 % to 2 % of bytes. Relief in makespan is
roughly shed fraction times wire amplification: under go-back-N a 79x
amplification turned 1.2 % of bytes into 3.9 %; under selective repair the
amplification is about one and 1.8 % of bytes became 0.78 %.

Three levers exist and only three. Dose: the origin paper's operating point
is `P_high = P_low + 40` points, and the dose grid under go-back-N reached
12 % at 0.6. DP share: the modeled window carries one representative DP
bucket of 256 per step, so DP is a fifth of the bytes; at production a
70B-class step moves about 2 x 7/8 x 140 GB of gradient per rank against
about 10 GiB of TP per microbatch, so the modeled DP share understates the
lever by an order of magnitude unless overlap hides DP entirely. And
amplification, which is a broken recovery algorithm and not a lever we
should want.

Dose is bounded by the tolerance oracle. Accordion's evidence is that
training tolerates aggressive compression outside critical regimes; the
retained pure-drop evidence (CLR evidence record) is a flat tolerance of
about 1 %. If defensible pure-drop doses are a few percent, the admission
half of DBLP on a selectively repairing UEC fabric is worth under 2 % of
communication time, and the phase-aware bound is a refinement of a lever
that has no purchase. That sentence is the crux, and the next wave must
either move it or confirm it.

## 3. Where bounded loss could still have purchase: hypotheses

The canary is one point (2:1, `direct2`, 7 x 128 MiB, no CC). Each
hypothesis names an operating region where an SR fabric might re-carry
bytes or wait on repair in a way tolerance can shorten.

- H1, sustained oversubscription with fan-in. `direct7` at 2:1 or 4:1
  (four failed spines) under selective repair: repairs get re-trimmed and W
  grows. Unknown; the fan-in sweep exists only under go-back-N.
- H2, burst intensity and persistence. 7 x 1 GiB, 14 sources, or a burst
  every step. Under SR the 7 x 128 MiB burst is a 29 ms event.
- H3, congestion control on. DCQCN (mode 1) is implemented and wired to
  trims. Under go-back-N it would tame the storm and likely erase the
  relief; under SR every non-last-hop trim becomes a rate cut, and rate
  cuts become the tail mechanism. Admission shedding reduces trims and so
  reduces cuts; forgiveness, being CC-neutral by design, cannot touch them.
- H4, TC_med collapse (trimmed-queue drops, RTO tails). With 64-byte trims
  of 4 KiB packets and a 25 % share the arithmetic does not allow it and
  it has never been observed. Drop.
- H5, control-plane queueing delay under load. Control is strict-priority
  and lossless in every arm. Drop unless H1 shows it.

The regime map is the wave that tests H1 to H3 at once, under selective
repair only, fixed-low arm only (a characterization needs no comparison),
one seed:

| Axis | Points |
| --- | --- |
| Congestion control | none (`CC_MODE 12`), DCQCN (mode 1) |
| DP fan-in | `direct2`, `direct7` |
| Oversubscription | 2:1, 4:1 |

Eight single arms at 64 ranks; the canary ran in 11 h, so the wave is days,
not weeks. Pre-registered estimands: W; burst drain time over its
serialization floor; DP span at steps 18 and 19 in excess of the step 4-17
median; trimmed-to-untrimmed DP flow median ratio; RTO count; CNP or
rate-cut count. Decision rule: the programme has an operating region if
some point shows W at or above 0.5 or a step 18 plus 19 excess of at least
20 % of the window with a repair-driven (not CC-driven) tail. If the worst
SR point's excess over serialization is under 5 % of the window, bounded
loss has no purchase on this transport, and the paper is the regime map
and the negative result.

## 4. Telemetry the map needs

These are transport changes, small, and they decide what the tail is made
of; without them the map cannot distinguish H1 from H3.

- Per queue pair: a cumulative retransmission-timeout count
  (`m_recovery_retries` resets on progress and cannot serve), a CNP or
  rate-cut count, and the time from first trim to first repair sent.
  Columns in `flow_events.csv` and sums in `transport_summary.csv`.
- A typed profile knob `network.congestion_control: none | dcqcn` that
  writes `CC_MODE`, validated, with `none` documented as the current
  default and every existing profile made explicit.
- W, wire-per-offered and burst drain time beside the trim counts in
  every report, and the per-step DP span table (the readout computed all
  of these by hand from the bundles).
- Estimand revision in the validation protocol: retire per-rank p99 as
  primary (it has never carried signal), promote W and the step 18 and 19
  spans, keep operation-span p99 as the episode's worst collective.

## 5. Order of work

1. Decide with the collaborator, as decisions and not defaults: selective
   repair becomes the default transport for every arm, with go-back-N kept
   as the "legacy recovery" appendix that explains where the July-August
   numbers came from; congestion control is a swept axis and no result is
   stated without naming its setting; DP share is a design parameter to be
   swept, not a fixed sample; per-rank p99 is retired.
2. Telemetry and the CC knob (section 4), plus the two harness fixes the
   matched waves need: drop `run_id` from the selection hash so profiles
   that differ only by name share a selection stream, and compare
   aggregate artifacts by relative profile path.
3. The regime map (section 3), one wave.
4. If the map finds an operating region: a matched dose x DP-share wave
   under selective repair at that point (`p_high` 0.1 and 0.4, TP-heavy
   and DP-heavy windows), which tests the ceiling algebra directly. The
   readout's pre-registered pi chunks 17 to 24 are the seeds.
5. Build recovery-domain forgiveness (the BLT plan) only if the map's tail
   is repair-driven, and place its decisive wave at that point. If the tail
   is CC-driven, the protocol question changes to CC-aware tolerance and
   the plan's skip-ahead variant is moot.
6. Write the negative result regardless of 3 to 5: the cost of loss on a
   UEC trimming fabric as a function of recovery algorithm and congestion
   control, with the regime table above as its first figure, and what
   bounded-loss tolerance buys in each regime. The go-back-N results are
   the amplification regime; the canary is the null; the map fills in the
   rest.

## 6. Framing, in one paragraph

DBLP is Accordion's phase-dependent budget plus a lossy transport. The
programme has simulated the budget at admission and found that it relieves
a transport that recovers badly and does nothing for one that recovers
well. That is not a failure of the simulation; it is the finding, and it
is the one a fabric designer wants: on a UEC-shaped fabric with selective
repair, the cost of a lost packet is one repair round trip and a re-carried
packet, and no bounded-loss policy can buy back more than that. The
contribution, if the map confirms the canary, is the measurement and the
regime taxonomy, with the protocol design retained as the answer to a
question the transport turned out not to ask. If the map finds a region
where selective repair still re-carries bytes or waits on repair, the
protocol work resumes there with a prize whose size is already known.

## Harness notes (not research; recorded so they are not lost)

`run_id` in the selection hash unmatches profiles that differ by name; the
aggregate check compares absolute profile paths and will fail the
sixteen-seed job when pp2 ends; a docs-only push fires a full cluster wave
(run #118 on 2026-09-05 was cancelled but its aggregate jobs still wrote
"missing" rows to ledger issue #65), so the workflow needs a paths filter;
the experiment README is stale in several places (it is not the
record; the code and the validation protocol are) and its congestion
control sentences go with section 4's knob.
