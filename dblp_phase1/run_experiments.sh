#!/bin/bash
# Phase-1 DBLP vs baseline comparison on the ASTRA-sim analytical backend.
# Runs inside the astra-sim Docker container (invoke from the host via docker run).
set -e

cd "$(dirname "$0")"

ROOT=/app/astra-sim
BIN="${ROOT}/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware"
SYSTEM="${ROOT}/examples/system/native_collectives/Ring_4chunks.json"
REMOTE_MEM="${ROOT}/examples/remote_memory/analytical/no_memory_expansion.json"

ITERS=186                 # 10x downsample of the 1860-round real schedule
COMM_SIZE=21200000        # EfficientNetB0: 5.3M params x 4 B
SCHEDULE=schedule_effnet.json
PLOW=0.008                # paper Table I (EfficientNetB0)
PHIGH=0.408

network_for() {
  case "$1" in
    4)  echo "${ROOT}/examples/network/analytical/Ring_4npus.yml" ;;
    16) echo "${ROOT}/examples/network/analytical/Ring_16npus.yml" ;;
    64) echo "Ring_64npus.yml" ;;
    *)  echo "unsupported scale $1" >&2; exit 1 ;;
  esac
}

run_sim() {  # $1=trace_prefix $2=network -> prints wall time (cycles)
  "${BIN}" \
    --workload-configuration="$1" \
    --system-configuration="${SYSTEM}" \
    --remote-memory-configuration="${REMOTE_MEM}" \
    --network-configuration="$2" 2>&1 |
    grep -o 'Wall time: [0-9]*' | grep -o '[0-9]*' | sort -n | tail -1
}

echo "scale,mode,wall_time_cycles" > results.csv

for NPUS in 4 16 64; do
  NET=$(network_for "${NPUS}")
  PREFIX_RAW="traces/effnet_${NPUS}npus/raw/allreduce"
  PREFIX_BASE="traces/effnet_${NPUS}npus/baseline/allreduce"
  PREFIX_DBLP="traces/effnet_${NPUS}npus/dblp/allreduce"

  python3 gen_workload.py --npus "${NPUS}" --iters "${ITERS}" \
    --comm-size "${COMM_SIZE}" --out-prefix "${PREFIX_RAW}"

  python3 apply_dblp.py --in-prefix "${PREFIX_RAW}" --out-prefix "${PREFIX_BASE}" \
    --npus "${NPUS}" --iters "${ITERS}" --mode baseline --plow "${PLOW}"

  python3 apply_dblp.py --in-prefix "${PREFIX_RAW}" --out-prefix "${PREFIX_DBLP}" \
    --npus "${NPUS}" --iters "${ITERS}" --mode dblp \
    --plow "${PLOW}" --phigh "${PHIGH}" --schedule "${SCHEDULE}"

  for MODE in baseline dblp; do
    VAR="PREFIX_$(echo ${MODE} | tr '[:lower:]' '[:upper:]')"
    if [ "${MODE}" = baseline ]; then PREFIX="${PREFIX_BASE}"; else PREFIX="${PREFIX_DBLP}"; fi
    WALL=$(run_sim "${PREFIX}" "${NET}")
    echo "${NPUS},${MODE},${WALL}" | tee -a results.csv
  done
done

echo ""
echo "=== Speedup summary ==="
python3 - <<'EOF'
import csv

rows = {(r["scale"], r["mode"]): int(r["wall_time_cycles"]) for r in csv.DictReader(open("results.csv"))}
scales = sorted({s for s, _ in rows}, key=int)
print(f"{'NPUs':>5} {'baseline (cyc)':>16} {'DBLP (cyc)':>14} {'comm speedup':>13}")
for s in scales:
    b, d = rows[(s, "baseline")], rows[(s, "dblp")]
    print(f"{s:>5} {b:>16,} {d:>14,} {b / d:>12.3f}x")
EOF
