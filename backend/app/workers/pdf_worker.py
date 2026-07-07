"""
pdf_worker.py — Worker ARQ nativo y limpio.
"""
from __future__ import annotations

import asyncio
import base64
import os
from arq.connections import RedisSettings

async def generate_heavy_pdf(
    ctx: dict,
    job_id: str,
    xml_b64: str,
    template_id: str,
    html_shell: str | None,
) -> None:
    """Función ARQ: genera el PDF en background y guarda el resultado en Redis."""
    redis = ctx["redis"]
    try:
        await redis.set(f"pdf:status:{job_id}", "generating_pdf", ex=3600)

        xml_bytes = base64.b64decode(xml_b64)
        from ..services.pdf_pipeline import generate
        pdf = await asyncio.to_thread(generate, xml_bytes, template_id, html_shell)

        await redis.set(f"pdf:result:{job_id}", pdf, ex=3600)
        await redis.set(f"pdf:status:{job_id}", "done", ex=3600)

    except Exception as exc:
        await redis.set(f"pdf:status:{job_id}", f"error:{exc}", ex=3600)

class WorkerSettings:
    functions = [generate_heavy_pdf]
    redis_settings = RedisSettings(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD", None),
        ssl=True if os.getenv("REDIS_PASSWORD") else False
    )
    max_jobs = 4
    job_timeout = 600
    keep_result = 3600
