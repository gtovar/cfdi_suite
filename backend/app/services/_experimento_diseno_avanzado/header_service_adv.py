"""
header_service_adv.py — Header avanzado vía WeasyPrint (página 1).

Copia de trabajo independiente de shell_service.py: NO modifica el de producción.
Demuestra el techo de CSS/WeasyPrint para el encabezado de la factura:

  1. Logo vectorial SVG ("LOGO") en la esquina superior izquierda.
  2. Header en dos columnas: emisor (izq, junto al logo) | receptor (der).
  3. Dos familias tipográficas vía @font-face: Georgia (títulos) + Verdana (cuerpo).
  4. Marca de agua diagonal semitransparente detrás del contenido.
  5. Bloque condicional "Descuento" (solo si descuento > 0).
  6. Línea condicional "Tipo de cambio" (solo si moneda != MXN).
  8. Divisor con gradiente CSS (no un <hr> simple).

WATERMARK_* se exportan para que canvas_adv.py (motor reportlab del cuerpo) pueda
sincronizar tono/ángulo/fuente — ver nota de "costura" en el reporte.
"""
from __future__ import annotations

from pathlib import Path

from weasyprint import HTML

WORK_DIR = Path(__file__).resolve().parent
FONTS_DIR = WORK_DIR / "fonts"

# ── Parámetros de marca de agua compartidos con el motor reportlab ─────────────
# (fuente Georgia, misma que títulos; gris; ~8% opacidad; ángulo 30° ascendente)
WATERMARK_TEXT = "TECNOLOGÍA DIGITAL NORTE"
WATERMARK_ANGLE = 30          # grados, ascendente izq→der
WATERMARK_RGB = (30, 58, 95)  # #1e3a5f (c-primary del tema)
WATERMARK_ALPHA = 0.07
WATERMARK_FONT = "Georgia"

# Paleta (misma que el tema "Moderno Corporativo" de A)
BRAND = "#1e3a5f"
ACCENT = "#2563eb"
ACCENT2 = "#7c3aed"


# Página del header: alto fijo dimensionado para la variante MÁS ALTA
# (con descuento + con tipo de cambio). Variantes más cortas => espacio en blanco
# antes de la tabla; el pipeline lee el mediabox real y reserva ese espacio.
_PAGE_W = 595.27
_PAGE_H = 300.0


def _logo_svg() -> str:
    """Logo vectorial simple con texto 'LOGO'. Gradiente + marca tipográfica."""
    return f'''<svg width="116" height="52" viewBox="0 0 116 52" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{BRAND}"/>
      <stop offset="1" stop-color="{ACCENT}"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="52" height="52" rx="10" fill="url(#lg)"/>
  <path d="M14 12 L14 40 L38 40" fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="38" cy="16" r="5.5" fill="#ffffff"/>
  <text x="60" y="24" font-family="Georgia, serif" font-size="17" font-weight="bold" fill="{BRAND}">LOGO</text>
  <text x="60" y="38" font-family="Verdana, sans-serif" font-size="7.5" fill="#64748b">TDN&#183;FISCAL</text>
</svg>'''


