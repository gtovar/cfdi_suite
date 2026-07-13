"""
Tests de app/services/zip_manifest.py -- las funciones puras compartidas
entre el constructor del manifiesto (pdf.py) y cada tarea del Cloud Run Job
de shards (batch_shard_worker.py). Ver el docstring del módulo para por qué
importa que nunca diverjan.
"""
from __future__ import annotations

import unittest
import zipfile

try:
    from backend.app.services import zip_manifest
except ModuleNotFoundError as error:
    zip_manifest = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


def _info(filename: str) -> zipfile.ZipInfo:
    return zipfile.ZipInfo(filename=filename)


@unittest.skipIf(zip_manifest is None, f"backend no disponible: {_IMPORT_ERROR}")
class IsValidXmlEntryTests(unittest.TestCase):
    def test_acepta_xml(self) -> None:
        self.assertTrue(zip_manifest.is_valid_xml_entry(_info("factura.xml")))
        self.assertTrue(zip_manifest.is_valid_xml_entry(_info("FACTURA.XML")))

    def test_rechaza_no_xml(self) -> None:
        self.assertFalse(zip_manifest.is_valid_xml_entry(_info("factura.pdf")))
        self.assertFalse(zip_manifest.is_valid_xml_entry(_info("readme.txt")))

    def test_rechaza_macosx_y_dsstore(self) -> None:
        self.assertFalse(zip_manifest.is_valid_xml_entry(_info("__MACOSX/factura.xml")))
        self.assertFalse(zip_manifest.is_valid_xml_entry(_info(".DS_Store")))


@unittest.skipIf(zip_manifest is None, f"backend no disponible: {_IMPORT_ERROR}")
class ComputeJobIdTests(unittest.TestCase):
    def test_deterministico(self) -> None:
        a = zip_manifest.compute_job_id("batch-1", "factura.xml")
        b = zip_manifest.compute_job_id("batch-1", "factura.xml")
        self.assertEqual(a, b)

    def test_nombres_distintos_mismo_batch_no_colisionan(self) -> None:
        a = zip_manifest.compute_job_id("batch-1", "factura1.xml")
        b = zip_manifest.compute_job_id("batch-1", "factura2.xml")
        self.assertNotEqual(a, b)

    def test_mismo_nombre_batches_distintos_no_colisionan(self) -> None:
        a = zip_manifest.compute_job_id("batch-1", "factura.xml")
        b = zip_manifest.compute_job_id("batch-2", "factura.xml")
        self.assertNotEqual(a, b)


@unittest.skipIf(zip_manifest is None, f"backend no disponible: {_IMPORT_ERROR}")
class BuildManifestTests(unittest.TestCase):
    def test_construye_job_id_a_filename_filtrando_invalidos(self) -> None:
        infolist = [
            _info("factura1.xml"),
            _info("factura2.xml"),
            _info("__MACOSX/factura1.xml"),
            _info("no_es_xml.txt"),
        ]
        manifest = zip_manifest.build_manifest(infolist, "batch-x")

        self.assertEqual(len(manifest), 2)
        self.assertEqual(set(manifest.values()), {"factura1.xml", "factura2.xml"})

    def test_manifest_coincide_con_compute_job_id_independiente(self) -> None:
        """La prueba que protege el diseño: cualquiera que llame
        compute_job_id() por su cuenta con el mismo batch_id+filename debe
        llegar exactamente al mismo job_id que build_manifest() -- es la
        garantía de que el manifiesto (una sola instancia) y cada tarea del
        shard (N instancias, cada una recalculando por su cuenta) nunca
        divergen."""
        infolist = [_info("factura1.xml"), _info("factura2.xml")]
        manifest = zip_manifest.build_manifest(infolist, "batch-y")

        expected_job_id = zip_manifest.compute_job_id("batch-y", "factura1.xml")
        self.assertIn(expected_job_id, manifest)
        self.assertEqual(manifest[expected_job_id], "factura1.xml")


if __name__ == "__main__":
    unittest.main()
