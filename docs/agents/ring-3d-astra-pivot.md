# Ring-3D ASTRA-sim pivot

## Decision

The target is not a literal reproduction of the DBLP deployment. The target is
credible **mechanism-level evidence** that a phase-aware policy improves modeled
DP All-Reduce tail latency under a specified large-scale network condition that
cannot currently be measured on physical hardware.

ASTRA-sim is therefore the experimental system, not a transparent stand-in for
the paper's PyTorch/UDP/TCP prototype. A deliberate deviation is valid only if
it preserves a named causal mechanism, controls alternative explanations, and
narrows the resulting claim to what the model actually measures.

This document defines the current model boundary; it does not prescribe a
solution for a DBLP flaw. Consult the
[known-flaws register](ring-3d-known-flaws.md) before proposing a remedy or
assuming that an existing abstraction resolves a paper limitation.

## Causal contract for an acceptable deviation

Every new condition must state these five facts in its profile, manifest,
telemetry, and report:

1. **Phase source:** CLR is trace-derived or an explicitly labeled proxy.
2. **Network stressor:** what creates the loss or congestion, where it acts,
   its seed, and its duration or byte budget.
3. **Policy action:** which traffic is eligible and exactly what changes when
   the policy selects it.
4. **Completion semantics:** how a simulated collective completes, fails, or
   accepts residual missing data.
5. **Measured consequence:** a preregistered tail-latency/makespan metric plus
   raw transport signals showing that the stressor occurred.

If any item is absent, describe the result as an exploratory simulator trace,
not empirical evidence for a transport mechanism.

## Mapping paper terms to current code

| Paper concept | Current Ring-3D mechanism | Relationship |
| --- | --- | --- |
| Gradient-norm CLR detector | Static seed-sampled `clr_mask.csv` with decay/spike proxy | Deliberate phase proxy; not training-derived |
| UDP chunks + bitmap recovery | Reliable RDMA QP and ASTRA completion callbacks | Not equivalent |
| $q$ loss burst | Seven finite background RDMA flows that create incast/PFC pressure | Congestion stressor; not packet loss |
| $D$ loss-window duration | No configured duration; background flows drain when the model permits | Not equivalent |
| $P_\mathrm{low}$/$P_\mathrm{high}$ residual loss | 0%/10% deterministic whole-payload substitution selection | Not equivalent |
| Fixed-$P_\mathrm{low}$ baseline | Zero-substitution lossless baseline | Different causal question |

The current system is correctly named a **phase-aware logical admission-
suppression under incast** experiment. It can test whether reducing selected
DP traffic relieves modeled congestion. It cannot reproduce DBLP's bitmap,
partial delivery, retransmission rounds, or accuracy behavior.

## Baseline selection is part of the claim

For the existing admission-suppression ablation, the zero-substitution baseline
is correct: it answers whether that new mechanism reduces congestion relative
to normal reliable payload transmission.

For a DBLP bounded-loss claim, use the paper-aligned baseline:

$$
P(t)=P_\mathrm{low}\quad\text{for all steps},
$$

and compare it with phase-aware $P(t)$. The comparison must share trace,
topology, $q$, $D$, CLR mask, policy-selection seed, and ns-3 RNG seed/run.
Only the phase-dependent tolerance may differ.

## Evidence ladder for unavailable hardware

1. **Mechanism validity:** every run has complete ranks/telemetry and observed
   queue/PFC or loss/recovery signals consistent with the configured stressor.
2. **Causal comparison:** matched baseline/policy pairs improve a primary
   native collective metric; no-incast/no-loss controls rule out a spurious
   policy-only benefit.
3. **Robustness:** sweep stressor severity, payload scale, source fan-in,
   phase mask, and seeds; retain null/invalid outcomes.
4. **Scale evidence:** run the largest feasible topologies and show how the
   effect behaves across completed sizes. A timeout is a resource observation,
   not a measurement at the timed-out scale.
5. **External validity boundary:** state precisely which simulator, topology,
   congestion-control model, trace abstraction, and transport semantics were
   used.

The current 16-rank 70B-class condition belongs to step 1 and can contribute
to step 2. It does not by itself establish performance on 256 accelerators or
production hardware. The unresolved issues that limit any next step are listed
in the [known-flaws register](ring-3d-known-flaws.md); no remedy is selected by
this document.

Read the [research context](ring-3d-research-context.md) for current backend
limits, the [glossary](../../experiments/ring_3d/GLOSSARY.md) for field names,
and the [validation protocol](../../experiments/ring_3d/VALIDATION_PROTOCOL.md)
for required evidence.
