"""
conftest.py — red de seguridad contra fugas de estado global entre tests.

Encontrado en vivo 2026-07-23: dos módulos de test (test_pdf_pipeline.py,
test_table_preview_equivalence.py) mutaban os.environ a nivel de módulo sin
restaurarlo, contaminando 8 tests en otros 2 archivos que corrían después en
el mismo proceso de pytest (documentados por años como "8 fallos
preexistentes" sin que nadie encontrara la causa real). Ya se corrigió esa
fuga puntual con fixtures locales -- este fixture es la red de seguridad para
que la PRÓXIMA fuga similar (cualquier archivo futuro que mute os.environ sin
restaurar) falle con un mensaje claro señalando al culpable, en vez de
manifestarse como fallos random en un módulo sin relación.
"""
from __future__ import annotations

import os

import pytest

from backend.app.services import redis_safety


# pytest gestiona esta variable por su cuenta alrededor de cada fase
# (setup/call/teardown) de cada test -- no es una fuga de un test real.
_PYTEST_OWNED_VARS = {"PYTEST_CURRENT_TEST"}


@pytest.fixture(autouse=True)
def _reset_redis_degraded_flag():
    """redis_safety._degraded_until es un reloj de pared real
    (time.monotonic()), global al proceso -- un test que simula un error de
    cuota (mark_degraded()) deja la bandera "degradada" prendida hasta 60s
    después, contaminando cualquier test que corra en esa ventana. Se vuelve
    crítico en cuanto safe_redis_call cortocircuita en base a is_degraded():
    sin este reset, tests que ni siquiera tocan Redis fallarían solo al
    correr en conjunto (nunca en aislamiento), porque heredarían la bandera
    prendida de un test anterior."""
    redis_safety._degraded_until = 0.0
    yield
    redis_safety._degraded_until = 0.0


@pytest.fixture(autouse=True, scope="session")
def _fail_on_leaked_environ():
    snapshot = dict(os.environ)
    yield
    current = {k: v for k, v in os.environ.items() if k not in _PYTEST_OWNED_VARS}
    baseline = {k: v for k, v in snapshot.items() if k not in _PYTEST_OWNED_VARS}
    leaked = {
        k: current.get(k)
        for k in set(current) - set(baseline)
    } | {
        k: current.get(k)
        for k in baseline
        if current.get(k) != baseline[k]
    }
    assert not leaked, (
        f"os.environ quedó modificado tras correr toda la suite: {leaked}. "
        "Algún test mutó una variable de entorno a nivel de módulo (u olvidó "
        "restaurarla en un fixture) -- eso contamina cualquier otro test que "
        "corra después en el mismo proceso. Revisa el/los módulo(s) que "
        "tocan os.environ sin usar un fixture con teardown."
    )
