"""
Tests de pdf_pipeline / sample_data (Fase 1).

Determinismo: reportlab/weasyprint/pypdf embeben timestamps por defecto. Para el
test de equivalencia byte-a-byte se fija SOURCE_DATE_EPOCH + reportlab.invariant
(solo en el proceso de test — no toca producción). El fixture de equivalencia es
chico (< 2000 filas) → camino single-process, sin spawn.
"""
from __future__ import annotations

import os
# Debe fijarse ANTES de que weasyprint/reportlab generen su primer PDF.
os.environ["SOURCE_DATE_EPOCH"] = "0"
import reportlab.rl_config as _rl_config
_rl_config.invariant = 1

import io
from pathlib import Path

from pypdf import PdfReader

from backend.app.services import pdf_pipeline
from backend.app.services.canvas_service import parse_xml_to_rows
from backend.app.services.sample_data import generar_datos_ejemplo

_FIXTURES = Path(__file__).parent.parent / "test-fixtures"


def _es_pdf_valido(data: bytes) -> int:
    assert data[:5] == b"%PDF-", "no empieza con %PDF-"
    reader = PdfReader(io.BytesIO(data))
    n = len(reader.pages)
    assert n >= 1
    return n


# ── sample_data ────────────────────────────────────────────────────────────────

_CFDI_KEYS = {
    "fecha", "serie", "folio", "moneda", "forma_pago", "metodo_pago",
    "lugar_expedicion", "tipo_cambio", "totales", "emisor", "receptor",
    "timbre", "moneda_desc", "forma_pago_desc", "metodo_pago_desc",
    "impuestos", "retenciones", "verifica_url",
}
_ROW_KEYS = {"num_id", "cantidad", "clave_unidad", "descripcion",
             "valor_unitario", "descuento", "importe"}


def test_sample_data_shape_exacto():
    cfdi, rows = generar_datos_ejemplo()
    assert set(cfdi.keys()) == _CFDI_KEYS
    assert "_sello_8" not in cfdi
    assert set(cfdi["totales"].keys()) == {"subtotal", "descuento", "total"}
    assert set(cfdi["emisor"].keys()) == {"nombre", "rfc", "regimen", "regimen_desc"}
    assert set(cfdi["receptor"].keys()) == {
        "nombre", "rfc", "uso", "uso_desc", "domicilio_fiscal_receptor",
        "regimen_fiscal_receptor", "regimen_receptor_desc"}
    assert set(cfdi["timbre"].keys()) == {
        "uuid", "fecha_timbrado", "no_cert_sat", "rfc_prov_certif", "sello_sat"}
    for row in rows:
        assert set(row.keys()) == _ROW_KEYS


def test_sample_data_incluye_descuento_cero_y_positivo():
    _, rows = generar_datos_ejemplo(n_rows=6, con_descuento=True)
    descuentos = [float(r["descuento"]) for r in rows]
    assert any(d == 0 for d in descuentos)
    assert any(d > 0 for d in descuentos)


def test_sample_data_sin_descuento_todo_cero():
    _, rows = generar_datos_ejemplo(n_rows=4, con_descuento=False)
    assert all(float(r["descuento"]) == 0 for r in rows)


def test_sample_data_montos_dos_decimales():
    _, rows = generar_datos_ejemplo()
    for r in rows:
        for k in ("valor_unitario", "descuento", "importe"):
            assert r[k] == f"{float(r[k]):.2f}"


def test_sample_data_deterministico():
    a = generar_datos_ejemplo()
    b = generar_datos_ejemplo()
    assert a == b


# ── generate_from_data ──────────────────────────────────────────────────────────

def test_generate_from_data_default_produce_pdf_valido():
    cfdi, rows = generar_datos_ejemplo()
    pdf = pdf_pipeline.generate_from_data(cfdi, rows, template_id="default")
    _es_pdf_valido(pdf)


def test_generate_from_data_config_v2_produce_pdf_valido(tmp_path, monkeypatch):
    import json
    from backend.app.services import pdf_pipeline as PP
    design_dir = Path(PP.__file__).resolve().parents[2] / "templates" / "design"
    tmp = design_dir / "_test_v2_pipeline.json"
    tmp.write_text(json.dumps({
        "schema_version": 2,
        "brand": {"color": "#1A365D", "accent": "#2B6CB0"},
        "tabla": {
            "header_bg": "#1A365D", "even_bg": "#F8FAFC", "border": "#E2E8F0",
            "columns": [
                {"id": "desc", "field": "descripcion", "width": 240, "visible": True, "order": 0, "format": "text", "color": "#4A5568"},
                {"id": "imp",  "field": "importe",     "width": 90,  "visible": True, "order": 1, "format": "money", "color": "#2D3748", "emphasis": True},
            ],
            "reglas": [
                {"columna": "importe", "operador": "gt", "valor": "5000", "scope": "row", "estilo": {"color": "#B7791F"}},
            ],
        },
    }), encoding="utf-8")
    try:
        cfdi, rows = generar_datos_ejemplo()
        pdf = PP.generate_from_data(cfdi, rows, template_id="_test_v2_pipeline")
        _es_pdf_valido(pdf)
    finally:
        tmp.unlink(missing_ok=True)


# ── equivalencia generate(xml) == generate_from_data(*parse(xml)) ───────────────

def test_equivalencia_generate_vs_generate_from_data():
    xml = (_FIXTURES / "cfdv40-pfic.xml").read_bytes()
    a = pdf_pipeline.generate(xml, template_id="default")
    cfdi, rows = parse_xml_to_rows(xml)
    b = pdf_pipeline.generate_from_data(cfdi, rows, template_id="default")
    assert a == b, "generate(xml) debe ser byte-idéntico a generate_from_data(*parse(xml))"


# ── regresión: config legacy mantiene comportamiento (7 cols, gris/rojo) ────────

def test_regresion_legacy_sin_columns_ni_reglas():
    from backend.app.services import canvas_service as C
    # Sin config → 7 columnas legacy + regla implícita gris/rojo sobre descuento.
    cols = C._resolve_columns(None)
    assert len(cols) == 7
    rules = C._compile_rules(None)
    assert len(rules) == 1 and rules[0]["columna"] == "descuento"
    # Y el pipeline completo con datos de ejemplo renderiza sin error.
    cfdi, rows = generar_datos_ejemplo()
    pdf = pdf_pipeline.generate_from_data(cfdi, rows, template_id="default")
    _es_pdf_valido(pdf)
