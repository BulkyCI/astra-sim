#!/bin/bash
# Build the ns-3 backend on a DCS node from the job's checkout, using only
# the rootless toolchain that ci/dcs/setup.sh installed: compiler, protoc,
# boost, MPI, and zlib all come from the conda env, nothing from the system
# but glibc. Delegates to the same build/astra_ns3/build.sh CI uses, so the
# flags (release, no asserts, LTO, x86-64-v3) stay defined in one place.
set -euo pipefail

ROOT="${DCS_CI_ROOT:-$HOME/astra-ci}"
ENV="$ROOT/buildenv"
repo_root="$(cd "$(dirname "$0")/../.." && pwd)"

# Reconcile the toolchain with the repo's declared package list, so a push
# that adds a build dependency deploys like any other change instead of
# demanding a manual setup.sh re-run. The stamp keeps the steady state a
# no-op; the lock serializes the sixteen first arrivals after a change.
spec="$repo_root/ci/dcs/buildenv-packages.txt"
stamp="$ENV/.provisioned-packages"
if ! cmp -s "$spec" "$stamp"; then
    (
        flock 9
        if ! cmp -s "$spec" "$stamp"; then
            export MAMBA_ROOT_PREFIX="$ROOT/mamba-root"
            grep -vE '^[[:space:]]*(#|$)' "$spec" \
                | xargs "$ROOT/bin/micromamba" install -y -p "$ENV" -c conda-forge
            cp "$spec" "$stamp"
        fi
    ) 9>"$ENV/.provision.lock"
fi

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
# resolved target instead.
export NS3_MARCH=native
target_sig=$("$CC" -march=native -Q --help=target 2>/dev/null \
    | sha256sum | cut -c1-12)
# On the expiring scratch the sbatch script selected, never in NFS home:
# concurrent jobs writing per-family caches into the quota'd home failed
# every compile with 'Disk quota exceeded'. All jobs of one CPU family
# share one warm cache here, and the scratch system's expiry is the
# pruning policy a cache deserves.
export CCACHE_DIR="${DCS_SCRATCH_BASE_DIR:-$ROOT}/astra-ccache-${target_sig}"
echo "ccache: $CCACHE_DIR"
ccache --set-config=max_size=5G

bash "$repo_root/build/astra_ns3/build.sh" -c

# Compute nodes mount /tmp as tmpfs, so every byte of the job's scratch is
# charged against its SLURM memory limit. The object tree is the largest
# single charge (~3-4 GB) and is dead weight once the binary links; the
# runtime needs only build/ (binary and rpath'd libraries). Reclaiming it
# here is what keeps the sims from being OOM-killed hours later.
rm -rf "$repo_root/extern/network_backend/ns-3/cmake-cache"
