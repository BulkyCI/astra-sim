"""Deterministic archive-bucket assignment for an experiment arm.

A GitHub release holds at most 1000 assets, and one wave's ~1.8 GB raw
segments alone approach that (927 observed), so per-run archives shard
into BUCKETS bucket releases beside the run-level release. The bucket is
a pure function of the arm's stable ledger key::

    bucket(ledger_key) = "b" + str(sha256(ledger_key) mod BUCKETS)
    release tag        = f"{run_release_tag}-{bucket}"

Nothing declares or stores the assignment: any consumer that knows an
arm's ledger key computes where its assets live. Re-runs land in their
original buckets because the function has no run-state inputs, and no
overflow-on-demand scheme can make placement depend on the timing of 31
concurrent writers.

Hashed at the ARM, never per file: an arm's segment family must
reconstruct (``cat <base>.zst.* | zstd -d``) from a single release.

Sizing law: expected assets per bucket ~ wave / BUCKETS (~250 today),
4x under the cap; raise BUCKETS as the matrix grows. Raising it moves
future runs' assignments only - published releases are immutable record.

Usage: python3 release_bucket.py <ledger_key>
"""

import hashlib
import sys

BUCKETS = 5


def bucket(ledger_key):
    """Map a ledger key to its bucket name, e.g. ``"b3"``."""
    digest = hashlib.sha256(ledger_key.encode("utf-8")).hexdigest()
    return "b{}".format(int(digest, 16) % BUCKETS)


def main(argv):
    if len(argv) != 2 or not argv[1]:
        print("usage: release_bucket.py <ledger_key>", file=sys.stderr)
        return 2
    print(bucket(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
