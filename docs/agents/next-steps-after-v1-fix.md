# Next steps: the v1 fix, then pacing

Written 2026-09-13, after Zechen relayed Yashar's suggestions from the
2026-09-10 meeting. FORGIVE is Joe's protocol, and the v2 revisions are
his own corrections to inefficiencies he found in v1. Yashar contributed
the two suggestions in section 2 and nothing else here. This document
records the reading we reported, those two suggestions, and the plan that
follows from both.

Joe Fang's work in collaboration with Zechen Ma.

Companion documents: [forgive-v1-revocation-fix.md](forgive-v1-revocation-fix.md)
is the fix and its re-run, [forgive-v2-design.md](forgive-v2-design.md) is
the change after that, and [figure-data.md](figure-data.md) supplies every
number quoted below.

## 1. The reading we reported, and why it is not yet safe to repeat

The sentence we reported was that discarded gradient bytes level off near
9.3 % because trimming stops before the budget is spent. Run #122
supports the first half. Across budgets 0.1, 0.2, 0.4 and 0.6 the exempt
arm forgives 6.4, 8.5, 9.4 and 9.2 % of data-parallel bytes, while the
admission arm discards 0.79 times the budget at every setting, so aimed
loss saturates and blind loss does not.

The second half attributes the saturation to the fabric, and the
revocation defect is an alternative cause we cannot yet rule out. Under
the defect the sender ends its exemption on any repair request, and two of
the three sites that emit one never consult the allowance. An exempt flow
therefore re-engages DCQCN constantly, slows down, and stops causing
trims. "Trimming stops before the budget is spent" is exactly what a
sender that keeps re-engaging congestion control would produce. The
measured ceiling may be the protocol's property or the defect's signature,
and the corrected re-run is what separates them.

Until that wave is read, state the saturation as measured and do not
attribute it.

## 2. Yashar's two suggestions

### 2.1 Probabilistic forgiveness

Yashar proposed that the receiver forgive with probability P rather than
forgiving every eligible trim while the allowance lasts, so that one
congestion episode cannot consume a cell at its start. Three facts bear on
it.

**The budget is already per (destination rank, step).** A cell opens when
the rank's data-parallel all-reduce for that step begins and closes when it
completes, so an episode that exhausts an allowance exhausts one
destination's allowance for one step. Our microburst fires at step 18 of
20, sending 7 simultaneous flows of 128 MiB each into rank 8, and it can
reach no cell other than (rank 8, step 18). The run-scope disaster Yashar
guards against cannot occur; the within-step ordering problem underneath it
can.

**The cell already binds at the budget we intend to publish.** Utilisation
is 81 % at budget 0.1, 54 % at 0.2, 30 % at 0.4 and 19 % at 0.6. Run #122
recommends 0.1 as the headline, because it recovers 80 % of the gain at two
thirds of the loss. Yashar's concern is therefore live precisely at the
operating point we want, and slack only at the budgets where we do not
intend to operate.

**We cannot currently count exhaustion.** No refusal counter exists.
`priority_pulls` increments only on `FLAG_PULL_PRIORITY`, which
`evaluate_forgiveness` sets only on a critical step, so it reports zero for
a permissive step however often the receiver refused. Edit 11 of the fix
adds `allowance_spent_signalled`, which is the instrument this question
needs, so the fix supplies the measurement as well as the semantics.

There is a fourth argument Yashar did not make and we should: an
independent draw per range decorrelates which gradient elements the
receiver loses, where spending the cap first come first served concentrates
the loss in one contiguous burst of ranges. That argument is about
convergence, and section 5's out-of-scope note says why our instrument
cannot test it.

### 2.2 A zero-tolerance baseline

Yashar asked for a comparison against DCQCN with no fixed loss tolerance,
`p_low = p_high = 0`. He is right that we do not have one. Every published
delta is measured against `fixed_p_low_baseline`, which sets both
thresholds to the profile's `p_low` of 0.005 and sheds at admission, so our
control already discards about 0.4 % of data-parallel bytes.

