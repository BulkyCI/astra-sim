#!/bin/bash
# Publish the run's prebuilt runtime bundles into the shared immutable
# store on cluster scratch - once, by this single seed job, before any
# evaluation runner is provisioned. The wave's 30+ jobs then link against
# one extracted copy per ISA level instead of each holding its own
# multi-gigabyte extraction.
#
# Lockless by construction, not by protocol: the workflow DAG runs this
# job to completion before any reader exists, so mutual exclusion is
# temporal and no filesystem lock (flock, mkdir mutex, sentinel) appears
# anywhere. The only atomic primitive is rename: an entry is built in a
# temp directory on the same filesystem, sealed read-only, and moved to
# its final name in one step - the final path's existence IS the proof of
# completeness, and a torn entry is unrepresentable because it only ever
# lives under a temp name.
#
# Total on degraded infrastructure: no shared scratch means no store, and
# the script exits 0 - every evaluation job falls back to its own private
# extraction, which is exactly the pre-store behavior.
#
# Usage: seed-store.sh <key>=<bundle.tar.gz> [<key>=<bundle.tar.gz> ...]
# Requires: ASTRA_STORE_ROOT exported by runner-job.sbatch (empty when the
# node found no network scratch base).
set -euo pipefail

STORE_ROOT="${ASTRA_STORE_ROOT:-}"
# Reap entries older than this many days: strictly above the 4d20h SLURM
# walltime plus queue slack, so no entry a live wave could still read is
# ever eligible. A pure age predicate - deliberately not a squeue oracle,
# whose read would race other runs' provisioning windows. A job that
# outlives its entry lands in the private fallback and stays correct;
# the scratch volume's own expiry is the backstop behind this sweep.
SWEEP_AGE_DAYS="${ASTRA_STORE_SWEEP_AGE_DAYS:-6}"

if (( $# == 0 )); then
    echo "usage: seed-store.sh <key>=<bundle.tar.gz> [...]" >&2
    exit 2
fi
if [[ -z "$STORE_ROOT" ]]; then
    echo "no network scratch on this node: store disabled, evaluations" \
         "will extract privately"
    exit 0
fi
mkdir -p "$STORE_ROOT"

# Sweep before publish: the single-writer phase is the only place any
# deletion happens. Orphaned temp directories from a crashed seed age out
# through the same predicate.
while IFS= read -r -d '' entry; do
    echo "store: sweeping expired entry ${entry##*/}"
    chmod -R u+w "$entry" 2>/dev/null || true
    rm -rf "$entry"
done < <(find "$STORE_ROOT" -mindepth 1 -maxdepth 1 \
    -mtime "+${SWEEP_AGE_DAYS}" -print0)

publish() {
    local key=$1 bundle=$2
    local final="$STORE_ROOT/$key"
    # Idempotent re-run (a workflow re-run attempt): the winner stands.
    if [[ -d "$final" ]]; then
        echo "store: ${key} already published"
        return 0
    fi
    local temp
    temp="$(mktemp -d "$STORE_ROOT/.tmp-${key}.XXXXXX")"
    tar -xzf "$bundle" -C "$temp"
    if ! find "$temp/extern/network_backend/ns-3/build/scratch" \
            -maxdepth 1 -type f -executable -name '*AstraSimNetwork*' \
            2>/dev/null | grep -q .; then
        echo "::error::bundle for ${key} has no AstraSimNetwork binary"
        chmod -R u+w "$temp" 2>/dev/null || true
        rm -rf "$temp"
        return 1
    fi
    # Seal, then publish. Read-only content means no reader's cleanup trap
    # or stray rm can unlink a file out from under a running sibling;
    # rename needs write permission only on the parents, so a sealed tree
    # still moves.
    chmod -R a-w "$temp"
    if mv -T "$temp" "$final" 2>/dev/null; then
        echo "store: published ${key}"
        return 0
    fi
    # mv -T refuses to replace: the only way to lose is a concurrent
    # attempt having published first, which same-key writers cannot do
    # live (GitHub serializes re-run attempts) but a stale NFS attribute
    # cache can fake. Either way the existing entry is complete by the
    # rename law - adopt it.
    chmod -R u+w "$temp" 2>/dev/null || true
    rm -rf "$temp"
    if [[ -d "$final" ]]; then
        echo "store: ${key} already published (adopted)"
        return 0
    fi
    echo "::error::publish failed for ${key}"
    return 1
}

status=0
for pair in "$@"; do
    if [[ "$pair" != *=* ]]; then
        echo "bad argument (want key=bundle): ${pair}" >&2
        exit 2
    fi
    publish "${pair%%=*}" "${pair#*=}" || status=1
done
exit "$status"
