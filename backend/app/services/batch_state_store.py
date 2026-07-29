"""
batch_state_store.py — Repositorio de estado de un batch de PDFs (dominio de
app.routers.pdf / app.workers.batch_shard_worker): status por job_id, Set de
membresía del batch, manifiesto de respaldo en GCS. Leído/escrito por dos
procesos separados (el servicio FastAPI y cada tarea del Cloud Run Job de
shards) que comparten el mismo Redis (Upstash) y el mismo bucket de GCS pero
NO una conexión física -- cada función recibe redis_client/bucket por
parámetro.

Movido tal cual desde app/routers/pdf.py (sin cambio de comportamiento) al
centralizar el acceso a Redis -- no reescrito desde
docs/aider/plan3-redis-cache-aside-unificado-2026-07-24.md, que quedó
desactualizado respecto al código real (la reconciliación contra GCS que ese
plan diseñaba como parte nueva ya existía en producción, agregada en la
sesión de síntesis de 3 herramientas del 2026-07-24 -- ver PROJECT_STATE.md).

Regla de fondo (Cache-Aside): Redis es un acelerador desechable para el
status por job; GCS (blob pdfs/{job_id}.pdf, manifiesto
xml_temp/_manifest_{batch_id}.json) es la fuente de verdad. Cuando Redis
reporta un job como None (mget vacío o key perdida), se reconcilia contra
GCS -- ver reconcile_none_statuses_with_gcs. Esto NO aplica a batch.py
(app.routers.batch): ese es un dominio distinto (análisis de CFDI por lote,
llaves batch:{batch_id}/batch:{batch_id}:results, cliente síncrono) sin
lógica real compartida con este módulo -- se dejó fuera a propósito.
"""
from __future__ import annotations

import asyncio
import json

from .redis_safety import safe_redis_call

# TTL de las claves de metadata de un batch en Redis (batch_ids, extracting_total,
# status por job). Debe ser >= al lifecycle real de GCS sobre pdfs/uploads/xml_temp
# (1 día, ver infra/gcs-lifecycle.json). Duplicado a propósito en app.routers.pdf
# (misma constante, mismo valor) -- ver comentario ahí.
BATCH_METADATA_TTL_SECONDS = 86400


def batch_manifest_blob(bucket, batch_id: str):
    return bucket.blob(f"xml_temp/_manifest_{batch_id}.json")


def loose_batch_blob(bucket, batch_id: str):
    """Marca durable que distingue una cola de XML sueltos de un ZIP."""
    return bucket.blob(f"xml_temp/_loose_batch_{batch_id}.json")


async def is_loose_batch(bucket, batch_id: str) -> bool:
    return await asyncio.to_thread(loose_batch_blob(bucket, batch_id).exists)


async def load_manifest(bucket, batch_id: str) -> dict[str, str] | None:
    """job_id -> filename, leído de xml_temp/_manifest_{batch_id}.json en GCS.

    Respaldo de membresía del batch cuando pdf:batch_ids (el Set de Redis)
    no está disponible o viene vacío por una falla de Redis durante la
    extracción -- ver process_zip_in_background, que escribe este manifiesto
    ANTES de iterar el ZIP, con la misma función (build_manifest) que ya usa
    el camino de sharding grande para no depender de Redis para saber qué
    archivos pertenecen al batch."""
    try:
        raw = await asyncio.to_thread(batch_manifest_blob(bucket, batch_id).download_as_bytes)
    except Exception:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def resolve_job_ids(redis_client, bucket, batch_id: str) -> list[str]:
    """Membresía del batch: Redis (pdf:batch_ids) con el manifiesto de GCS
    como respaldo. Compartido por list_ready_files, batch_estimated_size y
    download_batch_zip."""
    if await is_loose_batch(bucket, batch_id):
        manifest = await load_manifest(bucket, batch_id)
        return list(manifest.keys()) if manifest else []
    registered_raw = await safe_redis_call(lambda: redis_client.smembers(f"pdf:batch_ids:{batch_id}"))
    job_ids = [rid.decode("utf-8") for rid in registered_raw] if registered_raw else []
    if not job_ids:
        manifest = await load_manifest(bucket, batch_id)
        if manifest:
            job_ids = list(manifest.keys())
    return job_ids


