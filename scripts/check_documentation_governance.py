#!/usr/bin/env python3
"""Deterministic, offline documentation checks for Git hooks and CI.

The checker deliberately avoids semantic judgments. It validates local document
references, canonical placement, and index discoverability for changed Markdown
files, then stores ambiguous findings in Git's private directory for a later
agent session.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence
from urllib.parse import unquote, urlsplit


CONFIG_PATH = "docs/ai/documentation-checks.json"
PENDING_RELATIVE_PATH = "documentation-governance/pending.json"
HOOK_START = "# documentation-governance hook start"
HOOK_END = "# documentation-governance hook end"

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)]+)\)")
REFERENCE_LINK_RE = re.compile(
    r"^\s*\[[^\]]+\]:\s*(?P<target><[^>]+>|\S+)", re.MULTILINE
)
INLINE_CODE_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
ROOT_DOCUMENTS = {"AGENTS.md", "PROJECT_STATE.md", "README.md"}


@dataclasses.dataclass(frozen=True)
class Change:
    status: str
    path: str
    old_path: str | None = None


@dataclasses.dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    path: str
    line: int
    message: str
    target: str | None = None

    @property
    def fingerprint(self) -> str:
        material = "\0".join(
            (self.code, self.severity, self.path, str(self.line), self.target or "")
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.fingerprint,
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "target": self.target,
        }


def run_git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def repository_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    output = run_git(start, "rev-parse", "--show-toplevel")
    return Path(output.strip()).resolve()


def parse_name_status(output: str) -> list[Change]:
    changes: list[Change] = []
    for line in output.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        status = fields[0][:1]
        if status in {"R", "C"} and len(fields) >= 3:
            changes.append(Change(status=status, old_path=fields[1], path=fields[2]))
        elif len(fields) >= 2:
            changes.append(Change(status=status, path=fields[1]))
    return changes


def staged_changes(root: Path) -> list[Change]:
    return parse_name_status(
        run_git(
            root,
            "diff",
            "--cached",
            "--name-status",
            "--diff-filter=ACMRD",
        )
    )


def revision_changes(root: Path, base: str | None, head: str) -> list[Change]:
    if not base or set(base) == {"0"}:
        output = run_git(
            root,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            head,
        )
    else:
        output = run_git(
            root,
            "diff",
            "--name-status",
            "--diff-filter=ACMRD",
            base,
            head,
        )
    return parse_name_status(output)


class Snapshot:
    def __init__(self, root: Path, source: str, ref: str | None = None) -> None:
        self.root = root
        self.source = source
        self.ref = ref
        self.files = self._load_files()
        self.directories = self._directories(self.files)

    def _load_files(self) -> set[str]:
        if self.source == "working":
            tracked = run_git(self.root, "ls-files", "--cached").splitlines()
            untracked = run_git(
                self.root, "ls-files", "--others", "--exclude-standard"
            ).splitlines()
            return {normalize_repo_path(path) for path in tracked + untracked if path}
        if self.source == "index":
            return {
                normalize_repo_path(path)
                for path in run_git(self.root, "ls-files", "--cached").splitlines()
                if path
            }
        if self.source == "ref" and self.ref:
            return {
                normalize_repo_path(path)
                for path in run_git(
                    self.root, "ls-tree", "-r", "--name-only", self.ref
                ).splitlines()
                if path
            }
        raise ValueError(f"unsupported snapshot source: {self.source}")

    @staticmethod
    def _directories(files: Iterable[str]) -> set[str]:
        directories: set[str] = {"."}
        for path in files:
            parent = PurePosixPath(path).parent
            while str(parent) not in {"", "."}:
                directories.add(str(parent))
                parent = parent.parent
        return directories

    def exists(self, path: str) -> bool:
        normalized = normalize_repo_path(path)
        return normalized in self.files or normalized in self.directories

    def read_text(self, path: str) -> str | None:
        normalized = normalize_repo_path(path)
        if normalized not in self.files:
            return None
        if self.source == "working":
            try:
                return (self.root / normalized).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return None
        object_name = f":{normalized}" if self.source == "index" else f"{self.ref}:{normalized}"
        result = subprocess.run(
            ["git", "show", object_name],
            cwd=self.root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            return None
        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return None


def normalize_repo_path(path: str) -> str:
    normalized = posixpath.normpath(path.replace("\\", "/"))
    return normalized.removeprefix("./")


def load_config(root: Path) -> dict[str, object]:
    config_file = root / CONFIG_PATH
    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load {CONFIG_PATH}: {exc}") from exc
    if config.get("version") != 1:
        raise RuntimeError(f"unsupported {CONFIG_PATH} version")
    return config


def matches_any(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def is_document(path: str, config: dict[str, object]) -> bool:
    suffixes = tuple(str(item) for item in config.get("document_suffixes", [".md"]))
    return path.lower().endswith(suffixes)


def is_ignored(path: str, config: dict[str, object]) -> bool:
    patterns = [str(item) for item in config.get("ignored_paths", [])]
    return matches_any(path, patterns)


def ownership_rule(path: str, config: dict[str, object]) -> dict[str, object] | None:
    for rule in config.get("ownership", []):
        if not isinstance(rule, dict):
            continue
        pattern = str(rule.get("pattern", ""))
        if pattern and fnmatch.fnmatchcase(path, pattern):
            return rule
    return None


def nearest_index(path: str, available_files: set[str]) -> str | None:
    current = PurePosixPath(path).parent
    while str(current) not in {"", "."}:
        for filename in ("README.md", "index.md"):
            candidate = normalize_repo_path(str(current / filename))
            if candidate != path and candidate in available_files:
                return candidate
        current = current.parent
    return None


def owner_for(
    path: str, config: dict[str, object], available_files: set[str]
) -> str | None:
    rule = ownership_rule(path, config)
    if not rule:
        return None
    owner = rule.get("owner")
    if owner == "nearest-index":
        return nearest_index(path, available_files)
    if isinstance(owner, str) and owner:
        return normalize_repo_path(owner)
    return ""


def clean_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    elif any(char.isspace() for char in target):
        target = target.split(maxsplit=1)[0]
    target = target.strip()
    if not target or target.startswith("#"):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("//"):
        return None
    if parsed.path.startswith("/"):
        # Root-relative web application routes are not repository references.
        return None
    return unquote(parsed.path)


def resolve_link(source_path: str, target: str) -> str | None:
    resolved = normalize_repo_path(
        posixpath.join(posixpath.dirname(source_path), target)
    )
    if resolved == ".." or resolved.startswith("../"):
        return None
    return resolved


def markdown_targets(text: str) -> list[tuple[int, str]]:
    targets: list[tuple[int, str]] = []
    for pattern in (MARKDOWN_LINK_RE, REFERENCE_LINK_RE):
        for match in pattern.finditer(text):
            targets.append((text.count("\n", 0, match.start()) + 1, match.group("target")))
    return targets


def inline_document_targets(text: str) -> list[tuple[int, str]]:
    targets: list[tuple[int, str]] = []
    for match in INLINE_CODE_RE.finditer(text):
        candidate = match.group(1).strip().rstrip(".,:;")
        if not candidate or any(char in candidate for char in "*{}$()"):
            continue
        if any(char.isspace() for char in candidate):
            continue
        path_part = candidate.split("#", 1)[0]
        looks_like_document = (
            path_part.endswith((".md", ".mdx"))
            and (
                path_part.startswith(("docs/", "./", "../"))
                or path_part in ROOT_DOCUMENTS
            )
        )
        if looks_like_document:
            targets.append((text.count("\n", 0, match.start()) + 1, path_part))
    return targets


def resolve_inline_document(source_path: str, target: str) -> str | None:
    if target.startswith("docs/") or target in ROOT_DOCUMENTS:
        resolved = normalize_repo_path(target)
    else:
        resolved = resolve_link(source_path, target)
    if resolved == ".." or (resolved and resolved.startswith("../")):
        return None
    return resolved


def validate_references(path: str, text: str, snapshot: Snapshot) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()
    for line, raw_target in markdown_targets(text):
        target = clean_target(raw_target)
        if target is None:
            continue
        resolved = resolve_link(path, target)
        key = ("BROKEN_LOCAL_LINK", line, target)
        if key not in seen and (resolved is None or not snapshot.exists(resolved)):
            seen.add(key)
            findings.append(
                Finding(
                    code="BROKEN_LOCAL_LINK",
                    severity="error",
                    path=path,
                    line=line,
                    target=target,
                    message=f"La referencia Markdown local no existe: {target}",
                )
            )
    for line, target in inline_document_targets(text):
        resolved = resolve_inline_document(path, target)
        key = ("MISSING_DOCUMENT_REFERENCE", line, target)
        if key not in seen and (resolved is None or not snapshot.exists(resolved)):
            seen.add(key)
            findings.append(
                Finding(
                    code="MISSING_DOCUMENT_REFERENCE",
                    severity="error",
                    path=path,
                    line=line,
                    target=target,
                    message=f"La ruta documental citada no existe: {target}",
                )
            )
    return findings


def linked_repo_paths(owner: str, text: str) -> set[str]:
    destinations: set[str] = set()
    for _, raw_target in markdown_targets(text):
        target = clean_target(raw_target)
        if target is None:
            continue
        resolved = resolve_link(owner, target)
        if resolved:
            destinations.add(resolved.rstrip("/"))
    return destinations


def owner_indexes_path(owner: str, owner_text: str, path: str) -> bool:
    for destination in linked_repo_paths(owner, owner_text):
        if destination == path:
            return True
        if path.startswith(destination.rstrip("/") + "/"):
            return True
    return False


def analyze(
    changes: Sequence[Change], snapshot: Snapshot, config: dict[str, object]
) -> tuple[list[Finding], set[str]]:
    findings: list[Finding] = []
    document_changes = [
        change
        for change in changes
        if is_document(change.path, config) and not is_ignored(change.path, config)
    ]
    available_files = set(snapshot.files)
    for change in changes:
        if change.old_path:
            available_files.add(change.old_path)

    owners: dict[str, str] = {}
    owner_paths: set[str] = set()
    for change in document_changes:
        rule = ownership_rule(change.path, config)
        if rule is None and change.status != "D":
            findings.append(
                Finding(
                    code="DOCUMENT_OWNER_UNKNOWN",
                    severity="review",
                    path=change.path,
                    line=1,
                    message=(
                        "El documento modificado no pertenece a una ubicación "
                        "canónica reconocida; requiere revisión documental."
                    ),
                )
            )
            continue
        owner = owner_for(change.path, config, available_files)
        if owner:
            owners[change.path] = owner
            owner_paths.add(owner)
        if change.old_path:
            old_owner = owner_for(change.old_path, config, available_files)
            if old_owner:
                owner_paths.add(old_owner)

    paths_to_validate = {
        change.path
        for change in document_changes
        if change.status != "D" and snapshot.exists(change.path)
    }
    paths_to_validate.update(owner for owner in owner_paths if snapshot.exists(owner))
    for path in sorted(paths_to_validate):
        content = snapshot.read_text(path)
        if content is not None:
            findings.extend(validate_references(path, content, snapshot))

    for change in document_changes:
        if change.status not in {"A", "R", "C"}:
            continue
        owner = owners.get(change.path)
        if not owner or not snapshot.exists(owner):
            if ownership_rule(change.path, config) is not None:
                findings.append(
                    Finding(
                        code="DOCUMENT_OWNER_MISSING",
                        severity="error",
                        path=change.path,
                        line=1,
                        target=owner,
                        message="No existe el índice propietario esperado para el documento nuevo.",
                    )
                )
            continue
        owner_text = snapshot.read_text(owner)
        if owner_text is not None and not owner_indexes_path(owner, owner_text, change.path):
            findings.append(
                Finding(
                    code="INDEX_ENTRY_MISSING",
                    severity="error",
                    path=change.path,
                    line=1,
                    target=owner,
                    message=f"El documento nuevo no es descubrible desde su índice: {owner}",
                )
            )

    unique = {finding.fingerprint: finding for finding in findings}
    scoped_paths = {change.path for change in document_changes}
    return sorted(unique.values(), key=lambda item: (item.path, item.line, item.code)), scoped_paths


def pending_path(root: Path) -> Path:
    relative = run_git(root, "rev-parse", "--git-path", PENDING_RELATIVE_PATH).strip()
    path = Path(relative)
    return path if path.is_absolute() else root / path


def load_pending(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": 1, "findings": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "findings": []}
    if not isinstance(payload.get("findings"), list):
        payload["findings"] = []
    return payload


def update_pending(path: Path, findings: Sequence[Finding], scoped_paths: set[str]) -> None:
    payload = load_pending(path)
    retained = [
        item
        for item in payload.get("findings", [])
        if isinstance(item, dict) and item.get("path") not in scoped_paths
    ]
    merged = {str(item.get("id")): item for item in retained}
    for finding in findings:
        merged[finding.fingerprint] = finding.as_dict()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    output = {
        "version": 1,
        "updated_at": now,
        "findings": sorted(
            merged.values(), key=lambda item: (str(item.get("path")), int(item.get("line", 0)))
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def show_pending(root: Path) -> int:
    payload = load_pending(pending_path(root))
    findings = payload.get("findings", [])
    if not findings:
        return 0
    print("Gobernanza documental: pendientes conservados de una ejecución anterior:")
    for item in findings:
        severity = "ERROR" if item.get("severity") == "error" else "REVISAR"
        location = f"{item.get('path')}:{item.get('line', 1)}"
        print(f"  [{severity}] {location} {item.get('message')}")
    print("Ejecuta el verificador sobre los archivos corregidos para actualizar la cola.")
    return 0


def render_console(changes: Sequence[Change], findings: Sequence[Finding]) -> str:
    document_count = sum(1 for change in changes if change.path.endswith((".md", ".mdx")))
    if not findings:
        return f"Gobernanza documental: {document_count} documento(s) modificado(s), sin hallazgos."
    lines = [
        f"Gobernanza documental: {len(findings)} hallazgo(s) en {document_count} documento(s)."
    ]
    for finding in findings:
        severity = "ERROR" if finding.severity == "error" else "REVISAR"
        lines.append(
            f"  [{severity}] {finding.path}:{finding.line} {finding.code} — {finding.message}"
        )
    return "\n".join(lines)


def render_markdown(changes: Sequence[Change], findings: Sequence[Finding]) -> str:
    errors = sum(finding.severity == "error" for finding in findings)
    reviews = sum(finding.severity == "review" for finding in findings)
    lines = [
        "## Gobernanza documental determinista",
        "",
        f"Archivos modificados examinados: **{len(changes)}**  ",
        f"Errores objetivos: **{errors}**  ",
        f"Casos que requieren revisión: **{reviews}**",
        "",
    ]
    if not findings:
        lines.append("Sin hallazgos. La inactividad documental no se considera error.")
    else:
        lines.extend(
            [
                "| Nivel | Código | Ubicación | Detalle |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in findings:
            message = finding.message.replace("|", "\\|")
            lines.append(
                f"| {finding.severity} | `{finding.code}` | "
                f"`{finding.path}:{finding.line}` | {message} |"
            )
    lines.extend(
        [
            "",
            "Este control sólo usa el árbol Git y reglas locales; no realiza revisión semántica ni llamadas de red.",
        ]
    )
    return "\n".join(lines) + "\n"


def install_pre_commit_hook(root: Path) -> int:
    hook_output = run_git(root, "rev-parse", "--git-path", "hooks/pre-commit").strip()
    hook_path = Path(hook_output)
    if not hook_path.is_absolute():
        hook_path = root / hook_path
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    block = "\n".join(
        [
            HOOK_START,
            'repo_root="$(git rev-parse --show-toplevel)"',
            'python3 "$repo_root/scripts/check_documentation_governance.py" --staged',
            "documentation_status=$?",
            '[ "$documentation_status" -ne 0 ] && exit "$documentation_status"',
            HOOK_END,
        ]
    )
    if hook_path.exists():
        content = hook_path.read_text(encoding="utf-8")
    else:
        content = "#!/usr/bin/env bash\n\nexit 0\n"
    if HOOK_START in content and HOOK_END in content:
        content = re.sub(
            re.escape(HOOK_START) + r".*?" + re.escape(HOOK_END),
            block,
            content,
            flags=re.DOTALL,
        )
    else:
        final_exit = re.search(r"(?m)^exit 0\s*$", content)
        if final_exit:
            content = content[: final_exit.start()] + block + "\n\n" + content[final_exit.start() :]
        else:
            content = content.rstrip() + "\n\n" + block + "\n"
    hook_path.write_text(content, encoding="utf-8")
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Hook documental instalado sin reemplazar controles existentes: {hook_path}")
    return 0


def github_revisions(event_path: Path, root: Path) -> tuple[str | None, str]:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    if "pull_request" in event:
        pull_request = event["pull_request"]
        return pull_request["base"]["sha"], pull_request["head"]["sha"]
    base = event.get("before")
    head = event.get("after") or os.environ.get("GITHUB_SHA", "HEAD")
    if base and set(base) == {"0"}:
        default_branch = event.get("repository", {}).get("default_branch")
        pushed_ref = str(event.get("ref", "")).removeprefix("refs/heads/")
        if default_branch and pushed_ref != default_branch:
            merge_base = run_git(
                root, "merge-base", head, f"origin/{default_branch}", check=False
            ).strip()
            if merge_base:
                base = merge_base
    return base, head


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true", help="check the staged Git diff")
    source.add_argument("--github-event", type=Path, help="derive revisions from a GitHub event")
    source.add_argument("--paths", nargs="+", help="check explicit working-tree paths")
    parser.add_argument("--base", help="base revision for a committed diff")
    parser.add_argument("--head", default="HEAD", help="head revision for a committed diff")
    parser.add_argument("--summary", type=Path, help="append Markdown to a CI summary file")
    parser.add_argument("--no-persist", action="store_true", help="do not update the local queue")
    parser.add_argument("--show-pending", action="store_true", help="print the local queue")
    parser.add_argument("--install-hook", action="store_true", help="install into the current pre-commit hook")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = repository_root()
        if args.show_pending:
            return show_pending(root)
        if args.install_hook:
            return install_pre_commit_hook(root)
        config = load_config(root)
        if args.github_event:
            base, head = github_revisions(args.github_event, root)
            changes = revision_changes(root, base, head)
            snapshot = Snapshot(root, "ref", head)
        elif args.base:
            changes = revision_changes(root, args.base, args.head)
            snapshot = Snapshot(root, "ref", args.head)
        elif args.paths:
            changes = [Change(status="M", path=normalize_repo_path(path)) for path in args.paths]
            snapshot = Snapshot(root, "working")
        else:
            changes = staged_changes(root)
            snapshot = Snapshot(root, "index")
        findings, scoped_paths = analyze(changes, snapshot, config)
        if not args.no_persist and scoped_paths:
            update_pending(pending_path(root), findings, scoped_paths)
        print(render_console(changes, findings))
        if args.summary:
            args.summary.parent.mkdir(parents=True, exist_ok=True)
            with args.summary.open("a", encoding="utf-8") as summary_file:
                summary_file.write(render_markdown(changes, findings))
        return 1 if any(finding.severity == "error" for finding in findings) else 0
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Gobernanza documental: no se pudo ejecutar: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
