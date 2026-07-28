"""
catalogs.py — Acceso rápido a catálogos SAT desde la DB de satcfdi.

Catálogos pequeños (<300 filas): se precargan completos en memoria al primer uso.
ClaveProdServ (52k filas): consulta individual con lru_cache.
Spawn-safe: la conexión SQLite se re-crea por proceso.
"""
from __future__ import annotations

import pickle  # La DB de satcfdi serializa con pickle, no con json.
#   Los datos vienen del paquete satcfdi instalado (no de input del usuario),
#   por lo que no hay superficie de ataque de deserialización en runtime:
#   la DB es de solo lectura en producción (RO en Cloud Run, sin write path)
#   y el código que la usa no acepta bytes del exterior.
import sqlite3
import hashlib
from functools import lru_cache
from pathlib import Path

_conn: sqlite3.Connection | None = None
_PREFIX = "C756_"

# Sólo son los catálogos que el renderer solicita hoy. El identificador no
# puede parametrizarse en SQLite: validarlo antes de interpolarlo es obligatorio.
_ALLOWED_TABLES = frozenset({
    "c_ClaveUnidad", "c_RegimenFiscal", "c_UsoCFDI", "c_Moneda",
    "c_FormaPago", "c_MetodoPago",
})
_BIG = frozenset({"c_ClaveProdServ", "c_CodigoPostal", "c_Colonia", "c_Municipio", "c_Localidad"})
_CATALOG_DB_EXPECTED_SIZE = 45_367_296
# Hash público de integridad, no credencial. Debe rotar junto con satcfdi.
_CATALOG_DB_EXPECTED_SHA256 = "9f257048a3fdd9b9306728c518073b34297c50a368eb4ffa7d35d158b749728b"  # pragma: allowlist secret


class CatalogIntegrityError(RuntimeError):
    """La DB empaquetada de satcfdi no coincide con la versión aprobada."""


def _catalog_db_path() -> Path:
    import satcfdi.catalogs as catalogs
    return Path(catalogs.__file__).with_name("catalogs.db")


def _verify_catalog_db(path: Path) -> None:
    """Autentica el artefacto antes de que cualquier pickle sea deserializado."""
    if path.stat().st_size != _CATALOG_DB_EXPECTED_SIZE:
        raise CatalogIntegrityError("Tamaño inesperado de la DB de catálogos satcfdi")
    with path.open("rb") as db_file:
        digest = hashlib.file_digest(db_file, "sha256").hexdigest()
    if digest != _CATALOG_DB_EXPECTED_SHA256:
        raise CatalogIntegrityError("Hash inesperado de la DB de catálogos satcfdi")


def _validate_catalog_table(table: str) -> None:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Catálogo SAT no permitido: {table}")


def _trusted_pickle_loads(payload: bytes):
    """El payload se acepta sólo después de verificar la DB de paquete fija."""
    # `_verify_catalog_db` autentica el origen antes de deserializar.
    return pickle.loads(payload)  # nosec B301


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        import satcfdi.catalogs as _cat
        _verify_catalog_db(_catalog_db_path())
        _conn = _cat.conn
    return _conn


def _load_all(table: str) -> dict[str, str]:
    _validate_catalog_table(table)
    c = _get_conn().cursor()
    # `table` pasó `_validate_catalog_table`.
    c.execute(f"SELECT key, value FROM {_PREFIX}{table}")  # nosec B608
    result: dict[str, str] = {}
    for k, v in c.fetchall():
        val = _trusted_pickle_loads(v)
        result[str(_trusted_pickle_loads(k))] = str(val[0] if isinstance(val, list) else val)
    return result


_SMALL: dict[str, dict[str, str]] = {}


def _small(table: str) -> dict[str, str]:
    if table not in _SMALL:
        _SMALL[table] = _load_all(table)
    return _SMALL[table]


@lru_cache(maxsize=4096)
def _lookup_big(table: str, code: str) -> str:
    _validate_catalog_table(table)
    c = _get_conn().cursor()
    # `table` pasó `_validate_catalog_table`.
    c.execute(f"SELECT value FROM {_PREFIX}{table} WHERE key = ?",  # nosec B608
              (pickle.dumps(code, protocol=4),))
    row = c.fetchone()
    if not row:
        return ""
    val = _trusted_pickle_loads(row[0])
    return str(val[0] if isinstance(val, list) else val)


def describe(table: str, code: str) -> str:
    """Descripción de un código SAT. Retorna '' si no existe."""
    if not code:
        return ""
    _validate_catalog_table(table)
    try:
        if table in _BIG:
            return _lookup_big(table, code)
        return _small(table).get(code, "")
    except sqlite3.Error:
        return ""


def fmt_code(table: str, code: str) -> str:
    """'code - Descripción' o 'code' si no hay descripción."""
    if not code:
        return ""
    desc = describe(table, code)
    return f"{code} - {desc}" if desc else code
