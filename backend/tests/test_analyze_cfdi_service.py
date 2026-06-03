from __future__ import annotations

import importlib.util
import types
import unittest
from pathlib import Path

from backend.app.observability import LOGGER_NAME, reset_metrics, snapshot_metrics

# Importar SENTINEL_INVALIDO desde el wrapper para no duplicar la cadena
_WRAPPER_PATH = Path(__file__).parents[2] / "frontend" / "src" / "cfdi" / "engine" / "python-satcfdi-wrapper.py"
_spec = importlib.util.spec_from_file_location("python_satcfdi_wrapper", _WRAPPER_PATH)
_wrapper_mod: types.ModuleType = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_wrapper_mod)
SENTINEL_INVALIDO = _wrapper_mod.SENTINEL_INVALIDO
from backend.app.providers.base import (
    ProviderCapabilities,
    ProviderDiagnostics,
    ProviderDocumentSignal,
    ProviderIssue,
    ProviderResult,
)
from backend.app.providers.current_ts import CurrentTsProviderError
from backend.app.providers.python_satcfdi import PythonSatcfdiProviderError
from backend.app.services.analyze_cfdi import run_analyze_cfdi


class StubProvider:
    def __init__(self, result: ProviderResult | None = None, *, error: Exception | None = None) -> None:
        self.name = "stub-provider"
        self.mode = "bridge"
        self.version = "test-build"
        self._result = result or ProviderResult()
        self._error = error

    def analyze(self, xml: str) -> ProviderResult:
        if self._error is not None:
            raise self._error
        return self._result


class AnalyzeCfdiServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_metrics()

    def test_successful_response_exposes_v1_meta_and_degraded_issue(self) -> None:
        provider = StubProvider(
            ProviderResult(
                capabilities=ProviderCapabilities(
                    supported_profiles=("ingreso", "pagos", "unknown"),
                    supports_ingreso_rows=True,
                    supports_pago_rows=True,
                    supports_findings=False,
                ),
                document_signal=ProviderDocumentSignal(profile="ingreso"),
                structured_cfdi={
                    "version": "4.0",
                    "fecha": "2026-04-18T10:00:00",
                    "uuid": "UUID-123",
                    "emisor": "EMISOR SA DE CV",
                    "receptor": "RECEPTOR SA DE CV",
                    "subtotal": 100,
                    "descuento": 0,
                    "total": 116,
                    "conceptos": [],
                    "impuestosGlobales": [],
                },
                ingreso_rows=[],
                pago_rows=[],
                provider_issues=[
                    ProviderIssue(
                        code="findings_unavailable",
                        message="findings missing",
                        public_message="El provider Python devolvió estructura usable pero sin findings equivalentes completos.",
                        stage="extract",
                    )
                ],
                diagnostics=ProviderDiagnostics(bridge=True),
            )
        )

        with self.assertLogs(LOGGER_NAME, level="INFO") as captured:
            response = run_analyze_cfdi("<xml />", provider)

        self.assertIsNotNone(response.cfdi)
        self.assertTrue(response.meta.degraded)
        self.assertEqual(response.meta.contractVersion, "v1")
        self.assertEqual(response.meta.capability, "analyze_cfdi")
        self.assertEqual(response.meta.provider, "stub-provider")
        self.assertEqual(response.meta.providerMode, "bridge")
        self.assertEqual(response.meta.providerVersion, "test-build")
        self.assertTrue(response.meta.requestId)
        self.assertIsInstance(response.meta.timingMs, int)
        self.assertNotEqual(response.meta.requestId, "")
        self.assertIn("RESULT_DEGRADED", [issue.code for issue in response.issues])
        log_line = captured.output[-1]
        self.assertIn('"event": "analyze_cfdi.request"', log_line)
        self.assertNotIn('"xml"', log_line)
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.degraded_total, 1)
        self.assertEqual(metrics.fatal_error_total, 0)
        self.assertEqual(metrics.by_provider_mode["bridge"], 1)

    def test_runtime_error_returns_safe_fatal_issue_without_degraded(self) -> None:
        provider = StubProvider(error=PythonSatcfdiProviderError("boom"))

        with self.assertLogs(LOGGER_NAME, level="WARNING") as captured:
            response = run_analyze_cfdi("<xml />", provider, None)

        self.assertIsNone(response.cfdi)
        self.assertFalse(response.meta.degraded)
        self.assertEqual(len(response.issues), 1)
        self.assertEqual(response.issues[0].code, "ENGINE_RUNTIME_FAILED")
        self.assertTrue(response.issues[0].fatal)
        self.assertEqual(
            response.issues[0].message,
            "La plataforma no pudo completar el análisis.",
        )
        log_line = captured.output[-1]
        self.assertIn('"event": "analyze_cfdi.error"', log_line)
        self.assertNotIn("boom", log_line)
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.fatal_error_total, 1)
        self.assertEqual(metrics.fallback_total, 0)

    def test_provider_parse_issue_maps_to_fatal_contract_issue(self) -> None:
        provider = StubProvider(
            ProviderResult(
                document_signal=ProviderDocumentSignal(profile="unknown"),
                provider_issues=[
                    ProviderIssue(
                        code="parse_failed",
                        message="detalle interno parse",
                        public_message="No se pudo parsear el CFDI en el provider Python.",
                        stage="parse",
                    )
                ],
                diagnostics=ProviderDiagnostics(bridge=True),
            )
        )

        with self.assertLogs(LOGGER_NAME, level="WARNING"):
            response = run_analyze_cfdi("<xml />", provider)

        self.assertIsNone(response.cfdi)
        self.assertEqual(response.issues[0].code, "CFDI_PARSE_FAILED")
        self.assertTrue(response.issues[0].fatal)
        self.assertEqual(
            response.issues[0].message,
            "No se pudo parsear el CFDI en el provider Python.",
        )
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.fatal_error_total, 1)

    def test_runtime_failure_uses_fallback_provider_and_preserves_v1_meta(self) -> None:
        primary_provider = StubProvider(error=PythonSatcfdiProviderError("boom"))
        fallback_provider = StubProvider(
            ProviderResult(
                capabilities=ProviderCapabilities(
                    supported_profiles=("ingreso", "pagos", "unknown"),
                    supports_ingreso_rows=True,
                    supports_pago_rows=True,
                    supports_findings=True,
                ),
                document_signal=ProviderDocumentSignal(profile="ingreso"),
                structured_cfdi={
                    "version": "4.0",
                    "fecha": "2026-04-18T10:00:00",
                    "uuid": "UUID-FALLBACK-123",
                    "emisor": "EMISOR SA DE CV",
                    "receptor": "RECEPTOR SA DE CV",
                    "subtotal": 100,
                    "descuento": 0,
                    "total": 116,
                    "conceptos": [],
                    "impuestosGlobales": [],
                    "findings": [{"id": "f-1"}],
                },
                diagnostics=ProviderDiagnostics(),
            )
        )
        fallback_provider.name = "current-ts"
        fallback_provider.mode = "fallback"

        with self.assertLogs(LOGGER_NAME, level="INFO"):
            response = run_analyze_cfdi("<xml />", primary_provider, fallback_provider)

        self.assertIsNotNone(response.cfdi)
        self.assertEqual(response.meta.provider, "current-ts")
        self.assertEqual(response.meta.providerMode, "fallback")
        self.assertEqual(response.meta.fallbackReason, "provider_runtime_failure")
        self.assertFalse(response.meta.degraded)
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.fallback_total, 1)
        self.assertEqual(metrics.by_fallback_reason["provider_runtime_failure"], 1)
        self.assertEqual(metrics.by_provider_mode["fallback"], 1)

    def test_fallback_eligible_primary_result_uses_fallback_provider(self) -> None:
        primary_provider = StubProvider(
            ProviderResult(
                document_signal=ProviderDocumentSignal(profile="unknown"),
                provider_issues=[
                    ProviderIssue(
                        code="runtime_failed",
                        message="primary runtime",
                        public_message="primary runtime",
                        stage="parse",
                    )
                ],
                diagnostics=ProviderDiagnostics(
                    fallback_eligible=True,
                    fallback_reason="provider_runtime_failure",
                ),
            )
        )
        fallback_provider = StubProvider(
            ProviderResult(
                document_signal=ProviderDocumentSignal(profile="pagos"),
                structured_cfdi={
                    "version": "4.0",
                    "fecha": "2026-04-18T10:00:00",
                    "uuid": "UUID-FALLBACK-456",
                    "emisor": "EMISOR SA DE CV",
                    "receptor": "RECEPTOR SA DE CV",
                    "subtotal": 100,
                    "descuento": 0,
                    "total": 116,
                    "conceptos": [],
                    "impuestosGlobales": [],
                    "findings": [{"id": "f-2"}],
                },
                diagnostics=ProviderDiagnostics(),
            )
        )
        fallback_provider.name = "current-ts"
        fallback_provider.mode = "fallback"

        with self.assertLogs(LOGGER_NAME, level="INFO"):
            response = run_analyze_cfdi("<xml />", primary_provider, fallback_provider)

        self.assertEqual(response.profile, "pagos")
        self.assertEqual(response.meta.providerMode, "fallback")
        self.assertEqual(response.meta.fallbackReason, "provider_runtime_failure")
        self.assertEqual(response.issues, [])
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.fallback_total, 1)

    def test_parse_failure_does_not_use_fallback(self) -> None:
        primary_provider = StubProvider(
            ProviderResult(
                document_signal=ProviderDocumentSignal(profile="unknown"),
                provider_issues=[
                    ProviderIssue(
                        code="parse_failed",
                        message="detalle interno parse",
                        public_message="No se pudo parsear el CFDI en el provider Python.",
                        stage="parse",
                    )
                ],
                diagnostics=ProviderDiagnostics(
                    fallback_eligible=False,
                    fallback_reason=None,
                ),
            )
        )
        fallback_provider = StubProvider(error=AssertionError("fallback should not run"))
        fallback_provider.name = "current-ts"
        fallback_provider.mode = "fallback"

        with self.assertLogs(LOGGER_NAME, level="WARNING"):
            response = run_analyze_cfdi("<xml />", primary_provider, fallback_provider)

        self.assertIsNone(response.cfdi)
        self.assertEqual(response.meta.provider, "stub-provider")
        self.assertEqual(response.meta.providerMode, "bridge")
        self.assertIsNone(response.meta.fallbackReason)
        self.assertEqual(response.issues[0].code, "CFDI_PARSE_FAILED")
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.fallback_total, 0)

    def test_returns_safe_fatal_issue_when_primary_and_fallback_fail(self) -> None:
        primary_provider = StubProvider(error=PythonSatcfdiProviderError("boom"))
        fallback_provider = StubProvider(error=CurrentTsProviderError("fallback boom"))
        fallback_provider.name = "current-ts"
        fallback_provider.mode = "fallback"

        with self.assertLogs(LOGGER_NAME, level="WARNING"):
            response = run_analyze_cfdi("<xml />", primary_provider, fallback_provider)

        self.assertIsNone(response.cfdi)
        self.assertEqual(response.meta.provider, "stub-provider")
        self.assertEqual(response.meta.providerMode, "bridge")
        self.assertEqual(len(response.issues), 1)
        self.assertEqual(response.issues[0].code, "ENGINE_RUNTIME_FAILED")
        self.assertTrue(response.issues[0].fatal)
        self.assertEqual(
            response.issues[0].message,
            "La plataforma no pudo completar el análisis.",
        )
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.fatal_error_total, 1)
        self.assertEqual(metrics.fallback_total, 0)


