# syntax=docker/dockerfile:1.7
## ******************************************************************************
## This source code is licensed under the MIT license found in the
## LICENSE file in the root directory of this source tree.
##
## Copyright (c) 2024 Georgia Institute of Technology
## ******************************************************************************
##
## A self-contained build environment for ASTRA-sim + ns-3. Once this image is
## built (with network), every compile step works offline:
##
##   docker build -t astra-sim .
##   docker run --rm --network none astra-sim \
##       bash build/astra_ns3/build.sh -c
##
## The three build-time network dependencies are all baked in:
##   1. apt toolchain, Boost, and OpenMPI (image layers);
##   2. the locked Python environment: `uv sync --locked` warms the uv cache,
##      the managed CPython, and the git dependencies under /opt/uv, and the
##      venv itself lives in /opt/venv so a bind-mounted checkout can rebuild
##      it with `uv sync --locked --offline`;
##   3. the root CMakeLists' yaml-cpp FetchContent: a local bare mirror plus a
##      system-git `url.insteadOf` rewrite serves the clone from disk, so
##      `./ns3 configure` never reaches the network and no project file needs
##      to change.
##
## Multi-arch: every stage is portable. The base images are multi-arch, the
## abseil/protobuf source builds carry no -march flags, and the simulator's
## own build uses the ns-3 `release` profile, which is architecture-neutral
## (`optimized`, the profile that adds -march=native, is deliberately unused).
##   docker buildx build --platform linux/arm64 -t astra-sim .

ARG UV_VERSION=0.11.28
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv


