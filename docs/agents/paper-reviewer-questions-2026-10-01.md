# Reviewer questions on the DBLP-FORGIVE draft (2026-10-01)

Draft at `ZechenM/DBLP-0429-arxiv` tip `70274b6`. Conceptual questions a
reviewer is likely to raise, not data checks. Each entry: the question, what
the draft says (quoted or summarised, with the line in `main_paper.tex`),
why it confuses, and a fix.

## 1. Which 40 % of the gradient does DBLP drop?

**What the draft says.** Section III-B: "The first send pass follows sequential chunk order ... This probe–bitmap–retransmit loop continues until the receiver has at least a fraction 1 − p of the expected chunks. The receiver then sends a TCP stop signal" (line 184). Section V-A-5: "outside LSPs, the relaxed delivery threshold lets DBLP complete uploads earlier, including stopping an ongoing send pass" (line 440).

**Why it confuses.** With no network loss, the stop fires once the first 60 % of chunks have arrived, so the chunks never delivered are the last ones in sequence, round after round. That is systematic dropping of a fixed part of the gradient vector, not tolerance of random loss, and it is also where the no-burst training-time gains come from. The preliminary experiment (Section II-C) zeroed random entries, which is a different perturbation.

**Fix.** State which chunks go missing without a burst. Either randomise the send order per round, or report that the tail is always dropped and show the accuracy result holds under that pattern; the accuracy tables may already be that evidence, but the text must connect them.

## 2. How are missing gradient values treated, and does it bias the update?

**What the draft says.** "completes the round with missing gradient chunks zero-filled" (line 184); "the server averages the received gradients and broadcasts the result" (line 180).

**Why it confuses.** A chunk missing from one of three workers scales those entries by two thirds in the average; a chunk missing from all three zeroes them. Zero-filling without renormalisation is a biased estimator, and MLT and OptiReduce both discuss correcting it. The draft never says whether DBLP renormalises.

**Fix.** One sentence: zero-filled, no renormalisation, and why that is acceptable at the tolerances used (or cite the accuracy results as the empirical answer).

## 3. Is the LSP detector validated, or only exercised?

**What the draft says.** Equation 1 with η = 0.5 "following suggestions from" Accordion (line 169); Figure 3 "marks detected LSPs both early and later in training" (line 159).

**Why it confuses.** Accordion's threshold was tuned for a compression ratio, where a wrong call costs bandwidth. Here a false negative admits 40 % loss in a sensitive phase. The draft shows that detections occur, not that they coincide with sensitivity, and the microbursts are injected at iterations the detector never classifies as sensitive.

**Fix.** Say in Limitations that the detector's correspondence to sensitivity is not validated, and describe the cheap check: replay the detector over the gradient norms of a reliable run and count the phases it would have missed.

## 4. Is the exemption just turning congestion control off for the bulk traffic?

**What the draft says.** "When the exemption is active, the sender stops passing congestion signals to its controller" (line 223); "The improvement ... comes from selectively ignoring congestion signals for eligible flows rather than turning off congestion control entirely" (line 194).

**Why it confuses.** Data-parallel flows hold the exemption for most of their lifetime, so a networking reviewer reads this as CC off for the dominant traffic class. The two facts that answer the objection are stated nowhere together: the exemption is withdrawn whenever outstanding trims would exceed the budget, and the tensor-parallel collectives that share the leaf finish within the seed spread of the baseline (measured, not in the paper).

**Fix.** Add one sentence to the ablation or incast paragraph: the exempt senders trim about 2.4 times as much as the baseline, the budget-exhausted flag re-engages the controller when trims exceed the budget, and tensor-parallel collective time is unchanged within the seed spread.

## 5. Who pays for the exemption when another job shares the fabric?

**What the draft says.** The simulation has one job; the exempt flows share links only with their own tensor-parallel traffic and the injected incast (Section V-B-1). Limitations (line 602) do not mention multi-tenancy.

**Why it confuses.** Selective bypass of congestion control is a fairness question first. A second job obeying DCQCN on the same uplinks is the one that would absorb the exempt senders' extra trims, and nothing in the paper measures it.

**Fix.** Add to Limitations: single job, single tenant; the cost to a co-located job obeying congestion control is unmeasured.

## 6. Why does FORGIVE survive the incast?

**What the draft says.** "FORGIVE retains most of the completion-time benefit on the collective while completing the incast workload faster than the baseline, demonstrating the value of a budget-controlled exemption" (line 598); "these flows are not eligible for forgiveness" (line 585).

**Why it confuses.** The sentence claims the mechanism's value without stating the mechanism. The incast flows run under DCQCN and drain in the same time as under the baseline; what FORGIVE does is keep its own data-parallel senders at rate into the congested link, forgive the resulting trims within a 1.05 to 1.38 % budget, and hold the controller in reserve through the budget-exhausted flag. A reader cannot tell whether FORGIVE handled the incast or tolerated it; the honest answer is the latter.

**Fix.** Replace the "demonstrating" clause with three facts: the incast drains under DCQCN in the same time for every DCQCN configuration; the exempt senders' trims at the victim rank are forgiven within the budget; FORGIVE's own completion time rises about 5 % under the incast, as the baseline's does, so the lead is retained, not the incast absorbed.

## 7. Does AllGather forgiveness break synchronous data parallelism?

**What the draft says.** "Forgiveness during AllGather can leave ranks with inconsistent gradient replicas; deployments would need to address this at the application level or restrict forgiveness to ReduceScatter, which is left to future work" (line 602).

