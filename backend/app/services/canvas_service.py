"""
canvas_service.py — Motor rl_canvas page-streaming para conceptos y footer.

Arquitectura: escribe páginas directo al stream PDF sin árbol en memoria (O(N)).
Para N > 2000 divide en chunks (mismas funciones, spawn-safe si algo externo
las llama vía multiprocessing) — el aislamiento por proceso ahora vive un
nivel arriba, en pdf_pipeline._POOL, que aísla el documento completo.
"""
from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

# ── Constantes de layout ──────────────────────────────────────────────────────

W, H = A4
MARGIN = 36.0
PW = W - 2 * MARGIN
ROW_H = 13.0
HDR_H = 16.0
MIN_Y = MARGIN + 20

COL_HEADERS = ["No.Id", "Cant", "Unidad", "Descripcion", "P.Unit", "Desc", "Importe"]
COL_WIDTHS  = [60.0, 28.0, 36.0, 175.0, 52.0, 42.0, 54.0]

C_HEADER_BG  = rl_colors.HexColor("#1A365D")
C_ACCENT     = rl_colors.HexColor("#2B6CB0")
C_EVEN_BG    = rl_colors.HexColor("#F8FAFC")
C_BORDER     = rl_colors.HexColor("#E2E8F0")
C_TEXT       = rl_colors.HexColor("#4A5568")
C_MUTED      = rl_colors.HexColor("#A0AEC0")
C_WHITE      = rl_colors.white
C_RED        = rl_colors.HexColor("#C53030")
C_DARK       = rl_colors.HexColor("#2D3748")
C_GREEN_BG   = rl_colors.HexColor("#F0FFF4")
C_GREEN_BORDER = rl_colors.HexColor("#9AE6B4")
C_GREEN_TEXT = rl_colors.HexColor("#276749")

_CHUNK_SIZE = 1000

_IMP_MAP      = {"001": "ISR", "002": "IVA", "003": "IEPS"}
_VERIFICA_URL = "https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx"

# ── Columnas configurables + reglas condicionales (Fase 1) ─────────────────────
#
# `field` es un enum cerrado: las 7 claves que produce parse_xml_to_rows variante
# ingreso. Fuente de verdad del catálogo canónico (endpoint /design-defaults y
# validación al guardar). No agregar claves sin actualizar parse_xml_to_rows.
FIELD_ENUM = (
    "num_id", "cantidad", "clave_unidad", "descripcion",
    "valor_unitario", "descuento", "importe",
)

# Catálogo canónico de las 7 columnas default (contrato Fase 0, sección 1.0).
# Reproduce byte-a-byte la semántica de COL_HEADERS/COL_WIDTHS + colores hardcode.
DEFAULT_COLUMNS = [
    {"id": "no_id",   "label": "No.Id",       "field": "num_id",         "width": 60.0,  "visible": True, "order": 0, "format": "text",  "color": "#4A5568", "emphasis": False},
    {"id": "cant",    "label": "Cant",        "field": "cantidad",       "width": 28.0,  "visible": True, "order": 1, "format": "text",  "color": "#4A5568", "emphasis": False},
    {"id": "unidad",  "label": "Unidad",      "field": "clave_unidad",   "width": 36.0,  "visible": True, "order": 2, "format": "text",  "color": "#4A5568", "emphasis": False},
    {"id": "desc",    "label": "Descripcion", "field": "descripcion",    "width": 175.0, "visible": True, "order": 3, "format": "text",  "color": "#4A5568", "emphasis": False},
    {"id": "punit",   "label": "P.Unit",      "field": "valor_unitario", "width": 52.0,  "visible": True, "order": 4, "format": "money", "color": "#4A5568", "emphasis": False},
    {"id": "descto",  "label": "Desc",        "field": "descuento",      "width": 42.0,  "visible": True, "order": 5, "format": "money", "color": "#C53030", "emphasis": False},
    {"id": "importe", "label": "Importe",     "field": "importe",        "width": 54.0,  "visible": True, "order": 6, "format": "money", "color": "#2D3748", "emphasis": True},
]

# Columnas legacy resueltas (fallback sin `columns`). Reproduce EXACTAMENTE el
# comportamiento actual: mismos anchos, colores por posición y truncado fijo
# (num_id[:11], resto[:24]). El truncado derivado del ancho aplica solo a v2.
_LEGACY_COLUMNS = [
    {"field": "num_id",         "label": "No.Id",       "width": 60.0,  "format": "text",  "color": C_TEXT, "emphasis": False, "max_chars": 11},
    {"field": "cantidad",       "label": "Cant",        "width": 28.0,  "format": "text",  "color": C_TEXT, "emphasis": False, "max_chars": 24},
    {"field": "clave_unidad",   "label": "Unidad",      "width": 36.0,  "format": "text",  "color": C_TEXT, "emphasis": False, "max_chars": 24},
    {"field": "descripcion",    "label": "Descripcion", "width": 175.0, "format": "text",  "color": C_TEXT, "emphasis": False, "max_chars": 24},
    {"field": "valor_unitario", "label": "P.Unit",      "width": 52.0,  "format": "money", "color": C_TEXT, "emphasis": False, "max_chars": 24},
    {"field": "descuento",      "label": "Desc",        "width": 42.0,  "format": "money", "color": C_RED,  "emphasis": False, "max_chars": 24},
    {"field": "importe",        "label": "Importe",     "width": 54.0,  "format": "money", "color": C_DARK, "emphasis": True,  "max_chars": 24},
]


# ── Operadores puros module-level (spawn-safe, NUNCA lanzan excepción) ──────────
#
# Semántica de coerción, contrato sección 1.4:
#   gt/lt/gte/lte → coaccionan ambos a float; si falla → no matchea (False).
#   eq/neq        → intentan numérico (así "0.00" eq "0" es True); si falla → string.
#   contains      → substring de strings.
# Toda evaluación corre dentro del worker spawn: cualquier excepción → False.

