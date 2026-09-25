# Review of the DBLP-FORGIVE draft (2026-09-25)

Against `docs/agents/forgive-paper-section.md` (the write-up), `figure-data.md`
and `results-ledger.md`. Each item quotes the draft, says what is wrong or
missing, and gives the replacement or the file to take it from. Six-page
budget: every proposed addition names what to cut for it.

## The one structural problem

> (Section 5, Evaluation) "We evaluate DBLP on a data-parallel testbed and
> FORGIVE in simulations combining data and tensor parallelism across 64
> ranks. ... Pipeline parallelism is not evaluated."

1. The body contains no FORGIVE evaluation at all. The FORGIVE numbers appear
   only in the abstract and introduction; the setup paragraph is commented
   out, and there is no results subsection, table or figure. A reviewer will
   read the abstract's 16 % as unsupported.
2. Add one setup paragraph, one table and one paragraph, about 40 lines:
   - Setup (from write-up 3.1, compressed): 64 ranks, Llama-3-70B shape, TP 8
     on a leaf, DP 8 across leaves; two-tier Clos, 8 leaves x 8 hosts,
     400 Gbps, live spines 8 / 4 / 2 for 1:1 / 2:1 / 4:1; `direct7` AllReduce
     (fan-in 7 and fan-out 7); UEC-style trimming with selective
     retransmission, 1 ms RTO, PFC off, per-flow ECMP; DCQCN as configured;
     20 steps, critical steps 1, 2, 3, 20 at p = 0.005, else 0.1; three seeds
     (which move the ECN marking draw and the selection hash, not path
     selection); metric = job completion time against the p_low baseline on
     the same seed; every FORGIVE run verified to deliver at least 1 - p per
     rank and step.
   - Table (write-up 3.3 and 3.4 merged), most congested configuration,
     budget 0.1, rows: p_low baseline, DCQCN baseline (zero tolerance),
     sender-side shedding, forgiveness with congestion control on, FORGIVE,
     FORGIVE + pacing 0.25, budget in full at step start, no congestion
     control; columns: completion-time reduction, DP bytes lost,
     retransmitted bytes. Numbers in write-up 3.1c, 3.3, 3.3c, 3.4.
   - Paragraph on the incast (write-up 3.8): the table there is the result
     that answers "why not just turn congestion control off".
3. Space: cut Table `tab:latency_comparison_resnet` (its numbers are in the
   text and Figure 3(c)(d)) and either Figure `fig: training-time-normalized`
   or Table `tab:training_time_comparison` (they carry the same six numbers).
   That frees about the space needed.

## Abstract

> "DBLP permits $40\%$ more gradient loss outside critical regimes"

