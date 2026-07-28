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
    pdf:status:*) deben vivir tanto como el lifecycle real de GCS (24h,
    Fase 1) — no los 3600s (1h) originales. Con TTL corto, un batch
    terminado hace más de 1h pero cuyos PDFs todavía existen en Storage se
    reporta como "Lote no encontrado".
    """

    def setUp(self) -> None:
        self.assertEqual(
            pdf_router.BATCH_METADATA_TTL_SECONDS,
            86400,
            "el TTL objetivo debe alinearse al lifecycle de GCS confirmado en Fase 1",
        )
        # Desde el hallazgo #2, /internal/generate-pdf exige un token OIDC de
        # Cloud Tasks y ya no le basta el header (que era spoofeable). Estos
        # tests son sobre TTL de Redis, no sobre autenticación: se dan por
        # autenticados. Que el guard rechace de verdad lo cubre
        # test_internal_auth.py, que sí ejercita internal_auth.verify_cloud_tasks.
        _auth = patch.object(pdf_router, "verify_cloud_tasks", return_value=True)
        _auth.start()
        self.addCleanup(_auth.stop)
        # Los casos de esta clase prueban TTL/extracción, no metadata GCS.
        # La defensa de tamaño tiene pruebas dedicadas en test_zip_upload_policy.
        _zip_size = patch.object(pdf_router, "validate_gcs_zip_size", return_value=1)
        _zip_size.start()
        self.addCleanup(_zip_size.stop)

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

            _run(pdf_router.process_zip_in_background("uploads/123e4567-e89b-12d3-a456-426614174000.zip", "batch-2", "default"))

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

    def test_start_zip_gcs_only_accepts_request_upload_path_shape(self) -> None:
        """El endpoint público no puede convertir una ruta arbitraria en una
        tarea interna capaz de descargar y borrar cualquier objeto del bucket."""
        valid_path = "uploads/123e4567-e89b-12d3-a456-426614174000.zip"

        with (
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "enqueue_zip_extraction") as mock_enqueue,
        ):
            mock_redis.set = AsyncMock()
            result = _run(pdf_router.start_pdf_zip_gcs_generation(
                pdf_router.ProcessGcsZipPayload(gcsPath=valid_path)
            ))

        self.assertIn("batchId", result)
        mock_enqueue.assert_called_once()
        self.assertEqual(mock_enqueue.call_args.kwargs["gcs_path"], valid_path)

        for invalid_path in (
            "credenciales/default-tenant/emisores.enc",
            "uploads/../credenciales/default-tenant/emisores.enc",
            "uploads/123e4567-e89b-12d3-a456-426614174000.xml",
            "uploads/not-a-uuid.zip",
            "/uploads/123e4567-e89b-12d3-a456-426614174000.zip",
        ):
            with self.subTest(gcs_path=invalid_path), self.assertRaises(pdf_router.HTTPException) as error:
                _run(pdf_router.start_pdf_zip_gcs_generation(
                    pdf_router.ProcessGcsZipPayload(gcsPath=invalid_path)
                ))
            self.assertEqual(error.exception.status_code, 400)

    def test_internal_extract_zip_revalidates_cloud_task_payload(self) -> None:
        payload = pdf_router.ExtractZipPayload(
            gcs_path="credenciales/default-tenant/emisores.enc",
            batch_id="batch-malicioso",
            template_id="default",
        )
        with (
            patch.object(pdf_router, "verify_cloud_tasks", return_value=True),
            patch.object(pdf_router, "process_zip_in_background") as mock_process,
        ):
            with self.assertRaises(pdf_router.HTTPException) as error:
                _run(pdf_router.internal_extract_zip(payload, MagicMock()))

        self.assertEqual(error.exception.status_code, 400)
        mock_process.assert_not_called()

    def test_process_zip_never_opens_or_deletes_credentials_path(self) -> None:
        """Guardia de regresión del efecto destructivo: incluso si alguien
        llama el procesador directo, la ruta de credenciales no llega a GCS."""
        mock_storage_client = MagicMock()
        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
        ):
            with self.assertRaises(pdf_router.HTTPException) as error:
                _run(pdf_router.process_zip_in_background(
                    "credenciales/default-tenant/emisores.enc", "batch-malicioso", "default"
                ))

        self.assertEqual(error.exception.status_code, 400)
        mock_storage_client.bucket.assert_not_called()
        mock_redis.set.assert_not_called()

    def test_invalid_zip_with_owned_path_keeps_cleanup_scoped_to_uploads(self) -> None:
        """Un ZIP corrupto sigue el manejo de error existente, pero el único
        objeto elegible para cleanup es el ZIP temporal con UUID validado."""
        valid_path = "uploads/123e4567-e89b-12d3-a456-426614174003.zip"
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        def write_invalid_zip(path):
            with open(path, "wb") as file:
                file.write(b"not a zip")

        mock_blob.download_to_filename.side_effect = write_invalid_zip
        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
        ):
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis.delete = AsyncMock()
            ran = _run(pdf_router.process_zip_in_background(valid_path, "batch-invalid-zip", "default"))

        self.assertTrue(ran)
        mock_bucket.blob.assert_called_with(valid_path)
        mock_blob.delete.assert_called_once()

    def test_internal_generate_pdf_sets_status_ttl(self) -> None:
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
        ):
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.set = AsyncMock()
            mock_redis.delete = AsyncMock()

            _run(pdf_router.internal_generate_pdf(payload, mock_request))

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

    def test_start_pdf_generation_encola_aunque_redis_este_agotado(self) -> None:
        """Hallazgo en vivo el 23 de julio, reproduciendo el incidente real
        con el navegador contra producción: start_pdf_generation (pdf.py:234,
        camino individual, no ZIP) escribía a Redis SIN protección antes de
        encolar la tarea real -- el mismo defecto de Paso 1, en una función
        que el plan original no cubría. Con la cuota de Redis agotada, el
        XML debe subirse a GCS y la tarea debe encolarse igual (202/200,
        jobId presente), no un 500."""
        import io

        from fastapi.testclient import TestClient

        from backend.app.main import app

        mock_xml_blob = MagicMock()
        mock_metadata_blob = MagicMock()
        mock_pdf_blob = MagicMock()
        for blob in (mock_xml_blob, mock_metadata_blob, mock_pdf_blob):
            blob.exists.return_value = False
        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = lambda path: (
            mock_metadata_blob if path.startswith(pdf_router.SINGLE_JOB_METADATA_PREFIX)
            else mock_pdf_blob if path.startswith("pdfs/") else mock_xml_blob
        )
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "enqueue_pdf_generation") as mock_enqueue,
        ):
            mock_redis.set = AsyncMock(side_effect=RuntimeError(
                "max requests limit exceeded. Limit: 500000, Usage: 500000."
            ))

            client = TestClient(app)
            response = client.post(
                "/api/cfdi/pdf/start",
                files={"file": ("factura.xml", io.BytesIO(b"<xml/>"), "application/xml")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("jobId", response.json())
        mock_xml_blob.upload_from_string.assert_called_once()
        mock_enqueue.assert_called_once()

    def test_start_pdf_generation_limpia_xml_y_devuelve_503_si_no_encola(self) -> None:
        import io

        from fastapi.testclient import TestClient

        from backend.app.main import app

        mock_blob = MagicMock()
        mock_metadata_blob = MagicMock()
        mock_pdf_blob = MagicMock()
        for blob in (mock_blob, mock_metadata_blob, mock_pdf_blob):
            blob.exists.return_value = False
        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = lambda path: (
            mock_metadata_blob if path.startswith(pdf_router.SINGLE_JOB_METADATA_PREFIX)
            else mock_pdf_blob if path.startswith("pdfs/") else mock_blob
        )
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "enqueue_pdf_generation", side_effect=RuntimeError("tasks unavailable")),
        ):
            mock_redis.set = AsyncMock()
            response = TestClient(app).post(
                "/api/cfdi/pdf/start",
                files={"file": ("factura.xml", io.BytesIO(b"<xml/>"), "application/xml")},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Servicio temporalmente no disponible", response.json()["detail"])
        mock_blob.delete.assert_called_once()

    def test_start_pdf_generation_conserva_xml_si_encolado_es_incierto(self) -> None:
        import io

        from fastapi.testclient import TestClient

        from backend.app.main import app
        from backend.app.services.task_dispatcher import TaskEnqueueUncertainError

        mock_blob = MagicMock()
        mock_metadata_blob = MagicMock()
        mock_pdf_blob = MagicMock()
        for blob in (mock_blob, mock_metadata_blob, mock_pdf_blob):
            blob.exists.return_value = False
        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = lambda path: (
            mock_metadata_blob if path.startswith(pdf_router.SINGLE_JOB_METADATA_PREFIX)
            else mock_pdf_blob if path.startswith("pdfs/") else mock_blob
        )
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(
                pdf_router,
                "enqueue_pdf_generation",
                side_effect=TaskEnqueueUncertainError("timeout"),
            ),
        ):
            mock_redis.set = AsyncMock()
            response = TestClient(app).post(
                "/api/cfdi/pdf/start",
                files={"file": ("factura.xml", io.BytesIO(b"<xml/>"), "application/xml")},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "scheduling")
        self.assertIn("jobId", response.json())
        mock_blob.delete.assert_not_called()

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

            _run(pdf_router.process_zip_in_background("uploads/123e4567-e89b-12d3-a456-426614174000.zip", "batch-5", "default"))

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

            ran = _run(pdf_router.process_zip_in_background("uploads/123e4567-e89b-12d3-a456-426614174000.zip", "batch-lock", "default"))

        self.assertFalse(ran)
        mock_redis.set.assert_awaited_once_with(
            "pdf:extracting_lock:batch-lock", "1", nx=True, ex=pdf_router.EXTRACTION_LOCK_TTL_SECONDS
        )
        # No debe haber tocado GCS en absoluto si el lock no se adquirió.
        mock_storage_client.bucket.assert_not_called()

    def test_process_zip_in_background_continua_si_redis_no_responde_al_lock(self) -> None:
        """Verificado en vivo 2026-07-24 contra producción con la cuota de
        Redis realmente agotada: el lock fail-closed bloqueaba POR COMPLETO
        la conversión masiva vía ZIP (Cloud Tasks reintentando /internal/extract-zip
        para siempre sin llegar nunca al resto de la función). Decisión
        explícita del usuario: si Redis truena al intentar el lock (no si
        responde y dice que ya está tomado), se continúa de todas formas."""
        mock_storage_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch("tempfile.NamedTemporaryFile"),
            patch("zipfile.ZipFile") as mock_zipfile,
            patch("os.path.exists", return_value=False),
        ):
            mock_redis.set = AsyncMock(side_effect=ConnectionError("max requests limit exceeded"))
            mock_redis.delete = AsyncMock()
            mock_zip_instance = MagicMock()
            mock_zip_instance.infolist.return_value = []
            mock_zipfile.return_value.__enter__.return_value = mock_zip_instance

            ran = _run(pdf_router.process_zip_in_background("uploads/123e4567-e89b-12d3-a456-426614174000.zip", "batch-lock-down", "default"))

        # No debe abortar solo porque Redis truene al adquirir el lock -- debe
        # seguir hasta el final (batch vacío, pero SÍ corrió).
        self.assertTrue(ran)

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
        baja el ZIP completo), nunca debe subir contenido de XML individual a
        xml_temp/{job_id}.xml (la ruta remota evita mover ese contenido
        pesado por la red de esta instancia -- ver docstring de
        _try_remote_manifest_path), sí debe llamar trigger_batch_shard_job
        con el gcs_path, y NO debe borrar el ZIP original (decisión de
        diseño: se deja al lifecycle de GCS).

        Actualizado 2026-07-23 (auditoría de resiliencia): sí sube un
        manifiesto pequeño (job_id -> filename) a xml_temp/_manifest_{batch_id}.json
        -- reusa el prefijo xml_temp/ solo para heredar su regla de lifecycle
        de 1 día, no mueve contenido de XML. Ver _batch_manifest_blob."""
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
            patch.object(pdf_router, "publish_batch_signal"),
        ):
            ran = _run(pdf_router.process_zip_in_background("uploads/123e4567-e89b-12d3-a456-426614174001.zip", "batch-remote", "default"))

        self.assertTrue(ran)
        mock_blob.download_to_filename.assert_not_called()
        blob_paths = [call.args[0] for call in mock_bucket.blob.call_args_list if call.args]
        for path in blob_paths:
            if path.startswith("xml_temp/"):
                self.assertEqual(path, "xml_temp/_manifest_batch-remote.json")
        mock_trigger.assert_called_once_with(
            "batch-remote", 30, "default", "uploads/123e4567-e89b-12d3-a456-426614174001.zip"
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
            ran = _run(pdf_router.process_zip_in_background("uploads/123e4567-e89b-12d3-a456-426614174002.zip", "batch-chico", "default"))

        self.assertTrue(ran)
        mock_trigger.assert_not_called()
        # Cayó al camino de siempre: sí descargó el ZIP completo.
        mock_blob.download_to_filename.assert_called_once()

    def test_remote_zip_shard_read_apagado_por_defecto(self) -> None:
        self.assertFalse(pdf_router.REMOTE_ZIP_SHARD_READ)


if __name__ == "__main__":
    unittest.main()
