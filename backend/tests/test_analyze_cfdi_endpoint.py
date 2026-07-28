from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient

    from backend.app.contracts import AnalysisIssue, AnalyzeCfdiMeta, AnalyzeCfdiResponse
    from backend.app.main import app
    from backend.app.observability import LOGGER_NAME, reset_metrics, snapshot_metrics
except ModuleNotFoundError as error:
    TestClient = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class AnalyzeCfdiEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        reset_metrics()

    def test_endpoint_returns_contractual_v1_response(self) -> None:
        response_model = AnalyzeCfdiResponse(
            profile="ingreso",
            cfdi=None,
            ingresoRows=[],
            pagoRows=[],
            issues=[
                AnalysisIssue(
                    code="RESULT_DEGRADED",
                    message="Resultado degradado pero usable",
                    stage="extract",
                    fatal=False,
                )
            ],
            meta=AnalyzeCfdiMeta(
                provider="current-ts",
                providerMode="fallback",
                degraded=True,
                requestId="req-endpoint-1",
                fallbackReason="provider_runtime_failure",
            ),
        )

        with patch("backend.app.main.run_analyze_cfdi", return_value=response_model) as mocked_run:
            response = self.client.post(
                "/api/cfdi/analyze",
                files={"file": ("test.xml", b"<xml />", "text/xml")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        mocked_run.assert_called_once_with("<xml />")
        self.assertEqual(payload["meta"]["contractVersion"], "v1")
        self.assertEqual(payload["meta"]["capability"], "analyze_cfdi")
        self.assertEqual(payload["meta"]["providerMode"], "fallback")
        self.assertEqual(payload["meta"]["fallbackReason"], "provider_runtime_failure")
        self.assertEqual(payload["issues"][0]["code"], "RESULT_DEGRADED")
        self.assertNotIn("findings", payload)
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 0)

    def test_endpoint_rejects_missing_file(self) -> None:
        response = self.client.post("/api/cfdi/analyze")
        self.assertEqual(response.status_code, 422)

    def test_endpoint_rejects_oversized_xml(self) -> None:
        oversized = b"<xml>" + b"x" * 50_000_001 + b"</xml>"
        response = self.client.post(
            "/api/cfdi/analyze",
            files={"file": ("big.xml", oversized, "text/xml")},
        )
        self.assertEqual(response.status_code, 413)
