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
import tempfile
import time

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
from ..services.realtime import publish_batch_progress
from ..services.task_dispatcher import enqueue_pdf_generation, enqueue_zip_extraction

router = APIRouter(prefix="/api", tags=["PDF"])

# Techo duro por conexión SSE. Con concurrency=1 cada stream abierto retiene
# una instancia entera de Cloud Run; el cliente (subscribeWithRetry) se
# reconecta solo al cortarse, así que esto no interrumpe al usuario — solo
# evita que un stream retenga la instancia los 1800s del timeout del servicio.
SSE_MAX_STREAM_SECONDS = 600

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "cfdi-suite-uploads-706861124428")

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
    batch_id: Optional[str] = None

# --- NUEVOS MODELOS PARA EL FLUJO STORAGE ---
class SignedUrlResponse(BaseModel):
    uploadUrl: str
    gcsPath: str

class ProcessGcsZipPayload(BaseModel):
    gcsPath: str
    template: Optional[str] = None

class DownloadUrlResponse(BaseModel):
    downloadUrl: str

class ExtractZipPayload(BaseModel):
    gcs_path: str
    batch_id: str
    template_id: str


def _is_valid_xml_entry(file_info: zipfile.ZipInfo) -> bool:
    if "__MACOSX" in file_info.filename or ".DS_Store" in file_info.filename:
        return False
    return file_info.filename.lower().endswith(".xml")


PUBLISH_EVERY_N_JOBS = 5


