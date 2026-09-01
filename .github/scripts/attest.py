#!/usr/bin/env python3
"""Compose one arm's attestation: the provenance that replaces raw-log escrow.

The raw per-packet stream is hashed and discarded by segment_hasher.py; what
ships instead is this record, which pins everything a reproduction needs:

  identity  which commit, run, arm, profile, and seed produced the result
  code      the exact simulator binary (sha256 + ISA level) and the runtime
            bundle it shipped in - both durably archived on the run release
  machine   the node the arm ran on: CPU, memory, kernel, glibc, SLURM job
  stream    the uncompressed-content digest of the raw transport stream
  outputs   sha256 of every retained result file in the run directory

The simulator is a single-process, single-threaded discrete-event core with
an integer event clock and seeded PRNGs, so the stream and outputs are a
pure function of (binary, inputs, seed): re-running the archived binary on
a CPU of the same ISA level with the same glibc family reproduces every
hash byte for byte, which is what makes a hash a commitment rather than a
checksum. Divergence across ISA levels (different FP code generation) is
expected and is exactly why the binary identity is part of this record.

Also appends a short Provenance section to the arm's report, so the ledger
issue - whose comments GitHub versions on every edit - carries a
timestamped public commitment to the stream hash without any extra comment
traffic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys

from segment_hasher import DIGEST_FILENAME, segment_index

SCHEMA = 1

# The x86-64-v4 probe set the workflow's ISA selection step tests, plus the
# v3 markers; recorded so the machine section explains the march choice.
ISA_FLAGS = (
    "avx2",
    "fma",
    "avx512f",
    "avx512bw",
    "avx512cd",
    "avx512dq",
    "avx512vl",
)

READ_CHUNK_BYTES = 1 << 20

# ---------------------------------------------------------------------------
# Pure core: parsing and composition. No I/O below this line's functions.
# ---------------------------------------------------------------------------


def parse_cpu(cpuinfo_text):
    """Model name and ISA-relevant flags from /proc/cpuinfo content."""
    model = ""
    flags = ()
    for line in cpuinfo_text.splitlines():
        key, _, value = line.partition(":")
        key = key.strip()
        if key == "model name" and not model:
            model = value.strip()
        elif key == "flags" and not flags:
            present = set(value.split())
            flags = tuple(flag for flag in ISA_FLAGS if flag in present)
    return {"model": model, "isa_flags": list(flags)}


def parse_mem_total_kb(meminfo_text):
    for line in meminfo_text.splitlines():
        if line.startswith("MemTotal:"):
            fields = line.split()
            if len(fields) >= 2 and fields[1].isdigit():
                return int(fields[1])
    return 0


def stream_status(digest, leftover_count):
    """Total classification of the raw-stream evidence.

    absent    the hasher never wrote a digest (it never ran, or died before
              the first seal) - the arm still attests its outputs
    partial   a digest exists but some base is incomplete or segments
              survived on disk (hasher died mid-run, or a base anomaly)
    complete  every base drained cleanly and no segment file remains
    """
    if digest is None:
        return "absent"
    bases = digest.get("bases", {})
    if leftover_count == 0 and digest.get("complete") and all(
        entry.get("complete") for entry in bases.values()
    ):
        return "complete"
    return "partial"


def build_attestation(identity, code, machine, stream, outputs):
    return {
        "schema": SCHEMA,
        "identity": identity,
        "code": code,
        "machine": machine,
        "stream": stream,
        "outputs": outputs,
    }


def provenance_markdown(attestation):
    """The report section: the commitment, small enough to never paginate."""
    code = attestation["code"]
    machine = attestation["machine"]
    stream = attestation["stream"]
    lines = [
        "",
        "## Provenance",
        "",
        "| Field | Value |",
        "| --- | --- |",
        "| Simulator binary | `{}` · `sha256:{}` (bundle `{}`) |".format(
            code.get("march", "unknown"),
            code.get("binary_sha256", "unknown"),
            code.get("bundle", "unknown"),
        ),
        "| Node | {} · {} · glibc {} · kernel {} · SLURM job {} |".format(
            machine.get("hostname", "unknown"),
            machine.get("cpu", {}).get("model", "unknown"),
            machine.get("glibc", "unknown"),
            machine.get("kernel", "unknown"),
            machine.get("slurm_job_id", "none"),
        ),
        "| Raw transport stream | {} · {} segment(s), {:.1f} GiB uncompressed |".format(
            stream.get("status", "unknown"),
            sum(
                entry.get("segment_count", 0)
                for entry in stream.get("bases", {}).values()
            ),
            sum(
                entry.get("uncompressed_bytes", 0)
                for entry in stream.get("bases", {}).values()
            )
            / 2**30,
        ),
    ]
    bases = stream.get("bases", {})
    if bases:
        lines += ["", "| Stream (uncompressed content) | sha256 |", "| --- | --- |"]
        lines += [
            "| `{}` | `{}`{} |".format(
                base,
                entry.get("stream_sha256", ""),
                "" if entry.get("complete") else " (incomplete)",
            )
            for base, entry in sorted(bases.items())
        ]
    lines += [
        "",
        (
            "The raw stream was hashed and discarded, not archived: the "
            "simulator is deterministic, so re-running the archived binary "
            "with this profile and seed on a matching ISA level reproduces "
            "these hashes byte for byte. The full record is "
            "`attestation.json` in this arm's bundle."
        ),
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Effect shell: fact gathering, file digests, composition, the two writes.
# ---------------------------------------------------------------------------


def sha256_file(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def gather_machine():
    uname = os.uname()
    os_release = ""
    for line in read_text("/etc/os-release").splitlines():
        if line.startswith("PRETTY_NAME="):
            os_release = line.partition("=")[2].strip().strip('"')
            break
    return {
        "hostname": uname.nodename,
        "cpu": parse_cpu(read_text("/proc/cpuinfo")),
        "cpu_count": os.cpu_count() or 0,
        "mem_total_kb": parse_mem_total_kb(read_text("/proc/meminfo")),
        "kernel": uname.release,
        "glibc": platform.libc_ver()[1],
        "os": os_release,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
    }


def gather_identity():
    environment = os.environ
    return {
        "repository": environment.get("GITHUB_REPOSITORY", ""),
        "run_id": environment.get("GITHUB_RUN_ID", ""),
        "run_attempt": environment.get("GITHUB_RUN_ATTEMPT", ""),
        "sha": environment.get("GITHUB_SHA", ""),
        "ledger_key": environment.get("LEDGER_KEY", ""),
        "profile": environment.get("EXPERIMENT_PROFILE", ""),
        "comparison_seed": environment.get("COMPARISON_SEED", ""),
    }


def gather_code(binary, march, bundle):
    code = {"march": march, "bundle": bundle}
    if binary and os.path.isfile(binary):
        code["binary"] = binary
        code["binary_sha256"] = sha256_file(binary)
    return code


def gather_stream(run_dir):
    digest_path = os.path.join(run_dir, DIGEST_FILENAME)
    digest = None
    note = ""
    if os.path.isfile(digest_path):
        # A digest that exists but cannot be decoded (a hasher defect; the
        # write is atomic, so never a torn snapshot) must not cost the
        # whole attestation - the outputs and code identity still attest.
        try:
            with open(digest_path, encoding="utf-8") as handle:
                digest = json.load(handle)
            if not isinstance(digest, dict):
                digest, note = None, "digest unreadable: not a JSON object"
        except (OSError, ValueError) as error:
            note = "digest unreadable: {}".format(error)
    leftovers = [
        relative
        for relative in walk_relative(run_dir)
        if segment_index(relative) is not None
    ]
    return {
        "status": stream_status(digest, len(leftovers)),
        **({"note": note} if note else {}),
        "leftover_segments": sorted(leftovers),
        "bases": (digest or {}).get("bases", {}),
    }


def walk_relative(run_dir):
    for root, _, files in os.walk(run_dir):
        for name in files:
            full = os.path.join(root, name)
            yield os.path.relpath(full, run_dir).replace(os.sep, "/")


def gather_outputs(run_dir):
    """Digest every retained file: raw segments are the hasher's domain and
    the attestation itself cannot contain its own hash."""
    outputs = []
    for relative in sorted(walk_relative(run_dir)):
        if segment_index(relative) is not None:
            continue
        if os.path.basename(relative) == "attestation.json":
            continue
        full = os.path.join(run_dir, relative)
        outputs.append(
            {
                "path": relative,
                "bytes": os.path.getsize(full),
                "sha256": sha256_file(full),
            }
        )
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--binary", default=os.environ.get("ASTRA_SIM_BINARY", ""))
    parser.add_argument("--march", default=os.environ.get("MARCH", ""))
    parser.add_argument("--bundle", default=os.environ.get("RUNTIME_KEY", ""))
    parser.add_argument(
        "--report",
        default="",
        help="report file to append the Provenance section to, if it exists",
    )
    arguments = parser.parse_args()

    attestation = build_attestation(
        identity=gather_identity(),
        code=gather_code(arguments.binary, arguments.march, arguments.bundle),
        machine=gather_machine(),
        stream=gather_stream(arguments.run_dir),
        outputs=[],
    )

    # The report is amended BEFORE the outputs are digested, so the hash
    # recorded for it matches the file that actually ships and lands in
    # the ledger. The section depends only on code/machine/stream, which
    # are already final here.
    if arguments.report and os.path.isfile(arguments.report):
        with open(arguments.report, "a", encoding="utf-8") as handle:
            handle.write(provenance_markdown(attestation))
        print("provenance section appended to {}".format(arguments.report))

    attestation["outputs"] = gather_outputs(arguments.run_dir)
    destination = os.path.join(arguments.run_dir, "attestation.json")
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(attestation, handle, indent=2)
        handle.write("\n")
    print(
        "attestation: {} output file(s), stream {}".format(
            len(attestation["outputs"]), attestation["stream"]["status"]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
