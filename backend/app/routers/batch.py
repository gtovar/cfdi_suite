import redis
import redis.asyncio as aioredis
import asyncio
import uuid
import json
import os
import re
import hashlib
from pathlib import Path
# defusedxml, no la stdlib: el XML lo sube el usuario. xml.etree no resuelve
# entidades EXTERNAS (un file:// da ParseError), pero sí expande las INTERNAS,
# así que una bomba de expansión de ~400 bytes con 9 niveles anidados se
# convierte en ~1 GB en memoria y mata la instancia. defusedxml prohíbe las
# entidades de raíz (EntitiesForbidden) y deja el resto de la API igual --
# incluido ET.ParseError, que es literalmente el mismo objeto.
# El alias ET se conserva a propósito (es el nombre convencional y el que
# usa el resto del archivo); ruff sólo lo marca porque ya no es stdlib.
import defusedxml.ElementTree as ET  # noqa: N817
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from google.cloud import storage
from pusher import Pusher
import sentry_sdk

from ..services.analyze_cfdi import run_analyze_cfdi
from ..services.batch_reports import generate_diot
from ..services.task_dispatcher import enqueue_cfdi_analysis
from ..policy import ANALYZE_CFDI_XML_MAX_CHARS
from ..services.redis_safety import safe_redis_call_sync
from ..services.internal_auth import verify_cloud_tasks
from ..services.error_reporting import report
from ..rate_limits import rate_limit
from ..middleware import BATCH_FILE_MAX_BYTES, BATCH_TOTAL_MAX_BYTES

router = APIRouter(prefix="/api/cfdi/batch")

# Bucket compartido con app.routers.pdf -- reusamos el prefijo xml_temp/ (ya
# cubierto por la regla de lifecycle de 1 día, ver infra/gcs-lifecycle.json)
# para el contenido y los resultados de este pipeline también, en vez de dar
# de alta un prefijo nuevo que requeriría su propia regla.
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "cfdi-suite-uploads-706861124428")

# Único prefijo que /worker-task tiene permitido leer. El bucket es COMPARTIDO:
# también guarda uploads/ (los ZIP que sube el usuario), pdfs/ (los generados)
# y xml_temp/{job_id}.xml (el pipeline de PDF). El worker sólo necesita lo que
# escribe batch_analyze, f"xml_temp/analysis_{batch_id}/{fname}" (línea ~145),
# así que el guard se cierra sobre eso y nada más.
_ALLOWED_GCS_PREFIX = "xml_temp/analysis_"


def _analysis_bucket():
    return storage.Client().bucket(BUCKET_NAME)


def _batch_hash_key(batch_id: str) -> str:
    return f"batch:{batch_id}"


def _batch_results_key(batch_id: str) -> str:
    return f"batch:{batch_id}:results"


def _assert_batch_id(batch_id: str) -> str:
    try:
        return str(uuid.UUID(batch_id))
    except ValueError as exc:
        raise HTTPException(400, "Identificador de lote inválido") from exc

# Configuración dinámica de Redis mediante variables de entorno
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Pasamos los parámetros de control directamente al cliente síncrono de redis.
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=True,
    ssl_cert_reqs="required",
    max_connections=30,
    health_check_interval=25,
    decode_responses=True # True para recibir strings limpios en el estatus
)

# --- INICIALIZACIÓN SEGURA Y RESILIENTE DE PUSHER ---
PUSHER_APP_ID = os.getenv("PUSHER_APP_ID")
PUSHER_KEY = os.getenv("PUSHER_KEY")
PUSHER_SECRET = os.getenv("PUSHER_SECRET")
PUSHER_CLUSTER = os.getenv("PUSHER_CLUSTER", "us2")

pusher_client = None

# Solo encendemos Pusher si todas las credenciales requeridas están presentes
if PUSHER_APP_ID and PUSHER_KEY and PUSHER_SECRET:
    pusher_client = Pusher(
        app_id=PUSHER_APP_ID,
        key=PUSHER_KEY,
        secret=PUSHER_SECRET,
        cluster=PUSHER_CLUSTER,
        ssl=True
    )
