# FORGIVE v2: what changed over v1, and what prices it

The design history of the receiver's v2 policies, current at main
`59cf16c` and ns-3 `3e11ace49`. [forgive-spec.md](forgive-spec.md) states
the rules the changes below arrived at; where this file and the
specification disagree, the specification is right.
[forgive-protocol.md](forgive-protocol.md) says where each rule lives in
the code.

Joe Fang's work in collaboration with Zechen Ma.

## 1. What v2 changed, and why

Only the receiver can forgive, because only the receiver knows how much it
needs and how much it has. Every change below is a receiver change; no
sender logic moved.

**The vesting cap.** v1 measured the budget against the bytes senders had
launched into the cell. v2 measures it against the bytes the receiver has
accounted for, kept or forgiven: `forgiven <= p x (delivered + forgiven)`,
equivalently `forgiven <= p / (1 - p) x delivered`. A receiving NIC holds
both counters and never sees what a sender launched, so the law is one a
real receiver can run. A step ends with `delivered + forgiven = eligible`,
so the two forms share the ceiling `p x eligible`; the difference is when
the cap becomes available, which is what run #127 priced.

**The report follows the holes, and the sender follows the latest
report.** v1 revoked an exemption on the first refusal and never granted
it again. v2 reports `forgiven + holes + 4096 > p x owed`, the condition
that even forgiving every byte the rank is missing right now would exceed
the step's tolerance, and the sender is exempt exactly when the last
report it received said otherwise. Holes fall as repairs land, so a cell
that reported gone reports room again on its own. Two facts forced it: a
soft-cap refusal says nothing about the step, because the cap grows as
bytes arrive; and a one-way revocation ends the exemption on a
congestion episode the fabric then recovers from.

**The receiver grants the exemption.** The sender obeys its controller
until the first acknowledgement carrying the eligible bit with the gone
bit clear. It reads no cell and computes nothing about the budget, so one
round trip per flow is spent obeying and the receiver owns every decision.

**A critical step grants like any other.** v1 excluded critical steps from
the exemption by rule. Under the report rule the exclusion is redundant:
`p_low` puts the cell over the line after a few hundred kilobytes and the
controller returns almost at once, so the strict budget does the
protecting.

**Pacing.** The cap binds at the headline budget and first come first
served spends it on the first burst, so a Bernoulli coin lets the receiver
decline a forgivable trim and keep allowance for later in the step. The
coin is `hash(flow, range start, attempt)` with `attempt` the flow's count
of verdicts asked, so every trimmed arrival draws again and a declined
range meets the cap as it stands on its next trim. Nothing about a range
is remembered between trims. No ns-3 random stream is consumed and the
attempt counter is deterministic, so paired arms draw the same sequence.
A coin refusal charges nothing and sets no bit.

**The step stop.** Once `1 - p` of what one sender owes this rank for the
step has arrived, nothing that sender still holds is worth waiting for, so
the receiver acknowledges its open flows to their ends and charges the
holes to the step's pool. It is a budget decision and nothing else: no
timer, no view of the line, no check that the sender has finished. The
crossing arrival stops every open flow from that sender at once, because a
flow waiting on a repair receives nothing and would otherwise wait for its
own timeout. Run #124's arm stopped a flow whenever that one flow's
remainder fitted the cap, which fired early in the step; the rule reads
the sender's whole share instead.

**Delivered is credited per byte.** A receiving NIC credits a byte when it
accepts it, so the cap grows while the step is still arriving. Under
message-granular crediting a rank that receives one message per peer
released no budget until the step was over, which was a property of the
accounting rather than of the law.

**The contract became a guarantee.** The per-cell law was computed and
only reported. The simulator now throws at the step's last collective
completion, the analyzer fails the arm rather than reporting it, and
`min_delivered_share` names the worst cell, so an unverifiable forgiving
run is not a result.

**Zero is a legal threshold.** `p_low = 0` was refused by the generator
and the parser. A zero threshold already means "forgive nothing, shed
nothing" on every verdict path, so allowing it gives the zero-tolerance
reference arm; `exemption_eligible` requires a nonzero permissive
threshold, because acknowledgements on a step that forgives nothing would
otherwise grant an exemption against an empty budget.

**The analyzer's per-flow law.** `data_attempted_bytes >= physical_bytes`
assumed a completed flow sent every byte, which a remainder forgiveness
makes false. The law is now `data_attempted_bytes +
forgiven_remainder_bytes >= physical_bytes`, and the part of the remainder
that was never on the wire is derived as
`forgiven_remainder_unsent_bytes` rather than counted.

## 2. The ablations and what each measures

Each removes or replaces one piece of the design of record and is joined
at the seed against the arm that keeps it.

| ablation | profile key | what it measures |
| --- | --- | --- |
| the up-front cap | `cap_base = "owed"` | whether a cap available in full from the step's first packet beats one that vests with delivery. The plan is exact, because the certification holds the launches to it |
| never re-engage | `reengage = false` | the exemption's ceiling: what revocation costs in time against what it saves the fabric in re-sent bytes and in the job's own tensor-parallel collectives. Every report is still carried and counted, so the arms differ in the sender's reaction and in nothing else |
| the coin | `pacing = {"kind": "bernoulli", "p": P}` | what the receiver gains by spending the budget slowly. A declined trim is a repair, so the coin costs time and keeps allowance |
| the stop | `step_stop = true` | whether the last `p` of every sender's share is worth its bandwidth under selective repeat |

## 3. The arms of run #127

Budget 0.1 at the worst cell of the regime map (64 ranks, `direct7`, 4:1
oversubscription, DCQCN), three seeds each, 21 single arms joined at the
seed against the comparison wave's baselines. The design of record is the
vesting cap with the coin and the stop; every other arm removes one piece
of it.

| arm | what it answers |
| --- | --- |
| `p01_b25_stepstop` | the design of record entire |
| `p01_single` | the law's v1 point, neither coin nor stop |
| `p01_b25` | the coin alone |
| `p01_stepstop` | the stop alone |
| `p01_owed`, `p01_owed_b25` | the up-front cap, with and without the coin |
| `p01_noreengage` | arm D, the exemption's ceiling |

Each arm is read with two extra columns, the tensor-parallel all-reduce
span and re-sent bytes against the fixed-low baseline, which is how the
exempt flows' cost to the rest of the fabric is read.

What #127 measured is in [results-ledger.md](results-ledger.md). One
result belongs to the design rather than to the evaluation: the up-front
cap recovers 9.1 to 10.2 % of training time against vesting's 16.1 to
16.7 %, because it spends the allowance early and the controller comes
back for the rest of the step. Vesting is the law of record on that
number, and the up-front cap stays as the ablation that produced it.

## 4. Open questions

1. The headline point: budget 0.1 with a small coin, or the
   DBLP-validated 0.4, which has not run under the design of record.
2. The coin below 0.25 under the design of record. P of 0.1 and 0.05 were
   measured under the older rules only.
3. Whether `AstraSim::OperationContext` can name which half of an
   all-reduce a message belongs to, which decides whether a per-half `p`
   is a knob or a stated limitation. The budget does not distinguish
   reduce-scatter from all-gather today.
4. Uneven per-sender loss. The budget is pooled per (receiving rank,
   step), and the application's rescale from the forgiven ranges is a
   written assumption; the GPT-2 injection experiment on the May rig
   settles it, uneven against even loss at the same total, with and
   without the rescale, both halves separately.
