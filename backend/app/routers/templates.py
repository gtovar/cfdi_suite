from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from ..services.canvas_service import DEFAULT_COLUMNS, FIELD_ENUM

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
_DESIGN_DIR    = Path(__file__).parent.parent.parent / "templates" / "design"
_HTML_DIR      = Path(__file__).parent.parent.parent / "templates" / "html"
_DESIGN_DIR.mkdir(exist_ok=True)

# Identificador de plantilla válido (anti path-traversal). Case-insensitive para
# ids recibidos; los ids generados por _slugify siempre salen en minúsculas.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)

# ── Validación de design config (contrato Fase 0, sección 1.6) ──────────────────

_HEX_RE            = re.compile(r"^#[0-9A-Fa-f]{6}$")
_VALID_OPERATORS   = {"eq", "neq", "gt", "lt", "gte", "lte", "contains"}
_VALID_SCOPES      = {"cell", "row"}
_VALID_FORMATS     = {"text", "money"}
# PW = A4_width - 2*MARGIN = 595.2755... - 72 ≈ 523.28pt (canvas_service.PW).
_PAGE_WIDTH_LIMIT  = 523.28

# Etiquetas amigables por field (fuente de verdad para el catálogo del frontend).
_FIELD_LABELS = {
    "num_id":         "No. de identificación",
    "cantidad":       "Cantidad",
    "clave_unidad":   "Unidad",
    "descripcion":    "Descripción",
    "valor_unitario": "Precio unitario",
    "descuento":      "Descuento",
    "importe":        "Importe",
}


def _check_color(value, where: str) -> None:
    if value is None:
        return
    if not (isinstance(value, str) and _HEX_RE.match(value)):
        raise HTTPException(status_code=400, detail=f"Color inválido en {where}: {value!r} (esperado #RRGGBB)")


def _validate_columns(columns) -> None:
    if not isinstance(columns, list) or not columns:
        raise HTTPException(status_code=400, detail="tabla.columns debe ser una lista no vacía")
    ids: list = []
    visible_count = 0
    width_sum = 0.0
    for c in columns:
        if not isinstance(c, dict):
            raise HTTPException(status_code=400, detail="Cada columna debe ser un objeto")
        cid = c.get("id")
        if not cid:
            raise HTTPException(status_code=400, detail="Cada columna requiere un 'id'")
        ids.append(cid)
        if c.get("field") not in FIELD_ENUM:
            raise HTTPException(status_code=400, detail=f"field inválido: {c.get('field')!r}")
        if c.get("format", "text") not in _VALID_FORMATS:
            raise HTTPException(status_code=400, detail=f"format inválido: {c.get('format')!r}")
        try:
            width = float(c.get("width"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"width inválido en columna {cid!r}")
        if width <= 0:
            raise HTTPException(status_code=400, detail=f"width debe ser > 0 en columna {cid!r}")
        if c.get("visible", True):
            visible_count += 1
            width_sum += width
        _check_color(c.get("color"), f"columna {cid!r}")
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="Los 'id' de columna deben ser únicos")
    if visible_count < 1:
        raise HTTPException(status_code=400, detail="Debe haber al menos 1 columna visible")
    if width_sum > _PAGE_WIDTH_LIMIT + 1e-6:
        raise HTTPException(
            status_code=400,
            detail=f"La suma de anchos visibles ({width_sum:.2f}pt) supera {_PAGE_WIDTH_LIMIT}pt",
        )


def _validate_rules(reglas, columns) -> None:
    if not isinstance(reglas, list):
        raise HTTPException(status_code=400, detail="tabla.reglas debe ser una lista")
    if not (1 <= len(reglas) <= 3):
        raise HTTPException(status_code=400, detail="Debe haber entre 1 y 3 reglas")
    # Set de fields existentes y su format (para referencia y contains-sobre-money).
    if columns:
        field_set = {c.get("field") for c in columns}
        fmt_by_field = {c.get("field"): c.get("format", "text") for c in columns}
    else:
        field_set = set(FIELD_ENUM)
        fmt_by_field = {}
    for r in reglas:
        if not isinstance(r, dict):
            raise HTTPException(status_code=400, detail="Cada regla debe ser un objeto")
        op = r.get("operador")
        if op not in _VALID_OPERATORS:
            raise HTTPException(status_code=400, detail=f"operador inválido: {op!r}")
        if r.get("scope", "cell") not in _VALID_SCOPES:
            raise HTTPException(status_code=400, detail=f"scope inválido: {r.get('scope')!r}")
        columna = r.get("columna")
        if columna not in field_set:
            raise HTTPException(status_code=400, detail=f"La regla referencia una columna inexistente: {columna!r}")
        _check_color((r.get("estilo") or {}).get("color"), "estilo de regla")
        if (r.get("estilo") or {}).get("color") is None:
            raise HTTPException(status_code=400, detail="Cada regla requiere estilo.color")
        if op == "contains" and fmt_by_field.get(columna) == "money":
            raise HTTPException(status_code=400, detail="El operador 'contains' no aplica a columnas de dinero")