else:
    print("[Pusher Warning] Faltan variables de entorno. Los WebSockets en tiempo real estarán desactivados temporamente.")

MAX_FILES = 500
REDIS_TTL = 86400  # 24 horas en segundos


class DurableAnalysisFile(BaseModel):
    filename: str
    size: int


class DurableAnalysisBatchCreatePayload(BaseModel):
    files: list[DurableAnalysisFile]


def _durable_analysis_manifest_blob(bucket, batch_id: str):
    """Manifiesto que existe antes de recibir los bytes de cada XML.

    A diferencia del endpoint multipart histórico, el manifiesto conserva el
    total esperado aunque el usuario recargue o una subida individual falle.
    """
    return bucket.blob(f"xml_temp/analysis_manifest_{batch_id}.json")


def _durable_analysis_xml_path(batch_id: str, job_id: str) -> str:
    # job_id, no filename: dos archivos con el mismo nombre nunca pueden
    # sobrescribirse dentro del lote si la política de UI cambia en el futuro.
    return f"xml_temp/analysis_{batch_id}/{job_id}.xml"


async def _load_durable_analysis_manifest(bucket, batch_id: str) -> dict | None:
    try:
        raw = await asyncio.to_thread(_durable_analysis_manifest_blob(bucket, batch_id).download_as_bytes)
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("jobs"), dict):
        return None
    return data


def _assert_job_id(job_id: str) -> str:
    try:
        return str(uuid.UUID(job_id))
    except ValueError as exc:
        raise HTTPException(400, "Identificador de archivo inválido") from exc

def _extract_header(xml_bytes: bytes) -> dict[str, str]:
    try:
        root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))
    except Exception:
        return {}
    result: dict[str, str] = {}
    for node in root.iter():
        tag = node.tag.split("}", 1)[-1]
        if tag == "Emisor":
            result["rfc_emisor"] = node.attrib.get("Rfc", "").strip()
            result["nombre_emisor"] = node.attrib.get("Nombre", "")
        elif tag == "Receptor":
            result["rfc_receptor"] = node.attrib.get("Rfc", "").strip()
    result["total"] = root.attrib.get("Total", "")
    fecha = root.attrib.get("Fecha", "")
    result["fecha"] = fecha[:10] if fecha else ""
    return result

def _safe_filename(fname: str) -> str:
    allowed = re.compile(r"[A-Za-z0-9._-]")
    base = Path(fname).name
    return "".join(c if allowed.match(c) else "_" for c in base) or "archivo.xml"


def _is_valid_xml_content(raw: bytes) -> bool:
    if len(raw) >= 4 and raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    return raw.lstrip().startswith((b"<?xml", b"<"))


_UPLOAD_READ_CHUNK_BYTES = 64 * 1024


async def _read_upload_limited(f: UploadFile, *, total_bytes: int) -> tuple[str, bytes, int]:
    """Lee un archivo sin confiar en Content-Length ni materializar el lote.

    ``total_bytes`` es el acumulado de los archivos previos; se retorna el
    nuevo acumulado para que todos los endpoints apliquen el mismo presupuesto.
    """
    filename = f.filename or "archivo.xml"
    chunks: list[bytes] = []
    file_bytes = 0
    while chunk := await f.read(_UPLOAD_READ_CHUNK_BYTES):
        file_bytes += len(chunk)
        if file_bytes > BATCH_FILE_MAX_BYTES:
            raise HTTPException(413, f"El archivo {filename} excede el límite de 20 MB")
        if total_bytes + file_bytes > BATCH_TOTAL_MAX_BYTES:
            raise HTTPException(413, "El lote excede el límite agregado de 100 MB")
        chunks.append(chunk)
    return filename, b"".join(chunks), total_bytes + file_bytes


