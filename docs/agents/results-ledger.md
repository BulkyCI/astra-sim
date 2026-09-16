# Results ledger: what each run measured, what supersedes it, what stands

Written 2026-09-16. One row per run since the go-back-N result, with the
code it ran, the caveat that limits it, and the run that replaces any part
of it. A number is quotable only if its row says so and no later row
replaces it. Joe Fang's work in collaboration with Zechen Ma.

## 1. The rule for joining runs

Arms are compared only by seed, and only across runs whose simulator is
identical for the arms compared. Since run #123 the ns-3 fork has been at
`16d7c9d4d` and the frontend changes have been behaviour-neutral for every
existing arm (a legal zero threshold, a throw that never fires, an
exemption guard that only bites at `p_high = 0`), so #123 through #127
join freely. #121 and #122 join #123 for their baseline, admission and
fixed-high arms, which reproduce to the microsecond, and not for their
exempt arm.

## 2. The runs

| run | dispatched | code | what it measured | caveat | replaced by |
| --- | --- | --- | --- | --- | --- |
| #117 | 2026-09-03 | go-back-N era | phase-aware shedding under go-back-N, 16 seeds: 3.91 % of training time, worst all-reduce 15 % shorter | go-back-N recovery, not the lossy design's selective repeat; the result is about repair amplification | nothing; it is the go-back-N result and stays |
| #120 | 2026-09-06 | regime map | one seed per cell over recovery scheme, controller, fan-in, oversubscription; no repair-driven tail anywhere; the no-controller cell at 1367 ms | one seed; the no-CC figure is unpaired | the no-CC figure by #126 on three paired seeds |
| #121 | 2026-09-07 | 8dc9275, revocation defect | the congestion-exempt domain at budget 0.4, 3 seeds | the exemption ended on any repair request, two thirds of which never consulted the budget | its exempt arm by #123 (the other three arms reproduce and stand) |
| #122 | 2026-09-08 | 942f895, revocation defect | the dose front, budgets 0.1 to 0.6 and the mask ablation, 14 records | same defect; the "loss levels off at 9.3 %" reading was the defect's signature | its exempt arm by #123; baseline, admission and fixed-high columns stand and are byte-identical there |
| #123 | 2026-09-14 | main c6855f0, ns-3 9717200cc | FORGIVE v1 with the revocation corrected: the dose front, the mild cell, the control, 21 records, 84 arms | the control sheds 0.4 % at p 0.005 rather than zero; the contract was verified after the fact (section 4) | nothing; this is the v1 reference for every later join, pending #126's zero reference for the baseline sentence |
| #124 | 2026-09-15 | main 55d5767, ns-3 16d7c9d4d | v2 round 1 at budget 0.1: Bernoulli 0.5 and 0.25 stand; the other twelve arms measured mechanisms since deleted | see section 3 | |
| #125 | 2026-09-16 | main 8213401 | v2 round 2: the budget 0.05 comparison, Bernoulli 0.1 and 0.05 at 0.1, Bernoulli 0.25 at 0.05 and 0.2, 24 arms | in flight; its cluster analyzer predates the hard law, so every bundle is certified locally with the 87ad3ae analyzer before a number is read | |
| #126 | 2026-09-16 | main a1b30b0 | the references: zero tolerance at nine (fabric, seed) pairs, the recovery domain under DCQCN at 0.1, no controller at all, 15 single arms | in flight; same local certification | |
| #127 | pending | after sections 9 and 10 of the round-2 doc | one wave, 18 single arms at budget 0.1: the owed law's v1 point, the accounted ablation, Bernoulli 0.25 on each under the fresh coin, the step stop, and arm D (never re-engage) | the v1 point re-measures #123's configuration under the receiver-granted exemption and refusal-based revocation; read with TP all-reduce span and re-sent bytes per arm | |

## 3. Run #124 arm by arm

| arm | stands | note |
| --- | --- | --- |
| B25, B50 | yes, certified | joined against #123's p01 recovery arm on the same simulator |
| the other twelve arms | no | they measured mechanisms that no longer exist in the tree; nothing is quoted from them |

## 4. Certification

The per-cell contract, `shed + forgiven <= p(step) x eligible`, remainder
included, was computed by the analyzer from the start but only reported.
Since main `87ad3ae` it fails the arm, the simulator throws at cell close
if it is broken, and `min_delivered_share` names the worst cell. All 39
arms in hand at that point, the 21 recovery arms of #123 and the 18 of
#124, were re-analysed with that analyzer: no raise, worst cell at exactly
`1 - p` wherever the cap binds. Every number in section 5 rests on a
certified arm.

## 5. What is quotable today

| claim | source | number |
| --- | --- | --- |
| FORGIVE v1 at the worst cell, budget 0.1 | #123 | 12.9 to 14.1 % of training time for 6.75 to 6.89 % of gradient bytes, 5.3 times shedding per byte lost |
| the dose front | #123 | loss is 68 to 86 % of the cap; efficiency falls 1.96, 1.41, 0.95, 0.63 from budget 0.1 to 0.6 while shedding stays 0.33 to 0.45 |
| the mask | #123 | 1.4 % of forgiven bytes on critical steps at 0.1; 5.1 points of time and 4.4 of loss for the mask, paired on three seeds |
| the mild cell | #123 | 10.5 to 12.5 % for 2.37 to 2.50 % at `direct2` 2:1 |
| Bernoulli 0.25 | #124 against #123 | 16.0 to 16.2 % for 5.5 to 5.9 %, 7 to 8 % of exempt flows re-armed against 35 to 37 % |
| go-back-N | #117 | 3.91 % over 16 seeds, worst all-reduce 15 % shorter |

## 6. What is not quotable yet

- The receiver-local law's v1 point: no number until #127.
- "Against unmodified lossy RDMA under DCQCN": no sentence until #126's
  zero reference reads within 0.5 points of the fixed-low control.
- "How much of the gain is the exemption": no number until #126's
  recovery-domain arm.
- "Faster than no congestion control": the one-seed 1367 ms of #120 is
  not a table entry; #126 puts it on three paired seeds.
- Anything below budget 0.1 or below Bernoulli 0.25: #125.
- The step stop: no number until #127.
- The 9.3 % ceiling: not a result; it was the defect.

## 7. Documents and where they stand

`figure-data.md`, the two decks, the slides prompt and `forgive-protocol.md`
quote #123 for every v1 figure and one sentence each saying #121 and #122
predate the fix. None of them yet contains a v2 number; those are recorded in
[forgive-v2-round2.md](forgive-v2-round2.md) until #125, #126 and #127
are read, after which the decks get one v2 slide.
