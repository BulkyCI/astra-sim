# Read of the DBLP-FORGIVE draft at zee/master 7451b57 (2026-10-02)

Build: 7 pages, no overfull boxes, no undefined references; the body ends
0.27 of a column into page 7, so about a third of a column has to go before
the six-page body limit holds. Line numbers refer to `main_paper.tex` at
7451b57. Nothing here is applied; every item is Zechen's call.

## 1. One word for B = pD: budget

"Budget" is already the dominant term and the only one with the right
semantics: a budget is spent over time, which is what vesting governs,
while "limit", "allowance" and "cap" are static. Every compound in the
paper is built on it (receiver loss budget, shared receiver budget,
budget-exhausted flag, budget-controlled exemption), so standardising
costs nothing. The rule that falls out: p is the *loss tolerance* (a
fraction), B = pD is the *loss budget* (bytes). Both words stay, each for
its own quantity.

Places that mean the budget without saying it:

| Line | Now | Suggested |
| --- | --- | --- |
| 106 | "Allowing some gradient loss still leaves the question of how to allocate that allowance over time." | "... how to spend that budget over time." (the next sentence then says "assigns each receiving rank a loss budget", which reads as the answer) |
| 190 | "A per-step loss limit alone does not decide when to spend the budget or when to pause congestion response." | "A per-step loss budget alone does not decide when to spend it or when to pause congestion response." |
| 468 | "allowing us to test network-side benefits with a smaller loss allowance" | "with a smaller loss budget" (or "a smaller tolerance", since the sentence is about p; either is right, "allowance" is not) |
| 552 | "enforcing a per-step loss bound" | fine as a property of the mechanism; keep, or "per-step loss budget" if the word is to appear in the conclusion |

Places that say "tolerance" and mean p, which is correct and should stay:
84, 86, 102, 104, 106, 131, 133, 159, 165, 175, 183, 185, 190, 219, 273,
333, 424, 446, 462, 468, 552. Two of them deserve a look anyway:

- 159 "finish once a phase-dependent delivery threshold is met" and 428
  (footnote) and 552 "delivery requirement" name DBLP's 1 − p stop rule two
  ways. "Delivery requirement" is used twice; make 159 match.
- 183 "Table I lists the thresholds": the table lists tolerances, not
  thresholds (threshold is η in Equation 1). "lists the values of p."

Baseline names, for the record: "fixed-tolerance baseline" (88, 108),
"fixed-low-tolerance DCQCN baseline" (88), "fixed bounded-loss tolerance
p" (273), "fixed 0.5 %-dropping baseline" (Figure 4 caption), "DCQCN with
fixed p_low = 0.005 dropping" (512). Two names are enough, one for the
testbed baseline and one for the simulation baseline.

## 2. Findings from the whole read, most important first

### 2.1 The ablation text misdescribes the 5.8 to 7.5 % arm (line 520)

