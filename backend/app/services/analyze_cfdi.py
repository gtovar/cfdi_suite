from __future__ import annotations

from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal
from time import perf_counter
from typing import Any
from uuid import uuid4

from ..constants import MAX_CONCEPT_DIFFS_SHOWN, ROUNDING_TOLERANCE, TAX_RATE_PRECISION
from ..contracts import AnalysisIssue, AnalyzeCfdiMeta, AnalyzeCfdiResponse
from ..observability import record_analyze_cfdi_error, record_analyze_cfdi_request
from ..policy import (
    FALLBACK_REASON_PROVIDER_RUNTIME_FAILURE,
    PUBLIC_MESSAGE_PLATFORM_RUNTIME_FAILED,
    PUBLIC_MESSAGE_PROVIDER_PARSE_FAILED,
)
from ..providers.base import CfdiAnalysisProvider, ProviderIssue, ProviderResult
from ..providers.current_ts import (
    CurrentTsProviderError,
    default_current_ts_provider,
)
from ..providers.python_satcfdi import (
    PythonSatcfdiProviderError,
    default_python_satcfdi_provider,
)

_IMP_NOMBRES = {"001": "ISR", "002": "IVA", "003": "IEPS"}

_HEADER_CATALOG_FIELDS = [
    ("usoCfdi", "usoCfdiDescripcion", "catalog-uso-cfdi", "Uso de CFDI", "c_UsoCFDI"),
    ("metodoPago", "metodoPagoDescripcion", "catalog-metodo-pago", "Método de pago", "c_MetodoPago"),
    ("formaPago", "formaPagoDescripcion", "catalog-forma-pago", "Forma de pago", "c_FormaPago"),
    ("moneda", "monedaDescripcion", "catalog-moneda", "Moneda", "c_Moneda"),
]


# ── Public entry point ────────────────────────────────────────────────────────


def run_analyze_cfdi(
    xml: str,
    provider: CfdiAnalysisProvider = default_python_satcfdi_provider,
    fallback_provider: CfdiAnalysisProvider | None = default_current_ts_provider,
) -> AnalyzeCfdiResponse:
    started_at = perf_counter()
    request_id = str(uuid4())

    try:
        provider_result, effective_provider = _resolve_provider_result(
            xml=xml,
            provider=provider,
            fallback_provider=fallback_provider,
        )
    except (PythonSatcfdiProviderError, CurrentTsProviderError):
        response = AnalyzeCfdiResponse(
            profile="unknown",
            cfdi=None,
            ingresoRows=[],
            pagoRows=[],
            issues=[
                AnalysisIssue(
                    code="ENGINE_RUNTIME_FAILED",
                    message=PUBLIC_MESSAGE_PLATFORM_RUNTIME_FAILED,
                    stage="parse",
                    fatal=True,
                )
            ],
            meta=_build_meta(
                provider=provider,
                request_id=request_id,
                degraded=False,
                started_at=started_at,
                provider_result=None,
            ),
        )
        record_analyze_cfdi_error(response, http_status=200)
        return response

    profile = provider_result.document_signal.profile
    issues = _build_issues(provider_result)
    cfdi = _normalize_cfdi(provider_result.structured_cfdi)
    degraded = cfdi is not None and any(not issue.fatal for issue in issues)

    response = AnalyzeCfdiResponse(
        profile=profile,
        cfdi=cfdi,
        ingresoRows=provider_result.ingreso_rows,
        ingresoRowHeader=provider_result.ingreso_row_header,
        pagoRows=provider_result.pago_rows,
        issues=issues,
        meta=_build_meta(
            provider=effective_provider,
            request_id=request_id,
            degraded=degraded,
            started_at=started_at,
            provider_result=provider_result,
        ),
    )
    if any(issue.fatal for issue in response.issues):
        record_analyze_cfdi_error(response, http_status=200)
    else:
        record_analyze_cfdi_request(response, http_status=200)
    return response


# ── Provider orchestration ────────────────────────────────────────────────────


def _build_issues(provider_result: ProviderResult) -> list[AnalysisIssue]:
    issues: list[AnalysisIssue] = []
    for provider_issue in provider_result.provider_issues:
        mapped = _map_provider_issue(provider_issue)
        if mapped is not None:
            issues.append(mapped)
    return issues


