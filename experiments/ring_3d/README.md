# 3D native Ring All-Reduce experiment

This directory produces a self-contained TP/PP/DP experiment for ASTRA-sim 2.0. Its rank mapping is TP-fastest:

$$
rank=((dp\_rank\cdot PP)+pp\_rank)\cdot TP+tp\_rank.
$$

The trace generator writes one ET trace per rank, explicit TP/PP/DP communicator groups, a typed physical topology, native-Ring collective configuration, an ns-3 experiment policy, and a deterministic `clr_mask.csv`. The logical Ring collective and physical network are independent: a profile chooses either a two-stage Clos or a host-attached switch ring. The latter attaches every accelerator host to a dedicated switch and connects the switches in a bidirectional ring, preserving ns-3 switch queue and PFC observability. Workload modes make their trace shape explicit: the smoke profile uses two backward buckets with an overlap dependency, the structural mode expands transformer layers, and the Llama 3 70B-class mode models one representative DP gradient bucket per step.

## Profiles

- [profiles/smoke_8.json](profiles/smoke_8.json): $TP=2$, $PP=2$, $DP=2$, with an eight-host Clos topology.
- [profiles/no_incast_8.json](profiles/no_incast_8.json): an otherwise identical negative control with synthetic microbursts disabled.
- [profiles/llama3_70b_16.json](profiles/llama3_70b_16.json): a packet-accurate Llama 3 70B-class gradient-bucket stress workload with $TP=8$, $PP=1$, $DP=2$, 16 ranks, 4 KiB RoCE payloads, and a 400 Gb/s two-leaf Clos.
- [profiles/model_100b_256_clos.json](profiles/model_100b_256_clos.json): a 100B-parameter structural workload on 256 accelerator cards and a 16-leaf × 16-spine Clos.
- [profiles/model_100b_256_ring.json](profiles/model_100b_256_ring.json): the same 100B structural workload and communication schedule on a 256-switch host-attached physical ring.

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

The runner locates the default ns-3 binary. Pass `--binary /path/to/AstraSimNetwork` to [run.py](run.py) when using another build profile. It emits `telemetry/flow_events.csv`, `telemetry/collective_events.csv`, `telemetry/rank_completion.csv`, and `summary.json`. The analyzer verifies a one-to-one telemetry-to-ns-3 FCT join by `(src, dst, source_port)`, including start time, duration, and physical bytes. Native `collective_events.csv` records exactly one issue-to-completion event per rank and logical collective; it supports per-rank completion and all-rank span $\max(end)-\min(start)$ metrics. The analyzer also reports per-QP FCT diagnostics, rank-completion distribution, queue peak locations, and paired PFC pause/resume burden. To analyze an already completed run:

```sh
uv run --locked python experiments/ring_3d/analyze.py \
  --telemetry-dir runs/ring_3d/smoke_8/telemetry
```

## Deterministic CLR schedule

Every materialized run contains a static `clr_mask.csv` with one row per one-based training step: `step_id,is_clr,probability`. It is generated once with the profile/override seed and passed to ns-3 as `--clr-mask-configuration`. The runtime reads the mask before scheduling work, then applies the strict CLR tolerance when `is_clr=1` and the relaxed stable-convergence tolerance when `is_clr=0`; it does not sample CLR state during simulation.

The vectorized schedule computes

$$
P(\mathrm{CLR}\mid t)=\min\left(1, e^{-\lambda t}+
\sum_k A\exp\left(-\frac{(t-kT_{\mathrm{epoch}})^2}{2\sigma^2}\right)\right),
$$

then samples the whole Boolean mask with a fixed NumPy generator seed. Defaults are $\lambda=1.5$, $T_{\mathrm{epoch}}=2$ steps, $\sigma=0.5$ steps, and $A=1.0$. The first zero-indexed step is therefore always a CLR; narrow epoch-boundary spikes restore CLR state at configured shifts. `manifest.json` retains all parameters, the seed, and the CLR-step count.

Generate only the immutable schedule with:

```sh
uv run --locked python experiments/ring_3d/generate_clr_schedule.py \
  --steps 1000 --seed 314159265 --output runs/ring_3d/clr_mask.csv \
  --decay-rate 0.01 --epoch-steps 100 --spike-stddev-steps 1
```

