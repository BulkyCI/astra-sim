#!/bin/bash
# One-time DCS setup: rootless build toolchain plus a pinned GitHub Actions
# runner, everything under $HOME. Assumes nothing from the system but glibc
# (Ubuntu 26.04 / glibc 2.43 exceeds the runner's 2.28 floor). No root, no
# docker, no system protoc: every native dependency comes from conda-forge
# (see docs/agents/rootless-ephemeral-build.md for the pin rationale).
#
# Run from a repository checkout on the cluster:
#   bash ci/dcs/setup.sh
set -euo pipefail

ROOT="${DCS_CI_ROOT:-$HOME/astra-ci}"
RUNNER_VERSION=2.336.0
RUNNER_SHA256=04cf0be1aff4c3ec3554466c39124ca250e3effd8873bb7e8d68535aa9505d5d
MAMBA_VERSION=2.3.2
script_dir=$(cd "$(dirname "$0")" && pwd)

mkdir -p "$ROOT/bin" "$ROOT/jobs"

if [[ ! -x "$ROOT/bin/micromamba" ]]; then
    curl -fsSL "https://micro.mamba.pm/api/micromamba/linux-64/${MAMBA_VERSION}" \
        | tar -xj -C "$ROOT" bin/micromamba
fi

# libprotobuf pinned pre-abseil so ns-3's module-mode find_package works;
# python 3.11 because the ns3 CLI breaks under newer argparse. The conda
# cross-compilers link everything against the env's own runtimes, which is
# what satisfies the "only glibc from the system" constraint.
export MAMBA_ROOT_PREFIX="$ROOT/mamba-root"
if [[ ! -d "$ROOT/buildenv" ]]; then
    "$ROOT/bin/micromamba" create -y -p "$ROOT/buildenv" -c conda-forge \
        gcc_linux-64 gxx_linux-64 cmake ninja ccache \
        libprotobuf=3.21.12 boost openmpi zlib zstd python=3.11
fi

if [[ ! -x "$ROOT/runner/run.sh" ]]; then
    curl -fsSL -o "$ROOT/runner.tar.gz" \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
    echo "${RUNNER_SHA256}  $ROOT/runner.tar.gz" | sha256sum -c -
    mkdir -p "$ROOT/runner"
    tar -xzf "$ROOT/runner.tar.gz" -C "$ROOT/runner"
    rm "$ROOT/runner.tar.gz"
fi

# accept-runner.sh and runner-job.sbatch run outside any checkout (forced
# SSH command and sbatch), so they are installed to a stable path. build.sh
# is NOT copied: the workflow runs it from the job's own checkout.
install -m 700 "$script_dir/accept-runner.sh" "$ROOT/bin/"
install -m 600 "$script_dir/runner-job.sbatch" "$ROOT/bin/"

# Preflight: the runner boots rootless and every dynamic dependency resolves.
missing=$(ldd "$ROOT/runner/bin/Runner.Listener" | grep "not found" || true)
if [[ -n "$missing" ]]; then
    echo "unresolved runner dependencies:" >&2
    echo "$missing" >&2
    exit 1
fi
(cd "$ROOT/runner" && ./run.sh --version)
"$ROOT/buildenv/bin/protoc" --version
"$ROOT/buildenv/bin/x86_64-conda-linux-gnu-g++" --version | head -1

cat <<EOF

Setup OK under $ROOT.

Next: add the CI deploy key to ~/.ssh/authorized_keys as a forced command,
so the key can submit runner jobs and do nothing else:

  command="$ROOT/bin/accept-runner.sh",restrict ssh-ed25519 AAAA... astra-ci

Then create the GitHub secrets/vars listed in ci/dcs/README.md.
EOF