Predicted in advance so the run can contradict it: by the admission arm's
own slope of 0.3 points of training time per percent of gradient lost,
0.4 % of bytes is worth about 0.12 points, so FORGIVE's relief should read
about 0.1 points higher against true zero. The value of the arm is not the
number. It is the sentence "measured against unmodified lossy RDMA under
DCQCN", which no reviewer can then ask for.

## 3. The synthesis: Yashar's first suggestion and our v2 revision are one mechanism

One v1 inefficiency this revision corrects is that the cap ignores how
much of the step has already arrived, so the intended change is that the
budget grow as full packets arrive and more delivered bytes leave more
allowance for trimmed ones. Written as a law, that is
`forgiven <= p * delivered`, bounded above by
`p * eligible`. Since `delivered <= eligible`, the ceiling is unchanged and
only its availability moves, so the change is a vesting schedule rather
than a change in tolerance.

Probabilistic forgiveness is the same mechanism drawn at random. Both
reserve allowance for later in the step; the Bernoulli draw adds a
parameter and reserves an expected fraction, while vesting adds no
parameter and reserves a determined one. Vesting also releases the cap
exactly when the stragglers appear, which is what v2's Goal B needs, so
the two changes reinforce each other. Run them as competing arms rather
than composing them.

Two consequences for the design of record.

**The current law already paces, weakly.** `register_eligible` fires at
flow launch, once per message, so the denominator accumulates as the step's
messages are offered rather than starting at its final value. A burst early
in a step meets a small denominator and a correspondingly small cap. How
much pacing that provides depends on how quickly a step offers its
messages, which we have not measured.

**Section 2 of the v2 design must change.** It decides to fix `eligible`
when the cell opens, taking the total from the collective library. That
decision removes the pacing described above and makes Yashar's concern
strictly worse. The resolution keeps both: `eligible` stays fixed as the
denominator of the tolerance, and the vesting cap `p * delivered` becomes a
second, tighter bound. Both invariants then hold, and `outstanding` stays
computable during the step, which is what fixing `eligible` was for.

**A probabilistic refusal is not an exhausted allowance, and the fix
already encodes that.** Under the two-bit encoding, a refusal from a coin
flip leaves `kAllowanceSpent` clear and the exemption alive, while a
refusal from a spent cap sets the bit and revokes it. Under v1 the coin
flip would double as a congestion-control decision and the two effects
would be inseparable, which is the semantic reason, beyond scheduling, that
this experiment must follow the fix.

## 4. The four moves

