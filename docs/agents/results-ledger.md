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
| #123 | 2026-09-14 | main c6855f0, ns-3 9717200cc | FORGIVE v1 with the revocation corrected: the dose front, the mild cell, the control, 21 records, 84 arms | the control sheds 0.5 % at p 0.005 rather than zero; the contract was verified after the fact (section 4) | nothing; this is the v1 reference for every later join, pending #126's zero reference for the baseline sentence |
| #124 | 2026-09-15 | main 55d5767, ns-3 16d7c9d4d | v2 round 1 at budget 0.1: Bernoulli 0.5 and 0.25 stand; the other twelve arms measured mechanisms since deleted | see section 3 | |
| #125 | 2026-09-16 | main 8213401 | v2 round 2: the budget 0.05 comparison, Bernoulli 0.1 and 0.05 at 0.1, Bernoulli 0.25 at 0.05 and 0.2, 24 arms | read 2026-09-17, all 24 arms certified locally (worst cell 0.950 at budget 0.05, 0.94 to 0.98 under the coin at 0.1); measured on the same rules as #123 and #124 (sticky coin, one-way exemption, no exemption on critical steps) | nothing; #127 re-measures the v1 point and the coin under the design of record |
| #126 | 2026-09-16 | main a1b30b0 | the references: zero tolerance at nine (fabric, seed) pairs, forgive-but-obey-DCQCN at 0.1, no controller at all, 15 single arms | read 2026-09-16, all 15 certified locally (recovery arms verified at 0.9, zero arms not applicable) | nothing |
| #130 (run 35233809033) | 2026-09-17 | main 65e98e7 | the healthy cell: `direct7` at 1:1 (8 spines), vesting at 0.1 with and without the coin, the zero-tolerance reference, 9 records, 18 arms | read 2026-09-18, all 18 certified locally (FORGIVE worst cell 0.916 to 0.948, coin 0.983 to 0.984); the kill test (control trim ratio under 0.5 % and FORGIVE under 2 points) did not fire | nothing |
| #131 (run 35956943724) | 2026-09-24 | main 7f787ba | the 63-source incast on the 1:1 fabric: no congestion control with and without the burst, DCQCN with the burst, the four p01 arms with the burst, 12 records, 21 arms | read 2026-09-25, all arms re-analysed, FORGIVE arms verified (worst 0.905 to 0.940); neither kill test fired: no-CC with burst 1751.2 ms against 1126.3 without (+55 %), FORGIVE with burst 1242 to 1246 ms for 1.05 to 1.38 % loss; figure-data section 20 | nothing |
| #132 (run 35959366062) | 2026-09-24 | main 96bcf93 | 26 single arms under the design of record: the budget sweep (0.05, 0.2, 0.4, 0.6, 0.4 schedule off), forgiveness with congestion control on, P = 0, headline seeds 28410270 and 81117450, direct2 2:1 at budget 0.1; each joins a baseline already in hand | cancelled 2026-09-24 09:59 UTC to let #131's couriers through; re-dispatched 2026-09-25 04:14 UTC as run 36093633307; read 2026-09-26, 24 of 26 verified (two pending: schedule off seed 9550582, direct2 seed 23172535 courier rerun); figure-data section 21 | replaces every section 6 row when read |
| #127 (GitHub release #129) | 2026-09-17 | main 59cf16c, ns-3 3e11ace49 | the design of record at budget 0.1, 21 single arms: the law's v1 point, the coin, the stop, both, the up-front cap with and without the coin, never re-engage | read 2026-09-17 morning, all 21 certified (worst cell 0.900 to 0.909) | nothing; this is the reference for every later v2 join |

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

## 5. What is quotable today (design of record and the arms it does not change)

