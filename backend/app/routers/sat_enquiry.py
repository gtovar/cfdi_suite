from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
import openpyxl
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from ..credentials import get as get_cred

router = APIRouter(prefix="/api/sat", tags=["sat"])

_DIVERZA_BASE = "https://servicios.diverza.com/api/v2/documents"
_PRIORITY_FIELDS = {"estatus_cancelacion", "estado", "es_cancelable"}

# In-memory job results store (single-user local tool — no persistence needed)
_job_results: dict[str, bytes] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class EnquiryRequest(BaseModel):
    uuid: str
    rfc_emisor: str
    rfc_receptor: str
    total_cfdi: str
    motive: str = "01"


class EnquiryResult(BaseModel):
    uuid: str
    estado: str
    es_cancelable: str
    estatus_cancelacion: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Diverza response parsing
# ---------------------------------------------------------------------------


def _extract_json_objects(text: str) -> list[str]:
    """Extract JSON object strings from arbitrary text (handles malformed responses)."""
    objs: list[str] = []
    start: int | None = None
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objs.append(text[start : i + 1])
                start = None
    return objs


def _choose_best_json(text: str) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1
    for candidate in _extract_json_objects(text):
        try:
            parsed: dict[str, Any] = json.loads(candidate)
            score = sum(k in parsed for k in _PRIORITY_FIELDS)
            if score > best_score:
                best, best_score = parsed, score
        except json.JSONDecodeError:
            pass
    return best


