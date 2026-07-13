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
from google.cloud.storage import transfer_manager

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from opentelemetry import trace

import urllib.request
import traceback

tracer = trace.get_tracer(__name__)

import redis.asyncio as aioredis

from ..services.pdf_pipeline import generate, PDF_PROCESS_POOL
from ..services.realtime import publish_batch_progress
from ..services.task_dispatcher import enqueue_pdf_generation, enqueue_zip_extraction
from ..services.batch_progress import publish_batch_tick
from ..services.zip_manifest import is_valid_xml_entry, compute_job_id
from ..services.batch_job_trigger import should_use_batch_job, trigger_batch_shard_job

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

# TTL de las claves de metadata de un batch en Redis (batch_ids, extracting_total,
# ready_recent, done_count, error_count). Debe ser >= al lifecycle real de GCS
# sobre pdfs/uploads/xml_temp (1 día, ver infra/gcs-lifecycle.json) para que
# _batch_progress_snapshot pueda seguir resolviendo un batch terminado mientras
# sus PDFs todavía existen en Storage.
BATCH_METADATA_TTL_SECONDS = 86400

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


async def _publish_batch_tick(batch_id: str, *, definitive_error: bool = False):
    """Wrapper delgado sobre batch_progress.publish_batch_tick.

    La lógica en sí (INCR, umbral de "publica cada N", payload de Pusher) vive
    en app/services/batch_progress.py — compartida con el Cloud Run Job de
    shards (app/workers/batch_shard_worker.py, Capa 1 de
    docs/propuesta-arquitectura-batch.md). Este wrapper sigue existiendo tal
    cual (mismo nombre, misma firma) porque tests/test_pdf_batch_ttl.py lo
    llama directo y parchea `redis_client` a nivel de módulo — referenciarlo
    aquí (no importado a valor fijo) preserva ese patrón de test.
    """
    await publish_batch_tick(
        redis_client, publish_batch_progress, batch_id,
        definitive_error=definitive_error, ttl_seconds=BATCH_METADATA_TTL_SECONDS,
    )


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
            await redis_client.set(f"pdf:status:{payload.job_id}", b"error", ex=BATCH_METADATA_TTL_SECONDS)
            print(f"Abortando Job {payload.job_id}: XML ya no existe ni en Redis ni en GCS.")
            if payload.batch_id:
                try:
                    await _publish_batch_tick(payload.batch_id, definitive_error=True)
                except Exception as tick_err:
                    print(f"Aviso: tick de progreso no publicado para {payload.batch_id}: {tick_err}")
            return Response(status_code=204)

        with tracer.start_as_current_span("generacion_pdf_intensiva"):
            # Aislado en su propio proceso (PDF_PROCESS_POOL, spawn) — no
            # llamado directo aquí. Bajo concurrency>1, WeasyPrint/reportlab/
            # lxml de dos peticiones simultáneas compartiendo este proceso
            # corrompían heap nativo (signal 6, ver PROJECT_STATE.md). Con
            # run_in_executor tampoco se bloquea el event loop mientras el
            # worker renderiza — antes generate() corría síncrono aquí mismo.
            loop = asyncio.get_running_loop()
            pdf_bytes = await loop.run_in_executor(
                PDF_PROCESS_POOL, generate, xml_bytes, payload.template_id, payload.html_shell
            )
        
        # Guardado final del PDF
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"pdfs/{payload.job_id}.pdf")
        await asyncio.to_thread(blob.upload_from_string, pdf_bytes, content_type="application/pdf")

        await redis_client.set(f"pdf:status:{payload.job_id}", b"done", ex=BATCH_METADATA_TTL_SECONDS)
        # Tamaño en bytes, guardado aquí (ya lo tenemos en memoria) para que la
        # descarga del ZIP consolidado pueda estimar el progreso sin tener que
        # volver a golpear GCS por metadata de cada PDF del lote.
        await redis_client.set(f"pdf:size:{payload.job_id}", str(len(pdf_bytes)).encode(), ex=86400)
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
                await redis_client.rpush(f"pdf:ready_recent:{payload.batch_id}", payload.job_id)
                await redis_client.expire(f"pdf:ready_recent:{payload.batch_id}", BATCH_METADATA_TTL_SECONDS)
                await _publish_batch_tick(payload.batch_id)
            except Exception as tick_err:
                print(f"Aviso: tick de progreso no publicado para {payload.batch_id}: {tick_err}")
        return {"status": "success", "message": "PDF generado"}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error generando PDF {payload.job_id}: {e}")
        try:
            await redis_client.set(f"pdf:status:{payload.job_id}", b"error", ex=BATCH_METADATA_TTL_SECONDS)
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
                if is_valid_xml_entry(file_info):
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

    # Constantes oficiales de tu plan de Upstash para pintar la comparativa.
    # Confirmadas 2026-07-11 contra la Management API de Upstash
    # (GET https://api.upstash.com/v2/redis/databases), no estimadas:
    # db_disk_threshold=268435456B (256MB), db_max_request_size=10485760B (10MB),
    # db_request_limit=500000 (comandos/mes, Plan Free). El valor previo de
    # "10,000" confundía db_max_commands_per_second (límite de tasa) con un
    # presupuesto diario/mensual — no existe tal límite diario en este plan.
    UPSTASH_STORAGE_MAX_MB = 256          # Capacidad total del Tanque
    UPSTASH_REQUEST_MAX_MB = 10           # Capacidad máxima del Embudo por petición
    UPSTASH_MONTHLY_COMMANDS_LIMIT = "500,000 (Plan Free)"

    print("\n" + "="*80)
    print("🔍 [AUDITORÍA DE INFRAESTRUCTURA - TRANSMISIÓN DE DATOS]")
    print(f"📦 EL TANQUE (Almacenamiento): {mb_reales:.2f} MB ocupados de {UPSTASH_STORAGE_MAX_MB} MB disponibles en tu capacidad total.")
    print(f"⚠️ EL EMBUDO (Payload Size):  {mb_reales:.2f} MB enviados de {UPSTASH_REQUEST_MAX_MB} MB máximos permitidos en una sola petición.")
    print(f"🔀 COMANDOS EN PIPELINE:     Total de comandos de escritura en el Pipeline: {total_comandos_pipeline} de {UPSTASH_MONTHLY_COMMANDS_LIMIT}.")
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
    await redis_client.set(f"pdf:extracting_total:{batch_id}", len(just_ids), ex=BATCH_METADATA_TTL_SECONDS)
    await redis_client.sadd(f"pdf:batch_ids:{batch_id}", *just_ids)
    await redis_client.expire(f"pdf:batch_ids:{batch_id}", BATCH_METADATA_TTL_SECONDS)

    network_semaphore = asyncio.Semaphore(50)

    async def safe_enqueue_task(jid: str):
        async with network_semaphore:
            try:
                # Ejecutamos la función síncrona dentro del pool de hilos de forma segura
                await asyncio.to_thread(enqueue_pdf_generation, job_id=jid, xml_b64="", template_id=template_id, batch_id=batch_id)
            except Exception as ex:
                print(f"Error registrando archivo {jid} en la cola de Google: {ex}")
                await redis_client.set(f"pdf:status:{jid}", b"error", ex=BATCH_METADATA_TTL_SECONDS)

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

    # Fase de extracción: el ZIP todavía se está desempaquetando y subiendo a
    # GCS -- ningún XML ha empezado a convertirse todavía. Se reporta con un
    # status distinto ("extracting", no "processing") para no reusar el
    # mismo "percentage" con dos significados (extraído vs. convertido) y
    # arriesgar que la barra parezca retroceder al pasar de una fase a otra.
    # 2026-07-12: antes de esto, la pantalla se quedaba en 0% fijo toda la
    # extracción (6-25 min medidos) sin ningún aviso -- el dato (cuántos
    # XMLs ya están en pdf:batch_ids) ya existía, solo no se exponía aquí.
    is_extracting = await redis_client.get(f"pdf:extracting:{batch_id}")
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


