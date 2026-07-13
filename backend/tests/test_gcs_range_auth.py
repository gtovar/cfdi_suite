"""
Tests de app/services/gcs_range_auth.py -- sin red real, mockeando
google.auth.default() como ya hace el patrón existente en pdf.py
(_get_signing_credentials) para pruebas relacionadas.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    from backend.app.services import gcs_range_auth
except ModuleNotFoundError as error:
    gcs_range_auth = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


@unittest.skipIf(gcs_range_auth is None, f"backend no disponible: {_IMPORT_ERROR}")
class GcsObjectUrlTests(unittest.TestCase):
    def test_url_bien_formada(self) -> None:
        url = gcs_range_auth.gcs_object_url("mi-bucket", "uploads/batch-1.zip")
        self.assertEqual(
            url,
            "https://storage.googleapis.com/download/storage/v1/b/mi-bucket/o/uploads%2Fbatch-1.zip?alt=media",
        )

    def test_escapa_caracteres_especiales_en_el_path(self) -> None:
        url = gcs_range_auth.gcs_object_url("mi-bucket", "uploads/lote con espacios.zip")
        self.assertIn("lote%20con%20espacios.zip", url)
        self.assertNotIn(" ", url)


@unittest.skipIf(gcs_range_auth is None, f"backend no disponible: {_IMPORT_ERROR}")
class GetGcsAuthorizedSessionTests(unittest.TestCase):
    def test_usa_credenciales_ambientales_y_devuelve_authorized_session(self) -> None:
        fake_credentials = MagicMock()
        with (
            patch.object(gcs_range_auth.google.auth, "default", return_value=(fake_credentials, "proj")) as mock_default,
            patch.object(gcs_range_auth.google.auth.transport.requests, "AuthorizedSession") as mock_session_cls,
        ):
            gcs_range_auth.get_gcs_authorized_session()

        mock_default.assert_called_once()
        mock_session_cls.assert_called_once_with(fake_credentials)


if __name__ == "__main__":
    unittest.main()