**Constitution.** Per (rank, step) loss budget with a phase mask (DBLP,
ours, tweaked from MLT's global tolerance) + receiver-side forgiveness of
trimmed bytes (MLT NSDI'24 stop-at-(1-p), tweaked into a per-trim verdict)
+ budgeted self-revoking congestion-control exemption (new) + within-step
cap pacing (transferred from token-bucket rate limiting for the vesting
form, from RED's random marking for the Bernoulli form) + straggler
forgiveness of unsent bytes (new). Patterns: Tweak, so each change must be
ablated against the version without it; Composition, so the whole must beat
each part at a setup the field runs now.

**Currency.** Sources marked "from memory" carry the May 2026 cutoff.

| element | ours | class |
| --- | --- | --- |
| scale | 64 ranks, Clos, 8 hosts per leaf, 4 spines, 2 failed | toy against a production fabric, current for a simulation study |
| transport | packet trimming, PFC off, selective repeat | current, UEC 1.0 shaped (from memory) |
| congestion control | DCQCN | legacy; UEC specifies NSCC, per [uec-transport-brief.md](uec-transport-brief.md) |
| workload | Llama 3 70B, TP 8, DP 8, 20 steps | current model, toy step count |
| baseline | admission shedding at 0.005 | not a baseline the field would accept, which is section 2.2 |
| metric | worst all-reduce and 20-step window, 3 to 16 paired seeds | current |

**Envelope, as an assumption to correct.** The UofT DCS SLURM cluster
through `ci/dcs/evaluate.sh`, about 31 runner jobs per wave, 56 arms in
15.6 hours at run #122's rate, so roughly 100 arms per cluster day. No
accelerators and no real fabric. Two people plus Yashar as advisor.

**Claims and instruments.** Section 5 states them as phases, each with its
kill test.

## 5. Plan

## Target

FORGIVE recovers training time by spending a bounded, phase-aware loss
allowance at the receiver, the allowance self-limits with congestion rather
than with its own size, and the exemption it grants congestion control ends
only when the allowance is spent.

## Phases

Phases 1 to 3 are one dispatch. Phase 4 depends on phase 1's instrument and
phase 5 on phase 4's cap policy.

| # | phase | claim | instrument | kill test | cost | unlocks |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Correct the revocation, re-measure v1 | The exemption ends only on a spent allowance, and the 9.3 % ceiling belongs to the fabric | The 17 edits, then gates `forgive` and `forgive_dose`, 21 comparisons at 4 arms | The forgiven share at budget 0.4 moves outside 9.2 to 9.4 % by more than the seed spread of about 0.5 points, which retires the sentence in section 1 | 2 engineer days, 84 arms, about 1 cluster day | every later phase, and `allowance_spent_signalled` |
| 2 | Zero-tolerance reference | Relief is measured against unmodified lossy RDMA under DCQCN | 9 `single` records at `p_low = p_high = 0`, gate `forgive`, one per (fabric, seed) | The reference differs from `fixed_p_low_baseline` by more than 0.5 points of training time, which invalidates every published delta | 9 arms inside phase 1's wave | the baseline sentence, and Yashar's second question |
| 3 | Congestion-neutral recovery reference | The exemption, not forgiveness alone, produces the gain | 5 `single` records at `domain = recovery`, worst cell, budgets 0.1 and 0.4 | The neutral arm reaches within 1 point of the exempt arm, which makes the exemption unnecessary and the protocol smaller | 5 arms inside phase 1's wave | the answer to "how much of this is just turning congestion control off" |
| 4 | Pacing | Reserving allowance for later in the step beats spending it first come first served, at the budget we publish | 4 arms at budget 0.1, worst cell, 3 seeds: P = 1.0, P = 0.5, P = 0.25, vesting at `p * delivered` | No arm shortens training time at equal or lower forgiven share, and cells that exhaust under P = 1.0 are rare, which retires pacing and answers Yashar with a measurement | one knob plus a `delivered` counter, 48 arms, about half a cluster day | phase 5's cap policy |
| 5 | Straggler forgiveness | Forgiving a quiet remainder saves transmission, not only repair | v2 arms 3 and 4 under the cap policy phase 4 selected | Forgiving outstanding bytes does not shorten the collective beyond the trimmed-only arm by more than the seed spread | the transition function and the idle timer, about 1 cluster day | the wire-saving claim, and the reply to MLT |

Phases 2 and 3 cost 14 arms against phase 1's 84, so the wave grows by
about 15 % and stays inside a cluster day. Drop phase 3 first if it does
not; it answers a reviewer question rather than one of Yashar's two.

Phase 2 needs 9 records rather than 21 because `p = 0` makes both `p_high`
and the phase mask inert, so the five direct7 profiles at a given seed
reduce to one arm. The distinct pairs are direct7 at 5 seeds, direct2 at 3
seeds, and no-incast at 1.

## Deferred

- Freezing the experiment, and with it any obligation to backward
  compatibility, until phase 4 reports.
- The unconditional stop at `(1 - p)` delivered, v2 arm 4, until phase 4
  shows whether the cap binds; adopting it would convert the cap from a
  ceiling into a target and cost us the self-limiting result.
- NSCC, and with it the enumeration in section 4 of the fix document that
  proves an exempt flow runs no controller.
- Any statement to Yashar attributing the 9.3 % ceiling to the fabric,
  until phase 1 reports.

## Out of scope

Convergence. Our instrument simulates the network and not the optimiser, so
the argument that Bernoulli forgiveness decorrelates loss across the tensor
is one we can make and cannot show. The claim needs the tolerance
instrument the spine names, which is a small real DDP run with the measured
loss pattern injected, and that is hardware a simulator cannot provide. Say
so rather than implying the simulation covers it.

## Ask

Is the headline budget 0.1 or 0.4? Phase 4 exists because the cap binds at
0.1, where utilisation is 81 %. At 0.4, utilisation is 30 % and pacing is
dead by construction, so phase 4 should not run at all.
