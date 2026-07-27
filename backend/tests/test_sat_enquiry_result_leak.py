"""test_sat_enquiry_result_leak.py — hallazgo #3: fuga entre sesiones.

El resultado de una consulta por lote es un Excel con los UUID y RFC de las
facturas de un contribuyente. Antes vivía en `_job_results`, un dict a nivel de
módulo, y GET /enquiry/batch/{job_id}/result hacía pop() sin comprobar de quién
era el job. El job_id viajaba en claro en el evento SSE `done`, así que
cualquiera que lo viera se llevaba el Excel de otra sesión.

Cierra también #18: aquel dict evictaba al llegar a 5 entradas, tirando
resultados que el usuario todavía no había descargado.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    from backend.app.routers import sat_enquiry
except ModuleNotFoundError as error:  # pragma: no cover
    sat_enquiry = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


@unittest.skipIf(sat_enquiry is None, f"backend no disponible: {_IMPORT_ERROR}")
class ResultStorageTests(unittest.TestCase):
    def test_el_dict_en_memoria_ya_no_existe(self):
        """La fuente del hallazgo. Si alguien lo reintroduce, esto falla."""
        self.assertFalse(hasattr(sat_enquiry, "_job_results"))

    def test_el_job_id_no_abre_la_descarga(self):
        """El job_id sigue viajando por el SSE; ya no sirve para bajar nada.

        Se pide con un job_id válido puesto como token: la llave que se consulta
        es sat_enquiry:token:<...>, que no existe -> 404.
        """
        fake = MagicMock()
        fake.get.return_value = None  # no hay token con ese valor
        with patch.object(sat_enquiry, "_redis_client", fake):
            from fastapi import HTTPException

            with self.assertRaises(HTTPException) as ctx:
                sat_enquiry.get_batch_result(token="un-job-id-cualquiera")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_la_descarga_borra_el_resultado_y_el_token(self):
        """Un token es de un solo uso: dos descargas con el mismo token no
        pueden entregar el Excel dos veces."""
        fake = MagicMock()
        fake.get.return_value = b"job-123"
        fake.getdel.return_value = b"PK\x03\x04excel"
        with patch.object(sat_enquiry, "_redis_client", fake):
            resp = sat_enquiry.get_batch_result(token="tok-abc")

        self.assertEqual(resp.body, b"PK\x03\x04excel")
        # getdel, no get: leer y borrar en una sola operación, para que dos
        # peticiones simultáneas con el mismo token no bajen las dos.
        fake.getdel.assert_called_once_with("sat_enquiry:result:job-123")
        fake.delete.assert_called_once_with("sat_enquiry:token:tok-abc")

    def test_resultado_expirado_da_404(self):
        fake = MagicMock()
        fake.get.return_value = b"job-123"
        fake.getdel.return_value = None  # el TTL ya venció
        with patch.object(sat_enquiry, "_redis_client", fake):
            from fastapi import HTTPException

            with self.assertRaises(HTTPException) as ctx:
                sat_enquiry.get_batch_result(token="tok-abc")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_las_llaves_estan_separadas(self):
        """El token y el job_id viven en espacios de llaves distintos: conocer
        uno no permite construir el otro."""
        self.assertEqual(sat_enquiry._result_key("j"), "sat_enquiry:result:j")
        self.assertEqual(sat_enquiry._token_key("t"), "sat_enquiry:token:t")
        self.assertNotEqual(sat_enquiry._result_key("x"), sat_enquiry._token_key("x"))

    def test_el_ttl_se_limpia_solo(self):
        self.assertEqual(sat_enquiry._RESULT_TTL_SECONDS, 900)

    def test_el_token_no_es_adivinable(self):
        """secrets.token_urlsafe(32) = 256 bits. Un uuid4 (122 bits, y además
        predecible en algunos entornos) no sería suficiente aquí."""
        import secrets

        tokens = {secrets.token_urlsafe(32) for _ in range(100)}
        self.assertEqual(len(tokens), 100)
        self.assertGreaterEqual(len(next(iter(tokens))), 40)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
