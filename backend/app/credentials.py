from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from .fernet_utils import _ensure_key

_SUITE_DIR = Path.home() / ".cfdi-suite"
_DATA_FILE = _SUITE_DIR / "emisores.enc"


def _load_raw() -> dict[str, Any]:
    if not _DATA_FILE.exists():
        return {}
    fernet = _ensure_key()
    return json.loads(fernet.decrypt(_DATA_FILE.read_bytes()))


def _save_raw(data: dict[str, Any]) -> None:
    fernet = _ensure_key()
    _DATA_FILE.write_bytes(fernet.encrypt(json.dumps(data).encode()))
    _DATA_FILE.chmod(0o600)


def load_all() -> dict[str, dict[str, str]]:
    """Return all emisores without credential_token."""
    raw = _load_raw()
    return {
        rfc: {k: v for k, v in entry.items() if k != "credential_token"}
        for rfc, entry in raw.items()
    }


def get(rfc: str) -> dict[str, str] | None:
    """Return full credential including token (for internal use only)."""
    return _load_raw().get(rfc)


def set_emisor(rfc: str, data: dict[str, str]) -> None:
    raw = _load_raw()
    raw[rfc.upper()] = data
    _save_raw(raw)


def delete_emisor(rfc: str) -> bool:
    raw = _load_raw()
    if rfc.upper() not in raw:
        return False
    del raw[rfc.upper()]
    _save_raw(raw)
    return True
