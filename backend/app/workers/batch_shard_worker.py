"""
batch_shard_worker.py — Entrypoint de una tarea de Cloud Run Job.

Capa 1 de docs/propuesta-arquitectura-batch.md ("artillería pesada" para
batches grandes). Cada tarea toma un shard (SHARD_SIZE XMLs, default 100) del
manifiesto de un batch YA EXTRAÍDO — mismo Redis Set `pdf:batch_ids:{batch_id}`
que usa el camino de Cloud Tasks (app/routers/pdf.py) — y genera sus PDFs,
reutilizando el mismo bucket de GCS y el mismo tick de progreso hacia Pusher.

No reemplaza el camino de Cloud Tasks: es una ruta alterna para batches que
superan BATCH_JOB_THRESHOLD, disparada por
app.services.batch_job_trigger.trigger_batch_shard_job() después de que
process_zip_in_background termina de construir el manifiesto completo.

Variables de entorno:
  CLOUD_RUN_TASK_INDEX — puesta automáticamente por la plataforma (0-based).
  BATCH_ID              — pasado vía overrides al disparar la ejecución.
  TEMPLATE_ID            — default "default".
  SHARD_SIZE             — XMLs por tarea, default 100 (debe coincidir con el
                            cálculo de --tasks al disparar la ejecución, ver
                            batch_job_trigger.trigger_batch_shard_job).
  ZIP_GCS_PATH           — opcional. Si está presente, esta tarea lee sus
                            XMLs directo del ZIP original en GCS (lecturas
                            por rango vía remotezip, sin pasar por
                            xml_temp/) en vez del camino de siempre (leer
                            pdf:batch_ids de Redis + descargar de
                            xml_temp/{job_id}.xml). Ver run_shard() y
                            _process_one_remote() más abajo.
  GCS_BUCKET_NAME, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD — mismas que el
                            servicio principal (ver infra/deploy-batch-shard-job.sh).
"""
from __future__ import annotations

import asyncio
import os
import sys

import redis.asyncio as aioredis
from google.cloud import storage
from remotezip import RemoteZip

from ..services.batch_progress import BATCH_METADATA_TTL_SECONDS, publish_batch_tick
from ..services.gcs_range_auth import get_gcs_authorized_session, gcs_object_url
from ..services.pdf_pipeline import generate
from ..services.realtime import publish_batch_progress
from ..services.redis_safety import safe_redis_call
from ..services.zip_manifest import build_manifest

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "cfdi-suite-uploads-706861124428")

# Conexión propia (no la de app.routers.pdf — esta tarea corre en su propio
# proceso/contenedor, no importa el FastAPI app). Mismos parámetros que
# pdf.py:58-67 para apuntar al mismo Redis (Upstash en producción).
redis_client = aioredis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD", None),
    ssl=True,
    ssl_cert_reqs=None,
    max_connections=10,
    decode_responses=False,
)


async def _process_one(bucket, job_id: str, template_id: str) -> None:
    blob_xml = bucket.blob(f"xml_temp/{job_id}.xml")

    if not await asyncio.to_thread(blob_xml.exists):
        await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"error", ex=BATCH_METADATA_TTL_SECONDS))
        raise FileNotFoundError(f"xml_temp/{job_id}.xml no existe")

    xml_bytes = await asyncio.to_thread(blob_xml.download_as_bytes)
    await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"converting", ex=3600))

    # Llamada directa, sin PDF_PROCESS_POOL: esta tarea YA es su propio
    # proceso aislado (una tarea de Cloud Run Job = un contenedor). El
    # aislamiento entre XMLs que exige PDF_PROCESS_POOL en el camino de Cloud
    # Tasks (evitar que dos peticiones *concurrentes* compartan heap nativo de
    # WeasyPrint/reportlab, ver PROJECT_STATE.md, signal 6) no aplica aquí:
    # los XMLs del shard se procesan uno tras otro, nunca al mismo tiempo, en
    # este mismo proceso — así se reutiliza en caliente, entre los ~100 XMLs
    # del shard, el FontConfiguration de shell_service.py y el import de
    # WeasyPrint/reportlab, en vez de pagar ese costo por cada uno.
    pdf_bytes = generate(xml_bytes, template_id)

    blob_pdf = bucket.blob(f"pdfs/{job_id}.pdf")
    await asyncio.to_thread(blob_pdf.upload_from_string, pdf_bytes, content_type="application/pdf")
    # <-- A partir de aquí el PDF ya está generado y subido -- el reporte de
    # abajo es best-effort, nunca puede hacer que este job se cuente como error.

    await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"done", ex=BATCH_METADATA_TTL_SECONDS))
    await safe_redis_call(lambda: redis_client.set(f"pdf:size:{job_id}", str(len(pdf_bytes)).encode(), ex=86400))
    await asyncio.to_thread(blob_xml.delete)


