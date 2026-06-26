"""
canvas_service.py — Motor rl_canvas page-streaming para conceptos y footer.

Arquitectura: escribe páginas directo al stream PDF sin árbol en memoria (O(N)).
Para N > 2000 usa multiprocessing (spawn-safe: funciones en módulo propio).
"""
from __future__ import annotations

import io
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count

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

_WORKERS    = min(8, cpu_count())
_CHUNK_SIZE = 1000

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

def _draw_table_header(cv, y: float) -> float:
    cv.setFillColor(C_HEADER_BG)
    cv.rect(MARGIN, y - HDR_H, PW, HDR_H, fill=1, stroke=0)
    cv.setFillColor(C_WHITE)
    cv.setFont("Helvetica-Bold", 7)
    x = MARGIN
    for header, w in zip(COL_HEADERS, COL_WIDTHS):
        cv.drawString(x + 3, y - HDR_H + 5, header)
        x += w
    return y - HDR_H


def _draw_data_row(cv, y: float, row: dict, idx: int) -> float:
    if idx % 2 == 0:
        cv.setFillColor(C_EVEN_BG)
        cv.rect(MARGIN, y - ROW_H, PW, ROW_H, fill=1, stroke=0)
    cv.setStrokeColor(C_BORDER)
    cv.rect(MARGIN, y - ROW_H, PW, ROW_H, fill=0, stroke=1)

    # Bug fix #3: truncar No.Id a 11 chars (65pt / ~5.5pt por char ≈ 11)
    num_id = str(row.get("num_id", "") or "")[:11]
    desc_raw = row.get("descuento", "0") or "0"
    # Bug fix #4: $0 en gris, rojo solo si hay descuento real
    desc_is_zero = desc_raw in ("0", "0.0", "0.00", "0.000", "0.0000", "0.000000")

    vals = [
        num_id,
        str(row.get("cantidad", "") or ""),
        str(row.get("clave_unidad", "") or ""),
        str(row.get("descripcion", "") or "")[:40],
        f'${row.get("valor_unitario", "") or "0"}',
        f'${desc_raw}',
        f'${row.get("importe", "") or "0"}',
    ]

    x = MARGIN
    for i, (val, w) in enumerate(zip(vals, COL_WIDTHS)):
        if i == 5:
            cv.setFillColor(C_MUTED if desc_is_zero else C_RED)
        elif i == 6:
            cv.setFillColor(C_DARK)
        else:
            cv.setFillColor(C_TEXT)
        cv.setFont("Helvetica-Bold" if i == 6 else "Helvetica", 7)
        cv.drawString(x + 3, y - ROW_H + 4, val[:24])
        x += w
    return y - ROW_H


# ── Footer inline (spawn-safe) ────────────────────────────────────────────────

_FOOTER_MIN_H = 160.0  # espacio mínimo para dibujar el footer en la misma página


def _draw_footer_content(cv, y: float, cfdi_data: dict) -> None:
    """Dibuja el contenido del footer a partir de y. Spawn-safe."""
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

    lbl(f"Moneda: {moneda}", MARGIN, y)
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
    cv.setFillColor(C_HEADER_BG)
    cv.rect(col_label - 8, y - 6, PW - (col_label - 8 - MARGIN), 18, fill=1, stroke=0)
    cv.setFont("Helvetica-Bold", 11)
    cv.setFillColor(C_WHITE)
    cv.drawString(col_label, y + 4, "TOTAL:")
    cv.drawRightString(col_value, y + 4, f"${total}")
    y -= 22

    hr(y)
    y -= 16

    timbre = cfdi_data.get("timbre") or {}
    uuid   = timbre.get("uuid", "")
    if uuid:
        lbl("Folio Fiscal (UUID):", MARGIN, y, bold=True, size=7)
        y -= 11
        cv.setFont("Helvetica", 7)
        cv.setFillColor(C_TEXT)
        cv.drawString(MARGIN, y, uuid)
        y -= 13
        fecha_t = timbre.get("fecha_timbrado", "")
        no_cert = timbre.get("no_cert_sat", "")
        if fecha_t:
            cv.drawString(MARGIN, y, f"Fecha Timbrado: {fecha_t}    No. Cert. SAT: {no_cert}")
            y -= 20

    hr(y)
    y -= 12
    cv.setFont("Helvetica", 6)
    cv.setFillColor(C_MUTED)
    cv.drawCentredString(MARGIN + PW / 2, y, "Este documento es una representación impresa de un CFDI.")


