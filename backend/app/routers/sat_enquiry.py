from __future__ import annotations

import asyncio
import io
import json
import re
from datetime import datetime
from typing import Any, NamedTuple
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

# El UUID entra crudo a una URL de un tercero que se llama AUTENTICADA con el
# credential_id/credential_token del emisor. No basta con confiar en que httpx
# lo escape: httpx normaliza "../" según RFC 3986, así que un uuid de
# "../../../admin" convierte
#   https://servicios.diverza.com/api/v2/documents/{uuid}/sat_cfdi_enquiry
# en
#   https://servicios.diverza.com/admin/sat_cfdi_enquiry
# (comprobado con httpx.URL el 2026-07-26). Se valida la forma, que es la
# única defensa que no depende del comportamiento de la librería.
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _is_uuid(value: str) -> bool:
    return bool(value) and bool(_UUID_RE.match(value))


def _require_uuid(value: str) -> str:
    if not _is_uuid(value):
        raise HTTPException(status_code=400, detail="UUID de CFDI inválido")
    return value

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
    url = f"{_DIVERZA_BASE}/{_require_uuid(uuid)}/sat_cfdi_enquiry"
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


class ParsedInput(NamedTuple):
    """Filas utilizables + cuántas se descartaron por traer un UUID malformado.

    `descartadas` NO cuenta las filas con UUID vacío: en un Excel real las
    últimas filas suelen venir en blanco y reportarlas sería ruido. Cuenta sólo
    las que traen algo que no es un UUID -- ésas sí son un dato del usuario que
    no se va a consultar, y merece decírselo en vez de tragarlo.
    """

    rows: list[dict[str, str]]
    descartadas: int


def _parse_excel_input(content: bytes) -> ParsedInput:
    # read_only=True: el modelo eager de openpyxl expande 10 MB de XLSX
    # comprimido a ~1-2 GB de objetos Python y mata la instancia de Cloud Run
    # por OOM. El modo streaming sólo materializa la fila en curso. Aquí sólo
    # se usa iter_rows(values_only=True), que funciona igual en ese modo.
    # El finally es obligatorio: en read_only openpyxl deja abiertos los
    # handles del ZIP si no se cierra el workbook.
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row:
            return ParsedInput([], 0)

        headers = [str(cell or "").strip() for cell in header_row]

        rows: list[dict[str, str]] = []
        descartadas = 0
        for ws_row in rows_iter:
            row = dict(zip(headers, ws_row))
            uuid = str(row.get("UUID") or "").strip()
            # Se descarta la fila en vez de reventar el lote: un UUID malformado
            # en la fila 300 de un Excel no debe abortar las otras 499. El
            # rechazo duro vive en _require_uuid, en el único punto que arma la
            # URL de Diverza.
            if not _is_uuid(uuid):
                if uuid:
                    descartadas += 1
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
        return ParsedInput(rows, descartadas)
    finally:
        wb.close()


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
        rows, descartadas = _parse_excel_input(content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error leyendo Excel: {exc}") from exc

    if not rows:
        # Si TODAS las filas traían UUID pero ninguna era válida, decirlo: el
        # mensaje genérico haría pensar que el archivo venía vacío.
        if descartadas:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ninguna de las {descartadas} filas tiene un UUID válido. "
                    "El UUID de un CFDI tiene la forma "
                    "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx."
                ),
            )
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
        # `descartadas`: filas del Excel que traían un UUID malformado y no se
        # consultaron. Sin este dato el usuario sube 500 filas, recibe 480
        # resultados y no tiene forma de saber qué pasó con las otras 20.
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "done",
                    "job_id": job_id,
                    "total": total,
                    "descartadas": descartadas,
                }
            )
            + "\n\n"
        )

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
