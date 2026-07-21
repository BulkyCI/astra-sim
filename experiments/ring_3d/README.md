# 3D native Ring All-Reduce experiment

This directory produces a self-contained TP/PP/DP experiment for ASTRA-sim 2.0. Its rank mapping is TP-fastest:

$$
rank=((dp\_rank\cdot PP)+pp\_rank)\cdot TP+tp\_rank.
$$

The trace generator writes one ET trace per rank, explicit TP/PP/DP communicator groups, a physical Clos topology, native-Ring system configuration, and the ns-3 experiment policy. Each of the three steps contains TP All-Reduce, pipeline send/receive edges, two backward buckets, and two DP All-Reduces. The first DP reduction can overlap the second backward bucket; the optimizer waits for both DP reductions.

## Profiles

- [profiles/smoke_8.json](profiles/smoke_8.json): $TP=2$, $PP=2$, $DP=2$, with an eight-host Clos topology.
- [profiles/canonical_256.json](profiles/canonical_256.json): $TP=8$, $PP=4$, $DP=8$, with a 256-host, 16-leaf, 16-spine Clos topology.

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

The runner locates the default ns-3 binary. Pass `--binary /path/to/AstraSimNetwork` to [run.py](run.py) when using another build profile. It emits `telemetry/flow_events.csv`, `telemetry/rank_completion.csv`, and `summary.json`. To analyze an already completed run:

```sh
uv run --locked python experiments/ring_3d/analyze.py \
  --telemetry-dir runs/ring_3d/smoke_8/telemetry
```

## Admission policy

The generated policy uses deterministic integer hashing of the seed, run ID, training step, workload node ID, message sequence, endpoints, and tag. Only payload requests explicitly labeled `dp`, `CollectivePayload`, and `All_Reduce` are eligible. The default thresholds are $0\%$, $10\%$, and $10\%$ for steps 1–3. A selected logical payload uses a reliable, protected 64-byte provenance-control flow; completion still resolves the original sender and receiver. `flow_events.csv` records both logical and physical bytes so results do not characterize the modeled operation as literal packet loss.

Priority group 0 remains reserved. Foreground vnet 0 maps to priority group 3, while provenance controls use priority group 1. Step 2 also triggers deterministic cross-rack RDMA microbursts on the same modeled host/RDMA path.

## Tests

```sh
uv run --locked python -m unittest discover \
  -s experiments/ring_3d/tests -v
```