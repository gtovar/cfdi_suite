#!/usr/bin/env python3
"""Capture scan revision metadata — writes scan-meta.json in the run directory.

Usage:
    python3 write_scan_meta.py <run_dir> <scan_root> --mode scan|changes [--effort low|medium|high|max] [--scope <dirs>] [--commit <sha>] [--base <ref>] [--merge-base <sha>]

The script:
1. Captures the git revision (HEAD sha, dirty flag)
2. For whole-repo scans, computes top-level directories from git ls-files
3. Writes scan-meta.json in the run directory
4. Prints the meta as JSON for the Security Lead to read
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def run_git(scan_root: str, *args: str) -> str:
    """Run a git command and return stdout, empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", scan_root, *args],
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"},
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except Exception:
        return ""


def git_revision(scan_root: str) -> str:
    """Get the HEAD revision sha (12 chars) or UNVERSIONED."""
    sha = run_git(scan_root, "rev-parse", "--short=12", "HEAD")
    if not sha:
        return "UNVERSIONED"
    dirty = run_git(scan_root, "status", "--porcelain")
    if dirty:
        return f"{sha}-dirty"
    return sha


def top_level_dirs(scan_root: str, scope: str | None = None) -> list[str] | None:
    """Compute top-level directories from git ls-files. Returns None for scoped scans."""
    if scope and scope not in (".", "./"):
        return None
    files = run_git(scan_root, "ls-files")
    if not files:
        return None
    dirs = set()
    for line in files.split("\n"):
        line = line.strip()
        if line and "/" in line:
            dirs.add(line.split("/")[0])
    return sorted(dirs)


def main():
    parser = argparse.ArgumentParser(description="Write scan metadata")
    parser.add_argument("run_dir", help="Run directory path")
    parser.add_argument("scan_root", help="Scan root directory")
    parser.add_argument("--mode", default="scan", choices=["scan", "changes"])
    parser.add_argument("--effort", default="medium", choices=["low", "medium", "high", "max"])
    parser.add_argument("--scope", default=None)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--base", default=None)
    parser.add_argument("--merge-base", default=None)
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    revision = git_revision(args.scan_root)

    meta = {
        "scan_root": os.path.abspath(args.scan_root),
        "run_dir": os.path.abspath(args.run_dir),
        "mode": args.mode,
        "effort": args.effort,
        "scope": args.scope,
        "commit": args.commit,
        "base": args.base,
        "merge_base": args.merge_base,
        "timestamp": ts,
        "revision": revision,
        "self_reported": True,
    }

    tld = top_level_dirs(args.scan_root, args.scope)
    if tld is not None:
        meta["top_level_dirs"] = tld

    os.makedirs(args.run_dir, exist_ok=True)
    with open(os.path.join(args.run_dir, "scan-meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")

    if tld is not None:
        print(f"top_level_dirs: {json.dumps(tld)}")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
