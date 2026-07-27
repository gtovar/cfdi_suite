"""
fiel_config.py — almacenamiento de FIEL (e.firma) en GCS con tenant isolation.

B-lite: el material de la e.firma sale del filesystem efimero de Cloud Run
(~/.cfdi-suite/fiel.enc) y se mueve a GCS bajo fiel/{tenant_id}/fiel.enc,
cifrado con Fernet (FERNET_KEY).

Fallback local para desarrollo (sin credenciales GCS): mismos paths de antes.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from .fernet_utils import _ensure_key as _fernet

_DEFAULT_TENANT = "default-tenant"

_SUITE_DIR = Path.home() / ".cfdi-suite"
_FIEL_FILE = _SUITE_DIR / "fiel.enc"

_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "cfdi-suite-uploads-706861124428")


def _fiel_blob_path(tenant_id: str) -> str:
    return f"fiel/{tenant_id}/fiel.enc"


def _gcs_bucket():
    try:
        from google.cloud import storage
        return storage.Client().bucket(_BUCKET_NAME)
    except Exception:
        return None


def save_fiel(
    cer_bytes: bytes,
    key_bytes: bytes,
    password: str,
    tenant_id: str = _DEFAULT_TENANT,
) -> None:
    payload = {
        "cer": base64.b64encode(cer_bytes).decode(),
        "key": base64.b64encode(key_bytes).decode(),
        "password": password,
    }
    encrypted = _fernet().encrypt(json.dumps(payload).encode())

    bucket = _gcs_bucket()
    if bucket:
        bucket.blob(_fiel_blob_path(tenant_id)).upload_from_string(encrypted)
    else:
        _FIEL_FILE.write_bytes(encrypted)
        _FIEL_FILE.chmod(0o600)


def load_fiel(tenant_id: str = _DEFAULT_TENANT) -> tuple[bytes, bytes, str] | None:
    bucket = _gcs_bucket()
    if bucket:
        blob = bucket.blob(_fiel_blob_path(tenant_id))
        if not blob.exists():
            return None
        encrypted = blob.download_as_bytes()
    else:
        if not _FIEL_FILE.exists():
            return None
        encrypted = _FIEL_FILE.read_bytes()

    payload = json.loads(_fernet().decrypt(encrypted))
    return (
        base64.b64decode(payload["cer"]),
        base64.b64decode(payload["key"]),
        payload["password"],
    )


def fiel_rfc(tenant_id: str = _DEFAULT_TENANT) -> str | None:
    data = load_fiel(tenant_id)
    if not data:
        return None
    cer_bytes, _, _ = data
    try:
        from OpenSSL import crypto
        from satcfdi.models.certificate import Certificate
        cert = Certificate(crypto.load_certificate(crypto.FILETYPE_ASN1, cer_bytes))
        return str(cert.rfc) if cert.rfc else None
    except Exception:
        return None


def delete_fiel(tenant_id: str = _DEFAULT_TENANT) -> bool:
    bucket = _gcs_bucket()
    if bucket:
        blob = bucket.blob(_fiel_blob_path(tenant_id))
        if not blob.exists():
            return False
        blob.delete()
        return True

    if not _FIEL_FILE.exists():
        return False
    _FIEL_FILE.unlink()
    return True
