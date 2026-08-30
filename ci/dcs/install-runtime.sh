#!/bin/bash
# Install the cluster runtime into this checkout and export the runtime
# environment for every later step. Two sources, one closed choice:
#
#   Shared  - STORE_ENTRY names a sealed entry the run's seed job
#             published on shared scratch; the checkout links against it
#             and this job stores no private copy of the multi-gigabyte
#             runtime. The entry is immutable (chmod a-w at publish), so
#             no cleanup trap or stray write can disturb siblings.
#   Private - no STORE_ENTRY; extract the downloaded bundle exactly as
#             before the store existed. Sharing is an optimization layer:
#             this branch keeps every job correct when the store is
#             missing, expired, or was never seeded.
#
# Either way the binary's library closure is proven ON THIS NODE before
# any sim starts, and the exports land in $GITHUB_ENV.
#
# Usage: install-runtime.sh <bundle.tar.gz>   (with STORE_ENTRY optionally
# in the environment; when set, the bundle argument is unused - the
# download step is skipped on a store hit)
set -euo pipefail

bundle="${1:?usage: install-runtime.sh <bundle.tar.gz>}"
store_entry="${STORE_ENTRY:-}"

if [[ -n "$store_entry" ]]; then
    # A non-recursive checkout still materializes the submodule path as
    # an empty directory, so only the build tree link is created inside
    # it; the runtime env links at the checkout root, where the private
    # branch extracts it.
    ln -sfn "$store_entry/extern/network_backend/ns-3/build" \
        extern/network_backend/ns-3/build
    ln -sfn "$store_entry/runtimeenv" runtimeenv
    echo "runtime: linked against shared store entry $store_entry"
else
    # tar, not the artifact's own archiving: only tar restores the
    # executable bit and the runtime env's symlinks.
    tar -xzf "$bundle"
    rm -f "$bundle"
    echo "runtime: privately extracted (no shared store entry)"
fi

# Canonical physical path for the checkout; the store links inside it are
# deliberately left symbolic - the loader resolves through them, and the
# store entry path they point at is already canonical.
root="$(pwd -P)"
runtime="$root/runtimeenv"
lib="$root/extern/network_backend/ns-3/build/lib"

# Fail here, with a readable message, rather than inside an experiment.
# ns-3 leaves the release binary unsuffixed and suffixes every other
# build profile, so accept any of them and name what was unpacked.
mapfile -t binaries < <(
    find -L extern/network_backend/ns-3/build/scratch -maxdepth 1 -type f \
         -executable -name '*AstraSimNetwork*' | sort)
if (( ${#binaries[@]} == 0 )); then
    echo "::error::The installed cluster runtime has no AstraSimNetwork binary"
    exit 1
fi

# The RUNPATHs baked at build time point into the builder's dead scratch,
# so resolution must come entirely from the two directories exported
# below; env -i proves it on this node before hours of simulation depend
# on it.
unresolved="$(env -i PATH=/usr/bin:/bin LD_LIBRARY_PATH="$lib:$runtime/lib" \
    ldd "${binaries[0]}" | grep 'not found' || true)"
if [[ -n "$unresolved" ]]; then
    echo "::error::cluster runtime does not resolve on this node:"
    echo "$unresolved"
    exit 1
fi
printf '%s\n' "${binaries[@]}"

# Open MPI and its pmix/prrte substrate locate plugin trees through the
# prefix baked at build time - also dead here - unless these variables
# repoint them at the shipped env. ldd cannot see dlopen'd components,
# so these exports are load-bearing, not cosmetic.
{
    echo "LD_LIBRARY_PATH=${lib}:${runtime}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    echo "OPAL_PREFIX=${runtime}"
    echo "PMIX_INSTALL_PREFIX=${runtime}"
    echo "PRTE_PREFIX=${runtime}"
} >> "$GITHUB_ENV"
