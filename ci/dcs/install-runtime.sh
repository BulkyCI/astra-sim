#!/bin/bash
# Install a prebuilt cluster-runtime bundle into this checkout: unpack it,
# prove the binary's library closure resolves from the bundle alone on
# THIS node, and export the runtime environment for every later step.
# Run from the repository root of a job whose $GITHUB_ENV is live.
#
# Usage: install-runtime.sh <bundle.tar.gz>
set -euo pipefail

bundle="${1:?usage: install-runtime.sh <bundle.tar.gz>}"

# tar, not the artifact's own archiving: only tar restores the executable
# bit and the runtime env's symlinks.
tar -xzf "$bundle"
rm -f "$bundle"

# Canonical physical path: the loader records what it resolves, and any
# comparison against a /scratch symlink spelling must see one form.
root="$(pwd -P)"
runtime="$root/runtimeenv"
lib="$root/extern/network_backend/ns-3/build/lib"

# Fail here, with a readable message, rather than inside an experiment.
# ns-3 leaves the release binary unsuffixed and suffixes every other
# build profile, so accept any of them and name what was unpacked.
mapfile -t binaries < <(
    find extern/network_backend/ns-3/build/scratch -maxdepth 1 -type f \
         -executable -name '*AstraSimNetwork*' | sort)
if (( ${#binaries[@]} == 0 )); then
    echo "::error::The unpacked cluster runtime has no AstraSimNetwork binary"
    exit 1
fi

# The RUNPATHs baked at build time point into the builder's dead scratch,
# so resolution must come entirely from the two directories exported
# below; env -i proves it before hours of simulation depend on it.
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