# ── Chunks de renderizado (spawn-safe) ────────────────────────────────────────

def _render_chunk(rows: list[dict], start_idx: int = 0) -> bytes:
    """Páginas de conceptos sin header card. Spawn-safe."""
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    y = H - MARGIN
    y = _draw_table_header(cv, y)

    for idx, row in enumerate(rows):
        if y - ROW_H < MIN_Y:
            cv.showPage()
            y = H - MARGIN
            y = _draw_table_header(cv, y)
        y = _draw_data_row(cv, y, row, start_idx + idx)

    cv.save()
    return buf.getvalue()


def _render_last_chunk(rows: list[dict], start_idx: int, cfdi_data: dict) -> bytes:
    """Último chunk: conceptos + footer inline en la misma página si cabe. Spawn-safe."""
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    y = H - MARGIN
    y = _draw_table_header(cv, y)

    for idx, row in enumerate(rows):
        if y - ROW_H < MIN_Y:
            cv.showPage()
            y = H - MARGIN
            y = _draw_table_header(cv, y)
        y = _draw_data_row(cv, y, row, start_idx + idx)

    # Si no cabe el footer en el espacio restante, nueva página
    if y - _FOOTER_MIN_H < MIN_Y:
        cv.showPage()
        y = H - MARGIN

    _draw_footer_content(cv, y, cfdi_data)
    cv.save()
    return buf.getvalue()


def _render_first_chunk(rows: list[dict], cfdi_data: dict) -> bytes:
    """Primera página: card de encabezado + tabla. Spawn-safe."""
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    y = H - MARGIN
    y = _draw_card_header(cv, y, cfdi_data)
    y = _draw_table_header(cv, y)

    for idx, row in enumerate(rows):
        if y - ROW_H < MIN_Y:
            cv.showPage()
            y = H - MARGIN
            y = _draw_table_header(cv, y)
        y = _draw_data_row(cv, y, row, idx)

    cv.save()
    return buf.getvalue()


def _render_single(rows: list[dict], cfdi_data: dict) -> bytes:
    """Caso N <= 2000: header + conceptos + footer en un solo canvas. Spawn-safe."""
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    y = H - MARGIN
    y = _draw_card_header(cv, y, cfdi_data)
    y = _draw_table_header(cv, y)

    for idx, row in enumerate(rows):
        if y - ROW_H < MIN_Y:
            cv.showPage()
            y = H - MARGIN
            y = _draw_table_header(cv, y)
        y = _draw_data_row(cv, y, row, idx)

    if y - _FOOTER_MIN_H < MIN_Y:
        cv.showPage()
        y = H - MARGIN

    _draw_footer_content(cv, y, cfdi_data)
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

def render_conceptos(rows: list[dict], cfdi_data: dict, workers: int | None = None) -> bytes:
    """
    Genera el PDF completo: header card + conceptos + footer inline.

    N <= 2000: single-process, todo en un canvas.
    N > 2000: first chunk (header), chunks intermedios, last chunk (footer inline).
    """
    if len(rows) <= 2000:
        return _render_single(rows, cfdi_data)

    n_workers = min(workers or _WORKERS, _WORKERS)
    chunks = [rows[i:i + _CHUNK_SIZE] for i in range(0, len(rows), _CHUNK_SIZE)]
    starts = [i * _CHUNK_SIZE for i in range(len(chunks))]

    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futures = [ex.submit(_render_first_chunk, chunks[0], cfdi_data)]
        for chunk, start in zip(chunks[1:-1], starts[1:-1]):
            futures.append(ex.submit(_render_chunk, chunk, start))
        if len(chunks) > 1:
            futures.append(ex.submit(_render_last_chunk, chunks[-1], starts[-1], cfdi_data))
        pdfs = [f.result() for f in futures]

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

    lbl(f"Moneda: {moneda}", MARGIN, y)
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


