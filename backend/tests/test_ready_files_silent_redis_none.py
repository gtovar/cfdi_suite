"""test_ready_files_silent_redis_none.py — reproduce el bug real confirmado
en producción el 2026-07-24 con la cuota de Upstash genuinamente agotada:
`redis_client.mget` NO truena -- responde una lista de puros `None` sin
excepción. El fallback a GCS que ya existía en list_ready_files /
_batch_progress_snapshot solo se activaba ante una excepción real
(safe_redis_call devolviendo None), así que este caso lo dejaba pasar tal
cual: el detalle de estado se interpretaba como "todo pendiente" para
siempre, aunque los PDFs ya existieran en Storage.

Diseño de la reconciliación (_reconcile_none_statuses_with_gcs, compartido
por list_ready_files y _batch_progress_snapshot): por-job, no todo-o-nada --
solo se pregunta a GCS por los jobs cuyo status en Redis vino `None` (mget
completo tronó/frenado, o esa key puntual se perdió). Los jobs que Redis
reportó explícitamente pending/converting/error/done NUNCA tocan GCS, así
el costo en el camino sano sigue siendo cero incluso con pérdida parcial
de datos en Redis (no toda caída es "todo o nada").
"""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.services import redis_safety

try:
    from backend.app.routers import pdf as pdf_router
except ModuleNotFoundError as error:
    pdf_router = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


def _run(coro):
    return asyncio.run(coro)


def _bucket_with_pdfs(existing_job_ids: set[str]):
    bucket = MagicMock()

    def _blob(path: str):
        blob = MagicMock()
        if path.startswith("pdfs/") and path.endswith(".pdf"):
            job_id = path[len("pdfs/"):-len(".pdf")]
            blob.exists = MagicMock(return_value=job_id in existing_job_ids)
        return blob

    bucket.blob.side_effect = _blob
    return bucket


@unittest.skipIf(pdf_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class ReconcileNoneStatusesTests(unittest.TestCase):
    """Cobertura directa de _reconcile_none_statuses_with_gcs, el helper
    compartido por list_ready_files y _batch_progress_snapshot."""

    def test_solo_reconcilia_los_jobs_cuyo_status_vino_none(self) -> None:
        status_by_job = {"job-1": "done", "job-2": None, "job-3": "converting", "job-4": None}
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = _bucket_with_pdfs({"job-2"})  # job-4 no existe aún

        with patch.object(pdf_router.storage, "Client", return_value=mock_storage_client):
            _run(pdf_router._reconcile_none_statuses_with_gcs(
                ["job-1", "job-2", "job-3", "job-4"], status_by_job,
            ))

        # job-1 y job-3 nunca debieron tocar GCS -- sus valores quedan intactos.
        self.assertEqual(status_by_job["job-1"], "done")
        self.assertEqual(status_by_job["job-3"], "converting")
        # job-2 y job-4 sí se reconciliaron: uno existe en GCS, el otro no.
        self.assertEqual(status_by_job["job-2"], "done")
        self.assertEqual(status_by_job["job-4"], "pending")

    def test_no_toca_gcs_si_no_hay_ningun_none(self) -> None:
        status_by_job = {"job-1": "done", "job-2": "pending"}
        mock_storage_client = MagicMock()

        with patch.object(pdf_router.storage, "Client", return_value=mock_storage_client):
            _run(pdf_router._reconcile_none_statuses_with_gcs(["job-1", "job-2"], status_by_job))

        mock_storage_client.bucket.assert_not_called()


@unittest.skipIf(pdf_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class ListReadyFilesSilentNoneTests(unittest.TestCase):
    def test_boton_de_descarga_no_se_queda_atorado_en_cero(self) -> None:
        """Escenario exacto del incidente: job-1 y job-2 ya terminaron y sus
        PDFs existen en GCS, pero mget responde puros None sin tronar. Sin el
        fix, list_ready_files devolvía jobIds=[] para siempre; con el fix,
        cae a GCS.exists() por job y reporta los que de verdad ya están listos."""
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={b"job-1", b"job-2", b"job-3"})
        mock_redis.mget = AsyncMock(return_value=[None, None, None])

        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = _bucket_with_pdfs({"job-1", "job-2"})

        with (
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
        ):
            result = _run(pdf_router.list_ready_files("batch-real"))

        self.assertEqual(sorted(result["jobIds"]), ["job-1", "job-2"])

    def test_perdida_parcial_no_reconcilia_los_jobs_con_status_real(self) -> None:
        """Redis responde real para job-1 (pending) y job-3 (error), pero
        perdió job-2 (None) -- solo job-2 debe ir a GCS."""
        status_map = {"pdf:status:job-1": b"pending", "pdf:status:job-2": None, "pdf:status:job-3": b"error"}

        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={b"job-1", b"job-2", b"job-3"})
        # smembers devuelve un set -- el orden de iteración no está
        # garantizado, así que el mock de mget responde según las keys
        # pedidas (no una lista fija) para no depender de ese orden.
        mock_redis.mget = AsyncMock(side_effect=lambda keys: [status_map[k] for k in keys])

        checked: list[str] = []

        def _blob(path: str):
            blob = MagicMock()
            if path.startswith("pdfs/"):
                job_id = path[len("pdfs/"):-len(".pdf")]
                checked.append(job_id)
                blob.exists = MagicMock(return_value=True)
            return blob

        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = _blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
        ):
            result = _run(pdf_router.list_ready_files("batch-real"))

        self.assertEqual(checked, ["job-2"])  # nunca job-1 ni job-3
        self.assertEqual(result["jobIds"], ["job-2"])


@unittest.skipIf(pdf_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class BatchProgressSnapshotSilentNoneTests(unittest.TestCase):
    def setUp(self) -> None:
        redis_safety._degraded_until = 0.0

    def test_progreso_se_reconcilia_por_job_en_vez_de_congelarse_en_cero(self) -> None:
        """Antes: mget de puro None (sin excepción) se interpretaba como
        "todo pendiente" indefinidamente -- la barra se veía en 0% para
        siempre aunque el trabajo real ya hubiera avanzado. Con el fix, cada
        job se reconcilia contra GCS y el % refleja la realidad."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=[
            None,   # pdf:extracting_error
            b"3",   # pdf:extracting_total
            None,   # pdf:extracting (no está en fase de extracción)
        ])
        mock_redis.smembers = AsyncMock(return_value={b"job-1", b"job-2", b"job-3"})
        mock_redis.mget = AsyncMock(return_value=[None, None, None])

        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = _bucket_with_pdfs({"job-1", "job-2"})

        with (
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
        ):
            snapshot = _run(pdf_router._batch_progress_snapshot("batch-real"))

        self.assertEqual(snapshot["status"], "processing")
        self.assertEqual(snapshot["done"], 2)
        self.assertEqual(snapshot["pending"], 1)
        self.assertEqual(snapshot["percentage"], 66)
        self.assertNotIn("message", snapshot)

    def test_progreso_reporta_done_cuando_todos_los_faltantes_ya_existen_en_gcs(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=[None, b"2", None])
        mock_redis.smembers = AsyncMock(return_value={b"job-1", b"job-2"})
        mock_redis.mget = AsyncMock(return_value=[None, None])

        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = _bucket_with_pdfs({"job-1", "job-2"})

        with (
            patch.object(pdf_router, "redis_client", mock_redis),
            patch.object(pdf_router.storage, "Client", return_value=mock_storage_client),
        ):
            snapshot = _run(pdf_router._batch_progress_snapshot("batch-real"))

        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["percentage"], 100)


if __name__ == "__main__":
    unittest.main()
