"""redis_errors.py — clasificación de errores de cuota de Upstash.

Extraído tras el incidente del 23 de julio de 2026 (ver
docs/mesa-decision-resiliencia-redis-2026-07-23.md): la clasificación que
vivía en pdf.py buscaba "quota exceeded" y "oom", pero el mensaje real que
manda Upstash al agotar el plan gratuito es "max requests limit exceeded" —
ninguna de las dos cadenas viejas coincidía, así que esa rama nunca se
activaba en producción durante el incidente real.
"""
from __future__ import annotations

_QUOTA_ERROR_PATTERNS = (
    "max requests limit exceeded",
    "max daily request limit",
    "max_requests_limit",
)


def is_redis_quota_error(exc: BaseException) -> bool:
    """True si `exc` es un agotamiento de cuota de Upstash (no cualquier
    excepción de Redis — un timeout de red o una desconexión no cuentan)."""
    error_str = str(exc).lower()
    return any(pattern in error_str for pattern in _QUOTA_ERROR_PATTERNS)
