from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..policy import ANALYZE_CFDI_PROVIDER_TIMEOUT_SECONDS
from .base import (
    CfdiAnalysisProvider,
    ProviderCapabilities,
    ProviderDiagnostics,
    ProviderDocumentSignal,
    ProviderIssue,
    ProviderResult,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_PATH = REPO_ROOT / "src" / "cfdi" / "engine" / "current-ts-wrapper.ts"


class CurrentTsProviderError(RuntimeError):
    pass


class CurrentTsProvider(CfdiAnalysisProvider):
    name = "current-ts"
    mode = "fallback"
    version = None

    def analyze(self, xml: str) -> ProviderResult:
        try:
            completed = subprocess.run(
                ["node", "--import", "tsx", str(WRAPPER_PATH)],
                input=xml,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
                timeout=ANALYZE_CFDI_PROVIDER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise CurrentTsProviderError(
                "El provider current-ts excedió el tiempo límite de ejecución"
            ) from error
        except OSError as error:
            raise CurrentTsProviderError(
                "No se pudo ejecutar el provider current-ts"
            ) from error

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()

        if completed.returncode != 0 and not stdout:
            raise CurrentTsProviderError(
                stderr or "No se pudo ejecutar el provider current-ts"
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise CurrentTsProviderError(
                "El provider current-ts devolvió una respuesta inválida"
            ) from error

        return _to_provider_result(payload)


default_current_ts_provider = CurrentTsProvider()


def _to_provider_result(payload: dict[str, Any]) -> ProviderResult:
    provider_issues: list[ProviderIssue] = []

    for issue in payload.get("issues", []):
        mapped = _map_issue(issue)
        if mapped is not None:
            provider_issues.append(mapped)

    cfdi = payload.get("cfdi")
    supports_findings = bool(cfdi)

    return ProviderResult(
        capabilities=ProviderCapabilities(
            supported_profiles=("ingreso", "pagos", "unknown"),
            supports_ingreso_rows=True,
            supports_pago_rows=True,
            supports_findings=supports_findings,
        ),
        document_signal=ProviderDocumentSignal(
            profile=payload.get("profile", "unknown"),
            reason=None if payload.get("profile") else "provider_profile_missing",
        ),
        structured_cfdi=cfdi,
        ingreso_rows=payload.get("ingresoRows", []),
        pago_rows=payload.get("pagoRows", []),
        provider_issues=provider_issues,
        diagnostics=ProviderDiagnostics(),
    )


def _map_issue(issue: dict[str, Any]) -> ProviderIssue | None:
    code = issue.get("code")
    message = issue.get("message") or "Error desconocido del provider current-ts"
    stage = issue.get("stage") or "parse"

    if code in {"PROFILE_DETECTION_FAILED", "CFDI_PARSE_FAILED"}:
        return ProviderIssue(
            code="parse_failed",
            message=message,
            public_message=message,
            stage=stage,
        )

    if code == "ENGINE_RUNTIME_FAILED":
        return ProviderIssue(
            code="runtime_failed",
            message=message,
            public_message=message,
            stage=stage,
        )

    if code == "UNSUPPORTED_CAPABILITY":
        return ProviderIssue(
            code="unsupported_capability",
            message=message,
            public_message=message,
            stage=stage,
        )

    if code in {"INGRESO_EXTRACTION_FAILED", "PAGO_EXTRACTION_FAILED"}:
        return ProviderIssue(
            code="rows_unavailable",
            message=message,
            public_message=message,
            stage=stage,
        )

    if code == "RESULT_DEGRADED":
        return ProviderIssue(
            code="findings_unavailable",
            message=message,
            public_message=message,
            stage=stage,
        )

    return None
