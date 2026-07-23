from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.routers import pdf as pdf_router
except ModuleNotFoundError as error:
    TestClient = None
    pdf_router = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


def _run(coro):
    return asyncio.run(coro)


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


@unittest.skipIf(TestClient is None, f"fastapi no disponible: {_IMPORT_ERROR}")
class PdfProgressDegradedFallbackTests(unittest.TestCase):
    """Encontrado en vivo el 23 de julio reproduciendo el incidente contra
    producción: /cfdi/pdf/{job_id}/progress (el stream SSE que el frontend
    escucha) se quedaba reportando "converting" para siempre con Redis
    agotado, aunque el PDF ya estuviera listo en GCS -- el status "done"
    nunca llegaba a escribirse (safe_redis_call lo descarta). Mientras la
    bandera de degradación esté activa, debe caer a GCS como respaldo."""

    async def _first_event(self, job_id: str) -> str:
        """Invoca pdf_progress directo (sin pasar por TestClient/HTTP) y
        toma solo el primer evento del generador SSE -- iterar la StreamingResponse
        completa via TestClient.stream() se cuelga porque el generador real
        no termina hasta SSE_MAX_STREAM_SECONDS (600s) o un "done"/"error"."""
        response = await pdf_router.pdf_progress(job_id)
        return await response.body_iterator.__anext__()

    def test_reporta_done_via_gcs_cuando_redis_degradado_y_sin_status(self) -> None:
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with (
            patch("backend.app.routers.pdf.storage.Client", return_value=mock_storage_client),
            patch("backend.app.routers.pdf.redis_client.get", new_callable=AsyncMock) as mock_get,
            patch("backend.app.routers.pdf.redis_safety.is_degraded", return_value=True),
        ):
            mock_get.return_value = None
            first_event = _run(self._first_event("job-degraded"))

        self.assertIn("done", first_event)

    def test_no_cae_a_gcs_si_no_esta_degradado(self) -> None:
        """Sin la bandera activa, un status ausente sigue significando
        "converting" -- no se agrega una llamada a GCS por cada tick del
        camino feliz."""
        mock_storage_client = MagicMock()

        with (
            patch("backend.app.routers.pdf.storage.Client", return_value=mock_storage_client),
            patch("backend.app.routers.pdf.redis_client.get", new_callable=AsyncMock) as mock_get,
            patch("backend.app.routers.pdf.redis_safety.is_degraded", return_value=False),
        ):
            mock_get.return_value = None
            first_event = _run(self._first_event("job-normal"))

        self.assertIn("converting", first_event)
        mock_storage_client.bucket.return_value.blob.assert_not_called()


if __name__ == "__main__":
    unittest.main()
