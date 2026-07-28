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
from remotezip import RemoteZip

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
from ..services.realtime import publish_batch_signal
from ..services.task_dispatcher import enqueue_pdf_generation, enqueue_zip_extraction
from ..services.zip_manifest import (
    ZipBudgetError,
    compute_job_id,
    inspect_zip_manifest,
    validate_gcs_zip_size,
    validate_zip_compressed_size,
)
from ..services.gcs_range_auth import get_gcs_authorized_session, gcs_object_url
from ..services.batch_job_trigger import should_use_batch_job, trigger_batch_shard_job
from ..services.redis_errors import is_redis_quota_error
from ..services.redis_safety import safe_redis_call
from ..services.internal_auth import verify_cloud_tasks
from ..services.error_reporting import report
from ..services.template_ids import validate_template_id
from ..services import batch_state_store
from ..middleware import PDF_SINGLE_XML_MAX_BYTES

router = APIRouter(prefix="/api", tags=["PDF"])

_UPLOAD_READ_CHUNK_BYTES = 64 * 1024


async def _read_pdf_xml_upload(file: UploadFile) -> bytes:
    """Mantiene soporte de XML de 50 MB sin una lectura ilimitada."""
    chunks: list[bytes] = []
    received = 0
    while chunk := await file.read(_UPLOAD_READ_CHUNK_BYTES):
        received += len(chunk)
        if received > PDF_SINGLE_XML_MAX_BYTES:
            raise HTTPException(413, "El XML excede el límite de 50 MB")
        chunks.append(chunk)
    return b"".join(chunks)


class _SafeUrl(str):
    """Signed URL con representacion opaca para logging.

    Se comporta como str normal para JSON/fetch, pero __str__/__repr__
    redactan el query string para que un print() o logger.info() accidental
    no exponga el token firmado en Cloud Logging o Sentry.
    """
    def __new__(cls, url: str):
        obj = super().__new__(cls, url)
        return obj

    def __str__(self) -> str:
        return self.split("?")[0] + "?[REDACTED]"

    def __repr__(self) -> str:
        return self.__str__()


# Techo duro por conexión SSE. Cada stream abierto ocupa un slot de
# concurrencia de la instancia de Cloud Run (concurrency=5, confirmado en
# deploy-backend.yml -- corregido 2026-07-23, el comentario original decía
# "concurrency=1" desactualizado desde el fix de Signal 6); el cliente
# (subscribeWithRetry) se reconecta solo al cortarse, así que esto no
# interrumpe al usuario — solo evita que un stream retenga el slot los 1800s
# del timeout del servicio.
SSE_MAX_STREAM_SECONDS = 600

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "cfdi-suite-uploads-706861124428")

# No es configurable ni procede de una petición: es el endpoint documentado de
# GCP para recuperar únicamente el email de la service account de esta instancia.
_METADATA_SERVICE_ACCOUNT_EMAIL_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "service-accounts/default/email"
)
_METADATA_HEADERS = {"Metadata-Flavor": "Google"}
_METADATA_TIMEOUT_SECONDS = 2

# TTL de las claves de metadata de un batch en Redis (batch_ids, extracting_total,
# pdf:status:*). Debe ser >= al lifecycle real de GCS sobre pdfs/uploads/xml_temp
# (1 día, ver infra/gcs-lifecycle.json) para que get_batch_snapshot pueda seguir
# resolviendo un batch terminado mientras sus PDFs todavía existen en Storage.
# Duplicada a propósito en batch_state_store.py (mismo valor) -- ver comentario ahí.
BATCH_METADATA_TTL_SECONDS = 86400

redis_client = aioredis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=True,
    ssl_cert_reqs="required",
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
    uploadFields: dict[str, str]

class ProcessGcsZipPayload(BaseModel):
    gcsPath: str
    template: Optional[str] = None

class DownloadUrlResponse(BaseModel):
    downloadUrl: str

class ExtractZipPayload(BaseModel):
    gcs_path: str
    batch_id: str
    template_id: str


def _is_owned_upload_zip_path(gcs_path: object) -> bool:
    """True sólo para los ZIP temporales emitidos por ``request-upload``.

    ``gcs_path`` cruza el borde público y después viaja dentro del payload de
    Cloud Tasks; por eso no basta con confiar en que la segunda llamada sea
    interna. El formato canónico de uuid4 evita prefijos, traversal y aliases
    de ruta que pudieran apuntar a otro objeto del bucket.
    """
    if not isinstance(gcs_path, str) or not gcs_path.startswith("uploads/") or not gcs_path.endswith(".zip"):
        return False

    object_id = gcs_path[len("uploads/"):-len(".zip")]
    try:
        return str(uuid.UUID(object_id)) == object_id
    except (ValueError, AttributeError, TypeError):
        return False


def _validate_owned_upload_zip_path(gcs_path: object) -> None:
    if not _is_owned_upload_zip_path(gcs_path):
        raise HTTPException(
            status_code=400,
            detail="La ruta del ZIP debe ser uploads/{uuid}.zip",
        )


