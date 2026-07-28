"""
security.py — identidad de usuario verificada (B-lite).

Un Depends() global que cierra PADRE-AUTH y sus 13 hijos: la API completa (~28+
endpoints) requiere un Bearer token fijo, verificado contra API_BEARER_TOKEN del
entorno (Secret Manager).

Los endpoints internos que invoca Cloud Tasks (verify_cloud_tasks) pasan por este
mismo Depends pero son desviados antes de la verificacion de usuario — la
verificacion OIDC propia ocurre dentro del handler. /api/health tambien es libre.

Diseno de B-lite:
- Plan Vercel Hobby (sin Deployment Protection) → identidad en la aplicacion.
- Un solo usuario (single tenant) → Bearer token fijo rotado a mano.
- Multi-tenant futuro: cambiar el tenant_id de constante a claim del token.
"""
from __future__ import annotations

import os
import re
from hashlib import sha256

from fastapi import HTTPException, Request

_HEALTH_PATH = "/api/health"
_INTERNAL_PATH_PREFIX = "/api/internal/"
_CLOUD_TASKS_WORKER_PATH = "/api/cfdi/batch/worker-task"
_QUERY_TOKEN_PATHS = (
    re.compile(r"^/api/cfdi/pdf/[^/]+/progress$"),
    re.compile(r"^/api/cfdi/pdf/batch/[^/]+/progress$"),
    re.compile(r"^/api/cfdi/pdf/batch/[^/]+/download$"),
)


def _set_identity(request: Request, identity: str, fingerprint: str = "") -> str:
    request.state.identity = identity
    request.state.auth_fingerprint = fingerprint
    return identity


def _query_token_allowed(request: Request) -> bool:
    return request.method == "GET" and any(
        pattern.match(request.url.path) for pattern in _QUERY_TOKEN_PATHS
    )


async def verify_user_identity(request: Request) -> str:
    # La dependencia puede aparecer tanto globalmente como en una ruta. Aunque
    # FastAPI normalmente la cachea, conservar el resultado en el request hace
    # que identidad y fingerprint se calculen una sola vez en cualquier uso.
    identity = getattr(request.state, "identity", None)
    if identity is not None:
        return identity

    path = request.url.path

    if path == _HEALTH_PATH:
        return _set_identity(request, "system:health")

    if path == _CLOUD_TASKS_WORKER_PATH or path.startswith(_INTERNAL_PATH_PREFIX):
        return _set_identity(request, "system:internal")

    expected = os.getenv("API_BEARER_TOKEN", "")
    if not expected:
        return _set_identity(request, "dev-tenant")

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and auth[len("Bearer "):] == expected:
        return _set_identity(
            request,
            "default-tenant",
            sha256(expected.encode()).hexdigest()[:24],
        )

    query_token = request.query_params.get("token", "")
    if query_token == expected and _query_token_allowed(request):
        return _set_identity(
            request,
            "default-tenant",
            sha256(expected.encode()).hexdigest()[:24],
        )

    raise HTTPException(status_code=401, detail="Token invalido o ausente")