async def reconcile_none_statuses_with_gcs(
    bucket, job_ids: list[str], status_by_job: dict[str, str | None]
) -> None:
    """Completa in-place, contra GCS, el status de los jobs cuyo valor en
    Redis vino `None` -- ya sea porque el mget completo no respondió (dict
    vacío) o porque esa key puntual se perdió (hallazgo real de producción
    2026-07-24: con Redis agotado, Upstash no truena `mget`, entrega puros
    `None` sin excepción).

    Deliberadamente NO reconcilia los jobs que Redis reportó explícitamente
    como pending/converting/error -- solo los `None`, así el costo en el
    camino sano (Redis vivo, todo con status real) sigue siendo cero. Tampoco
    se condiciona a is_degraded(): esa bandera es por-instancia y la lectura
    puede caer en otra instancia (repetiría el bug multi-instancia ya
    documentado en pdf_progress) -- se reconcilia siempre que haga falta,
    job por job, sin depender de memoria compartida entre requests.
    """
    to_check = [jid for jid in job_ids if status_by_job.get(jid) is None]
    if not to_check:
        return
    # Tope de concurrencia obligatorio -- sin esto, un batch grande atascado
    # encolaría miles de llamadas HEAD detrás de los hilos del executor por
    # defecto y mataría de hambre cualquier otro asyncio.to_thread de la
    # misma instancia (subidas, descargas, etc.). Mismo valor que el
    # prefetch de download_batch_zip.
    sem = asyncio.Semaphore(8)

    async def _exists(jid: str) -> tuple[str, str]:
        async with sem:
            if await asyncio.to_thread(bucket.blob(f"pdfs/{jid}.pdf").exists):
                return jid, "done"
            # Un manifiesto de XML sueltos se crea ANTES de las subidas. Si
            # todavía no existe su XML, no está en Cloud Tasks: la UI debe
            # mostrarlo como pendiente de subir, no como "convirtiendo".
            xml_exists = await asyncio.to_thread(bucket.blob(f"xml_temp/{jid}.xml").exists)
            return jid, "pending" if xml_exists else "awaiting_upload"

    for jid, status in await asyncio.gather(*[_exists(jid) for jid in to_check]):
        status_by_job[jid] = status


