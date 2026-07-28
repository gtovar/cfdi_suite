"""test_batch_analysis_resilience.py — cobertura de la migración de
app.routers.batch (análisis de CFDI por lote) de Redis-como-almacén-de-XML a
GCS-como-almacén-durable.

Auditoría de resiliencia 2026-07-23 (ver PROJECT_STATE.md, decisión "Bucket 3"):
a diferencia del pipeline de PDFs, este router guardaba el contenido COMPLETO
de cada XML en Redis con TTL de 1h y sin ninguna copia de respaldo -- si
Upstash perdía esa llave antes de que Cloud Tasks la leyera, el archivo se
perdía para siempre. Ahora el XML (y el resultado ya calculado del análisis)
viven en GCS; Redis solo coordina contadores/progreso, best-effort.
"""
from __future__ import annotations

import asyncio
import io
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import UploadFile

try:
    from backend.app.routers import batch as batch_router
except ModuleNotFoundError as error:
    batch_router = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


def _run(coro):
    return asyncio.run(coro)


def _redis_down(*_args, **_kwargs):
    raise ConnectionError("Redis no responde (simulado)")


class _FakeRequest:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self):
        return self._payload


@unittest.skipIf(batch_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class BatchAnalyzeGcsDurabilityTests(unittest.TestCase):
    def test_sube_xml_a_gcs_sin_encolar_antes_de_la_suscripcion(self) -> None:
        mock_bucket = MagicMock()
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(batch_router, "redis_client") as mock_redis,
            patch.object(batch_router, "storage") as mock_storage_module,
            patch.object(batch_router, "enqueue_cfdi_analysis") as mock_enqueue,
        ):
            mock_storage_module.Client.return_value = mock_storage_client
            files = [UploadFile(filename="factura.xml", file=io.BytesIO(b"<cfdi/>"))]
            result = _run(batch_router.batch_analyze(files=files))

        batch_id = result["batch_id"]
        mock_bucket.blob.assert_any_call(f"xml_temp/analysis_{batch_id}/factura.xml")
        mock_enqueue.assert_not_called()
        self.assertEqual(result["status"], "ready")
        # El contenido del XML nunca se le pasa a Redis
        for call in mock_redis.set.call_args_list if mock_redis.set.called else []:
            self.assertNotIn("<cfdi/>", str(call))

    def test_batch_se_crea_igual_si_redis_falla_al_inicializar(self) -> None:
        """Si Redis truena al crear el hash de metadata (hmset), el batch
        igual se crea y el archivo igual se sube a GCS y queda listo para iniciar -- antes
        de este fix, Redis era el único lugar donde vivía el XML, así que un
        fallo aquí habría sido catastrófico; ahora es solo coordinación."""
        mock_bucket = MagicMock()
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(batch_router, "redis_client") as mock_redis,
            patch.object(batch_router, "storage") as mock_storage_module,
            patch.object(batch_router, "enqueue_cfdi_analysis") as mock_enqueue,
        ):
            mock_storage_module.Client.return_value = mock_storage_client
            mock_redis.hmset.side_effect = _redis_down
            mock_redis.expire.side_effect = _redis_down
            files = [UploadFile(filename="factura.xml", file=io.BytesIO(b"<cfdi/>"))]
            result = _run(batch_router.batch_analyze(files=files))

        self.assertEqual(result["status"], "ready")
        mock_enqueue.assert_not_called()
        mock_bucket.blob.return_value.upload_from_string.assert_called_once()