async def _publish_batch_tick(batch_id: str, *, definitive_error: bool = False):
    """Cuenta el avance con INCR atómico y lo empuja a Pusher.

    Publica cada N archivos (y siempre al llegar al total) — así los
    espectadores reciben el progreso sin SSE ni polling a Redis. Solo se
    cuenta el error definitivo (XML desaparecido); los errores transitorios
    no, porque Cloud Tasks los reintenta y podrían terminar en éxito.
    """
    counter = "error_count" if definitive_error else "done_count"
    await redis_client.incr(f"pdf:{counter}:{batch_id}")
    await redis_client.expire(f"pdf:{counter}:{batch_id}", 3600)

    total_bytes = await redis_client.get(f"pdf:extracting_total:{batch_id}")
    total = int(total_bytes) if total_bytes else 0
    if total <= 0:
        return

    done = int(await redis_client.get(f"pdf:done_count:{batch_id}") or 0)
    error = int(await redis_client.get(f"pdf:error_count:{batch_id}") or 0)
    processed = done + error
    if processed < total and processed % PUBLISH_EVERY_N_JOBS != 0 and not definitive_error:
        return

    payload = {
        "status": "done" if processed >= total else "processing",
        "total": total,
        "done": done,
        "error": error,
        "converting": 0,
        "pending": max(total - processed, 0),
        "percentage": int((processed / total) * 100),
    }
    await asyncio.to_thread(publish_batch_progress, batch_id, payload)


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
            # 1️⃣ Buscamos en Redis primero (por si quedaron tareas viejas en la cola)
            compressed_xml = await redis_client.get(f"pdf:xml:{payload.job_id}")
            if compressed_xml:
                xml_bytes = zlib.decompress(compressed_xml)
            else:
                # 2️⃣ NUEVO: Si no está en Redis, buscamos en Cloud Storage temporal
                storage_client = storage.Client()
                bucket = storage_client.bucket(BUCKET_NAME)
                blob_xml = bucket.blob(f"xml_temp/{payload.job_id}.xml")
                
                if await asyncio.to_thread(blob_xml.exists):
                    xml_bytes = await asyncio.to_thread(blob_xml.download_as_bytes)
                else:
                    xml_bytes = None
            
        if not xml_bytes:
            await redis_client.set(f"pdf:status:{payload.job_id}", b"error", ex=1800)
            print(f"Abortando Job {payload.job_id}: XML ya no existe ni en Redis ni en GCS.")
            if payload.batch_id:
                try:
                    await _publish_batch_tick(payload.batch_id, definitive_error=True)
                except Exception as tick_err:
                    print(f"Aviso: tick de progreso no publicado para {payload.batch_id}: {tick_err}")
            return Response(status_code=204)

        with tracer.start_as_current_span("generacion_pdf_intensiva"):
            pdf_bytes = generate(xml_bytes, payload.template_id, payload.html_shell)
        
        # Guardado final del PDF
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"pdfs/{payload.job_id}.pdf")
        await asyncio.to_thread(blob.upload_from_string, pdf_bytes, content_type="application/pdf")
        
        await redis_client.set(f"pdf:status:{payload.job_id}", b"done", ex=86400)
        await redis_client.delete(f"pdf:xml:{payload.job_id}")
        
        # 3️⃣ NUEVO: Borramos el XML temporal de GCS para no dejar basura
        try:
            blob_xml = bucket.blob(f"xml_temp/{payload.job_id}.xml")
            if await asyncio.to_thread(blob_xml.exists):
                await asyncio.to_thread(blob_xml.delete)
        except Exception as e:
            print(f"Aviso: No se pudo limpiar el XML temporal {payload.job_id}: {e}")
 
        print(f"PDF {payload.job_id} guardado con éxito.")
        if payload.batch_id:
            try:
                await _publish_batch_tick(payload.batch_id)
            except Exception as tick_err:
                print(f"Aviso: tick de progreso no publicado para {payload.batch_id}: {tick_err}")
        return {"status": "success", "message": "PDF generado"}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error generando PDF {payload.job_id}: {e}")
        try:
            await redis_client.set(f"pdf:status:{payload.job_id}", b"error", ex=1800)
        except Exception as redis_err:
            pass
        
        error_str = str(e).lower()
        if "quota exceeded" in error_str or "oom" in error_str:
            raise HTTPException(status_code=429, detail="El motor de procesamiento está a máxima capacidad.")
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

    # ☁️ NUEVO: Subir XML temporal a Google Cloud Storage
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_xml = bucket.blob(f"xml_temp/{job_id}.xml")
    await asyncio.to_thread(blob_xml.upload_from_string, xml_content, content_type="application/xml")

    # 🟢 En Redis SOLO guardamos el estatus inicial pendiente (pesa nada)
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
                if _is_valid_xml_entry(file_info):
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
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        
        CHUNK_SIZE = 20
        for i in range(0, len(job_ids), CHUNK_SIZE):
            chunk = job_ids[i:i + CHUNK_SIZE]
            
            # a) En Redis SÓLO creamos el estatus "pending" (pesa unos bytes)
            async with redis_client.pipeline(transaction=False) as pipe:
                for jid, _ in chunk:
                    pipe.set(f"pdf:status:{jid}", b"pending", ex=1800)
                await pipe.execute()
                
            # b) Subimos los contenidos XML reales a Cloud Storage temporal
            for jid, xml_content in chunk:
                blob_xml = bucket.blob(f"xml_temp/{jid}.xml")
                await asyncio.to_thread(blob_xml.upload_from_string, xml_content, content_type="application/xml")
                
    except Exception as infra_err:
        raise HTTPException(
            status_code=500,
            detail=f"Error al almacenar en GCS o Redis: {str(infra_err)}"
        )

    just_ids = [item[0] for item in job_ids]
    await redis_client.set(f"pdf:extracting_total:{batch_id}", len(just_ids), ex=3600)
    await redis_client.sadd(f"pdf:batch_ids:{batch_id}", *just_ids)
    await redis_client.expire(f"pdf:batch_ids:{batch_id}", 3600)

    network_semaphore = asyncio.Semaphore(50)

    async def safe_enqueue_task(jid: str):
        async with network_semaphore:
            try:
                # Ejecutamos la función síncrona dentro del pool de hilos de forma segura
                await asyncio.to_thread(enqueue_pdf_generation, job_id=jid, xml_b64="", template_id=template_id, batch_id=batch_id)
            except Exception as ex:
                print(f"Error registrando archivo {jid} en la cola de Google: {ex}")
                await redis_client.set(f"pdf:status:{jid}", b"error", ex=1800)

    async_tasks = [safe_enqueue_task(jid) for jid in just_ids]
    await asyncio.gather(*async_tasks)
    
    return {
        "batchId": batch_id,
        "totalFiles": len(just_ids)
    }


