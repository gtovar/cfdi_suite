import asyncio
import uuid
import json
import os
import xml.etree.ElementTree as ET
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import StreamingResponse
import redis

from ..services.analyze_cfdi import run_analyze_cfdi
from ..services.batch_reports import generate_diot
from ..services.task_dispatcher import enqueue_cfdi_analysis

router = APIRouter(prefix="/api/cfdi/batch")

# Configuración dinámica de Redis mediante variables de entorno
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

redis_client = redis.Redis(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    password=REDIS_PASSWORD, 
    decode_responses=True
)

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
    
    # Inicializamos el estado del lote en Redis
    redis_client.hmset(f"batch:{batch_id}", {
        "total_files": len(contents),
        "completed_count": 0,
        "status": "processing"
    })
    # Aseguramos la auto-limpieza de la memoria de Redis
    redis_client.expire(f"batch:{batch_id}", REDIS_TTL)
    redis_client.expire(f"batch:{batch_id}:results", REDIS_TTL)

    # Encolar cada archivo de manera inmediata en Cloud Tasks
    for fname, raw in contents:
        xml_str = raw.decode("utf-8", errors="replace")
        enqueue_cfdi_analysis(batch_id, fname, xml_str)

    return {"batch_id": batch_id, "total_files": len(contents), "status": "processing"}

@router.get("/status/{batch_id}")
async def get_batch_status(batch_id: str):
    """Endpoint de consulta (polling) para el frontend y rehidratación de estado."""
    batch_meta = redis_client.hgetall(f"batch:{batch_id}")
    if not batch_meta:
        raise HTTPException(404, "El lote de procesamiento no existe o ya caducó")

    raw_results = redis_client.lrange(f"batch:{batch_id}:results", 0, -1)
    results = [json.loads(r) for r in raw_results]

    completed = int(batch_meta.get("completed_count", 0))
    total = int(batch_meta.get("total_files", 0))
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

@router.post("/worker-task")
async def batch_worker_task(request: Request):
    """Webhook asíncrono e independiente invocado por Google Cloud Tasks."""
    payload = await request.json()
    batch_id = payload["batch_id"]
    filename = payload["filename"]
    xml_str = payload["xml_str"]

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
        # Si ocurre un fallo en el procesamiento, capturamos el motivo exacto
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

    # Guardado atómico en la lista de resultados e incremento de contadores en Redis
    redis_client.rpush(f"batch:{batch_id}:results", json.dumps(parsed_result))
    redis_client.hincrby(f"batch:{batch_id}", "completed_count", 1)

    return {"status": "processed"}

# El endpoint de DIOT permanece igual utilizando los UploadFiles síncronos
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