def _validate_design(body) -> None:
    """Valida un design config antes de escribirlo. Lanza HTTPException(400)."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="El cuerpo debe ser un objeto JSON")

    brand = body.get("brand") or {}
    _check_color(brand.get("color"), "brand.color")
    _check_color(brand.get("accent"), "brand.accent")

    tabla = body.get("tabla") or {}
    _check_color(tabla.get("header_bg"), "tabla.header_bg")
    _check_color(tabla.get("even_bg"), "tabla.even_bg")
    _check_color(tabla.get("border"), "tabla.border")

    columns = tabla.get("columns")
    reglas  = tabla.get("reglas")

    sv = body.get("schema_version", 1)
    is_v2 = isinstance(sv, (int, float)) and not isinstance(sv, bool) and sv >= 2

    # v2 sin columns → error (no fallback silencioso). Contrato 1.5.
    if is_v2 and columns is None:
        raise HTTPException(status_code=400, detail="schema_version>=2 requiere tabla.columns")

    if columns is not None:
        _validate_columns(columns)
    if reglas is not None:
        _validate_rules(reglas, columns)

    # Metadata Fase 4 (opcional). _validate_design ignora campos desconocidos,
    # pero si estos vienen deben tener el tipo correcto.
    if "nombre" in body:
        nombre = body.get("nombre")
        if not (isinstance(nombre, str) and nombre.strip()):
            raise HTTPException(status_code=400, detail="'nombre' debe ser una cadena no vacía")
    if "es_referencia" in body and not isinstance(body.get("es_referencia"), bool):
        raise HTTPException(status_code=400, detail="'es_referencia' debe ser booleano")


# ── Helpers Fase 4 (CRUD de plantillas design) ─────────────────────────────────

def _validate_id_or_400(template_id: str) -> None:
    """Rechaza ids con path-traversal o caracteres inválidos (400) antes de tocar disco."""
    if not isinstance(template_id, str) or not _ID_RE.match(template_id):
        raise HTTPException(status_code=400, detail=f"Identificador de plantilla inválido: {template_id!r}")


def _slugify(nombre: str) -> str:
    """Convierte un nombre visible a un id seguro [a-z0-9-]. Nunca vacío."""
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "plantilla"


def _unique_design_id(slug: str) -> str:
    """Devuelve un id que NO existe en design/ (sufijo -2, -3, … ante colisión)."""
    if not (_DESIGN_DIR / f"{slug}.json").exists():
        return slug
    i = 2
    while (_DESIGN_DIR / f"{slug}-{i}.json").exists():
        i += 1
    return f"{slug}-{i}"


def _create_from_base(base_id: str, nombre: str) -> str:
    """
    Copia design/{base_id}.json (y html/{base_id}.html si existe) a un id nuevo,
    seteando nombre y es_referencia=False. Devuelve el nuevo id. Nunca pisa un
    archivo existente: el id se genera verificando no-existencia antes de escribir.
    """
    base_path = _DESIGN_DIR / f"{base_id}.json"
    if not base_path.exists():
        raise HTTPException(status_code=404, detail=f"Plantilla base no encontrada: {base_id!r}")
    data = json.loads(base_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="La plantilla base no es un objeto JSON válido")

    new_id = _unique_design_id(_slugify(nombre))
    data["nombre"] = nombre
    data["es_referencia"] = False

    (_DESIGN_DIR / f"{new_id}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    base_html = _HTML_DIR / f"{base_id}.html"
    if base_html.exists():
        _HTML_DIR.mkdir(parents=True, exist_ok=True)
        (_HTML_DIR / f"{new_id}.html").write_text(
            base_html.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return new_id


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


@router.get("/api/templates/design-defaults")
async def design_defaults() -> JSONResponse:
    """
    Catálogo canónico de las 7 columnas default + enums (fuente de verdad que el
    frontend consume en Fase 3). Debe registrarse ANTES de /{template_id} para no
    ser capturado por el path param.
    """
    return JSONResponse({
        "columns": DEFAULT_COLUMNS,
        "field_labels": _FIELD_LABELS,
        "operators": sorted(_VALID_OPERATORS),
        "scopes": sorted(_VALID_SCOPES),
        "formats": sorted(_VALID_FORMATS),
        "page_width_limit": _PAGE_WIDTH_LIMIT,
        "max_reglas": 3,
    })


# ==============================================================================
# CRUD de plantillas design (Fase 4). Las rutas fijas /designs DEBEN declararse
# ANTES de las paramétricas /{template_id}, o FastAPI captura "designs" como
# template_id (p.ej. POST /api/templates/designs caería en save_template).
# ==============================================================================

@router.get("/api/templates/designs")
async def list_designs() -> JSONResponse:
    """Lista las plantillas design en disco: [{id, nombre, es_referencia}]."""
    items = []
    for path in sorted(_DESIGN_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue  # JSON corrupto: saltar sin romper el listado.
        if not isinstance(data, dict):
            continue
        tid = path.stem
        nombre = data.get("nombre")
        if not (isinstance(nombre, str) and nombre.strip()):
            nombre = tid
        es_ref = data.get("es_referencia")
        if not isinstance(es_ref, bool):
            es_ref = False
        items.append({"id": tid, "nombre": nombre, "es_referencia": es_ref})
    # default primero; el resto alfabético por nombre (case-insensitive).
    items.sort(key=lambda x: (x["id"] != "default", x["nombre"].lower()))
    return JSONResponse(items)


@router.post("/api/templates/designs")
async def create_design(request: Request) -> JSONResponse:
    """Crea una plantilla nueva a partir de una base (default por defecto)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="El cuerpo debe ser JSON válido")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="El cuerpo debe ser un objeto JSON")

    nombre = body.get("nombre")
    if not (isinstance(nombre, str) and nombre.strip()):
        raise HTTPException(status_code=400, detail="El campo 'nombre' es requerido")
    nombre = nombre.strip()

    base_id = body.get("base_id", "default")
    if base_id is None:
        base_id = "default"
    if not isinstance(base_id, str):
        raise HTTPException(status_code=400, detail="'base_id' debe ser una cadena")
    _validate_id_or_400(base_id)

    new_id = _create_from_base(base_id, nombre)
    return JSONResponse(status_code=201, content={"id": new_id, "nombre": nombre, "es_referencia": False})


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