def _validate_template_id_or_400(template_id: object) -> str:
    """Valida el ID antes de encolar o abrir cualquier archivo de plantilla."""
    try:
        return validate_template_id(template_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _template_id_from_form(template: str | None) -> str:
    """Extrae el ID opcional de form-data, conservando el fallback histórico.

    JSON malformado o sin ``_id`` seguía significando ``default``; un ``_id``
    explícito pero inseguro se rechaza antes de que alcance Cloud Tasks.
    """
    if not template:
        return "default"
    try:
        template_data = json.loads(template)
        template_id = template_data.get("_id", "default") if isinstance(template_data, dict) else "default"
    except (TypeError, ValueError, json.JSONDecodeError):
        return "default"
    return _validate_template_id_or_400(template_id)


@router.post("/internal/generate-pdf")
async def internal_generate_pdf(payload: GeneratePdfPayload, request: Request):
    if not verify_cloud_tasks(request):
        raise HTTPException(status_code=403, detail="Acceso denegado")

    _validate_template_id_or_400(payload.template_id)

    print(f"Iniciando generación de PDF para Job ID: {payload.job_id}")
    # Best-effort, nunca puede tumbar el trabajo real de abajo si Redis está
    # agotado (ver docs/mesa-decision-resiliencia-redis-2026-07-23.md).
    await batch_state_store.mark_job_converting(redis_client, payload.job_id)

    try:
        if payload.xml_b64:
            xml_bytes = base64.b64decode(payload.xml_b64)
        else:
            # 1️⃣ Buscamos en Redis primero (por si quedaron tareas viejas en la cola)
            # -- best-effort: si Redis falla aquí, no debe abortar la generación
            # cuando el 2️⃣ (GCS, la ruta real hoy) sí tiene el XML.
            compressed_xml = await safe_redis_call(lambda: redis_client.get(f"pdf:xml:{payload.job_id}"))
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
            print(f"Abortando Job {payload.job_id}: XML ya no existe ni en Redis ni en GCS.")
            await batch_state_store.mark_job_error(redis_client, payload.job_id, ttl_seconds=BATCH_METADATA_TTL_SECONDS)
            if payload.batch_id:
                # Aviso mínimo, SIEMPRE se intenta -- ver publish_batch_signal.
                await asyncio.to_thread(publish_batch_signal, payload.batch_id, "job_error")
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
        # <-- A partir de aquí el PDF ya está generado y subido a GCS. Nada de
        # lo que sigue (reporte de estado a Redis) puede convertir esto en un
        # 500 -- ver Paso 1 de docs/plan-implementacion-resiliencia-redis-2026-07-23.md.

    except HTTPException:
        raise
    except Exception as e:
        # Solo fallos reales de decodificar/generar/subir llegan aquí.
        print(f"Error generando PDF {payload.job_id}: {e}")
        await batch_state_store.mark_job_error(redis_client, payload.job_id, ttl_seconds=BATCH_METADATA_TTL_SECONDS)

        if is_redis_quota_error(e):
            raise HTTPException(status_code=429, detail="El motor de procesamiento está a máxima capacidad.")
        report(e, contexto="generar_pdf")
        raise HTTPException(status_code=500, detail="Error al generar el PDF") from e

    # Reporte best-effort, fuera del try de arriba -- nunca produce un 5xx.
    # Tamaño en bytes, guardado aquí (ya lo tenemos en memoria) para que la
    # descarga del ZIP consolidado pueda estimar el progreso sin tener que
    # volver a golpear GCS por metadata de cada PDF del lote.
    await batch_state_store.mark_job_done(
        redis_client, payload.job_id, len(pdf_bytes),
        ttl_seconds=BATCH_METADATA_TTL_SECONDS, size_ttl_seconds=86400,
    )
    await safe_redis_call(lambda: redis_client.delete(f"pdf:xml:{payload.job_id}"))

    # 3️⃣ Borramos el XML temporal de GCS para no dejar basura
    try:
        blob_xml = bucket.blob(f"xml_temp/{payload.job_id}.xml")
        if await asyncio.to_thread(blob_xml.exists):
            await asyncio.to_thread(blob_xml.delete)
    except Exception as e:
        print(f"Aviso: No se pudo limpiar el XML temporal {payload.job_id}: {e}")

    print(f"PDF {payload.job_id} guardado con éxito.")
    if payload.batch_id:
        # Aviso mínimo, SIEMPRE se intenta -- ver publish_batch_signal.
        await asyncio.to_thread(publish_batch_signal, payload.batch_id, "job_done")
    return {"status": "success", "message": "PDF generado"}

@router.post("/cfdi/pdf/start")
async def start_pdf_generation(
    file: UploadFile = File(...),
    template: Optional[str] = Form(None)
):
    job_id = str(uuid.uuid4())
    xml_content = await _read_pdf_xml_upload(file)
    
    template_id = _template_id_from_form(template)

    # ☁️ NUEVO: Subir XML temporal a Google Cloud Storage
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_xml = bucket.blob(f"xml_temp/{job_id}.xml")
    try:
        await asyncio.to_thread(
            blob_xml.upload_from_string, xml_content, content_type="application/xml"
        )
    except Exception as exc:
        report(exc, contexto="almacenar_xml_individual")
        raise HTTPException(
            status_code=503,
            detail="No se pudo preparar el XML para conversión. Intenta de nuevo.",
        ) from exc
    # <-- El XML ya está en GCS -- lo que sigue (status best-effort + encolar
    # la tarea real) nunca debe fallar por un problema de Redis. Encontrado en
    # vivo el 23 de julio: esta escritura, sin protección, tumbaba con 500 el
    # encolado de CADA XML individual mientras la cuota de Redis seguía
    # agotada -- el mismo defecto de Paso 1, en una función que el plan
    # original no había cubierto.

    # 🟢 En Redis SOLO guardamos el estatus inicial pendiente (pesa nada)
    await batch_state_store.mark_job_pending(redis_client, job_id)

    try:
        await asyncio.to_thread(enqueue_pdf_generation, job_id=job_id, xml_b64="", template_id=template_id)
    except Exception as exc:
        report(exc, contexto="encolar_pdf")
        try:
            await asyncio.to_thread(blob_xml.delete)
        except Exception as cleanup_exc:
            report(cleanup_exc, contexto="limpiar_xml_no_encolado")
        raise HTTPException(
            status_code=503,
            detail="No se pudo programar la conversión. Intenta de nuevo.",
        ) from exc
    
    return {"jobId": job_id}

@router.post("/cfdi/pdf/start-zip")
async def start_pdf_zip_generation(
    file: UploadFile = File(...),
    template: Optional[str] = Form(None)
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="El archivo cargado debe ser un formato .ZIP válido.")

    file.file.seek(0, os.SEEK_END)
    upload_size = file.file.tell()
    file.file.seek(0)
    try:
        validate_zip_compressed_size(upload_size)
    except ZipBudgetError as error:
        raise HTTPException(status_code=413, detail="El ZIP excede el presupuesto permitido.") from error

    header = file.file.read(4)
    file.file.seek(0)
    if header != b"PK\x03\x04":
        raise HTTPException(status_code=400, detail="El archivo no tiene firma ZIP válida")

    batch_id = str(uuid.uuid4())
    
    template_id = _template_id_from_form(template)

    job_ids = []
    manifest: dict[str, str] = {}

    try:
        with zipfile.ZipFile(file.file, "r") as z:
            validated = inspect_zip_manifest(z.infolist(), batch_id)
            for file_info in validated.xml_entries:
                job_id = str(uuid.uuid4())
                xml_content = z.read(file_info.filename)
                job_ids.append((job_id, xml_content))
                manifest[job_id] = file_info.filename
    except ZipBudgetError as error:
        raise HTTPException(status_code=413, detail="El ZIP excede el presupuesto permitido.") from error
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="El archivo comprimido está dañado o corrupto.")
    except Exception as e:
        report(e, contexto="leer_zip")
        raise HTTPException(status_code=500, detail="Error al leer el archivo ZIP") from e

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

    # Manifiesto (job_id -> filename) escrito a GCS ANTES de tocar Redis --
    # hallazgo real de producción 2026-07-24 (cuota de Upstash agotada en
    # vivo, no simulada): con la cuota agotada, el SADD/SET que registra la
    # membresía del batch más abajo fallaba en silencio, y esta ruta
    # síncrona (a diferencia de process_zip_in_background, la ruta grande
    # vía URL firmada) no tenía ningún respaldo en GCS -- el batch quedaba
    # sin forma de reconstruirse ("Lote no encontrado"/"jobIds": []) aunque
    # los PDFs ya existieran y fueran descargables uno por uno. Mismo
    # patrón que ya usa process_zip_in_background/_try_remote_manifest_path.
    try:
        await asyncio.to_thread(
            _batch_manifest_blob(batch_id).upload_from_string,
            json.dumps(manifest),
            content_type="application/json",
        )
    except Exception as manifest_err:
        print(f"Aviso: no se pudo escribir el manifiesto de {batch_id} en GCS: {manifest_err}")

    # El bloque que va justo abajo de los prints de auditoría en pdf.py
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)

        CHUNK_SIZE = 20
        for i in range(0, len(job_ids), CHUNK_SIZE):
            chunk = job_ids[i:i + CHUNK_SIZE]

            # a) En Redis SÓLO creamos el estatus "pending" (pesa unos bytes)
            # -- best-effort: un fallo de cuota aquí no debe tumbar la subida
            # real a GCS del chunk completo (mismo defecto que start_pdf_generation,
            # encontrado en vivo el 23 de julio con este mismo flujo de ZIP).
            async def _set_pending_chunk(chunk=chunk):
                async with redis_client.pipeline(transaction=False) as pipe:
                    for jid, _ in chunk:
                        pipe.set(f"pdf:status:{jid}", b"pending", ex=1800)
                    await pipe.execute()
            await safe_redis_call(_set_pending_chunk)

            # b) Subimos los contenidos XML reales a Cloud Storage temporal
            for jid, xml_content in chunk:
                blob_xml = bucket.blob(f"xml_temp/{jid}.xml")
                await asyncio.to_thread(blob_xml.upload_from_string, xml_content, content_type="application/xml")

    except Exception as infra_err:
        report(infra_err, contexto="almacenar_xmls_zip")
        raise HTTPException(
            status_code=500,
            detail="Error al almacenar los archivos extraídos del ZIP"
        )

    just_ids = [item[0] for item in job_ids]
    await safe_redis_call(lambda: redis_client.set(f"pdf:extracting_total:{batch_id}", len(just_ids), ex=BATCH_METADATA_TTL_SECONDS))
    await safe_redis_call(lambda: redis_client.sadd(f"pdf:batch_ids:{batch_id}", *just_ids))
    await safe_redis_call(lambda: redis_client.expire(f"pdf:batch_ids:{batch_id}", BATCH_METADATA_TTL_SECONDS))

    network_semaphore = asyncio.Semaphore(50)

    async def safe_enqueue_task(jid: str):
        async with network_semaphore:
            try:
                # Ejecutamos la función síncrona dentro del pool de hilos de forma segura
                await asyncio.to_thread(enqueue_pdf_generation, job_id=jid, xml_b64="", template_id=template_id, batch_id=batch_id)
            except Exception as ex:
                print(f"Error registrando archivo {jid} en la cola de Google: {ex}")
                await batch_state_store.mark_job_error(redis_client, jid, ttl_seconds=BATCH_METADATA_TTL_SECONDS)

    async_tasks = [safe_enqueue_task(jid) for jid in just_ids]
    await asyncio.gather(*async_tasks)
    
    return {
        "batchId": batch_id,
        "totalFiles": len(just_ids)
    }