@router.post("/loose-batches")
async def create_durable_analysis_batch(payload: DurableAnalysisBatchCreatePayload):
    """Reserva un lote de análisis sin transportar los XML en el POST inicial."""
    if not payload.files:
        raise HTTPException(400, "Selecciona al menos un XML")
    if len(payload.files) > MAX_FILES:
        raise HTTPException(400, f"Máximo {MAX_FILES} archivos por lote")

    seen: set[str] = set()
    for item in payload.files:
        if not item.filename.lower().endswith(".xml") or not item.filename or item.filename in seen:
            raise HTTPException(400, "La lista contiene nombres XML inválidos o duplicados")
        if item.size < 0 or item.size > BATCH_FILE_MAX_BYTES:
            raise HTTPException(413, f"{item.filename} excede el límite de 20 MB")
        seen.add(item.filename)

    batch_id = str(uuid.uuid4())
    jobs = {
        str(uuid.uuid4()): {"filename": item.filename, "size": item.size}
        for item in payload.files
    }
    manifest = {"version": 1, "total": len(jobs), "jobs": jobs}
    bucket = _analysis_bucket()
    try:
        await asyncio.to_thread(
            _durable_analysis_manifest_blob(bucket, batch_id).upload_from_string,
            json.dumps(manifest, sort_keys=True), content_type="application/json", if_generation_match=0,
        )
    except Exception as exc:
        report(exc, contexto="crear_lote_analisis_durable")
        raise HTTPException(503, "No se pudo preparar el lote. Intenta de nuevo.") from exc

    # Redis acelera el camino normal, pero el manifiesto de GCS es la fuente
    # de verdad incluso si esta escritura se pierde por cuota o disponibilidad.
    safe_redis_call_sync(lambda: (
        redis_client.pipeline()
        .hmset(_batch_hash_key(batch_id), {"total_files": len(jobs), "completed_count": 0, "status": "awaiting_upload"})
        .expire(_batch_hash_key(batch_id), REDIS_TTL)
        .execute()
    ))
    safe_redis_call_sync(lambda: redis_client.expire(_batch_results_key(batch_id), REDIS_TTL))
    return {
        "batchId": batch_id,
        "status": "awaiting_upload",
        "jobs": [{"jobId": job_id, **job} for job_id, job in jobs.items()],
    }


@router.post("/loose-batches/{batch_id}/files/{job_id}")
async def upload_durable_analysis_file(
    batch_id: str, job_id: str, file: UploadFile = File(...),
):
    """Guarda un XML individual de un lote durable, sin encolar todavía."""
    batch_id = _assert_batch_id(batch_id)
    job_id = _assert_job_id(job_id)
    bucket = _analysis_bucket()
    manifest = await _load_durable_analysis_manifest(bucket, batch_id)
    job = (manifest or {}).get("jobs", {}).get(job_id)
    if not job or file.filename != job.get("filename"):
        raise HTTPException(404, "El archivo no pertenece a este lote")

    filename, raw, _ = await _read_upload_limited(file, total_bytes=0)
    if len(raw.decode("utf-8", errors="replace")) > ANALYZE_CFDI_XML_MAX_CHARS:
        raise HTTPException(413, f"El archivo {filename} excede el límite de {ANALYZE_CFDI_XML_MAX_CHARS} caracteres")
    if not _is_valid_xml_content(raw):
        raise HTTPException(400, f"El archivo {filename} no parece ser un XML válido")
    if len(raw) != job.get("size"):
        raise HTTPException(409, "El tamaño del XML no coincide con el lote preparado")

    blob = bucket.blob(_durable_analysis_xml_path(batch_id, job_id))
    try:
        await asyncio.to_thread(blob.upload_from_string, raw, content_type="application/xml", if_generation_match=0)
        return {"batchId": batch_id, "jobId": job_id, "status": "uploaded"}
    except Exception as exc:
        # Un reintento después de una respuesta perdida debe conservar el
        # primer contenido, nunca sobrescribirlo. Comparamos bytes para que
        # el mismo jobId no pueda mutar de identidad.
        try:
            existing = await asyncio.to_thread(blob.download_as_bytes)
        except Exception:
            report(exc, contexto="subir_xml_analisis_individual")
            raise HTTPException(503, "No se pudo guardar el XML. Intenta de nuevo.") from exc
        if hashlib.sha256(existing).digest() != hashlib.sha256(raw).digest():
            raise HTTPException(409, "Ese job_id ya corresponde a otro XML")
        return {"batchId": batch_id, "jobId": job_id, "status": "already_uploaded"}


