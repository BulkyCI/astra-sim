#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJ_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

### ================== System Setups ======================
## Install System Dependencies
sudo apt-get update
sudo apt-get install --yes --no-install-recommends \
    coreutils wget vim git ccache \
    gcc-11 g++-11 make cmake ninja-build \
    clang-format \
    libboost-dev libboost-program-options-dev \
    libprotobuf-dev protobuf-compiler \
    openmpi-bin openmpi-doc libopenmpi-dev

"${PROJ_DIR}/utils/setup.sh"

### ======================================================
