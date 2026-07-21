#!/usr/bin/env bash
set -euo pipefail

# Path
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)"

cd "${SCRIPT_DIR}"
unset VIRTUAL_ENV
exec uv run --project "${PROJECT_DIR}" --locked python "${SCRIPT_DIR}/gen_chakra_traces.py"
