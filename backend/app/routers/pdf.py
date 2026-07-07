import base64
import json
import uuid
import os
import asyncio
# Importamos redis.asyncio para manejar conexiones asíncronas a tu Upstash
import redis.asyncio as aioredis
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from ..services.pdf_pipeline import generate
from ..services.task_dispatcher import enqueue_pdf_generation

router = APIRouter(prefix="/api", tags=["PDF"])

# 1. CONEXIÓN A TU UPSTASH REDIS (Usa las variables de entorno que ya tienes en Cloud Run)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

redis_client = aioredis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    decode_responses=False  # Lo dejamos en False para que no corrompa los bytes del PDF
)

class GeneratePdfPayload(BaseModel):
    job_id: str
    xml_b64: str
    template_id: str
    html_shell: Optional[str] = None

# --- 2. ENDPOINT INTERNO (Llamado por Google Cloud Tasks) ---
@router.post("/internal/generate-pdf")
async def internal_generate_pdf(payload: GeneratePdfPayload, request: Request):
    if "x-cloudtasks-queuename" not in request.headers:
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo Cloud Tasks.")

    print(f"Iniciando generación de PDF pesada para Job ID: {payload.job_id}")
    try:
        # Marcamos en Redis que la tarea ya se está procesando
        await redis_client.set(f"pdf:status:{payload.job_id}", b"converting", ex=3600)

        # Generamos los bytes reales del PDF
        xml_bytes = base64.b64decode(payload.xml_b64)
        pdf_bytes = generate(xml_bytes, payload.template_id, payload.html_shell)
        
        # Guardamos el PDF resultante y actualizamos el estado a "done" (Expira en 1 hora)
        await redis_client.set(f"pdf:data:{payload.job_id}", pdf_bytes, ex=3600)
        await redis_client.set(f"pdf:status:{payload.job_id}", b"done", ex=3600)
        
        print(f"PDF {payload.job_id} generado con éxito y guardado en Redis.")
        return {"status": "success", "message": "PDF generado con éxito"}
    except Exception as e:
        print(f"Error generando PDF {payload.job_id}: {e}")
        # Si algo falla, le avisamos a Redis para que el frontend no se quede esperando eternamente
        await redis_client.set(f"pdf:status:{payload.job_id}", b"error", ex=3600)
        raise HTTPException(status_code=500, detail=str(e))


# --- 3. ENDPOINT DE INICIO (Llamado por el Frontend) ---
@router.post("/cfdi/pdf/start")
async def start_pdf_generation(
    file: UploadFile = File(...),
    engine: str = Form("canvas_pipeline"),
    template: Optional[str] = Form(None)
):
    job_id = str(uuid.uuid4())
    xml_content = await file.read()
    
    xml_b64 = base64.b64encode(xml_content).decode("utf-8")
    
    template_id = "default"
    if template:
        try:
            template_data = json.loads(template)
            template_id = template_data.get("_id", "default")
        except Exception:
            pass

    # Colocamos el estado inicial en Redis
    await redis_client.set(f"pdf:status:{job_id}", b"pending", ex=3600)

    # Despachamos la tarea asíncrona a la cola de Google Cloud Tasks
    try:
        enqueue_pdf_generation(
            job_id=job_id,
            xml_b64=xml_b64,
            template_id=template_id
        )
        print(f"Éxito: Tarea para el Job {job_id} enviada a Google Cloud Tasks.")
    except Exception as e:
        print(f"Error crítico al encolar en Cloud Tasks: {e}")
        raise HTTPException(status_code=500, detail="Error al procesar la cola de tareas.")
    
    return {"jobId": job_id}


# --- 4. ENDPOINT DE PROGRESO (Llamado por el Frontend) ---
@router.get("/cfdi/pdf/{job_id}/progress")
async def pdf_progress(job_id: str):
    """
    Monitorea Redis en tiempo real y le avisa al frontend (SSE) el estado de la tarea.
    """
    async def event_generator():
        while True:
            status_bytes = await redis_client.get(f"pdf:status:{job_id}")
            status = status_bytes.decode("utf-8") if status_bytes else "pending"
            
            if status == "done":
                yield 'data: {"status": "done"}\n\n'
                break
            elif status == "error":
                yield 'data: {"status": "error", "error": "Error al procesar el PDF en el servidor"}\n\n'
                break
            else:
                yield 'data: {"status": "converting"}\n\n'
            
            # Esperamos 1 segundo antes de volver a consultar Redis para no saturar la base de datos
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- 5. ENDPOINT DE DESCARGA (Llamado por el Frontend) ---
@router.get("/cfdi/pdf/{job_id}/download")
async def download_pdf(job_id: str):
    """
    Entrega los bytes reales del PDF que Cloud Tasks guardó en Redis.
    """
    pdf_bytes = await redis_client.get(f"pdf:data:{job_id}")
    
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="El PDF no fue encontrado o ya expiró.")
        
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cfdi_{job_id}.pdf"'
        }
    )