def _batch_manifest_blob(batch_id: str):
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    return batch_state_store.batch_manifest_blob(bucket, batch_id)


async def _load_batch_manifest(batch_id: str) -> dict[str, str] | None:
    """Wrapper delgado sobre batch_state_store.load_manifest -- ver ese
    módulo para el comportamiento real (respaldo de membresía del batch en
    GCS cuando pdf:batch_ids no responde)."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    return await batch_state_store.load_manifest(bucket, batch_id)


async def _resolve_job_ids(batch_id: str) -> list[str]:
    """Wrapper delgado sobre batch_state_store.resolve_job_ids."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    return await batch_state_store.resolve_job_ids(redis_client, bucket, batch_id)


async def _reconcile_none_statuses_with_gcs(
    job_ids: list[str], status_by_job: dict[str, str | None]
) -> None:
    """Wrapper delgado sobre batch_state_store.reconcile_none_statuses_with_gcs
    (mutación in-place, ver ese módulo para el razonamiento completo).

    El chequeo de "¿hay algo que reconciliar?" se repite aquí (además de
    adentro del módulo) a propósito -- para que el camino sano (ningún status
    None) siga sin construir un storage.Client() en absoluto, igual que antes
    de mover esta función. Ver test_no_toca_gcs_si_no_hay_ningun_none."""
    if not any(status_by_job.get(jid) is None for jid in job_ids):
        return
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    await batch_state_store.reconcile_none_statuses_with_gcs(bucket, job_ids, status_by_job)