async def _batch_progress_snapshot(batch_id: str) -> dict:
    """Estado actual del lote calculado desde Redis (fuente de verdad).

    Lo comparten el SSE legacy y el endpoint /status; los ticks de Pusher usan
    contadores aproximados, este cálculo (MGET de statuses) es el exacto.
    """
    # Si el loop de extracción murió a mitad de camino, no dejamos la barra
    # congelada hasta el timeout del cliente: reportamos el error de inmediato.
    extracting_error = await redis_client.get(f"pdf:extracting_error:{batch_id}")
    if extracting_error:
        return {"status": "error", "message": extracting_error.decode("utf-8")}

    total_bytes = await redis_client.get(f"pdf:extracting_total:{batch_id}")
    if total_bytes is None:
        # Aún no conocemos el total real (ventana muy breve al arrancar).
        is_extracting = await redis_client.get(f"pdf:extracting:{batch_id}")
        if is_extracting:
            return {"status": "processing", "total": 0, "done": 0, "error": 0, "converting": 0, "pending": 0, "percentage": 0, "message": "Preparando lote..."}
        return {"status": "error", "message": "Lote no encontrado"}

    total = int(total_bytes)
    if total == 0:
        return {"status": "done", "total": 0, "done": 0, "error": 0, "converting": 0, "pending": 0, "percentage": 100}

    registered_raw = await redis_client.smembers(f"pdf:batch_ids:{batch_id}")
    registered_ids = [rid.decode("utf-8") for rid in registered_raw]

    done = error = converting = 0
    if registered_ids:
        keys = [f"pdf:status:{jid}" for jid in registered_ids]
        statuses = await redis_client.mget(keys)
        for status_bytes in statuses:
            status = status_bytes.decode("utf-8") if status_bytes else "pending"
            if status == "done":
                done += 1
            elif status == "error":
                error += 1
            elif status == "converting":
                converting += 1

    registered_pending = len(registered_ids) - done - error - converting
    not_yet_registered = total - len(registered_ids)
    pending = max(registered_pending, 0) + max(not_yet_registered, 0)
    processed = done + error

    return {
        "status": "processing" if processed < total else "done",
        "total": total,
        "done": done,
        "error": error,
        "converting": converting,
        "pending": pending,
        "percentage": int((processed / total) * 100)
    }


@router.get("/cfdi/pdf/batch/{batch_id}/status")
async def batch_status(batch_id: str):
    """Snapshot puntual del progreso — request corta que no retiene instancia.

    El frontend lo usa para hidratarse al conectar/reconectar y como
    reconciliación periódica; el avance en vivo llega por Pusher.
    """
    return await _batch_progress_snapshot(batch_id)


# CORREGIDO: Eliminamos el /api duplicado de la ruta (ya viene en el prefix del router)
@router.get("/cfdi/pdf/batch/{batch_id}/progress")
async def batch_progress(batch_id: str):
    async def event_generator():
        deadline = time.monotonic() + SSE_MAX_STREAM_SECONDS
        while time.monotonic() < deadline:
            snapshot = await _batch_progress_snapshot(batch_id)
            yield f"data: {json.dumps(snapshot)}\n\n"
            if snapshot["status"] in ("done", "error"):
                break
            await asyncio.sleep(1)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cfdi/pdf/batch/{batch_id}/ready-files")
async def list_ready_files(batch_id: str):
    """
    IDs de los archivos ya convertidos (status 'done') hasta ahora — el
    frontend la usa para ir llenando la tabla de descargas individuales
    conforme avanza el lote, sin esperar a que todo el batch termine.
    """
    registered_raw = await redis_client.smembers(f"pdf:batch_ids:{batch_id}")
    if not registered_raw:
        return {"jobIds": []}

    job_ids = [rid.decode("utf-8") for rid in registered_raw]
    keys = [f"pdf:status:{jid}" for jid in job_ids]
    statuses = await redis_client.mget(keys)

    ready = [
        jid for jid, status_bytes in zip(job_ids, statuses)
        if status_bytes and status_bytes.decode("utf-8") == "done"
    ]
    return {"jobIds": ready}


@router.get("/cfdi/pdf/batch/{batch_id}/download")
async def download_batch_zip(batch_id: str):
    registered_raw = await redis_client.smembers(f"pdf:batch_ids:{batch_id}")
    if not registered_raw:
        raise HTTPException(status_code=404, detail="El lote especificado no existe o ya expiró.")

    job_ids = [rid.decode("utf-8") for rid in registered_raw]
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    # Descargas concurrentes (antes eran secuenciales, una por una) — para
    # lotes grandes esto es lo que hacía que la respuesta tardara demasiado
    # en mandar el primer byte.
    download_semaphore = asyncio.Semaphore(50)

    async def fetch_pdf(jid: str):
        async with download_semaphore:
            blob = bucket.blob(f"pdfs/{jid}.pdf")
            try:
                pdf_bytes = await asyncio.to_thread(blob.download_as_bytes)
                return jid, pdf_bytes
            except Exception:
                return jid, None

    results = await asyncio.gather(*[fetch_pdf(jid) for jid in job_ids])

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for jid, pdf_bytes in results:
            if pdf_bytes is not None:
                z.writestr(f"cfdi_{jid}.pdf", pdf_bytes)
 
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
        deadline = time.monotonic() + SSE_MAX_STREAM_SECONDS
        while time.monotonic() < deadline:
            status_bytes = await redis_client.get(f"pdf:status:{job_id}")
            status = status_bytes.decode("utf-8") if status_bytes else "pending"
            if status in ["done", "error"]:
                yield f'data: {{"status": "{status}"}}\n\n'
                break
            yield 'data: {"status": "converting"}\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.get("/cfdi/pdf/{job_id}/download")
