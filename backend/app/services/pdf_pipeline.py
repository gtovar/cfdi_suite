"""
pdf_pipeline.py — Orquestador de las tres capas XML→PDF.

Flujo:
  1. Parse XML (SAX, O(1) memoria)
  2. Header HTML → WeasyPrint (página 1 — diseñable por el usuario)
  3. Conceptos → rl_canvas page-streaming (páginas 2..N, O(N), rápido)
  4. Footer inline en el último chunk de canvas
  5. Merge: [header_pdf] + [body_pdf] con pypdf
"""
from __future__ import annotations

import io
from multiprocessing import cpu_count

from pypdf import PdfReader, PdfWriter

from .canvas_service import parse_xml_to_rows, render_conceptos


def _merge(parts: list[bytes]) -> bytes:
    writer = PdfWriter()
    for part in parts:
        if not part:
            continue
        reader = PdfReader(io.BytesIO(part))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def generate(
    xml_str: str | bytes,
    template_id: str = "default",
    html_shell: str | None = None,
    workers: int | None = None,
) -> bytes:
    """
    Genera un PDF completo a partir de un XML CFDI.

    Estructura:
      - Página 1: header HTML/CSS (WeasyPrint) — editable desde Templates PDF
      - Páginas 2..N: tabla de conceptos en canvas streaming
      - Última página: footer con totales, UUID
    """
    if isinstance(xml_str, bytes):
        xml_str = xml_str.decode("utf-8", errors="replace")

    # 1. Parse XML (SAX, O(1) memoria)
    cfdi_data, rows = parse_xml_to_rows(xml_str)

    # 2. Header: WeasyPrint renderiza el template HTML guardado por el usuario
    from .shell_service import get_html_template, render_shell
    html_template = html_shell or get_html_template(template_id)
    header_pdf = render_shell(html_template, cfdi_data)

    # 3. Cuerpo: canvas streaming, sin el card de encabezado (ya viene de WeasyPrint)
    n_workers = workers or min(8, cpu_count())
    body_pdf = render_conceptos(rows, cfdi_data=cfdi_data, workers=n_workers, skip_header_card=True)

    # 4. Merge: [header page] + [tabla + footer]
    return _merge([header_pdf, body_pdf])
