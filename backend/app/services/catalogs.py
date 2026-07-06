"""
catalogs.py — Acceso rápido a catálogos SAT desde la DB de satcfdi.

Catálogos pequeños (<300 filas): se precargan completos en memoria al primer uso.
ClaveProdServ (52k filas): consulta individual con lru_cache.
Spawn-safe: la conexión SQLite se re-crea por proceso.
"""
from __future__ import annotations

import pickle
import sqlite3
from functools import lru_cache

_conn: sqlite3.Connection | None = None
_PREFIX = "C756_"


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        import satcfdi.catalogs as _cat
        _conn = _cat.conn
    return _conn


def _load_all(table: str) -> dict[str, str]:
    c = _get_conn().cursor()
    c.execute(f"SELECT key, value FROM {_PREFIX}{table}")
    result: dict[str, str] = {}
    for k, v in c.fetchall():
        val = pickle.loads(v)
        result[str(pickle.loads(k))] = str(val[0] if isinstance(val, list) else val)
    return result


_SMALL: dict[str, dict[str, str]] = {}
_BIG = {"c_ClaveProdServ", "c_CodigoPostal", "c_Colonia", "c_Municipio", "c_Localidad"}


def _small(table: str) -> dict[str, str]:
    if table not in _SMALL:
        _SMALL[table] = _load_all(table)
    return _SMALL[table]


@lru_cache(maxsize=4096)
def _lookup_big(table: str, code: str) -> str:
    c = _get_conn().cursor()
    c.execute(f"SELECT value FROM {_PREFIX}{table} WHERE key = ?",
              (pickle.dumps(code, protocol=4),))
    row = c.fetchone()
    if not row:
        return ""
    val = pickle.loads(row[0])
    return str(val[0] if isinstance(val, list) else val)


def describe(table: str, code: str) -> str:
    """Descripción de un código SAT. Retorna '' si no existe."""
    if not code:
        return ""
    try:
        if table in _BIG:
            return _lookup_big(table, code)
        return _small(table).get(code, "")
    except Exception:
        return ""


def fmt_code(table: str, code: str) -> str:
    """'code - Descripción' o 'code' si no hay descripción."""
    if not code:
        return ""
    desc = describe(table, code)
    return f"{code} - {desc}" if desc else code
