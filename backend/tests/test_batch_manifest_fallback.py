"""test_batch_manifest_fallback.py — cobertura del respaldo en GCS para la
membresía de un batch chico (pdf:batch_ids) cuando Redis no responde.

Auditoría de resiliencia 2026-07-23 (ver PROJECT_STATE.md): _batch_progress_snapshot,
list_ready_files, batch_estimated_size y download_batch_zip dependían 100% de
smembers(pdf:batch_ids:{batch_id}) sin protección -- un Redis caído los tumbaba
con 500. process_zip_in_background ahora escribe un manifiesto (job_id ->
filename) a xml_temp/_manifest_{batch_id}.json ANTES de iterar el ZIP; estos
tests confirman que los 4 endpoints de lectura caen a ese manifiesto cuando
Redis no responde, en vez de tronar o reportar "no existe" para un batch real.
"""
from __future__ import annotations

import asyncio
import json
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


def _redis_down(*_args, **_kwargs):
    raise ConnectionError("Redis no responde (simulado)")


def _make_manifest_bucket(manifest: dict[str, str] | None, *, raise_on_missing=True):
    """bucket mock cuyo blob('xml_temp/_manifest_{id}.json').download_as_bytes
    devuelve el manifiesto serializado, o truena si no existe (para simular
    un batch que nunca llegó a escribir el manifiesto)."""
    bucket = MagicMock()

    def _blob(path):
        blob = MagicMock()
        if manifest is not None and path.endswith(".json"):
            blob.download_as_bytes.return_value = json.dumps(manifest).encode()
        elif raise_on_missing:
            blob.download_as_bytes.side_effect = Exception("no existe")
        blob.exists.return_value = manifest is not None
        return blob

    bucket.blob.side_effect = _blob
    return bucket


