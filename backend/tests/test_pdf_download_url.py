from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

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
    antes de firmar la URL -- GCS es la señal principal de "¿está listo?", no
    Redis (Paso 3 de docs/plan-implementacion-resiliencia-redis-2026-07-23.md,
    post-incidente 2026-07-23: con Redis agotado, un PDF ya en GCS debía poder
    descargarse igual, y antes no se podía).
    """

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_returns_404_when_blob_missing_regardless_of_redis_status(self) -> None:
        """Post-incidente 2026-07-23 (Paso 3): GCS es la señal principal, no
        Redis -- este endpoint ya no consulta pdf:status en absoluto."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch("backend.app.routers.pdf._get_signing_credentials", return_value=(MagicMock(token="tok"), "sa@example.com")),
            patch("backend.app.routers.pdf.storage.Client", return_value=mock_storage_client),
        ):
            response = self.client.get("/api/cfdi/pdf/job-123/download-url")

        self.assertEqual(response.status_code, 404)

    def test_returns_signed_url_even_if_redis_is_down(self) -> None:
        """El caso central del incidente: Redis inalcanzable no debe impedir
        descargar un PDF que ya existe en GCS."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.generate_signed_url.return_value = "https://signed.example/pdf"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch("backend.app.routers.pdf._get_signing_credentials", return_value=(MagicMock(token="tok"), "sa@example.com")),
            patch("backend.app.routers.pdf.storage.Client", return_value=mock_storage_client),
        ):
            response = self.client.get("/api/cfdi/pdf/job-123/download-url")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["downloadUrl"], "https://signed.example/pdf")


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class DownloadPdfEndpointTests(unittest.TestCase):
    """/cfdi/pdf/{job_id}/download -- mismo cambio de Paso 3 que download-url:
    GCS es la señal principal, no Redis."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_returns_404_when_blob_missing(self) -> None:
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with patch("backend.app.routers.pdf.storage.Client", return_value=mock_storage_client):
            response = self.client.get("/api/cfdi/pdf/job-123/download")

        self.assertEqual(response.status_code, 404)

    def test_returns_pdf_even_if_redis_is_down(self) -> None:
        """El caso central del incidente: Redis inalcanzable no debe impedir
        descargar un PDF que ya existe en GCS."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_as_bytes.return_value = b"%PDF-fake"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with patch("backend.app.routers.pdf.storage.Client", return_value=mock_storage_client):
            response = self.client.get("/api/cfdi/pdf/job-123/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-fake")


if __name__ == "__main__":
    unittest.main()
