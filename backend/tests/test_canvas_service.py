"""
Tests de canvas_service — columnas configurables, reglas condicionales y
operadores (Fase 1). Contrato: docs/plan_editor_completo_B/fase0-resultado.md.
"""
from __future__ import annotations

from reportlab.lib import colors as rl_colors

from backend.app.services import canvas_service as C


# ── _resolve_columns ───────────────────────────────────────────────────────────

def test_resolve_columns_sin_columns_devuelve_legacy():
    cols = C._resolve_columns(None)
    assert [c["field"] for c in cols] == list(C.FIELD_ENUM)
    assert cols is C._LEGACY_COLUMNS
    # colores/truncado legacy exactos
    assert cols[0]["max_chars"] == 11          # num_id
    assert all(c["max_chars"] == 24 for c in cols[1:])
    assert cols[5]["color"] == C.C_RED         # descuento rojo default
    assert cols[6]["emphasis"] is True         # importe bold


def test_resolve_columns_vacio_tabla_es_legacy():
    assert C._resolve_columns({"tabla": {}}) is C._LEGACY_COLUMNS
    assert C._resolve_columns({"tabla": {"columns": []}}) is C._LEGACY_COLUMNS


def test_resolve_columns_filtra_visible_y_ordena():
    rc = {"tabla": {"columns": [
        {"id": "a", "field": "importe",     "width": 50, "visible": True,  "order": 2},
        {"id": "b", "field": "descripcion", "width": 100, "visible": False, "order": 1},
        {"id": "c", "field": "cantidad",    "width": 30, "visible": True,  "order": 0},
    ]}}
    cols = C._resolve_columns(rc)
    # oculta 'descripcion' fuera; orden por 'order': cantidad(0), importe(2)
    assert [c["field"] for c in cols] == ["cantidad", "importe"]


def test_resolve_columns_truncado_derivado_del_ancho():
    rc = {"tabla": {"columns": [
        {"id": "d", "field": "descripcion", "width": 175, "visible": True, "order": 0},
    ]}}
    col = C._resolve_columns(rc)[0]
    assert col["max_chars"] == int(175 / 5.5)   # ≈ 31 (corrimiento aceptado v2)


# ── operadores ─────────────────────────────────────────────────────────────────

def test_op_eq_numerico_y_string():
    assert C._op_eq("0.00", "0") is True        # coacción numérica
    assert C._op_eq("10.0", "10") is True
    assert C._op_eq("abc", "abc") is True        # cae a string
    assert C._op_eq("abc", "abd") is False


def test_op_neq():
    assert C._op_neq("0.00", "0") is False
    assert C._op_neq("abc", "abd") is True


def test_op_comparadores_numericos():
    assert C._op_gt("5000.01", "5000") is True
    assert C._op_gt("9.00", "10000.00") is False   # NO comparación de string
    assert C._op_lt("9", "10000") is True
    assert C._op_gte("10", "10") is True
    assert C._op_lte("10", "10") is True


def test_op_comparadores_no_numericos_no_matchean():
    assert C._op_gt("abc", "5") is False
    assert C._op_lt("5", "abc") is False
    assert C._op_gte("abc", "abc") is False


def test_op_none_nunca_lanza():
    assert C._op_eq(None, "0") is False or C._op_eq(None, "0") is True  # no excepción
    assert C._op_gt(None, "5") is False
    assert C._op_lt(None, None) is False
    assert C._op_contains(None, "x") is False


def test_op_contains():
    assert C._op_contains("hola mundo", "mundo") is True
    assert C._op_contains("hola", "xyz") is False


# ── _compile_rules ─────────────────────────────────────────────────────────────

def test_compile_rules_sin_reglas_legacy_implicita():
    rules = C._compile_rules(None)
    assert len(rules) == 1
    r = rules[0]
    assert r["columna"] == "descuento"
    assert r["op"] is C._op_eq
    assert r["valor"] == "0"
    assert r["scope"] == "cell"
    assert r["color"] == C.C_MUTED


