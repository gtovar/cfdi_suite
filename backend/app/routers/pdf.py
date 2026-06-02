from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from satcfdi.cfdi import CFDI
from satcfdi.render import html_str
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

_TIMEOUT_SECONDS = 180


@dataclass
class _Job:
    status: str = "queued"   # queued | parsing | rendering_html | generating_pdf | done | error
    pdf: bytes = field(default=b"", repr=False)
    filename: str = "cfdi.pdf"
    error: str = ""


_jobs: dict[str, _Job] = {}


def _uuid_prefix(cfdi: CFDI) -> str:
    tfd = (cfdi.get("Complemento") or {}).get("TimbreFiscalDigital") or {}
    prefix = str(tfd.get("UUID", "")).replace("-", "")[:8]
    return prefix


async def _process(job_id: str, xml: bytes) -> None:
    job = _jobs[job_id]
    try:
        job.status = "parsing"
        cfdi = await asyncio.to_thread(CFDI.from_string, xml)

        job.status = "rendering_html"
        html = await asyncio.to_thread(html_str, cfdi)

        job.status = "generating_pdf"
        pdf_bytes = await _playwright_pdf(html)

        prefix = _uuid_prefix(cfdi)
        job.filename = f"cfdi-{prefix}.pdf" if prefix else "cfdi.pdf"
        job.pdf = pdf_bytes
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


async def _playwright_pdf(html: str) -> bytes:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await asyncio.wait_for(
            page.set_content(html, wait_until="domcontentloaded"),
            timeout=_TIMEOUT_SECONDS,
        )
        pdf = await asyncio.wait_for(
            page.pdf(format="Letter", print_background=True),
            timeout=_TIMEOUT_SECONDS,
        )
        await browser.close()
        return pdf


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
        last = ""
        while True:
            job = _jobs.get(job_id)
            if job is None:
                break
            if job.status != last:
                last = job.status
                yield {"data": json.dumps({"status": job.status, "error": job.error})}
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

    _jobs.pop(job_id, None)  # limpiar después de descargar
    return Response(
        content=job.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={job.filename}"},
    )
