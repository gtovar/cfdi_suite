"""
Test de equivalencia — el corazón de la Fase 2.

Prueba OBJETIVA de "lo que el usuario diseña es exactamente lo que se genera":
el PDF producido por llamada directa a generate_from_data debe ser idéntico al
producido vía el endpoint HTTP POST /api/templates/{id}/table-preview, para el
mismo design_config y los mismos datos de ejemplo.

Determinismo: reportlab/weasyprint/pypdf embeben timestamps por defecto. Se fija
SOURCE_DATE_EPOCH + reportlab.invariant (solo mientras corren los tests de este
módulo, ver fixture `_pdf_determinismo` abajo). El endpoint corre en el MISMO
proceso que la llamada directa (TestClient + asyncio.to_thread), así que
comparten esos flags → equivalencia a nivel BYTES. n_rows es chico (< 2000) →
camino single-process, sin spawn. Se incluye además una comprobación
estructural (páginas + texto extraído) como red de seguridad documental.
"""
from __future__ import annotations

import io
import os

import pytest
import reportlab.rl_config as _rl_config
from pypdf import PdfReader

try:
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.services.pdf_pipeline import generate_from_data
    from backend.app.services.sample_data import generar_datos_ejemplo
except ModuleNotFoundError as error:  # pragma: no cover
    TestClient = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None

pytestmark = pytest.mark.skipif(TestClient is None, reason=f"fastapi no disponible: {_IMPORT_ERROR if TestClient is None else ''}")


@pytest.fixture(autouse=True, scope="module")
def _pdf_determinismo():
    """Fija SOURCE_DATE_EPOCH + reportlab.invariant para los tests de este
    módulo y los restaura al terminar -- ver el docstring de la fixture
    homónima en test_pdf_pipeline.py para el porqué (zipfile.ZipInfo lee
    SOURCE_DATE_EPOCH; sin restaurar, contamina cualquier test posterior que
    cree un .zip en el mismo proceso de pytest)."""
    original_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    original_invariant = _rl_config.invariant
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    _rl_config.invariant = 1
    yield
    if original_epoch is None:
        os.environ.pop("SOURCE_DATE_EPOCH", None)
    else:
        os.environ["SOURCE_DATE_EPOCH"] = original_epoch
    _rl_config.invariant = original_invariant


_LEGACY = {
    "brand": {"color": "#5b1a1a", "accent": "#8f2323"},
    "tabla": {"header_bg": "#5b1a1a", "even_bg": "#f8f7f7", "border": "#e3dddd", "density": "compact"},
}

_V2_COLUMNS = {
    "schema_version": 2,
    "brand": {"color": "#1A365D", "accent": "#2B6CB0"},
    "tabla": {
        "header_bg": "#1A365D", "even_bg": "#F8FAFC", "border": "#E2E8F0", "density": "normal",
        "columns": [
            {"id": "desc", "label": "Descripcion", "field": "descripcion", "width": 240, "visible": True, "order": 0, "format": "text", "color": "#4A5568", "emphasis": False},
            {"id": "cant", "label": "Cant", "field": "cantidad", "width": 40, "visible": True, "order": 1, "format": "text", "color": "#4A5568", "emphasis": False},
            {"id": "importe", "label": "Importe", "field": "importe", "width": 90, "visible": True, "order": 2, "format": "money", "color": "#2D3748", "emphasis": True},
        ],
    },
}

_V2_REGLAS = {
    "schema_version": 2,
    "brand": {"color": "#1A365D", "accent": "#2B6CB0"},
    "tabla": {
        "header_bg": "#1A365D", "even_bg": "#F8FAFC", "border": "#E2E8F0", "density": "normal",
        "columns": [
            {"id": "desc", "label": "Descripcion", "field": "descripcion", "width": 240, "visible": True, "order": 0, "format": "text", "color": "#4A5568", "emphasis": False},
            {"id": "descto", "label": "Desc", "field": "descuento", "width": 60, "visible": True, "order": 1, "format": "money", "color": "#C53030", "emphasis": False},
            {"id": "importe", "label": "Importe", "field": "importe", "width": 90, "visible": True, "order": 2, "format": "money", "color": "#2D3748", "emphasis": True},
        ],
        "reglas": [
            {"columna": "descuento", "operador": "eq", "valor": "0", "scope": "cell", "estilo": {"color": "#A0AEC0"}},
            {"columna": "importe", "operador": "gt", "valor": "5000", "scope": "row", "estilo": {"color": "#B7791F"}},
        ],
    },
}