@router.get("/cfdi/pdf/batch/{batch_id}/estimated-size")
async def batch_estimated_size(batch_id: str):
    """
    Suma los tamaños (bytes originales, no comprimidos) de los PDFs ya
    generados del lote — el frontend la usa para decidir si puede mostrar
    una barra de progreso real al descargar el ZIP (fetch + ReadableStream,
    que retiene el archivo completo en memoria) o si el lote es demasiado
    grande y conviene la descarga nativa del navegador sin progreso.
    El ZIP comprime, así que el tamaño final real será algo menor a esta suma.
    """
    registered_raw = await redis_client.smembers(f"pdf:batch_ids:{batch_id}")
    if not registered_raw:
        return {"estimatedBytes": 0, "knownCount": 0, "totalCount": 0}

    job_ids = [rid.decode("utf-8") for rid in registered_raw]
    keys = [f"pdf:size:{jid}" for jid in job_ids]
    sizes_raw = await redis_client.mget(keys)

    known_sizes = [int(s) for s in sizes_raw if s]
    return {
        "estimatedBytes": sum(known_sizes),
        "knownCount": len(known_sizes),
        "totalCount": len(job_ids),
    }


@router.get("/cfdi/pdf/batch/{batch_id}/download")
async def download_batch_zip(batch_id: str):
    registered_raw = await redis_client.smembers(f"pdf:batch_ids:{batch_id}")
    if not registered_raw:
        raise HTTPException(status_code=404, detail="El lote especificado no existe o ya expiró.")

    job_ids = [rid.decode("utf-8") for rid in registered_raw]
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    # ZIP en streaming real: nunca tenemos más de `prefetch` PDFs en RAM a la
    # vez (antes: asyncio.gather bajaba los ~2,000 PDFs completos a memoria y
    # LUEGO armaba un segundo buffer con el ZIP completo -> OOM con 2Gi en
    # lotes grandes). zipfile.ZipFile soporta escribir a un stream no-seekable
    # de forma nativa (usa data descriptors), así que basta con drenar el
    # buffer de salida cada vez que se cierra una entrada.
    class _GrowingStream(io.RawIOBase):
        def __init__(self):
            self._buf = bytearray()

        def writable(self):
            return True

        def write(self, b):
            self._buf += b
            return len(b)

        def drain(self) -> bytes:
            chunk = bytes(self._buf)
            self._buf.clear()
            return chunk

    async def stream_zip():
        stream = _GrowingStream()
        zf = zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED)

        prefetch = 8
        queue: asyncio.Queue = asyncio.Queue(maxsize=prefetch)
        fetch_semaphore = asyncio.Semaphore(prefetch)

        async def fetch_one(jid: str):
            async with fetch_semaphore:
                blob = bucket.blob(f"pdfs/{jid}.pdf")
                try:
                    pdf_bytes = await asyncio.to_thread(blob.download_as_bytes)
                except Exception:
                    pdf_bytes = None
                await queue.put((jid, pdf_bytes))

        async def fetch_all():
            await asyncio.gather(*[fetch_one(jid) for jid in job_ids])

        producer_task = asyncio.create_task(fetch_all())
        try:
            for _ in range(len(job_ids)):
                jid, pdf_bytes = await queue.get()
                if pdf_bytes is not None:
                    zf.writestr(f"cfdi_{jid}.pdf", pdf_bytes)
                    chunk = stream.drain()
                    if chunk:
                        yield chunk
        finally:
            await producer_task

        zf.close()
        chunk = stream.drain()
        if chunk:
            yield chunk

    return StreamingResponse(
        stream_zip(),
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
    
    if not await asyncio.to_thread(blob.exists):
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

        if not await asyncio.to_thread(blob.exists):
            raise HTTPException(status_code=404, detail="El archivo PDF no se encontró en Storage.")

        download_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="GET",
            response_disposition=f'attachment; filename="cfdi_{job_id}.pdf"',
            service_account_email=service_account_email,
            access_token=credentials.token,
        )
        return {"downloadUrl": download_url}
    except HTTPException:
        raise
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

    ran = await process_zip_in_background(payload.gcs_path, payload.batch_id, payload.template_id)
    return {"status": "success" if ran else "skipped_already_in_progress"}