@router.post("/analyze")
async def batch_analyze(
    files: list[UploadFile] = File(...),
    _rate=rate_limit(5),
):
    if not files:
        raise HTTPException(400, "Se requiere al menos un archivo")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Máximo {MAX_FILES} archivos por lote")

    # Validamos el lote completo antes de crear estado o escribir en GCS. El
    # primer pase es secuencial y conserva como máximo un archivo en memoria;
    # después rebobinamos los UploadFile spooled para subir sólo un lote válido.
    total_bytes = 0
    for upload in files:
        fname, raw, total_bytes = await _read_upload_limited(upload, total_bytes=total_bytes)
        if len(raw.decode("utf-8", errors="replace")) > ANALYZE_CFDI_XML_MAX_CHARS:
            raise HTTPException(413, f"El archivo {fname} excede el límite de {ANALYZE_CFDI_XML_MAX_CHARS} caracteres")
        if not _is_valid_xml_content(raw):
            raise HTTPException(400, f"El archivo {fname} no parece ser un XML válido")
        await upload.seek(0)

    batch_id = str(uuid.uuid4())

    # Inicializamos el estado del lote en Redis -- best-effort: es solo
    # coordinación (contador de progreso), el contenido real de cada XML ya
    # no vive aquí (ver abajo), así que un fallo aquí no impide crear el
    # lote ni encolar el trabajo real.
    safe_redis_call_sync(lambda: (
        redis_client.pipeline()
        .hmset(_batch_hash_key(batch_id), {
            "total_files": len(files),
            "completed_count": 0,
            "status": "ready"
        })
        .expire(_batch_hash_key(batch_id), REDIS_TTL)
        .execute()
    ))
    safe_redis_call_sync(lambda: redis_client.expire(_batch_results_key(batch_id), REDIS_TTL))

    bucket = _analysis_bucket()

    # Guardamos primero todos los XML. El navegador inicia los workers sólo
    # después de confirmar la suscripción a Pusher, evitando que eventos
    # rápidos se publiquen antes de que exista un receptor.
    total_bytes = 0
    for upload in files:
        fname, raw, total_bytes = await _read_upload_limited(upload, total_bytes=total_bytes)
        fname = _safe_filename(fname)
        xml_str = raw.decode("utf-8", errors="replace")

        # El XML se sube a GCS (durable) en vez de guardarse en Redis con TTL
        # de 1h -- antes, si Upstash perdía esa llave (agotamiento de cuota o
        # eviction) antes de que Cloud Tasks la leyera, el contenido se
        # perdía para siempre sin ninguna copia de respaldo (ver auditoría de
        # resiliencia 2026-07-23). Mismo patrón que xml_temp/ en
        # app.routers.pdf.
        gcs_path = f"xml_temp/analysis_{batch_id}/{fname}"
        await asyncio.to_thread(
            bucket.blob(gcs_path).upload_from_string, xml_str, content_type="application/xml"
        )

    return {"batch_id": batch_id, "total_files": len(files), "status": "ready"}


