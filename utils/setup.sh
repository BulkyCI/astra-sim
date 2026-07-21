#!/usr/bin/env bash
set -euo pipefail

## ******************************************************************************
## This source code is licensed under the MIT license found in the
## LICENSE file in the root directory of this source tree.
##
## Copyright (c) 2024 Georgia Institute of Technology
## ******************************************************************************

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
    echo "[ASTRA-sim] uv is required; install it from https://docs.astral.sh/uv/." >&2
    exit 1
fi

# Do not accidentally target a caller's activated environment. The container
# supplies its own persistent location; local setups use the project .venv.
unset VIRTUAL_ENV
: "${UV_PROJECT_ENVIRONMENT:=${PROJECT_DIR}/.venv}"
export UV_PROJECT_ENVIRONMENT

echo "[ASTRA-sim] Initializing pinned submodules..."
git -C "${PROJECT_DIR}" submodule update --init --recursive

echo "[ASTRA-sim] Synchronizing the locked Python environment..."
exec uv sync --project "${PROJECT_DIR}" --locked