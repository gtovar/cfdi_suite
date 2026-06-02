from __future__ import annotations

import io
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable
from satcfdi.cfdi import CFDI


# ── Template config ────────────────────────────────────────────────────────────

@dataclass
class PdfTemplate:
    primary_color: str = "#1a56db"
    logo_url: str | None = None
    show_columns: list[str] = field(default_factory=list)
    footer_note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "PdfTemplate":
        return cls(
            primary_color=d.get("primary_color", "#1a56db"),
            logo_url=d.get("logo_url"),
            show_columns=d.get("show_columns", []),
            footer_note=d.get("footer_note", ""),
        )

    def rl_color(self) -> colors.HexColor:
        return colors.HexColor(self.primary_color)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_money(value: Any, decimals: int = 2) -> str:
    try:
        d = Decimal(str(value))
        return f"${d:,.{decimals}f}"
    except (InvalidOperation, TypeError):
        return str(value) if value is not None else ""


def _fmt_qty(value: Any) -> str:
    try:
        d = Decimal(str(value))
        return f"{d:,}"
    except (InvalidOperation, TypeError):
        return str(value) if value is not None else ""


def _str(value: Any) -> str:
    return str(value) if value is not None else ""


def _sat_qr_url(cfdi: CFDI) -> str:
    tfd = (cfdi.get("Complemento") or {}).get("TimbreFiscalDigital") or {}
    uuid = _str(tfd.get("UUID"))
    rfc_e = _str((cfdi.get("Emisor") or {}).get("Rfc"))
    rfc_r = _str((cfdi.get("Receptor") or {}).get("Rfc"))
    total = _str(cfdi.get("Total", ""))
    sello = _str(tfd.get("SelloSAT") or cfdi.get("Sello") or "")[-8:]
    return (
        "https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx"
        f"?&id={uuid}&re={rfc_e}&rr={rfc_r}&tt={total}&fe={sello}"
    )


