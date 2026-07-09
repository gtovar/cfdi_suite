from __future__ import annotations
import asyncio
import base64
import json
import uuid
import os
import zipfile
import io
import zlib
import datetime

# --- AÑADIR ESTAS DOS LÍNEAS AQUÍ ARRIBA ---
import google.auth
import google.auth.transport.requests
# ----------------------------------------

from google.cloud import storage

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from opentelemetry import trace

import urllib.request
import traceback

tracer = trace.get_tracer(__name__)

import redis.asyncio as aioredis

from ..services.pdf_pipeline import generate
from ..services.task_dispatcher import enqueue_pdf_generation

router = APIRouter(prefix="/api", tags=["PDF"])

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "tu-bucket-cfdi-suite")

redis_client = aioredis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=True,
    ssl_cert_reqs=None,
    max_connections=30,
    health_check_interval=25,
    decode_responses=False # Mantener en False para los bytes binarios del PDF
)

class GeneratePdfPayload(BaseModel):
    job_id: str
    xml_b64: str
    template_id: str
    html_shell: Optional[str] = None

# --- NUEVOS MODELOS PARA EL FLUJO STORAGE ---
class SignedUrlResponse(BaseModel):
    uploadUrl: str
    gcsPath: str

class ProcessGcsZipPayload(BaseModel):
    gcsPath: str
    template: Optional[str] = None

