# 3D native Ring All-Reduce experiment

This directory produces a self-contained TP/PP/DP experiment for ASTRA-sim 2.0. Its rank mapping is TP-fastest:

$$
rank=((dp\_rank\cdot PP)+pp\_rank)\cdot TP+tp\_rank.
$$

The trace generator writes one ET trace per rank, explicit TP/PP/DP communicator groups, a physical Clos topology, native-Ring system configuration, and the ns-3 experiment policy. Workload modes make their trace shape explicit: the smoke profile uses two backward buckets with an overlap dependency, the structural mode expands transformer layers, and the Llama 3 70B-class mode models one representative DP gradient bucket per step.

## Profiles

- [profiles/smoke_8.json](profiles/smoke_8.json): $TP=2$, $PP=2$, $DP=2$, with an eight-host Clos topology.
- [profiles/no_incast_8.json](profiles/no_incast_8.json): an otherwise identical negative control with synthetic microbursts disabled.
- [profiles/llama3_70b_16.json](profiles/llama3_70b_16.json): a packet-accurate Llama 3 70B-class gradient-bucket stress workload with $TP=8$, $PP=1$, $DP=2$, 16 ranks, 4 KiB RoCE payloads, and a 400 Gb/s two-leaf Clos.

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

## Paired baseline comparison

Use [compare.py](compare.py) for a matched comparison. For every fixed seed it runs the lossless baseline first with the policy and microbursts still enabled but all suppression thresholds set to $0\%$, then runs the DBLP policy with the same generated workload, topology, seed, and microburst schedule. The default is five fixed seeds and it writes both individual run bundles, `comparison.json`, and `comparison_report.md`.

```sh
uv run --locked python experiments/ring_3d/compare.py \
  --profile experiments/ring_3d/profiles/llama3_70b_16.json \
  --output runs/ring_3d/llama3_70b_16_comparison \
  --require-congestion --clean
```

The comparison reports paired deltas for simulated makespan, native DP All-Reduce per-rank and all-rank-span P99 completion latency, all-QP P99 FCT as a transport diagnostic, and physical-byte reductions relative to foreground logical operations, DP All-Reduce traffic, and total offered traffic. It deliberately does not compare the conditional admitted-foreground QP population because provenance-controlled selections would change that population. Positive reductions favor DBLP, but a confidence interval spanning zero is not evidence of benefit. `--require-congestion` makes the command fail unless every baseline and policy run records background traffic, a nonzero queue peak, and at least one completed PFC pause interval.

The paired runner assigns every pair the same ns-3 random-stream seed and run number; each successive pair uses a different ns-3 run number. It records these values in `execution.json`. This makes paired baseline/policy comparisons reproducible while allowing independent ns-3 stochastic streams across seed runs.

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

The physical-budget calculation uses the configured 4 KiB RoCE payload, not a fictitious super-packet. A two-rank Ring transfers 2 GiB per DP group for a 1 GiB payload; the eight DP groups therefore carry 16 GiB per step and 48 GiB across the three steps. The representative TP collectives add 1.3125 GiB and the one-shot $7\times128$ MiB incast adds 0.875 GiB, for 50.1875 GiB and 13,156,352 data packets per baseline run before protocol overhead. Queue monitoring begins at 20 ms, the predicted step-2 bucket/incast overlap, and continues to simulation completion so the raw-signal gate observes the pressure interval without emitting idle telemetry before it. Five matched baseline/policy pairs therefore remain below the 160-minute CI execution guard while retaining packet-level PFC behavior.

This is a **70B-class bucket microbenchmark**, not an exact Llama, Megatron, DeepSpeed, or PyTorch replay and not a claim to simulate a complete 140 GB gradient synchronization per step. It deliberately isolates an industry-relevant 1 GiB communication spike. The CI gate requires observed queueing and PFC recovery before the paired results can be interpreted as congested-network evidence.

## Researcher-facing CI results

The native CI job publishes a Markdown report in its GitHub Actions job summary and uploads it as the standalone `ring-3d-research-report-<run-id>` artifact. It also retains the report in the `ring-3d-smoke-results-<run-id>` reproducibility bundle, alongside generated ET traces, topology, communicator groups, system and experiment policy JSON, raw ns-3 outputs, telemetry CSV files, and `summary.json`.

The report records the TP/PP/DP shape, workload and network parameters, configured and observed DP-only admission-suppression rates, completion coverage, logical-versus-physical byte accounting, native logical-collective latency, per-QP FCT diagnostics, simulated makespan distribution, and queue/PFC pause observations. It explicitly labels provenance control as the safe logical suppression model rather than literal packet loss.

Generate the same standalone Markdown record for any completed run with:

```sh
uv run --locked python experiments/ring_3d/report.py \
  --profile experiments/ring_3d/profiles/smoke_8.json \
  --run-dir runs/ring_3d/smoke_8 \
  --output runs/ring_3d/smoke_8/research_report.md
```

## Admission policy

The generated policy uses deterministic integer hashing of the seed, run ID, training step, workload node ID, message sequence, endpoints, and tag. Only payload requests explicitly labeled `dp`, `CollectivePayload`, and `All_Reduce` are eligible. The default thresholds are $0\%$, $10\%$, and $10\%$ for steps 1–3. A selected logical payload uses a reliable, protected 64-byte provenance-control flow; completion still resolves the original sender and receiver. `flow_events.csv` records both logical and physical bytes so results do not characterize the modeled operation as literal packet loss.

Priority group 0 remains reserved. Foreground vnet 0 maps to priority group 3, while provenance controls use priority group 1. Step 2 also triggers deterministic cross-rack RDMA microbursts on the same modeled host/RDMA path.

## Tests

```sh
uv run --locked python -m unittest discover \
  -s experiments/ring_3d/tests -v
```