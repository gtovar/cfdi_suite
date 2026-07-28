"""
rate_limits.py — rate limiting por identidad de usuario (B-lite, fix #6).

Rate limiter in-memory con ventana deslizante. La clave es SHA256 del Bearer
token (limite por usuario, no por IP). Sin token (dev mode): sin limite.

Un dict en memoria por proceso Cloud Run — cold start lo limpia, aceptable
para un solo usuario. La funcion rate_limit() devuelve un Depends() listo
para usar en cualquier endpoint de FastAPI.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Depends, HTTPException, Request


def _rate_limit_key(request: Request) -> str:
    return getattr(request.state, "auth_fingerprint", "")


def rate_limit(max_requests: int, window_seconds: int = 60):
    """Depends de FastAPI que rechaza 429 si se excede el limite por ventana.

    Uso:
        @router.post("/x")
        async def handler(body: Body, _rate=rate_limit(30)):
            ...
    """
    storage: dict[str, list[float]] = defaultdict(list)

    async def _check(request: Request) -> None:
        key = _rate_limit_key(request)
        if not key:
            return

        now = time.monotonic()
        cutoff = now - window_seconds
        timestamps = storage[key]

        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if len(timestamps) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail="Demasiadas solicitudes. Intenta de nuevo en unos segundos.",
                headers={"Retry-After": str(window_seconds)},
            )

        timestamps.append(now)

    return Depends(_check)
