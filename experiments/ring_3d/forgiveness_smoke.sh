#!/usr/bin/env bash
# Native gate for the recovery domain. It is a sibling of smoke.sh rather than
# a second invocation inside it because its assertions are about forgiveness,
# not about the generator, and a failure here must name that.
set -euo pipefail

SCRIPT_DIR=$(dirname "$(realpath "$0")")
REPOSITORY_ROOT=$(realpath "$SCRIPT_DIR/../..")
OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_smoke_8"
ADMISSION_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_smoke_8_admission"
RERUN_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_smoke_8_rerun"
RACE_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_race_8"
DCQCN_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_dcqcn_8"

uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_smoke_8.json" \
  --output "$OUTPUT" --clean

# The same profile in the admission domain: the reference W' is measured
# against, with every other input identical.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_smoke_8.json" \
  --output "$ADMISSION_OUTPUT" --clean --domain admission

# The same recovery run again at the same seed. Forgiveness reads a ledger
# that grows as the run proceeds, so a reordering bug shows up here and
# nowhere else.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_smoke_8.json" \
  --output "$RERUN_OUTPUT" --clean

# S5: a retransmission timeout an order below the round trip, so resent data
# races the forgiveness that made it redundant.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_race_8.json" \
  --output "$RACE_OUTPUT" --clean

# The same profile under DCQCN, where a forgiven trim must still cost the
# sender the rate cut a pulled one would have.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_dcqcn_8.json" \
  --output "$DCQCN_OUTPUT" --clean

uv --project "$REPOSITORY_ROOT" run --locked python \
  "$SCRIPT_DIR/check_forgiveness.py" "$OUTPUT" "$ADMISSION_OUTPUT" \
  --rerun "$RERUN_OUTPUT" --race "$RACE_OUTPUT" \
  --congestion-neutral "$DCQCN_OUTPUT"
