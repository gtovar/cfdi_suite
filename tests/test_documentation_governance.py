from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_documentation_governance import (
    Change,
    Finding,
    Snapshot,
    analyze,
    load_pending,
    update_pending,
)


CONFIG = {
    "version": 1,
    "document_suffixes": [".md"],
    "ignored_paths": [],
    "ownership": [
        {"pattern": "README.md", "owner": None},
        {"pattern": "docs/*.md", "owner": "nearest-index"},
        {"pattern": "docs/**/*.md", "owner": "nearest-index"},
    ],
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "scripts" / "check_documentation_governance.py"


class DocumentationGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "ai").mkdir()
        (self.root / "README.md").write_text("# Repo\n", encoding="utf-8")
        (self.root / "docs" / "README.md").write_text("# Docs\n", encoding="utf-8")
        (self.root / "docs" / "ai" / "documentation-checks.json").write_text(
            json.dumps(CONFIG), encoding="utf-8"
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "baseline"],
            cwd=self.root,
            check=True,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def snapshot(self) -> Snapshot:
        return Snapshot(self.root, "working")

    def test_no_changes_has_no_findings(self) -> None:
        findings, scope = analyze([], self.snapshot(), CONFIG)
        self.assertEqual(findings, [])
        self.assertEqual(scope, set())

    def test_broken_local_link_is_reproducible_error(self) -> None:
        guide = self.root / "docs" / "guide.md"
        guide.write_text("[ausente](./missing.md)\n", encoding="utf-8")
        findings, _ = analyze([Change("M", "docs/guide.md")], self.snapshot(), CONFIG)
        self.assertEqual([finding.code for finding in findings], ["BROKEN_LOCAL_LINK"])
        second_findings, _ = analyze(
            [Change("M", "docs/guide.md")], self.snapshot(), CONFIG
        )
        self.assertEqual(
            [finding.fingerprint for finding in findings],
            [finding.fingerprint for finding in second_findings],
        )

    def test_modified_document_without_owner_requires_review(self) -> None:
        notes = self.root / "notes"
        notes.mkdir()
        (notes / "idea.md").write_text("# Idea\n", encoding="utf-8")
        findings, _ = analyze([Change("M", "notes/idea.md")], self.snapshot(), CONFIG)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "DOCUMENT_OWNER_UNKNOWN")
        self.assertEqual(findings[0].severity, "review")

    def test_bare_document_name_is_not_treated_as_a_concrete_path(self) -> None:
        guide = self.root / "docs" / "guide.md"
        guide.write_text("El roadmap conserva un `STATUS.md`.\n", encoding="utf-8")
        findings, _ = analyze([Change("M", "docs/guide.md")], self.snapshot(), CONFIG)
        self.assertEqual(findings, [])

    def test_new_document_must_be_linked_from_owner_index(self) -> None:
        (self.root / "docs" / "decision.md").write_text("# Decision\n", encoding="utf-8")
        findings, _ = analyze([Change("A", "docs/decision.md")], self.snapshot(), CONFIG)
        self.assertIn("INDEX_ENTRY_MISSING", [finding.code for finding in findings])

    def test_directory_link_makes_child_discoverable(self) -> None:
        pilots = self.root / "docs" / "pilots"
        pilots.mkdir()
        (pilots / "README.md").write_text("# Pilots\n", encoding="utf-8")
        (pilots / "new.md").write_text("# New\n", encoding="utf-8")
        (self.root / "docs" / "README.md").write_text(
            "[Pilots](./pilots/)\n", encoding="utf-8"
        )
        findings, _ = analyze([Change("A", "docs/pilots/README.md")], self.snapshot(), CONFIG)
        self.assertNotIn("INDEX_ENTRY_MISSING", [finding.code for finding in findings])

    def test_rename_checks_the_previous_owner_index(self) -> None:
        old_area = self.root / "docs" / "old"
        new_area = self.root / "docs" / "new"
        old_area.mkdir()
        new_area.mkdir()
        (old_area / "README.md").write_text("[Guide](./guide.md)\n", encoding="utf-8")
        (new_area / "README.md").write_text("[Guide](./guide.md)\n", encoding="utf-8")
        (new_area / "guide.md").write_text("# Guide\n", encoding="utf-8")
        findings, _ = analyze(
            [Change("R", "docs/new/guide.md", "docs/old/guide.md")],
            self.snapshot(),
            CONFIG,
        )
        broken = [finding for finding in findings if finding.code == "BROKEN_LOCAL_LINK"]
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0].path, "docs/old/README.md")

    def test_pending_findings_survive_separate_reads(self) -> None:
        queue = self.root / ".git" / "documentation-governance" / "pending.json"
        finding = Finding(
            code="DOCUMENT_OWNER_UNKNOWN",
            severity="review",
            path="notes/idea.md",
            line=1,
            message="requires review",
        )
        update_pending(queue, [finding], {"notes/idea.md"})
        first = load_pending(queue)
        second = load_pending(queue)
        self.assertEqual(first["findings"], second["findings"])
        self.assertEqual(first["findings"][0]["id"], finding.fingerprint)

    def test_rechecking_fixed_path_clears_its_pending_finding(self) -> None:
        queue = self.root / ".git" / "documentation-governance" / "pending.json"
        finding = Finding(
            code="BROKEN_LOCAL_LINK",
            severity="error",
            path="docs/guide.md",
            line=2,
            message="broken",
        )
        update_pending(queue, [finding], {"docs/guide.md"})
        update_pending(queue, [], {"docs/guide.md"})
        self.assertEqual(load_pending(queue)["findings"], [])

    def test_staged_cli_persists_finding_for_next_session(self) -> None:
        guide = self.root / "docs" / "guide.md"
        guide.write_text("[ausente](./missing.md)\n", encoding="utf-8")
        subprocess.run(["git", "add", "docs/guide.md"], cwd=self.root, check=True)
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--staged"],
            cwd=self.root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        pending = self.root / ".git" / "documentation-governance" / "pending.json"
        self.assertTrue(pending.exists())
        resumed = subprocess.run(
            [sys.executable, str(CHECKER), "--show-pending"],
            cwd=self.root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(resumed.returncode, 0)
        self.assertIn("pendientes conservados", resumed.stdout)
        self.assertIn("missing.md", resumed.stdout)

    def test_github_event_catches_finding_after_hook_is_skipped(self) -> None:
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        (self.root / "docs" / "guide.md").write_text(
            "[ausente](./missing.md)\n", encoding="utf-8"
        )
        (self.root / "docs" / "README.md").write_text(
            "[Guide](./guide.md)\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "docs"], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "--no-verify",
                "-qm",
                "broken docs",
            ],
            cwd=self.root,
            check=True,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        event = self.root / "event.json"
        event.write_text(
            json.dumps(
                {
                    "pull_request": {
                        "base": {"sha": base},
                        "head": {"sha": head},
                    }
                }
            ),
            encoding="utf-8",
        )
        summary = self.root / "summary.md"
        result = subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--github-event",
                str(event),
                "--summary",
                str(summary),
                "--no-persist",
            ],
            cwd=self.root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("BROKEN_LOCAL_LINK", result.stdout)
        self.assertIn("Errores objetivos: **1**", summary.read_text(encoding="utf-8"))

    def test_ci_workflow_is_event_driven(self) -> None:
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "documentation-governance.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("push:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("--no-persist", workflow)


if __name__ == "__main__":
    unittest.main()
