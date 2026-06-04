from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..policy import (
    ANALYZE_CFDI_PROVIDER_TIMEOUT_SECONDS,
    FALLBACK_REASON_PROVIDER_RUNTIME_FAILURE,
)
from .base import (
    CfdiAnalysisProvider,
    ProviderCapabilities,
    ProviderDiagnostics,
    ProviderDocumentSignal,
    ProviderIssue,
    ProviderResult,
)

WRAPPER_PATH = Path(__file__).resolve().parent.parent.parent / "wrappers" / "python-satcfdi-wrapper.py"


class PythonSatcfdiProviderError(RuntimeError):
    pass


class PythonSatcfdiProvider(CfdiAnalysisProvider):
    name = "python-satcfdi"
    mode = "bridge"
    version = None

    def analyze(self, xml: str) -> ProviderResult:
        python_binary = str(Path(sys.executable))

        try:
            completed = subprocess.run(
                [python_binary, str(WRAPPER_PATH)],
                input=xml,
                capture_output=True,
                text=True,
                cwd=str(WRAPPER_PATH.parent),
                check=False,
                timeout=ANALYZE_CFDI_PROVIDER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise PythonSatcfdiProviderError(
                "El provider python-satcfdi excedió el tiempo límite de ejecución"
            ) from error

        stdout = completed.stdout.strip()
        if completed.returncode != 0 and not stdout:
            raise PythonSatcfdiProviderError("No se pudo ejecutar el provider python-satcfdi")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise PythonSatcfdiProviderError("El provider python-satcfdi devolvió una respuesta inválida") from error

        return _to_provider_result(payload)


default_python_satcfdi_provider = PythonSatcfdiProvider()


def _to_provider_result(payload: dict[str, Any]) -> ProviderResult:
    provider_issues: list[ProviderIssue] = []

    error_type = payload.get("errorType")
    error_message = payload.get("errorMessage")
    if error_type == "parse":
        provider_issues.append(
            ProviderIssue(
                code="parse_failed",
                message=error_message or "No se pudo parsear el CFDI en python-satcfdi",
                public_message="No se pudo parsear el CFDI en el provider Python.",
                stage="parse",
            )
        )
    elif error_type == "runtime":
        provider_issues.append(
            ProviderIssue(
                code="runtime_failed",
                message=error_message or "Error de ejecución del provider python-satcfdi",
                public_message="El provider Python no pudo completar el análisis.",
                stage="parse",
            )
        )

    unsupported_capabilities = payload.get("unsupportedCapabilities") or []
    if payload.get("satcfdiAvailable") is False:
        provider_issues.append(
            ProviderIssue(
                code="unsupported_capability",
                message=" | ".join(unsupported_capabilities) or "python-satcfdi no está disponible en este entorno",
                public_message="El provider Python no está disponible en este entorno.",
                stage="parse",
            )
        )
    elif unsupported_capabilities:
        provider_issues.append(
            ProviderIssue(
                code="unsupported_capability",
                message=" | ".join(unsupported_capabilities),
                public_message="El provider Python no soporta parte de la extracción requerida.",
                stage="extract",
            )
        )

    cfdi = payload.get("cfdi")
    findings_supported = bool(payload.get("findingsImplemented", False))
    if cfdi and not findings_supported:
        provider_issues.append(
            ProviderIssue(
                code="findings_unavailable",
                message="El backend Python aún no emite findings equivalentes al motor TypeScript.",
                public_message="El provider Python devolvió estructura usable pero sin findings equivalentes completos.",
                stage="extract",
            )
        )

    return ProviderResult(
        capabilities=ProviderCapabilities(
            supported_profiles=("ingreso", "pagos", "unknown"),
            supports_ingreso_rows=True,
            supports_pago_rows=True,
            supports_findings=findings_supported,
        ),
        document_signal=ProviderDocumentSignal(
            profile=payload.get("profile", "unknown"),
            reason=None if payload.get("profile") else "provider_profile_missing",
        ),
        structured_cfdi=cfdi,
        ingreso_rows=payload.get("ingresoRows", []),
        ingreso_row_header=payload.get("ingresoRowHeader", {}),
        pago_rows=payload.get("pagoRows", []),
        provider_issues=provider_issues,
        diagnostics=ProviderDiagnostics(
            bridge=True,
            fallback_eligible=any(issue.code == "runtime_failed" for issue in provider_issues),
            fallback_reason=FALLBACK_REASON_PROVIDER_RUNTIME_FAILURE
            if any(issue.code == "runtime_failed" for issue in provider_issues)
            else None,
            warning_messages=tuple(payload.get("warnings", [])),
        ),
    )
