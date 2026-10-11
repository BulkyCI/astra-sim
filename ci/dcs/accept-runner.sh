#!/bin/bash
# Forced SSH command: the ONLY operation the CI deploy key can perform.
# Reads a just-in-time runner config on stdin, stores it in a private file,
# and submits exactly one runner job to SLURM. Whatever command the client
# asked for is ignored, so a leaked key cannot get a shell.
set -euo pipefail

umask 077

# The client's command word may name a tenant before a slash. A tenant is a
# fixed (control root, checkout, upstream) triple written here, so the
# client picks one by name and can never supply a path or a URL. No prefix
# is this repository's own tenant, exactly as before tenants existed. Each
# tenant's runner-job.sbatch keeps its own scratch parent, store and outbox,
# so tenants share no directory.
requested="${SSH_ORIGINAL_COMMAND:-runner}"
case "$requested" in
asteria/*)
    ROOT="$HOME/asteria-ci"
    REPO="$HOME/asteria"
    UPSTREAM="https://github.com/BulkyCI/asteria-ci.git"
    requested="${requested#asteria/}"
    ;;
*)
    ROOT="${DCS_CI_ROOT:-$HOME/astra-ci}"
    REPO="${DCS_CI_REPO:-$HOME/astra-sim}"
    UPSTREAM=""
    ;;
esac
# A named tenant bootstraps its own control root and checkout on first use;
# this repository's tenant was set up by setup.sh and is never created here.
if [[ -n "$UPSTREAM" ]]; then
    mkdir -p "$ROOT/jobs"
    if [[ ! -d "$REPO/.git" ]]; then
        staging=$(mktemp -d "$REPO.clone.XXXXXX")
        if ! git clone --quiet --no-recurse-submodules "$UPSTREAM" "$staging"; then
            rm -rf "$staging"
            echo "cannot clone $UPSTREAM" >&2
            exit 1
        fi
        # A wave's first provisions race here; the rename is atomic, so one
        # clone becomes the checkout and the others discard theirs.
        mv -T "$staging" "$REPO" 2>/dev/null || rm -rf "$staging"
    fi
fi
cd "$ROOT/jobs"

jit_file=$(mktemp "$ROOT/jobs/jitconfig.XXXXXX")
# A JIT config blob is a few KB; cap stdin so a hostile client cannot fill
# the filesystem through this channel.
head -c 65536 > "$jit_file"
if [[ ! -s "$jit_file" ]]; then
    rm -f "$jit_file"
    echo "empty jitconfig on stdin" >&2
    exit 1
fi

# The client's command word carries a display name for the SLURM job so
# squeue shows which experiment a runner serves. It is never executed;
# sanitize it to a safe token before using it as a name.
name=$(printf '%s' "$requested" \
    | tr -cd 'A-Za-z0-9._-' | head -c 64)

# Submit the repository's copy of the sbatch script, freshened by a quiet
# fast-forward pull, so a pushed fix is live on the next provision without
# re-running setup.sh. A push already gates what this script does; offline
# or diverged, the pull is skipped and the last checkout still works. Only
# this accept script itself still deploys through setup.sh.
git -C "$REPO" pull --ff-only --quiet 2>/dev/null || true
sbatch --parsable --job-name="${name:-runner}" \
    "$REPO/ci/dcs/runner-job.sbatch" "$jit_file"
