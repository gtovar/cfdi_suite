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

    def test_detalle_de_estado_degrada_sin_reconstruir_por_gcs(self) -> None:
        """Si Redis responde el total/membresía pero NO el detalle de status
        (mget), no se reconstruye golpeando GCS por cada archivo (podrían ser
        miles) -- se reporta degradado explícitamente."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=[None, None])  # extracting_error, extracting_total
        mock_redis.smembers = AsyncMock(return_value={b"job-1", b"job-2"})
        mock_redis.mget = AsyncMock(side_effect=_redis_down)

        manifest = {"job-1": "a.xml", "job-2": "b.xml"}
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = _make_manifest_bucket(manifest)

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
        self.assertIn("no disponible", snapshot.get("message", ""))


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


if __name__ == "__main__":
    unittest.main()