async def download_pdf(job_id: str):
    # Primero verificamos rápidamente en Redis si el estatus dice "done"
    status_bytes = await redis_client.get(f"pdf:status:{job_id}")
    if not status_bytes or status_bytes.decode("utf-8") != "done":
        raise HTTPException(status_code=404, detail="El PDF aún no está listo o expiró.")

    # Descargamos desde Google Cloud Storage
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(f"pdfs/{job_id}.pdf")
    
    if not blob.exists():
         raise HTTPException(status_code=404, detail="El archivo PDF no se encontró en Storage.")
         
    pdf_bytes = await asyncio.to_thread(blob.download_as_bytes)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="cfdi_{job_id}.pdf"'}
    )

def _get_signing_credentials():
    """
    Credenciales base + email de service account, usados para firmar URLs
    (subida o descarga) vía la firma remota de IAM en Cloud Run, donde no
    hay una private key local disponible.
    """
    credentials, _ = google.auth.default()
    auth_request = google.auth.transport.requests.Request()
    credentials.refresh(auth_request)

    service_account_email = getattr(credentials, 'service_account_email', None)
    if not service_account_email:
        try:
            meta_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
            req = urllib.request.Request(meta_url, headers={"Metadata-Flavor": "Google"})
            with urllib.request.urlopen(req, timeout=2) as response:
                service_account_email = response.read().decode('utf-8').strip()
        except Exception as e:
            print(f"Advertencia: No se pudo obtener el email del metadata server: {e}")

    return credentials, service_account_email


@router.post("/cfdi/pdf/request-upload", response_model=SignedUrlResponse)
async def request_upload_url():
    """
    Genera una URL temporal firmada para que el frontend pueda subir el ZIP pesado
    directamente a un Bucket de Google Cloud Storage usando Cloud Run.
    """
    try:
        credentials, service_account_email = _get_signing_credentials()
        storage_client = storage.Client(credentials=credentials)
        bucket = storage_client.bucket(BUCKET_NAME)

        unique_id = str(uuid.uuid4())
        gcs_path = f"uploads/{unique_id}.zip"
        blob = bucket.blob(gcs_path)

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


@router.get("/cfdi/pdf/{job_id}/download-url", response_model=DownloadUrlResponse)
async def get_pdf_download_url(job_id: str):
    """
    Signed URL de lectura para un PDF individual ya listo — el navegador
    descarga directo de GCS, sin pasar por Cloud Run ni por el rewrite de
    Vercel (evita el límite de 120s de proxies externos para lotes grandes).
    """
    status_bytes = await redis_client.get(f"pdf:status:{job_id}")
    if not status_bytes or status_bytes.decode("utf-8") != "done":
        raise HTTPException(status_code=404, detail="El PDF aún no está listo o expiró.")

    try:
        credentials, service_account_email = _get_signing_credentials()
        storage_client = storage.Client(credentials=credentials)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"pdfs/{job_id}.pdf")

        download_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="GET",
            response_disposition=f'attachment; filename="cfdi_{job_id}.pdf"',
            service_account_email=service_account_email,
            access_token=credentials.token,
        )
        return {"downloadUrl": download_url}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creando la Signed URL de descarga: {str(e)}")


@router.post("/internal/extract-zip")
async def internal_extract_zip(payload: ExtractZipPayload, request: Request):
    """
    Disparado por Cloud Tasks (no directo por el usuario) — corre la
    extracción dentro de un request HTTP real en vez de un BackgroundTask,
    para que Cloud Run mantenga la instancia activa mientras dura, y para
    que Cloud Tasks reintente automáticamente si falla a medio camino.
    """
    if "x-cloudtasks-queuename" not in request.headers:
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo Cloud Tasks.")

    await process_zip_in_background(payload.gcs_path, payload.batch_id, payload.template_id)
    return {"status": "success"}


