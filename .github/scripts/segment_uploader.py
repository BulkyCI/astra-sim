#!/usr/bin/env python3
"""Ship sealed raw-log segments to the run's release while the sim runs.

The simulator writes its raw transport log as numbered zstd segments
(``<base>.zst.000``, ``.001``, ...) and rotates to a new segment when the
current one crosses ~1.8 GB. There is deliberately no channel between the
simulator and this process: the filesystem is the whole protocol. A segment
is *sealed* - immutable forever - exactly when a segment with a higher
index exists for the same base, so this watcher polls the run directory,
uploads every sealed segment as an individual release asset (each under
the 2 GiB asset cap by construction), and deletes it locally. Steady-state
disk is one sealed segment in flight plus one growing, ~3.6 GB; if the
uplink falls behind the simulator, disk grows - accepted, never guarded,
because the experiment must run at full speed.

On SIGTERM the contract changes: the simulator has exited, so every
segment including the last is final; drain them all and exit. A missing
release tag means recording is disabled for this run; exit immediately and
let the ordinary bundle artifact carry whatever accumulates.

Standard library only: this runs on cluster nodes where the only promise
is a system python3.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SEGMENT_PATTERN = re.compile(r"^(?P<base>.+\.zst)\.(?P<index>\d{3,})$")

# GitHub's documented failure surface, mapped to what we do about it.
# Duplicates are REJECTED, never overwritten ("you'll receive an error and
# must delete the old file before you can re-upload"), an interrupted
# upload "may leave an empty asset with a state of `starter`" that "can be
# safely deleted", and on self-hosted runners the GITHUB_TOKEN "can only
# be refreshed for up to 24 hours" - multi-day jobs outlive it unless
# handed a longer-lived credential.
RETRY_NOW = "retry_now"  # transient; retry on the normal poll cycle
RATE_LIMITED = "rate_limited"  # back off as instructed, then retry
CREDENTIAL = "credential"  # token dead or scope lost; long backoff, warn
STALE_RELEASE = "stale_release"  # release id no longer valid; re-resolve
DUPLICATE = "duplicate"  # name exists remotely; verify-or-replace


def classify_http_error(status, headers):
    """Map an HTTP status (+ response headers) to a recovery strategy.

    Pure and total: every integer status maps to exactly one strategy.
    Returns (kind, backoff_seconds); backoff 0 means the caller's normal
    cadence applies.
    """
    retry_after = 0
    if headers is not None:
        try:
            retry_after = int(headers.get("Retry-After", "0"))
        except (TypeError, ValueError):
            retry_after = 0
    if status == 422:
        return DUPLICATE, 0
    if status == 404:
        return STALE_RELEASE, 0
    if status in (401,):
        return CREDENTIAL, 900
    if status in (403, 429):
        # 403 is both "forbidden" and GitHub's secondary rate limit; a
        # Retry-After header disambiguates toward the rate limiter.
        if retry_after > 0:
            return RATE_LIMITED, min(retry_after, 3600)
        return (CREDENTIAL, 900) if status == 403 else (RATE_LIMITED, 60)
    return RETRY_NOW, 0

# ---------------------------------------------------------------------------
# Pure core: the sealing algebra. No I/O below this line's functions.
# ---------------------------------------------------------------------------


def segment_index(name):
    """Parse ``<base>.zst.NNN`` into (base, index), or None."""
    match = SEGMENT_PATTERN.match(name)
    if match is None:
        return None
    return match.group("base"), int(match.group("index"))


def sealed_segments(relative_paths, drain):
    """Return the shippable segments among ``relative_paths``, sorted.

    A segment is sealed when a higher-indexed sibling of the same base
    exists; in drain mode (writer has exited) every segment is sealed.
    O(n log n) in the number of segment files, which is at most a few
    dozen per arm.
    """
    groups = {}
    for path in relative_paths:
        parsed = segment_index(path)
        if parsed is None:
            continue
        base, index = parsed
        groups.setdefault(base, []).append((index, path))
    shippable = []
    for base, members in groups.items():
        members.sort()
        cutoff = len(members) if drain else len(members) - 1
        shippable.extend(path for _, path in members[:cutoff])
    return sorted(shippable)


def asset_name(prefix, relative_path):
    """Flatten a bundle-relative path into the release-archive convention."""
    return "{}--{}".format(prefix, relative_path.replace("/", "__"))


# ---------------------------------------------------------------------------
# Effect shell: GitHub REST, filesystem walk, poll loop.
# ---------------------------------------------------------------------------


def log(message):
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), message, flush=True)


class ReleaseClient:
    def __init__(self, repo, tag, token):
        self.repo = repo
        self.tag = tag
        self.token = token
        self.release_id = None
        self.upload_url_base = None

    def _request(self, url, method="GET", data=None, headers=None):
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer {}".format(self.token))
        request.add_header("Accept", "application/vnd.github+json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
        return json.loads(body) if body else {}

    def resolve_release(self):
        payload = self._request(
            "https://api.github.com/repos/{}/releases/tags/{}".format(
                self.repo, self.tag
            )
        )
        self.release_id = payload["id"]
        self.upload_url_base = (
            "https://uploads.github.com/repos/{}/releases/{}/assets".format(
                self.repo, self.release_id
            )
        )

    def existing_asset(self, name):
        """Return the asset dict for ``name`` if it exists, else None."""
        page = 1
        while True:
            assets = self._request(
                "https://api.github.com/repos/{}/releases/{}/assets"
                "?per_page=100&page={}".format(self.repo, self.release_id, page)
            )
            for asset in assets:
                if asset.get("name") == name:
                    return asset
            if len(assets) < 100:
                return None
            page += 1

    def delete_asset(self, asset_id):
        self._request(
            "https://api.github.com/repos/{}/releases/assets/{}".format(
                self.repo, asset_id
            ),
            method="DELETE",
        )

    def upload(self, path, name):
        # Stream from disk: with Content-Length set, http.client sends a
        # read()-able body in chunks, so a 1.8 GB segment never occupies
        # 1.8 GB of the job's memory budget.
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            self._request(
                "{}?name={}".format(
                    self.upload_url_base, urllib.parse.quote(name, safe="")
                ),
                method="POST",
                data=handle,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(size),
                },
            )

    def upload_idempotent(self, path, name):
        """Upload with the documented duplicate semantics handled.

        GitHub rejects duplicate names outright, and an interrupted
        upload can leave a broken remote asset in state ``starter`` or
        ``open`` that must be deleted before retrying. On 422 we
        therefore inspect the remote: a same-size asset in state
        ``uploaded`` is the kill-before-confirmation case - the earlier
        transfer actually completed - and counts as success; anything
        else is a corpse to delete and replace."""
        try:
            self.upload(path, name)
            return True
        except urllib.error.HTTPError as error:
            if error.code != 422:
                raise
        remote = self.existing_asset(name)
        if remote is not None:
            if remote.get("size") == os.path.getsize(path) and (
                remote.get("state") == "uploaded"
            ):
                log("{} already on the release with matching size".format(name))
                return True
            self.delete_asset(remote["id"])
        self.upload(path, name)
        return True


def walk_segments(watch_dir):
    found = []
    for root, _, files in os.walk(watch_dir):
        for name in files:
            full = os.path.join(root, name)
            relative = os.path.relpath(full, watch_dir)
            if segment_index(relative.replace(os.sep, "/")) is not None:
                found.append(relative.replace(os.sep, "/"))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--release-tag", default="")
    parser.add_argument("--asset-prefix", required=True)
    parser.add_argument("--watch-dir", required=True)
    parser.add_argument("--poll-seconds", type=int, default=60)
    arguments = parser.parse_args()

    if not arguments.release_tag:
        log("no release tag: recording disabled for this run; exiting")
        return 0
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        log("no GH_TOKEN in the environment; exiting")
        return 1

    draining = {"flag": False}

    def request_drain(_signum, _frame):
        draining["flag"] = True

    signal.signal(signal.SIGTERM, request_drain)

    client = ReleaseClient(arguments.repo, arguments.release_tag, token)
    resolved = False
    log(
        "watching {} for sealed segments -> release {}".format(
            arguments.watch_dir, arguments.release_tag
        )
    )
    while True:
        drain_now = draining["flag"]
        # The extra backoff is the maximum the cycle's failures asked for;
        # it stretches, never replaces, the normal poll cadence.
        extra_backoff = 0
        if not resolved:
            try:
                client.resolve_release()
                resolved = True
            except Exception as error:  # noqa: BLE001 - stay alive
                extra_backoff = _log_api_failure("release lookup", error)
        shippable = []
        if resolved:
            try:
                shippable = sealed_segments(
                    walk_segments(arguments.watch_dir), drain=drain_now
                )
            except OSError as error:
                log("directory walk failed, will retry: {}".format(error))
        shipped = 0
        failed = 0
        for relative in shippable:
            full = os.path.join(arguments.watch_dir, relative)
            name = asset_name(arguments.asset_prefix, relative)
            # Per-segment isolation: one poisoned segment must never
            # starve its siblings. Files are removed only after a
            # positively confirmed remote copy, so every failure path
            # leaves the segment on disk for this or a later sweep (the
            # archive job re-ships stragglers under identical names).
            try:
                size_mib = os.path.getsize(full) // 2**20
                log("uploading {} ({} MiB)".format(name, size_mib))
                client.upload_idempotent(full, name)
                os.remove(full)
                shipped += 1
                log("shipped and removed {}".format(relative))
            except urllib.error.HTTPError as error:
                failed += 1
                kind, wait = classify_http_error(error.code, error.headers)
                extra_backoff = max(extra_backoff, wait)
                if kind == STALE_RELEASE:
                    # The release was recreated or deleted; the cached id
                    # is dead. Stop the pass and re-resolve next cycle.
                    resolved = False
                    log("release id stale (HTTP 404); re-resolving")
                    break
                if kind == CREDENTIAL:
                    log(
                        "credential failure (HTTP {}) on {}: self-hosted "
                        "GITHUB_TOKEN refreshes for at most 24 h, so "
                        "multi-day runs outlive it unless given a PAT; "
                        "segments will accumulate and the archive job "
                        "sweeps them at run end".format(error.code, name)
                    )
                else:
                    log(
                        "{} failed (HTTP {}), will retry: {}".format(
                            name, error.code, error.reason
                        )
                    )
            except Exception as error:  # noqa: BLE001 - stay alive
                failed += 1
                log("{} failed, will retry: {}".format(name, error))
        if shipped or failed:
            log("cycle: {} shipped, {} pending retry".format(shipped, failed))
        if drain_now:
            log("drain complete ({} left for the bundle); exiting".format(failed))
            return 0
        time.sleep(arguments.poll_seconds + extra_backoff)


def _log_api_failure(operation, error):
    """Log one API failure and return the backoff its class asks for."""
    if isinstance(error, urllib.error.HTTPError):
        kind, wait = classify_http_error(error.code, error.headers)
        log("{} failed (HTTP {}, {}), will retry".format(
            operation, error.code, kind))
        return wait
    log("{} failed, will retry: {}".format(operation, error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
