from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from .contracts import AnalyzeCfdiResponse

LOGGER_NAME = "cfdi_platform.observability"
_LATENCY_BUCKETS = (
    (100, "le_100ms"),
    (500, "le_500ms"),
    (1000, "le_1000ms"),
)

logger = logging.getLogger(LOGGER_NAME)


@dataclass
class MetricsSnapshot:
    request_total: int
    fatal_error_total: int
    degraded_total: int
    fallback_total: int
    by_provider_mode: dict[str, int] = field(default_factory=dict)
    by_http_status: dict[str, int] = field(default_factory=dict)
    by_fallback_reason: dict[str, int] = field(default_factory=dict)
    latency_buckets: dict[str, int] = field(default_factory=dict)


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._request_total = 0
            self._fatal_error_total = 0
            self._degraded_total = 0
            self._fallback_total = 0
            self._by_provider_mode: Counter[str] = Counter()
            self._by_http_status: Counter[str] = Counter()
            self._by_fallback_reason: Counter[str] = Counter()
            self._latency_buckets: Counter[str] = Counter()

    def record(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._request_total += 1
            self._by_provider_mode[str(event["providerMode"])] += 1
            self._by_http_status[str(event["httpStatus"])] += 1

            if event["fatalIssueCount"] > 0:
                self._fatal_error_total += 1

            if event["degraded"]:
                self._degraded_total += 1

            if event["providerMode"] == "fallback":
                self._fallback_total += 1

            fallback_reason = event.get("fallbackReason")
            if fallback_reason:
                self._by_fallback_reason[str(fallback_reason)] += 1

            bucket = _latency_bucket_name(event.get("timingMs"))
            self._latency_buckets[bucket] += 1

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                request_total=self._request_total,
                fatal_error_total=self._fatal_error_total,
                degraded_total=self._degraded_total,
                fallback_total=self._fallback_total,
                by_provider_mode=dict(self._by_provider_mode),
                by_http_status=dict(self._by_http_status),
                by_fallback_reason=dict(self._by_fallback_reason),
                latency_buckets=dict(self._latency_buckets),
            )


metrics_registry = MetricsRegistry()


def record_analyze_cfdi_request(
    response: AnalyzeCfdiResponse,
    *,
    http_status: int,
) -> dict[str, Any]:
    event = _build_event(
        response=response,
        http_status=http_status,
        event_name="analyze_cfdi.request",
    )
    metrics_registry.record(event)
    logger.info(json.dumps(event, sort_keys=True, ensure_ascii=True))
    return event


def record_analyze_cfdi_error(
    response: AnalyzeCfdiResponse,
    *,
    http_status: int,
) -> dict[str, Any]:
    event = _build_event(
        response=response,
        http_status=http_status,
        event_name="analyze_cfdi.error",
    )
    metrics_registry.record(event)
    logger.warning(json.dumps(event, sort_keys=True, ensure_ascii=True))
    return event


def snapshot_metrics() -> MetricsSnapshot:
    return metrics_registry.snapshot()


def reset_metrics() -> None:
    metrics_registry.reset()


def _build_event(
    *,
    response: AnalyzeCfdiResponse,
    http_status: int,
    event_name: str,
) -> dict[str, Any]:
    fatal_issue_count = sum(1 for issue in response.issues if issue.fatal)

    return {
        "event": event_name,
        "requestId": response.meta.requestId,
        "capability": response.meta.capability,
        "provider": response.meta.provider,
        "providerMode": response.meta.providerMode,
        "degraded": response.meta.degraded,
        "fallbackReason": response.meta.fallbackReason,
        "profile": response.profile,
        "timingMs": response.meta.timingMs,
        "httpStatus": http_status,
        "fatalIssueCount": fatal_issue_count,
    }


def _latency_bucket_name(timing_ms: int | None) -> str:
    if timing_ms is None:
        return "unknown"

    for upper_bound, name in _LATENCY_BUCKETS:
        if timing_ms <= upper_bound:
            return name

    return "gt_1000ms"

from dataclasses import dataclass

@dataclass
class InfraDiagnosticReport:
    status: str
    verdict: str
    evidence: dict[str, Any]
    recommendations: list[str]

def run_infrastructure_self_diagnostic() -> InfraDiagnosticReport:
    """
    Analiza el historial de métricas del servidor para deducir de forma inteligente
    si la infraestructura serverless está estrangulando el rendimiento del backend.
    """
    snap = snapshot_metrics()
    recommendations = []
    verdict = "La infraestructura serverless opera dentro de los parámetros saludables."
    status = "OK"

    # 1. Diagnóstico de CPU Throttling o caídas de contenedores (HTTP 504 / 502)
    errors_504 = snap.by_http_status.get("504", 0)
    errors_502 = snap.by_http_status.get("502", 0)
    
    if errors_504 > 0 or errors_502 > 0:
        status = "INFRASTRUCTURE_STRESSED"
        verdict = f"ALERTA: Se detectaron {errors_504} timeouts (504) y {errors_502} caídas de pasarela (502)."
        recommendations.append(
            "Diagnóstico: Contenedor Cloud Run colapsado por límites físicos (Memory Limit Exceeded o CPU Throttling)."
        )
        recommendations.append(
            "Solución inmediata: Incrementa la configuración de hardware de tu servicio en Cloud Run a mínimo 2 vCPU y 2 GB de RAM."
        )

    # 2. Diagnóstico de Riesgo de Desconexión por el Enrutador de Vercel
    total_requests = snap.request_total or 1
    latencias_extremas = snap.latency_buckets.get("gt_1000ms", 0)
    
    if (latencias_extremas / total_requests) > 0.35 and total_requests > 15:
        if status == "OK":
            status = "VERCEL_TIMEOUT_RISK"
            verdict = "ADVERTENCIA: Alta concentración de latencias prolongadas (>1000ms en el 35%+ de peticiones)."
        recommendations.append(
            "Diagnóstico: Estás procesando XMLs masivos de forma sincrónica. Vercel matará conexiones que duren más de 10s-60s."
        )
        recommendations.append(
            "Solución inmediata: Sintoniza la cola de Cloud Tasks reduciendo el parámetro 'max_dispatches_per_second' a un valor menor (ej. 2 o 3) para no asfixiar el contenedor."
        )

    # 3. Diagnóstico de Exponential Backoff en la Cola distribuida
    if snap.fallback_total > (total_requests * 0.2):
        recommendations.append(
            "Diagnóstico: Activación frecuente de mecanismos alternos (Fallback Mode). Cloud Tasks entró en Exponential Backoff defensivo."
        )

    return InfraDiagnosticReport(
        status=status,
        verdict=verdict,
        evidence={
            "http_statuses": snap.by_http_status,
            "latency_profile": snap.latency_buckets,
            "total_traffic": snap.request_total
        },
        recommendations=recommendations
    )