@router.post("/{batch_id}/start")
async def start_batch_analysis(batch_id: str):
    """Encola un lote listo después de que el navegador confirmó Pusher.

    El marcador en GCS usa precondición de creación: dos llamadas de inicio
    (doble clic o reconexión) sólo pueden encolar los archivos una vez.
    """
    batch_id = _assert_batch_id(batch_id)
    bucket = _analysis_bucket()

    # Nuevo camino durable: el manifiesto sabe qué se esperaba subir, aun si
    # el navegador se recargó antes de terminar. No iniciar parcialmente evita
    # que una fila desaparecida se interprete como XML analizado.
    manifest = await _load_durable_analysis_manifest(bucket, batch_id)
    if manifest:
        jobs: dict[str, dict] = manifest["jobs"]
        uploaded_blobs = await asyncio.to_thread(
            lambda: list(bucket.list_blobs(prefix=f"xml_temp/analysis_{batch_id}/"))
        )
        uploaded_ids = {Path(blob.name).stem for blob in uploaded_blobs}
        missing = [job_id for job_id in jobs if job_id not in uploaded_ids]
        if missing:
            raise HTTPException(409, f"Faltan {len(missing)} XML por subir antes de iniciar el análisis")

        start_marker = bucket.blob(f"xml_temp/analysis_start_{batch_id}.json")
        already_started = False
        try:
            await asyncio.to_thread(
                start_marker.upload_from_string,
                json.dumps({"batch_id": batch_id, "version": 1}),
                content_type="application/json", if_generation_match=0,
            )
        except Exception as exc:
            if exc.__class__.__name__ in {"PreconditionFailed", "Conflict"}:
                already_started = True
            else:
                raise

        # Siempre recorremos todos los jobs, inclusive con marker existente:
        # task names deterministas hacen AlreadyExists exitoso y permiten
        # reanudar un /start que se cayó a mitad de su despacho.
        try:
            for job_id, job in jobs.items():
                enqueue_cfdi_analysis(
                    batch_id, job["filename"], _durable_analysis_xml_path(batch_id, job_id), job_id,
                )
        except Exception as exc:
            report(exc, contexto="encolar_lote_analisis_durable")
            raise HTTPException(503, "No se pudo confirmar toda la programación. Reintenta este lote.") from exc

        safe_redis_call_sync(lambda: redis_client.hset(_batch_hash_key(batch_id), "status", "processing"))
        return {
            "batchId": batch_id, "status": "processing", "totalFiles": len(jobs),
            "alreadyStarted": already_started,
        }

    # Compatibilidad con lotes históricos creados por POST /analyze.
    blobs = await asyncio.to_thread(
        lambda: list(bucket.list_blobs(prefix=f"xml_temp/analysis_{batch_id}/"))
    )
    if not blobs:
        raise HTTPException(404, "El lote de procesamiento no existe o ya caducó")

    start_marker = bucket.blob(f"xml_temp/analysis_start_{batch_id}.json")

    try:
        await asyncio.to_thread(
            start_marker.upload_from_string,
            json.dumps({"batch_id": batch_id}),
            content_type="application/json",
            if_generation_match=0,
        )
    except Exception as exc:
        # Un marcador ya creado significa que el lote ya fue iniciado. No
        # reencolamos: Cloud Tasks ejecutará las tareas originales.
        if exc.__class__.__name__ in {"PreconditionFailed", "Conflict"}:
            return {"batch_id": batch_id, "status": "processing", "already_started": True}
        raise

    for blob in blobs:
        filename = Path(blob.name).name
        enqueue_cfdi_analysis(batch_id, filename, blob.name)

    safe_redis_call_sync(lambda: redis_client.hset(_batch_hash_key(batch_id), "status", "processing"))
    return {"batch_id": batch_id, "status": "processing", "total_files": len(blobs), "already_started": False}

def _build_status_response(total: int, completed: int, results: list[dict]) -> dict:
    status = "done" if completed >= total else "processing"
    files_ok = sum(1 for r in results if r["status"] == "ok")
    files_con_errores = sum(1 for r in results if r["status"] == "con_errores")
    files_error = sum(1 for r in results if r["status"] == "error")
    return {
        "status": status,
        "results": results,
        "summary": {
            "total_files": total,
            "completed": completed,
            "files_ok": files_ok,
            "files_con_errores": files_con_errores,
            "files_error": files_error,
            "total_findings": sum(r["findings_count"] for r in results),
        },
    }


