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
import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

from pypdf import PdfReader, PdfWriter

from .canvas_service import parse_xml_to_rows, render_conceptos
from .cpu_quota import MAX_POOL_WORKERS, default_pool_workers

# Cuántos procesos reales caben aquí. Se autodetecta de la cuota real de CPU
# (cpu_quota.py) en vez de adivinar con cpu_count() -- pero PDF_POOL_WORKERS sigue
# siendo una variable de entorno explícita para poder fijarlo a mano si algún día la
# autodetección no aplica (otro proveedor de nube, otro mecanismo de cgroups, etc.),
# mismo patrón de "override explícito disponible" que BATCH_JOB_SHARD_SIZE/THRESHOLD.
#
# Ojo con dos cosas que ya mordieron en el código anterior de este módulo:
# 1. os.getenv(key, default) solo usa `default` cuando la LLAVE está ausente, no
#    cuando está vacía -- si alguien pone PDF_POOL_WORKERS="" a mano, la llave SÍ
#    está presente, y un int("") sin atrapar tumbaría el arranque completo de la
#    app (esto pasa al importar el módulo, antes de servir una sola petición).
# 2. `default` se evalúa siempre, aunque la variable SÍ esté puesta -- por eso aquí
#    solo se llama a default_pool_workers() (que hace I/O real contra cgroups)
#    dentro del branch donde de verdad hace falta, no como argumento de getenv().
_pdf_pool_workers_env = os.getenv("PDF_POOL_WORKERS")
if _pdf_pool_workers_env is not None:
    try:
        PDF_POOL_WORKERS = int(_pdf_pool_workers_env)
    except ValueError:
        print(
            f"[pdf_pipeline] PDF_POOL_WORKERS={_pdf_pool_workers_env!r} no es un "
            "entero válido -- usando autodetección de cuota real de CPU en su lugar."
        )
        PDF_POOL_WORKERS = default_pool_workers()
    else:
        # Techo de seguridad también para el override manual -- un typo humano
        # (ej. de más un cero) no debe poder agotar la memoria del contenedor
        # levantando demasiados procesos WeasyPrint/reportlab/lxml.
        PDF_POOL_WORKERS = min(MAX_POOL_WORKERS, max(1, PDF_POOL_WORKERS))
else:
    PDF_POOL_WORKERS = default_pool_workers()

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
    max_workers=PDF_POOL_WORKERS,
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
    # NOTA (2026-07-22, code review): render_conceptos ya NO usa este valor para
    # paralelismo real -- ver el comentario de "workers" en su firma, en
    # canvas_service.py. Se sigue calculando/pasando por compatibilidad de firma,
    # no lo quites asumiendo que no hace nada; solo no esperes que cambiar
    # PDF_POOL_WORKERS acelere el render de facturas con miles de conceptos.
    n_workers = workers or PDF_POOL_WORKERS
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
