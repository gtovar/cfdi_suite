from __future__ import annotations

from dataclasses import replace
from time import perf_counter
from typing import Any
from uuid import uuid4

from ..contracts import AnalysisIssue, AnalyzeCfdiMeta, AnalyzeCfdiResponse
from ..observability import record_analyze_cfdi_error, record_analyze_cfdi_request
from ..providers.base import CfdiAnalysisProvider, ProviderIssue, ProviderResult
from ..providers.current_ts import (
    CurrentTsProviderError,
    default_current_ts_provider,
)
from ..providers.python_satcfdi import (
    PythonSatcfdiProviderError,
    default_python_satcfdi_provider,
)
from ..policy import (
    FALLBACK_REASON_PROVIDER_RUNTIME_FAILURE,
    PUBLIC_MESSAGE_PLATFORM_RUNTIME_FAILED,
    PUBLIC_MESSAGE_PROVIDER_PARSE_FAILED,
)


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
    diagnostics = replace(
        provider_result.diagnostics,
        fallback_reason=fallback_reason,
    )
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


def _normalize_cfdi(source: dict[str, Any] | None) -> dict[str, Any] | None:
    if not source:
        return None

    conceptos = []
    for concept in source.get("conceptos", []):
        cantidad = float(concept.get("cantidad", 0) or 0)
        valor_unitario = float(concept.get("valorUnitario", 0) or 0)
        importe = float(concept.get("importe", 0) or 0)
        impuestos = []

        for tax in concept.get("impuestos", []):
            base = float(tax.get("base", 0) or 0)
            tasa = float(tax.get("tasaOCuota", 0) or 0)
            importe_tax = float(tax.get("importe", 0) or 0)
            tipo_factor = tax.get("tipoFactor", "")
            importe_calculado = round(base * tasa, 6) if tipo_factor == "Tasa" else 0
            diferencia = abs(importe_tax - (base * tasa)) if tipo_factor == "Tasa" else 0
            impuestos.append(
                {
                    "tipo": tax.get("tipo", ""),
                    "impuesto": tax.get("impuesto", ""),
                    "base": base,
                    "tipoFactor": tipo_factor,
                    "tasaOCuota": tasa,
                    "importe": importe_tax,
                    "importeCalculado": importe_calculado,
                    "diferencia": diferencia,
                }
            )

        conceptos.append(
            {
                "descripcion": concept.get("descripcion", ""),
                "cantidad": cantidad,
                "valorUnitario": valor_unitario,
                "importe": importe,
                "importeCalculado": round(cantidad * valor_unitario, 6),
                "diferencia": abs(importe - (cantidad * valor_unitario)),
                "claveProdServ": concept.get("claveProdServ", ""),
                "impuestos": impuestos,
            }
        )

    impuestos_globales = []
    for tax in source.get("impuestosGlobales", []):
        base = float(tax.get("base", 0) or 0)
        tasa = float(tax.get("tasaOCuota", 0) or 0)
        importe_tax = float(tax.get("importe", 0) or 0)
        tipo_factor = tax.get("tipoFactor", "")
        importe_calculado = round(base * tasa, 6) if tipo_factor == "Tasa" else 0
        diferencia = abs(importe_tax - (base * tasa)) if tipo_factor == "Tasa" else 0
        impuestos_globales.append(
            {
                "tipo": tax.get("tipo", ""),
                "impuesto": tax.get("impuesto", ""),
                "base": base,
                "tipoFactor": tipo_factor,
                "tasaOCuota": tasa,
                "importe": importe_tax,
                "importeCalculado": importe_calculado,
                "diferencia": diferencia,
            }
        )

    subtotal = float(source.get("subtotal", 0) or 0)
    total = float(source.get("total", 0) or 0)

    return {
        "version": source.get("version", ""),
        "fecha": source.get("fecha", ""),
        "uuid": source.get("uuid", ""),
        "emisor": source.get("emisor", ""),
        "receptor": source.get("receptor", ""),
        "subtotal": subtotal,
        "descuento": float(source.get("descuento", 0) or 0),
        "total": total,
        "conceptos": conceptos,
        "impuestosGlobales": impuestos_globales,
        "subtotalCalculado": round(sum(concept["importe"] for concept in conceptos), 2),
        "totalCalculado": round(total, 2),
        "hallazgos": [],
        "findings": [],
        "impactedConceptIndexes": [],
        "taxAuditGroups": [],
        "verdict": {
            "status": "clean",
            "title": "Sin discrepancias detectadas",
            "summary": "Resultado estructurado desde python-satcfdi. Los findings equivalentes aún no están implementados.",
        },
        "supportText": "Resultado estructurado desde python-satcfdi sin findings equivalentes todavía.",
    }
