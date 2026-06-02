"""
Test de integración: wrapper Python + _normalize_cfdi con XML real y satcfdi real.

Cubre el gap entre tests unitarios (que usan mocks) y el comportamiento real de satcfdi:
verifica que un CFDI con códigos inválidos pasa por parse_payload → _normalize_cfdi
y produce los findings esperados de catálogo de cabecera.
"""
from __future__ import annotations

import importlib.util
import types
import unittest
from pathlib import Path

_WRAPPER_PATH = Path(__file__).parents[2] / "src" / "cfdi" / "engine" / "python-satcfdi-wrapper.py"
_FIXTURE_PATH = Path(__file__).parent.parent / "test-fixtures" / "cfdi-catalogo-invalido-cabecera.xml"


def _load_wrapper() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("python_satcfdi_wrapper", _WRAPPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_wrapper = _load_wrapper()


class TestCatalogIntegrationRealSatcfdi(unittest.TestCase):
    """
    Integración real: parse_payload con XML de fixture → _normalize_cfdi.
    Requiere que python-satcfdi esté instalado en el entorno.
    """

    @classmethod
    def setUpClass(cls):
        cls.xml = _FIXTURE_PATH.read_text(encoding="utf-8")
        result = _wrapper.parse_payload(cls.xml)
        if not result.get("satcfdiAvailable"):
            raise unittest.SkipTest("python-satcfdi no disponible en este entorno")
        cls.parse_result = result

    def test_parse_ok(self):
        self.assertTrue(self.parse_result["ok"])
        self.assertIn("cfdi", self.parse_result)

    def test_uso_cfdi_invalido_emite_sentinel_real(self):
        cfdi = self.parse_result["cfdi"]
        self.assertEqual(cfdi["usoCfdi"], "ZZZ")
        self.assertEqual(cfdi["usoCfdiDescripcion"], _wrapper.SENTINEL_INVALIDO)

    def test_forma_pago_invalida_emite_sentinel_real(self):
        cfdi = self.parse_result["cfdi"]
        self.assertEqual(cfdi["formaPago"], "ZZ")
        self.assertEqual(cfdi["formaPagoDescripcion"], _wrapper.SENTINEL_INVALIDO)

    def test_metodo_pago_ausente_no_emite_sentinel(self):
        """En este CFDI tipo P, MetodoPago no está presente → debe ser None, no sentinel."""
        cfdi = self.parse_result["cfdi"]
        self.assertIsNone(cfdi.get("metodoPagoDescripcion"))

    def test_normalize_cfdi_genera_findings_de_catalogo(self):
        from backend.app.services.analyze_cfdi import _normalize_cfdi

        normalized = _normalize_cfdi(self.parse_result["cfdi"])
        self.assertIsNotNone(normalized)

        finding_ids = {f["id"] for f in normalized["findings"]}
        self.assertIn("catalog-uso-cfdi-ZZZ", finding_ids)
        self.assertIn("catalog-forma-pago-ZZ", finding_ids)

    def test_normalize_cfdi_no_genera_finding_de_metodo_pago_ausente(self):
        from backend.app.services.analyze_cfdi import _normalize_cfdi

        normalized = _normalize_cfdi(self.parse_result["cfdi"])
        finding_ids = {f["id"] for f in normalized["findings"]}
        metodo_findings = [fid for fid in finding_ids if fid.startswith("catalog-metodo-pago-")]
        self.assertEqual(metodo_findings, [])

    def test_findings_tienen_severity_warning(self):
        from backend.app.services.analyze_cfdi import _normalize_cfdi

        normalized = _normalize_cfdi(self.parse_result["cfdi"])
        catalog_findings = [f for f in normalized["findings"] if f["id"].startswith("catalog-uso-cfdi-")]
        self.assertEqual(len(catalog_findings), 1)
        self.assertEqual(catalog_findings[0]["severity"], "warning")
        self.assertEqual(catalog_findings[0]["declared"], "ZZZ")

    def test_clave_unidad_invalida_emite_sentinel_real(self):
        """El segundo concepto del fixture tiene ClaveUnidad='ZZZZ' → sentinel en wrapper."""
        cfdi = self.parse_result["cfdi"]
        conceptos = cfdi.get("conceptos", [])
        self.assertGreaterEqual(len(conceptos), 2)
        segundo = conceptos[1]
        self.assertEqual(segundo["claveUnidad"], "ZZZZ")
        self.assertEqual(segundo["claveUnidadDescripcion"], _wrapper.SENTINEL_INVALIDO)

    def test_normalize_cfdi_genera_finding_clave_unidad(self):
        from backend.app.services.analyze_cfdi import _normalize_cfdi

        normalized = _normalize_cfdi(self.parse_result["cfdi"])
        self.assertIsNotNone(normalized)
        finding_ids = {f["id"] for f in normalized["findings"]}
        self.assertIn("catalog-clave-unidad-ZZZZ", finding_ids)

    def test_finding_clave_unidad_tiene_severity_warning(self):
        from backend.app.services.analyze_cfdi import _normalize_cfdi

        normalized = _normalize_cfdi(self.parse_result["cfdi"])
        findings = [f for f in normalized["findings"] if f["id"] == "catalog-clave-unidad-ZZZZ"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertEqual(findings[0]["declared"], "ZZZZ")

    def test_clave_unidad_valida_no_genera_finding(self):
        """El primer concepto tiene ClaveUnidad='ACT' (válida) → no genera finding."""
        from backend.app.services.analyze_cfdi import _normalize_cfdi

        normalized = _normalize_cfdi(self.parse_result["cfdi"])
        findings = [f for f in normalized["findings"] if f["id"] == "catalog-clave-unidad-ACT"]
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
