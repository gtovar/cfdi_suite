"""test_shell_service_ssrf.py — hallazgo #35: WeasyPrint no sale a la red.

POST /api/templates/{id}/shell-preview acepta HTML crudo y WeasyPrint resuelve
por su cuenta todo <img src>, <link> y @import. Sin un url_fetcher propio, el
renderer es un proxy de peticiones salientes con la identidad de la instancia de
Cloud Run: servicios internos, redes privadas, el metadata server y port
scanning por diferencia de tiempos.

base_url=None sólo cortaba las URLs relativas. Las absolutas salían: comprobado
levantando un listener local y viendo llegar la petición.
"""
from __future__ import annotations

import unittest

try:
    from backend.app.services import shell_service
except ModuleNotFoundError as error:  # pragma: no cover
    shell_service = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


@unittest.skipIf(shell_service is None, f"backend no disponible: {_IMPORT_ERROR}")
class RestrictedUrlFetcherTests(unittest.TestCase):
    def _bloquea(self, url: str) -> bool:
        try:
            shell_service._restricted_url_fetcher(url)
        except ValueError:
            return True
        except Exception:
            # Cualquier otra excepción significa que ya intentó resolverla:
            # el guard no la detuvo.
            return False
        return False

    def test_permite_data_uri(self):
        """Los logos embebidos son el caso legítimo y no deben romperse."""
        self.assertFalse(self._bloquea("data:image/png;base64,iVBORw0KGgo="))

    def test_bloquea_metadata_server_y_redes_internas(self):
        for url in (
            "http://169.254.169.254/computeMetadata/v1/",
            "http://127.0.0.1:8080/admin",
            "http://localhost:6379/",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
        ):
            with self.subTest(url=url):
                self.assertTrue(self._bloquea(url))

    def test_bloquea_file_scheme(self):
        for url in ("file:///etc/passwd", "file:///proc/self/environ"):
            with self.subTest(url=url):
                self.assertTrue(self._bloquea(url))

    def test_bloquea_https_externo(self):
        """_ALLOWED_HOSTS está vacío a propósito: cero red, ni siquiera al PAC."""
        self.assertTrue(self._bloquea("https://servicios.diverza.com/api/v2/"))

    def test_allowlist_de_hosts_vacia_por_defecto(self):
        """Si alguien añade un host aquí, que sea una decisión visible en el
        diff y no un efecto colateral."""
        self.assertEqual(shell_service._ALLOWED_HOSTS, set())
        self.assertEqual(shell_service._ALLOWED_SCHEMES, {"data"})

    def test_los_tres_render_usan_el_fetcher(self):
        """Los 3 call sites de HTML() deben pasar url_fetcher; si alguien añade
        un cuarto sin él, vuelve el SSRF por esa vía."""
        import inspect

        fuente = inspect.getsource(shell_service)
        self.assertEqual(fuente.count("url_fetcher=_restricted_url_fetcher"), 3)
        self.assertEqual(fuente.count("HTML("), 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
