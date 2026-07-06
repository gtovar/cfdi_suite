"""
canvas_adv.py — Cuerpo avanzado vía reportlab (páginas 1..N).

Copia de trabajo adaptada de canvas_service.py — NO modifica el de producción.
Objetivo: probar el techo de reportlab para el cuerpo de alto volumen, cubriendo:

  3. Dos familias tipográficas embebidas (Georgia títulos / Verdana cuerpo).
  4. Marca de agua diagonal en TODAS las páginas del cuerpo, sincronizada
     (fuente/ángulo/tono/opacidad) con la del header WeasyPrint — ver header_service_adv.
  7. Tabla paginada: header de columnas repetido por página, sombreado alterno,
     numéricos a la derecha, fila de totales SOLO en la última página.
  8. Divisor con gradiente (simulado por franjas) + línea de sombra.
  9. Pie fiscal: UUID, sello, cadena original (placeholder rotulado) y QR real SAT.

FIX del bug heredado: la columna "Unidad" de canvas_service.py mide 36pt y dibuja
la descripción decodificada del catálogo ("Unidad de servicio") sin recorte, con
drawString → el texto se derrama sobre la columna "Descripción". Aquí la columna se
ensancha, el texto se ajusta a 2 líneas y se recorta al ancho real. Ver reporte.
"""
from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from . import header_service_adv as H

FONTS = Path(__file__).resolve().parent / "fonts"

# ── Registro de fuentes embebidas (dos familias distintas) ────────────────────
_FONTS_READY = False


def _ensure_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    pdfmetrics.registerFont(TTFont("Title", str(FONTS / "Georgia.ttf")))
    pdfmetrics.registerFont(TTFont("Title-Bold", str(FONTS / "Georgia-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Title-Italic", str(FONTS / "Georgia-Italic.ttf")))
    pdfmetrics.registerFont(TTFont("Body", str(FONTS / "Verdana.ttf")))
    pdfmetrics.registerFont(TTFont("Body-Bold", str(FONTS / "Verdana-Bold.ttf")))
    pdfmetrics.registerFontFamily("Title", normal="Title", bold="Title-Bold", italic="Title-Italic")
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold")
    _FONTS_READY = True


# ── Layout ────────────────────────────────────────────────────────────────────
W, H_PAGE = A4
MARGIN = 36.0
PW = W - 2 * MARGIN            # 523.27
MIN_Y = MARGIN + 24
HDR_H = 19.0
ROW_H = 23.0                    # alto para descripción de 2 líneas
FOOTER_MIN_H = 210.0

# FIX bug Unidad: columna ancha (58pt) + wrap 2 líneas + recorte real.
#          No.Id  Descripción  Unidad  Cant  P.Unit  Descuento  Importe
COL_W   = [58.0,  195.0,       58.0,   32.0, 60.0,   52.0,      68.27]
COL_KEY = ["No.Id", "Descripción", "Unidad", "Cant.", "P. Unit.", "Descuento", "Importe"]
COL_ALIGN = ["l", "l", "l", "r", "r", "r", "r"]

C_BRAND  = rl_colors.HexColor(H.BRAND)
C_ACCENT = rl_colors.HexColor(H.ACCENT)
C_ACCENT2 = rl_colors.HexColor(H.ACCENT2)
C_EVEN   = rl_colors.HexColor("#f0f7ff")
C_BORDER = rl_colors.HexColor("#e2e8f0")
C_TEXT   = rl_colors.HexColor("#475569")
C_MUTED  = rl_colors.HexColor("#94a3b8")
C_DARK   = rl_colors.HexColor("#1e293b")
C_WHITE  = rl_colors.white
C_RED    = rl_colors.HexColor("#c53030")
C_GREEN  = rl_colors.HexColor("#276749")
C_GREEN_BG = rl_colors.HexColor("#f0fff4")
C_GREEN_BD = rl_colors.HexColor("#9ae6b4")


def _clip(text: str, font: str, size: float, max_w: float) -> str:
    """Recorta a max_w con elipsis. Maneja tokens sin espacios (p.ej. No.Id)."""
    if pdfmetrics.stringWidth(text, font, size) <= max_w:
        return text
    while text and pdfmetrics.stringWidth(text + "…", font, size) > max_w:
        text = text[:-1]
    return text + "…"


def _wrap(text: str, font: str, size: float, max_w: float, max_lines: int) -> list[str]:
    """Word-wrap greedy. Cada línea se recorta duro al ancho real — nunca desborda,
    ni siquiera con tokens largos sin espacios. Elipsis si se corta por max_lines."""
    words = str(text or "").split()
    lines: list[str] = []
    cur = ""
    i = 0
    while i < len(words):
        w = words[i]
        trial = f"{cur} {w}".strip()
        if pdfmetrics.stringWidth(trial, font, size) <= max_w or not cur:
            cur = trial
            i += 1
        else:
            lines.append(cur)
            cur = ""
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)

    truncated = i < len(words)  # quedaron palabras sin colocar
    out: list[str] = []
    for k, ln in enumerate(lines):
        is_last = k == len(lines) - 1
        if is_last and truncated and not ln.endswith("…"):
            ln = ln + " …"
        out.append(_clip(ln, font, size, max_w))
    return out


