# Rootless ephemeral build of the ns-3 backend

Verified procedure for compiling and running `AstraSimNetwork` starting from
a bare-bones Ubuntu 24.04 machine: no root, no sudo password, and nothing
guaranteed beyond a gcc toolchain, a system `python3`, `git`, `curl`, and
`tar`/`bzip2`. No `apt` package is required at any step. Whatever the build
needs and the machine lacks — CPython 3.11, uv, protobuf, boost, OpenMPI,
zlib, cmake, ninja, ccache, possibly the C++ compiler itself — is installed
under `/tmp`, so the added toolchain is temporary by design: nothing
survives a reboot, nothing touches `$HOME`, and the repository tree keeps
only its normal `build/` outputs.

Distilled from the 2026-08-07 incident work, where this setup enabled the
local A/B that found a 93× hot-path regression; every step is the exact
verified path, with the failures preserved as gotchas.

## 0. Detect before installing

Tools already on the machine are preferred — but only where mixing is safe.
The dependencies split into two classes with different rules:

- **ABI-neutral drivers** — `cmake`, `ninja`, `ccache`, `git`, `curl`,
  `tar`. These never link into the binary; use any system copy that exists
  and install only the missing ones via micromamba. The verified incident
  build drove system cmake/ninja against conda compilers and libraries.
- **The ABI-coupled unit** — `libprotobuf`+`protoc`, boost, OpenMPI, zlib,
  and the C++ compiler that links against them. Resolve this set as a
  single unit, never piecewise. If the machine has the full system unit
  (`protoc`, `libprotobuf-dev`, `libboost-dev`,
  `libboost-program-options-dev`, `libopenmpi-dev`, zlib and zstd headers —
  i.e. what `.github/workflows/setup.sh` installs in CI), build with the
  system compiler and skip micromamba for all of them. If any member is missing,
  take the whole unit from conda-forge, including the conda compiler:
  conda-built libraries carry a newer libstdc++ than the system toolchain,
  and a mixed link is an unverified path.

```sh
# ABI-neutral: list what must come from micromamba
NEUTRAL=""
for t in cmake ninja ccache; do command -v "$t" >/dev/null || NEUTRAL="$NEUTRAL $t"; done

# ABI-coupled: system unit only if every member is present
if command -v protoc >/dev/null \
   && [ -e /usr/include/google/protobuf/message.h ] \
   && [ -e /usr/include/boost/version.hpp ] \
   && command -v mpicxx >/dev/null \
   && [ -e /usr/include/zlib.h ] \
   && [ -e /usr/include/zstd.h ]; then
  UNIT=system
else
  UNIT=conda
fi
echo "neutral to install:${NEUTRAL:- none}; ABI unit: $UNIT"
```

## 1. Create the ephemeral native toolchain

Skip this step entirely only when `UNIT=system` and `$NEUTRAL` is empty.
Pick a scratch root in `/tmp` (`$SCRATCH` below). Detect the architecture
first — micromamba downloads are arch-specific and the wrong one fails with
`Exec format error`:

```sh
SCRATCH=/tmp/astra-buildenv-$$   # ephemeral by design; never place in $HOME
mkdir -p "$SCRATCH" && cd "$SCRATCH"
ARCH=$(uname -m)                  # aarch64 -> linux-aarch64, x86_64 -> linux-64
case "$ARCH" in
  aarch64) MM_ARCH=linux-aarch64; GXX=gxx_linux-aarch64 ;;
  x86_64)  MM_ARCH=linux-64;      GXX=gxx_linux-64 ;;
esac
curl -sL "https://micro.mamba.pm/api/micromamba/${MM_ARCH}/latest" -o mm.tar.bz2
tar -xjf mm.tar.bz2 bin/micromamba
# Without this, micromamba leaks a multi-GB package cache into
# ~/.local/share/mamba, violating the nothing-outside-/tmp property.
export MAMBA_ROOT_PREFIX="$SCRATCH/mamba-root"

PKGS="$NEUTRAL"
if [ "$UNIT" = conda ]; then
  PKGS="$PKGS libprotobuf=3.21.12 libboost-devel openmpi zlib zstd $GXX"
fi
./bin/micromamba create -y -p "$SCRATCH/buildenv" -c conda-forge $PKGS
[ "$UNIT" = conda ] && ./buildenv/bin/protoc --version  # expect: libprotoc 3.21.12
```

Why each conda-unit pin exists:

- `libprotobuf=3.21.12` — conda-forge's default protobuf is the abseil-era
  35.x line; the repository's CMake uses module-mode `find_package(Protobuf)`
  (the apt-era path) and chakra's `protoio` includes
  `google/protobuf/io/gzip_stream.h`. 3.21.12 is the last pre-abseil line
  and matches the Ubuntu CI toolchain's API. The spec `protobuf=3.21` does
  not resolve on conda-forge; pin `libprotobuf` and let it pull the matching
  `protoc`.