async def _batch_progress_snapshot(batch_id: str) -> dict:
    """Wrapper delgado sobre batch_state_store.get_batch_snapshot -- lo
    comparten el SSE legacy y el endpoint /status."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    return await batch_state_store.get_batch_snapshot(redis_client, bucket, batch_id)


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
        # storage.Client()/bucket construidos UNA vez fuera del loop -- igual
        # que pdf_progress más abajo. Este stream puede iterar hasta 600 veces
        # (SSE_MAX_STREAM_SECONDS); llamar al wrapper _batch_progress_snapshot
        # aquí adentro reconstruiría el cliente en cada vuelta.
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        deadline = time.monotonic() + SSE_MAX_STREAM_SECONDS
        while time.monotonic() < deadline:
            snapshot = await batch_state_store.get_batch_snapshot(redis_client, bucket, batch_id)
            yield f"data: {json.dumps(snapshot)}\n\n"
            if snapshot["status"] in ("done", "error"):
                break
            await asyncio.sleep(1)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/cfdi/pdf/batch/{batch_id}/ready-files")
async def list_ready_files(batch_id: str):
    """
    IDs de los archivos ya convertidos (status 'done') hasta ahora — el
    frontend la usa para ir llenando la tabla de descargas individuales
    conforme avanza el lote, sin esperar a que todo el batch termine.

    Hallazgo real de producción 2026-07-24: con Redis agotado, Upstash NO
    truena `mget` -- responde una lista de puros `None` sin excepción. Por
    eso cada job se reconcilia contra GCS individualmente cuando su status
    vino `None` (ver batch_state_store.reconcile_none_statuses_with_gcs) --
    nunca los que Redis ya reportó explícitamente pending/converting/error,
    para que el costo en el camino sano (Redis vivo) siga siendo cero.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    ready = await batch_state_store.get_ready_job_ids(redis_client, bucket, batch_id)
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
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    return await batch_state_store.get_estimated_size(redis_client, bucket, batch_id)


@router.get("/cfdi/pdf/batch/{batch_id}/download")
async def download_batch_zip(batch_id: str):
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    job_ids = await batch_state_store.resolve_job_ids(redis_client, bucket, batch_id)
    if not job_ids:
        raise HTTPException(status_code=404, detail="El lote especificado no existe o ya expiró.")

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
        headers={
            "Content-Disposition": f'attachment; filename="resultado_pdfs_{batch_id}.zip"',
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
        },
    )