# ── (4) Marca de agua — sincronizada con el header WeasyPrint ─────────────────
def _draw_watermark(cv) -> None:
    cv.saveState()
    cv.setFont("Title", 52)  # Georgia embebida — misma familia que el watermark CSS
    r, g, b = [c / 255 for c in H.WATERMARK_RGB]
    cv.setFillColorRGB(r, g, b, alpha=H.WATERMARK_ALPHA)
    cv.translate(W / 2, H_PAGE * 0.44)
    cv.rotate(H.WATERMARK_ANGLE)
    cv.drawCentredString(0, 0, H.WATERMARK_TEXT)
    cv.restoreState()


# ── (8) Divisor con gradiente (franjas) + sombra ──────────────────────────────
def _grad_divider(cv, y: float, thickness: float = 2.5) -> None:
    n = 60
    c0 = (0x1e, 0x3a, 0x5f)
    c1 = (0x25, 0x63, 0xeb)
    c2 = (0x7c, 0x3a, 0xed)
    seg = PW / n
    for i in range(n):
        t = i / (n - 1)
        if t < 0.5:
            a, b_, tt = c0, c1, t / 0.5
        else:
            a, b_, tt = c1, c2, (t - 0.5) / 0.5
        col = tuple((a[k] + (b_[k] - a[k]) * tt) / 255 for k in range(3))
        cv.setFillColorRGB(*col)
        cv.rect(MARGIN + i * seg, y, seg + 0.5, thickness, fill=1, stroke=0)
    # sombra sutil bajo el divisor
    cv.setFillColorRGB(0.12, 0.23, 0.37, alpha=0.12)
    cv.rect(MARGIN, y - 1.4, PW, 1.4, fill=1, stroke=0)


# ── (7) Header de columnas (repetido en cada página) ──────────────────────────
def _table_header(cv, y: float) -> float:
    cv.setFillColor(C_BRAND)
    cv.rect(MARGIN, y - HDR_H, PW, HDR_H, fill=1, stroke=0)
    cv.setFillColor(C_WHITE)
    cv.setFont("Body-Bold", 7)
    x = MARGIN
    for i, (label, w) in enumerate(zip(COL_KEY, COL_W)):
        if COL_ALIGN[i] == "r":
            cv.drawRightString(x + w - 4, y - HDR_H + 6, label)
        else:
            cv.drawString(x + 4, y - HDR_H + 6, label)
        x += w
    return y - HDR_H


