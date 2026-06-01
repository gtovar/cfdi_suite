from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.fernet import Fernet

_SUITE_DIR = Path.home() / ".cfdi-suite"
_KEY_FILE = _SUITE_DIR / "secret.key"
_FIEL_FILE = _SUITE_DIR / "fiel.enc"


def _fernet() -> Fernet:
    _SUITE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not _KEY_FILE.exists():
        _KEY_FILE.write_bytes(Fernet.generate_key())
        _KEY_FILE.chmod(0o600)
    return Fernet(_KEY_FILE.read_bytes())


def save_fiel(cer_bytes: bytes, key_bytes: bytes, password: str) -> None:
    payload = {
        "cer": base64.b64encode(cer_bytes).decode(),
        "key": base64.b64encode(key_bytes).decode(),
        "password": password,
    }
    encrypted = _fernet().encrypt(json.dumps(payload).encode())
    _FIEL_FILE.write_bytes(encrypted)
    _FIEL_FILE.chmod(0o600)


def load_fiel() -> tuple[bytes, bytes, str] | None:
    """Return (cer_bytes, key_bytes, password) or None if not configured."""
    if not _FIEL_FILE.exists():
        return None
    payload = json.loads(_fernet().decrypt(_FIEL_FILE.read_bytes()))
    return (
        base64.b64decode(payload["cer"]),
        base64.b64decode(payload["key"]),
        payload["password"],
    )


def fiel_rfc() -> str | None:
    """Return the RFC embedded in the FIEL certificate, or None."""
    data = load_fiel()
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


def delete_fiel() -> bool:
    if not _FIEL_FILE.exists():
        return False
    _FIEL_FILE.unlink()
    return True
