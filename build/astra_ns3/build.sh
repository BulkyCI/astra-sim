#!/bin/bash
set -e
# Absolue path to this script
SCRIPT_DIR=$(dirname "$(realpath $0)")
# Absolute paths to useful directories
ASTRA_SIM_DIR="${SCRIPT_DIR:?}"/../../astra-sim
NS3_DIR="${SCRIPT_DIR:?}"/../../extern/network_backend/ns-3

# Functions
function setup {
    PROTO_DIR="${SCRIPT_DIR}/../../extern/graph_frontend/chakra/schema/protobuf"
    protoc "${PROTO_DIR}/et_def.proto" \
        --proto_path "${PROTO_DIR}" \
        --cpp_out "${PROTO_DIR}"
}
function compile {
    cd "${NS3_DIR}"
    # ns-3's CLI defaults to its `default` profile, which is relwithdebinfo
    # with -O2 rewritten to -Os and asserts and logging forced on: optimized
    # for size and instrumented, which suits interactive model development
    # rather than multi-hour evaluation runs. `release` is -O3 with logging
    # compiled out. `optimized` is deliberately not used: it adds
    # -march=native, and a hosted runner's CPU model varies between runs, so
    # one binary would stop being reproducible across them.
    local profile="${NS3_BUILD_PROFILE:-release}"
    # No --enable-asserts: measured at 13.7% of evaluation wall time
    # (59.3s vs 51.2s per 10ms of simulated time, identical config), and
    # every evaluation arm pays it for hours. The smoke and liveness
    # scripts check behavior from the outside; set NS3_BUILD_PROFILE or
    # add the flag back locally when chasing a transport bug.
    local configure_args=(--enable-mpi --build-profile "${profile}")
    # LTO is ISA-neutral (unlike `optimized`'s -march=native, which a
    # mixed hosted-runner fleet cannot run reliably). Fast-linker
    # detection is disabled because it grabs whatever mold/lld the host
    # happens to ship: lld cannot read GCC's GIMPLE LTO objects (with
    # -fno-fat-lto-objects they hold no machine code), which fails the
    # final link with 'undefined symbol: main' on any machine where
    # ns-3's probe finds lld. The toolchain's own GNU ld auto-loads the
    # GCC LTO plugin and links these objects correctly everywhere.
    local cmake_args=(-DNS3_LINK_TIME_OPTIMIZATION=ON -DNS3_FAST_LINKERS=OFF)
    # x86-64-v3 (AVX2/FMA/BMI2) is the highest ISA level every amd64 VM
    # GitHub has fielded supports; AVX-512 is not fleet-wide, and the
    # build VM and evaluation VMs differ, so -march=native is unsafe
    # there. Environments where the compile node IS the run node (the DCS
    # runners) override with NS3_MARCH=native.
    if [[ "$(uname -m)" == "x86_64" ]]; then
        local march="${NS3_MARCH:-x86-64-v3}"
        cmake_args+=("-DCMAKE_C_FLAGS=-march=${march}"
                     "-DCMAKE_CXX_FLAGS=-march=${march}")
    fi
    # ns-3's own ccache integration defaults ON and adopts whatever ccache
    # the host happens to have - a hermeticity leak (it also weakens
    # correctness with timestamp/include sloppiness), and on the cluster it
    # would silently write a shared cache into quota'd NFS home. Always
    # off; a build that wants ccache supplies it through CMake's standard
    # CMAKE_*_COMPILER_LAUNCHER environment variables, as hosted CI does.
    cmake_args+=(-DNS3_CCACHE=OFF)
    configure_args+=(-- "${cmake_args[@]}")
    ./ns3 configure "${configure_args[@]}"
    ./ns3 build AstraSimNetwork -j $(nproc)
    cd "${SCRIPT_DIR:?}"
}
function cleanup {
    cd "${NS3_DIR}"
    ./ns3 distclean
    cd "${SCRIPT_DIR:?}"
}
function cleanup_result {
    echo '0'
}
function debug {
    cd "${NS3_DIR}"
    ./ns3 configure --enable-mpi --build-profile debug
    ./ns3 build AstraSimNetwork -j 12 -v
    cd "${NS3_DIR}/build/scratch"
}
# Main Script
case "$1" in
-l|--clean)
    cleanup;;
-lr|--clean-result)
    cleanup
    cleanup_result;;
-d|--debug)
    setup
    debug;;
-c|--compile|"")
    setup
    compile;;
-h|--help|*)
    printf "Invalid option '$1'.\n";;
esac
