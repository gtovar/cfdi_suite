"""
shell_service.py — Pre-render de header HTML con WeasyPrint.

El shell es el PDF de la página de encabezado (logo, emisor, receptor, metadata).
Se genera una vez por versión de template y se cachea en backend/shells/.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from weasyprint import HTML

SHELLS_DIR = Path(__file__).resolve().parents[2] / "shells"
SHELLS_DIR.mkdir(exist_ok=True)

HTML_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "html"
HTML_TEMPLATES_DIR.mkdir(exist_ok=True)


# ── Template HTML base para el header ─────────────────────────────────────────

DEFAULT_HEADER_HTML = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  @page { size: A4; margin: 24px; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Helvetica, Arial, sans-serif; font-size: 11px;
         color: #2D3748; -webkit-print-color-adjust: exact; print-color-adjust: exact; }

  .card {
    background: #fff;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 24px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
  }
  .card::before {
    content: "";
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 4px;
    background: linear-gradient(90deg, #1A365D 0%, #2B6CB0 100%);
  }

  .title { font-size: 20px; font-weight: 700; color: #1A365D;
           text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
  .subtitle { font-size: 9px; color: #A0AEC0; text-transform: uppercase;
              letter-spacing: 1px; margin-bottom: 18px; }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .block h3 { font-size: 10px; color: #2B6CB0; font-weight: 700;
              text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }
  .block p  { color: #4A5568; line-height: 1.6; margin-bottom: 2px; }
  .block strong { color: #1A365D; }

  .badge {
    display: inline-block;
    background: #EBF8FF; color: #2B6CB0;
    border: 1px solid #BEE3F8;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 9px; font-weight: 600; font-family: monospace;
    margin-top: 4px;
  }
  .total-badge {
    display: inline-block;
    background: #F0FFF4; color: #276749;
    border: 1px solid #9AE6B4;
    border-radius: 6px;
    padding: 3px 10px;
    font-weight: 700; font-size: 13px;
  }
</style>
</head>
<body>
<div class="card">
  <div class="title">Comprobante Fiscal Digital por Internet</div>
  <div class="subtitle">CFDI 4.0 — Representación Impresa</div>

  <div class="grid">
    <div class="block">
      <h3>Emisor</h3>
      <p><strong>{{emisor_nombre}}</strong></p>
      <p>RFC: {{emisor_rfc}}</p>
      <p>Régimen: {{emisor_regimen}}</p>
    </div>
    <div class="block">
      <h3>Receptor</h3>
      <p><strong>{{receptor_nombre}}</strong></p>
      <p>RFC: {{receptor_rfc}}</p>
      <p>Uso CFDI: {{receptor_uso}}</p>
    </div>
    <div class="block">
      <h3>Datos del Comprobante</h3>
      <p>Fecha: {{fecha}}</p>
      <p>Serie / Folio: {{serie}} / {{folio}}</p>
      <p>Moneda: {{moneda}}</p>
    </div>
    <div class="block">
      <h3>Total</h3>
      <p class="total-badge">{{moneda}} ${{total}}</p>
      <p style="margin-top:6px">Subtotal: ${{subtotal}}</p>
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


def _shell_path(template_id: str, html_hash: str) -> Path:
    return SHELLS_DIR / f"{template_id}_{html_hash}.pdf"


def _fill_placeholders(html: str, cfdi_data: dict) -> str:
    """Sustituye {{placeholder}} en el HTML con datos reales del CFDI."""
    emisor   = cfdi_data.get("emisor", {})
    receptor = cfdi_data.get("receptor", {})
    totales  = cfdi_data.get("totales", {})
    replacements = {
        "{{emisor_nombre}}":   emisor.get("nombre", ""),
        "{{emisor_rfc}}":      emisor.get("rfc", ""),
        "{{emisor_regimen}}":  emisor.get("regimen", ""),
        "{{receptor_nombre}}": receptor.get("nombre", ""),
        "{{receptor_rfc}}":    receptor.get("rfc", ""),
        "{{receptor_uso}}":    receptor.get("uso", ""),
        "{{fecha}}":           cfdi_data.get("fecha", ""),
        "{{serie}}":           cfdi_data.get("serie", ""),
        "{{folio}}":           cfdi_data.get("folio", ""),
        "{{moneda}}":          cfdi_data.get("moneda", "MXN"),
        "{{total}}":           totales.get("total", ""),
        "{{subtotal}}":        totales.get("subtotal", ""),
    }
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, str(value))
    return html


def render_shell_preview(html: str) -> bytes:
    """WeasyPrint en memoria, sin cache. Usado para live preview en el diseñador."""
    return HTML(string=html, base_url=None).write_pdf()


def get_or_create_shell(template_id: str, html_template: str, cfdi_data: dict) -> bytes:
    """
    Devuelve bytes del shell PDF para este template_id + datos CFDI.

    Cache: se guarda por hash del html_template (la estructura).
    Los datos del CFDI (emisor/receptor/fecha) se rellenan en cada llamada
    sobre la estructura cacheada. Esto implica que el cache es por template,
    no por factura — correcto, ya que la estructura es la misma para todos.

    Si el diseño cambia (html_template distinto), se genera un nuevo shell.
    """
    html_hash = hashlib.md5(html_template.encode(), usedforsecurity=False).hexdigest()[:12]
    shell_path = _shell_path(template_id, html_hash)

    # El html con datos reales (no se cachea el PDF con datos, sino la generación)
    filled_html = _fill_placeholders(html_template, cfdi_data)
    return HTML(string=filled_html, base_url=None).write_pdf()