async def _load_results_from_gcs(bucket, batch_id: str) -> list[dict]:
    """Respaldo de resultados cuando la lista de Redis (batch:{id}:results)
    no responde -- cada resultado ya calculado se guarda de forma durable en
    GCS antes de tocar Redis (ver batch_worker_task), así que esto reconstruye
    el mismo contenido sin depender de Redis para nada."""
    prefix = f"xml_temp/analysis_results_{batch_id}/"
    blobs = await asyncio.to_thread(lambda: list(bucket.list_blobs(prefix=prefix)))
    if not blobs:
        return []

    async def _read(blob) -> dict:
        raw = await asyncio.to_thread(blob.download_as_bytes)
        return json.loads(raw)

    return list(await asyncio.gather(*[_read(b) for b in blobs]))


async def _get_durable_analysis_status(bucket, batch_id: str, manifest: dict) -> dict:
    """Snapshot que no depende de Redis para total, uploads ni resultados."""
    jobs: dict[str, dict] = manifest["jobs"]
    uploaded_blobs = await asyncio.to_thread(
        lambda: list(bucket.list_blobs(prefix=f"xml_temp/analysis_{batch_id}/"))
    )
    uploaded_ids = {Path(blob.name).stem for blob in uploaded_blobs}
    uploaded = sum(1 for job_id in jobs if job_id in uploaded_ids)
    results = await _load_results_from_gcs(bucket, batch_id)
    response = _build_status_response(total=len(jobs), completed=len(results), results=results)
    if uploaded < len(jobs):
        response["status"] = "awaiting_upload"
    elif response["status"] != "done":
        marker = bucket.blob(f"xml_temp/analysis_start_{batch_id}.json")
        if not await asyncio.to_thread(marker.exists):
            response["status"] = "ready"
    response["upload"] = {
        "total": len(jobs), "uploaded": uploaded, "awaitingUpload": len(jobs) - uploaded,
    }
    return response


@router.get("/status/{batch_id}")
async def get_batch_status(batch_id: str):
    """Endpoint de consulta (polling) para el frontend y rehidratación de estado."""
    bucket = _analysis_bucket()
    manifest = await _load_durable_analysis_manifest(bucket, batch_id)
    if manifest:
        return await _get_durable_analysis_status(bucket, batch_id, manifest)

    batch_meta = safe_redis_call_sync(lambda: redis_client.hgetall(_batch_hash_key(batch_id)))

    if not batch_meta:
        # Puede ser que el lote de verdad no exista, o que Redis no haya
        # respondido (o haya perdido el hash) -- antes de reportar 404,
        # confirmamos contra GCS: los XMLs originales sobreviven a un Redis
        # caído (ver batch_analyze), así que si existen, el lote es real.
        submitted = await asyncio.to_thread(
            lambda: list(bucket.list_blobs(prefix=f"xml_temp/analysis_{batch_id}/"))
        )
        if not submitted:
            raise HTTPException(404, "El lote de procesamiento no existe o ya caducó")

        results = await _load_results_from_gcs(bucket, batch_id)
        return _build_status_response(total=len(submitted), completed=len(results), results=results)

    raw_results = safe_redis_call_sync(lambda: redis_client.lrange(_batch_results_key(batch_id), 0, -1))
    results = [json.loads(r) for r in raw_results] if raw_results is not None else await _load_results_from_gcs(bucket, batch_id)

    completed = int(batch_meta.get("completed_count", 0))
    total = int(batch_meta.get("total_files", 0))
    return _build_status_response(total=total, completed=completed, results=results)