`generate.py` and `run.py` expose the same `--clr-decay-rate`, `--clr-epoch-steps`, `--clr-spike-stddev-steps`, and `--clr-spike-amplitude` controls. The seed override controls both the legacy deterministic per-flow admission decision and the static CLR-mask sample, so baseline and policy invocations in a pair ingest identical masks.

## Paired baseline comparison

Use [compare.py](compare.py) for a matched comparison. For every fixed seed it runs the lossless baseline first with the policy and microbursts still enabled but both CLR/stable suppression tolerances set to $0\%$, then runs the DBLP policy with the same generated workload, topology, seed, and static CLR mask. The default is five fixed seeds and it writes both individual run bundles, `comparison.json`, and `comparison_report.md`.

```sh
uv run --locked python experiments/ring_3d/compare.py \
  --profile experiments/ring_3d/profiles/llama3_70b_16.json \
  --output runs/ring_3d/llama3_70b_16_comparison \
  --require-congestion --clean
```

The comparison reports paired deltas for simulated makespan, native DP All-Reduce per-rank and all-rank-span P99 completion latency, all-QP P99 FCT as a transport diagnostic, and physical-byte reductions relative to foreground logical operations, DP All-Reduce traffic, and total offered traffic. It deliberately does not compare the conditional admitted-foreground QP population because provenance-controlled selections would change that population. Positive reductions favor DBLP, but a confidence interval spanning zero is not evidence of benefit. `--require-congestion` makes the command fail unless every baseline and policy run records background traffic, a nonzero queue peak, and at least one completed PFC pause interval.

The paired runner assigns every pair the same ns-3 random-stream seed and run number; each successive pair uses a different ns-3 run number. It records these values in `execution.json`. This makes paired baseline/policy comparisons reproducible while allowing independent ns-3 stochastic streams across seed runs. CI schedules the five pairs independently and then validates and aggregates their artifacts. Each pair gets GitHub Actions' six-hour job limit, a 330-minute pair guard, and a 150-minute cap for each of its two ns-3 processes, leaving time for build, report, and artifact publication without serializing five pairs into one job.

## Empirical-validation protocol

[VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md) pre-registers the primary logical-collective estimands, raw-signal gates, negative and congestion controls, payload/incast/policy-rate grid, causal-load criterion, and decision rules. The 70B-class CI condition uses a 128 MiB × 7 background incast and fails closed unless raw queue/PFC gates pass. It cannot by itself establish a DBLP benefit: the retained paired metrics and causal-load criterion remain required.

## Llama 3 70B-class packet-level bucket workload

Generate the 16-rank packet-level workload and its auditable `model_trace.json` ledger with:

```sh
uv run --locked python experiments/ring_3d/generate.py \
  --profile experiments/ring_3d/profiles/llama3_70b_16.json \
  --output runs/ring_3d/llama3_70b_16 --clean
```

The model reference is $70$ billion FP16 parameters, or $140$ GB of gradients. Its 140 nominal model-gradient buckets are 1 GB each. With $TP=8$ and $PP=1$, a rank owns a 17.5 GB gradient shard. The emitted trace intentionally models **one** 1 GiB local DP All-Reduce bucket per step, rather than falsely replaying all 140 global buckets. A 1 GiB simulated bucket is 7.37% larger than the nominal decimal 1 GB bucket, making the packet load conservative.

The physical-budget calculation uses the configured 4 KiB RoCE payload, not a fictitious super-packet. A two-rank Ring transfers 2 GiB per DP group for a 1 GiB payload; the eight DP groups therefore carry 16 GiB per step and 48 GiB across the three steps. The representative TP collectives add 1.3125 GiB and the one-shot $7\times128$ MiB incast adds 0.875 GiB, for 50.1875 GiB and 13,156,352 data packets per baseline run before protocol overhead. Queue monitoring begins at 20 ms, the predicted step-2 bucket/incast overlap, and continues to simulation completion so the raw-signal gate observes the pressure interval without emitting idle telemetry before it. Five matched baseline/policy pairs run in separate CI jobs; each pair has a 330-minute guard, and each simulator gets 150 minutes within GitHub Actions' six-hour job limit, while retaining packet-level PFC behavior.

