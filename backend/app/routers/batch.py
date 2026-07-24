import redis
import redis.asyncio as aioredis
import asyncio
import uuid
import json
import os
import xml.etree.ElementTree as ET
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import StreamingResponse
from google.cloud import storage
from pusher import Pusher
import sentry_sdk

from ..services.analyze_cfdi import run_analyze_cfdi
from ..services.batch_reports import generate_diot
from ..services.task_dispatcher import enqueue_cfdi_analysis
from ..services.redis_safety import safe_redis_call_sync

router = APIRouter(prefix="/api/cfdi/batch")

# Bucket compartido con app.routers.pdf -- reusamos el prefijo xml_temp/ (ya
# cubierto por la regla de lifecycle de 1 día, ver infra/gcs-lifecycle.json)
# para el contenido y los resultados de este pipeline también, en vez de dar
# de alta un prefijo nuevo que requeriría su propia regla.
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "cfdi-suite-uploads-706861124428")


def _analysis_bucket():
    return storage.Client().bucket(BUCKET_NAME)

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
    ssl_cert_reqs=None,
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

async def _read_upload(f: UploadFile) -> tuple[str, bytes]:
    return (f.filename or "archivo.xml", await f.read())

@router.post("/analyze")
async def batch_analyze(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "Se requiere al menos un archivo")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Máximo {MAX_FILES} archivos por lote")

    batch_id = str(uuid.uuid4())
    contents = list(await asyncio.gather(*[_read_upload(f) for f in files]))

    # Inicializamos el estado del lote en Redis -- best-effort: es solo
    # coordinación (contador de progreso), el contenido real de cada XML ya
    # no vive aquí (ver abajo), así que un fallo aquí no impide crear el
    # lote ni encolar el trabajo real.
    safe_redis_call_sync(lambda: redis_client.hmset(f"batch:{batch_id}", {
        "total_files": len(contents),
        "completed_count": 0,
        "status": "processing"
    }))
    # Aseguramos la auto-limpieza de la memoria de Redis
    safe_redis_call_sync(lambda: redis_client.expire(f"batch:{batch_id}", REDIS_TTL))
    safe_redis_call_sync(lambda: redis_client.expire(f"batch:{batch_id}:results", REDIS_TTL))

    bucket = _analysis_bucket()

    # Encolar cada archivo de manera inmediata en Cloud Tasks
    for fname, raw in contents:
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

        # Le pasamos a Cloud Tasks la RUTA de GCS, no el XML completo
        enqueue_cfdi_analysis(batch_id, fname, gcs_path)

    return {"batch_id": batch_id, "total_files": len(contents), "status": "processing"}

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


@router.get("/status/{batch_id}")
async def get_batch_status(batch_id: str):
    """Endpoint de consulta (polling) para el frontend y rehidratación de estado."""
    batch_meta = safe_redis_call_sync(lambda: redis_client.hgetall(f"batch:{batch_id}"))
    bucket = _analysis_bucket()

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

    raw_results = safe_redis_call_sync(lambda: redis_client.lrange(f"batch:{batch_id}:results", 0, -1))
    results = [json.loads(r) for r in raw_results] if raw_results is not None else await _load_results_from_gcs(bucket, batch_id)

    completed = int(batch_meta.get("completed_count", 0))
    total = int(batch_meta.get("total_files", 0))
    return _build_status_response(total=total, completed=completed, results=results)

@router.post("/worker-task")
async def batch_worker_task(request: Request):
    """Webhook asíncrono e independiente invocado por Google Cloud Tasks."""
    payload = await request.json()
    batch_id = payload["batch_id"]
    filename = payload["filename"]
    # payload.get("redis_key"): tareas ya encoladas en Cloud Tasks ANTES de
    # este deploy (migración de Redis a GCS) siguen trayendo el campo viejo.
    # Un valor así nunca es una ruta de GCS válida -- bucket.blob(...) sobre
    # esa cadena simplemente no existe, y cae al mismo try/except de abajo
    # (mismo comportamiento que el "expiró en caché" de antes), en vez de un
    # KeyError -> 500 -> reintento infinito de Cloud Tasks durante la ventana
    # del deploy.
    gcs_path = payload.get("gcs_path") or payload.get("redis_key")

    # 1. Traemos el XML real desde GCS (durable) -- antes vivía en Redis con
    #    TTL de 1h y sin ninguna copia de respaldo si Upstash lo perdía antes
    #    de que Cloud Tasks llegara a leerlo (ver auditoría de resiliencia
    #    2026-07-23).
    bucket = _analysis_bucket()
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
        error_msg = str(e)

    parsed_result = {
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
    result_path = f"xml_temp/analysis_results_{batch_id}/{filename}.json"
    await asyncio.to_thread(
        bucket.blob(result_path).upload_from_string,
        json.dumps(parsed_result),
        content_type="application/json",
    )

    # Contadores/lista en Redis: best-effort desde que el resultado ya está a
    # salvo en GCS -- un fallo aquí solo retrasa lo que /status ve por Redis,
    # nunca pierde el resultado (get_batch_status cae a GCS si hace falta).
    safe_redis_call_sync(lambda: redis_client.rpush(f"batch:{batch_id}:results", json.dumps(parsed_result)))
    safe_redis_call_sync(lambda: redis_client.hincrby(f"batch:{batch_id}", "completed_count", 1))

    # Emitimos el evento en tiempo real solo si Pusher se inicializó correctamente
    if pusher_client:
        try:
            pusher_client.trigger(f"batch_{batch_id}", "file_processed", parsed_result)
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

    xml_list = list(await asyncio.gather(*[f.read() for f in files]))
    try:
        loop = asyncio.get_running_loop()
        diot_bytes = await loop.run_in_executor(
            None,
            lambda: generate_diot(xml_list, year=year, month=month, rfc_presentante=rfc_presentante or None, razon_social=razon_social or None)
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error generando DIOT: {e}")

    rfc_label = (rfc_presentante or "DIOT").upper().replace(" ", "_")
    filename = f"DIOT_{rfc_label}_{year}{str(month).zfill(2)}.txt"
    return StreamingResponse(iter([diot_bytes]), media_type="text/plain; charset=windows-1252", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