@pytest.fixture()
def client():
    return TestClient(app)


def _pages_and_text(pdf: bytes):
    reader = PdfReader(io.BytesIO(pdf))
    return len(reader.pages), [p.extract_text() for p in reader.pages]


def _direct(design_config, n_rows=6, con_descuento=True) -> bytes:
    cfdi_data, rows = generar_datos_ejemplo(n_rows, con_descuento)
    return generate_from_data(
        cfdi_data, rows, template_id="default", html_shell=None, design_config=design_config
    )


def _http(client, design_config, n_rows=6, con_descuento=True) -> bytes:
    resp = client.post(
        "/api/templates/default/table-preview",
        json={"design_config": design_config, "n_rows": n_rows, "con_descuento": con_descuento},
    )
    assert resp.status_code == 200, (resp.status_code, resp.text[:400])
    assert resp.headers["content-type"] == "application/pdf"
    return resp.content


def _assert_equivalente(client, design_config):
    direct = _direct(design_config)
    http = _http(client, design_config)
    assert direct[:5] == b"%PDF-" and http[:5] == b"%PDF-"
    # Equivalencia a nivel bytes (mismo código, mismo proceso, mismo determinismo).
    assert direct == http, "El PDF del endpoint difiere byte-a-byte del directo"
    # Red de seguridad estructural (páginas + texto extraído idénticos).
    assert _pages_and_text(direct) == _pages_and_text(http)


# ── equivalencia: los 3 escenarios requeridos ──────────────────────────────────

def test_equivalencia_config_default_legacy(client):
    _assert_equivalente(client, _LEGACY)


def test_equivalencia_config_v2_columns_custom(client):
    _assert_equivalente(client, _V2_COLUMNS)


def test_equivalencia_config_v2_con_reglas(client):
    _assert_equivalente(client, _V2_REGLAS)


def test_equivalencia_distinto_n_rows(client):
    direct = _direct(_V2_REGLAS, n_rows=12)
    http = _http(client, _V2_REGLAS, n_rows=12)
    assert direct == http


# ── el endpoint refleja la config (columnas/reglas) en el PDF ───────────────────

def test_preview_refleja_columnas_custom(client):
    pdf = _http(client, _V2_COLUMNS)
    _, texts = _pages_and_text(pdf)
    text = "\n".join(texts)
    # Headers reordenados de la config custom presentes; 'P.Unit'/'Unidad' (cols
    # default no incluidas) ausentes.
    assert "Descripcion" in text and "Cant" in text and "Importe" in text
    assert "P.Unit" not in text and "Unidad" not in text


# ── validación (defensa en profundidad) ────────────────────────────────────────

def test_preview_rechaza_config_invalida(client):
    resp = client.post("/api/templates/default/table-preview",
                       json={"design_config": {"brand": {"color": "NOThex"}}})
    assert resp.status_code == 400


def test_preview_v2_sin_columns_rechazada(client):
    resp = client.post("/api/templates/default/table-preview",
                       json={"design_config": {"schema_version": 2, "tabla": {"header_bg": "#1A365D"}}})
    assert resp.status_code == 400


def test_preview_sin_design_config_rechazada(client):
    resp = client.post("/api/templates/default/table-preview", json={})
    assert resp.status_code == 400


def test_preview_n_rows_fuera_de_rango_rechazada(client):
    for n in (0, 51, 999):
        resp = client.post("/api/templates/default/table-preview",
                           json={"design_config": _LEGACY, "n_rows": n})
        assert resp.status_code == 400, n