def _build_qr_image(url: str, size_cm: float = 3.0) -> Image | None:
    try:
        import qrcode as qc
        qr = qc.QRCode(box_size=4, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return Image(buf, width=size_cm * cm, height=size_cm * cm)
    except Exception:
        return None


def _load_logo(url: str, max_w: float = 5 * cm, max_h: float = 2 * cm) -> Image | None:
    try:
        if url.startswith("data:"):
            import base64
            header, data = url.split(",", 1)
            buf = io.BytesIO(base64.b64decode(data))
        else:
            with urllib.request.urlopen(url, timeout=5) as r:
                buf = io.BytesIO(r.read())
        img = Image(buf)
        w, h = img.imageWidth, img.imageHeight
        ratio = min(max_w / w, max_h / h)
        img.drawWidth = w * ratio
        img.drawHeight = h * ratio
        return img
    except Exception:
        return None


# ── Styles ─────────────────────────────────────────────────────────────────────

def _make_styles(tpl: PdfTemplate) -> dict:
    base = getSampleStyleSheet()
    c = tpl.rl_color()
    white = colors.white
    gray = colors.HexColor("#6b7280")
    dark = colors.HexColor("#111827")

    return {
        "title": ParagraphStyle("title", fontSize=13, textColor=white, fontName="Helvetica-Bold",
                                leading=16, alignment=TA_RIGHT),
        "subtitle": ParagraphStyle("subtitle", fontSize=8, textColor=colors.HexColor("#dbeafe"),
                                   fontName="Helvetica", alignment=TA_RIGHT),
        "section_label": ParagraphStyle("sl", fontSize=6.5, textColor=gray, fontName="Helvetica",
                                        leading=9),
        "section_value": ParagraphStyle("sv", fontSize=8, textColor=dark, fontName="Helvetica-Bold",
                                        leading=10),
        "section_value_sm": ParagraphStyle("svs", fontSize=7.5, textColor=dark,
                                           fontName="Helvetica", leading=9),
        "total_label": ParagraphStyle("tl", fontSize=8, textColor=gray, fontName="Helvetica",
                                      alignment=TA_RIGHT),
        "total_value": ParagraphStyle("tv", fontSize=8, textColor=dark, fontName="Helvetica-Bold",
                                      alignment=TA_RIGHT),
        "grand_label": ParagraphStyle("gl", fontSize=10, textColor=white, fontName="Helvetica-Bold",
                                      alignment=TA_RIGHT),
        "grand_value": ParagraphStyle("gv", fontSize=10, textColor=white, fontName="Helvetica-Bold",
                                      alignment=TA_RIGHT),
        "table_header": ParagraphStyle("th", fontSize=7, textColor=white, fontName="Helvetica-Bold",
                                       alignment=TA_CENTER),
        "table_cell": ParagraphStyle("tc", fontSize=7, textColor=dark, fontName="Helvetica",
                                     leading=9),
        "table_cell_r": ParagraphStyle("tcr", fontSize=7, textColor=dark, fontName="Helvetica",
                                       leading=9, alignment=TA_RIGHT),
        "uuid": ParagraphStyle("uuid", fontSize=6.5, textColor=gray, fontName="Helvetica",
                               leading=8.5),
        "footer": ParagraphStyle("footer", fontSize=6.5, textColor=gray, fontName="Helvetica",
                                 alignment=TA_CENTER),
        "accent": c,
    }


# ── Section builders ───────────────────────────────────────────────────────────

class _ColorBar(Flowable):
    """Barra de color sólida de ancho completo."""
    def __init__(self, height: float, color: colors.Color):
        super().__init__()
        self.bar_height = height
        self.bar_color = color

    def wrap(self, avail_w, avail_h):
        self._w = avail_w
        return avail_w, self.bar_height

    def draw(self):
        self.canv.setFillColor(self.bar_color)
        self.canv.rect(0, 0, self._w, self.bar_height, fill=1, stroke=0)


def _header_table(cfdi: CFDI, tpl: PdfTemplate, styles: dict, page_w: float) -> Table:
    """Barra de color con logo + título + folio/fecha."""
    c = tpl.rl_color()
    tipo_map = {"I": "Ingreso", "E": "Egreso", "T": "Traslado", "P": "Pago", "N": "Nómina"}
    tipo = tipo_map.get(_str(cfdi.get("TipoDeComprobante")), _str(cfdi.get("TipoDeComprobante")))
    serie = _str(cfdi.get("Serie") or "")
    folio = _str(cfdi.get("Folio") or "")
    ref = f"{serie}-{folio}" if serie else folio
    fecha = _str(cfdi.get("Fecha", ""))[:10]

    logo_cell: Any = ""
    if tpl.logo_url:
        img = _load_logo(tpl.logo_url)
        if img:
            logo_cell = img

    title_content = [
        Paragraph("COMPROBANTE FISCAL DIGITAL 4.0", styles["title"]),
        Paragraph(f"{tipo}  ·  {ref}  ·  {fecha}", styles["subtitle"]),
    ]

    col_w = page_w / 2
    tbl = Table([[logo_cell, title_content]], colWidths=[col_w, col_w])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 6),
        ("RIGHTPADDING", (1, 0), (1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tbl


def _two_col_info(left_items: list, right_items: list, styles: dict,
                  page_w: float, accent: colors.Color) -> Table:
    """Bloque de dos columnas con label/value stacked."""
    def _cell(label: str, value: str) -> list:
        if not value:
            return [Paragraph("", styles["section_label"])]
        return [
            Paragraph(label.upper(), styles["section_label"]),
            Paragraph(value, styles["section_value"] if len(value) < 45 else styles["section_value_sm"]),
        ]

    left_col = []
    for label, val in left_items:
        left_col.extend(_cell(label, val))
        left_col.append(Spacer(1, 2))

    right_col = []
    for label, val in right_items:
        right_col.extend(_cell(label, val))
        right_col.append(Spacer(1, 2))

    col_w = page_w / 2
    tbl = Table([[left_col, right_col]], colWidths=[col_w, col_w])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, colors.HexColor("#e5e7eb")),
    ]))
    return tbl


def _section_header(label: str, accent: colors.Color, page_w: float, styles: dict) -> Table:
    tbl = Table([[Paragraph(label, ParagraphStyle(
        "sh", fontSize=7.5, textColor=colors.white, fontName="Helvetica-Bold"
    ))]], colWidths=[page_w])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tbl