This is a **70B-class bucket microbenchmark**, not an exact Llama, Megatron, DeepSpeed, or PyTorch replay and not a claim to simulate a complete 140 GB gradient synchronization per step. It deliberately isolates an industry-relevant 1 GiB communication spike. The CI gate requires observed queueing and PFC recovery before the paired results can be interpreted as congested-network evidence.

## 100B 256-card structural topology studies

The two 100B profiles retain the supplied large-model shape: $TP=8$, $PP=4$, and $DP=8$, for 256 accelerator cards; 80 transformer layers; eight pipeline microbatches; and two TP All-Reduces per layer. The reference model has 100 billion FP16 parameters, so a data-parallel replica contains 200 GB of gradients. Each rank owns a 6.25 GB decimal TP×PP gradient shard and emits 20 exact 312.5 MB decimal DP buckets per step. The activation-derived TP All-Reduce and PP message payloads are both $1\times2048\times12288\times2=50{,}331{,}648$ bytes. Both profiles use 4 KiB RDMA payloads and retain the supplied seven-source 50 MB step-2 incast.

The Clos layout contains 256 hosts, 16 leaf switches, 16 spine switches, and 512 bidirectional physical links. The physical-ring layout contains the same 256 hosts plus 256 attached switches and 512 bidirectional physical links: 256 host-to-switch links and 256 switch-ring links. It is not a direct host-only ring, because the bundled ns-3 backend models queueing and PFC at switches. In both cases the ASTRA-sim collective implementation remains Ring, making the reports explicit about the distinction between collective algorithm and physical fabric.

After `python-quality` passes, CI starts these two structural studies concurrently with the native smoke/regression job and the Llama 3 70B paired study. Each 100B job has GitHub Actions' six-hour ceiling, a 330-minute command guard, and a 300-minute per-simulator cap. They are single policy runs, not baseline/policy comparisons: their Markdown reports present topology geometry, model-trace ledger, execution budget, logical collective metrics, transport diagnostics, traffic accounting, and congestion telemetry without claiming a causal DBLP benefit.

## Researcher-facing CI results

The native CI job and each structural-topology job publish a Markdown report in their GitHub Actions job summary and retain it in their reproducibility artifact. Every bundle includes the exact source `profile.json`, ET traces, topology, topology manifest, communicator groups, system and experiment policy JSON, execution controls, raw ns-3 outputs, telemetry CSV files, and `summary.json` when the simulator completes.

The report records the TP/PP/DP shape, materialized model ledger, physical network geometry, execution controls, configured and observed DP-only admission-suppression rates, completion coverage, logical-versus-physical byte accounting, native logical-collective latency, per-QP FCT diagnostics, simulated makespan distribution, and queue/PFC pause observations. It explicitly labels provenance control as the safe logical suppression model rather than literal packet loss.

Generate the same standalone Markdown record for any completed run with:

```sh
uv run --locked python experiments/ring_3d/report.py \
  --profile experiments/ring_3d/profiles/smoke_8.json \
  --run-dir runs/ring_3d/smoke_8 \
  --output runs/ring_3d/smoke_8/research_report.md
```

## Admission policy and liveness

Only payload requests explicitly labeled `dp`, `CollectivePayload`, and `All_Reduce` are eligible. The static CLR mask selects a strict $0\%$ suppression tolerance during critical learning steps and a relaxed $10\%$ tolerance during stable steps. Within a selected tolerance, deterministic integer hashing of the seed, run ID, training step, workload node ID, message sequence, endpoints, and tag selects the logical payloads. A selected payload uses a reliable, protected 64-byte provenance-control flow; completion still resolves the original sender and receiver. `flow_events.csv` records both logical and physical bytes so results do not characterize the modeled operation as literal packet loss.

The ns-3 frontend emits an info-level liveness checkpoint every 10 ms of simulated time while work remains. Each message reports simulated time, completed QPs, active QPs, completed ranks, and pending background flows. The watchdog is bounded to 10,000 checkpoints (100 s simulated time); reaching that bound stops the simulation and returns a failed run instead of retaining a misleading partial result.

Priority group 0 remains reserved. Foreground vnet 0 maps to priority group 3, while provenance controls use priority group 1. Step 2 also triggers deterministic cross-rack RDMA microbursts on the same modeled host/RDMA path.

## Tests

```sh
uv run --locked python -m unittest discover \
  -s experiments/ring_3d/tests -v
```