async def _process_one_remote(rz: RemoteZip, bucket, job_id: str, filename: str, template_id: str) -> None:
    """Igual que _process_one, pero lee el XML directo del ZIP original vía
    una lectura por rango (rz.read) en vez de xml_temp/{job_id}.xml -- sin
    paso intermedio de subida/descarga. No hay xml_temp que borrar aquí."""
    xml_bytes = await asyncio.to_thread(rz.read, filename)
    await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"converting", ex=3600))

    pdf_bytes = generate(xml_bytes, template_id)

    blob_pdf = bucket.blob(f"pdfs/{job_id}.pdf")
    await asyncio.to_thread(blob_pdf.upload_from_string, pdf_bytes, content_type="application/pdf")
    # <-- A partir de aquí el PDF ya está generado y subido -- el reporte de
    # abajo es best-effort, nunca puede hacer que este job se cuente como error.

    await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"done", ex=BATCH_METADATA_TTL_SECONDS))
    await safe_redis_call(lambda: redis_client.set(f"pdf:size:{job_id}", str(len(pdf_bytes)).encode(), ex=86400))


def shard_slice(job_ids: list[str], task_index: int, shard_size: int) -> list[str]:
    """Partición determinística: cada tarea calcula su propio slice a partir
    de la MISMA lista ordenada — no requiere coordinación entre tareas ni una
    estructura de datos nueva más allá del Set que ya existe en Redis."""
    return sorted(job_ids)[task_index * shard_size: (task_index + 1) * shard_size]