_ROW_H = 11      # altura fija por fila (puntos)
_HDR_H = 14      # altura del header de la tabla
_ROWS_PER_PAGE = 55  # filas de datos por tabla; ajustado a la página Letter con márgenes


def _make_conceptos_chunk(header_row: list, data_rows: list, col_widths: list,
                          accent: colors.Color, desc_col: int) -> Table:
    """Crea una Table pequeña de una 'página' de conceptos."""
    rows = [header_row] + data_rows
    row_heights = [_HDR_H] + [_ROW_H] * len(data_rows)
    stripe = colors.HexColor("#f9fafb")
    tbl = Table(rows, colWidths=col_widths, rowHeights=row_heights)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, stripe]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (desc_col + 1, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return tbl


def _conceptos_tables(cfdi: CFDI, tpl: PdfTemplate, styles: dict,
                      page_w: float, accent: colors.Color) -> list:
    """Retorna lista de Tables (una por página aprox.) para los conceptos."""
    conceptos = cfdi.get("Conceptos") or []
    if isinstance(conceptos, dict):
        conceptos = [conceptos]

    extra_cols = set(tpl.show_columns)
    show_no_id = "NoIdentificacion" in extra_cols
    show_desc = "Descuento" in extra_cols

    headers = ["#", "Clave", "Descripción", "U.M.", "Cant.", "P.U.", "Importe"]
    col_w_base = [0.8, 1.6, 5.5, 1.0, 1.0, 1.6, 1.6]
    desc_col = 2

    if show_no_id:
        headers.insert(2, "No. ID")
        col_w_base.insert(2, 1.5)
        desc_col = 3
    if show_desc:
        headers.append("Descuento")
        col_w_base.append(1.4)

    total_w = sum(col_w_base)
    col_widths = [w / total_w * page_w for w in col_w_base]
    header_row = [Paragraph(h, styles["table_header"]) for h in headers]

    # Construir filas de datos como strings planos (sin Paragraph = sin medición de texto)
    all_data: list[list] = []
    for i, c in enumerate(conceptos, 1):
        desc = _str(c.get("Descripcion", ""))
        row: list = [str(i), _str(c.get("ClaveProdServ"))]
        if show_no_id:
            row.append(_str(c.get("NoIdentificacion")))
        row += [
            desc[:75] if len(desc) > 75 else desc,
            _str(c.get("ClaveUnidad", "")),
            _fmt_qty(c.get("Cantidad")),
            _fmt_money(c.get("ValorUnitario")),
            _fmt_money(c.get("Importe")),
        ]
        if show_desc:
            row.append(_fmt_money(c.get("Descuento")))
        all_data.append(row)

    # Dividir en chunks pequeños — evita que ReportLab pagine internamente una tabla enorme
    return [
        _make_conceptos_chunk(header_row, all_data[i:i + _ROWS_PER_PAGE],
                              col_widths, accent, desc_col)
        for i in range(0, len(all_data), _ROWS_PER_PAGE)
    ]


def _impuestos_y_totales(cfdi: CFDI, styles: dict, page_w: float,
                         accent: colors.Color) -> Table:
    """Bloque final: impuestos agrupados (izq) + totales (der)."""
    imp = cfdi.get("Impuestos") or {}
    traslados = imp.get("Traslados") or {}
    retenciones = imp.get("Retenciones") or {}
    if isinstance(traslados, dict):
        traslados = [traslados]
    if isinstance(retenciones, dict):
        retenciones = [retenciones]

    imp_lines: list[list] = []
    for t in (traslados if isinstance(traslados, list) else []):
        nombre = _str(t.get("Impuesto", ""))
        tasa = t.get("TasaOCuota")
        lbl = f"IVA {float(tasa)*100:.0f}%" if nombre == "002" and tasa else f"Imp {nombre}"
        imp_lines.append([
            Paragraph(lbl, styles["section_label"]),
            Paragraph(_fmt_money(t.get("Importe")), styles["section_label"]),
        ])
    for r in (retenciones if isinstance(retenciones, list) else []):
        nombre = _str(r.get("Impuesto", ""))
        lbl = {"001": "Ret. ISR", "002": "Ret. IVA"}.get(nombre, f"Ret. {nombre}")
        imp_lines.append([
            Paragraph(lbl, styles["section_label"]),
            Paragraph(_fmt_money(r.get("Importe")), styles["section_label"]),
        ])

    if not imp_lines:
        imp_lines = [[Paragraph("Sin impuestos", styles["section_label"]), Paragraph("", styles["section_label"])]]

    left_col = Table(imp_lines, colWidths=[page_w * 0.18, page_w * 0.12])
    left_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    subtotal = cfdi.get("SubTotal")
    descuento = cfdi.get("Descuento")
    total = cfdi.get("Total")
    iva_total = sum(
        float(t.get("Importe", 0))
        for t in (traslados if isinstance(traslados, list) else [])
    )

    P = Paragraph
    totales_rows = []
    totales_rows.append([P("Subtotal", styles["total_label"]), P(_fmt_money(subtotal), styles["total_value"])])
    if descuento:
        totales_rows.append([P("Descuento", styles["total_label"]), P(_fmt_money(descuento), styles["total_value"])])
    if iva_total:
        totales_rows.append([P("IVA", styles["total_label"]), P(_fmt_money(iva_total), styles["total_value"])])

    label_w = page_w * 0.18
    value_w = page_w * 0.12
    right_col_rows = Table(totales_rows, colWidths=[label_w, value_w])
    right_col_rows.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))

    grand_total = Table(
        [[P("TOTAL", styles["grand_label"]), P(_fmt_money(total), styles["grand_value"])]],
        colWidths=[label_w, value_w],
    )
    grand_total.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))

    spacer_w = page_w - page_w * 0.3 - page_w * 0.3
    outer = Table(
        [[left_col, "", [right_col_rows, grand_total]]],
        colWidths=[page_w * 0.3, spacer_w, page_w * 0.3],
    )
    outer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return outer


