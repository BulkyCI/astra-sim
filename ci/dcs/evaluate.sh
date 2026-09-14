#!/usr/bin/env bash
# The one experiment command. The `evaluate` job of ns3-evaluation.yml runs
# this on a cluster node for every matrix record; a local checkout with a
# built simulator runs it the same way.
#
#   evaluate.sh comparison   matched arms through compare.py
#   evaluate.sh single       one arm through run.py, then report.py
#   evaluate.sh smoke        the four smoke scripts, the 16-rank trace, report.py
#
# Environment, all passed by the workflow as quoted variables:
#
#   EXPERIMENT_PROFILE          repository-relative profile (comparison, single)
#   EXPERIMENT_RUN_DIRECTORY    results directory, and where report.md lands;
#                               smoke defaults it to runs
#   SIMULATION_TIMEOUT_SECONDS  per-simulator cap (comparison, single)
#   REQUIRE_CONGESTION          "true" adds compare.py --require-congestion
#   COMPARISON_SEED             non-zero runs that one seed instead of the set
#                               (comparison), or that one seed instead of the
#                               profile's own (single)
#
# Every kind leaves its report at $EXPERIMENT_RUN_DIRECTORY/report.md. That one
# name is what attest.py, the step summary, the ledger, and the archive read,
# so nothing downstream branches on the kind.
#
# Effect order is fixed: the simulator commands run first, then the reporter,
# even when a simulator command failed, so a dead arm still leaves a record for
# the ledger. The exit status is the first failure's.
# The simulate_* and publish_* functions below are invoked through the names
# the dispatch binds, which shellcheck cannot follow.
# shellcheck disable=SC2317
set -euo pipefail

script_dir="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
cd "$script_dir/../.."

# Two parse boundaries, argument then environment. An unknown kind is a usage
# error whatever else is set, so it is rejected first and costs nothing; the
# workflow's provision job rejects it earlier still, before a SLURM runner is
# minted. Everything past here treats both as trusted.
kind="${1:?usage: evaluate.sh <comparison|single|smoke>}"
case "$kind" in
comparison | single)
    run_directory="${EXPERIMENT_RUN_DIRECTORY:?evaluate.sh needs EXPERIMENT_RUN_DIRECTORY}"
    ;;
smoke)
    # The four smoke scripts write fixed paths under runs/, so the whole tree
    # is the result and a local invocation needs no environment at all.
    run_directory="${EXPERIMENT_RUN_DIRECTORY:-runs}"
    ;;
*)
    echo "evaluate.sh: unknown kind '$kind'; expected comparison, single, or smoke" >&2
    exit 64
    ;;
esac

simulate_comparison() {
    local arguments=(
        uv run --locked python experiments/ring_3d/compare.py
        --profile "${EXPERIMENT_PROFILE:?evaluate.sh comparison needs EXPERIMENT_PROFILE}"
        --output "$run_directory"
        --simulation-timeout-seconds "${SIMULATION_TIMEOUT_SECONDS:?evaluate.sh comparison needs SIMULATION_TIMEOUT_SECONDS}"
        --clean
    )
    if [[ "${REQUIRE_CONGESTION:-false}" == "true" ]]; then
        arguments+=(--require-congestion)
    fi
    if [[ "${COMPARISON_SEED:-0}" != "0" ]]; then
        arguments+=(--seeds "$COMPARISON_SEED")
    fi
    "${arguments[@]}"
}

# compare.py writes comparison_report.md as part of the run.
publish_comparison() {
    :
}

# A seeded single arm is the profile's own domain at one seed, which is the
# same simulation compare.py's matching arm runs, so the two join. Without a
# seed the profile's own seed stands, as every unseeded single record expects.
simulate_single() {
    local arguments=(
        uv run --locked python experiments/ring_3d/run.py
        --profile "${EXPERIMENT_PROFILE:?evaluate.sh single needs EXPERIMENT_PROFILE}"
        --output "$run_directory"
        --simulation-timeout-seconds "${SIMULATION_TIMEOUT_SECONDS:?evaluate.sh single needs SIMULATION_TIMEOUT_SECONDS}"
        --clean
    )
    if [[ "${COMPARISON_SEED:-0}" != "0" ]]; then
        arguments+=(--seed "$COMPARISON_SEED")
    fi
    "${arguments[@]}"
}

publish_single() {
    uv run --locked python experiments/ring_3d/report.py \
        --profile "$EXPERIMENT_PROFILE" \
        --run-dir "$run_directory" \
        --output "$run_directory/research_report.md"
}

# failure_liveness.sh asserts that its profile does NOT complete: the
# CalledProcessError traceback it prints is the pass.
simulate_smoke() {
    bash experiments/ring_3d/smoke.sh
    bash experiments/ring_3d/failure_liveness.sh
    bash experiments/ring_3d/forgiveness_smoke.sh
    bash experiments/dblp/smoke.sh
    uv run --locked python experiments/ring_3d/generate.py \
        --profile experiments/ring_3d/profiles/llama3_70b_16.json \
        --output runs/ring_3d/llama3_70b_16 \
        --clean
}

publish_smoke() {
    uv run --locked python experiments/ring_3d/report.py \
        --profile experiments/ring_3d/profiles/smoke_8.json \
        --run-dir runs/ring_3d/smoke_8 \
        --output runs/ring_3d/smoke_8/research_report.md
}

# The three kinds, eliminated exhaustively. No default branch: the parse above
# admits nothing else, and `set -u` would catch it here if it ever did.
case "$kind" in
comparison)
    simulate=simulate_comparison
    publish=publish_comparison
    report_source="$run_directory/comparison_report.md"
    ;;
single)
    simulate=simulate_single
    publish=publish_single
    report_source="$run_directory/research_report.md"
    ;;
smoke)
    simulate=simulate_smoke
    publish=publish_smoke
    report_source=runs/ring_3d/smoke_8/research_report.md
    ;;
esac

status=0
"$simulate" || status=$?

publish_status=0
"$publish" || publish_status=$?
if ((status == 0)); then
    status="$publish_status"
fi

# The post-condition. A hard link, not a copy: attest.py appends its
# Provenance section to report.md afterwards, and the link keeps the
# kind-named report in the bundle identical to it. A missing source means
# the arm died before writing a report; the workflow's publish step says so
# and the ledger records the absence, so this is not itself a failure.
if [[ -f "$report_source" ]]; then
    mkdir -p "$run_directory"
    ln -f "$report_source" "$run_directory/report.md" \
        || cp "$report_source" "$run_directory/report.md"
fi

exit "$status"
