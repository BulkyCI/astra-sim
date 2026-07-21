#!/usr/bin/env bash
set -euo pipefail

## ******************************************************************************
## This source code is licensed under the MIT license found in the
## LICENSE file in the root directory of this source tree.
##
## Copyright (c) 2024 Georgia Institute of Technology
## ******************************************************************************

# This legacy entry point intentionally delegates to the single supported
# environment workflow. Chakra and its trace-link dependency are declared in
# pyproject.toml and resolved from uv.lock.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "[ASTRA-sim] install_chakra.sh is maintained for compatibility."
exec "${SCRIPT_DIR}/setup.sh"
