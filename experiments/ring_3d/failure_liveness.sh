#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(dirname "$(realpath "$0")")
REPOSITORY_ROOT=$(realpath "$SCRIPT_DIR/../..")
OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/retry_exhaustion_8"

if uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/retry_exhaustion_8.json" \
  --output "$OUTPUT" --clean --simulation-timeout-seconds 60; then
  echo "retry-exhaustion profile unexpectedly completed" >&2
  exit 1
fi

uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/analyze.py" \
  --telemetry-dir "$OUTPUT/telemetry" \
  --ns3-dir "$OUTPUT/ns3" \
  --output "$OUTPUT/summary.json"

uv --project "$REPOSITORY_ROOT" run --locked python - "$OUTPUT" <<'PY'
import csv
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
with (run_dir / "telemetry" / "flow_events.csv").open(newline="", encoding="utf-8") as handle:
    flows = list(csv.DictReader(handle))

if not flows:
    raise SystemExit("retry-exhaustion run emitted no terminal flow telemetry")
if any(flow.get("terminal_outcome") not in {"completed", "failed"} for flow in flows):
    raise SystemExit("retry-exhaustion run retained a nonterminal flow telemetry row")
if not any(
    flow.get("terminal_outcome") == "failed"
    and flow.get("failure_reason") == "retry_exhausted"
    for flow in flows
):
    raise SystemExit("retry-exhaustion run did not retain a retry_exhausted QP")

summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
if summary.get("primary_analysis_eligibility", {}).get("status") != "ineligible":
    raise SystemExit("retry-exhaustion run was incorrectly eligible for primary analysis")
PY
