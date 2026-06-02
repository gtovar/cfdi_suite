from __future__ import annotations

import asyncio
import copy
import io
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator, Callable
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from satcfdi.cfdi import CFDI
from satcfdi.render import html_str
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

CHUNK_SIZE = 1500
MAX_PARALLEL_PAGES = 4
_TIMEOUT_SECONDS = 60  # por chunk individual


@dataclass
class _Job:
    status: str = "queued"
    progress_detail: str = ""
    pdf: bytes = field(default=b"", repr=False)
    filename: str = "cfdi.pdf"
    error: str = ""


_jobs: dict[str, _Job] = {}


def _split_cfdi(cfdi: CFDI, chunk_size: int) -> list[CFDI]:
    conceptos = cfdi.get("Conceptos") or []
    if isinstance(conceptos, dict):
        conceptos = [conceptos]
    if len(conceptos) <= chunk_size:
        return [cfdi]
    chunks = []
    for i in range(0, len(conceptos), chunk_size):
        c = copy.copy(cfdi)
        c["Conceptos"] = conceptos[i : i + chunk_size]
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


async def _render_chunks_parallel(
    htmls: list[str],
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> bytes:
    from playwright.async_api import async_playwright
    from pypdf import PdfReader, PdfWriter

    sem = asyncio.Semaphore(MAX_PARALLEL_PAGES)
    results: list[tuple[int, bytes]] = []

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

        tasks = [render_one(i, h) for i, h in enumerate(htmls)]
        done_count = 0
        for coro in asyncio.as_completed(tasks):
            idx, pdf = await coro
            results.append((idx, pdf))
            done_count += 1
            if on_chunk_done:
                on_chunk_done(done_count, len(htmls))

        await browser.close()

    writer = PdfWriter()
    for _, pdf_bytes in sorted(results):
        writer.append(PdfReader(io.BytesIO(pdf_bytes)))
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def _process(job_id: str, xml: bytes) -> None:
    job = _jobs[job_id]
    try:
        job.status = "parsing"
        cfdi = await asyncio.to_thread(CFDI.from_string, xml)

        job.status = "rendering_html"
        chunks = _split_cfdi(cfdi, CHUNK_SIZE)
        htmls: list[str] = []
        head_style = ""
        for i, c in enumerate(chunks):
            raw = await asyncio.to_thread(html_str, c)
            if i == 0:
                head_style = _extract_head_styles(raw)
                htmls.append(raw)
            else:
                thead, tbody = _extract_conceptos_table(raw)
                htmls.append(_build_chunk_html(head_style, thead, tbody))

        job.status = "generating_pdf"
        total = len(htmls)
        job.progress_detail = f"Generando parte 1 de {total}…" if total > 1 else ""

        def on_chunk_done(done: int, t: int) -> None:
            job.progress_detail = f"Generando parte {done} de {t}…" if t > 1 else ""

        job.pdf = await _render_chunks_parallel(htmls, on_chunk_done=on_chunk_done)

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


@router.post("/api/cfdi/pdf/start")
async def start_pdf_job(file: UploadFile) -> dict:
    xml = await file.read()
    job_id = str(uuid4())
    _jobs[job_id] = _Job()
    asyncio.create_task(_process(job_id, xml))
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