def _build_meta(
    provider: CfdiAnalysisProvider,
    request_id: str,
    degraded: bool,
    started_at: float,
    provider_result: ProviderResult | None,
) -> AnalyzeCfdiMeta:
    elapsed_ms = max(0, round((perf_counter() - started_at) * 1000))
    warnings = list(provider_result.diagnostics.warning_messages) if provider_result is not None else []
    fallback_reason = None
    if provider_result is not None and provider.mode == "fallback":
        fallback_reason = provider_result.diagnostics.fallback_reason

    return AnalyzeCfdiMeta(
        provider=provider.name,
        providerMode=provider.mode,
        degraded=degraded,
        requestId=request_id,
        providerVersion=provider.version,
        warnings=warnings,
        timingMs=elapsed_ms,
        fallbackReason=fallback_reason,
    )


def _resolve_provider_result(
    xml: str,
    provider: CfdiAnalysisProvider,
    fallback_provider: CfdiAnalysisProvider | None,
) -> tuple[ProviderResult, CfdiAnalysisProvider]:
    try:
        primary_result = provider.analyze(xml)
    except (PythonSatcfdiProviderError, CurrentTsProviderError):
        if fallback_provider is None:
            raise
        fallback_reason = FALLBACK_REASON_PROVIDER_RUNTIME_FAILURE
        fallback_result = fallback_provider.analyze(xml)
        return _with_fallback_reason(fallback_result, fallback_reason), fallback_provider

    if not _should_use_fallback(primary_result) or fallback_provider is None:
        return primary_result, provider

    fallback_reason = (
        primary_result.diagnostics.fallback_reason or FALLBACK_REASON_PROVIDER_RUNTIME_FAILURE
    )
    fallback_result = fallback_provider.analyze(xml)
    return _with_fallback_reason(fallback_result, fallback_reason), fallback_provider


def _should_use_fallback(provider_result: ProviderResult) -> bool:
    if provider_result.diagnostics.fallback_eligible:
        return True
    return any(issue.code == "runtime_failed" for issue in provider_result.provider_issues)


def _with_fallback_reason(
    provider_result: ProviderResult,
    fallback_reason: str,
) -> ProviderResult:
    diagnostics = replace(provider_result.diagnostics, fallback_reason=fallback_reason)
    return replace(provider_result, diagnostics=diagnostics)


def _map_provider_issue(provider_issue: ProviderIssue) -> AnalysisIssue | None:
    if provider_issue.code == "parse_failed":
        return AnalysisIssue(
            code="CFDI_PARSE_FAILED",
            message=provider_issue.public_message or PUBLIC_MESSAGE_PROVIDER_PARSE_FAILED,
            stage=provider_issue.stage,
            fatal=True,
        )

    if provider_issue.code == "runtime_failed":
        return AnalysisIssue(
            code="ENGINE_RUNTIME_FAILED",
            message=provider_issue.public_message or PUBLIC_MESSAGE_PLATFORM_RUNTIME_FAILED,
            stage=provider_issue.stage,
            fatal=True,
        )

    if provider_issue.code == "unsupported_capability":
        return AnalysisIssue(
            code="UNSUPPORTED_CAPABILITY",
            message=provider_issue.public_message or provider_issue.message,
            stage=provider_issue.stage,
            fatal=False,
        )

    if provider_issue.code in {"rows_unavailable", "findings_unavailable"}:
        return AnalysisIssue(
            code="RESULT_DEGRADED",
            message=provider_issue.public_message or provider_issue.message,
            stage=provider_issue.stage,
            fatal=False,
        )

    return None


# ── CFDI normalization: orchestrator ─────────────────────────────────────────


