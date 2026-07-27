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

from fastapi import HTTPException, Request

_HEALTH_PATH = "/api/health"
_INTERNAL_PATH_PREFIX = "/api/internal/"
_CLOUD_TASKS_WORKER_PATH = "/api/cfdi/batch/worker-task"


async def verify_user_identity(request: Request) -> str:
    path = request.url.path

    if path == _HEALTH_PATH:
        return "system:health"

    if path == _CLOUD_TASKS_WORKER_PATH or path.startswith(_INTERNAL_PATH_PREFIX):
        return "system:internal"

    expected = os.getenv("API_BEARER_TOKEN", "")
    if not expected:
        return "dev-tenant"

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[len("Bearer "):] != expected:
        raise HTTPException(status_code=401, detail="Token invalido o ausente")

    return "default-tenant"
