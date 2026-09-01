#!/usr/bin/env python3
"""Fold sealed raw-log segments into the arm's stream digest, then delete them.

The simulator writes its raw transport log as numbered zstd segments
(``<base>.zst.000``, ``.001``, ...) and rotates to a new segment when the
current one crosses the configured byte limit. There is deliberately no
channel between the simulator and this process: the filesystem is the whole
protocol. A segment is *sealed* - immutable forever - exactly when a segment
with a higher index exists for the same base, so this watcher polls the run
directory, folds every sealed segment's UNCOMPRESSED bytes into a running
sha256 per base, records a per-segment digest, and deletes the file.
Steady-state disk is one sealed segment in flight plus one growing.

The raw bytes are not shipped anywhere. The digest file this process
maintains is the arm's commitment to the stream it produced: the simulator
is a single-process, single-threaded discrete-event core, so the stream is
a pure function of (binary, inputs, seed) and anyone re-running the arm's
archived binary can recompute the same hashes. Hashing the uncompressed
content keeps the commitment independent of the zstd container; per-segment
digests exist only to localize a divergence, since segment boundaries are
an artifact of the compressor, not of the experiment.

On SIGTERM the contract changes: the simulator has exited, so every segment
including the last is final; drain them all, mark the digest complete, and
exit. No credential, no network: this process cannot outlive any token
because it never holds one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import sys
import time

import zstandard

SEGMENT_PATTERN = re.compile(r"^(?P<base>.+\.zst)\.(?P<index>\d{3,})$")

# One file per run directory; attest.py reads it after the drain. The name
# never matches SEGMENT_PATTERN, so the watcher cannot eat its own output.
DIGEST_FILENAME = "transport_stream_digest.json"

READ_CHUNK_BYTES = 1 << 20

# ---------------------------------------------------------------------------
# Pure core: the sealing algebra. No I/O below this line's functions.
# ---------------------------------------------------------------------------


def segment_index(name):
    """Parse ``<base>.zst.NNN`` into (base, index), or None."""
    match = SEGMENT_PATTERN.match(name)
    if match is None:
        return None
    return match.group("base"), int(match.group("index"))


def sealed_by_base(relative_paths, drain):
    """Group the hashable segments by base, in strict index order.

    A segment is sealed when a higher-indexed sibling of the same base
    exists; in drain mode (writer has exited) every segment is sealed.
    The order is numeric, never lexical: the stream hash is a left fold
    over the uncompressed concatenation, so ``.999`` must precede
    ``.1042`` even though the strings sort the other way. O(n log n) in
    the number of segment files, at most a few hundred per arm.
    """
    groups = {}
    for path in relative_paths:
        parsed = segment_index(path)
        if parsed is None:
            continue
        base, index = parsed
        groups.setdefault(base, []).append((index, path))
    sealed = {}
    for base, members in groups.items():
        members.sort()
        cutoff = len(members) if drain else len(members) - 1
        sealed[base] = tuple(members[:cutoff])
    return sealed


# ---------------------------------------------------------------------------
# Effect shell: streaming decompression, the digest fold, the poll loop.
# ---------------------------------------------------------------------------


def log(message):
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), message, flush=True)


class BaseState:
    """Running digest of one base's stream.

    ``next_index`` is the fold's frontier: a segment folds in exactly when
    its index equals it, so the stream hash is well-defined even though
    segments arrive (and are deleted) incrementally. ``note`` is a sticky
    first-anomaly record; once set, the base stops advancing and its
    remaining files stay on disk for forensics.
    """

    __slots__ = ("hasher", "segments", "next_index", "uncompressed_bytes", "note")

    def __init__(self):
        self.hasher = hashlib.sha256()
        self.segments = []
        self.next_index = 0
        self.uncompressed_bytes = 0
        self.note = ""

    def snapshot(self, drained):
        return {
            "stream_sha256": self.hasher.copy().hexdigest(),
            "uncompressed_bytes": self.uncompressed_bytes,
            "segment_count": self.next_index,
            "complete": bool(drained and not self.note),
            **({"note": self.note} if self.note else {}),
            "segments": list(self.segments),
        }


def digest_snapshot(states, drained):
    return {
        "schema": 1,
        "content": (
            "sha256 over the uncompressed concatenation of each base's "
            "segments, folded in index order; per-segment digests localize "
            "a divergence but segment boundaries belong to the compressor"
        ),
        "complete": bool(drained),
        "bases": {
            base: state.snapshot(drained) for base, state in sorted(states.items())
        },
    }


def hash_segment(path, stream_hasher):
    """Digest one sealed segment in one streaming pass, O(1) memory.

    Returns (sha256 hex, uncompressed bytes, advanced stream hasher). The
    stream fold works on a *copy* of the running hasher, so a decompression
    error mid-segment cannot poison the stream hash with a partial fold:
    the caller commits the returned copy only because this function proved
    the segment decompresses end to end.
    """
    segment_hasher = hashlib.sha256()
    candidate = stream_hasher.copy()
    total = 0
    with open(path, "rb") as handle:
        reader = zstandard.ZstdDecompressor().stream_reader(
            handle, read_across_frames=True
        )
        while True:
            chunk = reader.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            segment_hasher.update(chunk)
            candidate.update(chunk)
            total += len(chunk)
    return segment_hasher.hexdigest(), total, candidate


def walk_segments(watch_dir):
    found = []
    for root, _, files in os.walk(watch_dir):
        for name in files:
            full = os.path.join(root, name)
            relative = os.path.relpath(full, watch_dir)
            if segment_index(relative.replace(os.sep, "/")) is not None:
                found.append(relative.replace(os.sep, "/"))
    return found


def write_digest(watch_dir, states, drained):
    """Atomic snapshot: a reader sees the old digest or the new, never a torn one."""
    final = os.path.join(watch_dir, DIGEST_FILENAME)
    temporary = final + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(digest_snapshot(states, drained), handle, indent=2)
        handle.write("\n")
    os.replace(temporary, final)


def process_once(watch_dir, states, drain, keep):
    """One poll cycle: fold every newly sealed segment. Returns folds done."""
    folded = 0
    for base, members in sealed_by_base(walk_segments(watch_dir), drain).items():
        state = states.setdefault(base, BaseState())
        if state.note:
            continue
        for index, relative in members:
            if index < state.next_index:
                continue  # already folded; a leftover only --keep can produce
            if index > state.next_index:
                # The frontier segment is not in this listing. Mid-run that
                # is a racy directory walk to retry next cycle; at drain
                # nothing else will ever produce it, so the gap is final.
                if drain:
                    state.note = "gap: segment {} missing at drain".format(
                        state.next_index
                    )
                break
            full = os.path.join(watch_dir, relative)
            try:
                compressed = os.path.getsize(full)
                digest, uncompressed, advanced = hash_segment(full, state.hasher)
            except Exception as error:  # noqa: BLE001 - record, keep siblings alive
                state.note = "segment {}: {}".format(index, error)
                log("{}: {}".format(base, state.note))
                break
            state.hasher = advanced
            state.segments.append(
                {
                    "index": index,
                    "compressed_bytes": compressed,
                    "uncompressed_bytes": uncompressed,
                    "sha256": digest,
                }
            )
            state.next_index = index + 1
            state.uncompressed_bytes += uncompressed
            if not keep:
                os.remove(full)
            folded += 1
            log(
                "folded {} ({} MiB compressed, {} MiB uncompressed)".format(
                    relative, compressed // 2**20, uncompressed // 2**20
                )
            )
    return folded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch-dir", required=True)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="hash without deleting (debug escape hatch; disk grows unbounded)",
    )
    arguments = parser.parse_args()

    draining = {"flag": False}

    def request_drain(_signum, _frame):
        draining["flag"] = True

    signal.signal(signal.SIGTERM, request_drain)

    states = {}
    log("watching {} for sealed segments".format(arguments.watch_dir))
    while True:
        drain_now = draining["flag"]
        try:
            folded = process_once(
                arguments.watch_dir, states, drain=drain_now, keep=arguments.keep
            )
        except OSError as error:
            folded = 0
            log("directory walk failed, will retry: {}".format(error))
        # The digest is (re)written whenever it changed, and always at
        # drain - even an empty one records that the hasher ran and found
        # nothing, which attest.py distinguishes from "hasher never ran".
        if folded or drain_now:
            try:
                write_digest(arguments.watch_dir, states, drained=drain_now)
            except OSError as error:
                log("digest write failed, will retry: {}".format(error))
        if drain_now:
            log(
                "drain complete: {} base(s), {} anomalies".format(
                    len(states), sum(1 for s in states.values() if s.note)
                )
            )
            return 0
        time.sleep(arguments.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
