#!/usr/bin/env python3
"""Generate a data-parallel all-reduce Chakra ET workload for ASTRA-sim.

Emits one .et file per NPU rank, each containing `iters` COMM_COLL_NODE
(ALL_REDUCE) nodes chained via data dependencies, modeling per-iteration
gradient synchronization in data-parallel training.

Run inside the astra-sim Docker container (protobuf version must match the
generated et_def_pb2.py).
"""

import argparse
import sys

sys.path.insert(0, "/app/astra-sim/extern/graph_frontend/chakra/schema/protobuf")

import et_def_pb2 as et  # noqa: E402
from google.protobuf.internal import encoder  # noqa: E402

BOOL, INT64 = "bool_val", "int64_val"


def encode_delimited(msg) -> bytes:
    body = msg.SerializeToString()
    return encoder._VarintBytes(len(body)) + body


def add_attr(node, name, kind, value):
    attr = node.attr.add()
    attr.name = name
    setattr(attr, kind, value)


def build_trace(iters: int, comm_size: int) -> bytes:
    out = bytearray()
    gm = et.GlobalMetadata()
    gm.version = "0.0.4"
    out += encode_delimited(gm)

    for i in range(iters):
        node = et.Node()
        node.id = i + 1
        node.name = f"allreduce_iter{i}"
        node.type = et.COMM_COLL_NODE
        if i > 0:
            node.data_deps.append(i)  # depend on previous iteration's node
        add_attr(node, "is_cpu_op", BOOL, False)
        add_attr(node, "comm_type", INT64, et.ALL_REDUCE)
        add_attr(node, "comm_size", INT64, comm_size)
        out += encode_delimited(node)
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npus", type=int, required=True)
    ap.add_argument("--iters", type=int, required=True)
    ap.add_argument("--comm-size", type=int, required=True, help="bytes per all-reduce")
    ap.add_argument("--out-prefix", required=True, help="e.g. traces/effnet_4npus/allreduce")
    args = ap.parse_args()

    blob = build_trace(args.iters, args.comm_size)
    import os

    os.makedirs(os.path.dirname(args.out_prefix), exist_ok=True)
    for rank in range(args.npus):
        with open(f"{args.out_prefix}.{rank}.et", "wb") as f:
            f.write(blob)
    print(
        f"Wrote {args.npus} ranks x {args.iters} iters, "
        f"comm_size={args.comm_size} B -> {args.out_prefix}.*.et"
    )


if __name__ == "__main__":
    main()
