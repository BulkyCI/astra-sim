#!/bin/bash
# Build the ns-3 backend on a DCS node from the job's checkout, using only
# a rootless toolchain created fresh for this one job: compiler, protoc,
# boost, MPI, zlib, and zstd all come from a conda env on the job's own
# scratch, nothing from the system but glibc. The home directory is
# strictly control plane - jobs download their own tools (the network is
# unmetered), so there is no shared mutable state and no locks, and the
# job's cleanup trap reaps everything. Delegates to the same
# build/astra_ns3/build.sh CI uses, so the flags (release, no asserts,
# LTO, march) stay defined in one place.
set -euo pipefail

MAMBA_VERSION=2.3.2
repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
work="${RUNNER_TEMP:?}"
ENV="$work/buildenv"

# A fresh env per job from the declared package list: adding a package to
# ci/dcs/buildenv-packages.txt deploys with the push that declares it.
curl -fsSL "https://micro.mamba.pm/api/micromamba/linux-64/${MAMBA_VERSION}" \
    | tar -xj -C "$work" bin/micromamba
export MAMBA_ROOT_PREFIX="$work/mamba-root"
grep -vE '^[[:space:]]*(#|$)' "$repo_root/ci/dcs/buildenv-packages.txt" \
    | xargs "$work/bin/micromamba" create -y -q -p "$ENV" -c conda-forge

export PATH="$ENV/bin:$PATH"
export CC="$ENV/bin/x86_64-conda-linux-gnu-gcc"
export CXX="$ENV/bin/x86_64-conda-linux-gnu-g++"
export CMAKE_PREFIX_PATH="$ENV"
export LD_LIBRARY_PATH="$ENV/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CMAKE_C_COMPILER_LAUNCHER=ccache
export CMAKE_CXX_COMPILER_LAUNCHER=ccache

# Each job compiles on the node that runs the binary, so per-node codegen
# is safe here. ccache hashes the literal '-march=native' string, though:
# without a per-target cache, one CPU family's objects would be served to
# another's build and crash it. Namespace the cache by the compiler's
# resolved target instead. Shared across jobs of one CPU family on the
# expiring scratch (ccache manages its own concurrency); never NFS home.
export NS3_MARCH=native
target_sig=$("$CC" -march=native -Q --help=target 2>/dev/null \
    | sha256sum | cut -c1-12)
export CCACHE_DIR="${DCS_SCRATCH_BASE_DIR:-$work}/astra-ccache-${target_sig}"
echo "ccache: $CCACHE_DIR"
ccache --set-config=max_size=5G

bash "$repo_root/build/astra_ns3/build.sh" -c

# Compute nodes mount /tmp as tmpfs, so every byte of the job's scratch is
# charged against its SLURM memory limit. The object tree is the largest
# single charge (~3-4 GB) and is dead weight once the binary links; the
# runtime needs only build/ (binary and rpath'd libraries). Reclaiming it
# here is what keeps the sims from being OOM-killed hours later.
rm -rf "$repo_root/extern/network_backend/ns-3/cmake-cache"
