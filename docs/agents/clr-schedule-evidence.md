# Evidence record: the pinned CLR schedule `[1, 2, 3, 20]`

Four parallel retrieval rounds (2026-08-17, fact-check contract: verbatim
quotes, URLs, access dates; no verdict without retrieval) gathered the
literature behind the comparison profiles' explicit critical-step mask.
This file records the verdicts and the derivation so the schedule reads as
a documented judgment, not guesswork. Modern (2023–2026) LLM sources carry
the deciding weight; vision-era work is the concept's origin story.

## Circularity guard

The DBLP bounded-loss transport paper (arXiv:2605.01989) is **the system
this project evaluates**. Its findings about phase-dependent drop
tolerance (early drops harmful, mid/late drops free) are the
**hypothesis under test** and are excluded from this evidence base by
construction: a schedule justified by the claim it is designed to test
would be circular. Every verdict below rests on sources independent of
DBLP; where the schedule appears to "agree" with DBLP, the agreement comes
from the shared upstream literature both draw on.

One consequence is stated plainly: no retained source directly measures
*pure drop* (no error feedback) tolerance as a function of training phase.
The compression literature phases its aggressiveness but uses error
accumulation; the pure-loss literature (OptiReduce, NSDI 2025: accuracy
survives "up to 1% of gradient loss") reports a flat, phase-independent
tolerance. The permissive body of this schedule is therefore a prior
consistent with independent perturbation-sensitivity evidence. The
comparison experiment itself is what tests whether phase-varying pure-drop
tolerance holds.

## Verdicts that shaped the schedule

**Early training is fragile to gradient-information loss: SUPPORTED
(independently of the system under test).**
- Deep Gradient Compression (arXiv:1712.01887): compression warm-up over
  ~2.4% of the run ("4 epochs out of 164"); "In the early stages of
  training, the network is changing rapidly, and the gradients are more
  diverse and aggressive"; "Sparsifying gradients limits the range of
  variation of the model, and thus prolongs the period when the network
  changes dramatically."
- 1-bit Adam (arXiv:2102.02888): full-precision warmup phase of "15-20% of
  the overall training steps" before compression starts, because "Adam's
  variance term is unstable during LR warmup."
- Vision-era critical periods (Achille et al. arXiv:1711.08856; Frankle et
  al. arXiv:2002.10365; Jastrzebski et al. arXiv:2002.09572; Golatkar et
  al. arXiv:1905.13277): a single early unimodal sensitivity hump (Fisher
  Information rises then decays), perturbation windows spanning ~5–30% of
  the run, damage from early deficits permanent.

**LR warmup alone is tiny: SUPPORTED.** Llama 3: 8,000 of 1,200,000 steps
(~0.7%); DeepSeek-V3: 2K steps; OLMo 2: 2,000 steps; GLM-130B: 0.5% of
samples. Warmup marks the highest-risk launch but is far narrower than the
information-loss fragility window above; the schedule protects the wider
window.

**Epoch boundaries do not exist in ~1-epoch LLM pretraining: SUPPORTED.**
LLaMA: "each token is used only once during training" (most sources);
Chinchilla: "trained on less than an epoch of data"; GPT-3 per-dataset
epoch counts around or below 1. The sampled schedule's epoch-spike term
therefore names an event with no referent in the modeled workload and was
removed rather than quantized.

**Mid-run instability exists but is positionally unschedulable: MIXED.**
PaLM: ~20 spikes "at highly irregular intervals, sometimes happening late
into training," caused by "specific data batches with a particular model
parameter state"; OLMo 2: spike frequency grows with gradient norm over
the run; DeepSeek-V3: zero spikes end-to-end with a hardened recipe;
Llama 3: "very stable ... few loss spikes." A static per-step mask cannot
encode state-dependent events, and no retrieved 2023–2026 source measures
corruption damage as a function of run position (fault-injection work,
arXiv:2604.00726, varies rate, not position). Hence no mid-run critical
steps.

**The decay/annealing tail matters at sub-frontier scale: MODERATE.**
MiniCPM (arXiv:2404.06395): in the WSD decay stage "the loss experiences a
significant rapid decline"; OLMo 2 midtraining on curated data: +10.6
average points at 7B; Llama 3: annealing gains "negligible" at 405B.
Independent second reason: a documented late-run gradient-norm blow-up
(arXiv:2506.02285) from the weight-decay x LR-schedule interaction. For a
70B-class modeled workload the tail hedge is justified; at frontier scale
it would be droppable. Step 20 is that hedge, and this is the schedule's
weakest-evidenced element, stated as such.

**Late tolerance to lost gradient contributions: INDIRECT SUPPORT.**
Gradient noise scale / critical batch size grows and plateaus as loss
falls (McCandlish arXiv:1812.06162; AI2 2025 critical-batch-size revisit;
DeepSeek-V3 ramps batch 3072 → 15360), consistent with shed traffic being
cheaper late; no source tests the shedding framing directly.

**Caveats on generality.** Staleness-type errors run opposite in phase
(ABS, arXiv:2301.08895: staleness-tolerant early, fragile late); this
schedule governs *drop*-type errors only. A deliberate LR reset can reopen
a sensitivity window late in training (arXiv:2510.09687), so criticality
is partly schedule-triggered; the static mask is an abstraction over runs
with no such resets.

## Derivation

20-step abstraction of a ~1-epoch 70B-class run:

| Steps | Label | Basis |
| --- | --- | --- |
| 1–3 | critical | Launch window at 15%: center of the independent fragility bands (DGC ~2.4%, 1-bit Adam 15–20%, vision-era hump 5–30%), wider than bare LR warmup (0.1–4%) |
| 4–19 | stable | Prior, not proven: post-warmup aggressive compression precedent (DGC reaches 99.9% sparsity, with error feedback), CBS growth; phase-varying *pure-drop* tolerance here is the hypothesis the comparison experiment tests |
| 20 | critical | Annealing hedge, moderate scale-dependent evidence; also the late gradient-norm blow-up |

Prior schedules for the record: sampled decay-and-spike masks (seed-varying;
the seed-314159265 draw marked 10/20 steps including 15, 17, 20) and the
interim quantization `[1-7, 9]` (deterministic but inherited the spike term
and an over-wide 40% critical fraction from the unexamined curve).
