from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from fastapi.testclient import TestClient

    from backend.app.main import app
except ModuleNotFoundError as error:
    TestClient = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class DownloadUrlEndpointTests(unittest.TestCase):
    """/cfdi/pdf/{job_id}/download-url debe verificar que el blob exista en GCS
    antes de firmar la URL. Sin este chequeo, un PDF cuyo blob ya expiró por
    el lifecycle de GCS (1 día) pero cuyo status en Redis sigue diciendo
    "done" (TTL más largo) devuelve un link firmado que rompe al usarse.
    """

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_returns_404_when_status_done_but_blob_missing(self) -> None:
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch("backend.app.routers.pdf.redis_client.get", new_callable=AsyncMock) as mock_get,
            patch("backend.app.routers.pdf._get_signing_credentials", return_value=(MagicMock(token="tok"), "sa@example.com")),
            patch("backend.app.routers.pdf.storage.Client", return_value=mock_storage_client),
        ):
            mock_get.return_value = b"done"
            response = self.client.get("/api/cfdi/pdf/job-123/download-url")

        self.assertEqual(response.status_code, 404)
        mock_blob.exists.assert_called_once()
        mock_blob.generate_signed_url.assert_not_called()

    def test_returns_signed_url_when_status_done_and_blob_exists(self) -> None:
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.generate_signed_url.return_value = "https://signed.example/pdf"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch("backend.app.routers.pdf.redis_client.get", new_callable=AsyncMock) as mock_get,
            patch("backend.app.routers.pdf._get_signing_credentials", return_value=(MagicMock(token="tok"), "sa@example.com")),
            patch("backend.app.routers.pdf.storage.Client", return_value=mock_storage_client),
        ):
            mock_get.return_value = b"done"
            response = self.client.get("/api/cfdi/pdf/job-123/download-url")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["downloadUrl"], "https://signed.example/pdf")

    def test_returns_404_when_status_not_done(self) -> None:
        with patch("backend.app.routers.pdf.redis_client.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            response = self.client.get("/api/cfdi/pdf/job-123/download-url")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