"Forgiveness alone, with no vesting and no congestion-response exemption,
reduces completion time by 5.8–7.5 %." The run behind that number (run
#132, the arm that forgives under the vested cap but keeps reacting to
congestion signals) has vesting; what it lacks is the exemption. The
earlier forgive-only arm without vesting (run #126) gave 5.5 to 6.6 % for
6.8 to 7.0 % of bytes, which is not the number in the table.

Fix: "Forgiveness with vesting but without the congestion-response
exemption reduces completion time by 5.8–7.5 % through fewer
retransmissions." and the table label "Forgiveness only" to "Forgiveness,
no exemption". The three rows then read as a clean ladder: forgiveness
with vesting (5.8 to 7.5), exemption without vesting (9.1 to 10.2), all
three (16.1 to 16.7). The commented-out sentence at line 155 ("skipping
retransmissions for selected trimmed payloads reduces completion time by
5.8–7.5 %") has the same issue if it is ever restored.

### 2.2 Length: the cuts that cost nothing

About 0.3 column must go. In order of how little is lost:

1. Design, Section III-B, third paragraph (line 194, "The
   improvement from the congestion-response exemption comes from ... about
   5.3 %"). It is an evaluation result inside the design section and is
   repeated word for word in the incast section and the takeaway. Six lines.
2. Incast section (line 531): "remaining faster than the baseline both with
   and without incast. Despite this increase relative to its own no-incast
   run, FORGIVE under incast still finishes faster than the baseline without
   incast (1254 ms)." Two sentences say one thing; keep the second. Two lines.
3. The FORGIVE takeaway (line 541) restates the section's first
   paragraph and the abstract's last sentence. If a takeaway is wanted, one
   sentence: "A budget-controlled exemption recovers about 80 % of the gain of
   disabling congestion control at 4:1 while avoiding its 55 % incast
   slowdown." Four lines.
4. Section IV opening (line 256) and Section IV-B opening (line 462) both
   explain the testbed/simulation split; the first already does it. Two lines.
5. The incast result is stated five times (abstract, introduction, design,
   incast section, takeaway). Abstract and incast section are enough; the
   introduction can keep one clause.

Items 1 to 3 alone free about half a column.

### 2.3 "40 %" is 40 percentage points (abstract 88, Table I caption 247, 273, 333, 424, 446, 448)

Table I makes the meaning unambiguous (0.8 → 40.8), and the code adds 0.40
to the tolerance. The prose says "raises the loss tolerance by 40 %",
which a reader takes as 0.8 → 1.12 until the table corrects them. The
minimum fix is in the Table I caption, "p_high = p + 40 percentage points",
and once in the abstract; the other mentions then inherit it. Zechen has
reverted this before, so this is a note, not a request.

### 2.4 Mixed percent units in the accuracy results (lines 428, 448)

"DBLP is within 1.55 % of the baseline on EffNetB0 and 0.76 % on ResNet50"
are absolute differences (72.33 − 70.78 = 1.55 points). Two paragraphs
later "differs from the baseline by only 0.19 %–2.14 % relative to the
baseline accuracy" is the same gap as a relative figure (1.55 / 72.33 =
2.14 %). Both are correct; call the first "percentage points" so the two
numbers do not look like a contradiction.

### 2.5 Small things

- Line 183: "Table I lists the thresholds" (see Section 1).
- Line 462: "demonstrating its robustness to distinct network conditions"
  and line 453 "demonstrating the robustness of DBLP to stochastic network
  events" both claim robustness from two conditions each. "under both
  conditions" says what was measured.
- Figure 4(c) is a table typeset as a subfigure. IEEE reviewers sometimes
  ask for it as a Table; harmless if the space works, but then the text
  should say "Table" where it currently says "the table reports" (line 520)
  and "Figure 4(c)".
- The probability symbol is q in the paper and P in the figure files and
  README under `figures/forgive/` (`time-utilization.pdf` legend, README
  rows). Only matters if that figure is embedded; the README should say q
  either way.
- Line 88, abstract: "about 5.3 %" is 1243.5 / 1180.6 = 5.3 %, correct.
  The incast baseline "1254 to 1313 ms" and no-CC "1126 to 1751 ms" match
  the bundles.
- Line 466: "every rank receives at least 1 − p_low of its bytes in steps
  within LSPs and 1 − p_high in steps outside LSPs" is verified in the
  bundles (worst cells 0.995 and 0.916).
- Line 151: "DCQCN's rate reductions account for 10–20 % of job
  completion time" matches 9.7 to 10.6 % at 1:1 and 20.1 to 20.3 % at 4:1.

### 2.6 If the cuts free more than needed: two Limitations sentences

Both answer questions a networking reviewer will ask first (items 5 and
10 of `paper-reviewer-questions-2026-10-01.md`):

- "The simulation runs a single job; the cost of the exemption to a
  co-located job that obeys congestion control is unmeasured."
- "DCQCN runs with the simulator's default parameters rescaled to
  400 Gbps; no parameter sweep was run."

## 3. What was checked against data

Completion times, the incast numbers, the 1 − p guarantee, the 10 to 20 %
controller cost, and the ablation arm identities were checked against the
release bundles (runs #126, #127, #130, #131, #132) and
`docs/agents/forgive-paper-section.md`. The testbed figures (speedups,
accuracies, iteration counts) were checked only for internal consistency
(93 iterations per epoch, 57.6 to 59.2 % of chunks, the accuracy ratios);
the underlying logs are not available here.
