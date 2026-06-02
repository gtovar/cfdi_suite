from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import json
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import Response
from satcfdi.cfdi import CFDI
from satcfdi.render import html_str
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

CHUNK_SIZE = 1500
MAX_PARALLEL_PAGES = 4
_TIMEOUT_SECONDS = 60
_MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB

# Cache de CFDIs parseados para el endpoint de preview (evita re-parsear en cada cambio de template)
_cfdi_cache: dict[str, tuple[CFDI, float]] = {}
_CACHE_TTL = 300  # 5 minutos


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
    return (
        f"<!DOCTYPE html><html><head>{style}</head>"
        f"<body><table>{thead}{tbody}</table></body></html>"
    )


def _uuid_prefix(cfdi: CFDI) -> str:
    tfd = (cfdi.get("Complemento") or {}).get("TimbreFiscalDigital") or {}
    return str(tfd.get("UUID", "")).replace("-", "")[:8]


async def _process(job_id: str, xml: bytes, engine: str, template: dict | None) -> None:
    from playwright.async_api import async_playwright
    from pypdf import PdfReader, PdfWriter

    job = _jobs[job_id]
    try:
        job.status = "parsing"
        cfdi = await asyncio.to_thread(CFDI.from_string, xml)

        if engine == "reportlab":
            from app.services.pdf_reportlab import generate_pdf
            job.status = "generating_pdf"
            job.pdf = await asyncio.to_thread(generate_pdf, cfdi, template)
            prefix = _uuid_prefix(cfdi)
            job.filename = f"cfdi-{prefix}.pdf" if prefix else "cfdi.pdf"
            job.status = "done"
            return

        chunks = _split_cfdi(cfdi)
        n = len(chunks)

        job.status = "generating_pdf"
        job.progress_detail = f"Generando parte 1 de {n}…" if n > 1 else ""

        sem = asyncio.Semaphore(MAX_PARALLEL_PAGES)
        results: list[tuple[int, bytes]] = []
        done_count = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch()

            async def render_one(idx: int, html: str) -> tuple[int, bytes]:
                async with sem:
                    page = await browser.new_page()
                    await asyncio.wait_for(
                        page.set_content(html, wait_until="domcontentloaded"),
                        timeout=_TIMEOUT_SECONDS,
                    )
                    pdf = await asyncio.wait_for(
                        page.pdf(format="Letter", print_background=True),
                        timeout=_TIMEOUT_SECONDS,
                    )
                    await page.close()
                    return idx, pdf

            # Pipeline: dispatch render tasks as each chunk's HTML becomes ready,
            # instead of waiting for all HTML before starting any render.
            render_tasks: list[asyncio.Task[tuple[int, bytes]]] = []
            head_style = ""
            for i, c in enumerate(chunks):
                raw = await asyncio.to_thread(html_str, c)
                if i == 0:
                    head_style = _extract_head_styles(raw)
                    chunk_html = raw
                else:
                    thead, tbody = _extract_conceptos_table(raw)
                    chunk_html = _build_chunk_html(head_style, thead, tbody)
                render_tasks.append(asyncio.create_task(render_one(i, chunk_html)))

            for coro in asyncio.as_completed(render_tasks):
                idx, pdf_bytes = await coro
                results.append((idx, pdf_bytes))
                done_count += 1
                job.progress_detail = f"Generando parte {done_count} de {n}…" if n > 1 else ""

            await browser.close()

        writer = PdfWriter()
        for _, pdf_bytes in sorted(results):
            writer.append(PdfReader(io.BytesIO(pdf_bytes)))
        buf = io.BytesIO()
        writer.write(buf)
        job.pdf = buf.getvalue()

        prefix = _uuid_prefix(cfdi)
        job.filename = f"cfdi-{prefix}.pdf" if prefix else "cfdi.pdf"
        job.progress_detail = ""
        job.status = "done"

    except asyncio.TimeoutError:
        job.status = "error"
        job.error = (
            "Este CFDI tiene demasiados conceptos para generar un PDF completo. "
            "Prueba exportar a Excel primero."
        )
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)


@router.post("/api/cfdi/pdf/preview")
async def preview_pdf(request: Request) -> Response:
    """Generate a fast preview PDF using cached CFDI parse. Used by the template builder."""
    from app.services.pdf_reportlab import generate_preview
    form = await request.form(max_part_size=_MAX_UPLOAD)
    file = form["file"]
    xml = await file.read()
    template_dict: dict | None = None
    raw_template = form.get("template")
    if raw_template:
        try:
            template_dict = json.loads(raw_template)
        except Exception:
            pass
    cfdi = await _get_cfdi_cached(xml)
    pdf_bytes = await asyncio.to_thread(generate_preview, cfdi, template_dict)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=preview.pdf"},
    )


@router.post("/api/cfdi/pdf/start")
async def start_pdf_job(request: Request) -> dict:
    form = await request.form(max_part_size=_MAX_UPLOAD)
    file = form["file"]
    xml = await file.read()
    engine = form.get("engine", "playwright")
    template_dict: dict | None = None
    raw_template = form.get("template")
    if raw_template:
        try:
            template_dict = json.loads(raw_template)
        except Exception:
            pass
    job_id = str(uuid4())
    _jobs[job_id] = _Job()
    asyncio.create_task(_process(job_id, xml, engine, template_dict))
    return {"jobId": job_id}


@router.get("/api/cfdi/pdf/{job_id}/progress")
async def pdf_progress(job_id: str) -> EventSourceResponse:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    async def _stream() -> AsyncGenerator[dict, None]:
        last_key = ""
        while True:
            job = _jobs.get(job_id)
            if job is None:
                break
            key = f"{job.status}:{job.progress_detail}"
            if key != last_key:
                last_key = key
                yield {
                    "data": json.dumps({
                        "status": job.status,
                        "progress_detail": job.progress_detail,
                        "error": job.error,
                    })
                }
            if job.status in ("done", "error"):
                break
            await asyncio.sleep(0.3)

    return EventSourceResponse(_stream())


@router.get("/api/cfdi/pdf/{job_id}/status")
async def pdf_status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return {"status": job.status, "error": job.error, "progress_detail": job.progress_detail}


@router.get("/api/cfdi/pdf/{job_id}/download")
async def download_pdf(job_id: str) -> Response:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    if job.status != "done":
        raise HTTPException(status_code=409, detail=f"Job status: {job.status}")
    _jobs.pop(job_id, None)
    return Response(
        content=job.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={job.filename}"},
    )
