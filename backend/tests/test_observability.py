from __future__ import annotations

import unittest

from backend.app.contracts import AnalysisIssue, AnalyzeCfdiMeta, AnalyzeCfdiResponse
from backend.app.observability import LOGGER_NAME, record_analyze_cfdi_request, reset_metrics, snapshot_metrics


class ObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_metrics()

    def test_request_event_is_safe_and_updates_latency_bucket(self) -> None:
        response = AnalyzeCfdiResponse(
            profile="ingreso",
            cfdi={
                "uuid": "UUID-SHOULD-NOT-BE-LOGGED",
                "emisor": "EMISOR SA DE CV",
                "receptor": "RECEPTOR SA DE CV",
            },
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
                provider="python-satcfdi",
                providerMode="bridge",
                degraded=True,
                requestId="req-obs-1",
                timingMs=320,
                warnings=["warning"],
            ),
        )

        with self.assertLogs(LOGGER_NAME, level="INFO") as captured:
            event = record_analyze_cfdi_request(response, http_status=200)

        self.assertEqual(event["requestId"], "req-obs-1")
        self.assertEqual(event["timingMs"], 320)
        self.assertEqual(event["fatalIssueCount"], 0)
        log_line = captured.output[-1]
        self.assertIn('"event": "analyze_cfdi.request"', log_line)
        self.assertIn('"requestId": "req-obs-1"', log_line)
        self.assertNotIn("UUID-SHOULD-NOT-BE-LOGGED", log_line)
        self.assertNotIn("EMISOR SA DE CV", log_line)
        self.assertNotIn("RECEPTOR SA DE CV", log_line)

        metrics = snapshot_metrics()
        self.assertEqual(metrics.request_total, 1)
        self.assertEqual(metrics.degraded_total, 1)
        self.assertEqual(metrics.latency_buckets["le_500ms"], 1)


if __name__ == "__main__":
    unittest.main()
