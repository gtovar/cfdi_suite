"""Contrato de la política POST V4 y rechazo GCS previo al encolado."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi import UploadFile

from backend.app.routers import pdf as pdf_router
from backend.app.services.zip_manifest import MAX_ZIP_COMPRESSED_BYTES, ZipBudgetError


def _run(coro):
    return asyncio.run(coro)


class SignedPostPolicyTests(unittest.TestCase):
    def test_politica_post_v4_fija_objeto_tipo_y_presupuesto(self) -> None:
        credentials = MagicMock(token="token")
        client = MagicMock()
        client.generate_signed_post_policy_v4.return_value = {
            "url": "https://storage.example/upload",
            "fields": {"key": "uploads/id.zip", "policy": "policy", "x-goog-signature": "sig"},
        }
        with (
            patch.object(pdf_router, "_get_signing_credentials", return_value=(credentials, "sa@example")),
            patch.object(pdf_router.storage, "Client", return_value=client),
        ):
            result = _run(pdf_router.request_upload_url())

        self.assertEqual(result["uploadUrl"], "https://storage.example/upload")
        self.assertIn("uploadFields", result)
        kwargs = client.generate_signed_post_policy_v4.call_args.kwargs
        self.assertEqual(kwargs["fields"], {"Content-Type": "application/zip"})
        self.assertIn(["content-length-range", 0, MAX_ZIP_COMPRESSED_BYTES], kwargs["conditions"])
        self.assertEqual(kwargs["service_account_email"], "sa@example")


class StartZipGcsBudgetTests(unittest.TestCase):
    def test_rechaza_antes_de_encolar_objeto_mayor_a_512_mib(self) -> None:
        client = MagicMock()
        with (
            patch.object(pdf_router.storage, "Client", return_value=client),
            patch.object(
                pdf_router,
                "validate_gcs_zip_size",
                side_effect=ZipBudgetError("compressed_zip_too_large"),
            ),
            patch.object(pdf_router, "enqueue_zip_extraction") as enqueue,
        ):
            with self.assertRaises(HTTPException) as error:
                _run(pdf_router.start_pdf_zip_gcs_generation(
                    pdf_router.ProcessGcsZipPayload(gcsPath="uploads/123e4567-e89b-12d3-a456-426614174000.zip")
                ))

        self.assertEqual(error.exception.status_code, 413)
        enqueue.assert_not_called()

    def test_camino_directo_rechaza_antes_de_abrir_zip_mayor_a_512_mib(self) -> None:
        with tempfile.SpooledTemporaryFile() as raw:
            raw.seek(MAX_ZIP_COMPRESSED_BYTES)
            raw.write(b"x")
            raw.seek(0)
            upload = UploadFile(filename="grande.zip", file=raw)
            with self.assertRaises(HTTPException) as error:
                _run(pdf_router.start_pdf_zip_generation(upload))

        self.assertEqual(error.exception.status_code, 413)
