"""
shell_service.py — Pre-render de header HTML con WeasyPrint.

El shell es el PDF de la página de encabezado (logo, emisor, receptor, metadata).
Se genera una vez por versión de template y se cachea en backend/shells/.
"""
from __future__ import annotations

import threading
from pathlib import Path

from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

SHELLS_DIR = Path(__file__).resolve().parents[2] / "shells"
SHELLS_DIR.mkdir(exist_ok=True)

HTML_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "html"
HTML_TEMPLATES_DIR.mkdir(exist_ok=True)

# FontConfiguration() escanea TODO el inventario de fuentes del sistema
# (fontconfig.FcInitLoadConfigAndFonts) en cada instanciación — costoso
# (~30% del tiempo de un render de header) e independiente de los datos de
# la factura o de si el HTML declara @font-face. Un config por hilo (perfilado
# 2026-07 en docs/propuesta-arquitectura-batch.md) evita rehacer ese escaneo en
# cada factura, sin compartir el mismo objeto entre hilos concurrentes.
_font_config_local = threading.local()


def _get_font_config() -> FontConfiguration:
    config = getattr(_font_config_local, "config", None)
    if config is None:
        config = FontConfiguration()
        _font_config_local.config = config
    return config


# ── Template HTML base para el header ─────────────────────────────────────────

