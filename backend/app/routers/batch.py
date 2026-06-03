import asyncio
import xml.etree.ElementTree as ET
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..services.analyze_cfdi import run_analyze_cfdi
from ..services.batch_reports import generate_diot

router = APIRouter(prefix="/api/cfdi/batch")

_SEM = asyncio.Semaphore(10)
MAX_FILES = 500


def _extract_header(xml_bytes: bytes) -> dict[str, str]:
    """Lightweight XML header parse — used only in the error path of _analyze_one."""
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


async def _analyze_one(filename: str, xml_bytes: bytes) -> dict[str, Any]:
    xml_str = xml_bytes.decode("utf-8", errors="replace")

    async with _SEM:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, run_analyze_cfdi, xml_str)
        except Exception as e:
            # Only parse XML header on the error path (avoids double-parse on success)
            header = _extract_header(xml_bytes)
            return {
                "filename": filename,
                "status": "error",
                "profile": "unknown",
                "rfc_emisor": header.get("rfc_emisor", ""),
                "rfc_receptor": header.get("rfc_receptor", ""),
                "nombre_emisor": header.get("nombre_emisor", ""),
                "total": header.get("total", ""),
                "fecha": header.get("fecha", ""),
                "findings_count": 0,
                "error": str(e),
            }

    fatal = any(i.fatal for i in result.issues)
    findings = result.cfdi.get("findings", []) if result.cfdi else []

    # Source RFC/nombre from satcfdi post-parse rows (no second XML parse needed)
    rfc_emisor = ""
    nombre_emisor = ""
    rfc_receptor = ""
    if result.ingresoRows:
        rfc_emisor = result.ingresoRows[0].get("rfcEmisor", "").strip()
        nombre_emisor = result.ingresoRows[0].get("nombreEmisor", "")
        rfc_receptor = result.ingresoRows[0].get("rfcReceptor", "").strip()
    elif result.pagoRows:
        rfc_emisor = result.pagoRows[0].get("rfcEmisor", "").strip()
        rfc_receptor = result.pagoRows[0].get("rfcReceptor", "").strip()

    # Fallback for edge cases where rows are empty but cfdi has the data
    if not rfc_emisor and result.cfdi:
        header = _extract_header(xml_bytes)
        rfc_emisor = header.get("rfc_emisor", "")
        rfc_receptor = header.get("rfc_receptor", "")
        nombre_emisor = header.get("nombre_emisor", "")

    cfdi_dict = result.cfdi or {}
    total = str(cfdi_dict.get("total", "")) if cfdi_dict.get("total") is not None else ""
    fecha_raw = str(cfdi_dict.get("fecha", ""))
    fecha = fecha_raw[:10] if fecha_raw else ""

    if fatal:
        status = "error"
    elif findings:
        status = "con_errores"
    else:
        status = "ok"

    return {
        "filename": filename,
        "status": status,
        "profile": result.profile,
        "rfc_emisor": rfc_emisor,
        "rfc_receptor": rfc_receptor,
        "nombre_emisor": nombre_emisor,
        "total": total,
        "fecha": fecha,
        "findings_count": len(findings),
        "error": None,
    }


@router.post("/analyze")
async def batch_analyze(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "Se requiere al menos un archivo")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Máximo {MAX_FILES} archivos por lote")

    # Read all uploads in parallel before processing
    contents = list(await asyncio.gather(*[_read_upload(f) for f in files]))

    tasks = [_analyze_one(fname, raw) for fname, raw in contents]
    results = list(await asyncio.gather(*tasks))

    files_ok = sum(1 for r in results if r["status"] == "ok")
    files_con_errores = sum(1 for r in results if r["status"] == "con_errores")
    files_error = sum(1 for r in results if r["status"] == "error")

    return {
        "results": results,
        "summary": {
            "total_files": len(results),
            "files_ok": files_ok,
            "files_con_errores": files_con_errores,
            "files_error": files_error,
            "total_findings": sum(r["findings_count"] for r in results),
        },
    }


@router.post("/diot")
async def batch_diot(
    files: list[UploadFile] = File(...),
    year: int = Form(...),
    month: int = Form(...),
    rfc_presentante: str = Form(default=""),
    razon_social: str = Form(default=""),
):
    if not files:
        raise HTTPException(400, "Se requiere al menos un archivo")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Máximo {MAX_FILES} archivos por lote")
    if not 1 <= month <= 12:
        raise HTTPException(400, "El mes debe estar entre 1 y 12")

    # Read all uploads in parallel
    xml_list = list(await asyncio.gather(*[f.read() for f in files]))

    try:
        loop = asyncio.get_running_loop()
        diot_bytes = await loop.run_in_executor(
            None,
            lambda: generate_diot(
                xml_list,
                year=year,
                month=month,
                rfc_presentante=rfc_presentante or None,
                razon_social=razon_social or None,
            ),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error generando DIOT: {e}")

    rfc_label = (rfc_presentante or "DIOT").upper().replace(" ", "_")
    month_str = str(month).zfill(2)
    filename = f"DIOT_{rfc_label}_{year}{month_str}.txt"

    return StreamingResponse(
        iter([diot_bytes]),
        media_type="text/plain; charset=windows-1252",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
