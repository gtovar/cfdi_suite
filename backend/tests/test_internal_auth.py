"""test_internal_auth.py — el borde interno queda cerrado (hallazgo #2).

Los tres endpoints que sólo debería invocar Cloud Tasks
(`/api/internal/generate-pdf`, `/api/internal/extract-zip` y
`/api/cfdi/batch/worker-task`) viven en el mismo servicio público de Cloud Run
que el resto de la API. Antes de este fix, dos se defendían sólo con el header
`x-cloudtasks-queuename` -- que cualquiera puede mandar, porque el nombre de la
cola es público -- y el tercero no tenía absolutamente nada, además de leer una
ruta arbitraria de GCS del cuerpo del request.

Este archivo existe porque el resto de la suite parchea `verify_cloud_tasks` a
True (esos tests son sobre Redis y GCS, no sobre identidad). Sin esta cobertura
nadie estaría verificando el guard.

Cubre las dos direcciones, y las dos importan:
  - que un llamador anónimo NO pase (si sólo se probara esto, un `return False`
    constante aprobaría el test y rompería producción -- que es exactamente el
    fallo que advierte la AMPLIACIÓN de la spec #2);
  - que un token legítimo SÍ pase.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    from backend.app.routers import batch as batch_router
    from backend.app.services import internal_auth
except ModuleNotFoundError as error:  # pragma: no cover
    internal_auth = None
    batch_router = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None

_SA = "cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com"
_AUDIENCE = "https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app"
_HEADERS_OK = {
    "x-cloudtasks-queuename": "pdf-generator-queue",
    "Authorization": "Bearer token-firmado-por-google",
}


def _request(headers: dict) -> MagicMock:
    req = MagicMock()
    req.headers = headers
    return req


@unittest.skipIf(internal_auth is None, f"backend no disponible: {_IMPORT_ERROR}")
class VerifyCloudTasksTests(unittest.TestCase):
    def setUp(self) -> None:
        _aud = patch.object(internal_auth, "_AUDIENCE", _AUDIENCE)
        _aud.start()
        self.addCleanup(_aud.stop)

    def _con_claims(self, claims: dict):
        """Sustituye sólo la verificación criptográfica (que necesita las llaves
        públicas de Google y una red), no la lógica del guard."""
        return patch.object(
            internal_auth.id_token, "verify_oauth2_token", return_value=claims
        )

    def test_token_valido_de_la_sa_correcta_pasa(self) -> None:
        # La dirección que un `return False` constante rompería.
        with self._con_claims({"email": _SA, "email_verified": True}):
            self.assertTrue(internal_auth.verify_cloud_tasks(_request(_HEADERS_OK)))

    def test_sin_ningun_header_no_pasa(self) -> None:
        self.assertFalse(internal_auth.verify_cloud_tasks(_request({})))

    def test_header_de_cola_spoofeado_sin_token_no_pasa(self) -> None:
        """El ataque concreto del hallazgo: el nombre de la cola es público."""
        self.assertFalse(
            internal_auth.verify_cloud_tasks(
                _request({"x-cloudtasks-queuename": "pdf-generator-queue"})
            )
        )

    def test_token_que_no_verifica_no_pasa(self) -> None:
        with patch.object(
            internal_auth.id_token,
            "verify_oauth2_token",
            side_effect=ValueError("firma inválida"),
        ):
            self.assertFalse(internal_auth.verify_cloud_tasks(_request(_HEADERS_OK)))

    def test_token_valido_pero_de_otra_identidad_no_pasa(self) -> None:
        """Un token legítimo de otro servicio del mismo proyecto no sirve aquí."""
        with self._con_claims(
            {"email": "otro@ultra-acre-431617-p0.iam.gserviceaccount.com",
             "email_verified": True}
        ):
            self.assertFalse(internal_auth.verify_cloud_tasks(_request(_HEADERS_OK)))

    def test_email_sin_verificar_no_pasa(self) -> None:
        with self._con_claims({"email": _SA, "email_verified": False}):
            self.assertFalse(internal_auth.verify_cloud_tasks(_request(_HEADERS_OK)))

    def test_sin_api_url_no_pasa(self) -> None:
        """Un audience vacío hace que verify_oauth2_token acepte cualquier
        destinatario: es peor que no verificar, porque aparenta verificar."""
        with patch.object(internal_auth, "_AUDIENCE", ""):
            with self._con_claims({"email": _SA, "email_verified": True}):
                self.assertFalse(internal_auth.verify_cloud_tasks(_request(_HEADERS_OK)))


@unittest.skipIf(batch_router is None, f"backend no disponible: {_IMPORT_ERROR}")
class AllowedGcsPrefixTests(unittest.TestCase):
    """Defensa en profundidad sobre el token: /worker-task usa una ruta que
    viene del cuerpo del request para leer del bucket COMPARTIDO, donde también
    viven uploads/ (los ZIP de los usuarios) y pdfs/.

    OJO: la AMPLIACIÓN de la spec #2 propone el prefijo "xml_temp_analysis/",
    que no existe en el código. La ruta real la arma batch_analyze como
    f"xml_temp/analysis_{batch_id}/{fname}". Este test fija el prefijo correcto
    para que nadie lo "corrija" de vuelta al de la spec y rompa el análisis
    masivo en producción.
    """

    def _permitida(self, path) -> bool:
        p = batch_router._ALLOWED_GCS_PREFIX
        return bool(path) and path.startswith(p) and ".." not in path

    def test_el_prefijo_es_el_que_produce_batch_analyze(self) -> None:
        self.assertEqual(batch_router._ALLOWED_GCS_PREFIX, "xml_temp/analysis_")

    def test_acepta_la_ruta_legitima(self) -> None:
        self.assertTrue(self._permitida("xml_temp/analysis_batch-1/factura.xml"))

    def test_rechaza_otros_prefijos_del_mismo_bucket(self) -> None:
        for path in (
            "uploads/zip-de-otro-usuario.zip",
            "pdfs/documento-de-otro.pdf",
            "xml_temp/otro-job-id.xml",
        ):
            with self.subTest(path=path):
                self.assertFalse(self._permitida(path))

    def test_rechaza_traversal(self) -> None:
        self.assertFalse(self._permitida("xml_temp/analysis_../../uploads/x.zip"))

    def test_rechaza_vacio_y_redis_key_legado(self) -> None:
        for path in (None, "", "xml_payload:batch-1:factura.xml"):
            with self.subTest(path=path):
                self.assertFalse(self._permitida(path))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
