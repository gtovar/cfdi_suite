"""
Tests de la Capa 1 (Cloud Run Job de shards, docs/propuesta-arquitectura-batch.md):
partición determinística en batch_shard_worker, umbral en batch_job_trigger,
y que la lógica de progreso compartida (batch_progress) se comporte igual
que el _publish_batch_tick original que reemplazó (ver test_pdf_batch_ttl.py).
"""
from __future__ import annotations

import asyncio
import importlib
import os
import unittest
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from backend.app.services import batch_job_trigger, batch_progress
    from backend.app.workers import batch_shard_worker
    from backend.app.workers.batch_shard_worker import shard_slice
except ModuleNotFoundError as error:
    batch_job_trigger = None
    batch_progress = None
    batch_shard_worker = None
    shard_slice = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


def _run(coro):
    return asyncio.run(coro)


@unittest.skipIf(batch_job_trigger is None, f"backend no disponible: {_IMPORT_ERROR}")
class ShardSliceTests(unittest.TestCase):
    def test_particion_exacta_sin_residuo(self) -> None:
        job_ids = [f"job-{i}" for i in range(300)]
        shard_0 = shard_slice(job_ids, 0, 100)
        shard_1 = shard_slice(job_ids, 1, 100)
        shard_2 = shard_slice(job_ids, 2, 100)
        self.assertEqual(len(shard_0), 100)
        self.assertEqual(len(shard_1), 100)
        self.assertEqual(len(shard_2), 100)
        # Sin traslapes ni huecos: la unión de los tres shards es el total.
        self.assertEqual(set(shard_0) | set(shard_1) | set(shard_2), set(job_ids))
        self.assertEqual(len(set(shard_0) | set(shard_1) | set(shard_2)), 300)

    def test_particion_con_residuo_ultima_tarea_incompleta(self) -> None:
        job_ids = [f"job-{i}" for i in range(250)]
        shard_2 = shard_slice(job_ids, 2, 100)  # 250 = 2*100 + 50
        self.assertEqual(len(shard_2), 50)

    def test_tarea_de_mas_da_shard_vacio_no_error(self) -> None:
        job_ids = [f"job-{i}" for i in range(150)]
        # 150 XMLs / 100 por shard = 2 tareas necesarias; una tercera tarea de
        # más (ej. --tasks sobredimensionado a propósito, ver Ronda 0.5 en el
        # documento) debe dar shard vacío, no reventar.
        shard_2 = shard_slice(job_ids, 2, 100)
        self.assertEqual(shard_2, [])

    def test_orden_determinista_independiente_del_orden_de_entrada(self) -> None:
        # Dos "tareas" que reciben la misma lista pero en distinto orden de
        # llegada (como pasaría con SMEMBERS, que no garantiza orden) deben
        # calcular exactamente el mismo shard_0 -- si no, dos XMLs podrían
        # procesarse por duplicado o ninguna tarea los cubriría.
        job_ids_orden_a = ["c", "a", "b", "e", "d"]
        job_ids_orden_b = ["e", "d", "c", "b", "a"]
        self.assertEqual(
            shard_slice(job_ids_orden_a, 0, 2),
            shard_slice(job_ids_orden_b, 0, 2),
        )


@unittest.skipIf(batch_job_trigger is None, f"backend no disponible: {_IMPORT_ERROR}")
class ShouldUseBatchJobTests(unittest.TestCase):
    def test_apagado_por_defecto_sin_importar_el_volumen(self) -> None:
        # BATCH_JOB_ENABLED lee os.environ en tiempo de import -- sin la env
        # var puesta explícitamente, debe dar False sin importar cuántos XMLs.
        self.assertFalse(batch_job_trigger.BATCH_JOB_ENABLED)
        self.assertFalse(batch_job_trigger.should_use_batch_job(15000))
        self.assertFalse(batch_job_trigger.should_use_batch_job(999999999))

    def test_prendido_respeta_el_umbral(self) -> None:
        with patch.object(batch_job_trigger, "BATCH_JOB_ENABLED", True):
            with patch.object(batch_job_trigger, "BATCH_JOB_THRESHOLD", 1000):
                self.assertFalse(batch_job_trigger.should_use_batch_job(999))
                self.assertTrue(batch_job_trigger.should_use_batch_job(1000))
                self.assertTrue(batch_job_trigger.should_use_batch_job(15000))


@unittest.skipIf(batch_job_trigger is None, f"backend no disponible: {_IMPORT_ERROR}")
class TriggerBatchShardJobZipGcsPathTests(unittest.TestCase):
    """zip_gcs_path es opcional (default None) -- confirma que solo agrega
    el EnvVar ZIP_GCS_PATH cuando se pasa, y que no pasarlo (compatibilidad
    con cualquier llamador existente) no lo agrega."""

    def _run_trigger(self, **kwargs):
        mock_client = MagicMock()
        mock_client.job_path.return_value = "projects/p/locations/r/jobs/j"
        mock_client.run_job.return_value.operation.name = "op-name"
        with patch("google.cloud.run_v2.JobsClient", return_value=mock_client):
            batch_job_trigger.trigger_batch_shard_job(
                "batch-1", 250, "default", **kwargs
            )
        return mock_client

    def test_sin_zip_gcs_path_no_agrega_envvar(self) -> None:
        mock_client = self._run_trigger()
        request = mock_client.run_job.call_args.kwargs["request"]
        env_names = [e.name for e in request.overrides.container_overrides[0].env]
        self.assertNotIn("ZIP_GCS_PATH", env_names)

    def test_con_zip_gcs_path_agrega_envvar(self) -> None:
        mock_client = self._run_trigger(zip_gcs_path="uploads/batch-1.zip")
        request = mock_client.run_job.call_args.kwargs["request"]
        env_by_name = {e.name: e.value for e in request.overrides.container_overrides[0].env}
        self.assertEqual(env_by_name.get("ZIP_GCS_PATH"), "uploads/batch-1.zip")


