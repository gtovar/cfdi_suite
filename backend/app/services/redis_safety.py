"""redis_safety.py — bandera de degradación pasiva + wrapper de reporte que
nunca propaga.

Post-incidente 2026-07-23 (cuota de Upstash agotada durante pruebas de
carga): el trabajo real (generar el PDF, subirlo a GCS) nunca debe
convertirse en un 500 solo porque el REPORTE de progreso a Redis falló.
`safe_redis_call` envuelve cada escritura de reporte no esencial (status,
contadores, ticks de progreso) para que un fallo de Redis se registre y se
descarte, nunca se propague.

Deliberadamente NO es un circuit breaker completo (pybreaker): el error real
de Upstash falla rápido, no se cuelga, así que no hay timeouts que acumular
-- el beneficio clásico de un breaker no aplica aquí. Ver
docs/mesa-decision-resiliencia-redis-2026-07-23.md para el razonamiento
completo.
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable, TypeVar

from .redis_errors import is_redis_quota_error

T = TypeVar("T")

_degraded_until: float = 0.0
_COOLDOWN_SECONDS = 60


def mark_degraded() -> None:
    global _degraded_until
    _degraded_until = time.monotonic() + _COOLDOWN_SECONDS


def is_degraded() -> bool:
    """Solo lee un valor en memoria -- nunca hace red. Ver Paso 6 del plan:
    /api/health depende de esto para no gastar cuota de Redis él mismo."""
    return time.monotonic() < _degraded_until


async def safe_redis_call(coro_factory: Callable[[], Awaitable[T]], *, on_quota_error: Callable[[], None] = mark_degraded) -> T | None:
    """Ejecuta una llamada a Redis (ej. `lambda: redis_client.set(...)`);
    nunca propaga. Si el error es un agotamiento real de cuota, activa la
    bandera de degradación."""
    try:
        return await coro_factory()
    except Exception as e:
        if is_redis_quota_error(e):
            on_quota_error()
        print(f"[redis_safety] aviso: operación de Redis no completada: {e}")
        return None
