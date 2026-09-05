# Review: CI run #117 wave readout

Version reviewed: 2026-09-05 (the readout as it stood before this pass).
The readout has since been reframed around network health as the outcome
variable, with DBLP read as Accordion's phase-adaptive tolerance plus a
lossy transport; under that framing O1 is resolved rather than open: the
operation-span p99 already reported is the episode's worst collective
(the maximum span is at step 18 or 19 in every seed) and it improves
153 ms, CI [5.0, 301.7], while the episode's total duration does not.
O2 to O11 carry over unchanged.
Level: lite (desk check). Reading: 8 sections of the readout as extracted
text; corpus: none. The DBLP paper (arXiv:2605.01989) was read as the
idea's origin only; the simulated transport is the programme's own by
decision, so no transport-fidelity objection is raised. No novelty bank was
walked.

## Summary
The document reads one CI wave of a matched three-arm simulation study
(fixed-low, phase-aware admission shedding, fixed-high) of a DBLP-derived
phase-aware bounded-loss idea on a UEC trimming fabric in ASTRA-sim and
ns-3. It claims a sixteen-seed makespan and span-p99 benefit [C2] [C5], a
mechanism by which that benefit arises [C3] [C4], the absence of any channel
under selective repair [C6], a functional safety bound [C7], and a
dose-response reading [C8], in service of the DBLP tail-latency idea [C1].

## Claims
| Marker | Claim | Section | Verdict |
| --- | --- | --- | --- |
| C1 | a transport that knows which steps are critical can accept bounded loss outside them and buy tail latency with it | The bet | contested by O1, O10 |
| C2 | The anchor did better than the no-harm bound I sized it for. | What went well | questioned by O11 |
| C3 | Admission shedding helps only through the retransmission chains it happens to delete | What went well | standing |
| C4 | What #117 proves is that the admission policy's relief is exactly the retransmission volume it removes as a side effect. | Where we are | contested by O2 |
| C5 | By the rules as written this is "supported policy benefit" on makespan and span p99 | Where we are | contested by O5 |
| C6 | once the waste is gone the admission policy has no channel left | What went well | contested by O3 |
| C7 | The bound is doing work. | What went well | questioned by O7 |
| C8 | dose is a makespan lever with a tail-latency price, and it is not the amplifier | What went wrong | contested by O4 |

## Fatal
None.

## Major
[O1] (claims/unsupported, The bet) "a transport that knows which steps
are critical can accept bounded loss outside them and buy tail latency with
it." The claim under test is relief of the burst episode's tail, yet no
result in the document is computed at the burst step. The per-step
decomposition of the same telemetry shows about 84 % of the 292 ms makespan
relief accumulating over the fourteen steady-state permissive steps, while
the burst step's 116 ms mean delta has a 95 % CI of +/-229 ms and the
aftermath step is slightly worse under the policy. Report the burst-step and
aftermath-step span and per-rank p99 as the primary estimands, with CIs.

[O2] (claims/speculation, Where we are) "What #117 proves is that the
admission policy's relief is exactly the retransmission volume it removes
as a side effect." A 0.94 correlation between two outputs of the same
simulation is stated as proof of the causal path; both can be consequences
of the ECMP timing realisation the policy perturbs. Resolve with an
intervention that fixes shed bytes and varies recovery (the forgiveness arm,
or selective repair at equal budget); until then write consistent with, not
proof of.

[O3] (claims/overreach, What went well) "once the waste is gone the
admission policy has no channel left." One single-seed arm on a 2:1 fabric
without a burst is generalised to every selective-repair fabric. Run
selective repair in the 32-rank burst family, where the burst tail exists.

[O4] (claims/unsupported, What went wrong) "dose is a makespan lever with a
tail-latency price, and it is not the amplifier." One seed per point with
unmatched fixed-low baselines across points, as the document establishes;
no cross-dose difference is separable from selection-stream plus ECMP
noise. Rerun with a shared run identifier and at least three seeds per
point before stating a direction.

[O5] (limitations/scope, Where we are) "supported policy benefit" is
claimed while the same section concedes that no residual loss is accepted
and no negative control ran. State the benefit as conditional on go-back-N
recovery and a pending control, in the verdict sentence itself.

[O6] (limitations/unstated, Where we are) "every offered byte is trimmed
and re-sent between nine and ten times." The Storm regime that produces
the anchor's confidence interval is largely produced by go-back-N recovery:
the same fabric family under the programme's own selective-repair mode
shows W of 0.02. Name go-back-N as the condition of the result in the
verdict sentence and add a selective-repair baseline to the anchor family.

## Minor
[O7] (claims/rhetoric) "The bound is doing work." Fixed-high wins Storm
makespan by 9.4 % to 3.9 % and loses on tails; state the result per metric.

[O8] (limitations/shallow) Per-rank p99 is called chaos, but the document
does not say what follows: the pre-registered primary estimand has produced
no signal in any regime or wave. Say whether the design cannot resolve it or
the estimand should be replaced by a burst-step estimand.

[O9] (limitations/unstated) The missing no-incast control is conceded but
its consequence is not carried into the verdict sentence.

## Questions for the authors
[O10] Every result assumes the phase-tolerance premise that the source
paper established on CIFAR-scale models with three workers. Is the
contribution framed as conditional on a tolerance oracle, and does any
sentence depend on the premise holding for a 70B-class model?

[O11] The 3D-parallel realism argument rests on non-sheddable pipeline
traffic, but the pp2 arm has never completed in three waves. Is any claim
contingent on it?

## Points that did not affect the recommendation
The wall-hour and release-asset accounting is complete and does not bear
on any claim.

## Recommendation
major revision, confidence high (claims and limitations walked; corpus
none; echo ratio unavailable, the document has no Limitations heading).

This review was produced by an agent following the peer-review skill;
every quoted anchor was verified by its script.
