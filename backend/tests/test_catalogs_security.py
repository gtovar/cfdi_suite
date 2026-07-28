from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.app.services import catalogs


class CatalogsSecurityTests(unittest.TestCase):
    def tearDown(self) -> None:
        catalogs._SMALL.clear()
        catalogs._lookup_big.cache_clear()

    def test_allowlist_contiene_exactamente_catalogos_del_renderer(self) -> None:
        self.assertEqual(
            catalogs._ALLOWED_TABLES,
            {
                "c_ClaveUnidad", "c_RegimenFiscal", "c_UsoCFDI", "c_Moneda",
                "c_FormaPago", "c_MetodoPago",
            },
        )

    def test_tabla_fuera_de_allowlist_no_llega_a_sql(self) -> None:
        connection = MagicMock()
        with patch.object(catalogs, "_get_conn", return_value=connection):
            with self.assertRaises(ValueError):
                catalogs._load_all("c_ClaveUnidad; DROP TABLE users; --")
        connection.cursor.assert_not_called()

    def test_tabla_permitida_se_interpela_solo_despues_de_validacion(self) -> None:
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.cursor.return_value = cursor
        with patch.object(catalogs, "_get_conn", return_value=connection):
            self.assertEqual(catalogs._load_all("c_ClaveUnidad"), {})
        cursor.execute.assert_called_once_with("SELECT key, value FROM C756_c_ClaveUnidad")

    def test_integridad_acepta_db_con_tamano_y_hash_esperados(self) -> None:
        contents = b"catalog-db-fixture"
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "catalogs.db"
            db.write_bytes(contents)
            with (
                patch.object(catalogs, "_CATALOG_DB_EXPECTED_SIZE", len(contents)),
                patch.object(catalogs, "_CATALOG_DB_EXPECTED_SHA256", hashlib.sha256(contents).hexdigest()),
            ):
                catalogs._verify_catalog_db(db)

    def test_integridad_rechaza_hash_distinto_antes_de_deserializar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "catalogs.db"
            db.write_bytes(b"altered")
            with (
                patch.object(catalogs, "_CATALOG_DB_EXPECTED_SIZE", len(b"altered")),
                patch.object(catalogs, "_CATALOG_DB_EXPECTED_SHA256", "0" * 64),
            ):
                with self.assertRaises(catalogs.CatalogIntegrityError):
                    catalogs._verify_catalog_db(db)

    def test_error_de_integridad_no_se_oculta_como_descripcion_vacia(self) -> None:
        with patch.object(catalogs, "_load_all", side_effect=catalogs.CatalogIntegrityError("alterada")):
            with self.assertRaises(catalogs.CatalogIntegrityError):
                catalogs.describe("c_ClaveUnidad", "ACT")

    def test_db_instalada_coincide_con_la_version_aprobada(self) -> None:
        try:
            path = catalogs._catalog_db_path()
        except ModuleNotFoundError as error:
            self.skipTest(f"satcfdi no instalado: {error}")
        catalogs._verify_catalog_db(path)


if __name__ == "__main__":
    unittest.main()