class CollectCatalogFindingsTests(unittest.TestCase):
    """Tests unitarios para _collect_catalog_findings (catálogos de cabecera y concepto)."""

    def setUp(self):
        from backend.app.services.analyze_cfdi import _collect_catalog_findings
        self._fn = _collect_catalog_findings

    def _base_source(self, **overrides):
        src = {
            "conceptos": [],
            "usoCfdi": "",
            "usoCfdiDescripcion": None,
            "metodoPago": "",
            "metodoPagoDescripcion": None,
            "formaPago": "",
            "formaPagoDescripcion": None,
            "moneda": "",
            "monedaDescripcion": None,
        }
        src.update(overrides)
        return src

    def test_no_findings_when_all_valid(self):
        src = self._base_source(
            usoCfdi="G03", usoCfdiDescripcion="Gastos en general",
            metodoPago="PUE", metodoPagoDescripcion="Pago en una sola exhibición",
            formaPago="03", formaPagoDescripcion="Transferencia electrónica de fondos",
            moneda="MXN", monedaDescripcion="Peso Mexicano",
        )
        findings, impacted = self._fn(src)
        self.assertEqual(findings, [])
        self.assertEqual(impacted, [])

    def test_no_findings_when_fields_absent(self):
        """Campos ausentes (None) no producen findings."""
        findings, impacted = self._fn(self._base_source())
        self.assertEqual(findings, [])
        self.assertEqual(impacted, [])

    def test_uso_cfdi_invalido_genera_finding(self):
        src = self._base_source(usoCfdi="ZZZ", usoCfdiDescripcion=SENTINEL_INVALIDO)
        findings, _ = self._fn(src)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "catalog-uso-cfdi-ZZZ")
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertEqual(findings[0]["declared"], "ZZZ")

    def test_metodo_pago_invalido_genera_finding(self):
        src = self._base_source(metodoPago="ZZ", metodoPagoDescripcion=SENTINEL_INVALIDO)
        findings, _ = self._fn(src)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "catalog-metodo-pago-ZZ")

    def test_forma_pago_invalida_genera_finding(self):
        src = self._base_source(formaPago="ZZ", formaPagoDescripcion=SENTINEL_INVALIDO)
        findings, _ = self._fn(src)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "catalog-forma-pago-ZZ")

    def test_moneda_invalida_genera_finding(self):
        src = self._base_source(moneda="ZZZ", monedaDescripcion=SENTINEL_INVALIDO)
        findings, _ = self._fn(src)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "catalog-moneda-ZZZ")

    def test_multiples_invalidos_generan_un_finding_cada_uno(self):
        src = self._base_source(
            usoCfdi="ZZZ", usoCfdiDescripcion=SENTINEL_INVALIDO,
            moneda="QQQ", monedaDescripcion=SENTINEL_INVALIDO,
        )
        findings, _ = self._fn(src)
        ids = {f["id"] for f in findings}
        self.assertIn("catalog-uso-cfdi-ZZZ", ids)
        self.assertIn("catalog-moneda-QQQ", ids)
        self.assertEqual(len(findings), 2)

    def test_metodo_pago_ausente_no_genera_finding(self):
        """Campo ausente (None descriptor) con código vacío → sin finding."""
        findings, impacted = self._fn(self._base_source(metodoPago="", metodoPagoDescripcion=None))
        self.assertEqual(findings, [])
        self.assertEqual(impacted, [])

    def test_current_ts_sin_campos_no_genera_finding(self):
        """current_ts no emite campos de cabecera → source.get() devuelve None → sin finding."""
        findings, impacted = self._fn({"conceptos": []})
        self.assertEqual(findings, [])
        self.assertEqual(impacted, [])


if __name__ == "__main__":
    unittest.main()
