from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


def _load_all() -> list[dict]:
    templates = []
    for path in sorted(_TEMPLATES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("id", path.stem)
            templates.append(data)
        except Exception:
            pass
    return templates


@router.get("/api/templates")
async def list_templates() -> JSONResponse:
    return JSONResponse(_load_all())


@router.get("/api/templates/{template_id}")
async def get_template(template_id: str) -> JSONResponse:
    path = _TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template no encontrado")
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("id", template_id)
    return JSONResponse(data)


# ==============================================================================
# 🚀 RUTA DE GUARDADO DE PLANTILLAS (CORREGIDA Y COMPILADA)
# ==============================================================================
@router.post("/api/templates/{template_id}")
@router.put("/api/templates/{template_id}")
async def save_template(template_id: str, request: Request):
    try:
        template_data = await request.json()
        path = _TEMPLATES_DIR / f"{template_id}.json"
        
        path.write_text(
            json.dumps(template_data, indent=2, ensure_ascii=False), 
            encoding="utf-8"
        )
        return JSONResponse(status_code=200, content={"status": "success", "message": "Guardado exitoso"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar plantilla en disco: {str(e)}")


# ── HTML shell endpoints ──────────────────────────────────────────────────────

@router.get("/api/templates/{template_id}/html")
async def get_html_template(template_id: str):
    from ..services.shell_service import get_html_template as _get
    return JSONResponse({"html": _get(template_id)})


@router.put("/api/templates/{template_id}/html")
async def save_html_template(template_id: str, request: Request):
    try:
        body = await request.json()
        html = body.get("html", "")
        if not html.strip():
            raise HTTPException(status_code=400, detail="El campo 'html' es requerido")
        from ..services.shell_service import save_html_template as _save
        _save(template_id, html)
        return JSONResponse({"status": "ok"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/templates/{template_id}/shell-preview")
async def shell_preview(template_id: str, request: Request):
    """Renderiza el HTML shell en memoria y devuelve el PDF. Sin cache."""
    try:
        body = await request.json()
        html = body.get("html", "")
        if not html.strip():
            from ..services.shell_service import get_html_template
            html = get_html_template(template_id)
        from ..services.shell_service import render_shell_preview
        import asyncio
        pdf_bytes = await asyncio.to_thread(render_shell_preview, html)
        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/templates/{template_id}/shell")
async def regenerate_shell(template_id: str, request: Request):
    """Guarda el HTML y lo pre-renderiza con datos de ejemplo."""
    try:
        body = await request.json()
        html = body.get("html")
        if html:
            from ..services.shell_service import save_html_template
            save_html_template(template_id, html)
        return JSONResponse({"status": "ok", "message": "HTML guardado. El shell se genera en cada factura."})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
