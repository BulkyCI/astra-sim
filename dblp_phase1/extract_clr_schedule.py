#!/usr/bin/env python3
"""Extract a per-round CLR/tolerance schedule from a real DBLP server log.

Parses `server.log` produced by bound-tolerance-research
(mlt/server_multithreading.py) and emits schedule.json:

    {
      "source_log": "...",
      "num_rounds": 930,
      "clr_rounds": [0, 1, ..., 10, 372, ...],   # rounds where P_low was active
      "extracted_tolerances": {"low": 0.008, "high": 0.058}
    }

The binary CLR pattern (which rounds are critical) is the transferable part;
tolerance *values* for simulation are chosen later by apply_dblp.py so the
paper's settings (P_low=0.8%, P_high=40.8%) can be applied to a schedule
extracted from a run that used different config values.

Runs on plain Python 3 (no protobuf needed).
"""

import argparse
import json
import re

RE_ROUND = re.compile(r"Starting aggregation for round (\d+)")
RE_TOL = re.compile(r"Updated model bounded-loss tolerance to: ([0-9.]+)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("server_log")
    ap.add_argument("-o", "--out", default="schedule.json")
    args = ap.parse_args()

    rounds = []  # (round_number, tolerance_active_when_round_started)
    current_tol = None
    seen_tols = set()

    with open(args.server_log, errors="replace") as f:
        for line in f:
            m = RE_TOL.search(line)
            if m:
                current_tol = float(m.group(1))
                seen_tols.add(current_tol)
                continue
            m = RE_ROUND.search(line)
            if m:
                rounds.append((int(m.group(1)), current_tol))

    if not rounds:
        raise SystemExit("No aggregation rounds found — is this a DBLP server.log?")

    tol_low = min(seen_tols) if seen_tols else None
    # Rounds observed before any tolerance update ran under the initial
    # tolerance, which DBLP initializes to P_low (training start is critical).
    clr_rounds = sorted(
        r for r, tol in rounds if tol is None or (tol_low is not None and tol == tol_low)
    )

    schedule = {
        "source_log": args.server_log,
        "num_rounds": len(rounds),
        "clr_rounds": clr_rounds,
        "extracted_tolerances": {
            "low": tol_low,
            "high": max(seen_tols) if seen_tols else None,
        },
    }
    with open(args.out, "w") as f:
        json.dump(schedule, f, indent=1)

    frac = len(clr_rounds) / len(rounds)
    print(
        f"{len(rounds)} rounds, {len(clr_rounds)} CLR rounds ({frac:.1%}); "
        f"tolerances seen: {sorted(seen_tols)} -> {args.out}"
    )


if __name__ == "__main__":
    main()