@router.post("/worker-task")
async def batch_worker_task(request: Request):
    """Webhook asíncrono e independiente invocado por Google Cloud Tasks."""
    if not verify_cloud_tasks(request):
        raise HTTPException(status_code=403, detail="Acceso denegado")

    payload = await request.json()
    batch_id = payload["batch_id"]
    filename = payload["filename"]
    job_id = payload.get("job_id")
    # payload.get("redis_key"): tareas ya encoladas en Cloud Tasks ANTES de
    # este deploy (migración de Redis a GCS) siguen trayendo el campo viejo.
    # Un valor así nunca es una ruta de GCS válida -- bucket.blob(...) sobre
    # esa cadena simplemente no existe, y cae al mismo try/except de abajo
    # (mismo comportamiento que el "expiró en caché" de antes), en vez de un
    # KeyError -> 500 -> reintento infinito de Cloud Tasks durante la ventana
    # del deploy.
    gcs_path = payload.get("gcs_path") or payload.get("redis_key")

    # Defensa en profundidad sobre el token OIDC de arriba: aunque el
    # llamador esté autenticado, la ruta viene del cuerpo del request y este
    # endpoint la usa para leer del bucket COMPARTIDO -- ahí también viven
    # uploads/ y los PDF generados. Sin este guard, una ruta arbitraria deja
    # leer cualquier objeto del bucket y devolverlo procesado.
    #
    # OJO: la AMPLIACIÓN de la spec #2 propone el prefijo "xml_temp_analysis/",
    # que NO EXISTE. La ruta real la arma batch_analyze en la línea 145:
    # f"xml_temp/analysis_{batch_id}/{fname}". Con el prefijo de la spec, este
    # guard habría rechazado TODAS las tareas legítimas y roto el análisis por
    # lotes en producción.
    if not gcs_path or not gcs_path.startswith(_ALLOWED_GCS_PREFIX) or ".." in gcs_path:
        return {"status": "error", "message": "Ruta de objeto inválida"}

    # 1. Traemos el XML real desde GCS (durable) -- antes vivía en Redis con
    #    TTL de 1h y sin ninguna copia de respaldo si Upstash lo perdía antes
    #    de que Cloud Tasks llegara a leerlo (ver auditoría de resiliencia
    #    2026-07-23).
    bucket = _analysis_bucket()
    # Los trabajos nuevos tienen identidad durable por archivo. Si Cloud
    # Tasks reintenta después de haber recibido 200, el resultado ya guardado
    # es autoridad y no se vuelve a analizar ni a incrementar Redis.
    result_path = (
        f"xml_temp/analysis_results_{batch_id}/{job_id}.json"
        if job_id else f"xml_temp/analysis_results_{batch_id}/{filename}.json"
    )
    if job_id and await asyncio.to_thread(bucket.blob(result_path).exists):
        return {"status": "already_processed"}
    try:
        xml_bytes = await asyncio.to_thread(bucket.blob(gcs_path).download_as_bytes)
    except Exception:
        return {"status": "error", "message": "El XML no se encontró en Storage (lote expirado o ruta inválida)"}
    xml_str = xml_bytes.decode("utf-8", errors="replace")

    try:
        # Analizamos el CFDI de manera aislada
        result = run_analyze_cfdi(xml_str)
        fatal = any(i.fatal for i in result.issues)
        findings = result.cfdi.get("findings", []) if result.cfdi else []

        rfc_emisor, nombre_emisor, rfc_receptor = "", "", ""
        if result.ingresoRows:
            rfc_emisor = result.ingresoRows[0].get("rfcEmisor", "").strip()
            nombre_emisor = result.ingresoRows[0].get("nombreEmisor", "")
            rfc_receptor = result.ingresoRows[0].get("rfcReceptor", "").strip()
        elif result.pagoRows:
            rfc_emisor = result.pagoRows[0].get("rfcEmisor", "").strip()
            rfc_receptor = result.pagoRows[0].get("rfcReceptor", "").strip()

        cfdi_dict = result.cfdi or {}
        total = str(cfdi_dict.get("total", "")) if cfdi_dict.get("total") is not None else ""
        fecha_raw = str(cfdi_dict.get("fecha", ""))
        fecha = fecha_raw[:10] if fecha_raw else ""
        status = "error" if fatal else ("con_errores" if findings else "ok")
        error_msg = None
        profile = result.profile
    except Exception as e:
        # 🚀 Envío explícito a Sentry del error exacto para debugging en background
        sentry_sdk.capture_exception(e)

        # Si ocurre un fallo en el procesamiento, capturamos el motivo de respaldo
        header = _extract_header(xml_str.encode("utf-8"))
        status = "error"
        profile = "unknown"
        rfc_emisor = header.get("rfc_emisor", "")
        rfc_receptor = header.get("rfc_receptor", "")
        nombre_emisor = header.get("nombre_emisor", "")
        total = header.get("total", "")
        fecha = header.get("fecha", "")
        findings = []
        report(e, contexto="analizar_cfdi_lote")
        # El detalle va a Sentry; al usuario le llega el nombre del archivo
        # (que ya viaja en `filename`) y que ese archivo falló, no la traza.
        error_msg = "No se pudo analizar el archivo"

    parsed_result = {
        "job_id": job_id,
        "filename": filename,
        "status": status,
        "profile": profile,
        "rfc_emisor": rfc_emisor,
        "rfc_receptor": rfc_receptor,
        "nombre_emisor": nombre_emisor,
        "total": total,
        "fecha": fecha,
        "findings_count": len(findings),
        "error": error_msg,
    }

    # Guardado durable en GCS PRIMERO -- el resultado del análisis (ya
    # calculado con éxito) nunca debe perderse solo porque el REPORTE a Redis
    # falle; mismo principio ya aplicado en pdf.py tras el incidente del 23
    # de julio.
    await asyncio.to_thread(
        bucket.blob(result_path).upload_from_string,
        json.dumps(parsed_result),
        content_type="application/json",
    )

    # Contadores/lista en Redis: best-effort desde que el resultado ya está a
    # salvo en GCS -- un fallo aquí solo retrasa lo que /status ve por Redis,
    # nunca pierde el resultado (get_batch_status cae a GCS si hace falta).
    safe_redis_call_sync(lambda: redis_client.rpush(_batch_results_key(batch_id), json.dumps(parsed_result)))
    safe_redis_call_sync(lambda: redis_client.hincrby(_batch_hash_key(batch_id), "completed_count", 1))

    # Emitimos el evento en tiempo real solo si Pusher se inicializó correctamente
    if pusher_client:
        try:
            pusher_client.trigger(f"private-batch_{batch_id}", "file_processed", parsed_result)
        except Exception as e:
            print(f"[Pusher Error] No se pudo enviar el evento en tiempo real: {e}")

    return {"status": "processed"}