@router.get("/cfdi/pdf/{job_id}/progress")
async def pdf_progress(job_id: str):
    async def event_generator():
        # Encontrado en vivo el 23 de julio reproduciendo el incidente: con
        # Redis agotado, el status "done" nunca se escribe (safe_redis_call
        # lo descarta) y este stream se queda reportando "converting" para
        # siempre, aunque el PDF ya esté listo y descargable en GCS (Paso 3).
        #
        # NO basta con condicionar el respaldo a redis_safety.is_degraded():
        # esa bandera vive en memoria de UNA instancia de Cloud Run. Con
        # varias instancias activas (confirmado en vivo: la misma consulta
        # devolvía "done" pegando directo a una revisión, pero "converting"
        # para siempre pasando por el rewrite de Vercel, que aterrizó en otra
        # instancia que nunca había visto fallar un Redis propio), la
        # instancia que atiende ESTE stream puede no estar "degradada" según
        # su propia bandera aunque Redis esté agotado para todo el servicio.
        # Por eso se consulta GCS cada vez que el status viene vacío, sin
        # condicionarlo a la bandera -- una llamada extra a GCS por segundo
        # mientras el job sigue en vuelo es barata frente a dejar al usuario
        # viendo "Convirtiendo..." para siempre con el PDF ya listo.
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        deadline = time.monotonic() + SSE_MAX_STREAM_SECONDS
        while time.monotonic() < deadline:
            status_bytes = await safe_redis_call(lambda: redis_client.get(f"pdf:status:{job_id}"))
            status = status_bytes.decode("utf-8") if status_bytes else None
            if status in ("done", "error"):
                yield f'data: {{"status": "{status}"}}\n\n'
                break
            if status is None:
                blob = bucket.blob(f"pdfs/{job_id}.pdf")
                if await asyncio.to_thread(blob.exists):
                    yield 'data: {"status": "done"}\n\n'
                    break
            yield 'data: {"status": "converting"}\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/cfdi/pdf/{job_id}/download")
async def download_pdf(job_id: str):
    # La existencia del blob en GCS es la señal principal de "¿está listo?" --
    # no el status en Redis. Si Redis está caído o agotado (ver
    # docs/mesa-decision-resiliencia-redis-2026-07-23.md), un PDF ya generado
    # y subido debe poder descargarse igual.
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

def _get_metadata_service_account_email() -> str | None:
    """Obtiene el email desde el endpoint fijo de metadata de GCP.

    No acepta URL, host ni headers del llamador; mantenerlo así evita que este
    fallback se convierta accidentalmente en una superficie SSRF.
    """
    try:
        request = urllib.request.Request(
            _METADATA_SERVICE_ACCOUNT_EMAIL_URL, headers=_METADATA_HEADERS,
        )
        # URL sin parámetros, constante del metadata server de GCP.
        with urllib.request.urlopen(request, timeout=_METADATA_TIMEOUT_SECONDS) as response:  # nosec B310
            return response.read().decode("utf-8").strip() or None
    except Exception as error:
        print(f"Advertencia: No se pudo obtener el email del metadata server: {error}")
        return None


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
        service_account_email = _get_metadata_service_account_email()

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

        unique_id = str(uuid.uuid4())
        gcs_path = f"uploads/{unique_id}.zip"
        policy = storage_client.generate_signed_post_policy_v4(
            BUCKET_NAME,
            gcs_path,
            expiration=datetime.timedelta(minutes=15),
            conditions=[
                {"bucket": BUCKET_NAME},
                {"key": gcs_path},
                {"Content-Type": "application/zip"},
                ["content-length-range", 0, 512 * 1024 * 1024],
            ],
            fields={"Content-Type": "application/zip"},
            credentials=credentials,
            service_account_email=service_account_email,
            access_token=credentials.token,
        )

        return {
            "uploadUrl": _SafeUrl(policy["url"]),
            "gcsPath": gcs_path,
            "uploadFields": policy["fields"],
        }
    except Exception as e:
        traceback.print_exc()
        report(e, contexto="signed_url_subida")
        raise HTTPException(status_code=500, detail="Error al generar el enlace de subida") from e


@router.get("/cfdi/pdf/{job_id}/download-url", response_model=DownloadUrlResponse)
async def get_pdf_download_url(job_id: str):
    """
    Signed URL de lectura para un PDF individual ya listo — el navegador
    descarga directo de GCS, sin pasar por Cloud Run ni por el rewrite de
    Vercel (evita el límite de 120s de proxies externos para lotes grandes).

    La existencia del blob en GCS es la señal principal de "¿está listo?" --
    no el status en Redis (ver Paso 3 de
    docs/plan-implementacion-resiliencia-redis-2026-07-23.md): con Redis
    caído o agotado, un PDF ya generado debe poder descargarse igual.
    """
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
        return {"downloadUrl": _SafeUrl(download_url)}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        report(e, contexto="signed_url_descarga")
        raise HTTPException(status_code=500, detail="Error al generar el enlace de descarga") from e


@router.post("/internal/extract-zip")
async def internal_extract_zip(payload: ExtractZipPayload, request: Request):
    """
    Disparado por Cloud Tasks (no directo por el usuario) — corre la
    extracción dentro de un request HTTP real en vez de un BackgroundTask,
    para que Cloud Run mantenga la instancia activa mientras dura, y para
    que Cloud Tasks reintente automáticamente si falla a medio camino.
    """
    if not verify_cloud_tasks(request):
        raise HTTPException(status_code=403, detail="Acceso denegado")

    _validate_owned_upload_zip_path(payload.gcs_path)
    _validate_template_id_or_400(payload.template_id)
    ran = await process_zip_in_background(payload.gcs_path, payload.batch_id, payload.template_id)
    return {"status": "success" if ran else "skipped_already_in_progress"}


# Techo generoso vs. el peor caso medido en producción hasta hoy (13-17 min,
# ver docs/propuesta-arquitectura-batch.md) -- da margen a que la extracción
# tarde más sin que el lock expire antes de que termine sola.
EXTRACTION_LOCK_TTL_SECONDS = 1800