def _data_row(cv, y: float, row: dict, idx: int) -> float:
    if idx % 2 == 1:
        cv.setFillColor(C_EVEN)
        cv.rect(MARGIN, y - ROW_H, PW, ROW_H, fill=1, stroke=0)
    cv.setStrokeColor(C_BORDER)
    cv.setLineWidth(0.4)
    cv.line(MARGIN, y - ROW_H, MARGIN + PW, y - ROW_H)

    x = MARGIN
    top = y - 8
    # Col 0 — No.Id
    cv.setFont("Body", 7)
    cv.setFillColor(C_TEXT)
    _id = _wrap(row.get("num_id", ""), "Body", 7, COL_W[0] - 8, 1)
    cv.drawString(x + 4, top, _id[0] if _id else "")
    x += COL_W[0]

    # Col 1 — Descripción (2 líneas, SIN truncar a 40; título + subtítulo No.Ident)
    desc = str(row.get("descripcion", "") or "")
    dl = _wrap(desc, "Body-Bold", 7, COL_W[1] - 8, 2)
    cv.setFont("Body-Bold", 7)
    cv.setFillColor(C_DARK)
    if dl:
        cv.drawString(x + 4, top, dl[0])
    if len(dl) > 1:
        cv.drawString(x + 4, top - 8, dl[1])
    x += COL_W[1]

    # Col 2 — Unidad (FIX: columna ancha 58pt + wrap 2 líneas, sin derrame)
    cv.setFont("Body", 6.5)
    cv.setFillColor(C_TEXT)
    ul = _wrap(row.get("clave_unidad", ""), "Body", 6.5, COL_W[2] - 8, 2)
    if ul:
        cv.drawString(x + 4, top, ul[0])
    if len(ul) > 1:
        cv.drawString(x + 4, top - 8, ul[1])
    x += COL_W[2]

    # Cols numéricas a la derecha
    desc_raw = str(row.get("descuento", "0") or "0")
    desc_zero = desc_raw in ("0", "0.0", "0.00", "0.000", "0.0000", "0.000000")
    numvals = [
        (str(row.get("cantidad", "") or ""), C_TEXT, "Body"),
        (f'${row.get("valor_unitario", "") or "0"}', C_TEXT, "Body"),
        (f'-${desc_raw}' if not desc_zero else "—", C_MUTED if desc_zero else C_RED, "Body"),
        (f'${row.get("importe", "") or "0"}', C_DARK, "Body-Bold"),
    ]
    for k, (val, col, fnt) in enumerate(numvals):
        w = COL_W[3 + k]
        cv.setFont(fnt, 7)
        cv.setFillColor(col)
        cv.drawRightString(x + w - 4, top, val)
        x += w
    return y - ROW_H


# ── (9) Pie fiscal ────────────────────────────────────────────────────────────
def _draw_qr(cv, x: float, y_top: float, url: str, size: float = 68.0) -> None:
    import qrcode as _qrcode
    qr = _qrcode.QRCode(version=1, error_correction=_qrcode.constants.ERROR_CORRECT_M,
                        box_size=4, border=1)
    qr.add_data(url or "https://verificacfdi.facturaelectronica.sat.gob.mx/")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    cv.drawImage(ImageReader(buf), x, y_top - size, width=size, height=size)


