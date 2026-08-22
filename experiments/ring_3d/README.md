# 3D native Ring All-Reduce experiment

This directory produces a self-contained TP/PP/DP experiment for ASTRA-sim 2.0. Its rank mapping is TP-fastest:

$$
rank=((dp\_rank\cdot PP)+pp\_rank)\cdot TP+tp\_rank.
$$

The trace generator writes one ET trace per rank, explicit TP/PP/DP communicator groups, a typed physical topology, native-Ring collective configuration, an ns-3 experiment policy, and a deterministic `clr_mask.csv`. The logical Ring collective and physical network are independent: a profile chooses either a two-stage Clos or a host-attached switch ring. The latter attaches every accelerator host to a dedicated switch and connects the switches in a bidirectional ring, preserving ns-3 switch queue and PFC observability. Workload modes make their trace shape explicit: the smoke profile uses two backward buckets with an overlap dependency, the structural mode expands transformer layers, and the Llama 3 70B-class mode models one representative DP gradient bucket per step.

Before changing semantics or interpreting a result, read the
[DBLP paper brief](../../docs/agents/ring-3d-paper-brief.md),
[ASTRA-sim pivot](../../docs/agents/ring-3d-astra-pivot.md), and
[glossary](GLOSSARY.md). The experiment is not a DBLP packet-loss
reproduction: the flagship Llama profile runs a best-effort UEC
packet-trimming fabric with bounded transport recovery, while the historical
Phase-1 reference remains a lossless logical-payload-substitution ablation.

## Profiles

