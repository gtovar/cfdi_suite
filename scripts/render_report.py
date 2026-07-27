#!/usr/bin/env python3
"""Render the final security scan report.

Reads findings.json, votes.json, coverage.json, and scan-meta.json from the
run directory. Writes CLAUDE-SECURITY-RESULTS.jsonl and the revision stamp
into the products directory. Moves any existing CLAUDE-SECURITY-RESULTS.md
up into the products directory. Removes the run directory afterward.

Usage:
    python3 render_report.py <run_dir> --products-dir <path>

The script:
1. Reads all JSON artifacts from the run directory
2. Writes CLAUDE-SECURITY-RESULTS.jsonl (one JSON object per line)
3. Writes the revision stamp (CLAUDE-SECURITY-REVISION-<sha>.json)
4. Moves CLAUDE-SECURITY-RESULTS.md up if present
5. Cleans up the run directory
6. Prints the products directory path and revision stamp filename
"""

import argparse
import json
import os
import shutil
import sys


def read_json(path: str) -> dict | list | None:
    """Read a JSON file, return None if missing or invalid."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def render_report(run_dir: str, products_dir: str) -> dict:
    """Render the scan results from the run directory into the products directory."""
    meta = read_json(os.path.join(run_dir, "scan-meta.json")) or {}
    findings_data = read_json(os.path.join(run_dir, "findings.json")) or []
    votes = read_json(os.path.join(run_dir, "votes.json")) or {}
    coverage = read_json(os.path.join(run_dir, "coverage.json")) or {}
    tally = read_json(os.path.join(run_dir, "vote-tally.json")) or {}

    findings = findings_data if isinstance(findings_data, list) else findings_data.get("findings", [])
    verified = tally.get("verified_findings", []) if isinstance(tally, dict) else findings

    os.makedirs(products_dir, exist_ok=True)

    jsonl_path = os.path.join(products_dir, "CLAUDE-SECURITY-RESULTS.jsonl")
    with open(jsonl_path, "w") as f:
        for finding in verified:
            json.dump(finding, f)
            f.write("\n")

    revision = meta.get("revision", "UNVERSIONED")
    dirty = "-dirty" in revision
    clean_rev = revision.replace("-dirty", "")
    stamp_name = f"CLAUDE-SECURITY-REVISION-{clean_rev}{'-dirty' if dirty else ''}.json"

    severity_counts = {}
    for f in verified:
        sev = f.get("severity", "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    verification_status = tally.get("status", "unverified") if isinstance(tally, dict) else "unverified"

    stamp = {
        "revision": revision,
        "dirty": dirty,
        "timestamp": meta.get("timestamp", ""),
        "mode": meta.get("mode", "scan"),
        "effort": meta.get("effort", "medium"),
        "scope": meta.get("scope"),
        "verification": {
            "status": verification_status,
            "total_findings": len(findings),
            "verified_findings": len(verified),
            "rejected": tally.get("rejected", len(findings) - len(verified)) if isinstance(tally, dict) else 0,
        },
        "severity_counts": severity_counts,
    }

    stamp_path = os.path.join(products_dir, stamp_name)
    with open(stamp_path, "w") as f:
        json.dump(stamp, f, indent=2)
        f.write("\n")

    md_path = os.path.join(run_dir, "CLAUDE-SECURITY-RESULTS.md")
    if os.path.isfile(md_path):
        shutil.move(md_path, os.path.join(products_dir, "CLAUDE-SECURITY-RESULTS.md"))

    shutil.rmtree(run_dir, ignore_errors=True)

    return {
        "products_dir": products_dir,
        "revision_file": stamp_name,
        "jsonl_file": "CLAUDE-SECURITY-RESULTS.jsonl",
        "verification": stamp["verification"],
    }


def main():
    parser = argparse.ArgumentParser(description="Render the final security scan report")
    parser.add_argument("run_dir", help="Run directory path")
    parser.add_argument("--products-dir", required=True, help="Products directory path")
    args = parser.parse_args()

    if not os.path.isdir(args.run_dir):
        print(json.dumps({"error": f"Run directory not found: {args.run_dir}"}), file=sys.stderr)
        sys.exit(1)

    result = render_report(args.run_dir, args.products_dir)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
