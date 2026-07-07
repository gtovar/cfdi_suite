from __future__ import annotations
import asyncio
import base64
import json
import uuid
import os
import zipfile
import io

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

import redis.asyncio as aioredis

from ..services.pdf_pipeline import generate
from ..services.task_dispatcher import enqueue_pdf_generation

router = APIRouter(prefix="/api", tags=["PDF"])

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

pool = aioredis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=True,
    ssl_cert_reqs=None, # Mismo parámetro de tu Mac para máxima estabilidad
    max_connections=30, # Un número balanceado por instancia de Cloud Run
    health_check_interval=25,
    decode_responses=False
)

redis_client = aioredis.Redis(connection_pool=pool)

class GeneratePdfPayload(BaseModel):
    job_id: str
    xml_b64: str
    template_id: str
    html_shell: Optional[str] = None


@router.post("/internal/generate-pdf")
async def internal_generate_pdf(payload: GeneratePdfPayload, request: Request):
    if "x-cloudtasks-queuename" not in request.headers:
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo Cloud Tasks.")

    print(f"Iniciando generación de PDF para Job ID: {payload.job_id}")
    try:
        await redis_client.set(f"pdf:status:{payload.job_id}", b"converting", ex=1800)

        if payload.xml_b64:
            xml_bytes = base64.b64decode(payload.xml_b64)
        else:
            xml_bytes = await redis_client.get(f"pdf:xml:{payload.job_id}")
            
        if not xml_bytes:
            raise HTTPException(status_code=400, detail="XML no encontrado en caché.")

        pdf_bytes = generate(xml_bytes, payload.template_id, payload.html_shell)
        
        await redis_client.set(f"pdf:data:{payload.job_id}", pdf_bytes, ex=1800)
        await redis_client.set(f"pdf:status:{payload.job_id}", b"done", ex=1800)
        await redis_client.delete(f"pdf:xml:{payload.job_id}")
        
        print(f"PDF {payload.job_id} guardado con éxito.")
        return {"status": "success", "message": "PDF generado"}
    except Exception as e:
        print(f"Error generando PDF {payload.job_id}: {e}")
        await redis_client.set(f"pdf:status:{payload.job_id}", b"error", ex=1800)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cfdi/pdf/start")