def _parse_diverza_response(text: str) -> dict[str, str | None]:
    parsed = _choose_best_json(text)
    if not parsed:
        return {
            "estado": "",
            "es_cancelable": "",
            "estatus_cancelacion": "",
            "error": "JSON inválido en respuesta de Diverza",
        }

    estado = (parsed.get("estado") or "").strip()
    es_cancelable = (parsed.get("es_cancelable") or "").strip()
    estatus_cancelacion = (parsed.get("estatus_cancelacion") or "").strip()

    # Domain rule from reference implementation
    if (
        estado.lower() == "vigente"
        and es_cancelable.lower() == "no cancelable"
        and not estatus_cancelacion
    ):
        estatus_cancelacion = "No cancelable estatus"

    return {
        "estado": estado,
        "es_cancelable": es_cancelable,
        "estatus_cancelacion": estatus_cancelacion,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Diverza HTTP call
# ---------------------------------------------------------------------------


def _build_payload(
    uuid: str,
    rfc_emisor: str,
    rfc_receptor: str,
    total_cfdi: str,
    motive: str,
    cred: dict[str, str],
) -> dict[str, Any]:
    return {
        "credentials": {
            "id": cred.get("credential_id", ""),
            "token": cred.get("credential_token", ""),
        },
        "issuer": {"rfc": rfc_emisor},
        "document": {
            "certificate-number": cred.get("certificate_number", ""),
            "rfc_receptor": rfc_receptor,
            "total_cfdi": total_cfdi,
            "motive": str(motive).zfill(2),
            "replacement-folio": "",
        },
    }


async def _call_diverza(
    client: httpx.AsyncClient,
    uuid: str,
    payload: dict[str, Any],
    max_retries: int = 3,
) -> str:
    url = f"{_DIVERZA_BASE}/{uuid}/sat_cfdi_enquiry"
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.put(url, json=payload, timeout=30.0)
            if 500 <= resp.status_code < 600 and attempt < max_retries:
                await asyncio.sleep(2**attempt)
                continue
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < max_retries:
                await asyncio.sleep(2**attempt)

    raise last_exc or RuntimeError("Max retries exceeded")


async def _enquiry_indexed(
    client: httpx.AsyncClient,
    idx: int,
    uuid: str,
    rfc_emisor: str,
    rfc_receptor: str,
    total_cfdi: str,
    motive: str,
) -> tuple[int, dict[str, Any]]:
    cred = get_cred(rfc_emisor.upper())
    if not cred:
        return idx, {
            "uuid": uuid,
            "estado": "",
            "es_cancelable": "",
            "estatus_cancelacion": "",
            "error": f"RFC emisor no configurado: {rfc_emisor}",
        }

    payload = _build_payload(uuid, rfc_emisor, rfc_receptor, total_cfdi, motive, cred)

    try:
        text = await _call_diverza(client, uuid, payload)
    except Exception as exc:
        return idx, {
            "uuid": uuid,
            "estado": "",
            "es_cancelable": "",
            "estatus_cancelacion": "",
            "error": str(exc),
        }

    result = _parse_diverza_response(text)
    return idx, {"uuid": uuid, **result}


# ---------------------------------------------------------------------------
# Excel helpers
# ---------------------------------------------------------------------------


def _parse_excel_input(content: bytes) -> list[dict[str, str]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header_row = next(rows_iter, None)
    if not header_row:
        return []

    headers = [str(cell or "").strip() for cell in header_row]

    rows: list[dict[str, str]] = []
    for ws_row in rows_iter:
        row = dict(zip(headers, ws_row))
        uuid = str(row.get("UUID") or "").strip()
        if not uuid:
            continue
        rows.append(
            {
                "uuid": uuid,
                "rfc_emisor": str(row.get("RFC emisor") or "").strip().upper(),
                "rfc_receptor": str(row.get("RFC receptor") or "").strip(),
                "total_cfdi": str(row.get("TotalCFDI") or ""),
                "motive": str(row.get("Motive") or "01"),
            }
        )
    return rows


def _build_result_excel(
    rows_input: list[dict[str, str]], results: list[dict[str, Any] | None]
) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resultados SAT"
    ws.append(
        [
            "UUID",
            "RFC emisor",
            "RFC receptor",
            "Motive",
            "estado",
            "es_cancelable",
            "estatus_cancelacion",
            "fecha_consulta",
            "error",
        ]
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row, result in zip(rows_input, results):
        r: dict[str, Any] = result or {}
        ws.append(
            [
                row["uuid"],
                row["rfc_emisor"],
                row["rfc_receptor"],
                row["motive"],
                r.get("estado", ""),
                r.get("es_cancelable", ""),
                r.get("estatus_cancelacion", ""),
                now,
                r.get("error", "") or "",
            ]
        )

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.read()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/enquiry", response_model=EnquiryResult)
async def single_sat_enquiry(body: EnquiryRequest) -> EnquiryResult:
    cred = get_cred(body.rfc_emisor.upper())
    if not cred:
        raise HTTPException(
            status_code=404,
            detail=f"RFC emisor no configurado: {body.rfc_emisor}",
        )

    payload = _build_payload(
        body.uuid, body.rfc_emisor, body.rfc_receptor, body.total_cfdi, body.motive, cred
    )

    async with httpx.AsyncClient() as client:
        try:
            text = await _call_diverza(client, body.uuid, payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Error Diverza: {exc}") from exc

    result = _parse_diverza_response(text)
    return EnquiryResult(uuid=body.uuid, **result)


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/enquiry/batch")
async def batch_sat_enquiry(file: UploadFile = File(...)) -> StreamingResponse:
    content = await file.read()

    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="El archivo excede el límite de 10 MB")

    try:
        rows = _parse_excel_input(content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error leyendo Excel: {exc}") from exc

    if not rows:
        raise HTTPException(status_code=400, detail="El archivo no contiene filas con UUID")

    total = len(rows)
    job_id = str(uuid4())
    results: list[dict[str, Any] | None] = [None] * total

    async def event_stream():
        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=20)
        ) as client:
            tasks = [
                asyncio.create_task(
                    _enquiry_indexed(
                        client,
                        idx,
                        row["uuid"],
                        row["rfc_emisor"],
                        row["rfc_receptor"],
                        row["total_cfdi"],
                        row["motive"],
                    )
                )
                for idx, row in enumerate(rows)
            ]

            processed = 0
            for coro in asyncio.as_completed(tasks):
                idx, result = await coro
                results[idx] = result
                processed += 1
                yield f"data: {json.dumps({'type': 'progress', 'processed': processed, 'total': total})}\n\n"

        excel_bytes = _build_result_excel(rows, results)
        # Evict oldest entry if store grows (local tool — no concurrent users)
        if len(_job_results) >= 5:
            oldest = next(iter(_job_results))
            del _job_results[oldest]
        _job_results[job_id] = excel_bytes
        yield f"data: {json.dumps({'type': 'done', 'job_id': job_id, 'total': total})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/enquiry/batch/{job_id}/result")
def get_batch_result(job_id: str) -> Response:
    excel_bytes = _job_results.pop(job_id, None)
    if not excel_bytes:
        raise HTTPException(status_code=404, detail="Resultado no encontrado o ya descargado")

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="consultas_sat.xlsx"'},
    )
