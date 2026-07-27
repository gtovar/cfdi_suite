"""test_batch_signal_resilience.py — cobertura del aviso de Pusher que NO
depende de Redis (publish_batch_signal, app/services/realtime.py).

Hallazgo 2026-07-25 (verificado en vivo en producción, con la cuota de
Upstash genuinamente agotada): `_publish_batch_tick`/`publish_batch_tick`
(entonces existentes) vivían completos dentro de `safe_redis_call` en
pdf.py/batch_shard_worker.py -- si Redis estaba degradado, esa llamada se
cortaba ANTES de intentar Pusher, y el usuario se quedaba sin ningún aviso en
vivo hasta el respaldo periódico de 75s del frontend (`fetchSnapshot`,
pdf-download.ts). `publish_batch_signal` fue el fix: un aviso mínimo, SIEMPRE
intentado, sin ninguna lectura de Redis. 2026-07-25 (rediseño hint-only, ver
PROJECT_STATE.md): `publish_batch_tick`/`publish_batch_progress` se
eliminaron por completo -- `publish_batch_signal` es hoy el ÚNICO evento en
vivo, no solo el de respaldo.
"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from backend.app.routers import pdf as pdf_router
    from backend.app.services import realtime
except ModuleNotFoundError as error:
    pdf_router = None
    realtime = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


def _run(coro):
    return asyncio.run(coro)


@unittest.skipIf(realtime is None, f"backend no disponible: {_IMPORT_ERROR}")
class PublishBatchSignalUnitTests(unittest.TestCase):
    """publish_batch_signal en sí -- sin Redis en absoluto en su firma."""

    def setUp(self) -> None:
        # Throttle en memoria de módulo -- aislar cada test del anterior.
        realtime._last_signal_at.clear()

    def test_dispara_pusher_con_payload_pobre(self) -> None:
        mock_client = MagicMock()
        with patch.object(realtime, "get_pusher", return_value=mock_client):
            realtime.publish_batch_signal("batch-1", "job_done")

        mock_client.trigger.assert_called_once_with(
            "private-pdf-batch-batch-1", "signal", {"kind": "job_done"}
        )

    def test_sin_cliente_pusher_no_truena(self) -> None:
        with patch.object(realtime, "get_pusher", return_value=None):
            realtime.publish_batch_signal("batch-1", "job_done")  # no debe lanzar

    def test_trigger_que_truena_no_propaga(self) -> None:
        mock_client = MagicMock()
        mock_client.trigger.side_effect = RuntimeError("Pusher caído")
        with patch.object(realtime, "get_pusher", return_value=mock_client):
            realtime.publish_batch_signal("batch-1", "job_done")  # no debe lanzar

    def test_throttle_job_done_no_dispara_dos_veces_seguidas(self) -> None:
        mock_client = MagicMock()
        with (
            patch.object(realtime, "get_pusher", return_value=mock_client),
            patch.object(realtime.time, "monotonic", side_effect=[100.0, 100.5]),
        ):
            realtime.publish_batch_signal("batch-1", "job_done")
            realtime.publish_batch_signal("batch-1", "job_done")

        self.assertEqual(mock_client.trigger.call_count, 1)

    def test_throttle_expira_tras_el_intervalo(self) -> None:
        mock_client = MagicMock()
        with (
            patch.object(realtime, "get_pusher", return_value=mock_client),
            patch.object(
                realtime.time, "monotonic",
                side_effect=[100.0, 100.0 + realtime._SIGNAL_MIN_INTERVAL_SECONDS + 0.1],
            ),
        ):
            realtime.publish_batch_signal("batch-1", "job_done")
            realtime.publish_batch_signal("batch-1", "job_done")

        self.assertEqual(mock_client.trigger.call_count, 2)

    def test_job_error_nunca_se_frena_por_el_throttle(self) -> None:
        """Mismo criterio que definitive_error en el payload rico: un error
        siempre se avisa, no compite con el throttle de 'job_done'."""
        mock_client = MagicMock()
        with (
            patch.object(realtime, "get_pusher", return_value=mock_client),
            patch.object(realtime.time, "monotonic", side_effect=[100.0, 100.1, 100.2]),
        ):
            realtime.publish_batch_signal("batch-1", "job_done")
            realtime.publish_batch_signal("batch-1", "job_error")
            realtime.publish_batch_signal("batch-1", "job_error")

        self.assertEqual(mock_client.trigger.call_count, 3)

    def test_batches_distintos_no_comparten_throttle(self) -> None:
        mock_client = MagicMock()
        with (
            patch.object(realtime, "get_pusher", return_value=mock_client),
            patch.object(realtime.time, "monotonic", side_effect=[100.0, 100.1]),
        ):
            realtime.publish_batch_signal("batch-1", "job_done")
            realtime.publish_batch_signal("batch-2", "job_done")

        self.assertEqual(mock_client.trigger.call_count, 2)


@unittest.skipIf(pdf_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class InternalGeneratePdfSignalResilienceTests(unittest.TestCase):
    """El caso real: con Redis completamente caído (cada llamada truena),
    publish_batch_signal debe seguir disparándose -- a diferencia de
    _publish_batch_tick (el payload rico), que sí se pierde en este
    escenario porque vive dentro de safe_redis_call."""

    def setUp(self) -> None:
        realtime._last_signal_at.clear()
        # Ver la nota de test_pdf_batch_ttl.py: desde el hallazgo #2 el
        # endpoint exige token OIDC. Estos tests son sobre la señal de Pusher
        # con Redis caído, no sobre autenticación.
        _auth = patch.object(pdf_router, "verify_cloud_tasks", return_value=True)
        _auth.start()
        self.addCleanup(_auth.stop)

    def test_success_path_avisa_aunque_redis_truene_en_todo(self) -> None:
        from backend.app.routers.pdf import GeneratePdfPayload

        mock_request = MagicMock()
        mock_request.headers = {"x-cloudtasks-queuename": "pdf-generator-queue"}
        payload = GeneratePdfPayload(
            job_id="job-resiliente", xml_b64="", template_id="default", batch_id="batch-signal"
        )

        mock_blob_xml = MagicMock()
        mock_blob_xml.exists.return_value = True
        mock_blob_xml.download_as_bytes.return_value = b"<xml/>"
        mock_blob_pdf = MagicMock()
        mock_bucket = MagicMock()

        def bucket_blob(path):
            return mock_blob_xml if path.startswith("xml_temp/") else mock_blob_pdf

        mock_bucket.blob.side_effect = bucket_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "generate", return_value=b"%PDF-fake"),
            patch.object(pdf_router, "PDF_PROCESS_POOL", None),
            patch.object(pdf_router, "publish_batch_signal") as mock_signal,
        ):
            # Redis truena en CADA operación -- simula degradación total,
            # no solo un tick suelto. safe_redis_call atrapa esto y sigue
            # devolviendo None; publish_batch_signal no debe verse afectado
            # porque no pasa por ahí.
            error = RuntimeError("max requests limit exceeded")
            mock_redis.get = AsyncMock(side_effect=error)
            mock_redis.set = AsyncMock(side_effect=error)
            mock_redis.delete = AsyncMock(side_effect=error)
            mock_redis.rpush = AsyncMock(side_effect=error)
            mock_redis.expire = AsyncMock(side_effect=error)
            mock_redis.incr = AsyncMock(side_effect=error)

            _run(pdf_router.internal_generate_pdf(payload, mock_request))

        mock_signal.assert_called_once_with("batch-signal", "job_done")

    def test_xml_faltante_avisa_error_aunque_redis_truene_en_todo(self) -> None:
        from backend.app.routers.pdf import GeneratePdfPayload

        mock_request = MagicMock()
        mock_request.headers = {"x-cloudtasks-queuename": "pdf-generator-queue"}
        payload = GeneratePdfPayload(
            job_id="job-sin-xml", xml_b64="", template_id="default", batch_id="batch-signal-2"
        )

        mock_blob_xml = MagicMock()
        mock_blob_xml.exists.return_value = False
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob_xml
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "publish_batch_signal") as mock_signal,
        ):
            error = RuntimeError("max requests limit exceeded")
            mock_redis.get = AsyncMock(side_effect=error)
            mock_redis.set = AsyncMock(side_effect=error)
            mock_redis.incr = AsyncMock(side_effect=error)
            mock_redis.expire = AsyncMock(side_effect=error)

            _run(pdf_router.internal_generate_pdf(payload, mock_request))

        mock_signal.assert_called_once_with("batch-signal-2", "job_error")

    def test_sin_batch_id_no_avisa_nada(self) -> None:
        """PDF suelto (no batch) no tiene canal de Pusher que avisar --
        mismo criterio que ya aplica a _publish_batch_tick (if payload.batch_id)."""
        from backend.app.routers.pdf import GeneratePdfPayload

        mock_request = MagicMock()
        mock_request.headers = {"x-cloudtasks-queuename": "pdf-generator-queue"}
        payload = GeneratePdfPayload(
            job_id="job-suelto", xml_b64="", template_id="default", batch_id=None
        )

        mock_blob_xml = MagicMock()
        mock_blob_xml.exists.return_value = True
        mock_blob_xml.download_as_bytes.return_value = b"<xml/>"
        mock_blob_pdf = MagicMock()
        mock_bucket = MagicMock()

        def bucket_blob(path):
            return mock_blob_xml if path.startswith("xml_temp/") else mock_blob_pdf

        mock_bucket.blob.side_effect = bucket_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "generate", return_value=b"%PDF-fake"),
            patch.object(pdf_router, "PDF_PROCESS_POOL", None),
            patch.object(pdf_router, "publish_batch_signal") as mock_signal,
        ):
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock()
            mock_redis.delete = AsyncMock()

            _run(pdf_router.internal_generate_pdf(payload, mock_request))

        mock_signal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