# Interruptor SOLO para pruebas dirigidas -- apagado por defecto, mismo
# patrón que BATCH_JOB_ENABLED/EXTRACTION_PARALLEL_UPLOAD. Con esto en false
# (default de producción), process_zip_in_background se comporta exactamente
# igual que hoy (descarga el ZIP completo). Con esto en true Y el batch
# calificando para el Job de shards (should_use_batch_job), en vez de bajar
# el ZIP completo se lee solo su directorio central (remotezip) para armar
# el manifiesto y disparar el Job -- cada tarea del Job lee su propia
# porción directo del ZIP original por rango de bytes (ver
# batch_shard_worker.py), sin que ninguna instancia individual tenga que
# mover el contenido completo de los XMLs por su propia red. Ver
# docs/propuesta-arquitectura-batch.md para el hallazgo real (límite de red
# de 600 Mbps por instancia de Cloud Run) que motiva esto.
REMOTE_ZIP_SHARD_READ = os.getenv("REMOTE_ZIP_SHARD_READ", "false").lower() == "true"


async def _try_remote_manifest_path(bucket, gcs_path: str, batch_id: str, template_id: str) -> bool | None:
    """
    Camino nuevo (solo si REMOTE_ZIP_SHARD_READ=true): en vez de descargar
    el ZIP completo, lee solo su directorio central (remotezip -- una
    lectura por rango, sin tocar contenido de archivos) para construir el
    manifiesto y disparar el Job de shards directamente. Cada tarea del Job
    lee su propia porción del ZIP original por rango de bytes (ver
    batch_shard_worker.py), así que ninguna instancia individual -- ni
    siquiera esta -- llega a mover el contenido pesado de los XMLs.

    Devuelve:
      True  -- el batch calificó para el Job de shards y se disparó (con
               éxito o con un error ya registrado en pdf:extracting_error).
      None  -- el batch no calificó (muy chico, should_use_batch_job dio
               False incluso con el interruptor prendido) -- el llamador
               debe caer al camino de siempre (descarga completa).
    """
    try:
        session = get_gcs_authorized_session()
        url = gcs_object_url(BUCKET_NAME, gcs_path)
        rz = await asyncio.to_thread(RemoteZip, url, session=session)
        try:
            infolist = await asyncio.to_thread(rz.infolist)
        finally:
            rz.close()
    except Exception as e:
        print(f"[_try_remote_manifest_path] Error leyendo el directorio central remoto de {gcs_path}: {e}")
        report(e, contexto="extraccion_zip")
        # batch_state_store.get_batch_snapshot devuelve este valor tal cual
        # como {"status":"error","message":...} al frontend, así que no
        # puede llevar str(e).
        await safe_redis_call(lambda: redis_client.set(f"pdf:extracting_error:{batch_id}", "Error al extraer el ZIP", ex=3600))
        return True

    validated = inspect_zip_manifest(infolist, batch_id)
    manifest = validated.manifest  # job_id -> filename
    total_xmls = len(manifest)

    if not should_use_batch_job(total_xmls):
        # Batch muy chico -- ni con el interruptor prendido tiene sentido
        # esta ruta (ver Ronda 0.5, docs/propuesta-arquitectura-batch.md,
        # sobre por qué el umbral no es de tamaño sino de forma de trabajo).
        # Cae al camino de siempre, sin haber tocado Redis ni disparado nada.
        return None

    # Manifiesto también en GCS -- mismo respaldo que process_zip_in_background
    # para que _batch_progress_snapshot y afines no dependan solo del sadd de
    # abajo si Redis falla a media construcción.
    try:
        await asyncio.to_thread(
            _batch_manifest_blob(batch_id).upload_from_string,
            json.dumps(manifest),
            content_type="application/json",
        )
    except Exception as manifest_err:
        print(f"Aviso: no se pudo escribir el manifiesto remoto de {batch_id} en GCS: {manifest_err}")

    await safe_redis_call(lambda: redis_client.set(f"pdf:extracting_total:{batch_id}", total_xmls, ex=BATCH_METADATA_TTL_SECONDS))

    job_ids = list(manifest.keys())
    if job_ids:
        async def _write_manifest_redis():
            async with redis_client.pipeline(transaction=False) as pipe:
                for jid in job_ids:
                    pipe.set(f"pdf:status:{jid}", b"pending", ex=1800)
                pipe.sadd(f"pdf:batch_ids:{batch_id}", *job_ids)
                pipe.expire(f"pdf:batch_ids:{batch_id}", BATCH_METADATA_TTL_SECONDS)
                await pipe.execute()
        await safe_redis_call(_write_manifest_redis)

        # Un solo aviso (100% extraído) -- a diferencia del camino de
        # siempre, aquí no hay una fase de extracción larga que justifique
        # ticks intermedios: construir el manifiesto solo lee el directorio
        # central, no el contenido de los XMLs, así que esto termina en
        # segundos sin importar el tamaño del batch. Aviso mínimo (hint-only,
        # ver publish_batch_signal): el frontend relee /status, que ya
        # calcula el % de extracción real desde pdf:batch_ids.
        await asyncio.to_thread(publish_batch_signal, batch_id, "job_done")

        try:
            op_name = await asyncio.to_thread(
                trigger_batch_shard_job, batch_id, total_xmls, template_id, gcs_path
            )
            print(f"[_try_remote_manifest_path] Job de shards disparado para batch {batch_id}: {op_name}")
        except Exception as job_err:
            print(f"Error disparando Cloud Run Job para batch {batch_id}: {job_err}")
            report(job_err, contexto="disparar_job_shards")
            await safe_redis_call(lambda: redis_client.set(
                f"pdf:extracting_error:{batch_id}",
                "No se pudo iniciar el procesamiento del lote",
                ex=3600,
            ))

    # NOTA (decisión deliberada, ver docs/propuesta-arquitectura-batch.md):
    # el ZIP original NO se borra aquí. A diferencia del camino de siempre
    # (una sola instancia, "terminado" bien definido), aquí N tareas del Job
    # leen el mismo ZIP de forma concurrente e independiente -- no hay un
    # momento único y seguro para borrarlo. Se deja que la regla de
    # lifecycle de GCS ya existente (1 día sobre uploads/,
    # infra/gcs-lifecycle.json) lo limpie.
    return True