async def get_batch_snapshot(redis_client, bucket, batch_id: str) -> dict:
    """Estado actual del lote calculado desde Redis (fuente de verdad para el
    detalle done/error/converting) con el manifiesto de GCS como respaldo de
    membresía y total si Redis no responde.

    Lo comparten el SSE legacy y el endpoint /status; los ticks de Pusher usan
    contadores aproximados, este cálculo (MGET de statuses) es el exacto.
    """
    # Si el loop de extracción murió a mitad de camino, no dejamos la barra
    # congelada hasta el timeout del cliente: reportamos el error de inmediato.
    extracting_error = await safe_redis_call(lambda: redis_client.get(f"pdf:extracting_error:{batch_id}"))
    if extracting_error:
        return {"status": "error", "message": extracting_error.decode("utf-8")}

    loose_batch = await is_loose_batch(bucket, batch_id)
    total_bytes = await safe_redis_call(lambda: redis_client.get(f"pdf:extracting_total:{batch_id}"))
    manifest: dict[str, str] | None = None
    if loose_batch:
        manifest = await load_manifest(bucket, batch_id)
        total_bytes = len(manifest) if manifest else None
    if total_bytes is None:
        # Puede ser la ventana breve al arrancar (aún no se conoce el total)
        # o que Redis no esté respondiendo -- en ese segundo caso, el
        # manifiesto en GCS (si ya se escribió) es la fuente de verdad del
        # total real, sin depender de Redis para nada.
        manifest = await load_manifest(bucket, batch_id)
        if manifest:
            total_bytes = len(manifest)
        else:
            is_extracting = await safe_redis_call(lambda: redis_client.get(f"pdf:extracting:{batch_id}"))
            if is_extracting:
                return {"status": "processing", "total": 0, "done": 0, "error": 0, "converting": 0, "pending": 0, "percentage": 0, "message": "Preparando lote..."}
            return {"status": "error", "message": "Lote no encontrado"}

    total = int(total_bytes)
    if total == 0:
        return {"status": "done", "total": 0, "done": 0, "error": 0, "converting": 0, "pending": 0, "percentage": 100}

    registered_raw = await safe_redis_call(lambda: redis_client.smembers(f"pdf:batch_ids:{batch_id}"))
    registered_ids = [rid.decode("utf-8") for rid in registered_raw] if registered_raw else []
    if loose_batch and manifest:
        registered_ids = list(manifest.keys())
    elif not registered_ids:
        if manifest is None:
            manifest = await load_manifest(bucket, batch_id)
        if manifest:
            registered_ids = list(manifest.keys())

    # Fase de extracción: el ZIP todavía se está desempaquetando y subiendo a
    # GCS -- ningún XML ha empezado a convertirse todavía. Se reporta con un
    # status distinto ("extracting", no "processing") para no reusar el
    # mismo "percentage" con dos significados (extraído vs. convertido) y
    # arriesgar que la barra parezca retroceder al pasar de una fase a otra.
    # 2026-07-12: antes de esto, la pantalla se quedaba en 0% fijo toda la
    # extracción (6-25 min medidos) sin ningún aviso -- el dato (cuántos
    # XMLs ya están en pdf:batch_ids) ya existía, solo no se exponía aquí.
    is_extracting = await safe_redis_call(lambda: redis_client.get(f"pdf:extracting:{batch_id}"))
    if is_extracting:
        extracted = len(registered_ids)
        return {
            "status": "extracting",
            "total": total,
            "extracted": extracted,
            "done": 0,
            "error": 0,
            "converting": 0,
            "pending": total,
            "percentage": int((extracted / total) * 100) if total else 0,
        }

    done = error = converting = awaiting_upload = 0
    ready_ids: list[str] = []
    statuses = None
    if registered_ids:
        keys = [f"pdf:status:{jid}" for jid in registered_ids]
        statuses = await safe_redis_call(lambda: redis_client.mget(keys))

    # status_by_job queda vacío si el mget completo no respondió
    # (safe_redis_call devolvió None) -- en ese caso TODOS los jobs quedan
    # como None más abajo, igual que si Redis hubiera respondido puros None
    # para cada key. reconcile_none_statuses_with_gcs completa contra GCS
    # solo los jobs cuyo status quedó None (nunca los que Redis ya reportó
    # explícitamente), así el % de avance sigue siendo preciso incluso con
    # Redis agotado, en vez de congelarse en un mensaje genérico de "no
    # disponible" mientras el trabajo real ya avanzó.
    status_by_job: dict[str, str | None] = {}
    if statuses is not None:
        for jid, status_bytes in zip(registered_ids, statuses):
            status_by_job[jid] = status_bytes.decode("utf-8") if status_bytes else None

    await reconcile_none_statuses_with_gcs(bucket, registered_ids, status_by_job)

    for jid in registered_ids:
        status = status_by_job.get(jid) or "pending"
        if status == "done":
            done += 1
            ready_ids.append(jid)
        elif status == "error":
            error += 1
        elif status == "converting":
            converting += 1
        elif status == "awaiting_upload":
            awaiting_upload += 1

    registered_pending = len(registered_ids) - done - error - converting - awaiting_upload
    not_yet_registered = total - len(registered_ids)
    pending = max(registered_pending, 0)
    awaiting_upload += max(not_yet_registered, 0)
    processed = done + error

    return {
        "status": "processing" if processed < total else "done",
        "total": total,
        "done": done,
        "error": error,
        "converting": converting,
        "pending": pending,
        "awaitingUpload": awaiting_upload,
        "percentage": int((processed / total) * 100),
        # Mismo dato que get_ready_job_ids, calculado gratis del loop de
        # arriba (sin MGET extra) -- reemplaza a readyIds del extinto canal
        # de datos de Pusher ('progress'): con hint-only, la lista de listos
        # para descarga individual viaja aquí, en el único snapshot.
        "readyIds": ready_ids,
    }


