"""
pdf_pipeline.py — Orquestador de las tres capas XML→PDF.

Flujo:
  1. Parse XML (SAX, O(1) memoria)
  2. Shell HTML → WeasyPrint (header, 1 página, datos del CFDI)
  3. Conceptos → rl_canvas page-streaming (N páginas, rápido)
  4. Footer → rl_canvas (totales, impuestos, sello, 1-2 páginas)
  5. Merge: [shell] + [conceptos] + [footer] con pypdf
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
      - Página 1: card de encabezado (emisor/receptor/datos/total) + tabla de conceptos
      - Páginas 2..N: continuación de la tabla
      - Última página: footer con totales consolidados, UUID
    """
    if isinstance(xml_str, bytes):
        xml_str = xml_str.decode("utf-8", errors="replace")

    # 1. Parse XML (SAX, O(1) memoria)
    cfdi_data, rows = parse_xml_to_rows(xml_str)

    # 2. Todo en un solo PDF: header card + conceptos + footer inline
    n_workers = workers or min(8, cpu_count())
    return render_conceptos(rows, cfdi_data=cfdi_data, workers=n_workers)