| claim | source | number |
| --- | --- | --- |
| go-back-N | #117 | 3.91 % over 16 seeds, worst all-reduce 15 % shorter |
| the control is a true zero | #126 against #123 | zero tolerance within -1.1 to +0.8 % of the fixed-low control on `direct7` (5 seeds), -2.2 to -0.4 % on `direct2`; every delta stands as "against DCQCN with no loss tolerance" |
| forgiveness alone | #126 against #123 | forgive but obey DCQCN at 0.1: 5.5 to 6.6 % for 6.8 to 7.0 % loss; the exemption roughly doubles it |
| the no-controller ceiling | #126 | 20.1 to 20.3 % faster than the control on three seeds, 25.4 % of bytes re-sent; v1 at 0.4 reaches the same 20 % |
| the design of record at 0.1 | #127 against #123 | the law's v1 point 16.1 to 16.7 % for 7.55 to 7.57 % loss; the coin at 0.25 15.8 to 16.9 % for 5.5 to 5.6 %; the stop spends to the cap (8.1 %) and recovers no time; the up-front cap 9.1 to 10.2 %, far below vesting; never re-engage 18.7 to 19.0 % for 7.6 % and 6.5 to 6.8 % re-sent; TP collective time never worse than baseline in any vested arm |
| the headline (Yashar's decision, 2026-09-17) | #127 against #123 | vesting alone at budget 0.1, arm `p01_single`: 16.1 to 16.7 % for 7.55 to 7.57 %; the coin is quoted as a side result (loss lower at no time cost), the stop is not part of the design |
| the incast test | #131 | no congestion control collapses under a 63-source burst on the 1:1 fabric (1751.2 against 1126.3 ms, 65 % of bytes retransmitted, 28 887 timeouts); DCQCN absorbs it at +3.5 to +6.0 %; FORGIVE with the burst runs as fast as the no-burst baseline (1242 to 1246 against 1247.7 to 1260.2 ms), 4.4 to 6.2 % faster than its own burst baseline, for 1.05 to 1.38 % of DP bytes |
| the design-of-record sweep | #132 | budget 0.05: 14.2 to 15.4 % for 3.8 %; 0.1 (five seeds): 15.7 to 16.9 % for 7.5 to 7.6 %; 0.2: 17.7 to 18.6 % for 13.3 to 13.5 %; 0.4: 18.3 to 18.4 % for 16.1 to 16.4 %; 0.6: 17.5 to 18.4 % for 16.1 to 17.2 % (loss saturates, trims run out); schedule off at 0.4: 22.4 to 22.5 % for 20.0 to 20.3 % |
| P = 0 (exemption without forgiveness) | #132 | 15.0 to 15.7 % at zero loss, 9.5 to 10.5 % retransmitted, against 16.1 to 16.7 % for vesting on the same seeds: forgiveness is worth about one point and halves retransmission |
| forgive only under the vested cap | #132 | 5.8 to 7.5 % for 6.3 to 6.9 % of DP bytes |
| `direct2` 2:1 at budget 0.1 | #132 | 5.8 to 6.5 % for 0.89 to 0.93 % (two seeds) |
| the healthy cell | #130 | `direct7` at 1:1, control 1248 to 1260 ms trimming 0.02 to 0.04 % of bytes: vesting at 0.1 recovers 4.5 to 7.5 % for 1.0 to 1.3 % of DP bytes, the coin at 0.25 5.8 to 6.7 % for 0.27 to 0.42 %; zero tolerance -0.4 to +1.6 % of the control, sender-side shedding 0.1 to 0.3 %, loose baseline -0.4 to +0.7 % |

Every FORGIVE number above ran the rules of main `59cf16c` (vesting, the
holes rule, the receiver-granted exemption following its latest report).
The baselines, the zero-tolerance reference, the no-controller reference
and the sender-side shedding arms are unchanged by the rule set and stand
from whichever run measured them. The 2026-09-21 audit
(paper-section-audit.md) corrected the shedding-loss column of the dose
front (it equals the mask-weighted cap: 8.1, 16.1, 31.7 to 32.3, 48.0 to
48.2 %) and the critical-step share of the headline (1.25 to 1.26 %).

## 6. Measured under the earlier rule set (superseded, not quoted)

Runs #123 and #125 ran FORGIVE with the accounted cap without the holes
term, a one-way revocation and no exemption on critical steps; their
FORGIVE arms are kept for the record and replaced as noted. Their
baselines and shedding arms stand.

| claim | source | number | replaced by |
| --- | --- | --- | --- |
| FORGIVE v1 at the worst cell, budget 0.1 | #123 | 12.9 to 14.1 % of training time for 6.75 to 6.89 % of gradient bytes, 5.3 times shedding per byte lost | #127 at 0.1 (16.1 to 16.7 % for 7.55 %); the sweep, the mask cost, the mild cell and pacing below 0.25 await a re-run under vesting |
| the dose front | #123 | loss is 67 to 84 % of the cap; efficiency falls 1.96, 1.41, 0.95, 0.63 from budget 0.1 to 0.6 while shedding stays 0.33 to 0.45 | #127 at 0.1 (16.1 to 16.7 % for 7.55 %); the sweep, the mask cost, the mild cell and pacing below 0.25 await a re-run under vesting |
| the mask | #123 | 1.4 % of forgiven bytes on critical steps at 0.1; 5.1 points of time and 4.4 of loss for the mask, paired on three seeds | #127 at 0.1 (16.1 to 16.7 % for 7.55 %); the sweep, the mask cost, the mild cell and pacing below 0.25 await a re-run under vesting |
| the mild cell | #123 | 10.5 to 12.5 % for 2.37 to 2.50 % at `direct2` 2:1 | #127 at 0.1 (16.1 to 16.7 % for 7.55 %); the sweep, the mask cost, the mild cell and pacing below 0.25 await a re-run under vesting |
| Bernoulli 0.25 | #124 against #123 | 16.0 to 16.2 % for 5.5 to 5.9 %, 7 to 8 % of exempt flows re-armed against 35 to 37 % | #127 at 0.1 (16.1 to 16.7 % for 7.55 %); the sweep, the mask cost, the mild cell and pacing below 0.25 await a re-run under vesting |
| v1 at budget 0.05 | #125 | 8.0 to 8.6 % for 3.74 to 3.77 % loss, 47 to 49 % of exempt flows re-armed; admission at 0.05 recovers 0.1 to 1.3 % | #127 at 0.1 (16.1 to 16.7 % for 7.55 %); the sweep, the mask cost, the mild cell and pacing below 0.25 await a re-run under vesting |
| the coin below 0.25 | #125 against #123 | at budget 0.1: P = 0.1 gives 15.3 to 16.7 % for 2.6 to 2.9 % loss, P = 0.05 gives 15.0 to 16.6 % for 1.2 to 1.3 % loss, no exempt flow re-armed at either; the time gain is flat from P = 0.25 down while loss falls with P | #127 at 0.1 (16.1 to 16.7 % for 7.55 %); the sweep, the mask cost, the mild cell and pacing below 0.25 await a re-run under vesting |
| the coin across budgets | #125 | P = 0.25 at budget 0.2: 17.6 to 18.0 % for 7.2 to 7.6 % (v1 there: 16.0 to 16.7 % for 11.1 to 12.2 %); at budget 0.05: 13.5 to 14.8 % for 3.1 to 3.2 % (v1: 8.0 to 8.6 % for 3.8 %) | #127 at 0.1 (16.1 to 16.7 % for 7.55 %); the sweep, the mask cost, the mild cell and pacing below 0.25 await a re-run under vesting |

### Not quotable yet

- The receiver-local law's v1 point: no number until #127.
- The coin below 0.25 under the design of record (P = 0.1 and 0.05 were measured only under the old rules in #125).
- The 9.3 % ceiling: not a result; it was the defect.

## 7. Documents and where they stand

`figure-data.md` (sections 11 and 12), the two decks and the slides
prompt quote #123, #125 and #126 as read above, state the design of
record in one paragraph, and name #127 as running with no number quoted.
`forgive-protocol.md` and `forgive-design-plain.md` describe the
protocol as built at `59cf16c`. `forgive-paper-section.md` (2026-09-18)
is the draft section for the preprint's revision, vesting primary and
the coin secondary, with every number above it. No document keeps a
pre-fix sentence.