def parse_xml_to_rows(xml_str: str | bytes) -> tuple[dict, list[dict]]:
    """
    Parsea un XML CFDI con lxml.iterparse (SAX, O(1) memoria).
    Solo recoge <Traslado> y <Retencion> del nivel raíz de <Impuestos>,
    no los per-concepto (que son miles).
    """
    from lxml import etree

    meta: dict = {}
    rows: list[dict] = []
    impuestos: list[dict] = []
    retenciones: list[dict] = []

    _in_concepto = False  # Bug fix #2: flag para ignorar Traslados per-concepto

    if isinstance(xml_str, str):
        xml_str = xml_str.encode("utf-8")

    context = etree.iterparse(
        io.BytesIO(xml_str),
        events=("start", "end"),
        recover=True,
    )

    for event, el in context:
        local = etree.QName(el.tag).localname

        if event == "start":
            if local == "Comprobante":
                meta["fecha"]  = el.get("Fecha", "")
                meta["serie"]  = el.get("Serie", "")
                meta["folio"]  = el.get("Folio", "")
                meta["moneda"] = el.get("Moneda", "MXN")
                meta["totales"] = {
                    "subtotal":  el.get("SubTotal", ""),
                    "descuento": el.get("Descuento", "0") or "0",
                    "total":     el.get("Total", ""),
                }
            elif local == "Concepto":
                _in_concepto = True

        elif event == "end":
            if local == "Concepto":
                rows.append({
                    "num_id":         el.get("NoIdentificacion", "") or "",
                    "cantidad":       el.get("Cantidad", ""),
                    "clave_unidad":   el.get("ClaveUnidad", ""),
                    "descripcion":    el.get("Descripcion", ""),
                    "valor_unitario": el.get("ValorUnitario", ""),
                    "descuento":      el.get("Descuento", "0") or "0",
                    "importe":        el.get("Importe", ""),
                })
                el.clear()
                _in_concepto = False

            elif local == "Traslado" and not _in_concepto:
                # Solo traslados consolidados del nodo raíz <Impuestos>
                imp_code = el.get("Impuesto", "")
                nombre = {"001": "ISR", "002": "IVA", "003": "IEPS"}.get(imp_code, imp_code)
                importe = el.get("Importe", "")
                tasa    = el.get("TasaOCuota", "")
                if importe:
                    impuestos.append({"nombre": nombre, "importe": importe, "tasa": tasa})

            elif local == "Retencion" and not _in_concepto:
                imp_code = el.get("Impuesto", "")
                nombre = {"001": "ISR", "002": "IVA", "003": "IEPS"}.get(imp_code, imp_code)
                importe = el.get("Importe", "")
                if importe:
                    retenciones.append({"nombre": nombre, "importe": importe})

            elif local == "Emisor":
                meta["emisor"] = {
                    "nombre":  el.get("Nombre", ""),
                    "rfc":     el.get("Rfc", ""),
                    "regimen": el.get("RegimenFiscal", ""),
                }

            elif local == "Receptor":
                meta["receptor"] = {
                    "nombre": el.get("Nombre", ""),
                    "rfc":    el.get("Rfc", ""),
                    "uso":    el.get("UsoCFDI", ""),
                }

            elif local == "TimbreFiscalDigital":
                meta["timbre"] = {
                    "uuid":           el.get("UUID", ""),
                    "fecha_timbrado": el.get("FechaTimbrado", ""),
                    "no_cert_sat":    el.get("NoCertificadoSAT", ""),
                }

    meta["impuestos"]   = impuestos
    meta["retenciones"] = retenciones
    return meta, rows