1. It is 40 percentage points of tolerance (0.8 % to 40.8 %), not 40 % more.
   The same slip is in Section 5.5 ("Despite a $40\%$ higher gradient loss
   rate") and Table 1's caption ("$P_{high}=p+40\%$").
2. "DBLP raises the loss tolerance by 40 percentage points outside critical
   regimes with comparable test accuracy".

> "FORGIVE reduces the job completion time by $16.1$--$16.7\%$ under 4:1
> oversubscription and $4.5$--$7.5\%$ without oversubscription, relative to a
> fixed-low-tolerance DCQCN baseline."

1. Correct, but it omits the strongest result and leaves the obvious
   objection open: on these fabrics, turning congestion control off is
   faster than FORGIVE for a symmetric collective (20 % at 4:1, 10 % at 1:1).
2. Append: "Under a 63-source incast on the non-oversubscribed fabric,
   trimming without congestion control raises completion time by 55 %,
   DCQCN by 3.5--6.0 %, and FORGIVE completes as fast as the baseline runs
   without the incast, losing 1.05--1.38 % of data-parallel bytes." Source:
   write-up 3.8.

> "It progressively releases the budget as data arrives, forgives selected
> trimmed payloads, and restores congestion response when the budget
> allowance is exceeded."

1. "budget allowance is exceeded" is vague; the rule is on outstanding
   trimmed bytes.
2. "and restores congestion response while forgiven and outstanding trimmed
   bytes would exceed the budget".

## Introduction

> "Compared with raw DCQCN without discarding or forgiving bytes, FORGIVE
> demonstrates a similar reduction of approximately $16\%$."

1. Fine as a fact (the zero-tolerance reference is within -1.1 to +0.8 % of
   the p_low baseline over five seeds), but "raw DCQCN" is used here for the
   zero-tolerance run and elsewhere the reader may take the p_low baseline
   for it. Name both once.
2. "The fixed-low baseline drops 0.5 % of bytes at the sender; DCQCN with no
   loss at all completes within $\pm 1\%$ of it, so the reduction stands
   against lossless DCQCN."

> "Optional probabilistic forgiveness reduces loss further: at probability
> $0.25$, it achieves $5.8$--$6.7\%$ gains over the fixed-low-tolerance
> baseline on a non-oversubscribed fabric."

1. Wrong emphasis: the sentence promises a loss reduction and then quotes a
   time gain, which is inside the seed spread of FORGIVE without pacing
   (4.5--7.5 %). Pacing does not move time; it lowers loss.
2. "Optional probabilistic forgiveness at $P = 0.25$ keeps the same
   completion time and lowers the loss from 7.55 % to 5.5 % of data-parallel
   bytes at 4:1 (from 1.0--1.3 % to 0.27--0.42 % at 1:1)." Source: write-up
   3.4 and 3.7.

> "We present DBLP ... Our UDP/TCP implementation reduces burst-affected
> communication latency by up to $5.97\times$"

1. Fine.

## Section 2.5 (Lossy RDMA and Congestion Response)

> "With trimming and selective retransmission, the excess data-parallel
> collective duration in the two burst-affected steps amounts to only
> $0.04$--$0.62\%$ of job completion time."

1. True only for the seven-source burst of the configuration sweep; the
   63-source incast is the counterexample the paper now has. Without the
   qualifier the sentence contradicts Section 3.8's result.
2. "With trimming and selective retransmission, a seven-source burst adds
   only $0.04$--$0.62\%$ to job completion time; a 63-source incast, by
   contrast, raises it by 55 % without congestion control (Section V-x)."

> "in the 4:1 configuration, forgiveness alone reduces completion time by
> $5.5$--$6.6\%$, compared with $16.1$--$16.7\%$ when combined with FORGIVE's
> congestion-response exemption"

1. Correct (run #126 against #127). The forgive-only reference ran the
   earlier cap rule; its re-measurement under vesting is in run #132
   (reading pending). Keep the numbers, expect a small change.

## Section 3 (Design)

> "The \textit{exemption-eligible} flag is fixed when the receive flow is
> created and is set only for data-parallel AllReduce payload on a step with
> $p>0$."

1. Correct and matches the code.

> "$F+\ell \le p(R+F+\ell)$ ... equivalently, $F+\ell \le \frac{p}{1-p}R$"

1. Correct, including the range under decision on both sides (the earlier
   write-up had it wrong; this draft has it right).

> "Making the entire budget available a step start"

1. Typo: "at step start".

> "FORGIVE can further limit budget consumption by forgiving an otherwise
> eligible range with probability $P$, where $0<P\le1$."

1. $P = 0$ is now a legal setting (it forgives nothing and keeps the
   exemption; run #132 measures it). Write $0 \le P \le 1$ only if that
   result is in the paper; otherwise leave as is.

> "Handling missing gradient values is left to the application and is not
> modeled in our RDMA simulations."

1. Keep; it is the honest boundary. One clause would preempt the reviewer:
   the DBLP testbed zero-fills and converges at the same tolerance, which is
   the evidence the simulation inherits.

## Section 5.1 (Experimental Setup)

> "The network topology is treated as a black box to our system, and DBLP is
> designed to adapt to any settings."

1. Marketing; cut the second clause.

> "Our experiments focus on CNNs and a small-scale language model due to
> hardware constraints, but the protocol behavior generalizes across model
> architectures."

1. The generalization is asserted, not shown. Cut "but the protocol behavior
   generalizes across model architectures" or replace with "the simulation
   uses a Llama-3-70B-shaped workload".

## Section 5.5 (Evaluation Accuracy)

> "Besides, test accuracy converges within a stable range and may fluctuate
> within that range, which explains why some evaluation accuracies in the
> microburst experiments are higher than the no-burst results."

1. Weak as written; state the spread once as a number if available, else cut.

## Conclusion

> "Our study shows that the interaction between training dynamics and
> transport decisions fundamentally shapes system performance under realistic
> datacenter conditions."

1. Rhetoric, and FORGIVE is absent from the whole conclusion.
2. Replace the first paragraph with three sentences: on a trimming fabric
   with selective retransmission the repair tail is gone and the cost is
   congestion control's rate reduction; turning it off is fastest for a
   symmetric collective and collapses under a many-to-one incast; FORGIVE
   keeps congestion control on the traffic that needs it and, within a
   bounded loss, gives the data-parallel AllReduce back the time it takes.
   Source: write-up 3.8, last paragraph.

## The two headline metrics you named

**Total completion time.** Already the metric everywhere; keep it as job
completion time, paired by seed, against the p_low baseline.

**Link utilization.** Not measured, and I advise against it as a headline.
What exists: per-step goodput of the DP AllReduce (delivered gradient bytes
over the collective's span, aggregate over 64 ranks; FORGIVE 184--188 GB/s
against the baseline's 120--121, +55 %, figure-data section 17), trim ratio
and retransmitted bytes (fabric overhead), and per-flow completion times.
A per-link utilization can be computed from the ns-3 `qlen.txt` and flow
traces in every bundle, but the DP phase runs at roughly 70 Gbps into each
400 Gbps host link (149.5 MB per rank per step over about 20 ms), so the
absolute utilization figures will read as small and invite the wrong
question. Report goodput (+55 %) and retransmitted bytes instead; if a
utilization figure is required, define it as delivered gradient bytes over
link rate times AllReduce span and say so in the caption.

## Numbers in the draft checked against the bundles

| draft | status |
| --- | --- |
| 16.1--16.7 % at 4:1 for 7.55--7.57 % | correct (run #127, gross loss) |
| 4.5--7.5 % at 1:1 | correct (run #130) |
| 5.5--6.6 % forgiveness alone | correct (run #126, earlier cap rule) |
| 0.04--0.62 % burst excess | correct for the seven-source burst (run #120) |
| "approximately 16 %" against lossless DCQCN | correct within the zero-tolerance reference's spread |
| 5.8--6.7 % with pacing at 1:1 | correct as time, wrong as a loss claim |
| 40 % more loss | wrong wording: 40 percentage points |