@router.post("/internal/generate-pdf")
async def internal_generate_pdf(payload: GeneratePdfPayload, request: Request):
    if "x-cloudtasks-queuename" not in request.headers:
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo Cloud Tasks.")

    print(f"Iniciando generación de PDF para Job ID: {payload.job_id}")
    try:
        await redis_client.set(f"pdf:status:{payload.job_id}", b"converting", ex=3600)

        if payload.xml_b64:
            xml_bytes = base64.b64decode(payload.xml_b64)
        else:
            compressed_xml = await redis_client.get(f"pdf:xml:{payload.job_id}")
            xml_bytes = zlib.decompress(compressed_xml) if compressed_xml else None
            
        if not xml_bytes:
            raise HTTPException(status_code=400, detail="XML no encontrado en caché.")

        # 🕒 Medimos exactamente la "Regadera"
        with tracer.start_as_current_span("generacion_pdf_intensiva"):
            pdf_bytes = generate(xml_bytes, payload.template_id, payload.html_shell)
        
        await redis_client.set(f"pdf:data:{payload.job_id}", zlib.compress(pdf_bytes), ex=1800)
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

    await redis_client.set(f"pdf:xml:{job_id}", zlib.compress(xml_content), ex=900)
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
    
    template_id = "default"
    if template:
        try:
            template_data = json.loads(template)
            template_id = template_data.get("_id", "default")
        except Exception:
            pass

    job_ids = []

    try:
        with zipfile.ZipFile(file.file, "r") as z:
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

    # 📊 CONTROL DE CALIDAD Y AUDITORÍA (Validación del Embudo)
    total_bytes_descomprimidos = sum(len(xml_content) for jid, xml_content in job_ids)
    mb_reales = total_bytes_descomprimidos / (1024 * 1024)
    total_comandos_pipeline = len(job_ids) * 2 # 2 comandos (SET xml y SET status) por cada archivo

    # Constantes oficiales de tu plan de Upstash para pintar la comparativa
    UPSTASH_STORAGE_MAX_MB = 256         # Capacidad total del Tanque
    UPSTASH_REQUEST_MAX_MB = 50          # Capacidad máxima del Embudo por petición
    UPSTASH_DAILY_COMMANDS_LIMIT = "10,000 (Plan Free) / ilimitados (Plan Paid)"

    print("\n" + "="*80)
    print("🔍 [AUDITORÍA DE INFRAESTRUCTURA - TRANSMISIÓN DE DATOS]")
    print(f"📦 EL TANQUE (Almacenamiento): {mb_reales:.2f} MB ocupados de {UPSTASH_STORAGE_MAX_MB} MB disponibles en tu capacidad total.")
    print(f"⚠️ EL EMBUDO (Payload Size):  {mb_reales:.2f} MB enviados de {UPSTASH_REQUEST_MAX_MB} MB máximos permitidos en una sola petición.")
    print(f"🔀 COMANDOS EN PIPELINE:     Total de comandos de escritura en el Pipeline: {total_comandos_pipeline} de {UPSTASH_DAILY_COMMANDS_LIMIT}.")
    print("="*80 + "\n")

    # El bloque que va justo abajo de los prints de auditoría en pdf.py
    try:
        CHUNK_SIZE = 20
        for i in range(0, len(job_ids), CHUNK_SIZE):
            chunk = job_ids[i:i + CHUNK_SIZE]
            
            async with redis_client.pipeline(transaction=False) as pipe:
                for jid, xml_content in chunk:
                    pipe.set(f"pdf:xml:{jid}", zlib.compress(xml_content), ex=1800)
                    pipe.set(f"pdf:status:{jid}", b"pending", ex=1800)
                await pipe.execute() # <-- Cada paquete medirá escasos 4 MB, entrando limpiecito al embudo
                
    except Exception as redis_err:
        raise HTTPException(
            status_code=500,
            detail=f"Error de comunicación con el State Store de Redis: {str(redis_err)}"
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
            compressed_pdf = await redis_client.get(f"pdf:data:{jid}")
            if compressed_pdf:
                z.writestr(f"cfdi_{jid}.pdf", zlib.decompress(compressed_pdf))
                
    # 1. Regresamos el puntero al inicio del buffer en memoria
    zip_buffer.seek(0)
    
    # 2. SOLUCIÓN: Agregamos 'async def' para que sea un iterador asíncrono nativo
    async def stream_chunks():
        while chunk := zip_buffer.read(64 * 1024):
            yield chunk

    # 3. Le pasamos el generador asíncrono al StreamingResponse
    return StreamingResponse(
        stream_chunks(),
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
    compressed_pdf = await redis_client.get(f"pdf:data:{job_id}")
    if not compressed_pdf:
        raise HTTPException(status_code=404, detail="El PDF expiró o no existe.")
    return Response(
        content=zlib.decompress(compressed_pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="cfdi_{job_id}.pdf"'}
    )


@router.post("/cfdi/pdf/request-upload", response_model=SignedUrlResponse)
async def request_upload_url():
    """
    Genera una URL temporal firmada para que el frontend pueda subir el ZIP pesado 
    directamente a un Bucket de Google Cloud Storage usando Cloud Run.
    """
    try:
        # 1. Obtenemos credenciales base
        credentials, project = google.auth.default()
        
        # 2. CRUCIAL: Refrescamos explícitamente para garantizar que tengamos un 'access_token'
        auth_request = google.auth.transport.requests.Request()
        credentials.refresh(auth_request)
        
        # 3. Extraemos el email
        service_account_email = getattr(credentials, 'service_account_email', None)
        if not service_account_email:
            try:
                meta_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
                req = urllib.request.Request(meta_url, headers={"Metadata-Flavor": "Google"})
                with urllib.request.urlopen(req, timeout=2) as response:
                    service_account_email = response.read().decode('utf-8').strip()
            except Exception as e:
                print(f"Advertencia: No se pudo obtener el email del metadata server: {e}")

        storage_client = storage.Client(credentials=credentials)
        bucket = storage_client.bucket(BUCKET_NAME)
        
        unique_id = str(uuid.uuid4())
        gcs_path = f"uploads/{unique_id}.zip"
        blob = bucket.blob(gcs_path)
        
        # 4. Generamos la URL usando la firma remota de IAM
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="PUT",
            content_type="application/zip",
            service_account_email=service_account_email,
            access_token=credentials.token  # <--- ESTO EVITA EL ERROR DE LA PRIVATE KEY
        )
        
        return {
            "uploadUrl": upload_url,
            "gcsPath": gcs_path
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creando la Signed URL: {str(e)}")

# 5. Agrega el endpoint que procesa el ZIP desde Google Cloud Storage
@router.post("/cfdi/pdf/start-zip-gcs")
async def start_pdf_zip_gcs_generation(payload: ProcessGcsZipPayload):
    """
    Descarga y procesa el ZIP guardado en GCS. Conserva al 100% tu lógica 
    original de chunking para Redis y encolamiento en Cloud Tasks.
    """
    template_id = "default"
    if payload.template:
        try:
            template_data = json.loads(payload.template)
            template_id = template_data.get("_id", "default")
        except Exception:
            pass

    batch_id = str(uuid.uuid4())
    job_ids = []

    try:
        # Descargamos los bytes del ZIP de GCS directo a la memoria del contenedor
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(payload.gcsPath)
        
        zip_bytes = blob.download_as_bytes()
        zip_buffer = io.BytesIO(zip_bytes)
        
        # Leemos el ZIP exactamente igual que antes
        with zipfile.ZipFile(zip_buffer, "r") as z:
            for file_info in z.infolist():
                if "__MACOSX" in file_info.filename or ".DS_Store" in file_info.filename:
                    continue

                if file_info.filename.lower().endswith(".xml"):
                    job_id = str(uuid.uuid4())
                    xml_content = z.read(file_info.filename)
                    job_ids.append((job_id, xml_content))
                    
        # OPCIONAL: Si no deseas almacenar basura histórica, puedes eliminar el ZIP de GCS aquí
        # blob.delete()
        
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="El archivo comprimido está dañado o corrupto.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al descargar o leer desde GCS: {str(e)}")

    if not job_ids:
        raise HTTPException(status_code=400, detail="No se encontraron archivos XML válidos dentro del ZIP.")

    # 📊 AUDITORÍA (Conserva tu código original intacto)
    total_bytes_descomprimidos = sum(len(xml_content) for jid, xml_content in job_ids)
    mb_reales = total_bytes_descomprimidos / (1024 * 1024)
    total_comandos_pipeline = len(job_ids) * 2

    print("\n" + "="*80)
    print("🔍 [AUDITORÍA DE INFRAESTRUCTURA DESDE STORAGE]")
    print(f"📦 DATOS PROCESADOS: {mb_reales:.2f} MB.")
    print("="*80 + "\n")

    # 🔀 CHUNKING DE REDIS EN BLOQUES DE 20 (Mantiene protegido tu Upstash Redis)
    try:
        CHUNK_SIZE = 20
        for i in range(0, len(job_ids), CHUNK_SIZE):
            chunk = job_ids[i:i + CHUNK_SIZE]
            async with redis_client.pipeline(transaction=False) as pipe:
                for jid, xml_content in chunk:
                    pipe.set(f"pdf:xml:{jid}", zlib.compress(xml_content), ex=1800)
                    pipe.set(f"pdf:status:{jid}", b"pending", ex=1800)
                await pipe.execute()
    except Exception as redis_err:
        raise HTTPException(status_code=500, detail=f"Error con State Store de Redis: {str(redis_err)}")

    just_ids = [item[0] for item in job_ids]
    await redis_client.set(f"pdf:batch:{batch_id}", json.dumps(just_ids), ex=3600)

    network_semaphore = asyncio.Semaphore(50)

    async def safe_enqueue_task(jid: str):
        async with network_semaphore:
            try:
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
