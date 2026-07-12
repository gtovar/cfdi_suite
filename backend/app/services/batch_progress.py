"""
batch_progress.py — Lógica de progreso de batch compartida entre dos caminos.

Extraído de app/routers/pdf.py (_publish_batch_tick original) para que el
Cloud Run Job de shards (Capa 1 de docs/propuesta-arquitectura-batch.md,
ver app/workers/batch_shard_worker.py) pueda reportar el mismo progreso al
mismo Redis + Pusher que ya usa el camino de Cloud Tasks, sin duplicar la
fórmula de "publica cada N o al llegar al total".

pdf.py sigue usando su propio redis_client (patchable en tests, ver
tests/test_pdf_batch_ttl.py) — esta función lo recibe como parámetro en vez
de crear su propia conexión, así ambos caminos comparten la lógica pero cada
proceso (el servicio FastAPI y cada tarea del Job) usa su propia conexión.
"""
from __future__ import annotations

import asyncio
from typing import Callable

# Debe coincidir con app.routers.pdf.BATCH_METADATA_TTL_SECONDS (alineado al
# lifecycle real de GCS, ver infra/gcs-lifecycle.json) — duplicado a propósito
# en vez de importar pdf.py desde aquí, para que un entrypoint ligero (Cloud
# Run Job) no tenga que cargar el FastAPI app completo solo por una constante.
BATCH_METADATA_TTL_SECONDS = 86400

PUBLISH_EVERY_N_JOBS = 5


async def publish_batch_tick(
    redis_client,
    publish_fn: Callable[[str, dict], None],
    batch_id: str,
    *,
    definitive_error: bool = False,
    ttl_seconds: int = BATCH_METADATA_TTL_SECONDS,
) -> None:
    """Cuenta el avance con INCR atómico y lo empuja a Pusher.

    Publica cada N archivos (y siempre al llegar al total) — así los
    espectadores reciben el progreso sin SSE ni polling a Redis. Solo se
    cuenta el error definitivo (XML desaparecido/fallo real de render); los
    errores transitorios no, porque el camino de Cloud Tasks los reintenta y
    podrían terminar en éxito.
    """
    counter = "error_count" if definitive_error else "done_count"
    await redis_client.incr(f"pdf:{counter}:{batch_id}")
    await redis_client.expire(f"pdf:{counter}:{batch_id}", ttl_seconds)

    total_bytes = await redis_client.get(f"pdf:extracting_total:{batch_id}")
    total = int(total_bytes) if total_bytes else 0
    if total <= 0:
        return

    done = int(await redis_client.get(f"pdf:done_count:{batch_id}") or 0)
    error = int(await redis_client.get(f"pdf:error_count:{batch_id}") or 0)
    processed = done + error
    if processed < total and processed % PUBLISH_EVERY_N_JOBS != 0 and not definitive_error:
        return

    ready_ids_raw = await redis_client.lpop(f"pdf:ready_recent:{batch_id}", 200)
    ready_ids = [rid.decode("utf-8") for rid in ready_ids_raw] if ready_ids_raw else []

    payload = {
        "status": "done" if processed >= total else "processing",
        "total": total,
        "done": done,
        "error": error,
        "converting": 0,
        "pending": max(total - processed, 0),
        "percentage": int((processed / total) * 100),
        "readyIds": ready_ids,
    }
    await asyncio.to_thread(publish_fn, batch_id, payload)
