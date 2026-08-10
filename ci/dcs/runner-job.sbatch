#!/bin/bash
#SBATCH --job-name=astra-gh-runner
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=4-20:00:00
#SBATCH --output=runner-%j.log
#
# Runs one just-in-time GitHub Actions runner for exactly one workflow job.
# The runner deregisters itself and exits when its job ends - completed,
# failed, or cancelled - so the allocation is returned the moment the work
# stops. The walltime above stays under SLURM's 5-day cap and above the
# 5-day Actions self-hosted job limit will never be hit in practice.
set -euo pipefail

ROOT="${DCS_CI_ROOT:-$HOME/astra-ci}"
jit_file=$1
jit=$(cat "$jit_file")
rm -f "$jit_file"

# Private copy of the runner install: concurrent runner jobs must not share
# runner state or work directories, and NFS home is visible on every node.
dir="$ROOT/jobs/runner-$SLURM_JOB_ID"
cp -r "$ROOT/runner" "$dir"
cleanup() { rm -rf "$dir"; }
trap cleanup EXIT

cd "$dir"
./run.sh --jitconfig "$jit" &
runner_pid=$!
trap 'kill "$runner_pid" 2>/dev/null || true' TERM INT

# Leak guard: a JIT runner whose workflow job was cancelled while still
# queued would listen forever for work that never arrives. If no worker
# process has started within 30 minutes, tear down and return the cores.
(
    sleep 1800
    pgrep -f "$dir/bin/Runner.Worker" >/dev/null \
        || kill "$runner_pid" 2>/dev/null
) &
guard_pid=$!

status=0
wait "$runner_pid" || status=$?
kill "$guard_pid" 2>/dev/null || true
exit "$status"