@router.post("/api/templates/{template_id}/table-preview")
async def table_preview(template_id: str, request: Request):
    """
    Preview REAL de la tabla de conceptos con el motor de producción.

    Recibe `{ design_config, n_rows?, con_descuento? }` con el design_config que el
    usuario edita EN MEMORIA (aún no guardado en disco — mismo patrón que
    shell-preview). Genera datos de ejemplo y los renderiza con el MISMO
    generate_from_data que usa producción, inyectando ese design_config. Así el
    preview es idéntico por construcción a lo que se generará con datos reales.
    """
    try:
        body = await request.json()
        design_config = body.get("design_config")
        if design_config is None:
            raise HTTPException(status_code=400, detail="Falta 'design_config' en el body")
        # Defensa en profundidad: es input de usuario, mismo validador que al guardar.
        _validate_design(design_config)

        try:
            n_rows = int(body.get("n_rows", 6))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="n_rows debe ser un entero")
        if not (1 <= n_rows <= 50):
            raise HTTPException(status_code=400, detail="n_rows debe estar entre 1 y 50")
        con_descuento = bool(body.get("con_descuento", True))

        import asyncio
        from ..services.pdf_pipeline import generate_from_data
        from ..services.sample_data import generar_datos_ejemplo

        cfdi_data, rows = generar_datos_ejemplo(n_rows, con_descuento)
        pdf_bytes = await asyncio.to_thread(
            generate_from_data,
            cfdi_data, rows,
            template_id=template_id,
            html_shell=None,
            design_config=design_config,
        )
        return Response(content=pdf_bytes, media_type="application/pdf")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/templates/{template_id}/design")
async def get_design_config(template_id: str):
    path = _DESIGN_DIR / f"{template_id}.json"
    if not path.exists():
        return JSONResponse({})
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@router.put("/api/templates/{template_id}/design")
async def save_design_config(template_id: str, request: Request):
    try:
        body = await request.json()
        _validate_design(body)
        path = _DESIGN_DIR / f"{template_id}.json"
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        return JSONResponse({"status": "ok"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/templates/{template_id}/duplicate")
async def duplicate_design(template_id: str, request: Request) -> JSONResponse:
    """Duplica una plantilla design. El duplicado SIEMPRE sale con es_referencia=False."""
    _validate_id_or_400(template_id)
    src = _DESIGN_DIR / f"{template_id}.json"
    if not src.exists():
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    nombre = body.get("nombre")
    if isinstance(nombre, str) and nombre.strip():
        nombre = nombre.strip()
    else:
        try:
            src_data = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            src_data = {}
        orig = src_data.get("nombre") if isinstance(src_data, dict) else None
        if not (isinstance(orig, str) and orig.strip()):
            orig = template_id
        nombre = f"{orig} (copia)"

    new_id = _create_from_base(template_id, nombre)
    return JSONResponse(status_code=201, content={"id": new_id, "nombre": nombre, "es_referencia": False})


@router.delete("/api/templates/{template_id}")
async def delete_design(template_id: str) -> JSONResponse:
    """Borra design/{id}.json y html/{id}.html. Prohibido para default y referencias."""
    _validate_id_or_400(template_id)
    if template_id == "default":
        raise HTTPException(status_code=400, detail="No se puede eliminar la plantilla 'default'")

    path = _DESIGN_DIR / f"{template_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if isinstance(data, dict) and data.get("es_referencia") is True:
        raise HTTPException(status_code=400, detail="No se puede eliminar una plantilla de referencia")

    path.unlink()
    html_path = _HTML_DIR / f"{template_id}.html"
    if html_path.exists():
        html_path.unlink()
    return JSONResponse({"status": "ok"})


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