def test_compile_rules_v2_sin_reglas_es_vacio():
    rc = {"tabla": {"columns": [{"id": "a", "field": "importe", "width": 50, "visible": True, "order": 0}]}}
    assert C._compile_rules(rc) == []


def test_compile_rules_scope_default_cell():
    rc = {"tabla": {"reglas": [
        {"columna": "importe", "operador": "gt", "valor": "100", "estilo": {"color": "#B7791F"}},
    ]}}
    rules = C._compile_rules(rc)
    assert rules[0]["scope"] == "cell"           # scope ausente → cell
    assert rules[0]["op"] is C._op_gt
    assert rules[0]["color"] == rl_colors.HexColor("#B7791F")


def test_compile_rules_operador_invalido_se_ignora():
    rc = {"tabla": {"reglas": [
        {"columna": "importe", "operador": "??", "valor": "1", "estilo": {"color": "#000000"}},
    ]}}
    assert C._compile_rules(rc) == []


# ── precedencia por celda (contrato 1.3, ejemplo con scopes mixtos) ─────────────

def test_precedencia_scopes_mixtos():
    # R1 descuento eq 0 cell gris ; R2 importe gt 5000 row rojo
    rc = {"tabla": {"reglas": [
        {"columna": "descuento", "operador": "eq", "valor": "0", "scope": "cell", "estilo": {"color": "#A0AEC0"}},
        {"columna": "importe",   "operador": "gt", "valor": "5000", "scope": "row", "estilo": {"color": "#C53030"}},
    ]}}
    rules = C._compile_rules(rc)
    gris = rl_colors.HexColor("#A0AEC0")
    rojo = rl_colors.HexColor("#C53030")
    default = C.C_TEXT

    row = {"descuento": "0", "importe": "10000"}
    matched = C._match_rules(rules, row)
    # ambas condiciones matchean
    assert len(matched) == 2
    # celda descuento → gris (R1 la cubre primero, es cell de su columna)
    assert C._cell_color("descuento", default, matched) == gris
    # resto de la fila → rojo (R2 row cubre; R1 cell no cubre otras celdas)
    assert C._cell_color("importe", default, matched) == rojo
    assert C._cell_color("cantidad", default, matched) == rojo


def test_precedencia_row_no_anula_cell_previa():
    # Verifica que una regla row posterior NO pisa la celda cubierta por cell previa
    rc = {"tabla": {"reglas": [
        {"columna": "descuento", "operador": "eq", "valor": "0", "scope": "cell", "estilo": {"color": "#A0AEC0"}},
        {"columna": "importe",   "operador": "gt", "valor": "5000", "scope": "row", "estilo": {"color": "#C53030"}},
    ]}}
    rules = C._compile_rules(rc)
    row = {"descuento": "0", "importe": "10000"}
    matched = C._match_rules(rules, row)
    assert C._cell_color("descuento", C.C_TEXT, matched) == rl_colors.HexColor("#A0AEC0")


def test_cell_color_sin_match_usa_default():
    row = {"descuento": "100.00", "importe": "300"}
    rc = {"tabla": {"reglas": [
        {"columna": "importe", "operador": "gt", "valor": "5000", "scope": "row", "estilo": {"color": "#C53030"}},
    ]}}
    matched = C._match_rules(C._compile_rules(rc), row)
    assert matched == []
    assert C._cell_color("importe", C.C_DARK, matched) == C.C_DARK


def test_legacy_implicita_reproduce_gris_rojo():
    rules = C._compile_rules(None)   # regla implícita descuento eq 0 cell gris
    cols = C._resolve_columns(None)
    default_descuento = cols[5]["color"]         # rojo
    # descuento 0 → gris en la celda de descuento
    m0 = C._match_rules(rules, {"descuento": "0.00"})
    assert C._cell_color("descuento", default_descuento, m0) == C.C_MUTED
    # descuento > 0 → sin match → rojo default de la columna
    m1 = C._match_rules(rules, {"descuento": "100.10"})
    assert m1 == []
    assert C._cell_color("descuento", default_descuento, m1) == C.C_RED