async def get_ready_job_ids(redis_client, bucket, batch_id: str) -> list[str]:
    """
    IDs de los archivos ya convertidos (status 'done') hasta ahora — el
    frontend la usa para ir llenando la tabla de descargas individuales
    conforme avanza el lote, sin esperar a que todo el batch termine.

    Hallazgo real de producción 2026-07-24: con Redis agotado, Upstash NO
    truena `mget` -- responde una lista de puros `None` sin excepción. Por
    eso cada job se reconcilia contra GCS individualmente cuando su status
    vino `None` (ver reconcile_none_statuses_with_gcs) -- nunca los que
    Redis ya reportó explícitamente pending/converting/error, para que el
    costo en el camino sano (Redis vivo) siga siendo cero.
    """
    job_ids = await resolve_job_ids(redis_client, bucket, batch_id)
    if not job_ids:
        return []

    keys = [f"pdf:status:{jid}" for jid in job_ids]
    statuses = await safe_redis_call(lambda: redis_client.mget(keys))

    status_by_job: dict[str, str | None] = {}
    if statuses is not None:
        for jid, status_bytes in zip(job_ids, statuses):
            status_by_job[jid] = status_bytes.decode("utf-8") if status_bytes else None

    await reconcile_none_statuses_with_gcs(bucket, job_ids, status_by_job)

    return [jid for jid in job_ids if status_by_job.get(jid) == "done"]


async def get_estimated_size(redis_client, bucket, batch_id: str) -> dict:
    """
    Suma los tamaños (bytes originales, no comprimidos) de los PDFs ya
    generados del lote — el frontend la usa para decidir si puede mostrar
    una barra de progreso real al descargar el ZIP (fetch + ReadableStream,
    que retiene el archivo completo en memoria) o si el lote es demasiado
    grande y conviene la descarga nativa del navegador sin progreso.
    El ZIP comprime, así que el tamaño final real será algo menor a esta suma.
    """
    job_ids = await resolve_job_ids(redis_client, bucket, batch_id)
    if not job_ids:
        return {"estimatedBytes": 0, "knownCount": 0, "totalCount": 0}

    keys = [f"pdf:size:{jid}" for jid in job_ids]
    sizes_raw = await safe_redis_call(lambda: redis_client.mget(keys))

    known_sizes = [int(s) for s in (sizes_raw or []) if s]
    return {
        "estimatedBytes": sum(known_sizes),
        "knownCount": len(known_sizes),
        "totalCount": len(job_ids),
    }


# --- Escritura de status por job -- compartida por app.routers.pdf
# (internal_generate_pdf y afines, camino de Cloud Tasks) y
# app.workers.batch_shard_worker (_process_one/_process_one_remote, camino
# del Job de shards) -- mismas llaves/TTLs, antes duplicadas byte a byte en
# los dos archivos. Cada función es best-effort (envuelta en safe_redis_call,
# nunca propaga) -- igual que las escrituras que reemplazan.

async def mark_job_pending(redis_client, job_id: str, *, ttl_seconds: int = 1800) -> None:
    await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"pending", ex=ttl_seconds))


async def mark_job_converting(redis_client, job_id: str, *, ttl_seconds: int = 3600) -> None:
    await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"converting", ex=ttl_seconds))


async def mark_job_done(
    redis_client, job_id: str, pdf_size_bytes: int,
    *, ttl_seconds: int = BATCH_METADATA_TTL_SECONDS, size_ttl_seconds: int = 86400,
) -> None:
    await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"done", ex=ttl_seconds))
    await safe_redis_call(lambda: redis_client.set(f"pdf:size:{job_id}", str(pdf_size_bytes).encode(), ex=size_ttl_seconds))


async def mark_job_error(redis_client, job_id: str, *, ttl_seconds: int = BATCH_METADATA_TTL_SECONDS) -> None:
    await safe_redis_call(lambda: redis_client.set(f"pdf:status:{job_id}", b"error", ex=ttl_seconds))
