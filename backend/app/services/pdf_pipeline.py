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
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count, get_context

from pypdf import PdfReader, PdfWriter

from .canvas_service import parse_xml_to_rows, render_conceptos

# Pool de procesos persistente para aislar CADA generate() en su propio
# proceso (spawn) — no solo el de gRPC+fork (>2000 conceptos, ya resuelto
# en canvas_service). Encontrado 2026-07-11: bajo concurrency>1 real
# (canario, XMLs de Miniso reales), WeasyPrint/reportlab/lxml compartiendo
# el mismo proceso entre peticiones simultáneas corrompía heap nativo
# ("free(): invalid next size (fast)" en logs, seguido de signal 6) —
# WeasyPrint en particular corre SIEMPRE en el proceso que llama a
# generate(), sin importar cuántos conceptos tenga el XML, así que nunca
# estaba cubierto por el fix anterior.
# Persistente (no "with ProcessPoolExecutor(...) as ex" por llamada) para
# no pagar el costo de arrancar Python + reimportar WeasyPrint/reportlab en
# cada PDF — los workers quedan "calientes" tras las primeras peticiones.
PDF_PROCESS_POOL = ProcessPoolExecutor(
    max_workers=min(8, cpu_count()),
    mp_context=get_context("spawn"),
)


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

    Wrapper delgado: decodifica + parsea el XML (único paso exclusivo de
    producción) y delega el núcleo compartido a generate_from_data().
    Firma pública intacta — pdf.py y el worker ARQ la llaman posicionalmente.
    """
    if isinstance(xml_str, bytes):
        xml_str = xml_str.decode("utf-8", errors="replace")

    # 1. Parse XML (SAX, O(1) memoria)
    cfdi_data, rows = parse_xml_to_rows(xml_str)

    return generate_from_data(cfdi_data, rows, template_id, html_shell, workers)


def generate_from_data(
    cfdi_data: dict,
    rows: list[dict],
    template_id: str = "default",
    html_shell: str | None = None,
    workers: int | None = None,
    design_config: dict | None = None,
) -> bytes:
    """
    Núcleo compartido (pasos 2-6): dados los datos ya parseados, produce el PDF.

    Dos caminos convergen aquí y ejecutan EXACTAMENTE el mismo código:
      - producción:      parse_xml_to_rows(xml) → generate_from_data(...)
      - preview de diseño: generar_datos_ejemplo(...) → generate_from_data(...)

    `design_config`: si se pasa (preview con config en memoria, aún no guardada),
    se usa TAL CUAL como configuración de render en vez de cargar
    templates/design/{template_id}.json de disco. Cambio aditivo — los llamadores
    de producción no lo pasan y siguen leyendo de disco.

    Estructura:
      - Página 1: header HTML/CSS estampado en el tope + tabla canvas debajo
      - Páginas 2..N: continuación de la tabla en canvas streaming
      - Última página: footer con totales, UUID
    """
    # 2. Configuración de diseño: la inyectada en memoria tiene prioridad; si no,
    #    se carga de disco por template_id (camino de producción).
    if design_config is not None:
        render_config = design_config
    else:
        import json as _json
        from pathlib import Path as _Path
        _design_path = _Path(__file__).resolve().parents[2] / "templates" / "design" / f"{template_id}.json"
        render_config = _json.loads(_design_path.read_text()) if _design_path.exists() else None

    # 3. Header: WeasyPrint renderiza el template HTML del usuario
    from .shell_service import get_html_template, render_shell
    html_template = html_shell or get_html_template(template_id)
    header_pdf = render_shell(html_template, cfdi_data, render_config)

    # 4. Leer altura real del header para que canvas reserve exactamente ese espacio
    header_h = float(PdfReader(io.BytesIO(header_pdf)).pages[0].mediabox.height)
    HEADER_GAP = 8.0
    header_reserve = header_h + HEADER_GAP

    # 5. Canvas: tabla + footer, reservando header_reserve pts en el tope de pág 1
    n_workers = workers or min(8, cpu_count())
    body_pdf = render_conceptos(
        rows,
        cfdi_data=cfdi_data,
        workers=n_workers,
        skip_header_card=True,
        header_reserve=header_reserve,
        render_config=render_config,
    )

    # 6. Estampar header sobre página 1, pegar páginas 2+ sin cambio
    return _stamp_and_merge(header_pdf, body_pdf, header_reserve)
