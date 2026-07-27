#!/usr/bin/env python3
"""Deterministic vote computation for the adversarial verification panel.

Reads findings.json, votes.json, and coverage.json from a run directory.
Computes which findings survive the panel, clamps confidence levels,
and outputs the verified findings.

Usage:
    python3 compute_votes.py <run_dir> [--output <path>]

The script:
1. Reads findings.json, votes.json, coverage.json
2. For each finding, checks if it had a complete panel (3 voters)
3. Finding survives only if >= 2 of 3 voters said TRUE_POSITIVE
4. Clamps confidence: unanimous (3/3) → HIGH, 2/3 → MEDIUM, <2 → REJECTED
5. Computes verification.status: "verified" or "unverified" with reason
6. Writes verified findings and vote tally back
"""

import argparse
import json
import os
import sys


def compute_votes(findings: list, votes: dict, coverage: dict) -> dict:
    """Compute the panel verdicts and return verified results."""
    panel_results = {}
    total_dispatched = votes.get("panel_votes", 0)
    unreviewed = votes.get("unreviewed_candidate_sites", 0)

    for finding_id, vote_data in votes.get("rounds", {}).items():
        panel = vote_data.get("panel", {})
        adversarial = vote_data.get("adversarial", {})
        n_true = panel.get("true", 0)
        n_false = panel.get("false", 0)
        n_total = panel.get("voters", n_true + n_false)

        if n_total < 3:
            panel_results[finding_id] = {
                "panel": panel,
                "incomplete": True,
                "kept": False,
                "confidence": "REJECTED",
                "reason": f"only {n_total}/3 voters returned",
            }
            continue

        kept = n_true >= 2
        unanimous = n_true == 3
        confidence = "HIGH" if unanimous else "MEDIUM" if kept else "REJECTED"

        panel_results[finding_id] = {
            "panel": panel,
            "kept": kept,
            "confidence": confidence,
            "reason": f"{n_true}/3 TRUE_POSITIVE",
        }

        if adversarial:
            panel_results[finding_id]["adversarial"] = adversarial

    verified = []
    rejected_count = 0
    incomplete_count = 0

    for f in findings:
        fid = f.get("id", "")
        result = panel_results.get(fid)

        if not result:
            rejected_count += 1
            continue

        if result.get("incomplete"):
            incomplete_count += 1
            rejected_count += 1
            continue

        if not result["kept"]:
            rejected_count += 1
            continue

        clamped_confidence = result["confidence"]
        if f.get("confidence") == "HIGH" and clamped_confidence == "MEDIUM":
            clamped_confidence = "MEDIUM"

        verified.append({
            **f,
            "confidence": clamped_confidence,
            "verification": {
                "verdict": "VERIFIED",
                "panel": result["panel"],
                "adversarial": result.get("adversarial"),
            },
        })

    all_panels_complete = not any(
        r.get("incomplete") for r in panel_results.values()
    )
    verification_status = "verified" if all_panels_complete else "unverified"
    missed = sum(1 for f in findings if f.get("id", "") not in panel_results)

    reason_parts = []
    if not all_panels_complete:
        reason_parts.append("incomplete panel rounds")
    if missed:
        reason_parts.append(f"{missed} finding(s) missing from votes")
    if unreviewed:
        reason_parts.append(f"{unreviewed} candidate(s) unreviewed")

    return {
        "status": verification_status,
        "reason": "; ".join(reason_parts) if reason_parts else None,
        "total_findings": len(findings),
        "verified": len(verified),
        "rejected": rejected_count,
        "incomplete": incomplete_count,
        "unreviewed_candidates": unreviewed,
        "panel_votes_total": total_dispatched,
        "verified_findings": verified,
        "panel_results": {
            fid: {
                "kept": r["kept"],
                "confidence": r["confidence"],
                "reason": r["reason"],
            }
            for fid, r in panel_results.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Compute adversarial panel vote tally")
    parser.add_argument("run_dir", help="Run directory path")
    parser.add_argument("--output", help="Output file path (writes to run dir if not specified)")
    args = parser.parse_args()

    findings_path = os.path.join(args.run_dir, "findings.json")
    votes_path = os.path.join(args.run_dir, "votes.json")
    coverage_path = os.path.join(args.run_dir, "coverage.json")

    if not os.path.isfile(findings_path):
        print(json.dumps({"error": f"findings.json not found at {findings_path}"}), file=sys.stderr)
        sys.exit(1)

    findings = []
    try:
        with open(findings_path) as f:
            data = json.load(f)
            findings = data if isinstance(data, list) else data.get("findings", [])
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid findings.json: {e}"}), file=sys.stderr)
        sys.exit(1)

    votes = {}
    if os.path.isfile(votes_path):
        with open(votes_path) as f:
            votes = json.load(f)

    coverage = {}
    if os.path.isfile(coverage_path):
        with open(coverage_path) as f:
            coverage = json.load(f)

    result = compute_votes(findings, votes, coverage)

    output_path = args.output or os.path.join(args.run_dir, "vote-tally.json")
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    print(json.dumps(result))


if __name__ == "__main__":
    main()