# ── _validate_design (vive en el router; contrato 1.6) ─────────────────────────

import pytest
from fastapi import HTTPException

from backend.app.routers.templates import _validate_design


def _v2_valido():
    return {
        "schema_version": 2,
        "brand": {"color": "#1A365D", "accent": "#2B6CB0", "logo_url": None},
        "tabla": {
            "header_bg": "#1A365D", "even_bg": "#F8FAFC", "border": "#E2E8F0",
            "columns": [
                {"id": "desc", "field": "descripcion", "width": 175, "visible": True, "order": 0, "format": "text", "color": "#4A5568"},
                {"id": "imp",  "field": "importe",     "width": 54,  "visible": True, "order": 1, "format": "money", "color": "#2D3748", "emphasis": True},
            ],
            "reglas": [
                {"columna": "importe", "operador": "gt", "valor": "5000", "scope": "row", "estilo": {"color": "#C53030"}},
            ],
        },
        "cierre": {"show_uuid": True},
    }


def test_validate_design_v2_valido_pasa():
    _validate_design(_v2_valido())            # no lanza


def test_validate_design_legacy_sin_columns_pasa():
    legacy = {"brand": {"color": "#5b1a1a", "accent": "#8f2323"},
              "tabla": {"header_bg": "#5b1a1a", "even_bg": "#f8f7f7", "border": "#e3dddd", "density": "compact"}}
    _validate_design(legacy)                  # no lanza (sin schema_version, sin columns)


def test_validate_design_v2_sin_columns_falla():
    body = {"schema_version": 2, "tabla": {"header_bg": "#1A365D"}}
    with pytest.raises(HTTPException) as e:
        _validate_design(body)
    assert e.value.status_code == 400


def test_validate_design_hex_invalido_falla():
    body = _v2_valido()
    body["brand"]["color"] = "1A365D"          # sin '#'
    with pytest.raises(HTTPException) as e:
        _validate_design(body)
    assert e.value.status_code == 400


def test_validate_design_width_no_positivo_falla():
    body = _v2_valido()
    body["tabla"]["columns"][0]["width"] = 0
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_suma_anchos_excede_falla():
    body = _v2_valido()
    body["tabla"]["columns"][0]["width"] = 500
    body["tabla"]["columns"][1]["width"] = 500      # suma 1000 > 523.28
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_ids_duplicados_falla():
    body = _v2_valido()
    body["tabla"]["columns"][1]["id"] = "desc"       # id repetido
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_sin_visibles_falla():
    body = _v2_valido()
    for c in body["tabla"]["columns"]:
        c["visible"] = False
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_field_fuera_de_enum_falla():
    body = _v2_valido()
    body["tabla"]["columns"][0]["field"] = "no_existe"
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_format_invalido_falla():
    body = _v2_valido()
    body["tabla"]["columns"][0]["format"] = "html"
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_regla_columna_inexistente_falla():
    body = _v2_valido()
    body["tabla"]["reglas"][0]["columna"] = "cantidad"   # no está en columns
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_operador_invalido_falla():
    body = _v2_valido()
    body["tabla"]["reglas"][0]["operador"] = "matches"
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_scope_invalido_falla():
    body = _v2_valido()
    body["tabla"]["reglas"][0]["scope"] = "column"
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_contains_sobre_money_falla():
    body = _v2_valido()
    body["tabla"]["reglas"][0] = {"columna": "importe", "operador": "contains", "valor": "5",
                                  "scope": "cell", "estilo": {"color": "#C53030"}}
    with pytest.raises(HTTPException):
        _validate_design(body)


def test_validate_design_demasiadas_reglas_falla():
    body = _v2_valido()
    body["tabla"]["reglas"] = [body["tabla"]["reglas"][0]] * 4
    with pytest.raises(HTTPException):
        _validate_design(body)
