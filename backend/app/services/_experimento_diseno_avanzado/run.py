"""
run.py — Ejecuta el pipeline de dos motores (WeasyPrint header + reportlab cuerpo)
para las variantes del experimento y produce PDFs + PNGs de inspección.

Uso (desde ~/Documents/cfdi_suite/backend):
    .venv/bin/python -m app.services._experimento_diseno_avanzado.run
"""
from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader

from ..canvas_service import parse_xml_to_rows
from . import canvas_adv, gen_data
from . import header_service_adv as H

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def generate_variant(name: str, params: dict) -> Path:
    xml = gen_data.build_xml(**params)
    (OUT / f"{name}.xml").write_text(xml, encoding="utf-8")

    cfdi_data, rows = parse_xml_to_rows(xml)

    header_pdf = H.render_header(cfdi_data)
    header_h = float(PdfReader(io.BytesIO(header_pdf)).pages[0].mediabox.height)
    header_reserve = header_h + 8.0

    body_pdf = canvas_adv.render_body(rows, cfdi_data, header_reserve=header_reserve)
    final_pdf = canvas_adv.stamp_and_merge(header_pdf, body_pdf)

    out_pdf = OUT / f"{name}.pdf"
    out_pdf.write_bytes(final_pdf)

    n_pages = len(PdfReader(io.BytesIO(final_pdf)).pages)
    print(f"  {name:26s} -> {out_pdf.name}  ({n_pages} págs, {len(final_pdf)//1024} KB, "
          f"header={header_h:.0f}pt, conceptos={len(rows)})")
    return out_pdf


def main() -> None:
    print("Generando variantes del experimento de diseño avanzado (motor B):")
    for name, params in gen_data.VARIANTS:
        generate_variant(name, params)
    print(f"\nPDFs en: {OUT}")


if __name__ == "__main__":
    main()
