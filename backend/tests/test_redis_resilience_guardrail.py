"""test_redis_resilience_guardrail.py — barrera de revisión (no un gate ciego)
contra llamadas a Redis sin protección en los pipelines de PDF/batch.

Origen: auditoría de resiliencia 2026-07-23 (ver PROJECT_STATE.md) encontró
varias llamadas a `redis_client.*` sin envolver en safe_redis_call/
safe_redis_call_sync que el plan original de Redis (mismo día) no había
cubierto -- process_zip_in_background, _try_remote_manifest_path, batch.py.

Este test NO es un linter perfecto: escanea el AST buscando llamadas
`redis_client.<método>` / `pipe.<método>` y las clasifica como protegidas si
están dentro de un lambda o una función nombrada que a su vez se pasa como
argumento a safe_redis_call/safe_redis_call_sync en el mismo scope. Los
patrones que NO puede resolver así (fail-closed deliberado, o protección por
un try/except que las rodea en vez de por el wrapper) están en el ALLOWLIST
de abajo, cada uno con su razón -- si aparece una llamada nueva sin proteger
y sin entrada en el allowlist, el test falla pidiendo una decisión consciente
(envolver la llamada o documentar por qué no debe envolverse), no un arreglo
automático ni un permiso silencioso.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REDIS_METHOD_NAMES = {
    "get", "set", "delete", "smembers", "sadd", "scard", "mget", "expire",
    "incr", "lpop", "rpush", "hmset", "hgetall", "hincrby", "lrange",
    "pipeline",
}
SAFE_WRAPPER_NAMES = {"safe_redis_call", "safe_redis_call_sync"}

# (archivo relativo a backend/, línea, razón) -- cada entrada es una decisión
# ya tomada y documentada en el código fuente en esa misma línea/bloque.
ALLOWLIST: set[tuple[str, int]] = {
    (
        "app/routers/pdf.py", 996,
    ),  # Lock de idempotencia (SET NX) de process_zip_in_background --
        # deliberadamente fail-closed, ver el comentario ahí mismo: si Redis
        # falla aquí no hay lock que adquirir, la extracción no debe correr
        # dos veces en paralelo.
    (
        "app/workers/batch_shard_worker.py", 186,
    ),  # smembers de pdf:batch_ids en el camino "de siempre" (sin
        # ZIP_GCS_PATH) -- es el INSUMO de qué XMLs le tocan a esta tarea, no
        # un reporte; ver comentario ahí mismo. Fail-closed a propósito,
        # mismo criterio que el lock de arriba.
    (
        "app/routers/pdf.py", 1122,
    ),  # scard cosmético dentro de flush_chunk -- ya vive en su propio
        # try/except (líneas de alrededor) que nunca deja que un fallo aquí
        # tumbe la subida real del chunk; no usa safe_redis_call por nombre
        # pero el efecto (nunca propaga) es el mismo.
}


class _ParentTagger(ast.NodeVisitor):
    def __init__(self):
        self.parent: dict[ast.AST, ast.AST] = {}

    def generic_visit(self, node):
        for child in ast.iter_child_nodes(node):
            self.parent[child] = node
        super().generic_visit(node)


def _enclosing_function(node: ast.AST, parent: dict[ast.AST, ast.AST]) -> ast.AST | None:
    current = parent.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.Module)):
            return current
        current = parent.get(current)
    return None


def _call_func_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _name_passed_to_safe_wrapper(name: str, scope: ast.AST) -> bool:
    """True si `name` (una función nombrada) aparece como argumento bare de
    safe_redis_call/safe_redis_call_sync en algún lugar dentro de `scope`."""
    for node in ast.walk(scope):
        if isinstance(node, ast.Call) and _call_func_name(node) in SAFE_WRAPPER_NAMES:
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id == name:
                    return True
    return False


def _is_lambda_passed_to_safe_wrapper(lam: ast.Lambda, parent: dict[ast.AST, ast.AST]) -> bool:
    current = parent.get(lam)
    # El lambda debe ser un argumento directo de la llamada al wrapper.
    if isinstance(current, ast.Call) and _call_func_name(current) in SAFE_WRAPPER_NAMES:
        return True
    return False


def _find_unprotected_redis_calls(tree: ast.Module) -> list[tuple[int, str]]:
    tagger = _ParentTagger()
    tagger.visit(tree)
    parent = tagger.parent

    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        if node.func.value.id not in {"redis_client", "pipe"}:
            continue
        if node.func.attr not in REDIS_METHOD_NAMES:
            continue

        enclosing = _enclosing_function(node, parent)
        protected = False
        if isinstance(enclosing, ast.Lambda):
            protected = _is_lambda_passed_to_safe_wrapper(enclosing, parent)
            if not protected:
                # El lambda puede estar anidado dentro de OTRO lambda/función
                # ya protegido (poco común, pero no asumimos que no pasa).
                outer = _enclosing_function(enclosing, parent)
                if isinstance(outer, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scope = _enclosing_function(outer, parent) or tree
                    protected = _name_passed_to_safe_wrapper(outer.name, scope)
        elif isinstance(enclosing, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = _enclosing_function(enclosing, parent) or tree
            protected = _name_passed_to_safe_wrapper(enclosing.name, scope)

        if not protected:
            findings.append((node.lineno, ast.unparse(node)))

    return findings


TARGET_FILES = [
    "app/routers/pdf.py",
    "app/routers/batch.py",
    "app/workers/batch_shard_worker.py",
]


def test_no_unreviewed_unprotected_redis_calls():
    unreviewed: list[str] = []
    for rel_path in TARGET_FILES:
        path = BACKEND_ROOT / rel_path
        tree = ast.parse(path.read_text(), filename=str(path))
        for lineno, snippet in _find_unprotected_redis_calls(tree):
            if (rel_path, lineno) in ALLOWLIST:
                continue
            unreviewed.append(f"{rel_path}:{lineno}: {snippet}")

    assert not unreviewed, (
        "Llamada(s) a Redis sin envolver en safe_redis_call/safe_redis_call_sync "
        "y sin entrada en el ALLOWLIST de test_redis_resilience_guardrail.py:\n"
        + "\n".join(unreviewed)
        + "\n\nDecide de forma consciente: envuelve la llamada, o si es "
        "deliberadamente fail-closed (como el lock de idempotencia o el "
        "insumo de un shard), documenta el porqué en el código y agrega la "
        "línea al ALLOWLIST de este archivo."
    )


def test_allowlist_entries_still_exist_in_source():
    """Si el código se mueve/refactoriza, una entrada del allowlist puede
    quedar apuntando a una línea que ya no es la llamada real -- esto no
    detecta ESO directamente, pero sí confirma que el archivo sigue
    teniendo al menos tantas líneas como la entrada más alta, como aviso
    barato de que el allowlist no quedó huérfano tras un refactor grande."""
    by_file: dict[str, list[int]] = {}
    for rel_path, lineno in ALLOWLIST:
        by_file.setdefault(rel_path, []).append(lineno)

    for rel_path, linenos in by_file.items():
        path = BACKEND_ROOT / rel_path
        total_lines = len(path.read_text().splitlines())
        assert max(linenos) <= total_lines, (
            f"{rel_path}: el ALLOWLIST referencia la línea {max(linenos)} pero "
            f"el archivo solo tiene {total_lines} -- revisa si el refactor movió "
            "la llamada que esa entrada documentaba."
        )
