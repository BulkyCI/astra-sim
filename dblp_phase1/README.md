# DBLP × ASTRA-sim — Phase 1: first-order scaling estimate

Models DBLP's bounded-loss tolerance as **reduced effective communication
size**: an all-reduce that stops at (1 − p) of gradient chunks moves (1 − p)
of the bytes. Per-iteration p follows a CLR schedule extracted from a real
DBLP training run. No ASTRA-sim C++ changes.

## Pipeline

1. `extract_clr_schedule.py <server.log>` → `schedule_effnet.json`
   Parses a bound-tolerance-research server log; recovers which training
   rounds ran at P_low (CLR) vs P_high. Runs natively (no protobuf).
   Current schedule: exp4 (EfficientNetB0/CIFAR-10, A4500 testbed) —
   1860 rounds, CLR windows at 0–18, 1520–1528, 1650–1658 (2.0%).

2. `gen_workload.py` → baseline Chakra ET traces
   N ranks × M chained ALL_REDUCE `COMM_COLL_NODE`s (data-parallel gradient
   sync). Docker-only (protobuf must match generated `et_def_pb2.py`).

3. `apply_dblp.py` → scales each iteration's `comm_size` by (1 − p_iter)
   - `--mode baseline`: fixed p = P_low everywhere (the paper's MLT-style baseline)
   - `--mode dblp`: P_low inside CLR rounds, P_high outside (schedule-driven,
     index-scaled if trace has fewer iterations than the schedule)

4. `run_experiments.sh` → full matrix, `results.csv` + summary table.

## Run

```bash
cd ~/astra-sim
docker run --rm -v "$(pwd)":/app/astra-sim -w /app/astra-sim/dblp_phase1 \
  astra-sim:local ./run_experiments.sh
```

## Results (2026-07-15, EfficientNetB0 21.2 MB gradients, P_low=0.8%, P_high=40.8%, 186 iters, 50 GB/s ring)

| NPUs | Baseline (cycles) | DBLP (cycles) | Comm speedup |
|-----:|------------------:|--------------:|-------------:|
|    4 |       117,069,144 |    71,779,536 |       1.631× |
|   16 |       154,852,440 |    98,232,240 |       1.576× |
|   64 |       198,416,616 |   138,931,008 |       1.428× |

Sanity check: pure bandwidth-bound prediction is
(0.992·186)/(0.992·4 + 0.592·182) ≈ 1.652×; the 4-NPU result (1.631×)
matches, and the decline at 64 NPUs reflects the growing per-step latency
component of ring all-reduce (2(N−1) hops × 500 ns), which byte reduction
cannot shrink. **Finding: DBLP's byte-reduction benefit dilutes in
latency-bound regimes — worth highlighting when scaling out.**

## Caveats (Phase 1 model)

- Communication-only traces (no COMP nodes): speedups are comm-time, not
  end-to-end training time.
- No packet loss / retransmission dynamics; microburst behavior needs the
  ns-3 backend (Phase 3).
- Ring all-reduce here vs the paper's centralized parameter-server; loss
  semantics on a ring (dropped chunk corrupts downstream partial sums) is an
  open question for Phase 2.
