# Experiments for the 10/16 deadline (planned 2026-10-02)

The paper deadline moved to 2026-10-16. Two weeks allow two or three
cluster waves (one wave at a time, each about a day from dispatch to a
read bundle) plus a day each for reading, figures and text. This page
lists what is worth running, in dispatch order, with the question each
wave answers and the outcome that would change the paper.

## Status of the open verification items

- Figures 4(a) and 4(b) are 1:1 throughout: every run behind them has
  eight spines and none failed (profiles read 2026-10-02, see
  `run-130-1to1-no-incast-data.md` and `incast-figure-data.md`). The
  "no incast" runs carry the seven-flow step-18 burst that every
  simulation in the paper carries; "no incast" means without the
  63-source burst at step 10.
- The 1:1 results are complete for all three configurations with and
  without the incast (baseline, FORGIVE, no congestion control; DCQCN
  without loss and DBLP dropping also exist).
- The 4:1 fabric has no incast runs. Its no-incast runs exist for every
  configuration (runs #123, #126, #127, #132).
- The component ablation has no forgiveness-only arm: forgiveness under
  the whole-step cap with the controller obeyed was never run (the run
  #126 arm used a pre-vesting cap on superseded code).

## Wave 1: the 4:1 incast and the forgiveness-only arm (dispatch 2026-10-02)

Twelve records, gate `forgive_v2`, three seeds each, 21 arms:

| Profile | Arms | Question | Compared with |
| --- | --- | --- | --- |
| `regime_64_dcqcn_direct7_4to1_recovery_p01_owed` | 1 | What does forgiveness alone buy, with neither vesting nor the exemption? | p_low baseline of `..._4to1_exempt_p01` and the vested no-exemption arm `..._4to1_recovery_p01`, same seed |
| `regime_64_dcqcn_direct7_4to1_exempt_p01_burst63` | 4 | Does FORGIVE keep its 16 % lead under a 63-source incast on the oversubscribed fabric? | `..._4to1_exempt_p01` (no burst), same seed |
| `regime_64_none_direct7_4to1_zero_burst63` | 1 | How far does no congestion control collapse under the incast at 4:1? | `regime_64_none_direct7_4to1_zero` |
| `regime_64_dcqcn_direct7_4to1_zero_burst63` | 1 | The lossless DCQCN reference under the incast at 4:1 | `regime_64_dcqcn_direct7_4to1_zero` |

Expectations stated before the run, so the read is not post hoc:

- Forgiveness only: between the sender-dropping arm (about 1 % at 4:1)
  and the vested no-exemption arm (5.8 to 7.5 %). If it reads above the
  vested arm, vesting costs time at 4:1 and the paper's "no vesting" row
  (9.1 to 10.2 % with the exemption) needs a sentence explaining why
  vesting still wins with the exemption on.
- 4:1 incast: the rank-8 victim link is the same 400 Gbps link as at 1:1,
  but at 4:1 the 62 remote sources share two spines, so the burst is
  spine-limited and lasts longer. No-CC should collapse harder than the
  55 % seen at 1:1. FORGIVE's result relative to its own no-burst run is
  the number that matters; a rise above the baseline's rise is the
  outcome that would weaken the incast paragraph.
- Compare 4:1 incast only with 4:1 no-incast, never across fabrics.

What changes in the paper: the forgiveness-only row of Figure 4(c), and
either a sentence in the incast paragraph (4:1 confirms 1:1) or a second
pair of panels if the 4:1 story differs.

## Wave 2: DCQCN sensitivity (dispatch after wave 1 is read)

The cheapest rebuttal to the headline is that a tuned DCQCN closes the
gap. The generator exposes `network.congestion_control.rate_ai_fraction`
per profile today; the ECN marking thresholds (KMIN, KMAX, PMAX) and the
decrease interval are literals in `generate.py` and need a small profile
field each before they can be swept. Plan: at 4:1, three seeds, the
four-arm `exempt_p01` record under (a) rate_ai_fraction four times the
default, (b) one quarter of it, (c) KMIN and KMAX doubled, (d) halved.
Four settings × 4 arms × 3 seeds = 48 arms; if the budget is tight, run
(a) and (c) first. Outcome that changes the paper: a setting under which
the baseline closes to within 5 points of FORGIVE. Otherwise one
sentence in Limitations becomes one sentence in the ablation.

## Wave 3, if time remains

- ReduceScatter-only forgiveness (Limitations names it as future work and
  reviewers will ask). Not supported by the generator or the ns-3 policy
  today; needs an eligibility field per collective phase and a receiver
  check. Worth it only if waves 1 and 2 are read by 10/09.
- Five seeds for the 1:1 incast pair, to match the headline's five seeds.
  Cheap (two more seeds of three records) but changes no number by much.

Not in scope for this deadline: 128-rank data-parallel-only workload, a
second tenant on the fabric, NSCC.

## Schedule

| Date | Step |
| --- | --- |
| 10/02 | Wave 1 profiles and records committed, dispatched |
| 10/03 to 10/04 | Read wave 1, verify every record, update `figure-data.md`, redraw Figure 4(c) row and, if needed, a 4:1 incast panel |
| 10/04 | Commit wave 2 generator fields and profiles, dispatch |
| 10/06 to 10/07 | Read wave 2, write the sensitivity sentence |
| 10/08 to 10/13 | Paper text and figures in Zechen's repository, one PR per concern |
| 10/14 | Freeze numbers; final build and page count |

Dispatch is a `workflow_dispatch` of `workflow_main.yml` with
`run_forgive_v2=true` and a `record_filter` that selects the wave's
ledger keys; a plain push to main also starts the `always` family, so the
commits carry `[skip ci]` and the wave is started by hand.