- [profiles/smoke_8.json](profiles/smoke_8.json): $TP=2$, $PP=2$, $DP=2$, with an eight-host Clos topology.
- [profiles/no_incast_8.json](profiles/no_incast_8.json): an otherwise identical negative control with synthetic microbursts disabled.
- [profiles/retry_exhaustion_8.json](profiles/retry_exhaustion_8.json): a native regression fixture that deterministically exhausts a one-retry, data-only impairment budget; it must fail while retaining explicit terminal-QP telemetry and is never a primary-analysis result.
- [profiles/llama3_70b_16.json](profiles/llama3_70b_16.json): a twenty-step, production-shaped Llama 3 70B-class event window with $TP=8$, $PP=1$, $DP=2$, 16 ranks, 4 KiB RoCE payloads, and a 400 Gb/s two-leaf Clos running a best-effort UEC FTD-trimming fabric (no PFC, one-BDP data queues, 1 ms bounded recovery). Its $7\times128$ MiB incast stressor fires at step 18, deep in the converged non-CLR tail of the schedule. The retry budget bounds *consecutive silent retransmission timeouts* only — the one signal consistent with a dead path. Trim notifications are live congestion feedback and, like NACKs, never consume it; otherwise any sustained shared-buffer blockade (the burst holds leaf 1's dynamic ingress threshold down for its whole $\approx 18.8$ ms drain) would fail queue pairs at the sender's own send rate. At a 1 ms timeout, the budget of 1024 tolerates $\approx 1$ s of continuous silence, an order of magnitude beyond any engineered episode. Because budget-exempt signals cannot bound a recovery loop that never advances the cumulative acknowledgement, every recovery-enabled profile also carries a *forward-progress deadline* (`no_progress_timeout_ns`, default 5 simulated seconds): a queue pair whose `snd_una` has not moved for that long fails explicitly with reason `no_forward_progress` and its counters on record. The deadline is orders beyond any legitimate no-progress span (the engineered burst drains in $\approx 18.8$ ms) and exists to convert transport livelock — observed once as a lone queue pair cycling recovery signals on an otherwise idle fabric while simulated time raced past 9,800 s — into a fast, attributable failure instead of a silent wall-clock burn.
- [profiles/llama3_70b_32_direct.json](profiles/llama3_70b_32_direct.json): the same 70B event window widened to $DP=4$ (32 ranks, 4 leaves) on a **healthy 1:1 rail fabric** with `dp_all_reduce_implementation: "direct2"`. The first complete wave falsified the unwindowed form: with `direct` (fan-in 3), line-rate flow starts and ECMP collisions alone produced $\sim 1.2\times10^8$ trims per arm and pegged every queue at its cap *with the burst disabled*, so the episodic regime this arm exists to isolate was unobservable behind steady collapse. The two-flow window keeps the concurrent-direct structure while returning the baseline to the intended regime: the step-18 microburst incast at one receiver's downlink plus organic ECMP collisions.
- `profiles/llama3_70b_64_direct{1,2,4,""}.json`: the 70B window at $DP=8$ (64 ranks, 8 leaves) forming the fan-in sweep. `direct<k>` caps concurrent peer transfers at $k$, so the four windows sweep receiver fan-in $\{1,2,4,7\}$ on identical hardware, traces, seed, and schedule — transport concurrency is the only variable. [fan_in_sweep.py](fan_in_sweep.py) orders the completed pairs by fan-in and renders the congestion-knee and policy-relief tables.

Together the evaluation arms cover a **spectrum of fabric health** on the same rail-optimized 1:1 design, because that spectrum — not exotic provisioning — is how production AI clusters actually experience bad network conditions:

- **Healthy 1:1** (`llama3_70b_32_direct`, `spine_count: 8`, no failures): symmetric all-to-all is capacity-matched *in aggregate* (each sender's NIC divides across its concurrent flows), but the matched budget holds only once senders converge — measured run #110 showed the unwindowed fan-in-3 form never converging (every flow restarts at line rate per bucket, so onset overload recurs faster than DCQCN can pace it). The `direct2` window restores the designed behavior: congestion is purely episodic — the microburst incast at the destination downlink plus organic ECMP-collision hotspots. This is the well-run datacenter; it bounds how much benefit exists when the network is mostly clear.
- **Degraded 1:1** (`llama3_70b_64_direct*`, `spine_count: 8`, `failed_spine_count: 2`): two spines lost to failure or maintenance leave a 4:3 live ratio. The DP phase becomes network-bound — a 33% structural excess plus collision hotspots produce a heavy latency tail — while DCQCN can still hold the fabric at the congestion knee, the regime where shedding a bounded fraction of gradient traffic buys super-linear relief. The knee is bracketed by measurement: sustained 2× overload collapses go-back-N recovery under trimming outright, and a healthy fabric leaves little to relieve.
- **Designed 2:1** (`llama3_70b_16`): the hard oversubscribed condition, kept because its dp=2 phase is small enough to grind through. A full oversubscription sweep returns once the transport recovers trimmed packets selectively instead of rewinding the whole window.
- `profiles/llama3_70b_32_burst{0,2,4}.json`: the healthy-fabric window with the microburst source count swept; with the 7-source `llama3_70b_32_direct` arm these form the receiver-overload sweep, aggregated by `fan_in_sweep.py --swept-field microburst_source_count`. `burst0` disables the burst entirely and is the sweep's negative control.
- [profiles/llama3_70b_32_clrburst.json](profiles/llama3_70b_32_clrburst.json): the burst-timing contrast. Identical to the 7-source arm except the burst fires at step 1, a pinned critical step in every comparison profile's explicit schedule. The policy must shed almost nothing here; the contrast with the step-18 arm is the directional signature of phase-awareness itself.
- [profiles/llama3_70b_64_pp2.json](profiles/llama3_70b_64_pp2.json): the non-sheddable control on the degraded knee fabric. $PP=2$ puts pipeline activations on the same wire as the sheddable DP gradients; policy eligibility is `dp_all_reduce_only`, so PP flow completion must stay intact while DP is relieved.
- [profiles/llama3_70b_64_sr2x.json](profiles/llama3_70b_64_sr2x.json): the selective-retransmission canary on the designed-2:1 fabric that collapsed go-back-N. `transport_recovery.selective_repair` makes the sender retransmit exactly the reported trimmed or missing byte ranges while the receiver accepts out-of-order payload; timeout recovery stays go-back-N as the silent-loss fallback. If this pair completes, sustained oversubscription returns as a swept axis.
- [profiles/dblp_phase1_effnet_64dp.json](profiles/dblp_phase1_effnet_64dp.json): a 64-rank, communication-only native reference for the historical Phase-1 EfficientNet trace: 186 chained 21,200,000-byte DP All-Reduces on a 400 Gb/s physical switch ring, with no microburst or configured data loss.
- [profiles/model_100b_256_clos.json](profiles/model_100b_256_clos.json): a two-step 100B-parameter structural window on 256 accelerator cards and a 16-leaf × 16-spine Clos, with the shared step-two seven-source incast.
- [profiles/model_100b_256_ring.json](profiles/model_100b_256_ring.json): the identical 100B window and incast schedule on a 256-switch host-attached physical ring, retained to measure the physical Clos-versus-ring topology difference.

## Generate and run

Run from the repository root through uv only:

```sh
uv run --locked python experiments/ring_3d/generate.py \
  --profile experiments/ring_3d/profiles/smoke_8.json \
  --output runs/ring_3d/smoke_8 --clean
```

Build the ns-3 frontend, then execute the complete smoke run:

```sh
bash experiments/ring_3d/smoke.sh
```

The runner locates the ns-3 binary, preferring the `release` build the evaluations use and falling back to a development profile. Pass `--binary /path/to/AstraSimNetwork` to [run.py](run.py) to choose one explicitly. It emits `telemetry/flow_events.csv`, `telemetry/collective_events.csv`, `telemetry/rank_completion.csv`, and `summary.json`. The analyzer verifies exactly one completion row for every materialized rank, explicit completed/failed terminal QP outcomes, and a one-to-one telemetry-to-ns-3 FCT join by `(src, dst, source_port, start_time_ns)` — a source port names a live five-tuple and is reused once its queue pair terminates — including duration and physical bytes. A run that models no loss mechanism must record zero transport recovery, which is what a port reused while a straggler was still in flight would violate. Native `collective_events.csv` records exactly one issue-to-completion event per rank and logical collective; it supports per-rank completion and all-rank span $\max(end)-\min(start)$ metrics. The analyzer also reports per-QP FCT diagnostics, rank-completion distribution, queue peak locations, paired PFC pause/resume burden, configured data injection, and separately attributed switch admission/egress-queue drops. To analyze an already completed run:

```sh
uv run --locked python experiments/ring_3d/analyze.py \
  --telemetry-dir runs/ring_3d/smoke_8/telemetry
```

## Deterministic CLR schedule

Every materialized run contains a static `clr_mask.csv` with one row per one-based training step: `step_id,is_clr,probability`. It is generated once with the profile/override seed and passed to ns-3 as `--clr-mask-configuration`. The runtime reads the mask before scheduling work, then applies the strict CLR tolerance when `is_clr=1` and the relaxed stable-convergence tolerance when `is_clr=0`; it does not sample CLR state during simulation.

Critical learning regimes concentrate early in training and fade as the run converges, so the schedule decays over normalized training progress $\tau_t = t/(T-1)$ and scales every epoch-boundary spike by the envelope at its own center:

$$
P(\mathrm{CLR}\mid t)=\min\left(1, e^{-\lambda \tau_t}+
\sum_k A\,e^{-\lambda \tau_{kT_{\mathrm{epoch}}}}\exp\left(-\frac{(t-kT_{\mathrm{epoch}})^2}{2\sigma^2}\right)\right),
$$

then samples the whole Boolean mask with a fixed NumPy generator seed. Defaults are $\lambda=3.0$ over the full run, $T_{\mathrm{epoch}}=2$ steps, $\sigma=0.5$ steps, and $A=1.0$. Normalizing progress makes one parameter set describe the same curve at any step count; envelope-scaled spikes let an early boundary restore near-certain CLR while a late one barely registers, so the schedule trends monotonically from certain CLR at the first step toward $e^{-\lambda}$ at the last. `manifest.json` retains all parameters, the seed, and the CLR-step count.

A profile may instead retain an explicit, externally derived static mask through
`clr_schedule.kind: "explicit_critical_steps"`. This is an immutable phase
label input, not a detector or probability fit. The historical Phase-1 native
reference uses one-based steps 1, 2, 153, and 166: this is the exact 186-step
mapping produced by the old 1,860-round schedule's index-scaling rule.

Every 20-step comparison profile pins the explicit schedule
`critical_steps: [1, 2, 3, 20]`, derived from the training-dynamics
literature rather than from a sampled curve (the full evidence record with
verbatim citations lives in
[docs/agents/clr-schedule-evidence.md](../../docs/agents/clr-schedule-evidence.md)):

- **Steps 1–3 (launch window, 15% of the run).** Bare LR warmup in modern
  LLM runs is only 0.1–4% of steps (Llama 3, DeepSeek-V3, OLMo 2, GLM-130B),
  but fragility to gradient-information loss lasts longer: DGC holds back
  sparsification for ~2.4% of the run because early gradients are "diverse
  and aggressive", 1-bit Adam runs full-precision for 15–20% of steps, and
  the vision-era critical-period window spans 5–30%. Three of twenty steps
  sits in the center of those independent bands. The DBLP paper's own
  phase-tolerance findings are deliberately excluded from this derivation:
  DBLP is the system under test, so its claims are the hypothesis here,
  never the evidence.
- **Step 20 (annealing hedge, moderate evidence).** The end-of-run
  decay/annealing phase drives outsized quality gains at 7B–70B scale
  (MiniCPM's WSD decay-phase loss dive; OLMo 2's midtraining, +10.6 points
  at 7B) and a documented late-run gradient-norm blow-up gives a second
  independent reason for caution; Llama 3 found annealing gains negligible
  at 405B, so this step is a scale-dependent hedge, stated as such.
- **No mid-run critical steps, no epoch spikes.** LLM pretraining is ~1
  epoch (GPT-3, Chinchilla, LLaMA), so epoch boundaries — the sampled
  model's spike term — name an event that does not exist in the modeled
  workload. Mid-run loss spikes are real (PaLM, OLMo 2) but are
  state-dependent events at irregular positions that a static mask cannot
  encode, and no 2023–2026 source measures corruption damage as a function
  of run position.

Pinning also removes mask sampling from seed variance entirely: successive
seeds vary only the ns-3 random streams and the per-flow selection draws,
and the policy is guaranteed permissive across steps 4–19, where the
step-18 microburst fires. The sampled decay-and-spike mode remains for
exploration and for multi-epoch workloads where its spike term has a
referent.

Generate only the immutable schedule with:

```sh
uv run --locked python experiments/ring_3d/generate_clr_schedule.py \
  --steps 1000 --seed 314159265 --output runs/ring_3d/clr_mask.csv \
  --decay-rate 4 --epoch-steps 100 --spike-stddev-steps 1
```

`generate.py` and `run.py` expose the same `--clr-decay-rate`, `--clr-epoch-steps`, `--clr-spike-stddev-steps`, and `--clr-spike-amplitude` controls. The seed override controls both the legacy deterministic per-flow admission decision and the static CLR-mask sample, so baseline and policy invocations in a pair ingest identical masks.

## Matched three-arm comparison

Use [compare.py](compare.py) for a matched comparison. For every fixed seed it
runs three arms over the same generated workload, topology, seed, and static
CLR mask:

1. **Fixed-low baseline**: both phases at `p_low` (0.5% by default) — the
   conservative control that never risks a critical step.
2. **Fixed-high baseline**: both phases at `p_high` (10% by default). This arm
   deliberately sheds at the permissive rate *through critical steps* — the
   ceiling an unbounded policy would take — and is the only caller allowed to
   lift the strict-CLR `p_low` cap.
3. **Phase-aware policy**: `p_low` in CLR, `p_high` outside — the treatment.

The claim under test is captured headroom: the policy's relief over the
fixed-low control should approach the fixed-high ceiling while critical steps
stay at the strict bound, which the fixed-high arm abandons. The report
records the policy relief, the headroom, the experiment coordinates, and the
raw per-arm congestion evidence. The default is the sixteen pre-registered seeds - consecutive 8-digit chunks of pi taken in order, none screened - and it
writes the individual run bundles, `comparison.json`, and
`comparison_report.md`.

```sh
uv run --locked python experiments/ring_3d/compare.py \
  --profile experiments/ring_3d/profiles/llama3_70b_16.json \
  --output runs/ring_3d/llama3_70b_16_comparison \
  --require-congestion --clean
```

The comparison reports paired deltas for simulated makespan, native DP All-Reduce per-rank and all-rank-span P99 completion latency, all-QP P99 FCT as a transport diagnostic, and physical-byte reductions relative to foreground logical operations, DP All-Reduce traffic, and total offered traffic. It deliberately does not compare the conditional admitted-foreground QP population because provenance-controlled selections would change that population. Positive reductions favor the current policy, but a confidence interval spanning zero is not evidence of benefit. `--require-congestion` makes the command fail unless every baseline and policy run records background traffic, a nonzero queue peak, at least one completed PFC pause interval, and an eligible native collective/FCT/terminal ledger. After calibration demonstrates actual packet loss, add `--require-finite-buffer-data-drop`; it additionally requires at least one data-plane switch admission or egress-queue rejection and does not treat PFC alone as loss evidence.

The paired runner assigns every pair the same ns-3 random-stream seed and run number; each successive pair uses a different ns-3 run number. It records these values in `execution.json`. This makes paired baseline/policy comparisons reproducible while allowing independent ns-3 stochastic streams across seed runs. CI schedules the sixteen comparisons independently and then validates and aggregates their artifacts. Each comparison runs three matched arms sequentially, every arm capped at 240 minutes, inside a 330-minute command guard; the hosted-job limit is 360 minutes, leaving 30 minutes for setup, build, reports, and artifacts. The guard bounds the arms' sum, so the budget assumes at most one arm runs near its cap — a livelocked arm instead fails within seconds through the transport forward-progress deadline. The separate historical Phase-1 reference runs concurrently as one structural arm; together with native integration and the two manually dispatched structural jobs, the workflow stays below the account-level concurrency limit of ten.

## Historical Phase-1 64-rank native reference

`dblp_phase1_effnet_64dp.json` makes the old analytical trace shape auditable
in the packet-level path. It uses $TP=PP=1$, $DP=64$, and emits exactly one
21,200,000-byte DP All-Reduce per rank for each of 186 sequential steps; no
compute, TP, PP, microburst, or configured physical data-loss event is emitted.
The 50 GB/s analytical Ring is represented as a 400 Gb/s host-attached,
bidirectional physical switch ring, so packet queues and RDMA transport are
modeled rather than analytical link timing alone. The payload, round count, and
phase-mask mapping come from the historical `af8d809f9f4f0a7b09ac043b86202be54f59a95d`
Phase-1 configuration.

Its 0.8% low and 40.8% high values deliberately match the old Phase-1 command
line, but remain **logical whole-payload selection probabilities** here. They
are not DBLP residual-loss bounds, packet-loss rate $q$, or evidence of
accuracy preservation. The profile's static CLR labels preserve only the old
phase-mask mapping. It does not recreate the original server's gradient-norm
detector, packet-loss burst, bitmap recovery, or Stop/Probe control protocol.

CI runs one fixed-seed structural run for this expensive native reference
concurrently with the sixteen Llama incast comparisons. Its scientific role —
zero-recovery transport verification at 5.999M queue pairs and reproduction of
the historical trace shape — needs only a single arm, and its measured
2.75-hour arm makes a three-arm matched comparison arithmetically impossible
inside the six-hour hosted-job ceiling. It does not require the Llama
queue/PFC congestion gate because its historical source trace had no
background microburst. It is a reproducibility and transport-scaling
reference, not a policy result.

## Empirical-validation protocol

[VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md) pre-registers the primary logical-collective estimands, raw-signal gates, negative and congestion controls, payload/incast/policy-rate grid, causal-load criterion, and decision rules. The 70B-class CI condition uses a 128 MiB × 7 background incast and fails closed unless raw queue/PFC gates pass. It cannot by itself establish a DBLP benefit: the retained paired metrics and causal-load criterion remain required.

## Llama 3 70B-class production-shaped event window

Generate the 16-rank packet-level workload and its auditable `model_trace.json` ledger with:

```sh
uv run --locked python experiments/ring_3d/generate.py \
  --profile experiments/ring_3d/profiles/llama3_70b_16.json \
  --output runs/ring_3d/llama3_70b_16 --clean
```

The reference has $70$ billion BF16/FP16 parameters, or $140$ GB of gradients. With $TP=8$ and $PP=1$, a rank owns a 17.5 GB gradient shard. A local DP bucket is exactly $17{,}500{,}000{,}000/256=68{,}359{,}375$ bytes. The profile models one such bucket per optimizer step, while retaining the full bucket count in its ledger.

The trace samples one transformer-layer collective pattern across eight gradient-accumulation microbatches: each sampled step emits 16 TP All-Reduces of $4096\times8192\times2=67{,}108{,}864$ bytes per rank, then one local DP bucket. It is therefore a bounded production-shaped event window, not a literal replay of all 80 layers and all 256 gradient buckets. Across 16 ranks and two steps, those input payloads total 32 GiB of TP traffic plus about 2.04 GiB of sampled DP traffic; the retained $7\times128$ MiB incast adds 0.875 GiB at step two. At the configured 4 KiB payload size this is approximately 9.15 million input payload packets before the native collective algorithm expands them into transport flows. Queue monitoring starts at simulated time zero and samples every 10 μs, preserving queue/PFC evidence without a monitor event per packet-scale interval.

The incast remains enabled deliberately: it is the paired study's exogenous, reproducible congestion stressor. `compare.py --require-congestion` rejects a run unless that traffic produces background-flow evidence, a nonzero queue peak, and a completed PFC pause interval. The no-incast profile remains the separate negative control. This condition is not an exact Llama, Megatron, DeepSpeed, or PyTorch replay; it does not establish a 100-iteration warmup or a complete 140 GB gradient synchronization. A full framework trace is required for those claims.

## 100B 256-card structural topology studies

The two 100B profiles retain the supplied large-model shape: $TP=8$, $PP=4$, and $DP=8$, for 256 accelerator cards; 80 transformer layers; eight pipeline microbatches; and two TP All-Reduces per layer. The reference model has 100 billion FP16 parameters, so a data-parallel replica contains 200 GB of gradients. Each rank owns a 6.25 GB decimal TP×PP gradient shard and emits 96 local DP buckets per step. Exact byte preservation gives 64 buckets of 65,104,167 bytes and 32 buckets of 65,104,166 bytes, totaling exactly 6.25 GB per rank per step. The activation-derived TP All-Reduce and PP message payloads are both $1\times2048\times12288\times2=50{,}331{,}648$ bytes. Both profiles use 400 Gb/s links, 4 KiB RDMA payloads, two modeled steps, and the supplied seven-source 50 MB step-two incast.

The Clos layout contains 256 hosts, 16 leaf switches, 16 spine switches, and 512 bidirectional physical links. The physical-ring layout contains the same 256 hosts plus 256 attached switches and 512 bidirectional physical links: 256 host-to-switch links and 256 switch-ring links. It is not a direct host-only ring, because the bundled ns-3 backend models queueing and PFC at switches. In both cases the ASTRA-sim collective implementation remains Ring, making the reports explicit about the distinction between collective algorithm and physical fabric.

The two structural studies run only when a manual CI dispatch selects **Run 100B structural topology studies**. Routine pushes and pull requests run the native smoke/regression job and Llama 3 70B paired study without competing with these costly workloads. Each manually requested 100B job reserves a 270-minute per-simulator cap inside a 320-minute command guard. The remaining 40 minutes of GitHub Actions' six-hour ceiling cover checkout, dependency setup, native build, report generation, and artifact upload. Reducing the preceding three-step structural run to two modeled steps, together with the doubled link rate, reduces packet work while the 96 buckets retain realistic DP event granularity. They are single policy runs, not baseline/policy comparisons: their Markdown reports present topology geometry, model-trace ledger, execution budget, logical collective metrics, transport diagnostics, traffic accounting, and congestion telemetry without claiming a causal DBLP benefit.

## Researcher-facing CI results

The native CI job and each manually dispatched structural-topology job publish a Markdown report in their GitHub Actions job summary and retain it in their reproducibility artifact. Every bundle includes the exact source `profile.json`, ET traces, topology, topology manifest, communicator groups, system and experiment policy JSON, execution controls, raw ns-3 outputs, telemetry CSV files, and `summary.json` when the simulator completes.

The report records the TP/PP/DP shape, materialized model ledger, physical network geometry, execution controls, configured and observed DP-only admission-suppression rates, completion coverage, logical-versus-physical byte accounting, native logical-collective latency, per-QP FCT diagnostics, simulated makespan distribution, and queue/PFC pause observations. It explicitly labels provenance control as the safe logical suppression model rather than literal packet loss.

Generate the same standalone Markdown record for any completed run with:

```sh
uv run --locked python experiments/ring_3d/report.py \
  --profile experiments/ring_3d/profiles/smoke_8.json \
  --run-dir runs/ring_3d/smoke_8 \
  --output runs/ring_3d/smoke_8/research_report.md
```

## Admission policy and liveness

Only payload requests explicitly labeled `dp`, `CollectivePayload`, and
`All_Reduce` are eligible. The static CLR mask selects `p_low` (0.5% by
default) during critical-learning steps and `p_high` (10% by default) during
stable steps. Within a selected probability, deterministic integer hashing of
the seed, run ID, training step, workload node ID, message sequence, endpoints,
and tag selects the logical payloads. A selected payload uses a reliable
64-byte provenance-replacement QP on logical priority group 1; it is ordinary
UDP data on the wire, not an ACK/NACK/PFC/CNP control packet. Completion still
resolves the original sender and receiver. `flow_events.csv` records both
logical and physical bytes so results do not characterize the modeled operation
as literal packet loss. These are selection-proxy knobs, not DBLP residual-loss
$P$ semantics. See [POLICY_IMPLEMENTATION.md](../../astra-sim/network_frontend/ns3/POLICY_IMPLEMENTATION.md)
for the runtime contract.

The ns-3 frontend emits an info-level liveness checkpoint every 10 ms of simulated time while work remains. Each message reports simulated time, completed QPs, active QPs, completed ranks, and pending background flows. Simulated time is ns-3's virtual clock, not wall-clock duration: checkpoints never impose a virtual-time cutoff. The configured `--simulation-timeout-seconds` setting and CI's outer `timeout` command remain the only wall-clock guards for long-running experiments.

Priority group 0 remains reserved for wire control at the switch. Foreground
vnet 0 maps to priority group 3, while provenance-replacement QPs use priority
group 1. Generated network configurations enable strict ACK/NACK priority
independently of whether configured data impairment is active. Queue 0 has
strict scheduling but no capacity-reservation claim; its observed drops are
totaled in `transport_summary.csv`, with per-packet timing retained in the
raw `transport_events.csv.zst.NNN` segments (`cat`+`zstd -d` reconstructs the single stream). Step 2 also triggers deterministic
cross-rack RDMA microbursts on the same modeled host/RDMA path.

## Tests

```sh
uv run --locked python -m unittest discover \
  -s experiments/ring_3d/tests -v
bash experiments/ring_3d/failure_liveness.sh
```