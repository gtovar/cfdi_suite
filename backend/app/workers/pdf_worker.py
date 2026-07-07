"""
pdf_worker.py — Servidor dedicado con Worker ARQ integrado para Cloud Run.
"""
from __future__ import annotations

import asyncio
import base64
import os
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI
from arq.connections import RedisSettings
from arq.worker import Worker

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

# --- CONTROLADOR DEL CICLO DE VIDA (BLINDADO) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Iniciando instancia interna de ARQ Worker...")
    
    # 1. Evitamos que un TypeError por versiones viejas de ARQ mate la API
    try:
        worker = Worker(
            functions=WorkerSettings.functions,
            redis_settings=WorkerSettings.redis_settings,
            max_jobs=WorkerSettings.max_jobs,
            job_timeout=WorkerSettings.job_timeout,
            keep_result=WorkerSettings.keep_result,
            handle_signals=False
        )
    except TypeError:
        print("Advertencia: Esta versión de arq no soporta handle_signals. Inicializando normal...")
        worker = Worker(
            functions=WorkerSettings.functions,
            redis_settings=WorkerSettings.redis_settings,
            max_jobs=WorkerSettings.max_jobs,
            job_timeout=WorkerSettings.job_timeout,
            keep_result=WorkerSettings.keep_result
        )

    # 2. Aislamos la ejecución del worker. Si Redis falla, el error se imprime pero Uvicorn sigue vivo.
    async def run_worker_safely():
        try:
            await worker.main()
        except Exception as e:
            print(f"ERROR FATAL DE ARQ WORKER (Redis/Conexión): {e}")
            traceback.print_exc()

    # Lanzamos el worker al background
    worker_task = asyncio.create_task(run_worker_safely())
    print("ARQ Worker lanzado. Liberando el hilo principal...")
    
    # ¡Liberamos el hilo inmediatamente para que Uvicorn abra el puerto 8080!
    yield  
    
    # Apagado elegante
    print("Apagando Worker...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

# --- MINI API DE MONITOREO PARA GOOGLE ---
app = FastAPI(lifespan=lifespan)

@app.get("/")
def health_check():
    return {"status": "worker_running_smoothly"}
