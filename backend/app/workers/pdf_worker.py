from __future__ import annotations
import asyncio
import base64
import os
from arq.connections import RedisSettings

async def generate_heavy_pdf(ctx: dict, job_id: str, xml_b64: str, template_id: str, html_shell: str | None) -> None:
    # ... tu lógica intacta ...

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