def _normalize_cfdi(source: dict[str, Any] | None) -> dict[str, Any] | None:
    if not source:
        return None

    conceptos = _process_concepts(source)
    impuestos_globales = _process_global_taxes(source)
    subtotal = float(source.get("subtotal", 0) or 0)
    descuento = float(source.get("descuento", 0) or 0)
    total = float(source.get("total", 0) or 0)
    subtotal_calculado, total_calculado = _calculate_totals(conceptos, descuento)
    tax_audit_groups = _build_tax_audit_groups(conceptos, impuestos_globales)

    findings: list[dict[str, Any]] = []
    hallazgos: list[str] = []
    impacted: list[int] = []

    math_f, math_h, math_i = _collect_math_findings(
        conceptos, subtotal, subtotal_calculado, total, total_calculado
    )
    findings += math_f
    hallazgos += math_h
    for i in math_i:
        if i not in impacted:
            impacted.append(i)

    concept_f, concept_i = _collect_concept_diffs(conceptos)
    findings += concept_f
    for i in concept_i:
        if i not in impacted:
            impacted.append(i)

    audit_f, audit_i = _collect_tax_audit_group_findings(tax_audit_groups)
    findings += audit_f
    for i in audit_i:
        if i not in impacted:
            impacted.append(i)

    rounding_f, rounding_h = _collect_sat_rounding_findings(conceptos, impuestos_globales)
    findings += rounding_f
    hallazgos += rounding_h

    findings += _collect_catalog_findings(source)

    findings = _deduplicate_findings(findings)
    impacted.sort()
    verdict = _build_verdict(findings)

    support_lines = [verdict["title"], verdict["summary"]] + [
        f"{f['title']}: {f['summary']}" for f in findings[:5]
    ]

    return {
        "version": source.get("version", ""),
        "fecha": source.get("fecha", ""),
        "uuid": source.get("uuid", ""),
        "emisor": source.get("emisor", ""),
        "receptor": source.get("receptor", ""),
        "subtotal": subtotal,
        "descuento": descuento,
        "total": total,
        "conceptos": conceptos,
        "impuestosGlobales": impuestos_globales,
        "subtotalCalculado": subtotal_calculado,
        "totalCalculado": total_calculado,
        "hallazgos": hallazgos,
        "findings": findings,
        "impactedConceptIndexes": impacted,
        "taxAuditGroups": tax_audit_groups,
        "verdict": verdict,
        "supportText": "\n".join(support_lines),
    }


# ── CFDI normalization: data builders ────────────────────────────────────────


def _map_tax_entry(tax: dict[str, Any]) -> dict[str, Any]:
    base = float(tax.get("base", 0) or 0)
    tasa = float(tax.get("tasaOCuota", 0) or 0)
    importe_tax = float(tax.get("importe", 0) or 0)
    tipo_factor = tax.get("tipoFactor", "")
    importe_calculado = round(base * tasa, TAX_RATE_PRECISION) if tipo_factor == "Tasa" else 0
    diferencia = abs(importe_tax - (base * tasa)) if tipo_factor == "Tasa" else 0
    return {
        "tipo": tax.get("tipo", ""),
        "impuesto": tax.get("impuesto", ""),
        "base": base,
        "tipoFactor": tipo_factor,
        "tasaOCuota": tasa,
        "importe": importe_tax,
        "importeCalculado": importe_calculado,
        "diferencia": diferencia,
    }


def _process_concepts(source: dict[str, Any]) -> list[dict[str, Any]]:
    conceptos = []
    for concept in source.get("conceptos", []):
        cantidad = float(concept.get("cantidad", 0) or 0)
        valor_unitario = float(concept.get("valorUnitario", 0) or 0)
        importe = float(concept.get("importe", 0) or 0)
        conceptos.append({
            "descripcion": concept.get("descripcion", ""),
            "cantidad": cantidad,
            "valorUnitario": valor_unitario,
            "importe": importe,
            "importeCalculado": round(cantidad * valor_unitario, TAX_RATE_PRECISION),
            "diferencia": abs(importe - (cantidad * valor_unitario)),
            "claveProdServ": concept.get("claveProdServ", ""),
            "impuestos": [_map_tax_entry(tax) for tax in concept.get("impuestos", [])],
        })
    return conceptos


def _process_global_taxes(source: dict[str, Any]) -> list[dict[str, Any]]:
    return [_map_tax_entry(tax) for tax in source.get("impuestosGlobales", [])]


