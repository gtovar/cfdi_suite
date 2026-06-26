from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import io
import json
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator
from uuid import uuid4
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import Response
from satcfdi.cfdi import CFDI
from satcfdi.render import html_str
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

CHUNK_SIZE = 1500
MAX_PARALLEL_PAGES = 4
_TIMEOUT_SECONDS = 60
_ARQ_THRESHOLD = 50_000  # conceptos — por encima de este valor se despacha a ARQ

_cfdi_cache: dict[str, tuple[CFDI, float]] = {}
_CACHE_TTL = 300


async def _get_cfdi_cached(xml: bytes) -> CFDI:
    key = hashlib.md5(xml, usedforsecurity=False).hexdigest()
    if key in _cfdi_cache:
        cfdi, ts = _cfdi_cache[key]
        if time.monotonic() - ts < _CACHE_TTL:
            return cfdi
    cfdi = await asyncio.to_thread(CFDI.from_string, xml)
    _cfdi_cache[key] = (cfdi, time.monotonic())
    return cfdi


@dataclass
class _Job:
    status: str = "queued"
    progress_detail: str = ""
    pdf: bytes = field(default=b"", repr=False)
    filename: str = "cfdi.pdf"
    error: str = ""
    is_arq: bool = False  # True → resultado en Redis, no en .pdf


_jobs: dict[str, _Job] = {}


def _split_cfdi(cfdi: CFDI) -> list[CFDI]:
    conceptos = cfdi.get("Conceptos") or []
    if isinstance(conceptos, dict):
        conceptos = [conceptos]
    if len(conceptos) <= CHUNK_SIZE:
        return [cfdi]
    chunks = []
    for i in range(0, len(conceptos), CHUNK_SIZE):
        c = copy.copy(cfdi)
        c["Conceptos"] = conceptos[i : i + CHUNK_SIZE]
        chunks.append(c)
    return chunks


def _extract_head_styles(html: str) -> str:
    from lxml import html as lh
    doc = lh.fromstring(html.encode())
    styles = doc.xpath("//style")
    return lh.tostring(styles[0], encoding="unicode") if styles else ""


def _extract_conceptos_table(html: str) -> tuple[str, str]:
    from lxml import html as lh
    doc = lh.fromstring(html.encode())
    base = "//h5[contains(text(), 'Conceptos')]/following-sibling::table[1]"
    theads = doc.xpath(f"{base}/thead")
    tbodies = doc.xpath(f"{base}/tbody")
    if not theads or not tbodies:
        return "", ""
    return lh.tostring(theads[0], encoding="unicode"), lh.tostring(tbodies[0], encoding="unicode")


def _build_chunk_html(style: str, thead: str, tbody: str) -> str:
    return f"<!DOCTYPE html><html><head>{style}</head><body><table>{thead}{tbody}</table></body></html>"


def _uuid_prefix(cfdi: CFDI) -> str:
    tfd = (cfdi.get("Complemento") or {}).get("TimbreFiscalDigital") or {}
    return str(tfd.get("UUID", "")).replace("-", "")[:8]


