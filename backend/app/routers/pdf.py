from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from satcfdi.cfdi import CFDI
from satcfdi.render import pdf_bytes

router = APIRouter()


@router.post("/api/cfdi/pdf")
async def generate_pdf(file: UploadFile) -> Response:
    xml = await file.read()
    try:
        cfdi = CFDI.from_string(xml)
        pdf = pdf_bytes(cfdi)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo generar el PDF: {exc}") from exc

    uuid = cfdi.get("Complemento", {}).get("TimbreFiscalDigital", {}).get("UUID", "cfdi")
    filename = f"cfdi-{str(uuid)[:8]}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