def _timbre_section(cfdi: CFDI, styles: dict, page_w: float) -> list:
    tfd = (cfdi.get("Complemento") or {}).get("TimbreFiscalDigital") or {}
    uuid = _str(tfd.get("UUID"))
    fecha = _str(tfd.get("FechaTimbrado", ""))[:19]
    sello_sat = _str(tfd.get("SelloSAT", ""))
    rfc_pac = _str(tfd.get("RfcProvCertif", ""))

    qr_url = _sat_qr_url(cfdi)
    qr_img = _build_qr_image(qr_url, size_cm=2.8)

    uuid_block = [
        Paragraph(f"<b>UUID:</b> {uuid}", styles["uuid"]),
        Paragraph(f"<b>Timbrado:</b> {fecha}  ·  <b>PAC:</b> {rfc_pac}", styles["uuid"]),
        Spacer(1, 3),
        Paragraph(f"<b>Sello SAT:</b> {sello_sat[:80]}…" if len(sello_sat) > 80 else f"<b>Sello SAT:</b> {sello_sat}", styles["uuid"]),
        Spacer(1, 3),
        Paragraph(
            "Verifique este CFDI en: verificacfdi.facturaelectronica.sat.gob.mx",
            styles["uuid"],
        ),
    ]

    qr_cell = qr_img if qr_img else Paragraph("", styles["uuid"])
    tbl = Table(
        [[qr_cell, uuid_block]],
        colWidths=[3.2 * cm, page_w - 3.2 * cm],
    )
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 4),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [tbl]


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_pdf(cfdi: CFDI, template: dict | None = None) -> bytes:
    tpl = PdfTemplate.from_dict(template or {})
    accent = tpl.rl_color()
    styles = _make_styles(tpl)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.5 * cm,
        title="Comprobante Fiscal Digital",
    )
    page_w = LETTER[0] - 3 * cm  # ancho útil

    emisor = cfdi.get("Emisor") or {}
    receptor = cfdi.get("Receptor") or {}

    regimen_map = {
        "601": "General de Ley Personas Morales",
        "612": "Personas Físicas con Actividades Empresariales",
        "616": "Sin obligaciones fiscales",
        "621": "Incorporación Fiscal",
        "626": "Simplificado de Confianza",
    }
    regimen_code = _str(emisor.get("RegimenFiscal", ""))
    regimen = regimen_map.get(regimen_code, regimen_code)

    uso_map = {
        "G01": "Adquisición de mercancias",
        "G03": "Gastos en general",
        "I01": "Construcciones",
        "S01": "Sin efectos fiscales",
        "CP01": "Pagos",
        "D10": "Pagos por servicios educativos",
    }
    uso_code = _str(receptor.get("UsoCFDI", ""))
    uso = uso_map.get(uso_code, uso_code)

    moneda = _str(cfdi.get("Moneda", ""))
    tc = cfdi.get("TipoCambio")
    moneda_str = f"{moneda}" + (f"  ·  T/C: {tc}" if tc and str(tc) not in ("1", "1.0") else "")

    forma_map = {
        "01": "01 - Efectivo", "02": "02 - Cheque nominativo",
        "03": "03 - Transferencia", "04": "04 - Tarjeta de crédito",
        "28": "28 - Tarjeta de débito", "99": "99 - Por definir",
    }
    metodo_map = {"PUE": "PUE - Pago en una sola exhibición", "PPD": "PPD - Pago en parcialidades"}
    forma = forma_map.get(_str(cfdi.get("FormaPago", "")), _str(cfdi.get("FormaPago", "")))
    metodo = metodo_map.get(_str(cfdi.get("MetodoPago", "")), _str(cfdi.get("MetodoPago", "")))

    story: list = []

    # 1. Header con logo y título
    story.append(_header_table(cfdi, tpl, styles, page_w))
    story.append(Spacer(1, 4))

    # 2. Emisor + datos del comprobante
    story.append(_section_header("EMISOR / DATOS DEL COMPROBANTE", accent, page_w, styles))
    story.append(_two_col_info(
        left_items=[
            ("RFC", _str(emisor.get("Rfc"))),
            ("Nombre / Razón social", _str(emisor.get("Nombre"))),
            ("Régimen fiscal", regimen),
            ("CP de expedición", _str(cfdi.get("LugarExpedicion"))),
        ],
        right_items=[
            ("Moneda", moneda_str),
            ("Forma de pago", forma),
            ("Método de pago", metodo),
            ("Condiciones de pago", _str(cfdi.get("CondicionesDePago"))),
        ],
        styles=styles, page_w=page_w, accent=accent,
    ))

    # 3. Receptor
    story.append(_section_header("RECEPTOR", accent, page_w, styles))
    story.append(_two_col_info(
        left_items=[
            ("RFC", _str(receptor.get("Rfc"))),
            ("Nombre / Razón social", _str(receptor.get("Nombre"))),
        ],
        right_items=[
            ("Uso CFDI", uso),
            ("Domicilio fiscal receptor", _str(receptor.get("DomicilioFiscalReceptor"))),
        ],
        styles=styles, page_w=page_w, accent=accent,
    ))

    # 4. Conceptos (lista de Tables pequeñas, una por página aprox.)
    story.append(Spacer(1, 4))
    story.append(_section_header("CONCEPTOS", accent, page_w, styles))
    story.extend(_conceptos_tables(cfdi, tpl, styles, page_w, accent))

    # 5. Impuestos + Totales
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width=page_w, thickness=0.5, color=colors.HexColor("#e5e7eb")))
    story.append(_impuestos_y_totales(cfdi, styles, page_w, accent))
    story.append(HRFlowable(width=page_w, thickness=0.5, color=colors.HexColor("#e5e7eb")))

    # 6. Timbre Fiscal Digital + QR
    story.append(Spacer(1, 6))
    story.append(_section_header("TIMBRE FISCAL DIGITAL (SAT)", accent, page_w, styles))
    story.extend(_timbre_section(cfdi, styles, page_w))

    # 7. Footer opcional
    if tpl.footer_note:
        story.append(Spacer(1, 6))
        story.append(Paragraph(tpl.footer_note, styles["footer"]))

    doc.build(story)
    return buf.getvalue()