async def start_pdf_generation(
    file: UploadFile = File(...),
    engine: str = Form("canvas_pipeline"),
    template: Optional[str] = Form(None)
):
    job_id = str(uuid.uuid4())
    xml_content = await file.read()
    
    template_id = "default"
    if template:
        try:
            template_data = json.loads(template)
            template_id = template_data.get("_id", "default")
        except Exception:
            pass

    await redis_client.set(f"pdf:xml:{job_id}", xml_content, ex=900)
    await redis_client.set(f"pdf:status:{job_id}", b"pending", ex=1800)

    try:
        await asyncio.to_thread(enqueue_pdf_generation, job_id=job_id, xml_b64="", template_id=template_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en Cloud Tasks: {e}")
    
    return {"jobId": job_id}


@router.post("/cfdi/pdf/start-zip")
async def start_pdf_zip_generation(
    file: UploadFile = File(...),
    template: Optional[str] = Form(None)
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="El archivo cargado debe ser un formato .ZIP válido.")

    batch_id = str(uuid.uuid4())
    zip_contents = await file.read()
    
    template_id = "default"
    if template:
        try:
            template_data = json.loads(template)
            template_id = template_data.get("_id", "default")
        except Exception:
            pass

    job_ids = []

    try:
        with zipfile.ZipFile(io.BytesIO(zip_contents)) as z:
            for file_info in z.infolist():
                if "__MACOSX" in file_info.filename or ".DS_Store" in file_info.filename:
                    continue

                if file_info.filename.lower().endswith(".xml"):
                    job_id = str(uuid.uuid4())
                    xml_content = z.read(file_info.filename)
                    job_ids.append((job_id, xml_content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="El archivo comprimido está dañado o corrupto.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer el archivo ZIP: {str(e)}")

    if not job_ids:
        raise HTTPException(status_code=400, detail="No se encontraron archivos XML válidos dentro del ZIP.")

    try:
        async with redis_client.pipeline(transaction=False) as pipe:
            for jid, xml_content in job_ids:
                pipe.set(f"pdf:xml:{jid}", xml_content, ex=1800)
                pipe.set(f"pdf:status:{jid}", b"pending", ex=1800)
            await pipe.execute()
    except Exception as redis_err:
        raise HTTPException(
            status_code=507,
            detail=f"La base de datos Redis (Upstash) está LLENA. Detalles: {str(redis_err)}"
        )

    just_ids = [item[0] for item in job_ids]
    await redis_client.set(f"pdf:batch:{batch_id}", json.dumps(just_ids), ex=3600)

    network_semaphore = asyncio.Semaphore(50)

    async def safe_enqueue_task(jid: str):
        async with network_semaphore:
            try:
                # Ejecutamos la función síncrona dentro del pool de hilos de forma segura
                await asyncio.to_thread(enqueue_pdf_generation, job_id=jid, xml_b64="", template_id=template_id)
            except Exception as ex:
                print(f"Error registrando archivo {jid} en la cola de Google: {ex}")
                await redis_client.set(f"pdf:status:{jid}", b"error", ex=1800)

    async_tasks = [safe_enqueue_task(jid) for jid in just_ids]
    await asyncio.gather(*async_tasks)
    
    return {
        "batchId": batch_id,
        "totalFiles": len(just_ids)
    }


# CORREGIDO: Eliminamos el /api duplicado de la ruta (ya viene en el prefix del router)
@router.get("/cfdi/pdf/batch/{batch_id}/progress")
async def batch_progress(batch_id: str):
    async def event_generator():
        while True:
            batch_data = await redis_client.get(f"pdf:batch:{batch_id}")
            if not batch_data:
                yield 'data: {"status": "error", "message": "Lote no encontrado"}\n\n'
                break
                
            job_ids = json.loads(batch_data.decode("utf-8"))
            total = len(job_ids)
            
            done = 0
            error = 0
            converting = 0
            pending = 0
            
            keys = [f"pdf:status:{jid}" for jid in job_ids]
            statuses = await redis_client.mget(keys)
            
            for status_bytes in statuses:
                status = status_bytes.decode("utf-8") if status_bytes else "pending"
                if status == "done":
                    done += 1
                elif status == "error":
                    error += 1
                elif status == "converting":
                    converting += 1
                else:
                    pending += 1
                    
            processed = done + error
            porcentaje = int((processed / total) * 100) if total > 0 else 0
            
            payload = {
                "status": "processing" if processed < total else "done",
                "total": total,
                "done": done,
                "error": error,
                "converting": converting,
                "pending": pending,
                "percentage": porcentaje
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if processed >= total:
                break
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/cfdi/pdf/batch/{batch_id}/download")
async def download_batch_zip(batch_id: str):
    batch_data = await redis_client.get(f"pdf:batch:{batch_id}")
    if not batch_data:
        raise HTTPException(status_code=404, detail="El lote especificado no existe o ya expiró.")
        
    job_ids = json.loads(batch_data.decode("utf-8"))
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for jid in job_ids:
            pdf_bytes = await redis_client.get(f"pdf:data:{jid}")
            if pdf_bytes:
                z.writestr(f"cfdi_{jid}.pdf", pdf_bytes)
                
    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="resultado_pdfs_{batch_id}.zip"'}
    )


@router.get("/cfdi/pdf/{job_id}/progress")
async def pdf_progress(job_id: str):
    async def event_generator():
        while True:
            status_bytes = await redis_client.get(f"pdf:status:{job_id}")
            status = status_bytes.decode("utf-8") if status_bytes else "pending"
            if status in ["done", "error"]:
                yield f'data: {{"status": "{status}"}}\n\n'
                break
            yield 'data: {"status": "converting"}\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/cfdi/pdf/{job_id}/download")
async def download_pdf(job_id: str):
    pdf_bytes = await redis_client.get(f"pdf:data:{job_id}")
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="El PDF expiró o no existe.")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="cfdi_{job_id}.pdf"'}
    )