@unittest.skipIf(pdf_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class BatchProgressSnapshotManifestFallbackTests(unittest.TestCase):
    def test_cae_al_manifiesto_de_gcs_cuando_redis_no_responde(self) -> None:
        manifest = {"job-1": "a.xml", "job-2": "b.xml", "job-3": "c.xml"}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=_redis_down)
        mock_redis.smembers = AsyncMock(side_effect=_redis_down)
        mock_redis.mget = AsyncMock(side_effect=_redis_down)

        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = _make_manifest_bucket(manifest)

        with (
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
        ):
            snapshot = _run(pdf_router._batch_progress_snapshot("batch-x"))

        # Redis está totalmente caído (get/smembers/mget truenan) -- sin el
        # manifiesto, esto sería "Lote no encontrado". Con el manifiesto, el
        # total real (3) se conoce igual y el batch no se pierde.
        self.assertEqual(snapshot["total"], 3)
        self.assertNotEqual(snapshot.get("message"), "Lote no encontrado")

    def test_batch_realmente_inexistente_sigue_reportando_no_encontrado(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.smembers = AsyncMock(return_value=set())

        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = _make_manifest_bucket(None)

        with (
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
        ):
            snapshot = _run(pdf_router._batch_progress_snapshot("batch-nunca-existio"))

        self.assertEqual(snapshot["status"], "error")
        self.assertEqual(snapshot["message"], "Lote no encontrado")

    def test_detalle_de_estado_se_reconcilia_por_job_contra_gcs(self) -> None:
        """Si Redis responde el total/membresía pero NO el detalle de status
        (mget truena), cada job se reconcilia individualmente contra GCS
        (_reconcile_none_statuses_with_gcs) en vez de reportar un mensaje
        genérico de "no disponible" -- el % de avance sigue siendo preciso
        aunque Redis esté agotado."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=[None, None])  # extracting_error, extracting_total
        mock_redis.smembers = AsyncMock(return_value={b"job-1", b"job-2"})
        mock_redis.mget = AsyncMock(side_effect=_redis_down)

        manifest = {"job-1": "a.xml", "job-2": "b.xml"}

        def _blob(path):
            blob = MagicMock()
            if path == "xml_temp/_manifest_batch-y.json":
                blob.download_as_bytes.return_value = json.dumps(manifest).encode()
            elif path == "pdfs/job-1.pdf":
                blob.exists = MagicMock(return_value=True)   # ya convertido de verdad
            elif path == "pdfs/job-2.pdf":
                blob.exists = MagicMock(return_value=False)  # aún no
            return blob

        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = _blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
        ):
            # total_bytes viene None de get() -> usa manifiesto (2), luego
            # is_extracting get() -> None también vía side_effect agotado;
            # forzamos una tercera respuesta None para ese get.
            mock_redis.get = AsyncMock(side_effect=[None, None])
            snapshot = _run(pdf_router._batch_progress_snapshot("batch-y"))

        self.assertEqual(snapshot["status"], "processing")
        self.assertEqual(snapshot["done"], 1)
        self.assertEqual(snapshot["pending"], 1)
        self.assertEqual(snapshot["percentage"], 50)
        self.assertNotIn("no disponible", snapshot.get("message", ""))


@unittest.skipIf(pdf_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class ReadyFilesManifestFallbackTests(unittest.TestCase):
    def test_list_ready_files_usa_gcs_exists_si_redis_no_responde(self) -> None:
        manifest = {"job-1": "a.xml", "job-2": "b.xml"}
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(side_effect=_redis_down)
        mock_redis.mget = AsyncMock(side_effect=_redis_down)

        def _blob(path):
            blob = MagicMock()
            if path == "xml_temp/_manifest_batch-z.json":
                blob.download_as_bytes.return_value = json.dumps(manifest).encode()
            elif path == "pdfs/job-1.pdf":
                blob.exists = MagicMock(return_value=True)
            elif path == "pdfs/job-2.pdf":
                blob.exists = MagicMock(return_value=False)
            return blob

        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = _blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
        ):
            result = _run(pdf_router.list_ready_files("batch-z"))

        self.assertEqual(result["jobIds"], ["job-1"])


@unittest.skipIf(pdf_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class StartPdfZipGenerationWritesManifestTests(unittest.TestCase):
    """Hallazgo real de producción 2026-07-24 (cuota de Upstash agotada en
    vivo, no simulada): start_pdf_zip_generation (la ruta síncrona de ZIP
    chico, /cfdi/pdf/start-zip) no escribía ningún manifiesto de respaldo en
    GCS -- a diferencia de process_zip_in_background (la ruta grande vía
    URL firmada), que sí lo hace. Con la cuota agotada, el SADD/SET que
    registra pdf:batch_ids/pdf:extracting_total fallaba en silencio
    (safe_redis_call), y el batch quedaba sin ninguna forma de reconstruirse
    -- "Lote no encontrado" / jobIds: [] -- aunque los PDFs ya existieran y
    fueran descargables uno por uno. Estos tests confirman que ahora sí se
    escribe el manifiesto, ANTES de tocar Redis, y que list_ready_files
    puede resolver el batch usando SOLO ese manifiesto."""

    def test_escribe_el_manifiesto_en_gcs_aunque_redis_este_totalmente_caido(self) -> None:
        import io
        import zipfile

        from fastapi.testclient import TestClient

        from backend.app.main import app

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("factura1.xml", "<xml/>")
            zf.writestr("factura2.xml", "<xml/>")
        zip_bytes = buf.getvalue()

        written_manifests: dict[str, bytes] = {}

        def _blob(path: str):
            blob = MagicMock()
            if path.startswith("xml_temp/_manifest_") and path.endswith(".json"):
                def _capture(data, content_type=None, _path=path):
                    written_manifests[_path] = data
                blob.upload_from_string.side_effect = _capture
            return blob

        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = _blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
            patch.object(pdf_router, "redis_client") as mock_redis,
            patch.object(pdf_router, "enqueue_pdf_generation"),
        ):
            # Reproduce exactamente el hallazgo real: TODA llamada a Redis
            # truena con el error real de cuota agotada de Upstash (no una
            # ConnectionError genérica) -- safe_redis_call la traga y
            # devuelve None, igual que en producción.
            quota_error = Exception(
                "max requests limit exceeded. Limit: 500000, Usage: 500000."
            )
            mock_redis.set = AsyncMock(side_effect=quota_error)
            mock_redis.sadd = AsyncMock(side_effect=quota_error)
            mock_redis.expire = AsyncMock(side_effect=quota_error)
            pipe_cm = MagicMock()
            pipe_cm.__aenter__ = AsyncMock(return_value=pipe_cm)
            pipe_cm.__aexit__ = AsyncMock(return_value=False)
            pipe_cm.set = MagicMock()
            pipe_cm.execute = AsyncMock(side_effect=quota_error)
            mock_redis.pipeline = MagicMock(return_value=pipe_cm)

            client = TestClient(app)
            response = client.post(
                "/api/cfdi/pdf/start-zip",
                files={"file": ("batch.zip", zip_bytes, "application/zip")},
            )

        self.assertEqual(response.status_code, 200)
        batch_id = response.json()["batchId"]

        manifest_path = f"xml_temp/_manifest_{batch_id}.json"
        self.assertIn(manifest_path, written_manifests)
        manifest = json.loads(written_manifests[manifest_path])
        self.assertEqual(sorted(manifest.values()), ["factura1.xml", "factura2.xml"])

    def test_list_ready_files_resuelve_el_batch_solo_con_el_manifiesto(self) -> None:
        """Con Redis totalmente caído desde la creación (sin pdf:batch_ids
        ni pdf:status en absoluto), list_ready_files debe poder reconstruir
        la membresía completa del batch usando SOLO el manifiesto escrito
        por start_pdf_zip_generation, y reconciliar cada job contra GCS."""
        manifest = {"job-1": "factura1.xml", "job-2": "factura2.xml"}
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(side_effect=_redis_down)
        mock_redis.mget = AsyncMock(side_effect=_redis_down)

        def _blob(path):
            blob = MagicMock()
            if path == "xml_temp/_manifest_batch-sync.json":
                blob.download_as_bytes.return_value = json.dumps(manifest).encode()
            elif path == "pdfs/job-1.pdf":
                blob.exists = MagicMock(return_value=True)
            elif path == "pdfs/job-2.pdf":
                blob.exists = MagicMock(return_value=False)
            return blob

        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = _blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
        ):
            result = _run(pdf_router.list_ready_files("batch-sync"))

        self.assertEqual(result["jobIds"], ["job-1"])


if __name__ == "__main__":
    unittest.main()
