#!/usr/bin/env python3
"""
verify.py — Script determinista de verificación para el pipeline de seguridad.

Lee findings.json, votes.json, y coverage.json del batch especificado y calcula
verification.status. NUNCA usa un LLM — es código plano que cuenta votos.
El modelo nunca se autodeclara "verificado".

Uso:
    python verify.py docs/seguridad/batch-4
    python verify.py docs/seguridad/batch-4 --json   # salida JSON
"""

import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_QUORUM = 2  # ≥2 de 3 votos true para que un finding sobreviva
PANEL_SIZE = 3


def load_json(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def verify(batch_dir: Path) -> dict[str, Any]:
    findings = load_json(batch_dir / "findings.json")
    votes = load_json(batch_dir / "votes.json")
    coverage = load_json(batch_dir / "coverage.json")

    candidates = findings.get("candidates", [])
    rounds = votes.get("rounds", {})

    verified_findings: list[dict] = []
    refuted_findings: list[dict] = []
    unverified_findings: list[dict] = []

    for candidate in candidates:
        cid = candidate["id"]
        round_data = rounds.get(cid)

        if round_data is None:
            unverified_findings.append({
                "id": cid,
                "reason": "Sin ronda de panel — nunca fue evaluado"
            })
            continue

        panel = round_data.get("panel", {})
        true_votes = panel.get("true", 0)
        false_votes = panel.get("false", 0)
        total_votes = true_votes + false_votes

        if total_votes < PANEL_SIZE:
            unverified_findings.append({
                "id": cid,
                "reason": f"Panel incompleto: {total_votes}/{PANEL_SIZE} votos"
            })
            continue

        quorum_reached = true_votes >= REQUIRED_QUORUM

        if quorum_reached:
            confidence = "high" if true_votes == PANEL_SIZE else "medium"
            verified_findings.append({
                "id": cid,
                "severity": candidate["severity"],
                "confidence": confidence,
                "votes": {"true": true_votes, "false": false_votes}
            })
        else:
            refuted_findings.append({
                "id": cid,
                "severity_proposed": candidate["severity"],
                "reclassified_severity": round_data.get("reclassified_severity", "FALSE_POSITIVE"),
                "votes": {"true": true_votes, "false": false_votes}
            })

    # ── Determinar status ──────────────────────────────────────────
    total_candidates = len(candidates)
    paneled = len(verified_findings) + len(refuted_findings)
    unpaneled = len(unverified_findings)

    if unpaneled > 0:
        status = "unverified"
        reason = (
            f"{unpaneled} candidato(s) sin panel completo de {PANEL_SIZE} votos. "
            f"Panelados: {paneled}/{total_candidates}."
        )
    elif total_candidates == 0:
        status = "verified"
        reason = "Sin candidatos que verificar. Cobertura confirmada en coverage.json."
    else:
        status = "verified"
        reason = (
            f"{total_candidates} candidato(s) evaluado(s) por panel completo de {PANEL_SIZE} votos. "
            f"Sobrevivieron: {len(verified_findings)}. Refutados: {len(refuted_findings)}."
        )

    return {
        "batch": findings.get("batch"),
        "date": findings.get("date"),
        "verification": {
            "status": status,
            "reason": reason,
            "candidates_total": total_candidates,
            "candidates_paneled": paneled,
            "candidates_unpaneled": unpaneled,
            "panel_rounds_completed": len(rounds),
            "findings_verified": len(verified_findings),
            "findings_refuted": len(refuted_findings),
            "confirmed_existing": len(findings.get("confirmed_existing", [])),
            "clean_components": len(findings.get("clean_components", [])),
            "quorum_rule": f">={REQUIRED_QUORUM}/{PANEL_SIZE} true votes",
            "verified_findings": verified_findings if verified_findings else None,
            "refuted_findings": refuted_findings if refuted_findings else None,
            "unverified_findings": unverified_findings if unverified_findings else None
        }
    }


def main():
    if len(sys.argv) < 2:
        print("Uso: python verify.py <batch_dir> [--json]", file=sys.stderr)
        sys.exit(1)

    batch_dir = Path(sys.argv[1])
    as_json = "--json" in sys.argv

    required = ["findings.json", "votes.json", "coverage.json"]
    missing = [f for f in required if not (batch_dir / f).exists()]
    if missing:
        print(f"ERROR: Faltan archivos en {batch_dir}: {missing}", file=sys.stderr)
        sys.exit(2)

    result = verify(batch_dir)

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*60}")
        print(f"VERIFICACIÓN — Batch {result['batch']} ({result['date']})")
        print(f"{'='*60}")
        v = result["verification"]
        print(f"Status:     {v['status'].upper()}")
        print(f"Razón:      {v['reason']}")
        print(f"Regla:      {v['quorum_rule']}")
        print(f"")
        print(f"Candidatos: {v['candidates_total']}")
        print(f"Panelados:  {v['candidates_paneled']}")
        print(f"No panel:   {v['candidates_unpaneled']}")
        print(f"Verificados:{v['findings_verified']}")
        print(f"Refutados:  {v['findings_refuted']}")
        print(f"Confirmados:{v['confirmed_existing']} (hallazgos existentes)")
        print(f"Limpios:    {v['clean_components']} (componentes)")
        print(f"{'='*60}")

        if v["verified_findings"]:
            print("\n✅ FINDINGS VERIFICADOS:")
            for f in v["verified_findings"]:
                print(f"  {f['id']}: {f['severity']} (confianza: {f['confidence']}) — {f['votes']}")

        if v["refuted_findings"]:
            print("\n❌ FINDINGS REFUTADOS:")
            for f in v["refuted_findings"]:
                print(f"  {f['id']}: propuesto {f['severity_proposed']} → {f['reclassified_severity']} — {f['votes']}")

        if v["unverified_findings"]:
            print("\n⚠️  FINDINGS SIN VERIFICAR:")
            for f in v["unverified_findings"]:
                print(f"  {f['id']}: {f['reason']}")

        print()

    sys.exit(0 if result["verification"]["status"] == "verified" else 1)


if __name__ == "__main__":
    main()
