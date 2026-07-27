from __future__ import annotations

import logging
import os
from pathlib import Path

import sentry_sdk
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_SUITE_DIR = Path.home() / ".cfdi-suite"
_KEY_FILE = _SUITE_DIR / "secret.key"


def _ensure_key() -> Fernet:
    env_key = os.getenv("FERNET_KEY")
    if env_key:
        return Fernet(env_key.encode())

    _SUITE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    if not _KEY_FILE.exists():
        _KEY_FILE.write_bytes(Fernet.generate_key())
        _KEY_FILE.chmod(0o600)
        logger.info("Nueva Fernet key generada para desarrollo local")
        _warn_if_orphan_data()
    else:
        _warn_if_orphan_data()

    return Fernet(_KEY_FILE.read_bytes())


def _warn_if_orphan_data() -> None:
    for path in [_SUITE_DIR / "emisores.enc", _SUITE_DIR / "fiel.enc"]:
        if not path.exists():
            continue
        try:
            fernet = Fernet(_KEY_FILE.read_bytes() if _KEY_FILE.exists() else b"")
            fernet.decrypt(path.read_bytes())
        except Exception:
            msg = (
                f"Cold start: {path.name} existe pero no se puede descifrar "
                f"con la key actual. Credenciales perdidas — reconfigurar."
            )
            logger.warning(msg)
            sentry_sdk.capture_message(msg, level="warning")
