#!/bin/bash
# Build the ns-3 backend on a DCS node from the job's checkout, using only
# the rootless toolchain that ci/dcs/setup.sh installed: compiler, protoc,
# boost, MPI, and zlib all come from the conda env, nothing from the system
# but glibc. Delegates to the same build/astra_ns3/build.sh CI uses, so the
# flags (release, no asserts, LTO, x86-64-v3) stay defined in one place.
set -euo pipefail

ROOT="${DCS_CI_ROOT:-$HOME/astra-ci}"
ENV="$ROOT/buildenv"

export PATH="$ENV/bin:$PATH"
export CC="$ENV/bin/x86_64-conda-linux-gnu-gcc"
export CXX="$ENV/bin/x86_64-conda-linux-gnu-g++"
export CMAKE_PREFIX_PATH="$ENV"
export LD_LIBRARY_PATH="$ENV/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CMAKE_C_COMPILER_LAUNCHER=ccache
export CMAKE_CXX_COMPILER_LAUNCHER=ccache
export CCACHE_DIR="$ROOT/ccache"
ccache --set-config=max_size=5G

exec bash "$(dirname "$0")/../../build/astra_ns3/build.sh" -c