### =============== Stage 1: native dependency builds =====================
## Abseil and Protobuf are compiled from source so CMake can use
## `find_package(protobuf CONFIG)` and protoc matches the Python
## protobuf==5.29.x gencode. Only the install trees reach the final image.
FROM ubuntu:22.04 AS native-deps
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install --yes --no-install-recommends \
    ca-certificates wget \
    gcc-11 g++-11 make cmake ninja-build \
    && rm -rf /var/lib/apt/lists/*

## Abseil 20240722.0 (latest LTS as of 10/31/2024). Built with C++17 to match
## the C++ standard of every consumer (AstraSim and Protobuf 29), because
## abseil's ABI follows the language version it was compiled under.
ARG ABSL_VER=20240722.0
ARG ABSL_SHA256=f50e5ac311a81382da7fa75b97310e4b9006474f9560ac46f54a9967f07d4ae3
RUN <<'EOF'
set -euo pipefail
cd /opt
wget -q "https://github.com/abseil/abseil-cpp/releases/download/${ABSL_VER}/abseil-cpp-${ABSL_VER}.tar.gz"
echo "${ABSL_SHA256}  abseil-cpp-${ABSL_VER}.tar.gz" | sha256sum --check
tar -xf "abseil-cpp-${ABSL_VER}.tar.gz" && rm "abseil-cpp-${ABSL_VER}.tar.gz"
cmake -S "abseil-cpp-${ABSL_VER}" -B "abseil-cpp-${ABSL_VER}/build" -G Ninja \
    -DCMAKE_CXX_STANDARD=17 \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/opt/abseil/install
cmake --build "abseil-cpp-${ABSL_VER}/build" --target install
rm -rf "abseil-cpp-${ABSL_VER}"
EOF

## Protobuf C++ 29.0, matching the pinned Python protobuf==5.29.x runtime.
ARG PROTOBUF_VER=29.0
ARG PROTOBUF_SHA256=10a0d58f39a1a909e95e00e8ba0b5b1dc64d02997f741151953a2b3659f6e78c
RUN <<'EOF'
set -euo pipefail
cd /opt
wget -q "https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOBUF_VER}/protobuf-${PROTOBUF_VER}.tar.gz"
echo "${PROTOBUF_SHA256}  protobuf-${PROTOBUF_VER}.tar.gz" | sha256sum --check
tar -xf "protobuf-${PROTOBUF_VER}.tar.gz" && rm "protobuf-${PROTOBUF_VER}.tar.gz"
cmake -S "protobuf-${PROTOBUF_VER}" -B "protobuf-${PROTOBUF_VER}/build" -G Ninja \
    -DCMAKE_CXX_STANDARD=17 \
    -DCMAKE_BUILD_TYPE=Release \
    -Dprotobuf_BUILD_TESTS=OFF \
    -Dprotobuf_ABSL_PROVIDER=package \
    -Dabsl_DIR=/opt/abseil/install/lib/cmake/absl \
    -DCMAKE_INSTALL_PREFIX=/opt/protobuf/install
cmake --build "protobuf-${PROTOBUF_VER}/build" --target install
rm -rf "protobuf-${PROTOBUF_VER}"
EOF


### =============== Stage 2: the build environment ========================
FROM ubuntu:22.04
ARG DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="ASTRA-sim build environment" \
    org.opencontainers.image.description="Offline-complete toolchain for ASTRA-sim + ns-3 evaluation builds" \
    org.opencontainers.image.licenses="MIT" \
    maintainer="Will Won <william.won@gatech.edu>, Jinsun Yoo <jinsun@gatech.edu>"

## The complete native toolchain the build scripts expect: build.sh drives
## cmake/ninja through ns-3, links Boost and OpenMPI, and CI fills ccache.
## graphviz backs the chakra visualizer in the Python environment.
RUN apt-get update && apt-get install --yes --no-install-recommends \
    ca-certificates coreutils wget vim git ccache \
    gcc-11 g++-11 make cmake ninja-build \
    clang-format \
    libboost-dev libboost-program-options-dev \
    openmpi-bin libopenmpi-dev \
    graphviz \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 100 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 100

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=native-deps /opt/abseil/install /opt/abseil/install
COPY --from=native-deps /opt/protobuf/install /opt/protobuf/install
ENV absl_DIR=/opt/abseil/install \
    protobuf_DIR=/opt/protobuf/install \
    PATH="/opt/protobuf/install/bin:$PATH" \
    PROTOBUF_FROM_SOURCE=True

## Offline yaml-cpp: the root CMakeLists fetches it by URL at configure time.
## A bare local mirror plus a system-level URL rewrite serves that clone from
## disk; the pinned commit is verified so a stale mirror fails here, not
## during a build. No project file changes.
ARG YAML_CPP_COMMIT=a83cd31548b19d50f3f983b069dceb4f4d50756d
RUN <<'EOF'
set -euo pipefail
git clone --bare https://github.com/jbeder/yaml-cpp.git /opt/mirrors/yaml-cpp.git
git -C /opt/mirrors/yaml-cpp.git cat-file -e "${YAML_CPP_COMMIT}^{commit}"
git config --system \
    url."file:///opt/mirrors/yaml-cpp.git".insteadOf \
    "https://github.com/jbeder/yaml-cpp.git"
EOF

## Unprivileged build user. UID/GID are overridable so a bind-mounted checkout
## keeps its host ownership.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" astra \
    && useradd --uid "${UID}" --gid "${GID}" --create-home astra \
    && mkdir -p /opt/venv /opt/uv /opt/ccache /app/astra-sim \
    && chown -R astra:astra /opt/venv /opt/uv /opt/ccache /app

## The Python environment lives outside the worktree so it survives a host
## checkout being bind-mounted over /app/astra-sim; the uv cache and managed
## CPython live under /opt/uv so `uv sync --locked --offline` can rebuild the
## venv without network.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv/astra-sim \
    UV_CACHE_DIR=/opt/uv/cache \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    VIRTUAL_ENV=/opt/venv/astra-sim \
    PATH="/opt/venv/astra-sim/bin:$PATH" \
    PYTHONPATH=/app/astra-sim \
    CCACHE_DIR=/opt/ccache

USER astra
WORKDIR /app/astra-sim

## Lockfiles first: source edits do not invalidate the dependency layer.
COPY --chown=astra:astra pyproject.toml uv.lock .python-version ./
RUN uv sync --locked

COPY --chown=astra:astra . ./