def _calculate_totals(
    conceptos: list[dict[str, Any]],
    descuento: float,
) -> tuple[float, float]:
    subtotal_calculado = _round_currency(sum(c["importe"] for c in conceptos))
    traslados_sum = _round_currency(sum(
        imp["importe"] for c in conceptos for imp in c["impuestos"] if imp["tipo"] == "Traslado"
    ))
    retenciones_sum = _round_currency(sum(
        imp["importe"] for c in conceptos for imp in c["impuestos"] if imp["tipo"] == "Retencion"
    ))
    total_calculado = _round_currency(
        subtotal_calculado - _round_currency(descuento) + traslados_sum - retenciones_sum
    )
    return subtotal_calculado, total_calculado


def _build_tax_audit_groups(
    conceptos: list[dict[str, Any]],
    impuestos_globales: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tax_group_map: dict[str, dict[str, Any]] = {}
    for i, concepto in enumerate(conceptos):
        for imp in concepto["impuestos"]:
            key = f"{imp['impuesto']}|{imp['tipoFactor']}|{imp['tasaOCuota']}"
            grp = tax_group_map.setdefault(key, {
                "key": key, "impuesto": imp["impuesto"], "tipoFactor": imp["tipoFactor"],
                "tasaOCuota": imp["tasaOCuota"], "importeDetalle": 0.0,
                "importeAgrupado": 0.0, "diferencia": 0.0, "conceptos": [],
            })
            grp["importeDetalle"] += imp["importe"]
            if i not in grp["conceptos"]:
                grp["conceptos"].append(i)

    for imp in impuestos_globales:
        key = f"{imp['impuesto']}|{imp['tipoFactor']}|{imp['tasaOCuota']}"
        grp = tax_group_map.setdefault(key, {
            "key": key, "impuesto": imp["impuesto"], "tipoFactor": imp["tipoFactor"],
            "tasaOCuota": imp["tasaOCuota"], "importeDetalle": 0.0,
            "importeAgrupado": 0.0, "diferencia": 0.0, "conceptos": [],
        })
        grp["importeAgrupado"] += imp["importe"]

    return sorted(
        [
            dict(g, diferencia=_round_currency(g["importeAgrupado"]) - _round_currency(g["importeDetalle"]))
            for g in tax_group_map.values()
        ],
        key=lambda g: abs(g["diferencia"]),
        reverse=True,
    )


# ── CFDI normalization: diagnostic collectors ─────────────────────────────────


def _collect_math_findings(
    conceptos: list[dict[str, Any]],
    subtotal: float,
    subtotal_calculado: float,
    total: float,
    total_calculado: float,
) -> tuple[list[dict[str, Any]], list[str], list[int]]:
    findings: list[dict[str, Any]] = []
    hallazgos: list[str] = []
    impacted: list[int] = []

    for i, concepto in enumerate(conceptos):
        for j, imp in enumerate(concepto["impuestos"]):
            if imp["tipoFactor"] == "Tasa":
                calc = _round_currency(_round_currency(imp["base"]) * _round_rate(imp["tasaOCuota"]))
                diff = _diff_currency(imp["importe"], calc)
                if diff != 0:
                    title = f"Traslado inconsistente en concepto {i + 1}"
                    summary = f"XML declara {imp['importe']:.2f} y el cálculo da {calc:.2f}."
                    findings.append({
                        "id": f"math-LINE_TAX_MISMATCH-concept-{i}-{j}",
                        "severity": "critical",
                        "title": title,
                        "summary": summary,
                    })
                    hallazgos.append(f"{title}: {summary}")
                    if i not in impacted:
                        impacted.append(i)

    subtotal_diff = _diff_currency(subtotal, subtotal_calculado)
    if subtotal_diff != 0:
        title = "Discrepancia en subtotal"
        summary = f"XML declara {subtotal:.2f} y el cálculo da {subtotal_calculado:.2f}."
        findings.append({
            "id": "math-SUBTOTAL_MISMATCH-comprobante-na-na",
            "severity": "critical",
            "title": title,
            "summary": summary,
        })
        hallazgos.append(f"{title}: {summary}")

    total_diff = _diff_currency(total, total_calculado)
    if total_diff != 0:
        title = "Discrepancia en total"
        summary = f"XML declara {total:.2f} y el cálculo da {total_calculado:.2f}."
        findings.append({
            "id": "math-TOTAL_MISMATCH-comprobante-na-na",
            "severity": "critical",
            "title": title,
            "summary": summary,
        })
        hallazgos.append(f"{title}: {summary}")

    return findings, hallazgos, impacted


def _collect_concept_diffs(
    conceptos: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[int]]:
    findings: list[dict[str, Any]] = []
    impacted: list[int] = []
    concept_diffs = sorted(
        [(i, c) for i, c in enumerate(conceptos) if c["diferencia"] != 0],
        key=lambda x: x[1]["diferencia"],
        reverse=True,
    )[:MAX_CONCEPT_DIFFS_SHOWN]
    for i, c in concept_diffs:
        sev = "critical" if c["diferencia"] > ROUNDING_TOLERANCE else "warning"
        title = f"Importe inconsistente en concepto {i + 1}"
        summary = f"{c['descripcion']}: XML {c['importe']:.2f} vs cálculo {c['importeCalculado']:.2f}."
        findings.append({"id": f"concept-{i}", "severity": sev, "title": title, "summary": summary})
        if i not in impacted:
            impacted.append(i)
    return findings, impacted


def _collect_tax_audit_group_findings(
    tax_audit_groups: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[int]]:
    findings: list[dict[str, Any]] = []
    impacted: list[int] = []
    for grp in tax_audit_groups:
        if abs(grp["diferencia"]) > 0:
            sev = "critical" if abs(grp["diferencia"]) > ROUNDING_TOLERANCE else "warning"
            tasa_pct = grp["tasaOCuota"] * 100
            title = f"Diferencia en traslado {grp['impuesto']} {tasa_pct:.2f}%"
            summary = f"Detalle {grp['importeDetalle']:.2f} vs agrupado {grp['importeAgrupado']:.2f}."
            findings.append({"id": f"tax-group-{grp['key']}", "severity": sev, "title": title, "summary": summary})
            for idx in grp["conceptos"]:
                if idx not in impacted:
                    impacted.append(idx)
    return findings, impacted


def _collect_sat_rounding_findings(
    conceptos: list[dict[str, Any]],
    impuestos_globales: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    hallazgos: list[str] = []

    sat_acc: dict[str, dict[str, Decimal]] = {}
    for concepto in conceptos:
        for imp in concepto["impuestos"]:
            if imp["tipo"] != "Traslado":
                continue
            key = f"{imp['impuesto']}|{imp['tipoFactor']}|{imp['tasaOCuota']}"
            if key not in sat_acc:
                sat_acc[key] = {"base": Decimal(0), "importe": Decimal(0)}
            sat_acc[key]["base"] += Decimal(str(imp["base"]))
            sat_acc[key]["importe"] += Decimal(str(imp["importe"]))

    _q = Decimal("0.01")
    for imp in impuestos_globales:
        if imp["tipo"] != "Traslado":
            continue
        key = f"{imp['impuesto']}|{imp['tipoFactor']}|{imp['tasaOCuota']}"
        if key not in sat_acc:
            continue
        base_esp = sat_acc[key]["base"].quantize(_q, rounding=ROUND_HALF_UP)
        imp_esp = sat_acc[key]["importe"].quantize(_q, rounding=ROUND_HALF_UP)
        base_xml = Decimal(str(imp["base"]))
        imp_xml = Decimal(str(imp["importe"]))
        nombre = _IMP_NOMBRES.get(imp["impuesto"], imp["impuesto"])
        tasa_pct = imp["tasaOCuota"] * 100

        if base_xml != base_esp:
            diff = float(base_xml - base_esp)
            title = f"Error de redondeo en base de {nombre} {tasa_pct:.0f}%"
            summary = (
                f"La base declarada en el XML es {base_xml:.2f}, "
                f"pero la suma de las bases de todos los renglones, redondeada correctamente, da {base_esp:.2f}. "
                f"Diferencia de {abs(diff):.2f}."
            )
            findings.append({
                "id": f"sat-rounding-base-{key}", "severity": "critical",
                "title": title, "summary": summary,
                "declared": f"{base_xml:.2f}", "expected": f"{base_esp:.2f}",
            })
            hallazgos.append(f"{title}: {summary}")

        if imp_xml != imp_esp:
            diff = float(imp_xml - imp_esp)
            title = f"Error de redondeo en {nombre} {tasa_pct:.0f}%"
            summary = (
                f"El XML declara {imp_xml:.2f} de {nombre} {tasa_pct:.0f}%, "
                f"pero al sumar los importes de todos los renglones y redondear correctamente (regla SAT), "
                f"el resultado es {imp_esp:.2f}. Diferencia de {abs(diff):.2f}."
            )
            findings.append({
                "id": f"sat-rounding-imp-{key}", "severity": "critical",
                "title": title, "summary": summary,
                "declared": f"{imp_xml:.2f}", "expected": f"{imp_esp:.2f}",
            })
            hallazgos.append(f"{title}: {summary}")

    return findings, hallazgos


def _collect_catalog_findings(source: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    claves_invalidas: dict[str, list[int]] = {}
    for i, concept in enumerate(source.get("conceptos", [])):
        desc = concept.get("claveProdServDescripcion")
        code = concept.get("claveProdServ", "")
        if desc == "No existe en el catálogo" and code:
            claves_invalidas.setdefault(code, []).append(i)

    for invalid_code, indexes in claves_invalidas.items():
        count = len(indexes)
        findings.append({
            "id": f"catalog-clave-prod-serv-{invalid_code}",
            "severity": "warning",
            "title": f"Clave de producto/servicio inválida: {invalid_code}",
            "summary": (
                f"{count} concepto(s) usan la clave SAT '{invalid_code}' "
                f"que no existe en el catálogo oficial del SAT."
            ),
            "declared": invalid_code,
        })

    for code_field, desc_field, prefix, label, catalog in _HEADER_CATALOG_FIELDS:
        code = source.get(code_field, "")
        desc = source.get(desc_field)
        if desc == "No existe en el catálogo" and code:
            findings.append({
                "id": f"{prefix}-{code}",
                "severity": "warning",
                "title": f"{label} inválido: {code}",
                "summary": f"El código '{code}' no existe en el catálogo SAT {catalog}.",
                "declared": code,
            })

    return findings


def _deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for f in findings:
        k = f"{f['severity']}|{f['title']}|{f['summary']}"
        if k not in seen:
            seen[k] = f
    return sorted(
        seen.values(),
        key=lambda f: (0 if f["severity"] == "critical" else 1, f["title"]),
    )


def _build_verdict(findings: list[dict[str, Any]]) -> dict[str, str]:
    n_critical = sum(1 for f in findings if f["severity"] == "critical")
    n_warning = sum(1 for f in findings if f["severity"] == "warning")
    if n_critical > 0:
        return {
            "status": "critical",
            "title": "CFDI con discrepancias críticas",
            "summary": f"Se detectaron {n_critical} hallazgo(s) críticos que requieren revisión operativa.",
        }
    if n_warning > 0:
        return {
            "status": "review",
            "title": "CFDI requiere revisión",
            "summary": f"Hay {n_warning} alerta(s) menores, probablemente asociadas a redondeo o captura.",
        }
    return {
        "status": "clean",
        "title": "Sin discrepancias detectadas",
        "summary": "Los importes principales cuadran con el cálculo actual.",
    }


# ── Math helpers ──────────────────────────────────────────────────────────────


def _round_currency(v: float) -> float:
    """Replica JS Math.round((v + ε) * 100) / 100"""
    return int((v + 2.220446049250313e-16) * 100 + 0.5) / 100


def _round_rate(v: float) -> float:
    """Replica JS Math.round((v + ε) * 1_000_000) / 1_000_000"""
    return int((v + 2.220446049250313e-16) * 1_000_000 + 0.5) / 1_000_000


def _diff_currency(declared: float, calculated: float) -> float:
    """Replica diffCurrency de diagnoseCfdiMath.ts"""
    return _round_currency(_round_currency(declared) - _round_currency(calculated))
