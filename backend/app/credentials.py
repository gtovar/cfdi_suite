"""
credentials.py — credenciales de emisores (PAC) en GCS con tenant isolation.

B-lite: las credenciales de emisores (credential_id, credential_token de Diverza)
salen del filesystem efimero de Cloud Run (~/.cfdi-suite/emisores.enc) y se
mueven a GCS bajo credenciales/{tenant_id}/emisores.enc, cifrado con Fernet.

Fallback local para desarrollo (sin credenciales GCS): mismos paths de antes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .fernet_utils import _ensure_key

_DEFAULT_TENANT = "default-tenant"

_SUITE_DIR = Path.home() / ".cfdi-suite"
_DATA_FILE = _SUITE_DIR / "emisores.enc"

_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "cfdi-suite-uploads-706861124428")


def _creds_blob_path(tenant_id: str) -> str:
    return f"credenciales/{tenant_id}/emisores.enc"


def _gcs_bucket():
    try:
        from google.cloud import storage
        return storage.Client().bucket(_BUCKET_NAME)
    except Exception:
        return None


def _load_raw(tenant_id: str) -> dict[str, Any]:
    bucket = _gcs_bucket()
    if bucket:
        blob = bucket.blob(_creds_blob_path(tenant_id))
        if not blob.exists():
            return {}
        encrypted = blob.download_as_bytes()
    else:
        if not _DATA_FILE.exists():
            return {}
        encrypted = _DATA_FILE.read_bytes()

    fernet = _ensure_key()
    return json.loads(fernet.decrypt(encrypted))


def _save_raw(data: dict[str, Any], tenant_id: str) -> None:
    fernet = _ensure_key()
    encrypted = fernet.encrypt(json.dumps(data).encode())

    bucket = _gcs_bucket()
    if bucket:
        bucket.blob(_creds_blob_path(tenant_id)).upload_from_string(encrypted)
    else:
        _DATA_FILE.write_bytes(encrypted)
        _DATA_FILE.chmod(0o600)


def load_all(tenant_id: str = _DEFAULT_TENANT) -> dict[str, dict[str, str]]:
    raw = _load_raw(tenant_id)
    return {
        rfc: {k: v for k, v in entry.items() if k != "credential_token"}
        for rfc, entry in raw.items()
    }


def get(rfc: str, tenant_id: str = _DEFAULT_TENANT) -> dict[str, str] | None:
    return _load_raw(tenant_id).get(rfc.upper())


def set_emisor(
    rfc: str,
    data: dict[str, str],
    tenant_id: str = _DEFAULT_TENANT,
) -> None:
    raw = _load_raw(tenant_id)
    raw[rfc.upper()] = data
    _save_raw(raw, tenant_id)


def delete_emisor(
    rfc: str,
    tenant_id: str = _DEFAULT_TENANT,
) -> bool:
    raw = _load_raw(tenant_id)
    if rfc.upper() not in raw:
        return False
    del raw[rfc.upper()]
    _save_raw(raw, tenant_id)
    return True
