#!/usr/bin/env python3
"""
reconcile_registry.py — Reconciliación mecánica del registro unificado de hallazgos.

Código determinista, sin LLM, re-ejecutable cuando aparezca un batch nuevo.
verify.py ya establece el principio del repo: "el modelo nunca se autodeclara verificado".

Lo que hace (sólo la parte mecánica):

1. Recorre todos los docs/seguridad/batch-*/ y extrae candidates de cada findings.json.
2. Extrae las filas de las tablas de hallazgos de 08-auditoria-actual.md.
3. Cruza cada id contra votes.json para derivar el estado de verificación:
   panel unánime, panel mayoría, rechazado por panel, o sin panelear.
   Este dato se computa, no se declara.
4. Marca si existe spec para el hallazgo en plan-fixes.md,
   buscando los encabezados ### Fix #N.
5. Emite una tabla plana única: id | título | severidad_declarada | verificación |
   fuentes | archivo:línea | tiene_spec.
6. Sección aparte al final con los rechazados por panel y su motivo.

Lo que NO hace, y hay que decirlo explícitamente:
   NO deduplica semánticamente ni infiere subsunción. Que #4 "Error details leaked"
   y B8-FINDINGS-AUTH-01 "Backend SAT enquiry error details rendered raw" son el
   mismo defecto no lo resuelve un string match. Eso es trabajo de Opus 5.

Uso:
    python scripts/reconcile_registry.py
    python scripts/reconcile_registry.py --output docs/seguridad/registro-unificado.md
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEGURIDAD_DIR = PROJECT_ROOT / "docs" / "seguridad"
AUDIT_MD = SEGURIDAD_DIR / "08-auditoria-actual.md"
PLAN_FIXES_MD = SEGURIDAD_DIR / "plan-fixes.md"
BATCH_GLOB = "batch-*"

REQUIRED_QUORUM = 2
PANEL_SIZE = 3


# ── Helpers ──────────────────────────────────────────────────────────

def load_json(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def format_line(location: Any) -> str:
    """Convertir line (int, list[int], str) a string legible."""
    if location is None:
        return "-"
    if isinstance(location, list):
        return ",".join(str(ln) for ln in location)
    return str(location)


# ── Extracción de candidates de batches ──────────────────────────────

def extract_batch_candidates(batch_dir: Path) -> list[dict[str, Any]]:
    """Extrae candidates de un findings.json de batch."""
    findings_path = batch_dir / "findings.json"
    if not findings_path.exists():
        return []
    data = load_json(findings_path)
    batch_num = data.get("batch", batch_dir.name)
    candidates = data.get("candidates", [])
    result = []
    for c in candidates:
        fid = c.get("id", "")
        result.append({
            "id": fid,
            "title": c.get("title", ""),
            "severity": c.get("severity", ""),
            "file": c.get("file", ""),
            "line": c.get("line"),
            "source": f"batch-{batch_num}" if isinstance(batch_num, int) else str(batch_num),
            "source_type": "batch",
        })
    return result


# ── Cómputo de verificación desde votes.json ─────────────────────────

def compute_verification(candidate_id: str, votes_data: dict[str, Any]) -> dict[str, Any]:
    """
    Deriva el estado de verificación de un candidato desde votes.json.
    Retorna dict con 'status', 'reason', y datos del panel.
    """
    rounds = votes_data.get("rounds", {})
    round_data = rounds.get(candidate_id)

    if round_data is None:
        return {
            "status": "sin panelear",
            "reason": "Sin ronda de panel — nunca fue evaluado",
            "votes_true": 0,
            "votes_false": 0,
            "reclassified_severity": None,
            "reclassification_reason": None,
        }

    panel = round_data.get("panel", {})
    true_votes = panel.get("true", 0)
    false_votes = panel.get("false", 0)
    voters = panel.get("voters", true_votes + false_votes)

    if voters < PANEL_SIZE:
        return {
            "status": "sin panelear",
            "reason": f"Panel incompleto: {voters}/{PANEL_SIZE} votos",
            "votes_true": true_votes,
            "votes_false": false_votes,
            "reclassified_severity": round_data.get("reclassified_severity"),
            "reclassification_reason": round_data.get("reclassification_reason"),
        }

    if true_votes >= REQUIRED_QUORUM:
        if true_votes == PANEL_SIZE:
            status = "panel unánime"
        else:
            status = "panel mayoría"
        return {
            "status": status,
            "reason": f"{true_votes}/{voters} TRUE_POSITIVE",
            "votes_true": true_votes,
            "votes_false": false_votes,
            "reclassified_severity": None,
            "reclassification_reason": None,
        }
    else:
        reclassified = round_data.get("reclassified_severity", "FALSE_POSITIVE")
        return {
            "status": "rechazado por panel",
            "reason": f"{true_votes}/{voters} TRUE_POSITIVE — reclasificado {reclassified}",
            "votes_true": true_votes,
            "votes_false": false_votes,
            "reclassified_severity": reclassified,
            "reclassification_reason": round_data.get("reclassification_reason", ""),
        }


# ── Extracción de filas de 08-auditoria-actual.md ────────────────────

def extract_audit_rows(audit_path: Path) -> list[dict[str, Any]]:
    """
    Extrae filas de las tablas de hallazgos del documento de auditoría.
    Detecta la severidad por la sección (## CRITICAL, ## HIGH, etc.)
    y parsea cada fila de tabla.
    """
    if not audit_path.exists():
        return []

    text = audit_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    result = []
    current_severity = ""
    in_table = False
    table_columns: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Detectar encabezados de sección de severidad
        section_match = re.match(r"^###\s+(CRITICAL|HIGH|MEDIUM|LOW)\b", stripped)
        if section_match:
            current_severity = section_match.group(1)
            in_table = False
            table_columns = []
            continue

        # Detectar inicio de tabla (línea de headers): | # | Title | ... |
        table_header = re.match(r"^\|\s*#\s*\|", stripped)
        if table_header:
            # Parsear columnas: | # | Titulo | Descripcion | ... |
            columns = [c.strip() for c in stripped.split("|")[1:-1]]
            table_columns = columns
            in_table = True
            continue

        # Detectar separador de tabla (|---|---|...)
        if in_table and re.match(r"^\|[\s\-|]+\|$", stripped):
            continue

        # Procesar fila de tabla
        if in_table and stripped.startswith("|") and stripped.endswith("|"):
            cells_raw = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells_raw) < 2:
                continue

            col_count = len(cells_raw)

            # ── Detectar celdas estructuradas desde la derecha ──
            # Patrones: esfuerzo (ej. "30 min", "2h"), estado ("OPEN", "TRIVIAL"),
            # archivo:línea (celda de backtick-paths o lista corta de files:lines)
            def _is_esfuerzo(cell: str) -> bool:
                return bool(
                    re.match(r"^\d{1,3}\s*min$", cell) or
                    re.match(r"^\d+(\.\d+)?\s*[hm]$", cell)
                )

            def _is_estado(cell: str) -> bool:
                c = re.sub(r"\*\*|`", "", cell).strip()
                return c in (
                    "OPEN", "TRIVIAL", "CLOSED",
                    "OPEN (LOW)", "OPEN (MEDIUM)", "OPEN (HIGH)",
                    "FALSE_POSITIVE", "TRUE_POSITIVE",
                )

            def _is_archivo_cell(cell: str) -> bool:
                """Celda DEDICADA a archivo:línea, no parte de una descripción larga."""
                bare = cell.replace("`", "").strip()
                # Backtick-wrapped paths: la celda entera es paths entre backticks
                if cell.startswith("`"):
                    # Contar qué tanto de la celda son paths backtick-wrapped
                    backticked = re.findall(r"`([^`]+)`", cell)
                    if backticked:
                        joined = " ".join(backticked)
                        has_file = re.search(r"\.\w+\s*:\s*\d+", joined)
                        # Si lo backticked es ≥60% de la celda, es una celda de paths
                        if has_file and len(joined) >= len(bare) * 0.6:
                            return True
                # Celda corta (≤80 chars) que sólo contiene file:line references
                if len(bare) < 80 and re.fullmatch(
                    r"[\w.\-/,:\s\d]+", bare
                ) and re.search(r"\.\w+\s*:\s*\d+", bare):
                    return True
                # Edge cases como "Archivos listados"
                if re.match(r"^Archivos?\s+listados?$", bare, re.IGNORECASE):
                    return True
                # Lista de paths separados por comas, sin texto narrativo
                if "," in bare and len(bare) < 200 and re.search(
                    r"\.\w+\s*:\s*\d+", bare
                ):
                    words = bare.replace(",", " ").split()
                    file_refs = sum(1 for w in words if re.search(r"\.\w+:\d+", w))
                    if file_refs >= len(words) * 0.5:
                        return True
                return False

            tail_structured: list[tuple[int, str]] = []
            for idx in range(col_count - 1, 1, -1):
                cell = cells_raw[idx]
                if _is_esfuerzo(cell):
                    tail_structured.insert(0, (idx, "esfuerzo"))
                elif _is_estado(cell):
                    tail_structured.insert(0, (idx, "estado"))
                elif _is_archivo_cell(cell):
                    tail_structured.insert(0, (idx, "archivo"))
                else:
                    break

            # ── Extraer ID ──
            raw_id = cells_raw[0]
            raw_id = re.sub(r"\*\*", "", raw_id)
            id_nums = re.findall(r"#?(\d+)", raw_id)
            if not id_nums:
                continue
            primary_id = f"#{id_nums[0]}"
            if len(id_nums) > 1:
                primary_id = f"#{'/'.join(id_nums)}"

            # ── Extraer título ──
            title = cells_raw[1] if col_count > 1 else ""
            title = re.sub(r"\*\*(.*?)\*\*", r"\1", title)
            title = re.sub(r"[🆕⚠️🔬]", "", title).strip()
            title = re.sub(r"\s*\(AMPLIADO\)", "", title).strip()
            title = re.sub(r"\s*PREADVERSARIAL\s*", "", title).strip()
            title = re.sub(r"\s+RECALIBRADO\s*", "", title).strip()

            # ── Extraer celdas estructuradas ──
            file_line = "-"
            estado = ""
            esfuerzo = ""

            structured_indices = {kind: idx for idx, kind in tail_structured}
            for idx, kind in tail_structured:
                cell = cells_raw[idx]
                if kind == "archivo":
                    file_line = cell.replace("`", "").strip()
                elif kind == "estado":
                    estado = re.sub(r"\*\*(.*?)\*\*", r"\1", cell).strip()
                elif kind == "esfuerzo":
                    pass  # No usado en la tabla de salida

            result.append({
                "id": primary_id,
                "title": title,
                "severity": current_severity,
                "file_line": file_line,
                "estado": estado,
                "source": "audit",
                "source_type": "audit",
            })

        # Fin de sección de tabla
        if in_table and stripped == "":
            # Línea vacía — potencial fin de tabla, pero puede haber múltiples tablas
            # Sólo salimos si la siguiente línea no es fila de tabla
            in_table = False
            table_columns = []

    return result


# ── Detección de specs en plan-fixes.md ──────────────────────────────

def _parse_spec_ids(raw: str) -> list[str]:
    """Extrae IDs individuales de un string como '16/#34' o '27/#34'."""
    ids = []
    for part in re.split(r"[/,]\s*#?", raw):
        part = part.strip()
        if part:
            ids.append(f"#{part}")
    return ids


def find_fix_specs(plan_fixes_path: Path) -> set[str]:
    """
    Encuentra los IDs de hallazgos que tienen spec de fix.
    Busca encabezados '### Fix #N' y marcadores inline '**#N:' en plan-fixes.md.

    Además verifica (assert) que todos los hallazgos declarados en los títulos
    '## PR N' estén cubiertos por specs detectadas.
    """
    if not plan_fixes_path.exists():
        return set()

    text = plan_fixes_path.read_text(encoding="utf-8")
    specs: set[str] = set()

    # 1. Encabezados ### Fix #N y ### Fix #N/#M
    for match in re.finditer(
        r"^###\s+Fix\s+#(\d+(?:[/,]\s*#?\d+)*)",
        text,
        re.MULTILINE,
    ):
        for spec_id in _parse_spec_ids(match.group(1)):
            specs.add(spec_id)

    # 2. Marcadores inline en negritas: **#N: texto** o **#N/#M: texto**
    for match in re.finditer(
        r"\*\*#(\d+(?:[/,]\s*#?\d+)*):",
        text,
    ):
        for spec_id in _parse_spec_ids(match.group(1)):
            specs.add(spec_id)

    # 3. Assert: cada ## PR N debe tener todos sus hallazgos declarados cubiertos
    pr_declared: dict[str, set[str]] = {}
    for match in re.finditer(
        r"^##\s+PR\s+\d+\s+.*?\(hallazgos\s+(#[^)]+)\)",
        text,
        re.MULTILINE,
    ):
        pr_title = match.group(0).strip()
        raw_ids = match.group(1)
        declared = set()
        for token in re.split(r"[,;]\s*", raw_ids):
            token = token.strip()
            # "parcial" o "resto" no son IDs
            nums = re.findall(r"#(\d+)", token)
            for n in nums:
                declared.add(f"#{n}")
        pr_declared[pr_title] = declared

    all_declared: set[str] = set()
    for declared in pr_declared.values():
        all_declared.update(declared)

    missing = all_declared - specs
    if missing:
        by_pr = []
        for pr_title, declared in pr_declared.items():
            pr_missing = declared & missing
            if pr_missing:
                by_pr.append(f"  {pr_title}\n    Falta(n): {', '.join(sorted(pr_missing))}")
        raise AssertionError(
            f"Hallazgos declarados en títulos ## PR sin spec detectada:\n"
            + "\n".join(by_pr)
            + "\n\nAgrega '### Fix #N: ...' o '**#N: ...**' en plan-fixes.md."
        )

    return specs


# ── Reconciliación principal ─────────────────────────────────────────

def reconcile(seguridad_dir: Path) -> dict[str, Any]:
    """
    Reconciliación mecánica de todos los hallazgos:
    candidates de batches + filas de auditoría → tabla unificada.
    """
    rows: list[dict[str, Any]] = []
    rejected_findings: list[dict[str, Any]] = []

    # 1. Recorrer batches
    batch_dirs = sorted(
        seguridad_dir.glob(BATCH_GLOB),
        key=lambda p: p.name,
    )

    for batch_dir in batch_dirs:
        batch_candidates = extract_batch_candidates(batch_dir)
        votes_path = batch_dir / "votes.json"
        votes_data = load_json(votes_path) if votes_path.exists() else {}

        for candidate in batch_candidates:
            cid = candidate["id"]
            verification = compute_verification(cid, votes_data)

            rows.append({
                "id": cid,
                "title": candidate["title"],
                "severity": candidate["severity"],
                "verification": verification["status"],
                "sources": candidate["source"],
                "file_line": f"{candidate['file']}:{format_line(candidate['line'])}",
                "has_spec": False,  # Se llena después
            })

            if verification["status"] == "rechazado por panel":
                rejected_findings.append({
                    "id": cid,
                    "title": candidate["title"],
                    "severity_proposed": candidate["severity"],
                    "reclassified_severity": verification["reclassified_severity"],
                    "reason": verification["reason"],
                    "reclassification_reason": verification["reclassification_reason"],
                    "source": candidate["source"],
                })

    # 2. Extraer filas de auditoría
    audit_rows = extract_audit_rows(AUDIT_MD)
    for audit_row in audit_rows:
        rows.append({
            "id": audit_row["id"],
            "title": audit_row["title"],
            "severity": audit_row["severity"],
            "verification": audit_row["estado"],
            "sources": audit_row["source"],
            "file_line": audit_row["file_line"],
            "has_spec": False,  # Se llena después
        })

    # 3. Detectar specs en plan-fixes.md
    fix_specs = find_fix_specs(PLAN_FIXES_MD)
    for row in rows:
        row_id = row["id"]
        if row_id in fix_specs:
            row["has_spec"] = True
        # También buscar IDs individuales cuando hay compuestos (#16/#34)
        for part in re.split(r"[/,]", row_id.replace("#", "")):
            part = part.strip()
            if part and f"#{part}" in fix_specs:
                row["has_spec"] = True
                break

    # 4. Check también candidates against audit finding IDs in batch vote rounds
    #    for rejection info — some audit findings were also voted on in batches
    for batch_dir in batch_dirs:
        votes_path = batch_dir / "votes.json"
        if not votes_path.exists():
            continue
        votes_data = load_json(votes_path)
        for audit_row in audit_rows:
            # Look for the audit finding ID in votes also
            vid = audit_row["id"]
            if vid in votes_data.get("rounds", {}):
                verification = compute_verification(vid, votes_data)
                # Update verification if it was ever paneled
                if verification["status"] != "sin panelear":
                    # Update the row
                    for row in rows:
                        if row["id"] == vid and row["sources"] == "audit":
                            row["verification"] = verification["status"]
                            if row["sources"] == "audit":
                                row["sources"] = f"audit, {batch_dir.name}"
                if verification["status"] == "rechazado por panel":
                    # Check not already in rejected
                    if not any(r["id"] == vid for r in rejected_findings):
                        rejected_findings.append({
                            "id": vid,
                            "title": audit_row["title"],
                            "severity_proposed": audit_row["severity"],
                            "reclassified_severity": verification["reclassified_severity"],
                            "reason": verification["reason"],
                            "reclassification_reason": verification["reclassification_reason"],
                            "source": batch_dir.name,
                        })

    return {
        "rows": rows,
        "rejected": rejected_findings,
        "batch_count": len(batch_dirs),
        "total_candidates_from_batches": sum(
            1 for r in rows if r["sources"] != "audit"
        ),
        "total_from_audit": sum(
            1 for r in rows if "audit" in r["sources"]
        ),
        "total_unique": len(rows),
    }


# ── Formateo de salida ───────────────────────────────────────────────

def format_table(rows: list[dict[str, Any]]) -> str:
    """Formatea la tabla plana unificada en Markdown."""
    lines: list[str] = []
    lines.append("## Registro Unificado de Hallazgos de Seguridad")
    lines.append("")
    lines.append("| id | título | severidad | verificación | fuentes | archivo:línea | spec |")
    lines.append("|---|---|---|---|---|---|---|")

    for row in rows:
        rid = row["id"]
        title = row["title"][:72] + ("…" if len(row["title"]) > 72 else "")
        sev = row["severity"]
        ver = row["verification"]
        src = row["sources"]
        fl = row["file_line"]
        spec = "Sí" if row["has_spec"] else "—"

        # Escapar pipes en el título
        title = title.replace("|", "\\|")
        fl = fl.replace("|", "\\|")
        ver = ver.replace("|", "\\|")

        lines.append(f"| {rid} | {title} | {sev} | {ver} | {src} | {fl} | {spec} |")

    return "\n".join(lines)


def format_rejected(rejected: list[dict[str, Any]]) -> str:
    """Formatea la sección de hallazgos rechazados por panel."""
    if not rejected:
        return "\n\n*Sin hallazgos rechazados por panel.*\n"

    lines: list[str] = []
    lines.append("")
    lines.append("## Hallazgos Rechazados por Panel Adversarial")
    lines.append("")
    lines.append(
        "Estos hallazgos fueron evaluados por el panel de 3 votantes y recibieron "
        "<2 votos TRUE_POSITIVE. No se eliminan del registro — si desaparecen del "
        "código, el próximo scan los vuelve a encontrar y se re-triagean."
    )
    lines.append("")
    lines.append("| id | título | severidad propuesta | reclasificado | motivo del panel |")
    lines.append("|---|---|---|---|---|")

    for r in rejected:
        rid = r["id"]
        title = r["title"][:64] + ("…" if len(r["title"]) > 64 else "")
        sev_prop = r.get("severity_proposed", "")
        reclassified = r.get("reclassified_severity", "")
        reason = r.get("reclassification_reason") or r.get("reason", "")
        reason = reason[:100] + ("…" if len(reason) > 100 else "")

        title = title.replace("|", "\\|")
        reason = reason.replace("|", "\\|")

        lines.append(f"| {rid} | {title} | {sev_prop} | {reclassified} | {reason} |")

    return "\n".join(lines)


def format_summary(stats: dict[str, Any]) -> str:
    """Formatea el resumen al inicio."""
    return (
        f"> **Batches procesados:** {stats['batch_count']}\n"
        f"> **Candidates de batches:** {stats['total_candidates_from_batches']}\n"
        f"> **Filas de auditoría:** {stats['total_from_audit']}\n"
        f"> **Total en registro:** {stats['total_unique']}\n"
        f"> **Rechazados por panel:** {len(stats['rejected'])}\n"
    )


# ── Main ─────────────────────────────────────────────────────────────

def main():
    output_path = None
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--output":
        output_path = Path(args[1])
    elif len(args) == 1 and not args[0].startswith("-"):
        output_path = Path(args[0])

    if not AUDIT_MD.exists():
        print(
            f"ADVERTENCIA: {AUDIT_MD} no existe. Sólo se procesarán batches.",
            file=sys.stderr,
        )

    if not PLAN_FIXES_MD.exists():
        print(
            f"ADVERTENCIA: {PLAN_FIXES_MD} no existe. Sin detección de specs.",
            file=sys.stderr,
        )

    result = reconcile(SEGURIDAD_DIR)

    rows = sorted(result["rows"], key=lambda r: (
        # Orden: batches primero (por id), luego audit
        0 if r["sources"] != "audit" else 1,
        r["id"],
    ))

    # Ordenar rechazados por id
    rejected = sorted(result["rejected"], key=lambda r: r["id"])

    output = []
    output.append("# Registro Unificado de Hallazgos — cfdi_suite")
    output.append("")
    output.append(
        "> Generado por `scripts/reconcile_registry.py` — "
        "código determinista, sin LLM, re-ejecutable."
    )
    output.append(format_summary({
        **result,
        "rejected": rejected,
    }))
    output.append(format_table(rows))
    output.append(format_rejected(rejected))
    output.append("")

    full_output = "\n".join(output)

    if output_path:
        output_path.write_text(full_output, encoding="utf-8")
        print(f"Registro escrito en {output_path}")
    else:
        print(full_output)


if __name__ == "__main__":
    main()