- `zlib` — `gzip_stream.h` includes `zlib.h`; without it the build dies at
  ~90% in `protoio.cc`.
- `zstd` — `scratch/common.h` compresses the raw transport-event stream at
  runtime (`#include <zstd.h>`, linked via the scratch CMakeLists).
- `$GXX` — the conda cross-named compiler (`<arch>-conda-linux-gnu-g++`)
  keeps libstdc++ consistent with the conda-built protobuf/boost binaries;
  with the conda unit, the system gcc is left unused.
- `ccache` (when missing) — makes the second build of any A/B a
  minutes-long relink.

## 2. Create the ephemeral project Python environment

The `ns3` CLI needs Python ≤3.11 (its legacy argparse usage raises
`ValueError: action 'store_true' is not valid for positional arguments` on
3.12+, which includes Ubuntu 24.04's system `python3`), and the experiment
tooling needs the locked project dependencies. Prefer an environment that
already exists before creating one:

1. If `<repository_root>/.venv/bin/python3` exists and reports 3.11.x, use
   it directly: `PY=$PROJ/.venv/bin/python3`. This is the normal case on a
   machine where `./utils/setup.sh` has run.
2. Otherwise, bootstrap an ephemeral uv environment. Read the exact uv
   version bound from `required-version` in `pyproject.toml` (verified:
   0.11.28 against the `>=0.11.28,<0.12` bound; a newer uv — including a
   system-installed one — refuses the project outright, so check any
   existing `uv` on `PATH` against the bound before installing):

```sh
PROJ=<repository_root>            # checked out with submodules initialized
curl -LsSf https://astral.sh/uv/0.11.28/install.sh | \
    UV_INSTALL_DIR="$SCRATCH/uvhome" UV_NO_MODIFY_PATH=1 sh
rm -f ~/.config/uv/uv-receipt.json   # the installer writes this outside /tmp
cd "$PROJ"
UV_PROJECT_ENVIRONMENT="$SCRATCH/uvenv" \
UV_CACHE_DIR="$SCRATCH/uvcache" \
UV_PYTHON_INSTALL_DIR="$SCRATCH/uvpython" \
    "$SCRATCH/uvhome/uv" sync --locked
PY="$SCRATCH/uvenv/bin/python3"
"$PY" --version                   # expect: Python 3.11.x
```

The three `UV_*` overrides keep the interpreter download, the wheel cache,
and the venv itself inside `/tmp`; without them uv writes to `$HOME` and
the repository's `.venv`. If the repository lacks submodules, run
`git submodule update --init --recursive` first.

## 3. Export the native build environment

Putting `$ENV/bin` at the *end* of `PATH` keeps existing system tools
preferred and uses the conda copies only as fill-ins; the compiler and
library variables are set only when the ABI unit comes from conda:

```sh
ENV=$SCRATCH/buildenv
[ -d "$ENV/bin" ] && export PATH="$PATH:$ENV/bin"
export CMAKE_C_COMPILER_LAUNCHER=ccache CMAKE_CXX_COMPILER_LAUNCHER=ccache
export CCACHE_DIR="$SCRATCH/ccache"
if [ "$UNIT" = conda ]; then
  export CC="$ENV/bin/${ARCH}-conda-linux-gnu-gcc"
  export CXX="$ENV/bin/${ARCH}-conda-linux-gnu-g++"
  export CMAKE_PREFIX_PATH="$ENV"
  export LD_LIBRARY_PATH="$ENV/lib"
fi
```

With `UNIT=system`, none of the conda-specific variables are needed and
the build behaves exactly like CI's `.github/workflows/setup.sh` +
`build.sh` path.

## 4. Generate the chakra protobuf sources

The ns-3 scratch target compiles chakra's feeder directly and needs the
generated `et_def.pb.{h,cc}` beside the schema:

```sh
PROTO_DIR=$PROJ/extern/graph_frontend/chakra/schema/protobuf
protoc "$PROTO_DIR/et_def.proto" --proto_path "$PROTO_DIR" --cpp_out "$PROTO_DIR"
```

## 5. Clean foreign build state

If the working tree ever received an unpacked CI `native-runtime` artifact
(or any build from another machine), ninja's dependency graph records
absolute paths from that machine — the symptom is
`ninja: error: '/lib/x86_64-linux-gnu/libc.so.6' ... missing and no known
rule to make it`. Remove both directories unconditionally before the first
configure; a fresh configure is cheap:

```sh
rm -rf $PROJ/extern/network_backend/ns-3/cmake-cache \
       $PROJ/extern/network_backend/ns-3/build
```

## 6. Configure and build

Run the `ns3` CLI under `$PY` from step 2. Flags mirror CI exactly
(`build/astra_ns3/build.sh`): `release` profile (-O3, logging compiled
out), asserts re-enabled, MPI on, ns-3's own ccache integration off because
the launcher is supplied via environment:

```sh
cd $PROJ/extern/network_backend/ns-3
"$PY" ./ns3 configure \
    --enable-mpi --build-profile release --enable-asserts -- -DNS3_CCACHE=OFF
"$PY" ./ns3 build AstraSimNetwork -j "$(nproc)"
```

Expected: ~480 translation units, 25–40 minutes cold on 4 cores, minutes
warm via ccache. Success produces
`build/scratch/ns3.42-AstraSimNetwork` (~10 MB). Compile warnings
(sign-compare, pedantic anonymous structs) are normal; only `FAILED:` lines
matter.

## 7. Run the binary against a materialized profile

```sh
CFG=$SCRATCH/cfg
"$PY" -c "
import sys; sys.path.insert(0, '$PROJ/experiments/ring_3d')
from generate import materialize
from pathlib import Path
materialize(Path('$PROJ/experiments/ring_3d/profiles/<profile>.json'), Path('$CFG'))"

export LD_LIBRARY_PATH=$PROJ/extern/network_backend/ns-3/build/lib
[ "$UNIT" = conda ] && export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$ENV/lib"
$PROJ/extern/network_backend/ns-3/build/scratch/ns3.42-AstraSimNetwork \
  --workload-configuration="$CFG/workload/ring_3d" \
  --system-configuration="$CFG/system.json" \
  --network-configuration="$CFG/network_config.txt" \
  --remote-memory-configuration="$CFG/remote_memory.json" \
  --logical-topology-configuration="$CFG/logical_topology.json" \
  --comm-group-configuration="$CFG/communicator_groups.json" \
  --experiment-configuration="$CFG/experiment.json" \
  --clr-mask-configuration="$CFG/clr_mask.csv" \
  --experiment-output-dir="$CFG/telemetry" \
  --ns3-rng-seed=1 --ns3-rng-run=<seed>
```

For a pace measurement, wrap with `timeout --foreground <seconds>` and read
the `Liveness checkpoint` lines: `wall_ms_delta` per 10 ms of
`simulated_time_ns` is the figure of merit (see
[simulation liveness and performance](simulation-liveness-and-performance.md)).

## 8. A/B across submodule commits

Check out the comparison commit in place, rebuild (ccache turns this into a
few compiles plus a relink), re-measure, then restore:

```sh
cd $PROJ/extern/network_backend/ns-3
git checkout <commit-under-test>
# repeat step 6's build command, then step 7's measurement
git checkout <branch>            # restore; rebuild once more before trusting the tree
```

The comparison is valid on any architecture: the 93× x86 CI regression
reproduced on aarch64 at ≥7× with one three-line difference between
otherwise identical builds.

## Gotchas

- Never resolve the ABI-coupled unit piecewise (for example, system boost
  with conda protobuf, or conda libraries with the system compiler). The
  two verified configurations are all-system (the CI path) and all-conda
  with the conda compiler; anything in between risks libstdc++ and ABI
  mismatches that surface as link or runtime errors far from their cause.
- Wrong-arch micromamba fails with `Exec format error`; always derive the
  download URL from `uname -m`.
- Conda-forge default protobuf (35.x) configures but is the wrong API
  family for this repository; the failure surfaces late and confusingly.
  Pin `libprotobuf=3.21.12` up front.
- Missing `zlib` fails at ~90% of the build inside protobuf's
  `gzip_stream.h`, not in project code.
- The `ns3` CLI is incompatible with Python ≥3.12 argparse — this includes
  Ubuntu 24.04's system `python3` and conda's current Python. Only the uv
  3.11 environment from step 2 is known-good.
- A uv newer than the `required-version` bound in `pyproject.toml` refuses
  every project command (`error: Required uv version ... does not match`);
  install the pinned version, not "latest".
- Without the three `UV_*` environment overrides, uv writes its
  interpreter, cache, and venv outside `/tmp`, breaking the
  nothing-survives-a-reboot property. Two leaks survive even correct
  overrides and were caught only by a post-hoc `$HOME` audit: micromamba's
  package cache (multi-GB under `~/.local/share/mamba`, prevented by
  `MAMBA_ROOT_PREFIX`) and the uv installer's `~/.config/uv/uv-receipt.json`
  (delete it; `UV_UNMANAGED_INSTALL` does not work in this installer
  version). After any session, verify with
  `ls -d ~/micromamba ~/.mamba ~/.local/share/mamba ~/.config/uv` and check
  timestamps before deleting — a pre-existing `~/.local/share/uv` belongs
  to the machine's owner, not to this procedure.
- Stale `cmake-cache`/`build` directories from another machine poison
  ninja with foreign absolute paths; delete both before first configure.
- The scratch `AstraSim` objects compile with `-O0` appended after `-O3` by
  ns-3's scratch machinery. This is identical in CI — do not chase it as a
  local anomaly, and do not compare absolute pace against CI runners, only
  A/B ratios on the same machine.
- `sudo`/`apt` are unavailable on this class of machine; nothing in this
  procedure needs them, and nothing may be installed outside `/tmp`.