def _footer(cv, y: float, cfdi_data: dict) -> None:
    totales = cfdi_data.get("totales", {})
    subtotal = totales.get("subtotal", "")
    descuento = totales.get("descuento", "0") or "0"
    total = totales.get("total", "")
    moneda = cfdi_data.get("moneda", "MXN")
    has_desc = descuento not in ("0", "0.0", "0.00", "0.000000")

    _grad_divider(cv, y, 2.0)
    y -= 16

    # ── Bloque de totales (derecha) ──
    box_w = 210
    box_x = MARGIN + PW - box_w
    ty = y
    cv.setFont("Body", 8)

    def money_row(label, val, yy, color=C_DARK, bold=False):
        cv.setFont("Body-Bold" if bold else "Body", 8)
        cv.setFillColor(C_TEXT)
        cv.drawString(box_x, yy, label)
        cv.setFillColor(color)
        cv.drawRightString(box_x + box_w, yy, val)

    money_row("Subtotal:", f"${subtotal}", ty); ty -= 14
    if has_desc:
        money_row("Descuento:", f"-${descuento}", ty, color=C_RED); ty -= 14
    for imp in cfdi_data.get("impuestos", []):
        tasa = imp.get("tasa", "")
        label = f'{imp.get("nombre","")}{f" {float(tasa)*100:.0f}%" if tasa else ""}:'
        if imp.get("importe"):
            money_row(label, f'${imp.get("importe")}', ty); ty -= 14

    # Fila TOTAL (badge de marca)
    cv.setFillColor(C_BRAND)
    cv.rect(box_x - 6, ty - 7, box_w + 6, 20, fill=1, stroke=0)
    cv.setFont("Title-Bold", 11)
    cv.setFillColor(C_WHITE)
    cv.drawString(box_x, ty, "TOTAL")
    cv.drawRightString(box_x + box_w, ty, f"{moneda} ${total}")

    # ── Bloque fiscal (izquierda) — UUID, sello, cadena original, QR ──
    timbre = cfdi_data.get("timbre") or {}
    uuid = timbre.get("uuid", "")
    verifica_url = cfdi_data.get("verifica_url", "")
    fy = y
    cv.setFont("Title-Bold", 7)
    cv.setFillColor(C_ACCENT)
    cv.drawString(MARGIN, fy, "TIMBRE FISCAL DIGITAL — SAT · CFDI 4.0")
    fy -= 12

    qr_size = 68.0
    _draw_qr(cv, MARGIN, fy, verifica_url, size=qr_size)
    tx = MARGIN + qr_size + 10

    def kv(label, val, yy, mono=False):
        cv.setFont("Body-Bold", 5.6)
        cv.setFillColor(C_MUTED)
        cv.drawString(tx, yy, label)
        cv.setFont("Body", 6.2)
        cv.setFillColor(C_TEXT)
        cv.drawString(tx, yy - 7, val)

    kv("UUID / FOLIO FISCAL", uuid, fy)
    kv("FECHA TIMBRADO", timbre.get("fecha_timbrado", ""), fy - 16)
    kv("No. CERT. SAT", timbre.get("no_cert_sat", ""), fy - 32)
    kv("SELLO DEL SAT (fragmento)", (timbre.get("sello_sat", "") or "")[:52], fy - 48)

    # Cadena original — PLACEHOLDER rotulado (simétrico con A: no se computa real)
    fy2 = fy - qr_size - 4
    cv.setFont("Body-Bold", 5.6)
    cv.setFillColor(C_MUTED)
    cv.drawString(MARGIN, fy2, "CADENA ORIGINAL DEL COMPLEMENTO (placeholder — no computada)")
    cv.setFont("Body", 5.6)
    cv.setFillColor(C_TEXT)
    cadena = f'||4.0|{uuid}|{timbre.get("fecha_timbrado","")}|{timbre.get("rfc_prov_certif","")}|{(timbre.get("sello_sat","") or "")[:24]}…||'
    cl = _wrap(cadena, "Body", 5.6, PW, 2)
    for i, line in enumerate(cl):
        cv.drawString(MARGIN, fy2 - 8 - i * 7, line)

    yb = fy2 - 8 - len(cl) * 7 - 6
    cv.setStrokeColor(C_BORDER)
    cv.line(MARGIN, yb, MARGIN + PW, yb)
    cv.setFont("Body", 5.6)
    cv.setFillColor(C_MUTED)
    cv.drawCentredString(MARGIN + PW / 2, yb - 8,
                         "Este documento es una representación impresa de un CFDI 4.0.")


# ── API ───────────────────────────────────────────────────────────────────────
def render_body(rows: list[dict], cfdi_data: dict, header_reserve: float = 0.0) -> bytes:
    """Cuerpo completo: tabla paginada + footer inline en la última página.

    Single-process (N del experimento ≤ ~200). La lógica de paginación —
    header repetido, watermark por página, footer solo al final — es idéntica
    a la del path multiproceso de producción, sólo sin el fan-out de chunks.
    """
    _ensure_fonts()
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)

    _draw_watermark(cv)
    y = (H_PAGE - header_reserve) if header_reserve > 0 else (H_PAGE - MARGIN)
    y = _table_header(cv, y)

    for idx, row in enumerate(rows):
        if y - ROW_H < MIN_Y:
            cv.showPage()
            _draw_watermark(cv)
            y = H_PAGE - MARGIN
            y = _table_header(cv, y)
        y = _data_row(cv, y, row, idx)

    if y - FOOTER_MIN_H < MIN_Y:
        cv.showPage()
        _draw_watermark(cv)
        y = H_PAGE - MARGIN
    else:
        y -= 10
    _footer(cv, y, cfdi_data)
    cv.save()
    return buf.getvalue()


def stamp_and_merge(header_pdf: bytes, body_pdf: bytes) -> bytes:
    """Estampa el header WeasyPrint sobre la página 1 del cuerpo reportlab.
    Idéntico en espíritu a pdf_pipeline._stamp_and_merge de producción."""
    from pypdf import Transformation
    hr = PdfReader(io.BytesIO(header_pdf))
    br = PdfReader(io.BytesIO(body_pdf))
    header_page = hr.pages[0]
    header_h = float(header_page.mediabox.height)
    body_h = float(br.pages[0].mediabox.height)

    writer = PdfWriter()
    writer.add_page(br.pages[0])
    writer.pages[0].merge_transformed_page(
        header_page, Transformation().translate(ty=body_h - header_h), over=True,
    )
    for page in br.pages[1:]:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
