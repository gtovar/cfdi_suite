"""Reglas compartidas para identificadores de plantilla usados como nombres de archivo."""
from __future__ import annotations

import re


# Un ID empieza con un carácter alfanumérico y sólo puede contener letras,
# números, guiones y guiones bajos. ``fullmatch`` rechaza rutas, separadores y
# caracteres percent-encoded antes de que el valor alcance el filesystem.
TEMPLATE_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]*", re.IGNORECASE)


def is_valid_template_id(template_id: object) -> bool:
    """Indica si ``template_id`` puede usarse de forma segura en un path."""
    return isinstance(template_id, str) and TEMPLATE_ID_RE.fullmatch(template_id) is not None


def validate_template_id(template_id: object) -> str:
    """Devuelve un ID seguro o levanta ``ValueError`` sin tocar el disco."""
    if not is_valid_template_id(template_id):
        raise ValueError(f"Identificador de plantilla inválido: {template_id!r}")
    return template_id