async def process_zip_in_background(gcs_path: str, batch_id: str, template_id: str) -> bool:
    """
    Descarga el ZIP a disco (no a RAM), lo lee y manda los XMLs a GCS
    temporal y los estados mínimos a Redis. Invocada desde internal_extract_zip.

    Devuelve True si esta invocación corrió de verdad, False si se omitió por
    encontrar una extracción ya en curso para el mismo batch_id.
    """
    # Defensa en profundidad: este valor también puede llegar desde llamadas
    # internas o invocaciones directas de workers. No se debe tocar GCS, y
    # mucho menos limpiar un blob, si no es un ZIP temporal propio.
    _validate_owned_upload_zip_path(gcs_path)
    _validate_template_id_or_400(template_id)

    # Lock de idempotencia -- encontrado 2026-07-12 auditando logs reales de
    # Cloud Run: una extracción que tarda más que el dispatch deadline de
    # Cloud Tasks (~10 min) dispara un reintento MIENTRAS la primera sigue
    # corriendo, duplicando la descarga del ZIP completo y la subida de cada
    # XML en la misma instancia al mismo tiempo (confirmado con
    # `gcloud logging read`: dos requests con el mismo instanceId,
    # traslapados). El SET NX es atómico -- solo una invocación gana el lock;
    # cualquier reintento que llegue mientras el original sigue vivo se
    # aborta de inmediato en vez de repetir el trabajo completo.
    #
    # 2026-07-24: verificado en vivo contra producción con la cuota de Redis
    # realmente agotada -- esta línea, sin proteger, tronaba con 500 en
    # /api/internal/extract-zip, y Cloud Tasks reintentaba la misma llamada
    # indefinidamente sin llegar NUNCA al resto de la función (el manifiesto
    # en GCS, los endpoints degradados, nada de eso se alcanzaba). Con Redis
    # caído, subir un ZIP no funcionaba en absoluto -- a diferencia de los
    # XMLs sueltos y del análisis masivo, que sí sobrevivían la misma caída
    # real. Decisión explícita del usuario: best-effort en vez de fail-closed
    # -- si Redis no responde, se continúa la extracción de todas formas,
    # aceptando el riesgo (raro) de procesar el mismo ZIP dos veces en
    # paralelo si coincide un reintento de Cloud Tasks mientras Redis sigue
    # caído. El caso "Redis SÍ respondió y el lock ya existe" (duplicado
    # genuino con Redis sano) se sigue absteniendo igual que antes.
    lock_key = f"pdf:extracting_lock:{batch_id}"
    acquired = await safe_redis_call(lambda: redis_client.set(lock_key, "1", nx=True, ex=EXTRACTION_LOCK_TTL_SECONDS))
    if acquired is False:
        print(f"[process_zip_in_background] Extracción ya en curso para batch {batch_id} "
              f"(probable reintento de Cloud Tasks) -- se omite para no duplicar el trabajo.")
        return False
    if acquired is None:
        print(f"[process_zip_in_background] {batch_id}: Redis no respondió al intentar el lock "
              f"de idempotencia -- se continúa de todas formas (best-effort).")

    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(gcs_path)
    await asyncio.to_thread(validate_gcs_zip_size, blob)

    if REMOTE_ZIP_SHARD_READ:
        ran = await _try_remote_manifest_path(bucket, gcs_path, batch_id, template_id)
        if ran is not None:
            await safe_redis_call(lambda: redis_client.delete(f"pdf:extracting:{batch_id}"))
            await safe_redis_call(lambda: redis_client.delete(lock_key))
            return ran
        # ran is None: el batch no calificó para el Job de shards (batch
        # chico) incluso con el interruptor prendido -- cae al camino de
        # siempre debajo, sin cambios.

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
            validated = inspect_zip_manifest(z.infolist(), batch_id)
            xml_entries = validated.xml_entries

            # Manifiesto completo (job_id -> filename) escrito a GCS ANTES de
            # iterar el ZIP -- misma función (build_manifest) que ya usa el
            # camino de sharding grande para no depender de Redis para saber
            # qué archivos pertenecen al batch. Con esto, el sadd incremental
            # de más abajo (dentro de flush_chunk) puede ser puramente
            # best-effort: si Redis falla a media extracción, los endpoints
            # de lectura (_batch_progress_snapshot, list_ready_files, etc.)
            # tienen este manifiesto como respaldo de membresía en vez de
            # quedar con archivos "huérfanos" que existen en GCS pero de los
            # que nadie sabe que pertenecen al batch.
            manifest = validated.manifest
            try:
                await asyncio.to_thread(
                    _batch_manifest_blob(batch_id).upload_from_string,
                    json.dumps(manifest),
                    content_type="application/json",
                )
            except Exception as manifest_err:
                print(f"Aviso: no se pudo escribir el manifiesto de {batch_id} en GCS: {manifest_err}")

            # Total real conocido de inmediato: el frontend deja de ver 0% fijo
            # desde los primeros segundos, en vez de hasta que todo el ZIP termine.
            await safe_redis_call(lambda: redis_client.set(f"pdf:extracting_total:{batch_id}", len(xml_entries), ex=BATCH_METADATA_TTL_SECONDS))

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
                #    si el proceso muere a mitad de camino). Best-effort desde
                #    que existe el manifiesto en GCS (arriba): un fallo aquí ya
                #    no deja archivos huérfanos, solo hace que el progreso
                #    incremental por Redis se retrase hasta que Redis se
                #    recupere -- b) y c) (el trabajo real) nunca dependen de
                #    que esto tenga éxito.
                async def _write_chunk_pending():
                    async with redis_client.pipeline(transaction=False) as pipe:
                        for jid, _ in current_chunk:
                            pipe.set(f"pdf:status:{jid}", b"pending", ex=1800)
                        pipe.sadd(f"pdf:batch_ids:{batch_id}", *[jid for jid, _ in current_chunk])
                        pipe.expire(f"pdf:batch_ids:{batch_id}", BATCH_METADATA_TTL_SECONDS)
                        await pipe.execute()

                await safe_redis_call(_write_chunk_pending)

                # El aviso es cosmético -- un fallo aquí (Redis, Pusher, lo
                # que sea) NUNCA debe impedir que b) y c) corran de verdad
                # para este chunk, por eso va en su propio try/except,
                # aislado del trabajo real. Aviso mínimo (hint-only, ver
                # publish_batch_signal): el frontend relee /status, que ya
                # calcula el % de extracción real desde pdf:batch_ids.
                flushed_chunks += 1
                try:
                    total_xmls = len(xml_entries)
                    extracted_so_far = await redis_client.scard(f"pdf:batch_ids:{batch_id}")
                    if flushed_chunks % 5 == 0 or extracted_so_far >= total_xmls:
                        await asyncio.to_thread(publish_batch_signal, batch_id, "job_done")
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
                            await batch_state_store.mark_job_error(redis_client, jid, ttl_seconds=BATCH_METADATA_TTL_SECONDS)
                else:
                    for jid, xml_data in current_chunk:
                        try:
                            blob_xml = bucket.blob(f"xml_temp/{jid}.xml")
                            await asyncio.to_thread(blob_xml.upload_from_string, xml_data, content_type="application/xml")
                        except Exception as e:
                            print(f"Error subiendo XML {jid} a GCS: {e}")
                            failed_jids.add(jid)
                            await batch_state_store.mark_job_error(redis_client, jid, ttl_seconds=BATCH_METADATA_TTL_SECONDS)

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
                            await batch_state_store.mark_job_error(redis_client, jid, ttl_seconds=BATCH_METADATA_TTL_SECONDS)

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
                    report(job_err, contexto="disparar_job_shards")
                    await safe_redis_call(lambda: redis_client.set(
                        f"pdf:extracting_error:{batch_id}",
                        "No se pudo iniciar el procesamiento del lote",
                        ex=3600,
                    ))

    except Exception as e:
        print(f"Error crítico procesando ZIP en background: {e}")
        report(e, contexto="extraccion_zip")
        # batch_state_store.get_batch_snapshot devuelve este valor tal cual
        # como {"status":"error","message":...} al frontend, así que no
        # puede llevar str(e).
        await safe_redis_call(lambda: redis_client.set(f"pdf:extracting_error:{batch_id}", "Error al extraer el ZIP", ex=3600))
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
        await safe_redis_call(lambda: redis_client.delete(f"pdf:extracting:{batch_id}"))
        await safe_redis_call(lambda: redis_client.delete(lock_key))
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        # El ZIP original ya no se necesita para nada más una vez extraído
        # (con éxito o error) — no esperamos al lifecycle de 1 día del bucket.
        # Revalidar junto al efecto destructivo: sólo los objetos temporales
        # emitidos por request-upload son elegibles para borrado temprano.
        if _is_owned_upload_zip_path(gcs_path):
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
    _validate_owned_upload_zip_path(payload.gcsPath)
    template_id = _template_id_from_form(payload.template)

    try:
        storage_client = storage.Client()
        blob = storage_client.bucket(BUCKET_NAME).blob(payload.gcsPath)
        await asyncio.to_thread(validate_gcs_zip_size, blob)
    except ZipBudgetError as error:
        raise HTTPException(status_code=413, detail="El ZIP excede el presupuesto permitido.") from error

    batch_id = str(uuid.uuid4())

    # Avisamos a Redis que este lote está en fase de descarga/extracción (expira en 1 hr)
    await safe_redis_call(lambda: redis_client.set(f"pdf:extracting:{batch_id}", b"true", ex=3600))

    try:
        await asyncio.to_thread(
            enqueue_zip_extraction, gcs_path=payload.gcsPath, batch_id=batch_id, template_id=template_id
        )
    except Exception as e:
        await safe_redis_call(lambda: redis_client.delete(f"pdf:extracting:{batch_id}"))
        report(e, contexto="encolar_extraccion")
        raise HTTPException(status_code=500, detail="Error al encolar la extracción del ZIP") from e

    # Respondemos al Front-End INMEDIATAMENTE para que no se quede trabado
    return {
        "batchId": batch_id,
        "message": "El archivo ZIP se está procesando en segundo plano."
    }
