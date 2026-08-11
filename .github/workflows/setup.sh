#!/usr/bin/env bash
set -euo pipefail

# Native toolchain only. The locked Python environment is a separate concern
# owned by utils/setup.sh locally and by .github/actions/python-env in CI;
# installing it from here would re-initialize every submodule that
# actions/checkout has already materialized.

### ================== System Setups ======================
## Install System Dependencies
sudo apt-get update
sudo apt-get install --yes --no-install-recommends \
    coreutils wget vim git ccache \
    gcc-11 g++-11 make cmake ninja-build \
    clang-format \
    libboost-dev libboost-program-options-dev \
    libprotobuf-dev protobuf-compiler libzstd-dev \
    openmpi-bin openmpi-doc libopenmpi-dev

### ======================================================
