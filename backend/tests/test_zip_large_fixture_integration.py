"""Integración opt-in para el ZIP real compatible de 367 MB.

No se versiona un archivo de ese tamaño ni datos de clientes. El canario/CI
proporciona su ruta con ``ZIP_367MB_FIXTURE`` y habilita explícitamente
``RUN_LARGE_ZIP_INTEGRATION=1``.
"""
from __future__ import annotations

import os
from pathlib import Path
import unittest
import zipfile

from backend.app.services.zip_manifest import MAX_ZIP_COMPRESSED_BYTES, inspect_zip_manifest


@unittest.skipUnless(os.getenv("RUN_LARGE_ZIP_INTEGRATION") == "1", "integración ZIP grande no habilitada")
class LargeZipFixtureIntegrationTests(unittest.TestCase):
    def test_fixture_real_compatible_es_aceptado(self) -> None:
        fixture = Path(os.environ["ZIP_367MB_FIXTURE"])
        self.assertTrue(fixture.is_file(), f"fixture no encontrado: {fixture}")
        self.assertLessEqual(fixture.stat().st_size, MAX_ZIP_COMPRESSED_BYTES)

        with zipfile.ZipFile(fixture) as archive:
            validated = inspect_zip_manifest(archive.infolist(), "fixture-367mb")

        self.assertGreater(len(validated.xml_entries), 0)

