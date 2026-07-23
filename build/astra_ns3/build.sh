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
    local configure_args=(--enable-mpi)
    # CI supplies a launcher through CMake's standard environment variable.
    # Bypass ns-3's own integration there: it weakens ccache correctness by
    # enabling sloppiness for timestamps and include-file metadata.
    if [[ -n "${CMAKE_CXX_COMPILER_LAUNCHER:-}" ]]; then
        configure_args+=(-- -DNS3_CCACHE=OFF)
    fi
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