# Techo generoso vs. el peor caso medido en producción hasta hoy (13-17 min,
# ver docs/propuesta-arquitectura-batch.md) -- da margen a que la extracción
# tarde más sin que el lock expire antes de que termine sola.
EXTRACTION_LOCK_TTL_SECONDS = 1800


async def process_zip_in_background(gcs_path: str, batch_id: str, template_id: str) -> bool:
    """
    Descarga el ZIP a disco (no a RAM), lo lee y manda los XMLs a GCS
    temporal y los estados mínimos a Redis. Invocada desde internal_extract_zip.

    Devuelve True si esta invocación corrió de verdad, False si se omitió por
    encontrar una extracción ya en curso para el mismo batch_id.
    """
    # Lock de idempotencia -- encontrado 2026-07-12 auditando logs reales de
    # Cloud Run: una extracción que tarda más que el dispatch deadline de
    # Cloud Tasks (~10 min) dispara un reintento MIENTRAS la primera sigue
    # corriendo, duplicando la descarga del ZIP completo y la subida de cada
    # XML en la misma instancia al mismo tiempo (confirmado con
    # `gcloud logging read`: dos requests con el mismo instanceId,
    # traslapados). El SET NX es atómico -- solo una invocación gana el lock;
    # cualquier reintento que llegue mientras el original sigue vivo se
    # aborta de inmediato en vez de repetir el trabajo completo.
    lock_key = f"pdf:extracting_lock:{batch_id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=EXTRACTION_LOCK_TTL_SECONDS)
    if not acquired:
        print(f"[process_zip_in_background] Extracción ya en curso para batch {batch_id} "
              f"(probable reintento de Cloud Tasks) -- se omite para no duplicar el trabajo.")
        return False

    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(gcs_path)

    # Descargamos a un archivo temporal en disco. NOTA (corregido 2026-07-12,
    # ver PROJECT_STATE.md): el filesystem local de Cloud Run, sin volumen
    # montado, es tmpfs respaldado por RAM -- esto sigue consumiendo el mismo
    # presupuesto de memoria del contenedor, no un disco aparte. Igual vale la
    # pena escribirlo a archivo en vez de tenerlo como bytes de Python: evita
    # duplicar copias en el heap del proceso. Correrlo en un hilo evita
    # bloquear el event loop mientras dura.
    download_start = time.perf_counter()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        temp_filename = tmp.name
    await asyncio.to_thread(blob.download_to_filename, temp_filename)
    print(f"[process_zip_in_background] {batch_id}: descarga del ZIP tomó "
          f"{time.perf_counter() - download_start:.1f}s")

    extraction_start = time.perf_counter()
    total_upload_seconds = 0.0
    chunk_upload_seconds: list[float] = []
    try:
        with zipfile.ZipFile(temp_filename, "r") as z:
            xml_entries = [fi for fi in z.infolist() if is_valid_xml_entry(fi)]
            # Total real conocido de inmediato: el frontend deja de ver 0% fijo
            # desde los primeros segundos, en vez de hasta que todo el ZIP termine.
            await redis_client.set(f"pdf:extracting_total:{batch_id}", len(xml_entries), ex=BATCH_METADATA_TTL_SECONDS)

            # "Artillería pesada" (Capa 1, docs/propuesta-arquitectura-batch.md):
            # apagado por defecto (BATCH_JOB_ENABLED=false) — should_use_batch_job
            # siempre da False sin configuración explícita, así que el resto de
            # este bloque se comporta exactamente igual que antes de este cambio.
            # Cuando esté activo para un batch grande, el manifiesto y los XMLs en
            # GCS se siguen construyendo igual (pasos a y b) pero el paso c) NO
            # encola Cloud Tasks por XML — se dispara UN solo Cloud Run Job después,
            # una vez que el manifiesto completo ya existe (ver más abajo).
            use_batch_job = should_use_batch_job(len(xml_entries))

            chunk = []
            CHUNK_SIZE = 20
            # Nº de hilos para transfer_manager -- valor usado en las pruebas
            # locales (Mac y Docker con --cpus=2 --memory=2g, imitando la
            # instancia real), ver docs/propuesta-arquitectura-batch.md.
            UPLOAD_MAX_WORKERS = 16

            # Interruptor SOLO para pruebas dirigidas -- apagado por defecto
            # (mismo patrón que BATCH_JOB_ENABLED). Con esto en false (default
            # de producción), el comportamiento es idéntico al camino
            # secuencial ya revertido (85b301b) tras la regresión medida el
            # 12 de julio (ver PROJECT_STATE.md). Cuando está en true (solo
            # en un canario aislado, sin tráfico real), usa transfer_manager
            # E instrumenta el tiempo de cada chunk por separado -- la
            # medición anterior solo tenía el total (618.8s), no dónde se
            # concentraba esa lentitud dentro de los 100 chunks.
            EXTRACTION_PARALLEL_UPLOAD = os.getenv("EXTRACTION_PARALLEL_UPLOAD", "false").lower() == "true"

            # Aviso de progreso de EXTRACCIÓN vía Pusher (no solo el polling de
            # 30s a /status) -- throttled cada 5 chunks (100 XMLs), mismo
            # criterio que PUBLISH_EVERY_N_JOBS para el tick de conversión,
            # para no saturar el plan de Pusher en batches grandes.
            flushed_chunks = 0

            async def flush_chunk(current_chunk):
                nonlocal flushed_chunks
                # a) Redis: estado "pending" + registro incremental del batch
                #    (mismo pipeline, así el TTL del set nunca queda huérfano
                #    si el proceso muere a mitad de camino)
                async with redis_client.pipeline(transaction=False) as pipe:
                    for jid, _ in current_chunk:
                        pipe.set(f"pdf:status:{jid}", b"pending", ex=1800)
                    pipe.sadd(f"pdf:batch_ids:{batch_id}", *[jid for jid, _ in current_chunk])
                    pipe.expire(f"pdf:batch_ids:{batch_id}", BATCH_METADATA_TTL_SECONDS)
                    await pipe.execute()

                # El aviso de progreso es cosmético -- un fallo aquí (Redis,
                # Pusher, lo que sea) NUNCA debe impedir que b) y c) corran de
                # verdad para este chunk, por eso todo esto va en su propio
                # try/except, aislado del trabajo real.
                flushed_chunks += 1
                try:
                    total_xmls = len(xml_entries)
                    extracted_so_far = await redis_client.scard(f"pdf:batch_ids:{batch_id}")
                    if flushed_chunks % 5 == 0 or extracted_so_far >= total_xmls:
                        await asyncio.to_thread(publish_batch_progress, batch_id, {
                            "status": "extracting",
                            "total": total_xmls,
                            "extracted": extracted_so_far,
                            "done": 0, "error": 0, "converting": 0,
                            "pending": total_xmls,
                            "percentage": int(extracted_so_far / total_xmls * 100) if total_xmls else 0,
                        })
                except Exception as pusher_err:
                    print(f"Aviso: tick de extracción no publicado para {batch_id}: {pusher_err}")

                # b) Storage: el archivo pesado. Secuencial por default --
                #    (medido 2026-07-12: transfer_manager con max_workers=16
                #    subió el tiempo de 8min a 10m18s en Cloud Run, mientras
                #    6 reproducciones locales distintas, incluido el patrón
                #    EXACTO de producción, no reprodujeron esa lentitud --
                #    ver PROJECT_STATE.md. Sin explicación confirmada
                #    todavía). EXTRACTION_PARALLEL_UPLOAD activa el camino
                #    paralelo instrumentado por chunk, solo para la prueba
                #    dirigida en canario -- ver nota arriba.
                nonlocal total_upload_seconds
                upload_start = time.perf_counter()

                failed_jids: set[str] = set()
                if EXTRACTION_PARALLEL_UPLOAD:
                    pairs = [
                        (io.BytesIO(xml_data), bucket.blob(f"xml_temp/{jid}.xml"))
                        for jid, xml_data in current_chunk
                    ]
                    upload_results = await asyncio.to_thread(
                        transfer_manager.upload_many,
                        pairs,
                        worker_type=transfer_manager.THREAD,
                        max_workers=UPLOAD_MAX_WORKERS,
                        upload_kwargs={"content_type": "application/xml"},
                        raise_exception=False,
                    )
                    for (jid, _), result in zip(current_chunk, upload_results):
                        if isinstance(result, Exception):
                            print(f"Error subiendo XML {jid} a GCS: {result}")
                            failed_jids.add(jid)
                            await redis_client.set(f"pdf:status:{jid}", b"error", ex=BATCH_METADATA_TTL_SECONDS)
                else:
                    for jid, xml_data in current_chunk:
                        try:
                            blob_xml = bucket.blob(f"xml_temp/{jid}.xml")
                            await asyncio.to_thread(blob_xml.upload_from_string, xml_data, content_type="application/xml")
                        except Exception as e:
                            print(f"Error subiendo XML {jid} a GCS: {e}")
                            failed_jids.add(jid)
                            await redis_client.set(f"pdf:status:{jid}", b"error", ex=BATCH_METADATA_TTL_SECONDS)

                chunk_elapsed = time.perf_counter() - upload_start
                total_upload_seconds += chunk_elapsed
                chunk_upload_seconds.append(chunk_elapsed)
                # Log por chunk -- barato (~100 líneas por batch de 2000) y es
                # justo el dato que faltó en la medición del 12 de julio: solo
                # había un total (618.8s), no la distribución. Con esto se
                # puede saber si la lentitud es pareja en los 100 chunks o se
                # concentra en unos pocos.
                print(f"[process_zip_in_background] {batch_id}: chunk #{len(chunk_upload_seconds)} "
                      f"({len(current_chunk)} XMLs) subida tomó {chunk_elapsed:.2f}s "
                      f"({'paralelo' if EXTRACTION_PARALLEL_UPLOAD else 'secuencial'})")

                # c) Cloud Tasks: encolamos (solo camino normal — el Job de
                #    shards procesa su manifiesto directo, sin pasar por Tasks)
                #    -- salvo los que ya fallaron al subir, no existe XML que
                #    generar para esos.
                if not use_batch_job:
                    for jid, _ in current_chunk:
                        if jid in failed_jids:
                            continue
                        try:
                            await asyncio.to_thread(enqueue_pdf_generation, job_id=jid, xml_b64="", template_id=template_id, batch_id=batch_id)
                        except Exception as ex:
                            print(f"Error registrando en Tasks {jid}: {ex}")
                            await redis_client.set(f"pdf:status:{jid}", b"error", ex=BATCH_METADATA_TTL_SECONDS)

            for file_info in xml_entries:
                # Determinístico (no uuid4): si Cloud Tasks reintenta esta
                # extracción completa tras un fallo, regenera los mismos IDs
                # en vez de duplicar registros para los mismos archivos.
                # compute_job_id vive en zip_manifest.py -- misma fórmula que
                # usa el manifiesto remoto y cada tarea del shard, para que
                # nunca diverjan (ver zip_manifest.py).
                job_id = compute_job_id(batch_id, file_info.filename)
                xml_content = z.read(file_info.filename)
                chunk.append((job_id, xml_content))

                # Si juntamos 20, procesamos y vaciamos memoria
                if len(chunk) >= CHUNK_SIZE:
                    await flush_chunk(chunk)
                    chunk = []

            # Procesamos el residuo final (si sobraron menos de 20)
            if chunk:
                await flush_chunk(chunk)

            # Manifiesto completo (pdf:batch_ids:{batch_id} en Redis, XMLs ya en
            # GCS) -- ahora sí se puede disparar el Job de shards, una sola vez.
            if use_batch_job and xml_entries:
                try:
                    op_name = await asyncio.to_thread(
                        trigger_batch_shard_job, batch_id, len(xml_entries), template_id
                    )
                    print(f"[process_zip_in_background] Job de shards disparado para batch {batch_id}: {op_name}")
                except Exception as job_err:
                    print(f"Error disparando Cloud Run Job para batch {batch_id}: {job_err}")
                    await redis_client.set(
                        f"pdf:extracting_error:{batch_id}",
                        f"No se pudo disparar el Job de shards: {job_err}",
                        ex=3600,
                    )

    except Exception as e:
        print(f"Error crítico procesando ZIP en background: {e}")
        await redis_client.set(f"pdf:extracting_error:{batch_id}", str(e), ex=3600)
    finally:
        print(f"[process_zip_in_background] {batch_id}: extracción+subida (sin contar descarga) "
              f"tomó {time.perf_counter() - extraction_start:.1f}s, de los cuales "
              f"{total_upload_seconds:.1f}s fueron subidas a GCS")
        if chunk_upload_seconds:
            sorted_chunks = sorted(chunk_upload_seconds)
            n = len(sorted_chunks)
            median = sorted_chunks[n // 2]
            p90 = sorted_chunks[int(n * 0.9)]
            print(f"[process_zip_in_background] {batch_id}: distribución por chunk (n={n}): "
                  f"min={sorted_chunks[0]:.2f}s mediana={median:.2f}s p90={p90:.2f}s "
                  f"max={sorted_chunks[-1]:.2f}s")
        await redis_client.delete(f"pdf:extracting:{batch_id}")
        await redis_client.delete(lock_key)
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        # El ZIP original ya no se necesita para nada más una vez extraído
        # (con éxito o error) — no esperamos al lifecycle de 1 día del bucket.
        try:
            await asyncio.to_thread(blob.delete)
        except Exception as cleanup_err:
            print(f"Aviso: no se pudo borrar {gcs_path} de GCS: {cleanup_err}")

    return True

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