@router.post("/diot")
async def batch_diot(
    files: list[UploadFile] = File(...),
    year: int = Form(...),
    month: int = Form(...),
    rfc_presentante: str = Form(default=""),
    razon_social: str = Form(default=""),
):
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, "Lote de archivos inválido")
    if not 1 <= month <= 12:
        raise HTTPException(400, "El mes debe estar entre 1 y 12")

    try:
        loop = asyncio.get_running_loop()
        diot_bytes = await loop.run_in_executor(
            None,
            lambda: generate_diot(
                _read_diot_uploads(files), year=year, month=month,
                rfc_presentante=rfc_presentante or None, razon_social=razon_social or None,
            )
        )
    except ValueError as e:
        report(e, contexto="diot_entrada")
        raise HTTPException(400, "Error al procesar el archivo del lote") from e
    except Exception as e:
        report(e, contexto="generar_diot")
        raise HTTPException(500, "Error al generar el DIOT") from e

    rfc_label = (rfc_presentante or "DIOT").upper().replace(" ", "_")
    filename = f"DIOT_{rfc_label}_{year}{str(month).zfill(2)}.txt"
    return StreamingResponse(iter([diot_bytes]), media_type="text/plain; charset=windows-1252", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _read_diot_uploads(files: list[UploadFile]):
    """Adaptador síncrono para el worker DIOT; los archivos ya están spooled."""
    total_bytes = 0
    for upload in files:
        filename = upload.filename or "archivo.xml"
        chunks: list[bytes] = []
        file_bytes = 0
        while chunk := upload.file.read(_UPLOAD_READ_CHUNK_BYTES):
            file_bytes += len(chunk)
            if file_bytes > BATCH_FILE_MAX_BYTES:
                raise ValueError(f"El archivo {filename} excede el límite de 20 MB")
            if total_bytes + file_bytes > BATCH_TOTAL_MAX_BYTES:
                raise ValueError("El lote excede el límite agregado de 100 MB")
            chunks.append(chunk)
        total_bytes += file_bytes
        yield b"".join(chunks)
