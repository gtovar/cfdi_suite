from __future__ import annotations

import io
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable
from satcfdi.cfdi import CFDI


# ── Zone config ────────────────────────────────────────────────────────────────

_DEFAULT_CONCEPTOS_COLUMNS = [
    "#", "ClaveProdServ", "Descripcion", "ClaveUnidad", "Cantidad", "ValorUnitario", "Importe"
]

# Column spec: id → (header label, relative width)
_COL_SPEC: dict[str, tuple[str, float]] = {
    "#":                ("#",           0.8),
    "ClaveProdServ":    ("Clave",       1.6),
    "NoIdentificacion": ("No. ID",      1.5),
    "Descripcion":      ("Descripción", 5.5),
    "ClaveUnidad":      ("U.M.",        1.0),
    "Cantidad":         ("Cant.",       1.0),
    "ValorUnitario":    ("P.U.",        1.6),
    "Importe":          ("Importe",     1.6),
    "Descuento":        ("Descuento",   1.4),
}


@dataclass
class ZoneConfig:
    id: str
    visible: bool = True
    order: int = 0
    columns: list[str] = field(default_factory=list)  # used by conceptos zone


def _default_zones() -> list[ZoneConfig]:
    return [
        ZoneConfig(id="header",    visible=True, order=1),
        ZoneConfig(id="emisor",    visible=True, order=2),
        ZoneConfig(id="receptor",  visible=True, order=3),
        ZoneConfig(id="conceptos", visible=True, order=4,
                   columns=list(_DEFAULT_CONCEPTOS_COLUMNS)),
        ZoneConfig(id="impuestos", visible=True, order=5),
        ZoneConfig(id="timbre",    visible=True, order=6),
        ZoneConfig(id="footer",    visible=True, order=7),
    ]


# ── Template config ────────────────────────────────────────────────────────────