async def run_shard() -> None:
    batch_id = os.environ["BATCH_ID"]
    template_id = os.getenv("TEMPLATE_ID", "default")
    shard_size = int(os.getenv("SHARD_SIZE", "100"))
    task_index = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    zip_gcs_path = os.getenv("ZIP_GCS_PATH")  # presencia = camino nuevo

    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    if zip_gcs_path:
        # Camino nuevo: la tarea calcula su propia porción a partir del
        # MISMO manifiesto (build_manifest) que usó process_zip_in_background
        # para construir pdf:batch_ids -- deliberadamente NO se lee ese Set
        # de Redis aquí. Si esta tarea leyera Redis para la lista de
        # job_ids y por separado el ZIP para los nombres de archivo, serían
        # dos listas calculadas de forma independiente que podrían divergir
        # (un job_id sin archivo, o viceversa) -- el peor bug para depurar,
        # se ve como un batch atorado sin error visible. Con una sola fuente
        # (el manifiesto derivado del ZIP), eso es estructuralmente imposible.
        session = get_gcs_authorized_session()
        url = gcs_object_url(BUCKET_NAME, zip_gcs_path)
        rz = await asyncio.to_thread(RemoteZip, url, session=session)
        try:
            infolist = await asyncio.to_thread(rz.infolist)
            manifest = build_manifest(infolist, batch_id)  # job_id -> filename
            job_ids = list(manifest.keys())

            my_shard = shard_slice(job_ids, task_index, shard_size)
            if not my_shard:
                print(f"[batch_shard_worker] tarea {task_index}: shard vacío (batch {batch_id} más chico de lo esperado), nada que hacer.")
                return

            print(f"[batch_shard_worker] tarea {task_index}: procesando {len(my_shard)} XMLs del batch {batch_id} (lectura remota por rango, sin xml_temp/).")

            for job_id in my_shard:
                try:
                    await _process_one_remote(rz, bucket, job_id, manifest[job_id], template_id)
                    await safe_redis_call(lambda: redis_client.rpush(f"pdf:ready_recent:{batch_id}", job_id))
                    await safe_redis_call(lambda: redis_client.expire(f"pdf:ready_recent:{batch_id}", BATCH_METADATA_TTL_SECONDS))
                    await safe_redis_call(lambda: publish_batch_tick(redis_client, publish_batch_progress, batch_id))
                except Exception as exc:
                    # Un fallo de Redis aquí (reporte de un XML individual)
                    # nunca debe escapar el `for` -- eso es lo que antes
                    # tumbaba el shard completo vía sys.exit (ver Paso 2 de
                    # docs/plan-implementacion-resiliencia-redis-2026-07-23.md).
                    print(f"[batch_shard_worker] error procesando {job_id}: {exc}")
                    await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"error", ex=BATCH_METADATA_TTL_SECONDS))
                    await safe_redis_call(lambda: publish_batch_tick(redis_client, publish_batch_progress, batch_id, definitive_error=True))
        finally:
            rz.close()
        return

    # Camino de siempre (sin ZIP_GCS_PATH): lee pdf:batch_ids de Redis y
    # descarga cada XML de xml_temp/{job_id}.xml -- sin cambios.
    # Orden determinístico: SMEMBERS no garantiza orden, pero ordenar la misma
    # lista en cada una de las N tareas (todas leen el mismo Set, ya inmutable
    # -- la extracción del batch ya terminó antes de disparar el Job) produce
    # el mismo particionado sin necesitar una estructura de datos nueva.
    job_ids_raw = await redis_client.smembers(f"pdf:batch_ids:{batch_id}")
    job_ids = [jid.decode("utf-8") for jid in job_ids_raw]

    my_shard = shard_slice(job_ids, task_index, shard_size)
    if not my_shard:
        print(f"[batch_shard_worker] tarea {task_index}: shard vacío (batch {batch_id} más chico de lo esperado), nada que hacer.")
        return

    print(f"[batch_shard_worker] tarea {task_index}: procesando {len(my_shard)} XMLs del batch {batch_id}.")

    for job_id in my_shard:
        try:
            await _process_one(bucket, job_id, template_id)
            await safe_redis_call(lambda: redis_client.rpush(f"pdf:ready_recent:{batch_id}", job_id))
            await safe_redis_call(lambda: redis_client.expire(f"pdf:ready_recent:{batch_id}", BATCH_METADATA_TTL_SECONDS))
            await safe_redis_call(lambda: publish_batch_tick(redis_client, publish_batch_progress, batch_id))
        except Exception as exc:
            # Error de un solo XML no debe tirar el shard completo -- un XML
            # corrupto no se arregla reintentando la tarea entera, y los otros
            # ~99 XMLs del shard sí deben completarse. Tampoco debe tirarlo un
            # fallo de Redis durante el reporte (ver Paso 2 del plan).
            print(f"[batch_shard_worker] error procesando {job_id}: {exc}")
            await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"error", ex=BATCH_METADATA_TTL_SECONDS))
            await safe_redis_call(lambda: publish_batch_tick(redis_client, publish_batch_progress, batch_id, definitive_error=True))


def main() -> None:
    try:
        asyncio.run(run_shard())
    except Exception as exc:
        # Esto sí debe fallar la tarea completa (Cloud Run Job la reintentará
        # según --max-retries): significa que algo previo al procesamiento de
        # XMLs individuales falló (Redis inalcanzable, BATCH_ID ausente, etc.).
        print(f"[batch_shard_worker] fallo fatal de la tarea: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
