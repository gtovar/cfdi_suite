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


def _stamp_and_merge(header_pdf: bytes, body_pdf: bytes, header_reserve: float) -> bytes:
    """
    Estampa el header HTML sobre la parte superior de la página 1 del canvas.
    Páginas 2+ se pasan tal cual. Resultado: header + tabla en la misma página 1.
    """
    from pypdf import Transformation

    hr = PdfReader(io.BytesIO(header_pdf))
    br = PdfReader(io.BytesIO(body_pdf))

    header_page = hr.pages[0]
    header_h = float(header_page.mediabox.height)
    body_page_1 = br.pages[0]
    body_h = float(body_page_1.mediabox.height)

    writer = PdfWriter()

    # Página 1: canvas como base + header HTML encima (translado al tope de la página)
    writer.add_page(body_page_1)
    p1 = writer.pages[0]
    p1.merge_transformed_page(
        header_page,
        Transformation().translate(ty=body_h - header_h),
        over=True,
    )

    # Páginas 2+: canvas sin cambios
    for page in br.pages[1:]:
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
      - Página 1: header HTML/CSS estampado en el tope + tabla canvas debajo
      - Páginas 2..N: continuación de la tabla en canvas streaming
      - Última página: footer con totales, UUID
    """
    if isinstance(xml_str, bytes):
        xml_str = xml_str.decode("utf-8", errors="replace")

    # 1. Parse XML (SAX, O(1) memoria)
    cfdi_data, rows = parse_xml_to_rows(xml_str)

    # 2. Header: WeasyPrint renderiza el template HTML del usuario
    from .shell_service import get_html_template, render_shell
    html_template = html_shell or get_html_template(template_id)
    header_pdf = render_shell(html_template, cfdi_data)

    # 3. Leer altura real del header para que canvas reserve exactamente ese espacio
    header_h = float(PdfReader(io.BytesIO(header_pdf)).pages[0].mediabox.height)
    HEADER_GAP = 8.0
    header_reserve = header_h + HEADER_GAP

    # 4. Canvas: tabla + footer, reservando header_reserve pts en el tope de pág 1
    n_workers = workers or min(8, cpu_count())
    body_pdf = render_conceptos(
        rows,
        cfdi_data=cfdi_data,
        workers=n_workers,
        skip_header_card=True,
        header_reserve=header_reserve,
    )

    # 5. Estampar header sobre página 1, pegar páginas 2+ sin cambio
    return _stamp_and_merge(header_pdf, body_pdf, header_reserve)
