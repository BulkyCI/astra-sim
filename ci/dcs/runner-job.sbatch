#!/bin/bash
#SBATCH --job-name=astra-gh-runner
# Two, not one: the simulator is single-threaded, but the uncached LTO
# link runs on every job and parallelizes with the core count, and the
# runner's own streaming threads would otherwise steal cycles from the
# sim for days. Two, not four: everything past the link uses one core,
# and allocation - not load - is what blocks other cluster users.
#SBATCH --cpus-per-task=2
# The simulator needs <1 GB; the rest is headroom for the build phase and
# for the last-resort case where scratch selection below lands on tmpfs
# /tmp, whose bytes are RAM charged to this limit.
#SBATCH --mem=16G
#SBATCH --time=4-20:00:00
#SBATCH --output=runner-%j.log
# Anything but the 2018 Threadrippers: the simulator is single-threaded and
# their Zen+ cores run it roughly half as fast as the modern nodes. A hard
# constraint is safe - the allowed set has 1184 CPUs and a full fleet needs
# 64 - and unlike --nodelist it never serializes behind specific hosts.
#SBATCH --constraint=EPYC_9634|AMD_Epyc7453|XeonGold-6348|AMD_Epyc9754
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

# The cluster's sanctioned scratch is /scratch/scratch-space/expires-<date>
# (support.cs.toronto.edu/systems/slurmresource.html): network-backed,
# shared by every node, wiped on expiry. The newest directory is guaranteed
# to expire more than five days out, which outlives this job's 4d20h
# walltime. Month names do not sort lexically, so rank by parsed date.
newest_scratch_space() {
    local dir stamp y m d epoch best="" best_epoch=0
    for dir in "${DCS_SCRATCH_BASE:-/scratch/scratch-space}"/expires-*; do
        [[ -d "$dir" ]] || continue
        stamp="${dir##*expires-}"
        read -r y m d <<< "${stamp//-/ }"
        epoch=$(date -d "$d $m $y" +%s 2>/dev/null) || continue
        if (( epoch > best_epoch )); then
            best="$dir"
            best_epoch=$epoch
        fi
    done
    [[ -n "$best" ]] && printf '%s\n' "$best"
}

# Everything mutable lives under this job's private directory: runner
# state, checkout, build tree. Candidates, best first. NFS home is quota'd
# (observed: provision failing on a 10 KB write); /var/tmp is a small root
# partition that co-located jobs fill (observed: runners dying logless on
# ENOSPC); /tmp is tmpfs billed to the job's memory limit (observed: the
# OOM killer taking the simulator). The 16G ask is sized to survive the
# tmpfs last resort.
dir=""
for base in "${SLURM_TMPDIR:-}" "$(newest_scratch_space)" /var/tmp /tmp; do
    [[ -n "$base" ]] || continue
    if mkdir -p "$base/astra-runner-$SLURM_JOB_ID" 2>/dev/null; then
        dir="$base/astra-runner-$SLURM_JOB_ID"
        break
    fi
done
if [[ -z "$dir" ]]; then
    echo "no writable scratch base found" >&2
    exit 1
fi
cp -r "$ROOT/runner/." "$dir/"
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
