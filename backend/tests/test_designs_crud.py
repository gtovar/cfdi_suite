"""
Fase 4 — CRUD de plantillas design (backend).

Aísla el estado en disco: monkeypatchea los directorios del router a tmp_path
(design/, html/, templates/ raíz), copiando el default.json/default.html reales
como punto de partida. Así los tests no dejan basura ni tocan las plantillas
productivas, y verifican la trampa de orden de rutas sin escribir en la raíz real.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.routers import templates as templates_router
except ModuleNotFoundError as error:  # pragma: no cover
    TestClient = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None

pytestmark = pytest.mark.skipif(
    TestClient is None, reason=f"fastapi no disponible: {_IMPORT_ERROR if TestClient is None else ''}"
)

_REAL_TEMPLATES = Path(templates_router.__file__).parent.parent.parent / "templates"
_REAL_DEFAULT_DESIGN = _REAL_TEMPLATES / "design" / "default.json"
_REAL_DEFAULT_HTML = _REAL_TEMPLATES / "html" / "default.html"


@pytest.fixture()
def dirs(tmp_path, monkeypatch):
    design = tmp_path / "design"
    html = tmp_path / "html"
    root = tmp_path / "templates"
    for d in (design, html, root):
        d.mkdir()

    (design / "default.json").write_bytes(_REAL_DEFAULT_DESIGN.read_bytes())
    if _REAL_DEFAULT_HTML.exists():
        (html / "default.html").write_bytes(_REAL_DEFAULT_HTML.read_bytes())

    monkeypatch.setattr(templates_router, "_DESIGN_DIR", design)
    monkeypatch.setattr(templates_router, "_HTML_DIR", html)
    monkeypatch.setattr(templates_router, "_TEMPLATES_DIR", root)
    return SimpleNamespace(design=design, html=html, root=root)


@pytest.fixture()
def client(dirs):
    return TestClient(app)


# ── GET /api/templates/designs ──────────────────────────────────────────────────

def test_listado_refleja_disco_y_default_primero(client, dirs):
    (dirs.design / "zeta.json").write_text('{"nombre": "Zeta"}', encoding="utf-8")
    (dirs.design / "alfa.json").write_text('{"nombre": "Alfa"}', encoding="utf-8")

    resp = client.get("/api/templates/designs")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["id"] == "default"  # default siempre primero
    assert [x["id"] for x in data[1:]] == ["alfa", "zeta"]  # resto alfabético por nombre
    assert all(set(x) == {"id", "nombre", "es_referencia"} for x in data)


def test_listado_fallbacks_y_salta_corruptos(client, dirs):
    (dirs.design / "sinmeta.json").write_text("{}", encoding="utf-8")
    (dirs.design / "corrupto.json").write_text("{ no json", encoding="utf-8")

    data = client.get("/api/templates/designs").json()
    ids = {x["id"] for x in data}
    assert "corrupto" not in ids  # corrupto saltado
    sinmeta = next(x for x in data if x["id"] == "sinmeta")
    assert sinmeta["nombre"] == "sinmeta" and sinmeta["es_referencia"] is False


# ── POST /api/templates/designs ─────────────────────────────────────────────────

def test_crear_con_nombre_genera_slug(client, dirs):
    resp = client.post("/api/templates/designs", json={"nombre": "Factura Águila"})
    assert resp.status_code == 201
    body = resp.json()
    assert body == {"id": "factura-aguila", "nombre": "Factura Águila", "es_referencia": False}
    creado = dirs.design / "factura-aguila.json"
    assert creado.exists()
    import json
    data = json.loads(creado.read_text(encoding="utf-8"))
    assert data["nombre"] == "Factura Águila" and data["es_referencia"] is False


def test_crear_colision_agrega_sufijo(client, dirs):
    r1 = client.post("/api/templates/designs", json={"nombre": "Repetida"})
    r2 = client.post("/api/templates/designs", json={"nombre": "Repetida"})
    r3 = client.post("/api/templates/designs", json={"nombre": "Repetida"})
    assert r1.json()["id"] == "repetida"
    assert r2.json()["id"] == "repetida-2"
    assert r3.json()["id"] == "repetida-3"


def test_crear_copia_html_de_la_base(client, dirs):
    client.post("/api/templates/designs", json={"nombre": "Con Header"})
    assert (dirs.html / "con-header.html").exists()
    assert (dirs.html / "con-header.html").read_bytes() == (dirs.html / "default.html").read_bytes()


def test_crear_base_inexistente_404(client, dirs):
    resp = client.post("/api/templates/designs", json={"nombre": "X", "base_id": "noexiste"})
    assert resp.status_code == 404


def test_crear_sin_nombre_400(client, dirs):
    assert client.post("/api/templates/designs", json={}).status_code == 400
    assert client.post("/api/templates/designs", json={"nombre": "   "}).status_code == 400


def test_crear_no_escribe_designs_json_en_raiz(client, dirs):
    """Trampa de orden de rutas: POST /designs NO debe caer en save_template."""
    resp = client.post("/api/templates/designs", json={"nombre": "Ruta OK"})
    assert resp.status_code == 201
    assert not (dirs.root / "designs.json").exists()


# ── POST /api/templates/{id}/duplicate ──────────────────────────────────────────

def test_duplicar_default_no_lo_pisa_byte_a_byte(client, dirs):
    original = (dirs.design / "default.json").read_bytes()
    resp = client.post("/api/templates/default/duplicate")
    assert resp.status_code == 201
    body = resp.json()
    assert body["nombre"] == "default (copia)"  # nombre original fallback = id
    assert body["es_referencia"] is False
    # default.json intacto byte a byte.
    assert (dirs.design / "default.json").read_bytes() == original
    assert (dirs.design / f"{body['id']}.json").exists()


def test_duplicar_copia_metadata_y_fuerza_es_referencia_false(client, dirs):
    import json
    ref = {"nombre": "Referencia Oficial", "es_referencia": True, "brand": {"color": "#112233"}}
    (dirs.design / "ref.json").write_text(json.dumps(ref), encoding="utf-8")

    resp = client.post("/api/templates/ref/duplicate", json={"nombre": "Mi Copia"})
    assert resp.status_code == 201
    body = resp.json()
    assert body == {"id": "mi-copia", "nombre": "Mi Copia", "es_referencia": False}
    data = json.loads((dirs.design / "mi-copia.json").read_text(encoding="utf-8"))
    assert data["es_referencia"] is False  # forzado, aunque el origen era referencia
    assert data["brand"] == {"color": "#112233"}  # contenido copiado


def test_duplicar_origen_inexistente_404(client, dirs):
    assert client.post("/api/templates/fantasma/duplicate").status_code == 404


def test_duplicar_no_pisa_existentes(client, dirs):
    # Duplica default varias veces: cada id es nuevo, ninguno se pisa.
    ids = {client.post("/api/templates/default/duplicate").json()["id"] for _ in range(3)}
    assert len(ids) == 3


# ── DELETE /api/templates/{id} ──────────────────────────────────────────────────

def test_borrar_elimina_ambos_archivos(client, dirs):
    client.post("/api/templates/designs", json={"nombre": "Borrable"})
    assert (dirs.design / "borrable.json").exists()
    assert (dirs.html / "borrable.html").exists()

    resp = client.delete("/api/templates/borrable")
    assert resp.status_code == 200
    assert not (dirs.design / "borrable.json").exists()
    assert not (dirs.html / "borrable.html").exists()


def test_borrar_default_400(client, dirs):
    resp = client.delete("/api/templates/default")
    assert resp.status_code == 400
    assert (dirs.design / "default.json").exists()  # intacto


def test_borrar_es_referencia_400(client, dirs):
    import json
    (dirs.design / "ref.json").write_text(json.dumps({"es_referencia": True}), encoding="utf-8")
    resp = client.delete("/api/templates/ref")
    assert resp.status_code == 400
    assert (dirs.design / "ref.json").exists()  # no se borró


def test_borrar_inexistente_404(client, dirs):
    assert client.delete("/api/templates/fantasma").status_code == 404


# ── Anti path-traversal ─────────────────────────────────────────────────────────

def test_delete_id_invalido_400_sin_tocar_disco(client, dirs):
    before = sorted(p.name for p in dirs.design.iterdir())
    # ids de un solo segmento con caracteres inválidos → 400 por regex (nunca
    # llegan a tocar disco). El caso "../evil" con separador se cubre vía base_id
    # (test_create_base_id_traversal_400_sin_crear_nada), ya que el cliente HTTP
    # normaliza los ".." del path antes del ruteo.
    assert client.delete("/api/templates/evil.json").status_code == 400
    assert client.delete("/api/templates/mal$id").status_code == 400
    assert sorted(p.name for p in dirs.design.iterdir()) == before


def test_create_base_id_traversal_400_sin_crear_nada(client, dirs):
    before = sorted(p.name for p in dirs.design.iterdir())
    resp = client.post("/api/templates/designs", json={"nombre": "X", "base_id": "../evil"})
    assert resp.status_code == 400
    assert sorted(p.name for p in dirs.design.iterdir()) == before
    # y no se creó nada fuera del design dir.
    assert not (dirs.root / "evil.json").exists()
