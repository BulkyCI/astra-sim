# Plan for the DBLP paper repository (BulkyCI/DBLP, main)

Written 2026-09-26. The clone is at `/config/repositories/DBLP`; `main` is
at `d4e3e21` (2026-09-23), `main_paper.tex` is the draft reviewed in
`paper-draft-review-2026-09-25.md`, and the committed `main_paper.pdf` is
eight pages: six pages of body and a third of a column of conclusion on
page 7, then references. Against a six-page body limit the draft is
already over by about a third of a column before any FORGIVE evaluation
is added, so every PR below states what it adds and what it removes, in
lines of the two-column layout, and the sequence ends shorter than it
starts.

Style rules for every edit: match the draft's register (short declarative
sentences, present tense, numbers with the draft's precision, `$...$` for
numbers with units as the draft does), touch no sentence that is not
wrong or needed for space, add no citation that is not already in
`main_paper.bib`, and keep every new number traceable to
`forgive-paper-section.md` or `figure-data.md` in this repository.

Four pull requests, each one concern, in this order.

## PR 1: corrections of fact and wording (no new content)

About twelve lines changed, net length unchanged or slightly shorter.

1. Abstract, Section V-E and Table I caption: "40 % more gradient loss"
   and "$P_{high}=p+40\%$" become "40 percentage points" (the tolerance
   goes from 0.8 % to 40.8 %).
2. Introduction, last paragraph: "Compared with raw DCQCN without
   discarding or forgiving bytes, FORGIVE demonstrates a similar reduction
   of approximately 16 %" becomes a sentence that names both baselines
   once (the fixed-low baseline drops 0.5 % at the sender; DCQCN with no
   loss at all completes within 1 % of it), so the two are not confused
   later.
3. Introduction, last sentence: the pacing claim quotes a time gain as if
   it were a loss reduction. Replace with the loss numbers: at $P=0.25$
   the same completion time for 5.5 % instead of 7.55 % of data-parallel
   bytes at 4:1.
4. Section II-E: "the excess ... amounts to only 0.04--0.62 %" gains the
   qualifier "a seven-source burst", because the 63-source incast
   contradicts the sentence as written; the forgive-only figure moves
   from 5.5--6.6 % to the design-of-record 5.8--7.5 %.
5. Section III-C-2: "Making the entire budget available a step start"
   gains the missing "at".
6. Section III-C-4: "$0<P\le1$" becomes "$0\le P\le1$" only if PR 2 lands
   the $P=0$ result; otherwise unchanged.
7. Section IV-A: cut "and DBLP is designed to adapt to any settings" and
   "but the protocol behavior generalizes across model architectures";
   both are assertions without a measurement.

## PR 2: the FORGIVE evaluation, paid for by cuts

The draft's body has no FORGIVE evaluation; the abstract's 16 % is
unsupported in the text. This PR adds about 45 lines and removes about
55.

Additions, as a new subsection IV-E "FORGIVE on a Trimming Fabric" after
the DBLP results:

1. Setup, one paragraph of about nine lines from
   `forgive-paper-section.md` section 3.1: 64 ranks, Llama-3-70B shape,
   TP 8 on a leaf and DP 8 across leaves, two-tier Clos of 8 leaves x 8
   hosts at 400 Gbps with 8 / 4 / 2 live spines (1:1, 2:1, 4:1), all-to-all
   AllReduce with fan-in 7, trimming with selective retransmission, DCQCN
   as configured, 20 steps with critical steps 1, 2, 3 and 20 at
   $p=0.005$ and 0.1 otherwise, seeds paired, every run verified to
   deliver at least $1-p$ per rank and step.
2. One table, eight rows, three columns (completion-time reduction, DP
   bytes lost, retransmitted), most congested configuration, budget 0.1:
   fixed-low baseline; DCQCN with no loss; sender-side shedding; forgive
   with congestion control on; FORGIVE; FORGIVE with pacing 0.25; budget
   available in full at step start; no congestion control. Numbers from
   `forgive-paper-section.md` 3.1c, 3.3, 3.4 and `figure-data.md`
   section 21.
3. One paragraph on the sweep and the exemption without forgiveness
   (five lines): budget 0.05 to 0.6 under vesting, loss saturating near
   16 % above 0.4, and $P=0$ recovering 15.0--15.7 % at zero loss against
   16.1--16.7 % with forgiveness (section 3.5, 3.6).
4. One paragraph on the 63-source incast (eight lines), with its four
   numbers: no congestion control 1126 to 1751 ms, DCQCN 1304--1325 ms,
   FORGIVE 1242--1246 ms for 1.05--1.38 % loss, sender-side shedding
   within 1 % of its baseline (section 3.8).
5. One figure only if the page count allows after the cuts: the incast
   per-step DP span for the three transports, drawn from
   `figure-data.md` section 20 with the repository's figure scripts and
   exported as PDF into `figures/forgive/`.

Cuts:

1. Table `tab:latency_comparison_resnet` (about 14 lines): its numbers are
   in the text and in Figure 4(c)(d).
2. Table `tab:training_time_comparison` (about 14 lines): the same six
   numbers as Figure 6.
3. Section II-A (about 9 lines): it repeats the introduction's first
   paragraph.
4. The last two paragraphs of Section IV-D (about 10 lines): the
   microburst-accuracy explanation is a restatement.
5. In Figure 5, the CDF row, drop the 60 % and 80 % panels (the 70 % and
   90 % panels and the ResNet panel carry the claim), about 6 lines of
   height.

## PR 3: abstract, introduction and conclusion aligned with PR 2

About fifteen lines changed, net length shorter.

1. Abstract: replace "restores congestion response when the budget
   allowance is exceeded" with "while forgiven and outstanding trimmed
   bytes would exceed the budget"; append one sentence with the incast
   result; quote the five-seed headline (15.7--16.9 %) or keep the
   three-seed figure, consistently with PR 2's table (recommendation:
   three seeds in the table, five seeds named in the setup sentence).
2. Introduction, FORGIVE paragraph: one sentence on the mechanism's
   measured split (the exemption is fifteen of the sixteen points, the
   loss bounds it), which is what the paper now claims.
3. Conclusion: replace the first paragraph (rhetoric, no FORGIVE) with
   three sentences from `forgive-paper-section.md` 3.8: the repair tail
   is gone on a trimming fabric and the cost is the rate reduction;
   turning congestion control off is fastest for a symmetric collective
   and collapses under a many-to-one incast; FORGIVE keeps congestion
   control on the traffic that needs it and gives the AllReduce back the
   time it takes within a bounded loss. Cut the second paragraph's last
   sentence ("practical and scalable path").

## PR 4: figures (only if PR 2 shows room)

Redraw nothing that exists; add at most one PDF figure for FORGIVE
(incast per-step span, or goodput per configuration) generated by
`docs/agents/figures/forgive-metrics.py` and `dp-allreduce-goodput.py`
from the bundles, with the draft's caption style (one sentence of what
is plotted, one of what it shows).

## What I cannot verify here

There is no LaTeX on this machine, so the page count after each PR is
checked by building the PDF elsewhere (Overleaf or the author's machine)
and reading it with pypdf; each PR description states the expected line
delta and asks the reviewer to confirm the page count. I will try to
provision a user-space TeX (tectonic) in the scratchpad before PR 2; if
that works, each PR carries a measured page count.

## Out of scope

The DBLP testbed numbers, the training-time normalisation question in
`introduction-revision-notes.md`, the author list, and any figure that is
not needed to support a sentence in the text.