@unittest.skipIf(batch_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class StartBatchAnalysisTests(unittest.TestCase):
    def test_encola_xmls_despues_de_confirmar_suscripcion(self) -> None:
        batch_id = "2e4af825-2316-4c20-95d7-2641aa5a6771"
        xml_blob = MagicMock()
        xml_blob.name = f"xml_temp/analysis_{batch_id}/factura.xml"
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [xml_blob]
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(batch_router, "storage") as mock_storage_module,
            patch.object(batch_router, "enqueue_cfdi_analysis") as mock_enqueue,
        ):
            mock_storage_module.Client.return_value = mock_storage_client
            outcome = _run(batch_router.start_batch_analysis(batch_id))

        self.assertEqual(outcome["status"], "processing")
        self.assertFalse(outcome["already_started"])
        mock_enqueue.assert_called_once_with(batch_id, "factura.xml", xml_blob.name)

    def test_inicio_repetido_no_reencola_archivos(self) -> None:
        batch_id = "2e4af825-2316-4c20-95d7-2641aa5a6771"

        class PreconditionFailed(Exception):
            pass

        mock_bucket = MagicMock()
        xml_blob = MagicMock()
        xml_blob.name = f"xml_temp/analysis_{batch_id}/factura.xml"
        mock_bucket.list_blobs.return_value = [xml_blob]
        mock_bucket.blob.return_value.upload_from_string.side_effect = PreconditionFailed()
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(batch_router, "storage") as mock_storage_module,
            patch.object(batch_router, "enqueue_cfdi_analysis") as mock_enqueue,
        ):
            mock_storage_module.Client.return_value = mock_storage_client
            outcome = _run(batch_router.start_batch_analysis(batch_id))

        self.assertTrue(outcome["already_started"])
        mock_enqueue.assert_not_called()


