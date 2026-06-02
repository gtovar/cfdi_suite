from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

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