async def process_zip_in_background(gcs_path: str, batch_id: str, template_id: str):
    """
    Descarga el ZIP a disco (no a RAM), lo lee y manda los XMLs a GCS
    temporal y los estados mínimos a Redis. Invocada desde internal_extract_zip.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(gcs_path)
    
    # Descargamos a un archivo temporal en disco, liberando la RAM. Esto puede
    # tardar segundos para ZIPs grandes — correrlo en un hilo evita bloquear el
    # event loop (y con él, el polling de progreso de este u otros batches en
    # la misma instancia).
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        temp_filename = tmp.name
    await asyncio.to_thread(blob.download_to_filename, temp_filename)

    try:
        with zipfile.ZipFile(temp_filename, "r") as z:
            xml_entries = [fi for fi in z.infolist() if _is_valid_xml_entry(fi)]
            # Total real conocido de inmediato: el frontend deja de ver 0% fijo
            # desde los primeros segundos, en vez de hasta que todo el ZIP termine.
            await redis_client.set(f"pdf:extracting_total:{batch_id}", len(xml_entries), ex=3600)

            chunk = []
            CHUNK_SIZE = 20

            async def flush_chunk(current_chunk):
                # a) Redis: estado "pending" + registro incremental del batch
                #    (mismo pipeline, así el TTL del set nunca queda huérfano
                #    si el proceso muere a mitad de camino)
                async with redis_client.pipeline(transaction=False) as pipe:
                    for jid, _ in current_chunk:
                        pipe.set(f"pdf:status:{jid}", b"pending", ex=1800)
                    pipe.sadd(f"pdf:batch_ids:{batch_id}", *[jid for jid, _ in current_chunk])
                    pipe.expire(f"pdf:batch_ids:{batch_id}", 3600)
                    await pipe.execute()

                # b) Storage: el archivo pesado
                for jid, xml_data in current_chunk:
                    blob_xml = bucket.blob(f"xml_temp/{jid}.xml")
                    await asyncio.to_thread(blob_xml.upload_from_string, xml_data, content_type="application/xml")

                # c) Cloud Tasks: encolamos
                for jid, _ in current_chunk:
                    try:
                        await asyncio.to_thread(enqueue_pdf_generation, job_id=jid, xml_b64="", template_id=template_id, batch_id=batch_id)
                    except Exception as ex:
                        print(f"Error registrando en Tasks {jid}: {ex}")
                        await redis_client.set(f"pdf:status:{jid}", b"error", ex=1800)

            for file_info in xml_entries:
                # Determinístico (no uuid4): si Cloud Tasks reintenta esta
                # extracción completa tras un fallo, regenera los mismos IDs
                # en vez de duplicar registros para los mismos archivos.
                job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{batch_id}:{file_info.filename}"))
                xml_content = z.read(file_info.filename)
                chunk.append((job_id, xml_content))

                # Si juntamos 20, procesamos y vaciamos memoria
                if len(chunk) >= CHUNK_SIZE:
                    await flush_chunk(chunk)
                    chunk = []

            # Procesamos el residuo final (si sobraron menos de 20)
            if chunk:
                await flush_chunk(chunk)

    except Exception as e:
        print(f"Error crítico procesando ZIP en background: {e}")
        await redis_client.set(f"pdf:extracting_error:{batch_id}", str(e), ex=3600)
    finally:
        await redis_client.delete(f"pdf:extracting:{batch_id}")
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        # El ZIP original ya no se necesita para nada más una vez extraído
        # (con éxito o error) — no esperamos al lifecycle de 1 día del bucket.
        try:
            await asyncio.to_thread(blob.delete)
        except Exception as cleanup_err:
            print(f"Aviso: no se pudo borrar {gcs_path} de GCS: {cleanup_err}")

@router.post("/cfdi/pdf/start-zip-gcs")
async def start_pdf_zip_gcs_generation(payload: ProcessGcsZipPayload):
    """
    Endpoint que responde instantáneamente al frontend y delega el trabajo
    pesado a un Cloud Task real (no un BackgroundTask en memoria) — así
    sobrevive al reciclaje de instancias de Cloud Run y Cloud Tasks
    reintenta automáticamente si falla a medio camino.
    """
    template_id = "default"
    if payload.template:
        try:
            template_data = json.loads(payload.template)
            template_id = template_data.get("_id", "default")
        except Exception:
            pass

    batch_id = str(uuid.uuid4())

    # Avisamos a Redis que este lote está en fase de descarga/extracción (expira en 1 hr)
    await redis_client.set(f"pdf:extracting:{batch_id}", b"true", ex=3600)

    try:
        await asyncio.to_thread(
            enqueue_zip_extraction, gcs_path=payload.gcsPath, batch_id=batch_id, template_id=template_id
        )
    except Exception as e:
        await redis_client.delete(f"pdf:extracting:{batch_id}")
        raise HTTPException(status_code=500, detail=f"Error encolando la extracción en Cloud Tasks: {e}")

    # Respondemos al Front-End INMEDIATAMENTE para que no se quede trabado
    return {
        "batchId": batch_id,
        "message": "El archivo ZIP se está procesando en segundo plano."
    }