async def _process(job_id: str, xml: bytes, engine: str, template: dict | None) -> None:
    job = _jobs[job_id]
    try:
        # canvas_pipeline tiene su propio parser (lxml SAX), no necesita satcfdi
        if engine == "canvas_pipeline":
            from ..services.pdf_pipeline import generate as pipeline_generate
            job.status = "generating_pdf"
            xml_str = xml.decode("utf-8", errors="replace")
            concepto_count = xml_str.count("<cfdi:Concepto ")
            job.progress_detail = f"Generando PDF ({concepto_count:,} conceptos)..."
            template_id = (template or {}).get("_id", "default")
            html_shell = (template or {}).get("_html_shell")
            job.pdf = await asyncio.to_thread(pipeline_generate, xml_str, template_id, html_shell)
            job.status = "done"
            return

        # reportlab y gopdfsuit necesitan el objeto CFDI de satcfdi
        job.status = "parsing"
        cfdi = await asyncio.to_thread(CFDI.from_string, xml)

        if engine == "reportlab":
            from ..services.pdf_reportlab import generate_pdf
            job.status = "generating_pdf"
            job.pdf = await asyncio.to_thread(generate_pdf, cfdi, template)
            prefix = _uuid_prefix(cfdi)
            job.filename = f"cfdi-{prefix}.pdf" if prefix else "cfdi.pdf"
            job.status = "done"
            return

        if engine == "gopdfsuit":
            import httpx
            job.status = "generating_pdf"
            job.progress_detail = "Enviando datos al motor Go..."

            final_template = template
            if not final_template or "elements" not in final_template or not final_template["elements"]:
                try:
                    template_path = Path(__file__).resolve().parents[2] / "templates" / "default.json"
                    if template_path.exists():
                        final_template = json.loads(template_path.read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"Error forzando lectura de respaldo: {e}")

            payload = {
                "xml": xml.decode("utf-8", errors="replace"),
                "template": final_template
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8080/api/v1/generate",
                    json=payload,
                    timeout=60.0
                )
                if response.status_code != 200:
                    raise RuntimeError(f"GoPdfSuit falló ({response.status_code}): {response.text}")

                job.pdf = response.content
                prefix = _uuid_prefix(cfdi)
                job.filename = f"cfdi-{prefix}.pdf" if prefix else "cfdi.pdf"
                job.status = "done"
                return

        job.status = "error"
        job.error = "Motor no soportado"
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.post("/api/cfdi/pdf/preview")
async def preview_pdf(request: Request) -> Response:
    import httpx
    form = await request.form()
    file = form["file"]
    xml_bytes = await file.read()

    template_dict = {}
    raw_template = form.get("template")
    if raw_template:
        try:
            template_dict = json.loads(raw_template)
        except Exception:
            pass

    if not template_dict or "elements" not in template_dict or not template_dict["elements"]:
        try:
            template_path = Path(__file__).resolve().parents[2] / "templates" / "default.json"
            if template_path.exists():
                template_dict = json.loads(template_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    payload = {
        "xml": xml_bytes.decode("utf-8", errors="replace"),
        "template": template_dict
    }

    async with httpx.AsyncClient() as client:
        go_response = await client.post(
            "http://localhost:8080/api/v1/generate",
            json=payload,
            timeout=30.0
        )
        return Response(content=go_response.content, media_type="application/pdf")


@router.post("/api/cfdi/pdf/start")
async def start_pdf_job(request: Request) -> dict:
    form = await request.form()
    file = form["file"]
    xml = await file.read()
    engine = form.get("engine", "reportlab")
    template_dict: dict | None = None
    raw_template = form.get("template")
    if raw_template:
        try:
            template_dict = json.loads(raw_template)
        except Exception:
            pass

    job_id = str(uuid4())

    # Dispatcher: jobs canvas_pipeline con >50k conceptos van a ARQ si Redis está disponible
    if engine == "canvas_pipeline":
        xml_str = xml.decode("utf-8", errors="replace")
        concepto_count = xml_str.count("<cfdi:Concepto ")
        arq_pool = getattr(request.app.state, "arq_pool", None)

        if concepto_count > _ARQ_THRESHOLD and arq_pool is not None:
            template_id = (template_dict or {}).get("_id", "default")
            html_shell = (template_dict or {}).get("_html_shell")
            xml_b64 = base64.b64encode(xml).decode()

            _jobs[job_id] = _Job(
                status="queued",
                progress_detail=f"En cola ARQ ({concepto_count:,} conceptos)",
                is_arq=True,
            )
            await arq_pool.enqueue_job(
                "generate_heavy_pdf", job_id, xml_b64, template_id, html_shell
            )
            return {"jobId": job_id}

    _jobs[job_id] = _Job()
    asyncio.create_task(_process(job_id, xml, engine, template_dict))
    return {"jobId": job_id}


@router.get("/api/cfdi/pdf/{job_id}/progress")
async def pdf_progress(job_id: str, request: Request) -> EventSourceResponse:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    async def _stream() -> AsyncGenerator[dict, None]:
        while True:
            job = _jobs.get(job_id)
            if job is None:
                break

            if job.is_arq:
                arq_pool = getattr(request.app.state, "arq_pool", None)
                if arq_pool:
                    raw = await arq_pool.get(f"pdf:status:{job_id}")
                    arq_status = raw.decode() if raw else job.status
                    if arq_status.startswith("error:"):
                        job.status = "error"
                        job.error = arq_status[6:]
                        arq_status = "error"
                    else:
                        job.status = arq_status
                    yield {"data": json.dumps({
                        "status": arq_status,
                        "progress_detail": job.progress_detail,
                        "error": job.error,
                    })}
                    if arq_status in ("done", "error"):
                        break
            else:
                yield {"data": json.dumps({
                    "status": job.status,
                    "progress_detail": job.progress_detail,
                    "error": job.error,
                })}
                if job.status in ("done", "error"):
                    break

            await asyncio.sleep(0.5)

    return EventSourceResponse(_stream())


@router.get("/api/cfdi/pdf/{job_id}/status")
async def pdf_status(job_id: str, request: Request) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    if job.is_arq:
        arq_pool = getattr(request.app.state, "arq_pool", None)
        if arq_pool:
            raw = await arq_pool.get(f"pdf:status:{job_id}")
            status = raw.decode() if raw else job.status
            if status.startswith("error:"):
                return {"status": "error", "error": status[6:], "progress_detail": ""}
            return {"status": status, "error": "", "progress_detail": job.progress_detail}

    return {"status": job.status, "error": job.error, "progress_detail": job.progress_detail}


@router.get("/api/cfdi/pdf/{job_id}/download")
async def download_pdf(job_id: str, request: Request) -> Response:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    if job.is_arq:
        arq_pool = getattr(request.app.state, "arq_pool", None)
        if arq_pool:
            pdf_bytes = await arq_pool.get(f"pdf:result:{job_id}")
            if pdf_bytes is None:
                raise HTTPException(status_code=409, detail="PDF aún no disponible en Redis")
            await arq_pool.delete(f"pdf:result:{job_id}", f"pdf:status:{job_id}")
            _jobs.pop(job_id, None)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={job.filename}"},
            )

    if job.status != "done":
        raise HTTPException(status_code=409, detail=f"Job status: {job.status}")
    _jobs.pop(job_id, None)
    return Response(
        content=job.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={job.filename}"},
    )


@router.post("/api/cfdi/pdf/preview-template")
@router.post("/cfdi/pdf/preview-template")
async def preview_template(template: dict):
    try:
        import httpx
        fixture_path = Path(__file__).resolve().parents[2] / "test-fixtures" / "pago_h_e951128469_ingreso_ieps_exento.xml"
        xml_content = fixture_path.read_text(encoding="utf-8")
        payload = {"xml": xml_content, "template": template}

        async with httpx.AsyncClient() as client:
            go_response = await client.post("http://localhost:8080/api/v1/generate", json=payload, timeout=30.0)
            return Response(content=go_response.content, media_type="application/pdf")
    except Exception as e:
        return Response(content=f"Error: {str(e)}", status_code=500)