def build_header_html(cfdi_data: dict) -> str:
    emisor = cfdi_data.get("emisor", {})
    receptor = cfdi_data.get("receptor", {})
    totales = cfdi_data.get("totales", {})
    timbre = cfdi_data.get("timbre", {})

    moneda = cfdi_data.get("moneda", "MXN")
    moneda_desc = cfdi_data.get("moneda_desc", "") or moneda
    tipo_cambio = cfdi_data.get("tipo_cambio", "")
    descuento = totales.get("descuento", "0") or "0"
    has_descuento = descuento not in ("0", "0.0", "0.00", "0.000000")
    has_tc = moneda != "MXN" and tipo_cambio and tipo_cambio not in ("1", "1.0", "")

    fonts_url = FONTS_DIR.as_uri()

    # ── Bloque condicional #2: tipo de cambio (solo si moneda != MXN) ──
    tc_block = (
        f'<div class="meta-row"><span class="k">Tipo de cambio</span>'
        f'<span class="v">{tipo_cambio} MXN/USD</span></div>'
        if has_tc else ""
    )

    # ── Bloque condicional #1: descuento (solo si descuento > 0) ──
    desc_block = (
        f'<div class="cond-pill"><span class="cond-k">DESCUENTO APLICADO</span>'
        f'<span class="cond-v">- ${descuento}</span></div>'
        if has_descuento else ""
    )

    wm_rgba = f"rgba({WATERMARK_RGB[0]},{WATERMARK_RGB[1]},{WATERMARK_RGB[2]},{WATERMARK_ALPHA})"

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  @font-face {{
    font-family: "TitleFont";
    src: url("{fonts_url}/Georgia.ttf");
    font-weight: normal;
  }}
  @font-face {{
    font-family: "TitleFont";
    src: url("{fonts_url}/Georgia-Bold.ttf");
    font-weight: bold;
  }}
  @font-face {{
    font-family: "BodyFont";
    src: url("{fonts_url}/Verdana.ttf");
    font-weight: normal;
  }}
  @font-face {{
    font-family: "BodyFont";
    src: url("{fonts_url}/Verdana-Bold.ttf");
    font-weight: bold;
  }}

  @page {{ size: {_PAGE_W}pt {_PAGE_H}pt; margin: 0; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}

  body {{
    font-family: "BodyFont", Arial, sans-serif;
    font-size: 8px; color: #0f172a; position: relative;
  }}

  /* (4) Marca de agua diagonal semitransparente detrás del contenido */
  .watermark {{
    position: fixed;
    top: 42%; left: -6%;
    width: 130%;
    text-align: center;
    transform: rotate(-{WATERMARK_ANGLE}deg);
    transform-origin: center;
    font-family: "TitleFont", serif;
    font-size: 52px; font-weight: bold;
    color: {wm_rgba};
    letter-spacing: 3px;
    z-index: 0;
    white-space: nowrap;
  }}
  .layer {{ position: relative; z-index: 1; }}

  .top-bar {{
    height: 7px;
    background: linear-gradient(90deg, {BRAND} 0%, {ACCENT} 55%, {ACCENT2} 100%);
  }}
  .content {{ padding: 16px 30px 14px; }}

  /* (2) Header dos columnas: logo+emisor izq | receptor der */
  .head-grid {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; }}
  .col-left {{ display: flex; gap: 14px; align-items: flex-start; flex: 1.3; }}
  .logo {{ flex: 0 0 auto; line-height: 0; }}

  .doc-kicker {{
    font-family: "TitleFont", serif;
    font-size: 20px; font-weight: bold; color: {BRAND};
    letter-spacing: .3px; line-height: 1;
  }}
  .doc-sub {{ font-size: 6.5px; color: #94a3b8; text-transform: uppercase; letter-spacing: 2px; margin-top: 3px; }}

  .entity-label {{
    font-family: "BodyFont"; font-size: 6.5px; font-weight: bold;
    color: {ACCENT}; text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 3px;
  }}
  .entity-name {{
    font-family: "TitleFont", serif; font-size: 10.5px; font-weight: bold;
    color: {BRAND}; margin-bottom: 4px; line-height: 1.15;
  }}
  .field {{ font-size: 7.5px; color: #475569; line-height: 1.55; }}
  .field b {{ color: #1e293b; font-weight: bold; }}

  .col-right {{
    flex: 0 0 44%;
    border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 10px 13px;
    box-shadow: 0 2px 8px rgba(30,58,95,0.08);
    background: #ffffff;
  }}

  /* (8) Divisor con gradiente (no un <hr>) */
  .grad-divider {{
    height: 2.5px; border: none; margin: 12px 0 10px;
    background: linear-gradient(90deg, {BRAND}, {ACCENT}, {ACCENT2});
    border-radius: 2px;
  }}

  .meta-strip {{ display: flex; gap: 10px; }}
  .meta-card {{
    flex: 1; border: 1px solid #e8edf3; border-radius: 6px;
    padding: 7px 10px; background: #f8fafc;
  }}
  .meta-card .t {{ font-size: 6px; font-weight: bold; color: {ACCENT}; text-transform: uppercase; letter-spacing: .8px; margin-bottom: 4px; }}
  .meta-row {{ display: flex; justify-content: space-between; font-size: 7.5px; line-height: 1.5; }}
  .meta-row .k {{ color: #64748b; }}
  .meta-row .v {{ color: #1e293b; font-weight: bold; }}

  .total-card {{
    flex: 0 0 30%;
    border: 1px solid #9ae6b4; border-radius: 6px;
    background: linear-gradient(135deg, #f0fff4, #e6fffa);
    padding: 8px 11px; text-align: right;
  }}
  .total-card .t {{ font-size: 6px; font-weight: bold; color: #276749; text-transform: uppercase; letter-spacing: 1px; }}
  .total-card .amt {{ font-family: "TitleFont", serif; font-size: 17px; font-weight: bold; color: #276749; line-height: 1.1; }}
  .total-card .cur {{ font-size: 6.5px; color: #38a169; }}

  .cond-pill {{
    display: inline-flex; align-items: center; gap: 6px;
    margin-top: 6px; padding: 3px 9px;
    background: #fff5f5; border: 1px solid #feb2b2; border-radius: 20px;
  }}
  .cond-k {{ font-size: 6px; font-weight: bold; color: #c53030; letter-spacing: .6px; }}
  .cond-v {{ font-size: 8px; font-weight: bold; color: #c53030; font-family: "TitleFont", serif; }}

  .uuid-line {{
    margin-top: 9px; font-size: 6px; color: #94a3b8;
    font-family: "BodyFont"; letter-spacing: .3px;
  }}
  .uuid-line b {{ color: #475569; }}
</style>
</head>
<body>
  <div class="watermark">{WATERMARK_TEXT}</div>
  <div class="layer">
    <div class="top-bar"></div>
    <div class="content">

      <div class="head-grid">
        <div class="col-left">
          <div class="logo">{_logo_svg()}</div>
          <div>
            <div class="doc-kicker">Factura</div>
            <div class="doc-sub">CFDI 4.0 &#183; Representación Impresa</div>
            <div style="margin-top:8px">
              <div class="entity-label">Emisor</div>
              <div class="entity-name">{emisor.get("nombre","")}</div>
              <div class="field"><b>RFC:</b> {emisor.get("rfc","")}</div>
              <div class="field"><b>Régimen:</b> {emisor.get("regimen_desc","") or emisor.get("regimen","")}</div>
              <div class="field"><b>Lugar exp.:</b> {cfdi_data.get("lugar_expedicion","")}</div>
            </div>
          </div>
        </div>

        <div class="col-right">
          <div class="entity-label">Receptor</div>
          <div class="entity-name">{receptor.get("nombre","")}</div>
          <div class="field"><b>RFC:</b> {receptor.get("rfc","")}</div>
          <div class="field"><b>Régimen:</b> {receptor.get("regimen_receptor_desc","") or receptor.get("regimen_fiscal_receptor","")}</div>
          <div class="field"><b>Uso CFDI:</b> {receptor.get("uso_desc","") or receptor.get("uso","")}</div>
          <div class="field"><b>Dom. fiscal:</b> {receptor.get("domicilio_fiscal_receptor","")}</div>
          {desc_block}
        </div>
      </div>

      <hr class="grad-divider">

      <div class="meta-strip">
        <div class="meta-card">
          <div class="t">Comprobante</div>
          <div class="meta-row"><span class="k">Serie / Folio</span><span class="v">{cfdi_data.get("serie","")}/{cfdi_data.get("folio","")}</span></div>
          <div class="meta-row"><span class="k">Fecha</span><span class="v">{cfdi_data.get("fecha","")}</span></div>
          <div class="meta-row"><span class="k">Moneda</span><span class="v">{moneda_desc}</span></div>
          {tc_block}
        </div>
        <div class="meta-card">
          <div class="t">Pago</div>
          <div class="meta-row"><span class="k">Forma</span><span class="v">{cfdi_data.get("forma_pago_desc","") or "—"}</span></div>
          <div class="meta-row"><span class="k">Método</span><span class="v">{cfdi_data.get("metodo_pago_desc","") or "—"}</span></div>
          <div class="meta-row"><span class="k">Subtotal</span><span class="v">${totales.get("subtotal","")}</span></div>
        </div>
        <div class="total-card">
          <div class="t">Total</div>
          <div class="amt">${totales.get("total","")}</div>
          <div class="cur">{moneda}</div>
        </div>
      </div>

      <div class="uuid-line"><b>UUID:</b> {timbre.get("uuid","")} &nbsp;&#183;&nbsp; <b>Timbrado:</b> {timbre.get("fecha_timbrado","")}</div>

    </div>
  </div>
</body>
</html>'''


def render_header(cfdi_data: dict) -> bytes:
    html = build_header_html(cfdi_data)
    return HTML(string=html, base_url=str(WORK_DIR)).write_pdf()