@dataclass
class PdfTemplate:
    primary_color: str = "#1a56db"
    logo_url: str | None = None
    show_columns: list[str] = field(default_factory=list)  # backward compat
    footer_note: str = ""
    zones: list[ZoneConfig] = field(default_factory=_default_zones)
    # design controls
    font_family: str = "helvetica"       # "helvetica" | "times" | "courier"
    accent_color: str | None = None      # table headers; None → uses primary_color
    table_density: str = "normal"        # "compact" | "normal" | "spacious"
    table_borders: str = "horizontal"    # "full" | "horizontal" | "none"
    table_striping: bool = True
    header_layout: str = "logo-left"     # "logo-left" | "logo-center" | "text-only"
    page_size: str = "letter"            # "letter" | "a4"
    # layout controls (Frente F)
    header_height: int = 56             # encabezado en puntos (pt)
    column_widths: dict = field(default_factory=dict)  # overrides relativos por columna
    margin_top: float = 1.2            # cm
    margin_bottom: float = 1.5         # cm
    margin_left: float = 1.5           # cm
    margin_right: float = 1.5          # cm

    @classmethod
    def from_dict(cls, d: dict) -> "PdfTemplate":
        parsed_zones: list[ZoneConfig] | None = None
        if "zones" in d and isinstance(d["zones"], list):
            parsed_zones = [
                ZoneConfig(
                    id=z.get("id", ""),
                    visible=bool(z.get("visible", True)),
                    order=int(z.get("order", 0)),
                    columns=list(z.get("columns", [])),
                )
                for z in d["zones"]
                if z.get("id")
            ]

        tpl = cls(
            primary_color=d.get("primary_color", "#1a56db"),
            logo_url=d.get("logo_url"),
            show_columns=d.get("show_columns", []),
            footer_note=d.get("footer_note", ""),
            zones=parsed_zones if parsed_zones is not None else _default_zones(),
            font_family=d.get("font_family", "helvetica"),
            accent_color=d.get("accent_color") or None,
            table_density=d.get("table_density", "normal"),
            table_borders=d.get("table_borders", "horizontal"),
            table_striping=bool(d.get("table_striping", True)),
            header_layout=d.get("header_layout", "logo-left"),
            page_size=d.get("page_size", "letter"),
            header_height=int(d.get("header_height", 56)),
            column_widths=d.get("column_widths") or {},
            margin_top=float(d.get("margin_top", 1.2)),
            margin_bottom=float(d.get("margin_bottom", 1.5)),
            margin_left=float(d.get("margin_left", 1.5)),
            margin_right=float(d.get("margin_right", 1.5)),
        )

        # Backward compat: map legacy show_columns into conceptos zone columns
        if parsed_zones is None and tpl.show_columns:
            extra = set(tpl.show_columns)
            for z in tpl.zones:
                if z.id == "conceptos":
                    base = list(_DEFAULT_CONCEPTOS_COLUMNS)
                    if "NoIdentificacion" in extra:
                        base.insert(2, "NoIdentificacion")
                    if "Descuento" in extra:
                        base.append("Descuento")
                    z.columns = base
                    break

        return tpl

    def rl_color(self) -> colors.HexColor:
        return colors.HexColor(self.primary_color)

    def rl_accent(self) -> colors.HexColor:
        return colors.HexColor(self.accent_color or self.primary_color)

    def fonts(self) -> tuple[str, str]:
        return _FONT_MAP.get(self.font_family, _FONT_MAP["helvetica"])


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
            _header, data = url.split(",", 1)
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
    c = tpl.rl_color()
    white = colors.white
    gray = colors.HexColor("#6b7280")
    dark = colors.HexColor("#111827")
    fn, fn_bold = tpl.fonts()

    return {
        "title": ParagraphStyle("title", fontSize=13, textColor=white, fontName=fn_bold,
                                leading=16, alignment=TA_RIGHT),
        "subtitle": ParagraphStyle("subtitle", fontSize=8, textColor=colors.HexColor("#dbeafe"),
                                   fontName=fn, alignment=TA_RIGHT),
        "section_label": ParagraphStyle("sl", fontSize=6.5, textColor=gray, fontName=fn,
                                        leading=9),
        "section_value": ParagraphStyle("sv", fontSize=8, textColor=dark, fontName=fn_bold,
                                        leading=10),
        "section_value_sm": ParagraphStyle("svs", fontSize=7.5, textColor=dark,
                                           fontName=fn, leading=9),
        "total_label": ParagraphStyle("tl", fontSize=8, textColor=gray, fontName=fn,
                                      alignment=TA_RIGHT),
        "total_value": ParagraphStyle("tv", fontSize=8, textColor=dark, fontName=fn_bold,
                                      alignment=TA_RIGHT),
        "grand_label": ParagraphStyle("gl", fontSize=10, textColor=white, fontName=fn_bold,
                                      alignment=TA_RIGHT),
        "grand_value": ParagraphStyle("gv", fontSize=10, textColor=white, fontName=fn_bold,
                                      alignment=TA_RIGHT),
        "table_header": ParagraphStyle("th", fontSize=7, textColor=white, fontName=fn_bold,
                                       alignment=TA_CENTER),
        "table_cell": ParagraphStyle("tc", fontSize=7, textColor=dark, fontName=fn,
                                     leading=9),
        "table_cell_r": ParagraphStyle("tcr", fontSize=7, textColor=dark, fontName=fn,
                                       leading=9, alignment=TA_RIGHT),
        "uuid": ParagraphStyle("uuid", fontSize=6.5, textColor=gray, fontName=fn,
                               leading=8.5),
        "footer": ParagraphStyle("footer", fontSize=6.5, textColor=gray, fontName=fn,
                                 alignment=TA_CENTER),
        "section_head": ParagraphStyle("sh", fontSize=7.5, textColor=white, fontName=fn_bold),
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

    title_content = [
        Paragraph("COMPROBANTE FISCAL DIGITAL 4.0", styles["title"]),
        Paragraph(f"{tipo}  ·  {ref}  ·  {fecha}", styles["subtitle"]),
    ]

    # Scale padding and logo proportionally to header_height (default=56pt)
    scale = tpl.header_height / 56
    pad = max(4, int(8 * scale))
    logo_max_h = 2 * cm * scale

    bg_style = [
        ("BACKGROUND", (0, 0), (-1, -1), c),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
    ]

    layout = tpl.header_layout

    if layout == "text-only":
        # Sin logo, título ocupa todo el ancho
        tbl = Table([[title_content]], colWidths=[page_w])
        tbl.setStyle(TableStyle(bg_style + [
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        return tbl

    logo_img: Any = ""
    if tpl.logo_url:
        img = _load_logo(tpl.logo_url, max_h=logo_max_h)
        if img:
            logo_img = img

    if layout == "logo-center":
        # Logo centrado arriba, título abajo en fila completa
        _, fn_bold = tpl.fonts()
        center_title = ParagraphStyle("ct", fontSize=10, textColor=colors.white,
                                      fontName=fn_bold, alignment=TA_CENTER)
        center_sub = ParagraphStyle("cs", fontSize=8,
                                    textColor=colors.HexColor("#dbeafe"),
                                    fontName=tpl.fonts()[0], alignment=TA_CENTER)
        rows: list = []
        if logo_img:
            rows.append([logo_img])
        rows.append([Paragraph("COMPROBANTE FISCAL DIGITAL 4.0", center_title)])
        rows.append([Paragraph(f"{tipo}  ·  {ref}  ·  {fecha}", center_sub)])
        tbl = Table(rows, colWidths=[page_w])
        tbl.setStyle(TableStyle(bg_style + [
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        return tbl

    # Default: logo-left
    col_w = page_w / 2
    tbl = Table([[logo_img, title_content]], colWidths=[col_w, col_w])
    tbl.setStyle(TableStyle(bg_style + [
        ("LEFTPADDING", (0, 0), (0, 0), 6),
        ("RIGHTPADDING", (1, 0), (1, 0), 6),
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

    left_col: list = []
    for label, val in left_items:
        left_col.extend(_cell(label, val))
        left_col.append(Spacer(1, 2))

    right_col: list = []
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
    tbl = Table([[Paragraph(label, styles["section_head"])]], colWidths=[page_w])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tbl


_ROW_H = 11
_HDR_H = 14
_ROWS_PER_PAGE = 55
_PREVIEW_ROWS = 10

_FONT_MAP: dict[str, tuple[str, str]] = {
    "helvetica": ("Helvetica",   "Helvetica-Bold"),
    "times":     ("Times-Roman", "Times-Bold"),
    "courier":   ("Courier",     "Courier-Bold"),
}

_DENSITY_MAP: dict[str, dict] = {
    "compact":  {"header_h": 11, "row_h": 9,  "pad": 2},
    "normal":   {"header_h": _HDR_H, "row_h": _ROW_H, "pad": 4},
    "spacious": {"header_h": 18, "row_h": 14, "pad": 6},
}

_PAGE_SIZE_MAP = {"letter": LETTER, "a4": A4}


def _make_conceptos_chunk(header_row: list, data_rows: list, col_widths: list,
                          accent: colors.Color, desc_col: int, tpl: PdfTemplate) -> Table:
    density = _DENSITY_MAP.get(tpl.table_density, _DENSITY_MAP["normal"])
    hdr_h = density["header_h"]
    row_h = density["row_h"]
    pad = density["pad"]
    fn, fn_bold = tpl.fonts()

    rows = [header_row] + data_rows
    row_heights = [hdr_h] + [row_h] * len(data_rows)
    stripe = colors.HexColor("#f9fafb")

    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), fn_bold),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTNAME", (0, 1), (-1, -1), fn),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (desc_col + 1, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]

    if tpl.table_striping:
        cmds.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, stripe]))

    border_color = colors.HexColor("#e5e7eb")
    if tpl.table_borders == "full":
        cmds.append(("GRID", (0, 0), (-1, -1), 0.3, border_color))
    elif tpl.table_borders == "horizontal":
        cmds.append(("LINEBELOW", (0, 0), (-1, -1), 0.3, border_color))
    # "none" → no border commands

    tbl = Table(rows, colWidths=col_widths, rowHeights=row_heights)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _row_value(col: str, idx: int, c: Any) -> str:
    if col == "#":               return str(idx)
    if col == "ClaveProdServ":   return _str(c.get("ClaveProdServ"))
    if col == "NoIdentificacion": return _str(c.get("NoIdentificacion"))
    if col == "Descripcion":
        d = _str(c.get("Descripcion", ""))
        return d[:75] if len(d) > 75 else d
    if col == "ClaveUnidad":     return _str(c.get("ClaveUnidad", ""))
    if col == "Cantidad":        return _fmt_qty(c.get("Cantidad"))
    if col == "ValorUnitario":   return _fmt_money(c.get("ValorUnitario"))
    if col == "Importe":         return _fmt_money(c.get("Importe"))
    if col == "Descuento":       return _fmt_money(c.get("Descuento"))
    return ""


def _conceptos_tables(cfdi: CFDI, zone: ZoneConfig, styles: dict,
                      page_w: float, accent: colors.Color, tpl: PdfTemplate) -> list:
    conceptos = cfdi.get("Conceptos") or []
    if isinstance(conceptos, dict):
        conceptos = [conceptos]

    active_cols = [c for c in (zone.columns if zone.columns else _DEFAULT_CONCEPTOS_COLUMNS)
                   if c in _COL_SPEC]
    if not active_cols:
        active_cols = list(_DEFAULT_CONCEPTOS_COLUMNS)

    headers = [_COL_SPEC[c][0] for c in active_cols]
    col_w_base = [tpl.column_widths.get(c, _COL_SPEC[c][1]) for c in active_cols]
    desc_col = next((i for i, c in enumerate(active_cols) if c == "Descripcion"), 0)

    total_w = sum(col_w_base)
    col_widths = [w / total_w * page_w for w in col_w_base]
    header_row = [Paragraph(h, styles["table_header"]) for h in headers]

    all_data = [
        [_row_value(col, i, c) for col in active_cols]
        for i, c in enumerate(conceptos, 1)
    ]

    return [
        _make_conceptos_chunk(header_row, all_data[k:k + _ROWS_PER_PAGE],
                              col_widths, accent, desc_col, tpl)
        for k in range(0, len(all_data), _ROWS_PER_PAGE)
    ]


def _impuestos_y_totales(cfdi: CFDI, styles: dict, page_w: float,
                         accent: colors.Color) -> Table:
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
        imp_lines = [[Paragraph("Sin impuestos", styles["section_label"]),
                      Paragraph("", styles["section_label"])]]

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
    totales_rows.append([P("Subtotal", styles["total_label"]),
                         P(_fmt_money(subtotal), styles["total_value"])])
    if descuento:
        totales_rows.append([P("Descuento", styles["total_label"]),
                             P(_fmt_money(descuento), styles["total_value"])])
    if iva_total:
        totales_rows.append([P("IVA", styles["total_label"]),
                             P(_fmt_money(iva_total), styles["total_value"])])

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
        Paragraph(
            f"<b>Sello SAT:</b> {sello_sat[:80]}…" if len(sello_sat) > 80
            else f"<b>Sello SAT:</b> {sello_sat}",
            styles["uuid"],
        ),
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

_REGIMEN_MAP = {
    "601": "General de Ley Personas Morales",
    "612": "Personas Físicas con Actividades Empresariales",
    "616": "Sin obligaciones fiscales",
    "621": "Incorporación Fiscal",
    "626": "Simplificado de Confianza",
}
_USO_MAP = {
    "G01": "Adquisición de mercancias", "G03": "Gastos en general",
    "I01": "Construcciones", "S01": "Sin efectos fiscales",
    "CP01": "Pagos", "D10": "Pagos por servicios educativos",
}
_FORMA_MAP = {
    "01": "01 - Efectivo", "02": "02 - Cheque nominativo",
    "03": "03 - Transferencia", "04": "04 - Tarjeta de crédito",
    "28": "28 - Tarjeta de débito", "99": "99 - Por definir",
}
_METODO_MAP = {
    "PUE": "PUE - Pago en una sola exhibición",
    "PPD": "PPD - Pago en parcialidades",
}


def generate_pdf(cfdi: CFDI, template: dict | None = None) -> bytes:
    tpl = PdfTemplate.from_dict(template or {})
    accent = tpl.rl_accent()   # table headers, section headers
    styles = _make_styles(tpl)

    pagesize = _PAGE_SIZE_MAP.get(tpl.page_size, LETTER)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagesize,
        leftMargin=tpl.margin_left * cm,
        rightMargin=tpl.margin_right * cm,
        topMargin=tpl.margin_top * cm,
        bottomMargin=tpl.margin_bottom * cm,
        title="Comprobante Fiscal Digital",
    )
    page_w = pagesize[0] - (tpl.margin_left + tpl.margin_right) * cm

    emisor = cfdi.get("Emisor") or {}
    receptor = cfdi.get("Receptor") or {}

    regimen_code = _str(emisor.get("RegimenFiscal", ""))
    uso_code = _str(receptor.get("UsoCFDI", ""))
    moneda = _str(cfdi.get("Moneda", ""))
    tc = cfdi.get("TipoCambio")
    moneda_str = moneda + (f"  ·  T/C: {tc}" if tc and str(tc) not in ("1", "1.0") else "")

    story: list = []

    for zone in sorted(tpl.zones, key=lambda z: z.order):
        if not zone.visible:
            continue

        if zone.id == "header":
            story.append(_header_table(cfdi, tpl, styles, page_w))
            story.append(Spacer(1, 4))

        elif zone.id == "emisor":
            story.append(_section_header("EMISOR / DATOS DEL COMPROBANTE", accent, page_w, styles))
            story.append(_two_col_info(
                left_items=[
                    ("RFC", _str(emisor.get("Rfc"))),
                    ("Nombre / Razón social", _str(emisor.get("Nombre"))),
                    ("Régimen fiscal", _REGIMEN_MAP.get(regimen_code, regimen_code)),
                    ("CP de expedición", _str(cfdi.get("LugarExpedicion"))),
                ],
                right_items=[
                    ("Moneda", moneda_str),
                    ("Forma de pago", _FORMA_MAP.get(_str(cfdi.get("FormaPago", "")),
                                                     _str(cfdi.get("FormaPago", "")))),
                    ("Método de pago", _METODO_MAP.get(_str(cfdi.get("MetodoPago", "")),
                                                       _str(cfdi.get("MetodoPago", "")))),
                    ("Condiciones de pago", _str(cfdi.get("CondicionesDePago"))),
                ],
                styles=styles, page_w=page_w, accent=accent,
            ))

        elif zone.id == "receptor":
            story.append(_section_header("RECEPTOR", accent, page_w, styles))
            story.append(_two_col_info(
                left_items=[
                    ("RFC", _str(receptor.get("Rfc"))),
                    ("Nombre / Razón social", _str(receptor.get("Nombre"))),
                ],
                right_items=[
                    ("Uso CFDI", _USO_MAP.get(uso_code, uso_code)),
                    ("Domicilio fiscal receptor", _str(receptor.get("DomicilioFiscalReceptor"))),
                ],
                styles=styles, page_w=page_w, accent=accent,
            ))

        elif zone.id == "conceptos":
            story.append(Spacer(1, 4))
            story.append(_section_header("CONCEPTOS", accent, page_w, styles))
            story.extend(_conceptos_tables(cfdi, zone, styles, page_w, accent, tpl))

        elif zone.id == "impuestos":
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width=page_w, thickness=0.5, color=colors.HexColor("#e5e7eb")))
            story.append(_impuestos_y_totales(cfdi, styles, page_w, accent))
            story.append(HRFlowable(width=page_w, thickness=0.5, color=colors.HexColor("#e5e7eb")))

        elif zone.id == "timbre":
            story.append(Spacer(1, 6))
            story.append(_section_header("TIMBRE FISCAL DIGITAL (SAT)", accent, page_w, styles))
            story.extend(_timbre_section(cfdi, styles, page_w))

        elif zone.id == "footer":
            if tpl.footer_note:
                story.append(Spacer(1, 6))
                story.append(Paragraph(tpl.footer_note, styles["footer"]))

    doc.build(story)
    return buf.getvalue()


def generate_preview(cfdi: CFDI, template: dict | None = None) -> bytes:
    """Generate a fast preview PDF — limits concepts to _PREVIEW_ROWS for speed."""
    import copy
    preview = copy.copy(cfdi)
    conceptos = cfdi.get("Conceptos") or []
    if isinstance(conceptos, dict):
        conceptos = [conceptos]
    if len(conceptos) > _PREVIEW_ROWS:
        preview["Conceptos"] = conceptos[:_PREVIEW_ROWS]
    return generate_pdf(preview, template)
