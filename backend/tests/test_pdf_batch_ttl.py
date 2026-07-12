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


if __name__ == "__main__":
    unittest.main()
