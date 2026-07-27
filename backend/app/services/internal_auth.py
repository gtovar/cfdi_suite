"""
internal_auth.py — verificación de identidad para los endpoints internos.

Los tres endpoints que sólo invoca Cloud Tasks
(`/api/internal/generate-pdf`, `/api/internal/extract-zip` y
`/api/cfdi/batch/worker-task`) están expuestos en el mismo servicio público de
Cloud Run que el resto de la API. Antes de este módulo, dos de ellos se
defendían sólo con `x-cloudtasks-queuename`, un header que cualquiera puede
mandar porque el nombre de la cola es público, y el tercero no tenía nada.

Aquí se verifica el token OIDC que Cloud Tasks adjunta a la tarea
(`task_dispatcher._oidc_token()`). El token lo firma Google, va dirigido a
`API_URL` y lo emite la service account del servicio: no se puede fabricar
desde fuera.

Las dos mitades tienen que desplegarse en orden -- primero el emisor
(task_dispatcher), después este verificador -- porque viven en la misma imagen
y un deploy al revés deja a Cloud Tasks mandando tareas sin token contra un
endpoint que ya las exige. Ver el mensaje del commit 12a.
"""
from __future__ import annotations

import os

import sentry_sdk
from fastapi import Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

# Tiene que ser EXACTAMENTE la misma cadena que task_dispatcher pone en el
# `audience` del token; las dos salen de API_URL a propósito.
_AUDIENCE = os.getenv("API_URL", "")

# La SA que Cloud Tasks usa para firmar. Se valida además del audience para que
# un token legítimo de otro servicio del mismo proyecto no sirva aquí.
_EXPECTED_SA = os.getenv(
    "OIDC_SERVICE_ACCOUNT",
    "cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com",
)


def verify_cloud_tasks(request: Request) -> bool:
    """True sólo si el request trae un token OIDC válido de Cloud Tasks.

    A diferencia de la spec original de #2, aquí NO hay rama que acepte el
    header a secas: el header es spoofable y aceptarlo dejaría el agujero
    abierto. El header se sigue exigiendo como filtro barato previo, pero el
    token es lo que decide.
    """
    if not _AUDIENCE:
        # Un audience vacío hace que verify_oauth2_token acepte cualquier
        # destinatario. Es peor que no verificar, porque parece que verifica.
        sentry_sdk.capture_message(
            "API_URL no está definida: no se puede verificar el token OIDC de "
            "los endpoints internos",
            level="error",
        )
        return False

    if "x-cloudtasks-queuename" not in request.headers:
        sentry_sdk.capture_message(
            "Intento de acceso a endpoint interno sin header de Cloud Tasks",
            level="warning",
        )
        return False

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        sentry_sdk.capture_message(
            "Endpoint interno sin token OIDC (¿tarea encolada antes del "
            "deploy que empezó a firmarlas?)",
            level="warning",
        )
        return False

    token = auth[len("Bearer "):]
    try:
        claims = id_token.verify_oauth2_token(
            token, google_requests.Request(), audience=_AUDIENCE
        )
    except Exception:
        sentry_sdk.capture_message(
            "Token OIDC inválido en endpoint interno", level="error"
        )
        return False

    if claims.get("email") != _EXPECTED_SA or not claims.get("email_verified"):
        sentry_sdk.capture_message(
            f"Token OIDC válido pero de otra identidad: {claims.get('email')}",
            level="error",
        )
        return False

    return True
