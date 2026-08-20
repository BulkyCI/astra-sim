#!/usr/bin/env python3
"""Partition bundle files into input-bounded tar batches.

The release archive carries every small file of a reproducibility bundle in
``<asset>.partNNN.tar.gz`` batches. A batch is a maximal run over the
lexicographically sorted relative paths whose summed cost stays within the
cap, with ``cost(file) = size + overhead`` over-approximating each tar
member's header and padding. The bound is arithmetic, not hope: gzip's
worst case on incompressible input is stored deflate blocks (inflation
under 0.04% plus a constant), so a 1,500,000,000-byte input budget provably
compresses below GitHub's 2,147,483,648-byte asset cap with ~600 MB of
margin. Lexicographic order makes the plan deterministic across re-runs
(same inputs, same batches, same asset names) and keeps a directory's files
together in one part.

Shell protocol: NUL-separated ``<size>\t<relative path>`` records on stdin
(``find . -type f -printf '%s\t%P\0'``); per-batch NUL-separated file lists
written to ``partNNN.files`` in the output directory (``tar --null -T``
consumes them verbatim); the batch count on stdout. Standard library only.
"""

from __future__ import annotations

import argparse
import os
import sys


def plan_batches(entries, cap, overhead):
    """Greedy next-fit over lexicographically sorted (path, size) pairs.

    Total, deterministic, order-preserving; O(n log n) in the file count.
    Every returned batch is nonempty and satisfies sum(size + overhead)
    <= cap. A single file whose own cost exceeds the cap is an upstream
    invariant violation (files over 100 MiB ship as individual assets
    long before batching) and raises rather than silently emitting an
    over-cap batch.
    """
    batches = []
    current = []
    current_cost = 0
    for path, size in sorted(entries):
        cost = size + overhead
        if cost > cap:
            raise ValueError(
                "single file exceeds the batch budget: {} ({} bytes)".format(
                    path, size
                )
            )
        if current and current_cost + cost > cap:
            batches.append(current)
            current = []
            current_cost = 0
        current.append(path)
        current_cost += cost
    if current:
        batches.append(current)
    return batches


def read_null_records(stream):
    """Parse NUL-separated ``<size>\\t<path>`` records into (path, size)."""
    for record in stream.read().split(b"\0"):
        if not record:
            continue
        size, _, path = record.partition(b"\t")
        yield path.decode(), int(size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cap", type=int, required=True)
    parser.add_argument("--overhead", type=int, default=2048)
    parser.add_argument("--output-dir", required=True)
    arguments = parser.parse_args()

    batches = plan_batches(
        read_null_records(sys.stdin.buffer), arguments.cap, arguments.overhead
    )
    os.makedirs(arguments.output_dir, exist_ok=True)
    for index, batch in enumerate(batches):
        list_path = os.path.join(
            arguments.output_dir, "part{:03d}.files".format(index)
        )
        with open(list_path, "wb") as handle:
            handle.write(b"\0".join(p.encode() for p in batch) + b"\0")
    print(len(batches))
    return 0


if __name__ == "__main__":
    sys.exit(main())
