#!/bin/bash
# Forced SSH command: the ONLY operation the CI deploy key can perform.
# Reads a just-in-time runner config on stdin, stores it in a private file,
# and submits exactly one runner job to SLURM. Whatever command the client
# asked for is ignored, so a leaked key cannot get a shell.
set -euo pipefail

ROOT="${DCS_CI_ROOT:-$HOME/astra-ci}"
umask 077
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

sbatch --parsable "$ROOT/bin/runner-job.sbatch" "$jit_file"
