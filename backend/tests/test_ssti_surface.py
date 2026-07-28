"""
test_ssti_surface.py — Canario SSTI para archivos de render.

Si alguien introduce un motor de templates (jinja2, mako, string.Template),
eval/exec, o __import__ en canvas_service.py o shell_service.py, este test
falla en CI.

La primera linea de defensa es ruff S (flake8-bandit) habilitado globalmente.
Este test es la segunda linea: especifico para los archivos de render.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_SERVICES_DIR = Path(__file__).resolve().parent.parent / "app" / "services"
_RENDER_FILES = [
    _SERVICES_DIR / "canvas_service.py",
    _SERVICES_DIR / "shell_service.py",
]

_FORBIDDEN_IMPORTS = {"jinja2", "mako", "string"}
_FORBIDDEN_FUNCTIONS = {"eval", "exec", "compile"}


def _walk_ast(filepath: Path) -> list[ast.AST]:
    return list(ast.walk(ast.parse(filepath.read_text())))


@pytest.mark.parametrize("filepath", _RENDER_FILES)
def test_no_template_engine_imported(filepath: Path) -> None:
    """Falla si se importa jinja2, mako, o string.Template en archivos de render."""
    for node in _walk_ast(filepath):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top not in _FORBIDDEN_IMPORTS, (
                    f"{filepath.name}:{node.lineno} importa {alias.name} — prohibido en archivos de render"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                assert top not in _FORBIDDEN_IMPORTS, (
                    f"{filepath.name}:{node.lineno} importa de {node.module} — prohibido en archivos de render"
                )


@pytest.mark.parametrize("filepath", _RENDER_FILES)
def test_no_dangerous_builtins(filepath: Path) -> None:
    """Falla si se usa eval(), exec(), compile(), o __import__() en archivos de render."""
    for node in _walk_ast(filepath):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_FUNCTIONS:
                raise AssertionError(
                    f"{filepath.name}:{node.lineno} usa {node.func.id}() — prohibido en archivos de render"
                )
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                raise AssertionError(
                    f"{filepath.name}:{node.lineno} usa __import__() — prohibido en archivos de render"
                )
