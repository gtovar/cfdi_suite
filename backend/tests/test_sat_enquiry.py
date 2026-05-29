from __future__ import annotations

import io
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import httpx
    import openpyxl
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.routers.sat_enquiry import (
        _choose_best_json,
        _extract_json_objects,
        _parse_diverza_response,
        _parse_excel_input,
    )
except ModuleNotFoundError as error:
    TestClient = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


def _make_xlsx(rows: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    if not rows:
        return b""
    ws.append(list(rows[0].keys()))
    for row in rows:
        ws.append(list(row.values()))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


SAMPLE_DIVERZA_RESPONSE = json.dumps(
    {
        "uuid": "abc-123",
        "estado": "Vigente",
        "es_cancelable": "Cancelable sin aceptación",
        "estatus_cancelacion": "",
    }
)


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class ExtractJsonTests(unittest.TestCase):
    def test_extracts_single_object(self):
        text = 'prefix{"a":1}suffix'
        objs = _extract_json_objects(text)
        self.assertEqual(objs, ['{"a":1}'])

    def test_extracts_multiple_objects(self):
        text = '{"a":1} noise {"b":2}'
        objs = _extract_json_objects(text)
        self.assertEqual(len(objs), 2)

    def test_empty_text(self):
        self.assertEqual(_extract_json_objects(""), [])

    def test_choose_best_prefers_priority_fields(self):
        text = '{"x":1} {"estado":"Vigente","es_cancelable":"No cancelable","estatus_cancelacion":""}'
        best = _choose_best_json(text)
        self.assertIsNotNone(best)
        self.assertIn("estado", best)

    def test_choose_best_returns_none_on_garbage(self):
        self.assertIsNone(_choose_best_json("no json here"))


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class ParseDiverzaResponseTests(unittest.TestCase):
    def test_parses_vigente_cancelable(self):
        text = json.dumps(
            {
                "estado": "Vigente",
                "es_cancelable": "Cancelable sin aceptación",
                "estatus_cancelacion": "",
            }
        )
        result = _parse_diverza_response(text)
        self.assertEqual(result["estado"], "Vigente")
        self.assertIsNone(result["error"])

    def test_derives_no_cancelable_estatus(self):
        text = json.dumps(
            {
                "estado": "Vigente",
                "es_cancelable": "No cancelable",
                "estatus_cancelacion": "",
            }
        )
        result = _parse_diverza_response(text)
        self.assertEqual(result["estatus_cancelacion"], "No cancelable estatus")

    def test_handles_garbage_response(self):
        result = _parse_diverza_response("<!DOCTYPE html>error</html>")
        self.assertEqual(result["estado"], "")
        self.assertIsNotNone(result["error"])


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class ParseExcelInputTests(unittest.TestCase):
    def test_parses_standard_columns(self):
        rows = [
            {
                "UUID": "aaa-111",
                "RFC emisor": "AAA010101001",
                "RFC receptor": "BBB010101002",
                "TotalCFDI": "1160.00",
                "Motive": "01",
            }
        ]
        xlsx_bytes = _make_xlsx(rows)
        parsed = _parse_excel_input(xlsx_bytes)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["uuid"], "aaa-111")
        self.assertEqual(parsed[0]["rfc_emisor"], "AAA010101001")

    def test_skips_empty_uuid_rows(self):
        rows = [
            {"UUID": "", "RFC emisor": "AAA", "RFC receptor": "BBB", "TotalCFDI": "100", "Motive": "01"},
            {"UUID": "bbb-222", "RFC emisor": "CCC", "RFC receptor": "DDD", "TotalCFDI": "200", "Motive": "02"},
        ]
        xlsx_bytes = _make_xlsx(rows)
        parsed = _parse_excel_input(xlsx_bytes)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["uuid"], "bbb-222")

    def test_upcases_rfc_emisor(self):
        rows = [{"UUID": "x", "RFC emisor": "aaa010101", "RFC receptor": "bbb", "TotalCFDI": "1", "Motive": "01"}]
        parsed = _parse_excel_input(_make_xlsx(rows))
        self.assertEqual(parsed[0]["rfc_emisor"], "AAA010101")


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class SingleEnquiryEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_returns_404_when_rfc_not_configured(self):
        with patch("backend.app.routers.sat_enquiry.get_cred", return_value=None):
            resp = self.client.post(
                "/api/sat/enquiry",
                json={
                    "uuid": "aaa-111",
                    "rfc_emisor": "RFC_SIN_CONFIG",
                    "rfc_receptor": "BBB010101002",
                    "total_cfdi": "100.00",
                    "motive": "01",
                },
            )
        self.assertEqual(resp.status_code, 404)

    def test_returns_enquiry_result_on_success(self):
        mock_cred = {
            "credential_id": "123",
            "credential_token": "tok",
            "certificate_number": "cert",
        }
        mock_response = MagicMock()
        mock_response.text = SAMPLE_DIVERZA_RESPONSE
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with (
            patch("backend.app.routers.sat_enquiry.get_cred", return_value=mock_cred),
            patch("httpx.AsyncClient.put", new_callable=AsyncMock, return_value=mock_response),
        ):
            resp = self.client.post(
                "/api/sat/enquiry",
                json={
                    "uuid": "abc-123",
                    "rfc_emisor": "GMP080119QF0",
                    "rfc_receptor": "XAXX010101000",
                    "total_cfdi": "1160.00",
                    "motive": "01",
                },
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["estado"], "Vigente")
        self.assertIsNone(data["error"])
