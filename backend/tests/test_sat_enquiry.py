from __future__ import annotations

import io
import json
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import httpx
    import openpyxl
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.routers.sat_enquiry import (
        _DIVERZA_BASE,
        BATCH_ENQUIRY_WORKERS,
        _batch_enquiry_results,
        _call_diverza,
        _choose_best_json,
        _extract_json_objects,
        _is_uuid,
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
        "uuid": "a1b2c3d4-e5f6-4a7b-8c9d-ef1234567890",
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
                "UUID": "aaa11111-1111-4111-8111-111111111111",
                "RFC emisor": "AAA010101001",
                "RFC receptor": "BBB010101002",
                "TotalCFDI": "1160.00",
                "Motive": "01",
            }
        ]
        xlsx_bytes = _make_xlsx(rows)
        parsed, descartadas = _parse_excel_input(xlsx_bytes)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["uuid"], "aaa11111-1111-4111-8111-111111111111")
        self.assertEqual(parsed[0]["rfc_emisor"], "AAA010101001")
        self.assertEqual(descartadas, 0)

    def test_skips_empty_uuid_rows(self):
        rows = [
            {"UUID": "", "RFC emisor": "AAA", "RFC receptor": "BBB", "TotalCFDI": "100", "Motive": "01"},
            {"UUID": "bbb22222-2222-4222-8222-222222222222", "RFC emisor": "CCC", "RFC receptor": "DDD", "TotalCFDI": "200", "Motive": "02"},
        ]
        xlsx_bytes = _make_xlsx(rows)
        parsed, descartadas = _parse_excel_input(xlsx_bytes)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["uuid"], "bbb22222-2222-4222-8222-222222222222")
        # Una fila en blanco NO cuenta como descartada: en un Excel real las
        # últimas filas suelen venir vacías y reportarlas sería ruido.
        self.assertEqual(descartadas, 0)

    def test_upcases_rfc_emisor(self):
        rows = [{"UUID": "ccc33333-3333-4333-8333-333333333333", "RFC emisor": "aaa010101", "RFC receptor": "bbb", "TotalCFDI": "1", "Motive": "01"}]
        parsed, descartadas = _parse_excel_input(_make_xlsx(rows))
        self.assertEqual(parsed[0]["rfc_emisor"], "AAA010101")
        self.assertEqual(descartadas, 0)

    def test_descarta_uuid_malformado_y_lo_cuenta(self):
        """Hallazgo #38: un UUID que no es un UUID nunca debe llegar a la URL
        de Diverza. La fila se omite -- no revienta el lote -- pero se cuenta,
        para poder decírselo al usuario en vez de tragárselo."""
        rows = [
            {"UUID": "../../../admin", "RFC emisor": "AAA", "RFC receptor": "B", "TotalCFDI": "1", "Motive": "01"},
            {"UUID": "no-soy-un-uuid", "RFC emisor": "AAA", "RFC receptor": "B", "TotalCFDI": "1", "Motive": "01"},
            {"UUID": "", "RFC emisor": "AAA", "RFC receptor": "B", "TotalCFDI": "1", "Motive": "01"},
            {"UUID": "ddd44444-4444-4444-8444-444444444444", "RFC emisor": "CCC", "RFC receptor": "D", "TotalCFDI": "2", "Motive": "02"},
        ]
        parsed, descartadas = _parse_excel_input(_make_xlsx(rows))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["uuid"], "ddd44444-4444-4444-8444-444444444444")
        # 2, no 3: la fila con UUID vacío no cuenta.
        self.assertEqual(descartadas, 2)

    def test_accepts_500_valid_uuids(self):
        rows = [
            {"UUID": f"00000000-0000-4000-8000-{number:012d}", "RFC emisor": "AAA", "RFC receptor": "BBB", "TotalCFDI": "1", "Motive": "01"}
            for number in range(500)
        ]
        parsed, descartadas = _parse_excel_input(_make_xlsx(rows))
        self.assertEqual(len(parsed), 500)
        self.assertEqual(descartadas, 0)

    def test_rejects_501_valid_uuids(self):
        rows = [
            {"UUID": f"00000000-0000-4000-8000-{number:012d}", "RFC emisor": "AAA", "RFC receptor": "BBB", "TotalCFDI": "1", "Motive": "01"}
            for number in range(501)
        ]
        with self.assertRaisesRegex(Exception, "máximo de 500 UUIDs válidos") as raised:
            _parse_excel_input(_make_xlsx(rows))
        self.assertEqual(raised.exception.status_code, 413)

    def test_batch_endpoint_rejects_501_before_any_diverza_call(self):
        """El rechazo de tamaño ocurre antes de crear el stream o sus workers."""
        rows = [
            {
                "UUID": f"00000000-0000-4000-8000-{number:012d}",
                "RFC emisor": "AAA",
                "RFC receptor": "BBB",
                "TotalCFDI": "1",
                "Motive": "01",
            }
            for number in range(501)
        ]
        put = AsyncMock()
        with (
            TestClient(app) as client,
            patch("httpx.AsyncClient.put", put),
        ):
            response = client.post(
                "/api/sat/enquiry/batch",
                files={
                    "file": (
                        "lote.xlsx",
                        _make_xlsx(rows),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn("máximo de 500 UUIDs válidos", response.json()["detail"])
        put.assert_not_called()


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class BatchEnquiryPoolTests(unittest.TestCase):
    def test_never_exceeds_worker_limit_and_preserves_indices(self):
        rows = [
            {"uuid": str(index), "rfc_emisor": "A", "rfc_receptor": "B", "total_cfdi": "1", "motive": "01"}
            for index in range(BATCH_ENQUIRY_WORKERS * 2)
        ]
        active = 0
        maximum_active = 0

        async def fake_enquiry(client, idx, *args):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0)
            active -= 1
            return idx, {"uuid": str(idx)}

        async def collect():
            with patch("backend.app.routers.sat_enquiry._enquiry_indexed", side_effect=fake_enquiry):
                return [
                    result async for result in _batch_enquiry_results(MagicMock(), rows, "tenant")
                ]

        results = asyncio.run(collect())
        self.assertLessEqual(maximum_active, BATCH_ENQUIRY_WORKERS)
        self.assertEqual(sorted(index for index, _ in results), list(range(len(rows))))


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class SingleEnquiryEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_returns_404_when_rfc_not_configured(self):
        with patch("backend.app.routers.sat_enquiry.get_cred", return_value=None):
            resp = self.client.post(
                "/api/sat/enquiry",
                json={
                    "uuid": "aaa11111-1111-4111-8111-111111111111",
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
                    "uuid": "a1b2c3d4-e5f6-4a7b-8c9d-ef1234567890",
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


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class DiverzaSsrfTests(unittest.TestCase):
    """Hallazgo #38: el UUID se interpola en una URL de Diverza que se llama
    AUTENTICADA con el credential_id/credential_token del emisor. httpx
    normaliza '../' según RFC 3986, así que sin validar la forma un uuid de
    '../../../admin' saca la petición del prefijo /api/v2/documents.

    Este archivo fija las dos mitades: que la validación reconoce un UUID real
    y rechaza los ataques, y que _call_diverza nunca llega a hacer la petición
    con un uuid inválido.
    """

    def test_acepta_uuid_canonico_en_ambas_cajas(self):
        for valido in (
            "a1b2c3d4-e5f6-4a7b-8c9d-ef1234567890",
            "A1B2C3D4-E5F6-4A7B-8C9D-EF1234567890",  # el SAT los emite en mayúsculas
        ):
            with self.subTest(uuid=valido):
                self.assertTrue(_is_uuid(valido))

    def test_rechaza_traversal_y_basura(self):
        for malo in (
            "../../../admin",
            "..%2f..%2fadmin",
            "a1b2c3d4-e5f6-4a7b-8c9d-ef1234567890/../../admin",
            # 32 hex seguidos: detect-secrets lo marca como "Hex High Entropy
            # String". Es un UUID inventado para esta prueba, no un secreto.
            "a1b2c3d4e5f64a7b8c9def1234567890",  # sin guiones  # pragma: allowlist secret
            "a1b2c3d4-e5f6-4a7b-8c9d-ef123456789",  # un dígito de menos
            "zzzzzzzz-e5f6-4a7b-8c9d-ef1234567890",  # no es hex
            "",
        ):
            with self.subTest(uuid=malo):
                self.assertFalse(_is_uuid(malo))

    def test_httpx_normalizaria_el_traversal_si_no_se_validara(self):
        """El ataque que justifica el fix, medido -- no supuesto."""
        atacada = str(httpx.URL(f"{_DIVERZA_BASE}/../../../admin/sat_cfdi_enquiry"))
        self.assertNotIn("/api/v2/documents/", atacada)
        self.assertEqual(atacada, "https://servicios.diverza.com/admin/sat_cfdi_enquiry")

    def test_call_diverza_no_hace_la_peticion_con_uuid_invalido(self):
        import asyncio

        from fastapi import HTTPException

        put = AsyncMock()
        with patch("httpx.AsyncClient.put", put):
            async def run():
                async with httpx.AsyncClient() as client:
                    await _call_diverza(client, "../../../admin", {"a": 1})

            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(run())

        self.assertEqual(ctx.exception.status_code, 400)
        put.assert_not_called()  # lo que importa: nunca salió de la máquina