@unittest.skipIf(batch_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class BatchWorkerTaskGcsDurabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        # Desde el hallazgo #2, /worker-task exige un token OIDC de Cloud Tasks
        # -- antes no tenía verificación de ningún tipo. Estos tests son sobre
        # la durabilidad en GCS, no sobre autenticación: se dan por
        # autenticados. Que el guard rechace de verdad (y que el guard de
        # gcs_path funcione) lo cubre test_internal_auth.py.
        _auth = patch.object(batch_router, "verify_cloud_tasks", return_value=True)
        _auth.start()
        self.addCleanup(_auth.stop)

    def test_lee_xml_de_gcs_y_persiste_resultado_ahi_antes_que_redis(self) -> None:
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.return_value = b"<cfdi/>"
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        fake_result = MagicMock()
        fake_result.issues = []
        fake_result.cfdi = {"findings": [], "total": "100.00", "fecha": "2026-07-23"}
        fake_result.ingresoRows = [{"rfcEmisor": "AAA010101AAA", "nombreEmisor": "Emisor", "rfcReceptor": "BBB010101BBB"}]
        fake_result.pagoRows = []
        fake_result.profile = "ingresos"

        with (
            patch.object(batch_router, "redis_client") as mock_redis,
            patch.object(batch_router, "storage") as mock_storage_module,
            patch.object(batch_router, "run_analyze_cfdi", return_value=fake_result),
        ):
            mock_storage_module.Client.return_value = mock_storage_client
            request = _FakeRequest({"batch_id": "batch-1", "filename": "factura.xml", "gcs_path": "xml_temp/analysis_batch-1/factura.xml"})
            outcome = _run(batch_router.batch_worker_task(request))

        self.assertEqual(outcome["status"], "processed")
        mock_bucket.blob.assert_any_call("xml_temp/analysis_results_batch-1/factura.xml.json")
        mock_blob.upload_from_string.assert_any_call(
            unittest.mock.ANY, content_type="application/json"
        )
        mock_redis.rpush.assert_called_once()
        mock_redis.hincrby.assert_called_once()

    def test_resultado_ya_calculado_no_se_pierde_si_redis_falla_al_reportar(self) -> None:
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.return_value = b"<cfdi/>"
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        fake_result = MagicMock()
        fake_result.issues = []
        fake_result.cfdi = {"findings": [], "total": "100.00", "fecha": "2026-07-23"}
        fake_result.ingresoRows = [{"rfcEmisor": "AAA010101AAA", "nombreEmisor": "Emisor", "rfcReceptor": "BBB010101BBB"}]
        fake_result.pagoRows = []
        fake_result.profile = "ingresos"

        with (
            patch.object(batch_router, "redis_client") as mock_redis,
            patch.object(batch_router, "storage") as mock_storage_module,
            patch.object(batch_router, "run_analyze_cfdi", return_value=fake_result),
        ):
            mock_storage_module.Client.return_value = mock_storage_client
            mock_redis.rpush.side_effect = _redis_down
            mock_redis.hincrby.side_effect = _redis_down
            request = _FakeRequest({"batch_id": "batch-1", "filename": "factura.xml", "gcs_path": "xml_temp/analysis_batch-1/factura.xml"})
            outcome = _run(batch_router.batch_worker_task(request))

        # El resultado ya se subió a GCS ANTES de intentar Redis -- el fallo
        # de rpush/hincrby (best-effort) no debe tumbar el webhook.
        self.assertEqual(outcome["status"], "processed")
        result_upload_calls = [
            call for call in mock_blob.upload_from_string.call_args_list
            if call.kwargs.get("content_type") == "application/json"
        ]
        self.assertEqual(len(result_upload_calls), 1)

    def test_payload_viejo_con_redis_key_no_causa_keyerror(self) -> None:
        """Tareas ya encoladas en Cloud Tasks ANTES del deploy que migró
        Redis->GCS siguen trayendo "redis_key" en vez de "gcs_path" -- deben
        degradar a un error limpio (mismo formato que "no encontrado"), no un
        KeyError -> 500 -> reintento infinito durante la ventana del deploy."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.side_effect = Exception("no es una ruta de GCS válida")
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with patch.object(batch_router, "storage") as mock_storage_module:
            mock_storage_module.Client.return_value = mock_storage_client
            request = _FakeRequest({"batch_id": "batch-1", "filename": "factura.xml", "redis_key": "xml_payload:batch-1:factura.xml"})
            outcome = _run(batch_router.batch_worker_task(request))

        self.assertEqual(outcome["status"], "error")

    def test_xml_no_encontrado_en_gcs_reporta_error_sin_tronar(self) -> None:
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.side_effect = Exception("404 not found")
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(batch_router, "storage") as mock_storage_module,
        ):
            mock_storage_module.Client.return_value = mock_storage_client
            request = _FakeRequest({"batch_id": "batch-1", "filename": "factura.xml", "gcs_path": "xml_temp/analysis_batch-1/factura.xml"})
            outcome = _run(batch_router.batch_worker_task(request))

        self.assertEqual(outcome["status"], "error")


@unittest.skipIf(batch_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class GetBatchStatusGcsFallbackTests(unittest.TestCase):
    def test_reconstruye_desde_gcs_si_redis_no_responde(self) -> None:
        submitted_blobs = [MagicMock(), MagicMock(), MagicMock()]
        result_blob = MagicMock()
        result_blob.download_as_bytes.return_value = json.dumps({
            "filename": "a.xml", "status": "ok", "profile": "ingresos",
            "rfc_emisor": "", "rfc_receptor": "", "nombre_emisor": "",
            "total": "", "fecha": "", "findings_count": 0, "error": None,
        }).encode()

        def _list_blobs(prefix):
            if prefix == "xml_temp/analysis_batch-x/":
                return submitted_blobs
            if prefix == "xml_temp/analysis_results_batch-x/":
                return [result_blob]
            return []

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.side_effect = _list_blobs
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(batch_router, "redis_client") as mock_redis,
            patch.object(batch_router, "storage") as mock_storage_module,
        ):
            mock_storage_module.Client.return_value = mock_storage_client
            mock_redis.hgetall.side_effect = _redis_down
            response = _run(batch_router.get_batch_status("batch-x"))

        self.assertEqual(response["summary"]["total_files"], 3)
        self.assertEqual(response["summary"]["completed"], 1)

    def test_batch_realmente_inexistente_sigue_dando_404(self) -> None:
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(batch_router, "redis_client") as mock_redis,
            patch.object(batch_router, "storage") as mock_storage_module,
        ):
            mock_storage_module.Client.return_value = mock_storage_client
            mock_redis.hgetall.return_value = {}
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                _run(batch_router.get_batch_status("batch-nunca-existio"))
            self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