@unittest.skipIf(batch_shard_worker is None, f"backend no disponible: {_IMPORT_ERROR}")
class RunShardZipGcsPathTests(unittest.TestCase):
    """run_shard() con ZIP_GCS_PATH presente debe leer directo del ZIP
    remoto (vía RemoteZip mockeado) y NUNCA tocar pdf:batch_ids de Redis
    para particionar -- ver el comentario en batch_shard_worker.py sobre
    por qué mezclar las dos fuentes sería peligroso."""

    def _make_zip_info(self, filename: str) -> zipfile.ZipInfo:
        return zipfile.ZipInfo(filename=filename)

    def test_camino_nuevo_no_usa_smembers_y_procesa_su_shard(self) -> None:
        fake_infolist = [self._make_zip_info(f"factura_{i}.xml") for i in range(5)]
        mock_rz = MagicMock()
        mock_rz.infolist.return_value = fake_infolist
        mock_rz.read.return_value = b"<xml/>"
        mock_rz.close = MagicMock()

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.rpush = AsyncMock()
        mock_redis.expire = AsyncMock()

        env = {
            "BATCH_ID": "batch-remote",
            "TEMPLATE_ID": "default",
            "SHARD_SIZE": "5",
            "CLOUD_RUN_TASK_INDEX": "0",
            "ZIP_GCS_PATH": "uploads/batch-remote.zip",
        }

        with (
            patch.dict("os.environ", env, clear=False),
            patch.object(batch_shard_worker, "redis_client", mock_redis),
            patch.object(batch_shard_worker, "RemoteZip", return_value=mock_rz),
            patch.object(batch_shard_worker, "get_gcs_authorized_session", return_value=MagicMock()),
            patch.object(batch_shard_worker.storage, "Client", return_value=MagicMock()),
            patch.object(batch_shard_worker, "generate", return_value=b"%PDF-fake"),
            patch.object(batch_shard_worker, "publish_batch_tick", new=AsyncMock()),
        ):
            asyncio.run(batch_shard_worker.run_shard())

        mock_redis.smembers.assert_not_called()
        self.assertEqual(mock_rz.read.call_count, 5)
        mock_rz.close.assert_called_once()

    def test_camino_de_siempre_sin_zip_gcs_path_usa_smembers(self) -> None:
        """Guarda de regresión: sin ZIP_GCS_PATH, el comportamiento debe
        seguir siendo exactamente el de antes (Redis + xml_temp/)."""
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={b"job-1"})
        mock_redis.set = AsyncMock()
        mock_redis.rpush = AsyncMock()
        mock_redis.expire = AsyncMock()

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_as_bytes.return_value = b"<xml/>"
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        env = {
            "BATCH_ID": "batch-old",
            "TEMPLATE_ID": "default",
            "SHARD_SIZE": "5",
            "CLOUD_RUN_TASK_INDEX": "0",
        }

        with (
            patch.dict("os.environ", env, clear=False),
            patch.object(batch_shard_worker, "redis_client", mock_redis),
            patch.object(batch_shard_worker.storage, "Client", return_value=mock_storage_client),
            patch.object(batch_shard_worker, "generate", return_value=b"%PDF-fake"),
            patch.object(batch_shard_worker, "publish_batch_tick", new=AsyncMock()),
        ):
            os.environ.pop("ZIP_GCS_PATH", None)  # por si una prueba anterior lo dejó puesto
            asyncio.run(batch_shard_worker.run_shard())

        mock_redis.smembers.assert_called_once_with("pdf:batch_ids:batch-old")
        mock_bucket.blob.assert_any_call("xml_temp/job-1.xml")


@unittest.skipIf(batch_progress is None, f"backend no disponible: {_IMPORT_ERROR}")
class PublishBatchTickSharedLogicTests(unittest.TestCase):
    """Misma cobertura que test_pdf_batch_ttl.py pero contra la función
    compartida directamente (no el wrapper de pdf.py) -- confirma que el
    Cloud Run Job (que llama esta función con SU PROPIA conexión de Redis,
    no la de pdf.py) obtiene el mismo comportamiento de umbral/TTL."""

    def test_incrementa_contador_y_fija_ttl(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # sin total -> corta rápido
        mock_publish = MagicMock()

        _run(batch_progress.publish_batch_tick(mock_redis, mock_publish, "batch-x"))

        mock_redis.incr.assert_awaited_with("pdf:done_count:batch-x")
        mock_redis.expire.assert_awaited_with(
            "pdf:done_count:batch-x", batch_progress.BATCH_METADATA_TTL_SECONDS
        )
        mock_publish.assert_not_called()  # sin total conocido, no publica nada

    def test_publica_al_llegar_al_total(self) -> None:
        mock_redis = AsyncMock()

        async def fake_get(key):
            if "extracting_total" in key:
                return b"1"
            if "done_count" in key:
                return b"1"
            if "error_count" in key:
                return b"0"
            return None

        mock_redis.get = AsyncMock(side_effect=fake_get)
        mock_redis.lpop = AsyncMock(return_value=[b"job-1"])
        mock_publish = MagicMock()

        _run(batch_progress.publish_batch_tick(mock_redis, mock_publish, "batch-y"))

        mock_publish.assert_called_once()
        args, _ = mock_publish.call_args
        self.assertEqual(args[0], "batch-y")
        self.assertEqual(args[1]["status"], "done")
        self.assertEqual(args[1]["percentage"], 100)


if __name__ == "__main__":
    unittest.main()