def _op_eq(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        try:
            return str(a) == str(b)
        except Exception:
            return False


def _op_neq(a, b) -> bool:
    try:
        return float(a) != float(b)
    except (TypeError, ValueError):
        try:
            return str(a) != str(b)
        except Exception:
            return False


def _op_gt(a, b) -> bool:
    try:
        return float(a) > float(b)
    except (TypeError, ValueError):
        return False


def _op_lt(a, b) -> bool:
    try:
        return float(a) < float(b)
    except (TypeError, ValueError):
        return False


def _op_gte(a, b) -> bool:
    try:
        return float(a) >= float(b)
    except (TypeError, ValueError):
        return False


def _op_lte(a, b) -> bool:
    try:
        return float(a) <= float(b)
    except (TypeError, ValueError):
        return False


def _op_contains(a, b) -> bool:
    try:
        return str(b) in str(a)
    except Exception:
        return False


_OPERATORS = {
    "eq": _op_eq, "neq": _op_neq, "gt": _op_gt, "lt": _op_lt,
    "gte": _op_gte, "lte": _op_lte, "contains": _op_contains,
}


def _resolve_columns(render_config: dict | None) -> list[dict]:
    """
    Devuelve la lista de columnas a dibujar (filtradas por visible, ordenadas por
    order). Con `tabla.columns` (v2) → columnas configuradas con truncado derivado
    del ancho. Sin `columns` (legacy) → constantes actuales, truncado fijo.
    Se llama UNA vez por chunk (gate de rendimiento, contrato 1.7).
    """
    cols = (render_config or {}).get("tabla", {}).get("columns")
    if not cols:
        return _LEGACY_COLUMNS
    visibles = [c for c in cols if c.get("visible", True)]
    visibles.sort(key=lambda c: c.get("order", 0))
    resolved = []
    for c in visibles:
        width = float(c.get("width", 0) or 0)
        resolved.append({
            "field":    c["field"],
            "label":    c.get("label", ""),
            "width":    width,
            "format":   c.get("format", "text"),
            "color":    rl_colors.HexColor(c.get("color", "#4A5568")),
            "emphasis": bool(c.get("emphasis", False)),
            # Helvetica 7pt ≈ 5.5pt/char. Truncado derivado del ancho real (v2).
            "max_chars": max(1, int(width / 5.5)),
        })
    return resolved


def _compile_rules(render_config: dict | None) -> list[dict]:
    """
    Compila `tabla.reglas` a predicados evaluables (op module-level + HexColor).
    Sin `reglas`:
      - v2 (con `columns`) → sin reglas.
      - legacy → regla implícita gris sobre descuento==0 scope cell (reproduce el
        hardcode 'Bug fix #4'; el rojo default lo aporta el color de la columna).
    Se llama UNA vez por chunk, del lado del worker (gate 1.7). Devuelve dicts con
    referencia a función pura (picklable) y HexColor ya construido.
    """
    tabla = (render_config or {}).get("tabla", {})
    reglas = tabla.get("reglas")
    if reglas is None:
        if tabla.get("columns"):
            return []
        return [{"columna": "descuento", "op": _op_eq, "valor": "0",
                 "scope": "cell", "color": C_MUTED}]
    compiled = []
    for r in reglas:
        op = _OPERATORS.get(r.get("operador"))
        if op is None:
            continue
        compiled.append({
            "columna": r.get("columna"),
            "op":      op,
            "valor":   r.get("valor", ""),
            "scope":   r.get("scope", "cell"),
            "color":   rl_colors.HexColor((r.get("estilo") or {}).get("color", "#000000")),
        })
    return compiled


def _match_rules(rules: list[dict], row: dict) -> list[dict]:
    """Evalúa la condición de cada regla UNA vez por fila (≤3). Pura, spawn-safe."""
    return [r for r in rules if r["op"](row.get(r["columna"]), r["valor"])]


def _cell_color(field: str, default_color, matched: list[dict]):
    """
    Precedencia por celda (contrato 1.3): primera regla ya-matcheada cuyo scope
    cubre esta celda (row = toda la fila; cell = solo la celda de su columna).
    Si ninguna cubre → color default de la columna. Pura, spawn-safe.
    """
    for r in matched:
        if r["scope"] == "row" or r["columna"] == field:
            return r["color"]
    return default_color


def _prepare_render(render_config: dict | None):
    """Prepara todo lo derivado de la config UNA vez por chunk (gate 1.7)."""
    tabla   = (render_config or {}).get("tabla", {})
    columns = _resolve_columns(render_config)
    rules   = _compile_rules(render_config)
    row_h   = {"compact": 11.0, "normal": 13.0, "comfortable": 16.0}.get(
        tabla.get("density", "normal"), ROW_H)
    even_bg = rl_colors.HexColor(tabla.get("even_bg",   "#F8FAFC"))
    border  = rl_colors.HexColor(tabla.get("border",    "#E2E8F0"))
    hdr_bg  = rl_colors.HexColor(tabla.get("header_bg", "#1A365D"))
    return columns, rules, row_h, even_bg, border, hdr_bg


def _fmt_mxn(v: str) -> str:
    """'117.9893' → '117.99'. Seguro ante None o cadena vacía."""
    try:
        return f"{float(v):.2f}"
    except (ValueError, TypeError):
        return str(v or "0")

# Altura del card de encabezado (calculada para emisor/receptor/datos/total en 2 cols)
_CARD_H = 148.0
_CARD_PADDING = 10.0


# ── Header card (dibujado en la primera página junto con la tabla) ─────────────

def _draw_card_header(cv, y: float, cfdi_data: dict) -> float:
    """
    Dibuja el card de encabezado (emisor, receptor, datos, total) en la página
    actual y devuelve el Y después del card.
    Spawn-safe: no closures, solo primitivos.
    """
    card_top = y
    card_bot = y - _CARD_H

    # Borde del card
    cv.setStrokeColor(C_BORDER)
    cv.setFillColor(C_WHITE)
    cv.rect(MARGIN, card_bot, PW, _CARD_H, fill=1, stroke=1)

    # Barra de acento superior (4pt)
    cv.setFillColor(C_HEADER_BG)
    cv.rect(MARGIN, card_top - 4, PW, 4, fill=1, stroke=0)

    # Título
    cv.setFont("Helvetica-Bold", 13)
    cv.setFillColor(C_HEADER_BG)
    cv.drawString(MARGIN + _CARD_PADDING, card_top - 20, "COMPROBANTE FISCAL DIGITAL POR INTERNET")

    cv.setFont("Helvetica", 7)
    cv.setFillColor(C_MUTED)
    cv.drawString(MARGIN + _CARD_PADDING, card_top - 30, "CFDI 4.0  —  REPRESENTACIÓN IMPRESA")

    # Línea separadora bajo título
    cv.setStrokeColor(C_BORDER)
    cv.line(MARGIN + _CARD_PADDING, card_top - 36, MARGIN + PW - _CARD_PADDING, card_top - 36)

    half = PW / 2

    def section_title(text, x, y_):
        cv.setFont("Helvetica-Bold", 7)
        cv.setFillColor(C_ACCENT)
        cv.drawString(x, y_, text.upper())

    def field(label, value, x, y_):
        cv.setFont("Helvetica-Bold", 7)
        cv.setFillColor(C_TEXT)
        cv.drawString(x, y_, label)
        cv.setFont("Helvetica", 7)
        cv.setFillColor(C_DARK)
        cv.drawString(x + 30, y_, str(value or "")[:42])

    row1_y = card_top - 50
    # Emisor
    emisor = cfdi_data.get("emisor", {})
    section_title("Emisor", MARGIN + _CARD_PADDING, row1_y)
    cv.setFont("Helvetica-Bold", 8)
    cv.setFillColor(C_DARK)
    cv.drawString(MARGIN + _CARD_PADDING, row1_y - 11, str(emisor.get("nombre", ""))[:38])
    field("RFC:", emisor.get("rfc", ""), MARGIN + _CARD_PADDING, row1_y - 21)
    field("Rég:", emisor.get("regimen", ""), MARGIN + _CARD_PADDING, row1_y - 31)

    # Receptor
    receptor = cfdi_data.get("receptor", {})
    section_title("Receptor", MARGIN + half, row1_y)
    cv.setFont("Helvetica-Bold", 8)
    cv.setFillColor(C_DARK)
    cv.drawString(MARGIN + half, row1_y - 11, str(receptor.get("nombre", ""))[:38])
    field("RFC:", receptor.get("rfc", ""), MARGIN + half, row1_y - 21)
    field("Uso:", receptor.get("uso", ""), MARGIN + half, row1_y - 31)

    # Línea separadora de fila
    sep_y = row1_y - 40
    cv.setStrokeColor(C_BORDER)
    cv.line(MARGIN + _CARD_PADDING, sep_y, MARGIN + PW - _CARD_PADDING, sep_y)

    row2_y = sep_y - 12
    totales = cfdi_data.get("totales", {})

    # Datos del comprobante
    section_title("Datos del Comprobante", MARGIN + _CARD_PADDING, row2_y)
    field("Fecha:", cfdi_data.get("fecha", ""), MARGIN + _CARD_PADDING, row2_y - 11)
    serie  = cfdi_data.get("serie", "")
    folio  = cfdi_data.get("folio", "")
    field("Folio:", f"{serie}/{folio}" if serie else folio, MARGIN + _CARD_PADDING, row2_y - 21)
    field("Moneda:", cfdi_data.get("moneda", "MXN"), MARGIN + _CARD_PADDING, row2_y - 31)

    # Total (badge verde)
    section_title("Total", MARGIN + half, row2_y)
    total_str = f'{cfdi_data.get("moneda","MXN")} ${totales.get("total","")}'
    badge_x = MARGIN + half
    badge_y = row2_y - 25
    badge_w = min(len(total_str) * 6.5 + 12, half - 10)
    cv.setFillColor(C_GREEN_BG)
    cv.setStrokeColor(C_GREEN_BORDER)
    cv.rect(badge_x, badge_y - 4, badge_w, 16, fill=1, stroke=1)
    cv.setFont("Helvetica-Bold", 9)
    cv.setFillColor(C_GREEN_TEXT)
    cv.drawString(badge_x + 5, badge_y + 1, total_str)

    sub = totales.get("subtotal", "")
    if sub:
        cv.setFont("Helvetica", 7)
        cv.setFillColor(C_TEXT)
        cv.drawString(badge_x, row2_y - 36, f"Subtotal: ${sub}")

    return card_bot - 10  # Y después del card + espacio


# ── Tabla de conceptos ────────────────────────────────────────────────────────

def _draw_table_header(cv, y: float, columns: list[dict], hdr_bg) -> float:
    cv.setFillColor(hdr_bg)
    cv.rect(MARGIN, y - HDR_H, PW, HDR_H, fill=1, stroke=0)
    cv.setFillColor(C_WHITE)
    cv.setFont("Helvetica-Bold", 7)
    x = MARGIN
    for col in columns:
        cv.drawString(x + 3, y - HDR_H + 5, col["label"])
        x += col["width"]
    return y - HDR_H


def _draw_data_row(cv, y: float, row: dict, idx: int,
                   columns: list[dict], rules: list[dict],
                   row_h: float, even_bg, border) -> float:
    if idx % 2 == 0:
        cv.setFillColor(even_bg)
        cv.rect(MARGIN, y - row_h, PW, row_h, fill=1, stroke=0)
    cv.setStrokeColor(border)
    cv.rect(MARGIN, y - row_h, PW, row_h, fill=0, stroke=1)

    # Reglas: se evalúa cada condición UNA vez por fila (≤3), luego selección
    # barata por celda. Sin json.loads / re.compile / construcción de config aquí
    # (todo ya compilado por chunk en _prepare_render — gate de rendimiento 1.7).
    matched = _match_rules(rules, row)

    x = MARGIN
    for col in columns:
        field = col["field"]
        raw = str(row.get(field, "") or "")
        # format:"money" = anteponer '$' sin reformatear (ya viene a 2 decimales).
        disp = ("$" + (raw or "0")) if col["format"] == "money" else raw
        disp = disp[:col["max_chars"]]

        # Precedencia por celda (contrato 1.3).
        color = _cell_color(field, col["color"], matched)
        cv.setFillColor(color)
        cv.setFont("Helvetica-Bold" if col["emphasis"] else "Helvetica", 7)
        cv.drawString(x + 3, y - row_h + 4, disp)
        x += col["width"]
    return y - row_h


# ── Footer inline (spawn-safe) ────────────────────────────────────────────────

_FOOTER_MIN_H = 220.0  # espacio mínimo para footer + QR 65pt


def _draw_qr(cv, x: float, y_top: float, url: str, size: float = 65.0) -> None:
    """Dibuja QR de verificación SAT. Spawn-safe. qrcode es dep transitiva de satcfdi."""
    import qrcode as _qrcode
    from reportlab.lib.utils import ImageReader

    qr = _qrcode.QRCode(version=1, error_correction=_qrcode.constants.ERROR_CORRECT_M,
                         box_size=4, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    cv.drawImage(ImageReader(buf), x, y_top - size, width=size, height=size)


def _draw_footer_content(cv, y: float, cfdi_data: dict, render_config=None) -> None:
    """Dibuja el contenido del footer a partir de y. Spawn-safe."""
    rc          = render_config or {}
    c_cfg       = rc.get('cierre', {})
    brand_hex   = rc.get('brand', {}).get('color', '#1A365D')
    c_brand     = rl_colors.HexColor(brand_hex)
    show_uuid            = c_cfg.get('show_uuid', True)
    show_fecha_timbrado  = c_cfg.get('show_fecha_timbrado', True)
    show_disclaimer      = c_cfg.get('show_disclaimer', True)

    def lbl(text, x, yy, bold=False, size=8):
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        cv.setFillColor(C_DARK)
        cv.drawString(x, yy, text)

    def hr(yy):
        cv.setStrokeColor(C_BORDER)
        cv.line(MARGIN, yy, MARGIN + PW, yy)

    y -= 10
    hr(y)
    y -= 16

    totales  = cfdi_data.get("totales", {})
    subtotal = totales.get("subtotal", "")
    desc     = totales.get("descuento", "0") or "0"
    total    = totales.get("total", "")
    moneda   = cfdi_data.get("moneda", "MXN")

    col_label = MARGIN + PW - 200
    col_value = MARGIN + PW - 8

    def money_row(label, value, yy, bold=False, color=None):
        lbl(label, col_label, yy, bold=bold)
        cv.setFillColor(color if color else C_DARK)
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", 8)
        cv.drawRightString(col_value, yy, value)

    lbl(f"Moneda: {cfdi_data.get('moneda_desc', '') or moneda}", MARGIN, y)
    y -= 14

    if subtotal:
        money_row("Subtotal:", f"${subtotal}", y)
        y -= 13

    if desc not in ("0", "0.0", "0.00", "0.000000"):
        money_row("Descuento:", f"-${desc}", y, color=C_RED)
        y -= 13

    for imp in cfdi_data.get("impuestos", []):
        nombre = imp.get("nombre", "")
        monto  = imp.get("importe", "")
        tasa   = imp.get("tasa", "")
        label  = f"{nombre}{f' {float(tasa)*100:.0f}%' if tasa else ''}:"
        if monto:
            money_row(label, f"${monto}", y)
            y -= 13

    for ret in cfdi_data.get("retenciones", []):
        nombre = ret.get("nombre", "")
        monto  = ret.get("importe", "")
        if monto:
            money_row(f"Ret. {nombre}:", f"-${monto}", y, color=C_RED)
            y -= 13

    hr(y + 4)
    y -= 4
    cv.setFillColor(c_brand)
    cv.rect(col_label - 8, y - 6, PW - (col_label - 8 - MARGIN), 18, fill=1, stroke=0)
    cv.setFont("Helvetica-Bold", 11)
    cv.setFillColor(C_WHITE)
    cv.drawString(col_label, y + 4, "TOTAL:")
    cv.drawRightString(col_value, y + 4, f"${total}")
    y -= 22

    hr(y)
    y -= 16

    timbre       = cfdi_data.get("timbre") or {}
    uuid         = timbre.get("uuid", "")
    verifica_url = cfdi_data.get("verifica_url", "")

    if uuid and show_uuid:
        qr_size    = 65.0
        qr_x       = MARGIN + PW - qr_size - 4
        block_top  = y  # Y al inicio del bloque UUID — ancla del QR

        lbl("Folio Fiscal (UUID):", MARGIN, y, bold=True, size=7)
        y -= 11
        cv.setFont("Helvetica", 7)
        cv.setFillColor(C_TEXT)
        cv.drawString(MARGIN, y, uuid)
        y -= 13

        fecha_t = timbre.get("fecha_timbrado", "")
        no_cert = timbre.get("no_cert_sat", "")
        if fecha_t and show_fecha_timbrado:
            cv.drawString(MARGIN, y, f"Fecha Timbrado: {fecha_t}")
            y -= 10
            cv.drawString(MARGIN, y, f"No. Cert. SAT: {no_cert}")
            y -= 14

        if verifica_url:
            _draw_qr(cv, qr_x, block_top, verifica_url, size=qr_size)
            # Bajar Y si el texto no alcanzó la parte inferior del QR
            qr_bottom = block_top - qr_size
            if y > qr_bottom:
                y = qr_bottom

    hr(y)
    y -= 12
    if show_disclaimer:
        cv.setFont("Helvetica", 6)
        cv.setFillColor(C_MUTED)
        cv.drawCentredString(MARGIN + PW / 2, y, "Este documento es una representación impresa de un CFDI.")


# ── Chunks de renderizado (spawn-safe) ────────────────────────────────────────

def _render_chunk(rows: list[dict], start_idx: int = 0, render_config=None) -> bytes:
    """Páginas de conceptos sin header card. Spawn-safe."""
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    columns, rules, row_h, even_bg, border, hdr_bg = _prepare_render(render_config)
    y = H - MARGIN
    y = _draw_table_header(cv, y, columns, hdr_bg)

    for idx, row in enumerate(rows):
        if y - row_h < MIN_Y:
            cv.showPage()
            y = H - MARGIN
            y = _draw_table_header(cv, y, columns, hdr_bg)
        y = _draw_data_row(cv, y, row, start_idx + idx, columns, rules, row_h, even_bg, border)

    cv.save()
    return buf.getvalue()


def _render_last_chunk(rows: list[dict], start_idx: int, cfdi_data: dict, render_config=None) -> bytes:
    """Último chunk: conceptos + footer inline en la misma página si cabe. Spawn-safe."""
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    columns, rules, row_h, even_bg, border, hdr_bg = _prepare_render(render_config)
    y = H - MARGIN
    y = _draw_table_header(cv, y, columns, hdr_bg)

    for idx, row in enumerate(rows):
        if y - row_h < MIN_Y:
            cv.showPage()
            y = H - MARGIN
            y = _draw_table_header(cv, y, columns, hdr_bg)
        y = _draw_data_row(cv, y, row, start_idx + idx, columns, rules, row_h, even_bg, border)

    # Si no cabe el footer en el espacio restante, nueva página
    if y - _FOOTER_MIN_H < MIN_Y:
        cv.showPage()
        y = H - MARGIN

    _draw_footer_content(cv, y, cfdi_data, render_config)
    cv.save()
    return buf.getvalue()


def _render_first_chunk(
    rows: list[dict],
    cfdi_data: dict,
    skip_header_card: bool = False,
    header_reserve: float = 0.0,
    render_config=None,
) -> bytes:
    """Primera página: card de encabezado (opcional) + tabla. Spawn-safe."""
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    columns, rules, row_h, even_bg, border, hdr_bg = _prepare_render(render_config)
    if not skip_header_card:
        y = H - MARGIN
        y = _draw_card_header(cv, y, cfdi_data)
    else:
        # Reserva espacio para el header HTML estampado encima
        y = H - header_reserve if header_reserve > 0 else H - MARGIN
    y = _draw_table_header(cv, y, columns, hdr_bg)

    for idx, row in enumerate(rows):
        if y - row_h < MIN_Y:
            cv.showPage()
            y = H - MARGIN
            y = _draw_table_header(cv, y, columns, hdr_bg)
        y = _draw_data_row(cv, y, row, idx, columns, rules, row_h, even_bg, border)

    cv.save()
    return buf.getvalue()


def _render_single(
    rows: list[dict],
    cfdi_data: dict,
    skip_header_card: bool = False,
    header_reserve: float = 0.0,
    render_config=None,
) -> bytes:
    """Caso N <= 2000: header (opcional) + conceptos + footer en un solo canvas. Spawn-safe."""
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    columns, rules, row_h, even_bg, border, hdr_bg = _prepare_render(render_config)
    if not skip_header_card:
        y = H - MARGIN
        y = _draw_card_header(cv, y, cfdi_data)
    else:
        y = H - header_reserve if header_reserve > 0 else H - MARGIN
    y = _draw_table_header(cv, y, columns, hdr_bg)

    for idx, row in enumerate(rows):
        if y - row_h < MIN_Y:
            cv.showPage()
            y = H - MARGIN
            y = _draw_table_header(cv, y, columns, hdr_bg)
        y = _draw_data_row(cv, y, row, idx, columns, rules, row_h, even_bg, border)

    if y - _FOOTER_MIN_H < MIN_Y:
        cv.showPage()
        y = H - MARGIN

    _draw_footer_content(cv, y, cfdi_data, render_config)
    cv.save()
    return buf.getvalue()


def _merge_pdfs(pdf_list: list[bytes]) -> bytes:
    writer = PdfWriter()
    for pdf_bytes in pdf_list:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ── API pública ───────────────────────────────────────────────────────────────

def render_conceptos(
    rows: list[dict],
    cfdi_data: dict,
    workers: int | None = None,
    skip_header_card: bool = False,
    header_reserve: float = 0.0,
    render_config: dict | None = None,
) -> bytes:
    """
    Genera el PDF de conceptos + footer inline.

    skip_header_card=True + header_reserve=Xpt: reserva X puntos en el tope de página 1
    para que el header HTML se estampe encima sin solaparse con la tabla.
    N <= 2000: single-process.  N > 2000: chunks en paralelo.
    render_config: dict con primitivos (hex strings, bools) — spawn-safe.
    """
    if len(rows) <= 2000:
        return _render_single(
            rows, cfdi_data,
            skip_header_card=skip_header_card,
            header_reserve=header_reserve,
            render_config=render_config,
        )

    chunks = [rows[i:i + _CHUNK_SIZE] for i in range(0, len(rows), _CHUNK_SIZE)]
    starts = [i * _CHUNK_SIZE for i in range(len(chunks))]

    # 2026-07-11: ya NO se crea un ProcessPoolExecutor aquí. Desde que
    # pdf_pipeline.generate() completo corre aislado en su propio proceso
    # (ver pdf_pipeline._POOL / pdf.py internal_generate_pdf), esta función
    # ya se ejecuta DENTRO de un worker — anidar otro pool de procesos ahí
    # es frágil (workers no siempre pueden tener hijos) y ya no hace falta
    # para el problema que resolvía originalmente (gRPC+fork, ver historia
    # de este archivo): ese proceso ya está aislado del principal.
    # Costo real de este cambio: un solo documento con miles de conceptos
    # ya no reparte sus propios chunks entre varios núcleos — los renderiza
    # uno tras otro dentro de su worker. Los documentos grandes tardan más
    # individualmente; el throughput del batch completo no baja igual,
    # porque varios documentos distintos siguen renderizándose en paralelo
    # entre sí (cada uno en su propio worker del pool persistente).
    pdfs = [_render_first_chunk(chunks[0], cfdi_data, skip_header_card, header_reserve, render_config)]
    for chunk, start in zip(chunks[1:-1], starts[1:-1]):
        pdfs.append(_render_chunk(chunk, start, render_config))
    if len(chunks) > 1:
        pdfs.append(_render_last_chunk(chunks[-1], starts[-1], cfdi_data, render_config))

    return _merge_pdfs(pdfs)


def render_footer(cfdi_data: dict) -> bytes:
    """
    Genera el PDF del footer: totales consolidados, UUID, nota al pie.
    Sin QR ni sellos por ahora.
    """
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    y = H - MARGIN

    def lbl(text: str, x: float, yy: float, bold: bool = False, size: int = 8) -> None:
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        cv.setFillColor(C_DARK)
        cv.drawString(x, yy, text)

    def hr(yy: float) -> None:
        cv.setStrokeColor(C_BORDER)
        cv.line(MARGIN, yy, MARGIN + PW, yy)

    hr(y)
    y -= 16

    totales  = cfdi_data.get("totales", {})
    subtotal = totales.get("subtotal", "")
    desc     = totales.get("descuento", "0") or "0"
    total    = totales.get("total", "")
    moneda   = cfdi_data.get("moneda", "MXN")

    col_label = MARGIN + PW - 200
    col_value = MARGIN + PW - 60

    def money_row(label, value, yy, bold=False, color=None):
        lbl(label, col_label, yy, bold=bold)
        if color:
            cv.setFillColor(color)
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", 8)
        cv.drawRightString(col_value, yy, value)

    lbl(f"Moneda: {cfdi_data.get('moneda_desc', '') or moneda}", MARGIN, y)
    y -= 14

    if subtotal:
        money_row("Subtotal:", f"${subtotal}", y)
        y -= 13

    if desc not in ("0", "0.0", "0.00", "0.000000"):
        money_row("Descuento:", f"-${desc}", y, color=C_RED)
        y -= 13

    for imp in cfdi_data.get("impuestos", []):
        nombre = imp.get("nombre", "")
        monto  = imp.get("importe", "")
        tasa   = imp.get("tasa", "")
        label  = f"{nombre}{f' {float(tasa)*100:.0f}%' if tasa else ''}:"
        if monto:
            money_row(label, f"${monto}", y)
            y -= 13

    for ret in cfdi_data.get("retenciones", []):
        nombre = ret.get("nombre", "")
        monto  = ret.get("importe", "")
        if monto:
            money_row(f"Ret. {nombre}:", f"-${monto}", y, color=C_RED)
            y -= 13

    hr(y + 4)
    y -= 4
    # Fila de total
    cv.setFillColor(C_HEADER_BG)
    cv.rect(col_label - 8, y - 6, PW - (col_label - 8 - MARGIN), 18, fill=1, stroke=0)
    cv.setFont("Helvetica-Bold", 11)
    cv.setFillColor(C_WHITE)
    cv.drawString(col_label, y + 4, "TOTAL:")
    cv.drawRightString(col_value, y + 4, f"${total}")
    y -= 22

    hr(y)
    y -= 16

    # Timbre
    timbre = cfdi_data.get("timbre", {})
    uuid   = timbre.get("uuid", "")
    fecha_t = timbre.get("fecha_timbrado", "")
    no_cert = timbre.get("no_cert_sat", "")

    if uuid:
        lbl("Folio Fiscal (UUID):", MARGIN, y, bold=True, size=7)
        y -= 11
        cv.setFont("Helvetica", 7)
        cv.setFillColor(C_TEXT)
        cv.drawString(MARGIN, y, uuid)
        y -= 13

    if fecha_t:
        cv.setFont("Helvetica", 7)
        cv.setFillColor(C_TEXT)
        cv.drawString(MARGIN, y, f"Fecha de Timbrado: {fecha_t}    No. Cert. SAT: {no_cert}")
        y -= 20

    hr(y)
    y -= 12

    cv.setFont("Helvetica", 6)
    cv.setFillColor(C_MUTED)
    cv.drawCentredString(MARGIN + PW / 2, y, "Este documento es una representación impresa de un CFDI.")

    cv.save()
    return buf.getvalue()


# ── Parseo XML — varios SAX, uno por variante ────────────────────────────────

def _detect_tipo(xml_bytes: bytes) -> str:
    """Lee solo el elemento raíz para obtener TipoDeComprobante. < 0.1ms."""
    from lxml import etree
    for _, el in etree.iterparse(io.BytesIO(xml_bytes), events=("start",), recover=True):
        local = etree.QName(el.tag).localname
        return el.get("TipoDeComprobante", "I") if local == "Comprobante" else local
    return "I"


def _build_verifica_url(meta: dict) -> str:
    """Computa la URL de verificación SAT con los campos ya extraídos."""
    timbre   = meta.get("timbre", {})
    emisor   = meta.get("emisor", {})
    receptor = meta.get("receptor", {})
    uuid     = timbre.get("uuid", "")
    if not uuid:
        return ""
    return (
        f"{_VERIFICA_URL}?id={uuid}"
        f"&re={emisor.get('rfc', '')}"
        f"&rr={receptor.get('rfc', '')}"
        f"&tt={meta.get('totales', {}).get('total', '')}"
        f"&fe={meta.pop('_sello_8', '')}"
    )


def _parse_ingreso_sax(xml_bytes: bytes) -> tuple[dict, list[dict]]:
    """SAX para TipoDeComprobante I / E / T y variantes con Conceptos estándar."""
    from lxml import etree
    from .catalogs import fmt_code, describe

    meta: dict      = {}
    rows: list      = []
    impuestos: list = []
    retenciones: list = []
    _in_concepto    = False

    for event, el in etree.iterparse(io.BytesIO(xml_bytes), events=("start", "end"), recover=True):
        local = etree.QName(el.tag).localname

        if event == "start":
            if local == "Comprobante":
                moneda = el.get("Moneda", "MXN")
                meta["fecha"]            = el.get("Fecha", "")
                meta["serie"]            = el.get("Serie", "")
                meta["folio"]            = el.get("Folio", "")
                meta["moneda"]           = moneda
                meta["forma_pago"]       = el.get("FormaPago", "")
                meta["metodo_pago"]      = el.get("MetodoPago", "")
                meta["lugar_expedicion"] = el.get("LugarExpedicion", "")
                meta["tipo_cambio"]      = el.get("TipoCambio", "")
                meta["_sello_8"]         = el.get("Sello", "")[-8:]
                meta["totales"]          = {
                    "subtotal":  _fmt_mxn(el.get("SubTotal", "0")),
                    "descuento": _fmt_mxn(el.get("Descuento", "0") or "0"),
                    "total":     _fmt_mxn(el.get("Total", "0")),
                }
            elif local == "Concepto":
                _in_concepto = True

        elif event == "end":
            if local == "Concepto":
                clave_prod = el.get("ClaveProdServ", "")
                no_ident   = el.get("NoIdentificacion", "") or ""
                clave_u    = el.get("ClaveUnidad", "")
                # No.Id: columna 60pt — solo el código (no la descripción larga)
                num_id = no_ident or clave_prod
                # Unidad: columna 36pt — solo la descripción ("Pieza") cabe; código si sin desc
                unidad_desc = describe("c_ClaveUnidad", clave_u)
                rows.append({
                    "num_id":         num_id,
                    "cantidad":       el.get("Cantidad", ""),
                    "clave_unidad":   unidad_desc or clave_u,
                    "descripcion":    el.get("Descripcion", ""),
                    "valor_unitario": _fmt_mxn(el.get("ValorUnitario", "0")),
                    "descuento":      _fmt_mxn(el.get("Descuento", "0") or "0"),
                    "importe":        _fmt_mxn(el.get("Importe", "0")),
                })
                el.clear()
                _in_concepto = False

            elif local == "Traslado" and not _in_concepto:
                imp_code = el.get("Impuesto", "")
                importe  = el.get("Importe", "")
                if importe:
                    impuestos.append({
                        "nombre":  _IMP_MAP.get(imp_code, imp_code),
                        "importe": _fmt_mxn(importe),
                        "tasa":    el.get("TasaOCuota", ""),
                    })

            elif local == "Retencion" and not _in_concepto:
                imp_code = el.get("Impuesto", "")
                importe  = el.get("Importe", "")
                if importe:
                    retenciones.append({
                        "nombre":  _IMP_MAP.get(imp_code, imp_code),
                        "importe": _fmt_mxn(importe),
                    })

            elif local == "Emisor":
                regimen = el.get("RegimenFiscal", "")
                meta["emisor"] = {
                    "nombre":       el.get("Nombre", ""),
                    "rfc":          el.get("Rfc", ""),
                    "regimen":      regimen,
                    "regimen_desc": fmt_code("c_RegimenFiscal", regimen),
                }

            elif local == "Receptor":
                uso      = el.get("UsoCFDI", "")
                regimen_r = el.get("RegimenFiscalReceptor", "")
                meta["receptor"] = {
                    "nombre":                    el.get("Nombre", ""),
                    "rfc":                       el.get("Rfc", ""),
                    "uso":                       uso,
                    "uso_desc":                  fmt_code("c_UsoCFDI", uso),
                    "domicilio_fiscal_receptor": el.get("DomicilioFiscalReceptor", ""),
                    "regimen_fiscal_receptor":   regimen_r,
                    "regimen_receptor_desc":     fmt_code("c_RegimenFiscal", regimen_r),
                }

            elif local == "TimbreFiscalDigital":
                sello_sat = el.get("SelloSAT", "")
                meta["timbre"] = {
                    "uuid":           el.get("UUID", ""),
                    "fecha_timbrado": el.get("FechaTimbrado", ""),
                    "no_cert_sat":    el.get("NoCertificadoSAT", ""),
                    "rfc_prov_certif": el.get("RfcProvCertif", ""),
                    "sello_sat":      sello_sat[:60] + "…" if len(sello_sat) > 60 else sello_sat,
                }

    # Decodificar catálogos de nivel Comprobante
    meta["moneda_desc"]       = fmt_code("c_Moneda", meta.get("moneda", ""))
    meta["forma_pago_desc"]   = fmt_code("c_FormaPago", meta.get("forma_pago", ""))
    meta["metodo_pago_desc"]  = fmt_code("c_MetodoPago", meta.get("metodo_pago", ""))
    meta["impuestos"]         = impuestos
    meta["retenciones"]       = retenciones
    meta["verifica_url"]      = _build_verifica_url(meta)
    return meta, rows


def _parse_pago_sax(xml_bytes: bytes) -> tuple[dict, list[dict]]:
    """SAX para TipoDeComprobante P — DoctoRelacionado como rows."""
    from lxml import etree
    from .catalogs import fmt_code

    meta: dict          = {}
    rows: list          = []
    _current_pago: dict = {}

    for event, el in etree.iterparse(io.BytesIO(xml_bytes), events=("start", "end"), recover=True):
        local = etree.QName(el.tag).localname

        if event == "start":
            if local == "Comprobante":
                moneda = el.get("Moneda", "MXN")
                meta["fecha"]            = el.get("Fecha", "")
                meta["serie"]            = el.get("Serie", "")
                meta["folio"]            = el.get("Folio", "")
                meta["moneda"]           = moneda
                meta["forma_pago"]       = el.get("FormaPago", "")
                meta["metodo_pago"]      = el.get("MetodoPago", "")
                meta["lugar_expedicion"] = el.get("LugarExpedicion", "")
                meta["tipo_cambio"]      = el.get("TipoCambio", "")
                meta["_sello_8"]         = el.get("Sello", "")[-8:]
                meta["totales"]          = {
                    "subtotal":  _fmt_mxn(el.get("SubTotal", "0")),
                    "descuento": "0.00",
                    "total":     _fmt_mxn(el.get("Total", "0")),
                }
            elif local == "Pago":
                _current_pago = {
                    "fecha":    el.get("FechaPago", "")[:10],
                    "monto":    el.get("Monto", ""),
                    "forma_p":  el.get("FormaDePagoP", ""),
                    "moneda_p": el.get("MonedaP", "MXN"),
                    "tc_p":     el.get("TipoCambioP", "1"),
                }

        elif event == "end":
            if local == "DoctoRelacionado":
                parc      = el.get("NumParcialidad", "")
                saldo_ant = _fmt_mxn(el.get("ImpSaldoAnt", "0"))
                pagado    = _fmt_mxn(el.get("ImpPagado", "0"))
                insoluto  = _fmt_mxn(el.get("ImpSaldoInsoluto", "0"))
                forma_p   = _current_pago.get("forma_p", "")
                moneda_p  = _current_pago.get("moneda_p", "MXN")
                tc_p      = _current_pago.get("tc_p", "1")
                desc = f"Parc. {parc}  Ant: ${saldo_ant}  Insoluto: ${insoluto}"
                if moneda_p and moneda_p != "MXN" and tc_p and tc_p not in ("1", "1.0"):
                    desc += f"  {moneda_p} T.C.:{tc_p}"
                rows.append({
                    "num_id":         el.get("IdDocumento", "")[:11],
                    "cantidad":       parc,
                    "clave_unidad":   _current_pago.get("fecha", ""),
                    "descripcion":    desc,
                    "valor_unitario": forma_p,
                    "descuento":      "0.00",
                    "importe":        pagado,
                })
                el.clear()

            elif local == "Totales":
                monto_total = el.get("MontoTotalPagos")
                if monto_total:
                    meta["monto_total_pagos"] = _fmt_mxn(monto_total)
                    totales = meta.get("totales", {})
                    if totales.get("total", "0.00") in ("0", "0.00", "0.000000"):
                        totales["total"] = meta["monto_total_pagos"]

            elif local == "Pago":
                _current_pago = {}

            elif local == "Emisor":
                regimen = el.get("RegimenFiscal", "")
                meta["emisor"] = {
                    "nombre":       el.get("Nombre", ""),
                    "rfc":          el.get("Rfc", ""),
                    "regimen":      regimen,
                    "regimen_desc": fmt_code("c_RegimenFiscal", regimen),
                }

            elif local == "Receptor":
                uso       = el.get("UsoCFDI", "")
                regimen_r = el.get("RegimenFiscalReceptor", "")
                meta["receptor"] = {
                    "nombre":                    el.get("Nombre", ""),
                    "rfc":                       el.get("Rfc", ""),
                    "uso":                       uso,
                    "uso_desc":                  fmt_code("c_UsoCFDI", uso),
                    "domicilio_fiscal_receptor": el.get("DomicilioFiscalReceptor", ""),
                    "regimen_fiscal_receptor":   regimen_r,
                    "regimen_receptor_desc":     fmt_code("c_RegimenFiscal", regimen_r),
                }

            elif local == "TimbreFiscalDigital":
                sello_sat = el.get("SelloSAT", "")
                meta["timbre"] = {
                    "uuid":            el.get("UUID", ""),
                    "fecha_timbrado":  el.get("FechaTimbrado", ""),
                    "no_cert_sat":     el.get("NoCertificadoSAT", ""),
                    "rfc_prov_certif": el.get("RfcProvCertif", ""),
                    "sello_sat":       sello_sat[:60] + "…" if len(sello_sat) > 60 else sello_sat,
                }

    meta["moneda_desc"]      = fmt_code("c_Moneda", meta.get("moneda", ""))
    meta["forma_pago_desc"]  = fmt_code("c_FormaPago", meta.get("forma_pago", ""))
    meta["metodo_pago_desc"] = fmt_code("c_MetodoPago", meta.get("metodo_pago", ""))
    meta["impuestos"]        = []
    meta["retenciones"]      = []
    meta["verifica_url"]     = _build_verifica_url(meta)
    return meta, rows


def parse_xml_to_rows(xml_str: str | bytes) -> tuple[dict, list[dict]]:
    """
    Dispatcher: detecta TipoDeComprobante y delega al SAX apropiado.
      I / E / T / N / Carta Porte  →  _parse_ingreso_sax  (Conceptos)
      P                            →  _parse_pago_sax      (DoctoRelacionado)
    """
    if isinstance(xml_str, str):
        xml_str = xml_str.encode("utf-8")
    tipo = _detect_tipo(xml_str)
    return _parse_pago_sax(xml_str) if tipo == "P" else _parse_ingreso_sax(xml_str)
