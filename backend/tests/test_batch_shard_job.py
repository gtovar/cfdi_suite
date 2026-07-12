"""
Tests de la Capa 1 (Cloud Run Job de shards, docs/propuesta-arquitectura-batch.md):
partición determinística en batch_shard_worker, umbral en batch_job_trigger,
y que la lógica de progreso compartida (batch_progress) se comporte igual
que el _publish_batch_tick original que reemplazó (ver test_pdf_batch_ttl.py).
"""
from __future__ import annotations

import asyncio
import importlib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from backend.app.services import batch_job_trigger, batch_progress
    from backend.app.workers.batch_shard_worker import shard_slice
except ModuleNotFoundError as error:
    batch_job_trigger = None
    batch_progress = None
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
