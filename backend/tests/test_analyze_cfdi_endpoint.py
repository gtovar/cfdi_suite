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
            response = self.client.post("/api/cfdi/analyze", json={"xml": "<xml />"})

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

    def test_endpoint_returns_contractual_invalid_request_response(self) -> None:
        with self.assertLogs(LOGGER_NAME, level="WARNING") as captured:
            response = self.client.post("/api/cfdi/analyze", json={"xml": ""})

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["profile"], "unknown")
        self.assertIsNone(payload["cfdi"])
        self.assertEqual(payload["issues"][0]["code"], "CFDI_PARSE_FAILED")
        self.assertTrue(payload["issues"][0]["fatal"])
        self.assertEqual(payload["meta"]["contractVersion"], "v1")
        self.assertEqual(payload["meta"]["provider"], "platform")
        self.assertTrue(payload["meta"]["requestId"])
        log_line = captured.output[-1]
        self.assertIn('"event": "analyze_cfdi.error"', log_line)
        self.assertIn(payload["meta"]["requestId"], log_line)
        self.assertNotIn('"xml"', log_line)
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.fatal_error_total, 1)
        self.assertEqual(metrics.by_http_status["422"], 1)
        self.assertEqual(metrics.by_provider_mode["primary"], 1)

    def test_endpoint_rejects_oversized_xml_with_contractual_response(self) -> None:
        with self.assertLogs(LOGGER_NAME, level="WARNING"):
            response = self.client.post("/api/cfdi/analyze", json={"xml": "x" * 20_000_001})

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["profile"], "unknown")
        self.assertIsNone(payload["cfdi"])
        self.assertEqual(payload["issues"][0]["code"], "CFDI_PARSE_FAILED")
        self.assertTrue(payload["meta"]["requestId"])
        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.fatal_error_total, 1)
