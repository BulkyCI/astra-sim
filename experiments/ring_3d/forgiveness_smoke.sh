#!/usr/bin/env bash
# Native gate for the recovery domain. It is a sibling of smoke.sh rather than
# a second invocation inside it because its assertions are about forgiveness,
# not about the generator, and a failure here must name that.
set -euo pipefail

SCRIPT_DIR=$(dirname "$(realpath "$0")")
REPOSITORY_ROOT=$(realpath "$SCRIPT_DIR/../..")
OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_smoke_8"
ADMISSION_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_smoke_8_admission"
RERUN_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_smoke_8_rerun"
RACE_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_race_8"
DCQCN_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_dcqcn_8"
EXEMPT_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/exempt_smoke_8"
BERNOULLI_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/bernoulli_smoke_8"
VESTING_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/vesting_smoke_8"
VESTING_UNPACED_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/vesting_smoke_8_unpaced"
STRAGGLER_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/straggler_smoke_8"
REPRODUCTION_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_join_8"
COMPARISON_OUTPUT="$REPOSITORY_ROOT/runs/ring_3d/forgiveness_join_8_comparison"
# Deliberately not the profile's own seed: the claim under test is that both
# entry points derive the selection seed and the ns-3 run number from this
# number the same way, which a seed equal to the profile's would not exercise.
JOIN_SEED=9550582

RANGE_ALGEBRA="$REPOSITORY_ROOT/extern/network_backend/ns-3/build/scratch/ns3.42-RdmaRangeAlgebra"

# The receive-side range algebra first. Its straddle and partial-overlap
# branches cannot be reached through the switch, because every packet and
# every repair segment starts at a packet boundary, so no run below exercises
# them and this fixture is the only thing that does.
"$RANGE_ALGEBRA"

uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_smoke_8.json" \
  --output "$OUTPUT" --clean

# The same profile in the admission domain: the reference W' is measured
# against, with every other input identical.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_smoke_8.json" \
  --output "$ADMISSION_OUTPUT" --clean --domain admission

# The same recovery run again at the same seed. Forgiveness reads a ledger
# that grows as the run proceeds, so a reordering bug shows up here and
# nowhere else.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_smoke_8.json" \
  --output "$RERUN_OUTPUT" --clean

# S5: a retransmission timeout an order below the round trip, so resent data
# races the forgiveness that made it redundant.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_race_8.json" \
  --output "$RACE_OUTPUT" --clean

# The same profile under DCQCN, where a forgiven trim must still cost the
# sender the rate cut a pulled one would have.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_dcqcn_8.json" \
  --output "$DCQCN_OUTPUT" --clean

# The same fabric with the exemption on, where an eligible flow on a
# non-critical step discards its rate cuts until a receiver refuses to forgive.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/exempt_smoke_8.json" \
  --output "$EXEMPT_OUTPUT" --clean

# The three FORGIVE v2 receiver policies, one profile each and nothing else
# changed.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/bernoulli_smoke_8.json" \
  --output "$BERNOULLI_OUTPUT" --clean

# Vesting needs its own pair. It measures the budget against what a rank has
# received, so it releases nothing until a message completes, and the other
# smoke profiles send one DP All-Reduce per step that completes at the end of
# it. This pair buckets the gradient instead, and the two profiles differ only
# in the pacing rule.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/vesting_smoke_8.json" \
  --output "$VESTING_OUTPUT" --clean

uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/vesting_smoke_8_unpaced.json" \
  --output "$VESTING_UNPACED_OUTPUT" --clean

uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/straggler_smoke_8.json" \
  --output "$STRAGGLER_OUTPUT" --clean

uv --project "$REPOSITORY_ROOT" run --locked python \
  "$SCRIPT_DIR/check_forgiveness.py" "$OUTPUT" "$ADMISSION_OUTPUT" \
  --rerun "$RERUN_OUTPUT" --race "$RACE_OUTPUT" \
  --congestion-neutral "$DCQCN_OUTPUT" \
  --congestion-exempt "$EXEMPT_OUTPUT" \
  --bernoulli "$BERNOULLI_OUTPUT" \
  --vesting "$VESTING_OUTPUT" \
  --vesting-unpaced "$VESTING_UNPACED_OUTPUT" \
  --straggler "$STRAGGLER_OUTPUT"

# The v2 arms run as single records joined against the v1 wave's comparison
# arms, so a single run.py arm must reproduce compare.py's recovery arm at the
# same profile and seed. If it does not, the join is invalid and the variants
# have to run as full comparisons instead.
uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/run.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_smoke_8.json" \
  --output "$REPRODUCTION_OUTPUT" --clean --seed "$JOIN_SEED"

uv --project "$REPOSITORY_ROOT" run --locked python "$SCRIPT_DIR/compare.py" \
  --profile "$SCRIPT_DIR/profiles/forgiveness_smoke_8.json" \
  --output "$COMPARISON_OUTPUT" --clean --seeds "$JOIN_SEED" \
  --arm recovery_policy

uv --project "$REPOSITORY_ROOT" run --locked python \
  "$SCRIPT_DIR/check_single_arm_join.py" \
  --single "$REPRODUCTION_OUTPUT" \
  --comparison-arm "$COMPARISON_OUTPUT/seed_$JOIN_SEED/recovery_policy"

# The same inputs with one field broken per case. Each must be refused by
# name, and none may leave telemetry behind.
uv --project "$REPOSITORY_ROOT" run --locked python \
  "$SCRIPT_DIR/check_refusals.py" "$OUTPUT"
