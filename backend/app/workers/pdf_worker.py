"""
pdf_worker.py — ARQ worker para jobs pesados de PDF (>50k conceptos).

Levantarlo:
    arq backend.app.workers.pdf_worker.WorkerSettings
"""
from __future__ import annotations

import asyncio
import base64
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from arq.connections import RedisSettings


# === SERVIDOR WEB FALSO PARA PASAR EL HEALTH CHECK ===
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "worker_alive"}')
    
    def log_message(self, format, *args):
        return  # Silenciar logs internos para no ensuciar la consola

def start_fake_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    print(f"--- Fake Web Server activo en puerto {port} ---")
    server.serve_forever()

async def startup(ctx):
    """Evento nativo de ARQ que se ejecuta al arrancar el Worker."""
    print("Iniciando Worker de ARQ y levantando puerto fake...")
    # Iniciamos el hilo justo cuando ARQ está listo y activo
    t = threading.Thread(target=start_fake_server, daemon=True)
    t.start()
    print("Puerto fake acoplado con éxito.")
# ====================================================


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
    )
    max_jobs = 4
    job_timeout = 600   # 10 min máximo por job
    keep_result = 3600  # mantener resultado 1h
    
    # Vinculamos el evento de inicio nativo de ARQ
    on_startup = startup
