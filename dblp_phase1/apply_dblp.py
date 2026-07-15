#!/usr/bin/env python3
"""Rewrite a baseline all-reduce trace into a DBLP (or fixed-tolerance) variant.

Phase-1 first-order model: a communication round that stops at (1 - p) of
gradient chunks delivers (1 - p) of the bytes, so each iteration's comm_size
is scaled by (1 - p_iter).

  --mode baseline : uniform p = --plow for every iteration (MLT-style fixed
                    tolerance; the paper's baseline).
  --mode dblp     : p = --plow inside CLR rounds (from schedule.json),
                    p = --phigh outside.

Iteration i of the trace maps to round i of the schedule. If the trace has
fewer iterations than the schedule, the schedule is downsampled by index
scaling so the CLR pattern's position/fraction is preserved.

Run inside the astra-sim Docker container.
"""

import argparse
import json
import sys

sys.path.insert(0, "/app/astra-sim/extern/graph_frontend/chakra/schema/protobuf")

import et_def_pb2 as et  # noqa: E402
from google.protobuf.internal import encoder  # noqa: E402
from google.protobuf.internal.decoder import _DecodeVarint32  # noqa: E402


def encode_delimited(msg) -> bytes:
    body = msg.SerializeToString()
    return encoder._VarintBytes(len(body)) + body


def read_delimited(buf, pos, msg):
    size, pos = _DecodeVarint32(buf, pos)
    msg.ParseFromString(buf[pos : pos + size])
    return pos + size


def rewrite_rank(path_in, path_out, p_for_iter):
    with open(path_in, "rb") as f:
        buf = f.read()
    out = bytearray()
    pos = 0

    gm = et.GlobalMetadata()
    pos = read_delimited(buf, pos, gm)
    out += encode_delimited(gm)

    it = 0
    while pos < len(buf):
        node = et.Node()
        pos = read_delimited(buf, pos, node)
        if node.type == et.COMM_COLL_NODE:
            for attr in node.attr:
                if attr.name == "comm_size":
                    p = p_for_iter(it)
                    attr.int64_val = max(1, int(attr.int64_val * (1.0 - p)))
            it += 1
        out += encode_delimited(node)

    with open(path_out, "wb") as f:
        f.write(bytes(out))
    return it


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-prefix", required=True)
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--npus", type=int, required=True)
    ap.add_argument("--mode", choices=["baseline", "dblp"], required=True)
    ap.add_argument("--plow", type=float, default=0.008)
    ap.add_argument("--phigh", type=float, default=0.408)
    ap.add_argument("--schedule", help="schedule.json (required for --mode dblp)")
    ap.add_argument("--iters", type=int, required=True, help="iterations in the trace")
    args = ap.parse_args()

    if args.mode == "baseline":
        p_for_iter = lambda i: args.plow  # noqa: E731
    else:
        if not args.schedule:
            ap.error("--mode dblp requires --schedule")
        with open(args.schedule) as f:
            sched = json.load(f)
        num_rounds = sched["num_rounds"]
        clr = set(sched["clr_rounds"])
        scale = num_rounds / args.iters

        def p_for_iter(i):
            round_idx = int(i * scale)
            # A trace iteration is critical if any schedule round it covers is.
            span = range(round_idx, max(round_idx + 1, int((i + 1) * scale)))
            return args.plow if any(r in clr for r in span) else args.phigh

    import os

    os.makedirs(os.path.dirname(args.out_prefix), exist_ok=True)
    iters = 0
    for rank in range(args.npus):
        iters = rewrite_rank(
            f"{args.in_prefix}.{rank}.et", f"{args.out_prefix}.{rank}.et", p_for_iter
        )

    n_low = sum(1 for i in range(iters) if p_for_iter(i) == args.plow)
    print(
        f"mode={args.mode}: {args.npus} ranks x {iters} iters -> {args.out_prefix}.*.et "
        f"({n_low} iters @ p={args.plow}, {iters - n_low} iters @ "
        f"p={args.phigh if args.mode == 'dblp' else args.plow})"
    )


if __name__ == "__main__":
    main()
