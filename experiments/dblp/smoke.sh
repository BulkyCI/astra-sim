#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(dirname "$(realpath "$0")")
REPOSITORY_ROOT=$(realpath "$SCRIPT_DIR/../..")
OUTPUT="$REPOSITORY_ROOT/runs/dblp/injected_loss_retry_exhaustion_8"

uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/injected_loss_retry_exhaustion_8.json" \
  --output "$OUTPUT" --clean --simulation-timeout-seconds 60
