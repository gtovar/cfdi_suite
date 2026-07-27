"""
pusher_auth.py — endpoint de autorizacion para canales privados de Pusher (#12).

B-lite: los canales de Pusher dejan de ser publicos. Este endpoint firma la
suscripcion a canales privados (private-*) y a canales de presencia (presence-*)
usando el secreto de Pusher. La identidad del usuario ya esta verificada por el
Depends global antes de llegar aqui.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from ..security import verify_user_identity

router = APIRouter(prefix="/api/pusher", tags=["pusher"])

_PUSHER_SECRET = os.getenv("PUSHER_SECRET", "")
_PUSHER_KEY = os.getenv("PUSHER_KEY", "")

_CHANNEL_PREFIX = "private-"


@router.post("/auth")
async def pusher_authenticate(
    request: Request,
    socket_id: str = Form(...),
    channel_name: str = Form(...),
    tenant_id: str = Depends(verify_user_identity),
) -> dict:
    if not channel_name.startswith(_CHANNEL_PREFIX):
        raise HTTPException(
            status_code=403,
            detail=f"Solo se permiten canales privados (prefijo {_CHANNEL_PREFIX})",
        )

    if not _PUSHER_SECRET or not _PUSHER_KEY:
        raise HTTPException(status_code=500, detail="Pusher no configurado en el servidor")

    string_to_sign = f"{socket_id}:{channel_name}"
    signature = hmac.new(
        _PUSHER_SECRET.encode(),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()

    auth = f"{_PUSHER_KEY}:{signature}"

    if channel_name.startswith("presence-"):
        return {
            "auth": auth,
            "channel_data": '{"user_id":"default-tenant"}',
        }

    return {"auth": auth}