DEFAULT_HEADER_HTML = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  @page { size: 595.27pt 205pt; margin: 0; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 9px;
    color: #2D3748;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .top-bar { background: {{brand_color}}; height: 6px; }
  .content { padding: 14px 28px 14px; }

  .logo-area { margin-bottom: 6px; line-height: 0; }
  .logo-area img { max-height: 40px; max-width: 130px; object-fit: contain; }

  .doc-header {
    display: flex; align-items: flex-start; justify-content: space-between;
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: 8px; margin-bottom: 10px;
  }
  .doc-title {
    font-size: 13px; font-weight: 700; color: {{brand_color}};
    text-transform: uppercase; letter-spacing: .4px;
  }
  .doc-subtitle { font-size: 7px; color: #A0AEC0; text-transform: uppercase; letter-spacing: 1px; margin-top: 2px; }

  .card {
    border: 1px solid #E2E8F0; border-radius: 6px;
    padding: 10px 14px; margin-bottom: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  }

  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .grid-4 { display: grid; grid-template-columns: 1.3fr 1fr 1fr 1fr; gap: 12px; }

  .section-label {
    font-size: 7px; font-weight: 700; color: {{brand_accent}};
    text-transform: uppercase; letter-spacing: .4px; margin-bottom: 4px;
  }
  .entity-name { font-size: 10px; font-weight: 700; color: {{brand_color}}; margin-bottom: 3px; }
  .field { color: #4A5568; line-height: 1.6; font-size: 8px; }
  .field strong { color: #2D3748; }

  .divider { border: none; border-top: 1px solid #E2E8F0; margin: 8px 0; }

  .total-box {
    background: #F0FFF4; border: 1px solid #9AE6B4; border-radius: 5px;
    padding: 8px 10px; text-align: center;
  }
  .total-label { font-size: 7px; color: #276749; text-transform: uppercase; font-weight: 700; }
  .total-amount { font-size: 15px; font-weight: 700; color: #276749; margin-top: 2px; }
</style>
</head>
<body>
<div class="top-bar"></div>
<div class="content">

  <div class="doc-header">
    <div>
      {{logo_block}}
      <div class="doc-title">Comprobante Fiscal Digital por Internet</div>
      <div class="doc-subtitle">CFDI 4.0 — Representación Impresa</div>
    </div>
  </div>

  <div class="card">
    <div class="grid-2">
      <div>
        <div class="section-label">Emisor</div>
        <div class="entity-name">{{emisor_nombre}}</div>
        <div class="field"><strong>RFC:</strong> {{emisor_rfc}}</div>
        <div class="field"><strong>Régimen:</strong> {{emisor_regimen_desc}}</div>
        <div class="field"><strong>CP Expedición:</strong> {{lugar_expedicion}}</div>
      </div>
      <div>
        <div class="section-label">Receptor</div>
        <div class="entity-name">{{receptor_nombre}}</div>
        <div class="field"><strong>RFC:</strong> {{receptor_rfc}}</div>
        <div class="field"><strong>Régimen:</strong> {{receptor_regimen_desc}}</div>
        <div class="field"><strong>Uso CFDI:</strong> {{receptor_uso_desc}}</div>
        <div class="field"><strong>Dom. Fiscal:</strong> {{domicilio_fiscal_receptor}}</div>
      </div>
    </div>

    <hr class="divider">

    <div class="grid-4">
      <div>
        <div class="section-label">Comprobante</div>
        <div class="field"><strong>Fecha:</strong> {{fecha}}</div>
        <div class="field"><strong>Serie/Folio:</strong> {{serie}}/{{folio}}</div>
        <div class="field"><strong>Moneda:</strong> {{moneda_desc}}</div>
        {{tipo_cambio_block}}
      </div>
      <div>
        <div class="section-label">Pago</div>
        <div class="field"><strong>Forma:</strong> {{forma_pago_desc}}</div>
        <div class="field"><strong>Método:</strong> {{metodo_pago_desc}}</div>
      </div>
      <div>
        <div class="section-label">Importes</div>
        <div class="field"><strong>Subtotal:</strong> ${{subtotal}}</div>
      </div>
      <div>
        <div class="total-box">
          <div class="total-label">Total</div>
          <div class="total-amount">${{total}}</div>
        </div>
      </div>
    </div>
  </div>

</div>
</body>
</html>
"""


# ── API pública ───────────────────────────────────────────────────────────────

def get_html_template(template_id: str) -> str:
    """Lee el HTML guardado para un template_id, o devuelve el default."""
    path = HTML_TEMPLATES_DIR / f"{template_id}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return DEFAULT_HEADER_HTML


def save_html_template(template_id: str, html: str) -> None:
    """Guarda el HTML de un template en disco."""
    path = HTML_TEMPLATES_DIR / f"{template_id}.html"
    path.write_text(html, encoding="utf-8")


def _fill_placeholders(html: str, cfdi_data: dict, design_config: dict | None = None) -> str:
    """Sustituye {{placeholder}} en el HTML con datos reales del CFDI y configuración de diseño."""
    emisor   = cfdi_data.get("emisor", {})
    receptor = cfdi_data.get("receptor", {})
    totales  = cfdi_data.get("totales", {})
    timbre   = cfdi_data.get("timbre", {})

    brand        = (design_config or {}).get("brand", {})
    brand_color  = brand.get("color", "#1A365D")
    brand_accent = brand.get("accent", "#2B6CB0")
    logo_url     = brand.get("logo_url") or ""
    logo_block   = (
        f'<div class="logo-area"><img src="{logo_url}" /></div>'
        if logo_url else ""
    )

    replacements = {
        # Emisor
        "{{emisor_nombre}}":        emisor.get("nombre", ""),
        "{{emisor_rfc}}":           emisor.get("rfc", ""),
        "{{emisor_regimen}}":       emisor.get("regimen_desc", "") or emisor.get("regimen", ""),
        "{{emisor_regimen_desc}}":  emisor.get("regimen_desc", "") or emisor.get("regimen", ""),
        # Receptor
        "{{receptor_nombre}}":               receptor.get("nombre", ""),
        "{{receptor_rfc}}":                  receptor.get("rfc", ""),
        "{{receptor_uso}}":                  receptor.get("uso_desc", "") or receptor.get("uso", ""),
        "{{receptor_uso_desc}}":             receptor.get("uso_desc", "") or receptor.get("uso", ""),
        "{{receptor_regimen_desc}}":         receptor.get("regimen_receptor_desc", "") or receptor.get("regimen_fiscal_receptor", ""),
        "{{domicilio_fiscal_receptor}}":     receptor.get("domicilio_fiscal_receptor", ""),
        # Comprobante
        "{{fecha}}":                cfdi_data.get("fecha", ""),
        "{{serie}}":                cfdi_data.get("serie", ""),
        "{{folio}}":                cfdi_data.get("folio", ""),
        "{{moneda}}":               cfdi_data.get("moneda_desc", "") or cfdi_data.get("moneda", "MXN"),
        "{{moneda_desc}}":          cfdi_data.get("moneda_desc", "") or cfdi_data.get("moneda", "MXN"),
        "{{tipo_cambio_block}}":    (
            f'<div class="field"><strong>T.C.:</strong> {cfdi_data["tipo_cambio"]}</div>'
            if cfdi_data.get("tipo_cambio") and cfdi_data["tipo_cambio"] not in ("1", "1.0", "")
            else ""
        ),
        "{{forma_pago_desc}}":      cfdi_data.get("forma_pago_desc", ""),
        "{{metodo_pago_desc}}":     cfdi_data.get("metodo_pago_desc", ""),
        "{{lugar_expedicion}}":     cfdi_data.get("lugar_expedicion", ""),
        # Totales
        "{{total}}":                totales.get("total", ""),
        "{{subtotal}}":             totales.get("subtotal", ""),
        # Timbre
        "{{uuid}}":                 timbre.get("uuid", ""),
        "{{fecha_timbrado}}":       timbre.get("fecha_timbrado", ""),
        "{{rfc_prov_certif}}":      timbre.get("rfc_prov_certif", ""),
        "{{sello_sat}}":            timbre.get("sello_sat", ""),
        # Diseño
        "{{brand_color}}":          brand_color,
        "{{brand_accent}}":         brand_accent,
        "{{logo_block}}":           logo_block,
    }
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, str(value))

    # Retrocompatibilidad: colores hardcoded en templates guardados antes de la paleta dinámica
    if brand_color != "#1A365D" and "{{brand_color}}" not in html:
        html = html.replace("#1A365D", brand_color)
    if brand_accent != "#2B6CB0" and "{{brand_accent}}" not in html:
        html = html.replace("#2B6CB0", brand_accent)

    return html


def render_shell(html_template: str, cfdi_data: dict, design_config: dict | None = None) -> bytes:
    """Renderiza el header HTML con datos reales del CFDI. Sin caché de PDF (cada factura tiene datos únicos)."""
    filled = _fill_placeholders(html_template, cfdi_data, design_config)
    return HTML(string=filled, base_url=None).write_pdf(font_config=_get_font_config())


def render_shell_preview(html: str) -> bytes:
    """WeasyPrint en memoria, sin cache de PDF. Usado para live preview en el diseñador."""
    return HTML(string=html, base_url=None).write_pdf(font_config=_get_font_config())


def get_or_create_shell(template_id: str, html_template: str, cfdi_data: dict) -> bytes:
    """
    Devuelve bytes del shell PDF para este template_id + datos CFDI.

    Cache: se guarda por hash del html_template (la estructura).
    Los datos del CFDI (emisor/receptor/fecha) se rellenan en cada llamada
    sobre la estructura cacheada. Esto implica que el cache es por template,
    no por factura — correcto, ya que la estructura es la misma para todos.

    Si el diseño cambia (html_template distinto), se genera un nuevo shell.
    """
    # El html con datos reales (no se cachea el PDF con datos, sino la generación)
    filled_html = _fill_placeholders(html_template, cfdi_data)
    return HTML(string=filled_html, base_url=None).write_pdf()
