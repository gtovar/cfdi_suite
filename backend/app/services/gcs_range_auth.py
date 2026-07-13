"""
gcs_range_auth.py — sesión HTTP autenticada para lecturas por rango contra
GCS (usada por remotezip.RemoteZip), sin necesitar una signed URL.

A diferencia de las signed URLs que ya usa pdf.py para links de descarga
entregados a un navegador externo (que requieren permiso IAM signBlob sobre
la cuenta de servicio), aquí quien pide los datos es el propio backend --
puede usar sus credenciales ambientales directo como Bearer token contra la
API JSON de GCS, sin firmar nada.
"""
from __future__ import annotations

from urllib.parse import quote

import google.auth
import google.auth.transport.requests


def get_gcs_authorized_session() -> google.auth.transport.requests.AuthorizedSession:
    """AuthorizedSession es subclase de requests.Session y se refresca sola
    -- segura de reusar durante toda una tarea del Cloud Run Job (hasta
    varios minutos) sin lógica manual de refresh de token. Sirve directo
    como el parámetro session= de remotezip.RemoteZip."""
    credentials, _ = google.auth.default()
    return google.auth.transport.requests.AuthorizedSession(credentials)


def gcs_object_url(bucket_name: str, gcs_path: str) -> str:
    """URL de descarga de la API JSON de GCS para un objeto -- soporta
    peticiones con encabezado Range, que es lo que remotezip necesita para
    leer solo una porción del archivo."""
    return (
        f"https://storage.googleapis.com/download/storage/v1/b/"
        f"{bucket_name}/o/{quote(gcs_path, safe='')}?alt=media"
    )
