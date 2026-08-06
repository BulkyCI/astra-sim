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
- [profiles/llama3_70b_16.json](profiles/llama3_70b_16.json): a twenty-step, production-shaped Llama 3 70B-class event window with $TP=8$, $PP=1$, $DP=2$, 16 ranks, 4 KiB RoCE payloads, and a 400 Gb/s two-leaf Clos running a best-effort UEC FTD-trimming fabric (no PFC, one-BDP data queues, 1 ms bounded recovery). Its $7\times128$ MiB incast stressor fires at step 18, deep in the converged non-CLR tail of the schedule.
- [profiles/llama3_70b_32_direct.json](profiles/llama3_70b_32_direct.json): the same 70B event window widened to $DP=4$ (32 ranks, 4 leaves) with `dp_all_reduce_implementation: "direct"`, so every DP rank receives $DP-1$ concurrent gradient shards through the spine. Incast is organic to the workload here; the step-18 microburst remains as the calibrated exogenous stressor.
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

Generate only the immutable schedule with:

```sh
uv run --locked python experiments/ring_3d/generate_clr_schedule.py \
  --steps 1000 --seed 314159265 --output runs/ring_3d/clr_mask.csv \
  --decay-rate 4 --epoch-steps 100 --spike-stddev-steps 1
```

`generate.py` and `run.py` expose the same `--clr-decay-rate`, `--clr-epoch-steps`, `--clr-spike-stddev-steps`, and `--clr-spike-amplitude` controls. The seed override controls both the legacy deterministic per-flow admission decision and the static CLR-mask sample, so baseline and policy invocations in a pair ingest identical masks.

## Paired baseline comparison

Use [compare.py](compare.py) for a matched comparison. For every fixed seed it
runs a fixed-low baseline first with policy and microbursts still enabled, but
with both phases set to `p_low` (0.5% by default). It then runs the phase-aware
selection policy with the same generated workload, topology, seed, and static
CLR mask: `p_low` in CLR and `p_high` (10% by default) outside CLR. The
default is five fixed seeds and it writes both individual run bundles,
`comparison.json`, and `comparison_report.md`.

```sh
uv run --locked python experiments/ring_3d/compare.py \
  --profile experiments/ring_3d/profiles/llama3_70b_16.json \
  --output runs/ring_3d/llama3_70b_16_comparison \
  --require-congestion --clean
```

The comparison reports paired deltas for simulated makespan, native DP All-Reduce per-rank and all-rank-span P99 completion latency, all-QP P99 FCT as a transport diagnostic, and physical-byte reductions relative to foreground logical operations, DP All-Reduce traffic, and total offered traffic. It deliberately does not compare the conditional admitted-foreground QP population because provenance-controlled selections would change that population. Positive reductions favor the current policy, but a confidence interval spanning zero is not evidence of benefit. `--require-congestion` makes the command fail unless every baseline and policy run records background traffic, a nonzero queue peak, at least one completed PFC pause interval, and an eligible native collective/FCT/terminal ledger. After calibration demonstrates actual packet loss, add `--require-finite-buffer-data-drop`; it additionally requires at least one data-plane switch admission or egress-queue rejection and does not treat PFC alone as loss evidence.

The paired runner assigns every pair the same ns-3 random-stream seed and run number; each successive pair uses a different ns-3 run number. It records these values in `execution.json`. This makes paired baseline/policy comparisons reproducible while allowing independent ns-3 stochastic streams across seed runs. CI schedules the five pairs independently and then validates and aggregates their artifacts. A pair reserves $2\times150=300$ minutes for its two ns-3 processes inside a 330-minute command guard; the hosted-job limit is 360 minutes, leaving 30 minutes for setup, build, reports, and artifacts. The matrix permits five pairs concurrently. The separate historical Phase-1 reference pair runs concurrently; together with native integration and the two manually dispatched structural jobs, the workflow reaches at most nine active evaluation jobs, below the account-level limit of ten.

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

CI runs one fixed-seed matched baseline/policy pair for this expensive native
reference concurrently with the five Llama incast pairs. It does not require
the Llama queue/PFC congestion gate because its historical source trace had no
background microburst. It is a reproducibility and transport-scaling reference,
not a multi-seed primary policy result.

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
strict scheduling but no capacity-reservation claim; its observed delay and
drops remain part of `transport_events.csv`. Step 2 also triggers deterministic
cross-rack RDMA microbursts on the same modeled host/RDMA path.

## Tests

```sh
uv run --locked python -m unittest discover \
  -s experiments/ring_3d/tests -v
bash experiments/ring_3d/failure_liveness.sh
```