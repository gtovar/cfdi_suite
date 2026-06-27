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
  @page { size: A4; margin: 0; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 10px;
    color: #2D3748;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .top-bar { background: #1A365D; height: 8px; }

  .content { padding: 28px 32px 24px; }

  .doc-header {
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: 14px;
    margin-bottom: 20px;
  }
  .doc-title {
    font-size: 15px; font-weight: 700; color: #1A365D;
    text-transform: uppercase; letter-spacing: .5px;
  }
  .doc-subtitle {
    font-size: 8px; color: #A0AEC0; text-transform: uppercase;
    letter-spacing: 1px; margin-top: 3px;
  }

  .card {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 18px 20px;
    margin-bottom: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  }

  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }

  .section-label {
    font-size: 8px; font-weight: 700; color: #2B6CB0;
    text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px;
  }
  .entity-name { font-size: 11px; font-weight: 700; color: #1A365D; margin-bottom: 4px; }
  .field { color: #4A5568; line-height: 1.7; }
  .field strong { color: #2D3748; }

  .divider { border: none; border-top: 1px solid #E2E8F0; margin: 14px 0; }

  .total-box {
    background: #F0FFF4;
    border: 1px solid #9AE6B4;
    border-radius: 6px;
    padding: 10px 14px;
    text-align: center;
  }
  .total-label { font-size: 8px; color: #276749; text-transform: uppercase; font-weight: 700; }
  .total-amount { font-size: 17px; font-weight: 700; color: #276749; margin-top: 3px; }

  .uuid-bar {
    background: #F7FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 8px 14px;
  }
  .uuid-label { font-size: 7px; font-weight: 700; color: #2B6CB0; text-transform: uppercase; }
  .uuid-value {
    font-size: 8px; font-family: Courier, monospace;
    color: #4A5568; margin-top: 3px; word-break: break-all;
  }
</style>
</head>
<body>
<div class="top-bar"></div>
<div class="content">

  <div class="doc-header">
    <div class="doc-title">Comprobante Fiscal Digital por Internet</div>
    <div class="doc-subtitle">CFDI 4.0 — Representación Impresa</div>
  </div>

  <div class="card">
    <div class="grid-2">
      <div>
        <div class="section-label">Emisor</div>
        <div class="entity-name">{{emisor_nombre}}</div>
        <div class="field"><strong>RFC:</strong> {{emisor_rfc}}</div>
        <div class="field"><strong>Régimen:</strong> {{emisor_regimen}}</div>
      </div>
      <div>
        <div class="section-label">Receptor</div>
        <div class="entity-name">{{receptor_nombre}}</div>
        <div class="field"><strong>RFC:</strong> {{receptor_rfc}}</div>
        <div class="field"><strong>Uso CFDI:</strong> {{receptor_uso}}</div>
      </div>
    </div>

    <hr class="divider">

    <div class="grid-3">
      <div>
        <div class="section-label">Datos del Comprobante</div>
        <div class="field"><strong>Fecha:</strong> {{fecha}}</div>
        <div class="field"><strong>Serie/Folio:</strong> {{serie}}/{{folio}}</div>
        <div class="field"><strong>Moneda:</strong> {{moneda}}</div>
      </div>
      <div>
        <div class="section-label">Importes</div>
        <div class="field"><strong>Subtotal:</strong> ${{subtotal}}</div>
      </div>
      <div>
        <div class="total-box">
          <div class="total-label">Total</div>
          <div class="total-amount">{{moneda}} ${{total}}</div>
        </div>
      </div>
    </div>
  </div>

  <div class="uuid-bar">
    <div class="uuid-label">Folio Fiscal (UUID)</div>
    <div class="uuid-value">{{uuid}}</div>
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
    timbre   = cfdi_data.get("timbre", {})
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
        "{{uuid}}":            timbre.get("uuid", ""),
    }
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, str(value))
    return html


def render_shell(html_template: str, cfdi_data: dict) -> bytes:
    """Renderiza el header HTML con datos reales del CFDI. Sin caché (cada factura tiene datos únicos)."""
    filled = _fill_placeholders(html_template, cfdi_data)
    return HTML(string=filled, base_url=None).write_pdf()


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