**Why it confuses.** Inconsistent replicas after AllGather means the data-parallel ranks apply different updates, which is not synchronous SGD any more. A reviewer will treat this as disqualifying unless the ReduceScatter-only variant is shown to keep most of the gain, since it halves the eligible bytes.

**Fix.** Run the ReduceScatter-only profile (a configuration change) and report its reduction; if it is close to the full result, make it the default and drop the limitation.

## 8. On what basis does the simulation's tolerance inherit the testbed's?

**What the draft says.** "We believe that tolerating 40 % higher loss outside LSPs without showing model accuracy degradation on our testbed experiments allows FORGIVE to use any threshold that is less than 40 % on the simulator" (line 526).

**Why it confuses.** The transfer crosses model class (CIFAR CNNs to a 70B-shaped workload), loss pattern (random per-entry zeroing to contiguous 4 KB ranges concentrated at bursts and at one receiver), and scale. "We believe" signals that the authors know it is unsupported.

**Fix.** Write it as an assumption: "We assume a tolerance below the testbed's 40 percentage points transfers to the simulated workload; validating bursty, correlated loss on a large model is future work." Then say in Limitations that the simulation's loss pattern differs from the testbed's.

## 9. What is the baseline, and why does it drop anything?

**What the draft says.** "The baseline runs DCQCN with fixed p_low = 0.005 sender-side dropping on every step" (line 519); Table IV has a second row, "Raw DCQCN, no loss", at −1.1 to +0.8 % of it.

**Why it confuses.** A reader meeting "fixed 0.5 % sender-side dropping" in the abstract does not know it is the fixed-tolerance transport of the DBLP testbed carried into the simulation, nor that the lossless DCQCN run is within 1 % of it, so every reduction also stands against lossless DCQCN. That second fact is the one a networking reviewer wants and it is never stated in prose.

**Fix.** One sentence after the baseline definition: "DCQCN without any dropping completes within 1 % of this baseline (Table IV), so the reductions hold against lossless DCQCN as well."

## 10. Would a tuned DCQCN close the gap?

**What the draft says.** Limitations (line 604) names NSCC as the controller not tested; the DCQCN parameters are "as configured" in the simulator and no sweep is mentioned anywhere.

**Why it confuses.** The main result is the gap between reacting and not reacting to DCQCN at one parameter setting. The cheapest rebuttal a reviewer can write is that a gentler decrease or faster increase recovers most of the 20 % that disabling congestion control recovers.

**Fix.** Add to Limitations: DCQCN runs with the ns-3 defaults rescaled to 400 Gbps and no parameter sweep was run. If time allows before camera-ready, a four-setting sweep at 4:1 on three seeds settles it.

## 11. Are DBLP's p and FORGIVE's p the same quantity?

**What the draft says.** DBLP: "the receiver has at least a fraction 1 − p of the expected chunks" (line 184). FORGIVE: "sets its loss budget to B = pD" over "the total number of payload bytes D" per rank per step (line 204).

**Why it confuses.** One is a fraction of chunks per round per worker, dropped at the tail of a sequence; the other is a fraction of bytes per rank per step, lost as 4 KB ranges wherever the fabric trims. Both are called loss tolerance p, and the accuracy evidence exists only for the first.

**Fix.** One sentence at the start of Section III: "DBLP applies p per round and worker to chunks; FORGIVE applies it per step and rank to bytes."

## 12. Why is step 20 a loss-sensitive phase?

**What the draft says.** "Steps 1, 2, 3, and 20 are designated as belonging to LSPs" (line 519).

**Why it confuses.** The first three steps follow the early-sensitivity literature; the last step has no stated reason and looks arbitrary.

**Fix.** Append: "step 20 exercises a late LSP, as Figure 3 shows them occurring in training."

## 13. Are these two papers?

**What the draft says.** "The DBLP testbed evaluates communication time and model accuracy during real training; the FORGIVE simulations evaluate network performance without computing gradient values. These experiments test complementary aspects of phase-dependent delivery" (line 319).

**Why it confuses.** A three-worker UDP parameter server with CNNs and a 64-rank RDMA simulation with no model are joined by one borrowed tolerance (item 8). The abstract and introduction do not say what each proves that the other cannot, so a reviewer scores the weaker half.

**Fix.** One clause in the abstract and the introduction: DBLP establishes that phase-dependent tolerance preserves accuracy on real training; FORGIVE establishes what that tolerance buys at scale on a trimming fabric, where the simulator can run 64 ranks but no model.

## 14. Where is the evidence for the conclusion's causal claim?

**What the draft says.** "our simulations show that congestion-induced rate reductions remain costly even when selective retransmission reduces recovery delays" (line 626).

**Why it confuses.** The measurement behind it is the "No congestion control" row of Table IV, 20.1 to 20.3 % faster than the baseline on the same trimming fabric, which is the whole cost of the congestion response once recovery is cheap. The text never names that row as the measurement of the cost; the conclusion asserts it.

**Fix.** In the ablation paragraph, label the no-CC row as the measurement: "the 20 % gap to no congestion control is the cost of the congestion response on this fabric; FORGIVE recovers 16 of those 20 points while keeping the response available."

## Priority

Items 1, 4, 6 and 10 will appear in every review. Items 7 and 8 decide whether the tolerance claim is believed. The rest are one-sentence fixes.
