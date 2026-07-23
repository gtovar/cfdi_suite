from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from backend.app.routers import pdf as pdf_router
except ModuleNotFoundError as error:
    pdf_router = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


def _run(coro):
    return asyncio.run(coro)


@unittest.skipIf(pdf_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class BatchMetadataTtlTests(unittest.TestCase):
    """Las claves de metadata de un batch (batch_ids, extracting_total,
    ready_recent, done_count, error_count) deben vivir tanto como el
    lifecycle real de GCS (24h, Fase 1) — no los 3600s (1h) originales.
    Con TTL corto, un batch terminado hace más de 1h pero cuyos PDFs
    todavía existen en Storage se reporta como "Lote no encontrado".
    """

    def setUp(self) -> None:
        self.assertEqual(
            pdf_router.BATCH_METADATA_TTL_SECONDS,
            86400,
            "el TTL objetivo debe alinearse al lifecycle de GCS confirmado en Fase 1",
        )

    def test_publish_batch_tick_sets_counter_ttl_to_24h(self) -> None:
        with (
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "publish_batch_progress"),
        ):
            mock_redis.incr = AsyncMock()
            mock_redis.expire = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)  # sin total -> corta rápido
            _run(pdf_router._publish_batch_tick("batch-1"))

        mock_redis.expire.assert_any_call(
            "pdf:done_count:batch-1", pdf_router.BATCH_METADATA_TTL_SECONDS
        )

    def test_process_zip_in_background_sets_extracting_total_and_batch_ids_ttl(self) -> None:
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.xml", "<xml/>")
        zip_bytes = buf.getvalue()

        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        def fake_download_to_filename(path):
            with open(path, "wb") as fh:
                fh.write(zip_bytes)

        mock_blob.download_to_filename.side_effect = fake_download_to_filename

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "enqueue_pdf_generation"),
        ):
            mock_redis.set = AsyncMock()
            pipe_cm = MagicMock()
            pipe_cm.__aenter__ = AsyncMock(return_value=pipe_cm)
            pipe_cm.__aexit__ = AsyncMock(return_value=False)
            pipe_cm.set = MagicMock()
            pipe_cm.sadd = MagicMock()
            pipe_cm.expire = MagicMock()
            pipe_cm.execute = AsyncMock()
            mock_redis.pipeline = MagicMock(return_value=pipe_cm)
            mock_redis.delete = AsyncMock()

            _run(pdf_router.process_zip_in_background("uploads/some.zip", "batch-2", "default"))

        mock_redis.set.assert_any_call(
            "pdf:extracting_total:batch-2", 1, ex=pdf_router.BATCH_METADATA_TTL_SECONDS
        )
        pipe_cm.expire.assert_any_call(
            "pdf:batch_ids:batch-2", pdf_router.BATCH_METADATA_TTL_SECONDS
        )

    def test_start_pdf_zip_generation_direct_path_sets_ttl(self) -> None:
        """Cubre el segundo camino de extracción (~283-346): subida directa
        vía UploadFile, sin pasar por Cloud Tasks/GCS de fondo."""
        import io
        import zipfile

        from fastapi.testclient import TestClient

        from backend.app.main import app

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.xml", "<xml/>")
        zip_bytes = buf.getvalue()

        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "enqueue_pdf_generation"),
        ):
            mock_redis.set = AsyncMock()
            mock_redis.sadd = AsyncMock()
            mock_redis.expire = AsyncMock()
            pipe_cm = MagicMock()
            pipe_cm.__aenter__ = AsyncMock(return_value=pipe_cm)
            pipe_cm.__aexit__ = AsyncMock(return_value=False)
            pipe_cm.set = MagicMock()
            pipe_cm.execute = AsyncMock()
            mock_redis.pipeline = MagicMock(return_value=pipe_cm)

            client = TestClient(app)
            response = client.post(
                "/api/cfdi/pdf/start-zip",
                files={"file": ("batch.zip", zip_bytes, "application/zip")},
            )

        self.assertEqual(response.status_code, 200)
        mock_redis.set.assert_any_call(
            unittest.mock.ANY, 1, ex=pdf_router.BATCH_METADATA_TTL_SECONDS
        )
        mock_redis.expire.assert_any_call(
            unittest.mock.ANY, pdf_router.BATCH_METADATA_TTL_SECONDS
        )

    def test_internal_generate_pdf_sets_ready_recent_ttl(self) -> None:
        from backend.app.routers.pdf import GeneratePdfPayload

        mock_request = MagicMock()
        mock_request.headers = {"x-cloudtasks-queuename": "pdf-generator-queue"}

        payload = GeneratePdfPayload(
            job_id="job-9", xml_b64="", template_id="default", batch_id="batch-3"
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
            patch.object(pdf_router, "publish_batch_progress"),
        ):
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock()
            mock_redis.delete = AsyncMock()
            mock_redis.rpush = AsyncMock()
            mock_redis.expire = AsyncMock()
            mock_redis.incr = AsyncMock()

            _run(pdf_router.internal_generate_pdf(payload, mock_request))

        mock_redis.expire.assert_any_call(
            "pdf:ready_recent:batch-3", pdf_router.BATCH_METADATA_TTL_SECONDS
        )
        mock_redis.set.assert_any_call(
            "pdf:status:job-9", b"done", ex=pdf_router.BATCH_METADATA_TTL_SECONDS
        )

    def test_internal_generate_pdf_xml_missing_sets_error_status_ttl_to_24h(self) -> None:
        """Estado terminal ("error", XML ya no existe ni en Redis ni GCS) debe
        vivir tanto como pdf:batch_ids — si expira antes (era ex=1800, 30 min),
        _batch_progress_snapshot ve este job como "pending" para siempre y el
        batch nunca reporta "done" dentro de la ventana de 24h de Fase 2."""
        from backend.app.routers.pdf import GeneratePdfPayload

        mock_request = MagicMock()
        mock_request.headers = {"x-cloudtasks-queuename": "pdf-generator-queue"}
        payload = GeneratePdfPayload(
            job_id="job-missing", xml_b64="", template_id="default", batch_id="batch-4"
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
            patch.object(pdf_router, "publish_batch_progress"),
        ):
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock()
            mock_redis.incr = AsyncMock()
            mock_redis.expire = AsyncMock()

            _run(pdf_router.internal_generate_pdf(payload, mock_request))

        mock_redis.set.assert_any_call(
            "pdf:status:job-missing", b"error", ex=pdf_router.BATCH_METADATA_TTL_SECONDS
        )

    def test_internal_generate_pdf_generation_failure_sets_error_status_ttl_to_24h(self) -> None:
        from backend.app.routers.pdf import GeneratePdfPayload

        mock_request = MagicMock()
        mock_request.headers = {"x-cloudtasks-queuename": "pdf-generator-queue"}
        payload = GeneratePdfPayload(
            job_id="job-boom", xml_b64="", template_id="default", batch_id=None
        )

        mock_blob_xml = MagicMock()
        mock_blob_xml.exists.return_value = True
        mock_blob_xml.download_as_bytes.return_value = b"<xml/>"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob_xml
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        from fastapi import HTTPException

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "generate", side_effect=RuntimeError("motor de render colapsó")),
            patch.object(pdf_router, "PDF_PROCESS_POOL", None),
        ):
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock()

            # El endpoint re-lanza como HTTPException 500 tras marcar el
            # status — eso es esperado, lo relevante aquí es el TTL grabado.
            with self.assertRaises(HTTPException):
                _run(pdf_router.internal_generate_pdf(payload, mock_request))

        mock_redis.set.assert_any_call(
            "pdf:status:job-boom", b"error", ex=pdf_router.BATCH_METADATA_TTL_SECONDS
        )

    def test_pdf_se_genera_y_sube_aunque_redis_este_agotado(self) -> None:
        """El caso central del incidente 2026-07-23: la cuota de Upstash
        agotada en la escritura de status "converting" NO debe impedir que
        el PDF se genere y se suba a GCS -- la respuesta debe seguir siendo
        200, no 500 (ver Paso 1 de
        docs/plan-implementacion-resiliencia-redis-2026-07-23.md)."""
        import redis.exceptions

        from backend.app.routers.pdf import GeneratePdfPayload

        mock_request = MagicMock()
        mock_request.headers = {"x-cloudtasks-queuename": "pdf-generator-queue"}
        payload = GeneratePdfPayload(
            job_id="job-degraded", xml_b64="", template_id="default", batch_id=None
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
        ):
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock(
                side_effect=redis.exceptions.ResponseError(
                    "max requests limit exceeded. Limit: 500000, Usage: 500000."
                )
            )
            mock_redis.delete = AsyncMock()

            result = _run(pdf_router.internal_generate_pdf(payload, mock_request))

        self.assertEqual(result, {"status": "success", "message": "PDF generado"})
        mock_blob_pdf.upload_from_string.assert_called_once_with(
            b"%PDF-fake", content_type="application/pdf"
        )

    def test_direct_path_enqueue_failure_sets_error_status_ttl_to_24h(self) -> None:
        """start_pdf_zip_generation (~283-346): si Cloud Tasks rechaza el
        encolado, el job nunca progresará — su status "error" debe vivir
        24h, igual que pdf:batch_ids, no los 1800s (30 min) originales."""
        import io
        import zipfile

        from fastapi.testclient import TestClient

        from backend.app.main import app

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.xml", "<xml/>")
        zip_bytes = buf.getvalue()

        mock_bucket = MagicMock()
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "enqueue_pdf_generation", side_effect=RuntimeError("cloud tasks down")),
        ):
            mock_redis.set = AsyncMock()
            mock_redis.sadd = AsyncMock()
            mock_redis.expire = AsyncMock()
            pipe_cm = MagicMock()
            pipe_cm.__aenter__ = AsyncMock(return_value=pipe_cm)
            pipe_cm.__aexit__ = AsyncMock(return_value=False)
            pipe_cm.set = MagicMock()
            pipe_cm.execute = AsyncMock()
            mock_redis.pipeline = MagicMock(return_value=pipe_cm)

            client = TestClient(app)
            client.post(
                "/api/cfdi/pdf/start-zip",
                files={"file": ("batch.zip", zip_bytes, "application/zip")},
            )

        mock_redis.set.assert_any_call(
            unittest.mock.ANY, b"error", ex=pdf_router.BATCH_METADATA_TTL_SECONDS
        )

    def test_background_path_enqueue_failure_sets_error_status_ttl_to_24h(self) -> None:
        """process_zip_in_background/flush_chunk: mismo caso que el test
        anterior, para el segundo camino de extracción (Cloud Tasks)."""
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.xml", "<xml/>")
        zip_bytes = buf.getvalue()

        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        def fake_download_to_filename(path):
            with open(path, "wb") as fh:
                fh.write(zip_bytes)

        mock_blob.download_to_filename.side_effect = fake_download_to_filename

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "enqueue_pdf_generation", side_effect=RuntimeError("cloud tasks down")),
        ):
            mock_redis.set = AsyncMock()
            pipe_cm = MagicMock()
            pipe_cm.__aenter__ = AsyncMock(return_value=pipe_cm)
            pipe_cm.__aexit__ = AsyncMock(return_value=False)
            pipe_cm.set = MagicMock()
            pipe_cm.sadd = MagicMock()
            pipe_cm.expire = MagicMock()
            pipe_cm.execute = AsyncMock()
            mock_redis.pipeline = MagicMock(return_value=pipe_cm)
            mock_redis.delete = AsyncMock()

            _run(pdf_router.process_zip_in_background("uploads/some.zip", "batch-5", "default"))

        mock_redis.set.assert_any_call(
            unittest.mock.ANY, b"error", ex=pdf_router.BATCH_METADATA_TTL_SECONDS
        )

    def test_process_zip_in_background_skips_when_lock_already_held(self) -> None:
        """Encontrado 2026-07-12 auditando logs reales de Cloud Run: una
        extracción que tarda más que el dispatch deadline de Cloud Tasks
        (~10 min) dispara un reintento MIENTRAS la primera sigue corriendo,
        duplicando descarga+subida en la misma instancia al mismo tiempo. El
        lock de idempotencia (`pdf:extracting_lock:{batch_id}`, SET NX) debe
        hacer que ese reintento se aborte de inmediato, sin tocar GCS."""
        mock_storage_client = MagicMock()

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
        ):
            mock_redis.set = AsyncMock(return_value=False)  # SET NX no adquirido

            ran = _run(pdf_router.process_zip_in_background("uploads/some.zip", "batch-lock", "default"))

        self.assertFalse(ran)
        mock_redis.set.assert_awaited_once_with(
            "pdf:extracting_lock:batch-lock", "1", nx=True, ex=pdf_router.EXTRACTION_LOCK_TTL_SECONDS
        )
        # No debe haber tocado GCS en absoluto si el lock no se adquirió.
        mock_storage_client.bucket.assert_not_called()

    def _make_zip_info(self, filename: str):
        import zipfile
        return zipfile.ZipInfo(filename=filename)

    def _mock_redis_for_remote_path(self):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)  # lock adquirido
        mock_redis.delete = AsyncMock()
        pipe_cm = MagicMock()
        pipe_cm.__aenter__ = AsyncMock(return_value=pipe_cm)
        pipe_cm.__aexit__ = AsyncMock(return_value=False)
        pipe_cm.set = MagicMock()
        pipe_cm.sadd = MagicMock()
        pipe_cm.expire = MagicMock()
        pipe_cm.execute = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=pipe_cm)
        return mock_redis, pipe_cm

    def test_remote_zip_shard_read_activo_no_descarga_el_zip_completo(self) -> None:
        """Con REMOTE_ZIP_SHARD_READ=true y un batch que sí califica para el
        Job de shards: nunca debe llamar blob.download_to_filename (nunca
        baja el ZIP completo), nunca debe subir nada a xml_temp/, sí debe
        llamar trigger_batch_shard_job con el gcs_path, y NO debe borrar el
        ZIP original (decisión de diseño: se deja al lifecycle de GCS)."""
        fake_infolist = [self._make_zip_info(f"factura_{i}.xml") for i in range(30)]
        mock_rz = MagicMock()
        mock_rz.infolist.return_value = fake_infolist
        mock_rz.close = MagicMock()

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        mock_redis, pipe_cm = self._mock_redis_for_remote_path()

        with (
            patch.object(pdf_router, "REMOTE_ZIP_SHARD_READ", True),
            patch.object(pdf_router, "should_use_batch_job", return_value=True),
            patch.object(pdf_router, "trigger_batch_shard_job", return_value="op-name") as mock_trigger,
            patch.object(pdf_router, "RemoteZip", return_value=mock_rz),
            patch.object(pdf_router, "get_gcs_authorized_session", return_value=MagicMock()),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router, "publish_batch_progress"),
        ):
            ran = _run(pdf_router.process_zip_in_background("uploads/batch-remote.zip", "batch-remote", "default"))

        self.assertTrue(ran)
        mock_blob.download_to_filename.assert_not_called()
        for call in mock_bucket.blob.call_args_list:
            self.assertNotIn("xml_temp/", call.args[0] if call.args else "")
        mock_trigger.assert_called_once_with(
            "batch-remote", 30, "default", "uploads/batch-remote.zip"
        )
        mock_blob.delete.assert_not_called()
        pipe_cm.sadd.assert_called_once()
        self.assertEqual(pipe_cm.sadd.call_args.args[0], "pdf:batch_ids:batch-remote")

    def test_remote_zip_shard_read_batch_chico_cae_al_camino_de_siempre(self) -> None:
        """Con el interruptor prendido pero should_use_batch_job=False (batch
        muy chico): debe caer al camino de descarga completa de siempre, sin
        haber disparado el Job ni tocado pdf:batch_ids."""
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.xml", "<xml/>")
        zip_bytes = buf.getvalue()

        fake_infolist = [self._make_zip_info("a.xml")]
        mock_rz = MagicMock()
        mock_rz.infolist.return_value = fake_infolist
        mock_rz.close = MagicMock()

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        def fake_download_to_filename(path):
            with open(path, "wb") as fh:
                fh.write(zip_bytes)

        mock_blob.download_to_filename.side_effect = fake_download_to_filename
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        mock_redis, _ = self._mock_redis_for_remote_path()
        mock_redis.scard = AsyncMock(return_value=1)

        with (
            patch.object(pdf_router, "REMOTE_ZIP_SHARD_READ", True),
            patch.object(pdf_router, "should_use_batch_job", return_value=False),
            patch.object(pdf_router, "trigger_batch_shard_job") as mock_trigger,
            patch.object(pdf_router, "RemoteZip", return_value=mock_rz),
            patch.object(pdf_router, "get_gcs_authorized_session", return_value=MagicMock()),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router, "enqueue_pdf_generation"),
        ):
            ran = _run(pdf_router.process_zip_in_background("uploads/batch-chico.zip", "batch-chico", "default"))

        self.assertTrue(ran)
        mock_trigger.assert_not_called()
        # Cayó al camino de siempre: sí descargó el ZIP completo.
        mock_blob.download_to_filename.assert_called_once()

    def test_remote_zip_shard_read_apagado_por_defecto(self) -> None:
        self.assertFalse(pdf_router.REMOTE_ZIP_SHARD_READ)


if __name__ == "__main__":
    unittest.main()
