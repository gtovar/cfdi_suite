"""
Tests para src/cfdi/engine/python-satcfdi-wrapper.py

Cubre el comportamiento de normalize_concept y build_cfdi_payload frente a claves SAT
válidas e inválidas, verificando que el sentinel "No existe en el catálogo"
se emite correctamente para que _collect_catalog_findings lo detecte.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# El wrapper usa guiones en el nombre — importar vía importlib
_WRAPPER_PATH = Path(__file__).parents[2] / "src" / "cfdi" / "engine" / "python-satcfdi-wrapper.py"


def _load_wrapper() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("python_satcfdi_wrapper", _WRAPPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_wrapper = _load_wrapper()
normalize_concept = _wrapper.normalize_concept
build_cfdi_payload = _wrapper.build_cfdi_payload
catalog_desc_or_sentinel = _wrapper.catalog_desc_or_sentinel
SENTINEL_INVALIDO = _wrapper.SENTINEL_INVALIDO


def _make_concepto(clave_prod_serv, description, importe="100.00"):
    """Construye un dict de concepto simulando el output de satcfdi."""
    cprod = MagicMock()
    cprod.description = description

    return {
        "ClaveProdServ": cprod if description is not None else None,
        "Descripcion": "Servicio de prueba",
        "Cantidad": "1",
        "ValorUnitario": importe,
        "Importe": importe,
        "ObjetoImp": None,
        "Impuestos": {},
        "_raw_clave": clave_prod_serv,
    }


class TestNormalizeConceptClaveProdServ(unittest.TestCase):

    def _run(self, description):
        """Llama a normalize_concept con un cprod simulado."""
        cprod = MagicMock()
        cprod.description = description

        # Construir manualmente el concepto dict que espera normalize_concept
        concepto = {
            "ClaveProdServ": cprod,
            "Descripcion": "Servicio prueba",
            "Cantidad": "1",
            "ValorUnitario": "100.00",
            "Importe": "100.00",
            "ObjetoImp": None,
            "Impuestos": {},
        }
        return normalize_concept(concepto)

    def test_clave_valida_usa_descripcion_real(self):
        """Clave reconocida por satcfdi → descripción del catálogo."""
        result = self._run("Servicios de tecnología de la información")
        self.assertEqual(
            result["claveProdServDescripcion"],
            "Servicios de tecnología de la información",
        )

    def test_clave_invalida_emite_sentinel(self):
        """
        Clave desconocida → satcfdi retorna cprod sin description (None).
        El wrapper debe emitir el sentinel que _collect_catalog_findings detecta.
        """
        result = self._run(None)
        self.assertEqual(result["claveProdServDescripcion"], SENTINEL_INVALIDO)

    def test_clave_ausente_no_emite_sentinel(self):
        """Concepto sin ClaveProdServ (cprod=None) → descripción None, sin sentinel."""
        concepto = {
            "ClaveProdServ": None,
            "Descripcion": "Sin clave",
            "Cantidad": "1",
            "ValorUnitario": "100.00",
            "Importe": "100.00",
            "ObjetoImp": None,
            "Impuestos": {},
        }
        result = normalize_concept(concepto)
        self.assertIsNone(result["claveProdServDescripcion"])

    def test_sentinel_activa_catalog_finding(self):
        """
        Integración mínima: el sentinel emitido por el wrapper
        debe ser detectado por _collect_catalog_findings.
        """
        from backend.app.services.analyze_cfdi import _collect_catalog_findings

        result = self._run(None)
        source = {"conceptos": [result]}
        findings, impacted = _collect_catalog_findings(source)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertIn("catalog-clave-prod-serv-", findings[0]["id"])
        self.assertIn(0, impacted)


class TestCatalogDescOrSentinel(unittest.TestCase):
    """Prueba la función helper que abstrae el patrón de sentinel para todos los catálogos."""

    def _make_code(self, description):
        obj = MagicMock()
        obj.description = description
        return obj

    def test_field_absent_returns_none(self):
        """Campo ausente (None) → None, no sentinel."""
        self.assertIsNone(catalog_desc_or_sentinel(None))

    def test_valid_code_returns_description(self):
        """Código válido → devuelve la descripción del catálogo."""
        code = self._make_code("Por definir")
        self.assertEqual(catalog_desc_or_sentinel(code), "Por definir")

    def test_invalid_code_returns_sentinel(self):
        """Código desconocido (description=None) → emite sentinel."""
        code = self._make_code(None)
        self.assertEqual(catalog_desc_or_sentinel(code), SENTINEL_INVALIDO)


class TestBuildCfdiPayloadHeaderCatalogs(unittest.TestCase):
    """Verifica que build_cfdi_payload emite los campos de descripción de catálogo de cabecera."""

    def _make_code(self, raw_code, description):
        obj = MagicMock()
        obj.code = raw_code
        obj.description = description
        return obj

    def _make_cfdi(self, uso_cfdi=None, mp=None, fp=None, mon=None):
        """Construye un dict minimal que simula la interfaz de un objeto CFDI de satcfdi."""
        return {
            "Version": "4.0",
            "Fecha": "2026-01-01T00:00:00",
            "Complemento": {},
            "Emisor": {"Nombre": "Test", "Rfc": "TEST010101AAA"},
            "Receptor": {"Nombre": "Receptor", "Rfc": "RECEPT010101BBB", "UsoCFDI": uso_cfdi},
            "SubTotal": 100,
            "Descuento": None,
            "Total": 116,
            "Conceptos": [],
            "Impuestos": None,
            "MetodoPago": mp,
            "FormaPago": fp,
            "Moneda": mon,
        }

    def test_uso_cfdi_invalido_emite_sentinel(self):
        cfdi = self._make_cfdi(uso_cfdi=self._make_code("ZZZ", None))
        payload = build_cfdi_payload(cfdi)
        self.assertEqual(payload["usoCfdi"], "ZZZ")
        self.assertEqual(payload["usoCfdiDescripcion"], SENTINEL_INVALIDO)

    def test_uso_cfdi_valido_no_emite_sentinel(self):
        cfdi = self._make_cfdi(uso_cfdi=self._make_code("G03", "Gastos en general"))
        payload = build_cfdi_payload(cfdi)
        self.assertEqual(payload["usoCfdi"], "G03")
        self.assertEqual(payload["usoCfdiDescripcion"], "Gastos en general")

    def test_uso_cfdi_ausente_devuelve_none(self):
        cfdi = self._make_cfdi(uso_cfdi=None)
        payload = build_cfdi_payload(cfdi)
        self.assertIsNone(payload["usoCfdiDescripcion"])

    def test_metodo_pago_invalido_emite_sentinel(self):
        cfdi = self._make_cfdi(mp=self._make_code("ZZ", None))
        payload = build_cfdi_payload(cfdi)
        self.assertEqual(payload["metodoPago"], "ZZ")
        self.assertEqual(payload["metodoPagoDescripcion"], SENTINEL_INVALIDO)

    def test_metodo_pago_ausente_devuelve_none(self):
        """Campo MetodoPago ausente (None) → no debe generar sentinel (regresión clave)."""
        cfdi = self._make_cfdi(mp=None)
        payload = build_cfdi_payload(cfdi)
        self.assertIsNone(payload["metodoPagoDescripcion"])

    def test_forma_pago_invalida_emite_sentinel(self):
        cfdi = self._make_cfdi(fp=self._make_code("ZZ", None))
        payload = build_cfdi_payload(cfdi)
        self.assertEqual(payload["formaPago"], "ZZ")
        self.assertEqual(payload["formaPagoDescripcion"], SENTINEL_INVALIDO)

    def test_moneda_invalida_emite_sentinel(self):
        cfdi = self._make_cfdi(mon=self._make_code("ZZZ", None))
        payload = build_cfdi_payload(cfdi)
        self.assertEqual(payload["moneda"], "ZZZ")
        self.assertEqual(payload["monedaDescripcion"], SENTINEL_INVALIDO)

    def test_moneda_valida_no_emite_sentinel(self):
        cfdi = self._make_cfdi(mon=self._make_code("MXN", "Peso Mexicano"))
        payload = build_cfdi_payload(cfdi)
        self.assertEqual(payload["monedaDescripcion"], "Peso Mexicano")

    def test_sentinel_header_activa_catalog_finding(self):
        """Integración: sentinel en usoCFDI → finding generado por _collect_catalog_findings."""
        from backend.app.services.analyze_cfdi import _collect_catalog_findings

        cfdi = self._make_cfdi(uso_cfdi=self._make_code("ZZZ", None))
        payload = build_cfdi_payload(cfdi)
        source = {**payload, "conceptos": []}
        findings, _ = _collect_catalog_findings(source)

        ids = [f["id"] for f in findings]
        self.assertIn("catalog-uso-cfdi-ZZZ", ids)
        finding = next(f for f in findings if f["id"] == "catalog-uso-cfdi-ZZZ")
        self.assertEqual(finding["severity"], "warning")
        self.assertEqual(finding["declared"], "ZZZ")


class TestNormalizeConceptClaveUnidad(unittest.TestCase):
    """Verifica que normalize_concept maneja ClaveUnidad con el mismo patrón sentinel que ClaveProdServ."""

    def _run(self, description):
        cunidad = MagicMock()
        cunidad.description = description
        concepto = {
            "ClaveProdServ": None,
            "ClaveUnidad": cunidad,
            "Descripcion": "Servicio prueba",
            "Cantidad": "1",
            "ValorUnitario": "100.00",
            "Importe": "100.00",
            "ObjetoImp": None,
            "Impuestos": {},
        }
        return normalize_concept(concepto)

    def test_clave_unidad_valida_usa_descripcion_real(self):
        result = self._run("Actividad")
        self.assertEqual(result["claveUnidadDescripcion"], "Actividad")

    def test_clave_unidad_invalida_emite_sentinel(self):
        result = self._run(None)
        self.assertEqual(result["claveUnidadDescripcion"], SENTINEL_INVALIDO)

    def test_clave_unidad_ausente_devuelve_none(self):
        concepto = {
            "ClaveProdServ": None,
            "ClaveUnidad": None,
            "Descripcion": "Sin unidad",
            "Cantidad": "1",
            "ValorUnitario": "0",
            "Importe": "0",
            "ObjetoImp": None,
            "Impuestos": {},
        }
        result = normalize_concept(concepto)
        self.assertIsNone(result["claveUnidadDescripcion"])

    def test_sentinel_clave_unidad_activa_catalog_finding(self):
        """Integración: sentinel en claveUnidad → finding generado por _collect_catalog_findings."""
        from backend.app.services.analyze_cfdi import _collect_catalog_findings

        result = self._run(None)
        source = {"conceptos": [result]}
        findings, impacted = _collect_catalog_findings(source)

        ids = [f["id"] for f in findings]
        unidad_findings = [fid for fid in ids if fid.startswith("catalog-clave-unidad-")]
        self.assertEqual(len(unidad_findings), 1)
        finding = next(f for f in findings if f["id"].startswith("catalog-clave-unidad-"))
        self.assertEqual(finding["severity"], "warning")
        self.assertIn(0, impacted)


_FIXTURE_SELLO_REAL = Path(__file__).parents[2] / "backend" / "test-fixtures" / "pago_h_e951128469_ingreso_ieps_exento.xml"


class TestVerifySelloRealFixture(unittest.TestCase):
    """Integración real con satcfdi: verifica que verify_sello funciona con un CFDI con sello real."""

    @classmethod
    def setUpClass(cls):
        if not _FIXTURE_SELLO_REAL.exists():
            raise unittest.SkipTest(f"Fixture no encontrado: {_FIXTURE_SELLO_REAL}")
        cls.xml = _FIXTURE_SELLO_REAL.read_text(encoding="utf-8")
        result = _wrapper.parse_payload(cls.xml)
        if not result.get("satcfdiAvailable"):
            raise unittest.SkipTest("python-satcfdi no disponible")
        cls.parse_result = result
        cls.sv = result["cfdi"]["selloVerificacion"]

    def test_sello_verif_presente_en_payload(self):
        self.assertIn("selloVerificacion", self.parse_result["cfdi"])

    def test_status_no_es_missing(self):
        """El fixture tiene sello y certificado reales → no debe ser 'missing'."""
        self.assertNotEqual(self.sv["status"], "missing")

    def test_status_no_es_error(self):
        """No debe haber errores de procesamiento (solo valid/invalid esperado)."""
        self.assertNotEqual(self.sv["status"], "error", msg=self.sv.get("error"))

    def test_sello_firma_es_valida(self):
        """La firma criptográfica del CFDI debe ser válida (fixture UAT con sello correcto)."""
        self.assertTrue(self.sv["checks"]["selloFirma"])

    def test_numero_certificado_cuadra(self):
        self.assertTrue(self.sv["checks"]["numeroCertificado"])

    def test_rfc_emisor_cuadra(self):
        self.assertTrue(self.sv["checks"]["rfcEmisor"])

    def test_cfdi_valido_no_produce_findings_firma_sello(self):
        """Un CFDI con sello criptográficamente válido no debe emitir el finding firma-sello-invalido."""
        from backend.app.services.analyze_cfdi import _normalize_cfdi
        normalized = _normalize_cfdi(self.parse_result["cfdi"])
        self.assertIsNotNone(normalized)
        firma_sello_findings = [f for f in normalized["findings"] if f["id"] == "firma-sello-invalido"]
        self.assertEqual(firma_sello_findings, [])


class TestVerifySelloMissing(unittest.TestCase):
    """Verifica comportamiento cuando Sello/Certificado están vacíos."""

    def _make_minimal_cfdi(self, sello="", certificado=""):
        from unittest.mock import MagicMock
        cfdi = {}
        cfdi["Sello"] = sello
        cfdi["Certificado"] = certificado
        cfdi["NoCertificado"] = "30001000000400002460"
        cfdi["Fecha"] = None
        cfdi["Emisor"] = {"Rfc": "TEST010101AAA"}
        return cfdi

    def test_empty_sello_returns_missing(self):
        cfdi = self._make_minimal_cfdi(sello="", certificado="")
        result = _wrapper.verify_sello(cfdi)
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["checks"], {})
        self.assertIsNone(result["error"])


class TestVerifySelloVersionAlgorithm(unittest.TestCase):
    """Verifica que verify_sello selecciona SHA-1 para CFDI 3.x y SHA-256 para CFDI 4.0."""

    def _make_cfdi_stub(self, version, sello, certificado):
        """Stub mínimo que imita la interfaz del objeto CFDI de satcfdi."""
        from unittest.mock import MagicMock, patch
        cfdi = MagicMock()
        cfdi.get = lambda k, default=None: {
            "Version": version,
            "Sello": sello,
            "Certificado": certificado,
            "NoCertificado": "00000000000000000000",
            "Fecha": None,
            "Emisor": {"Rfc": "TEST010101AAA"},
        }.get(k, default)
        cfdi.cadena_original = MagicMock(return_value="||cadena||")
        return cfdi

    def test_version_40_usa_sha256(self):
        """Para CFDI 4.0 se debe llamar a verify_sha256, no a verify_sha1."""
        from unittest.mock import MagicMock, patch
        import base64
        cfdi = self._make_cfdi_stub("4.0", "ZmFrZXNlbGxv", "ZmFrZWNlcnQ=")
        with patch("satcfdi.models.certificate.Certificate.load_certificate") as mock_load, \
             patch("satcfdi.transform.verify_certificate", return_value=False):
            mock_cert = MagicMock()
            mock_cert.certificate_number = "00000000000000000000"
            mock_cert.rfc = "TEST010101AAA"
            mock_cert.verify_sha256 = MagicMock(return_value=True)
            mock_cert.verify_sha1 = MagicMock(return_value=True)
            mock_load.return_value = mock_cert
            _wrapper.verify_sello(cfdi)
            mock_cert.verify_sha256.assert_called_once()
            mock_cert.verify_sha1.assert_not_called()

    def test_version_33_usa_sha1(self):
        """Para CFDI 3.3 se debe llamar a verify_sha1, no a verify_sha256."""
        from unittest.mock import MagicMock, patch
        cfdi = self._make_cfdi_stub("3.3", "ZmFrZXNlbGxv", "ZmFrZWNlcnQ=")
        with patch("satcfdi.models.certificate.Certificate.load_certificate") as mock_load, \
             patch("satcfdi.transform.verify_certificate", return_value=False):
            mock_cert = MagicMock()
            mock_cert.certificate_number = "00000000000000000000"
            mock_cert.rfc = "TEST010101AAA"
            mock_cert.verify_sha256 = MagicMock(return_value=True)
            mock_cert.verify_sha1 = MagicMock(return_value=True)
            mock_load.return_value = mock_cert
            _wrapper.verify_sello(cfdi)
            mock_cert.verify_sha1.assert_called_once()
            mock_cert.verify_sha256.assert_not_called()

    def test_version_32_usa_sha1(self):
        """Para CFDI 3.2 se debe llamar a verify_sha1."""
        from unittest.mock import MagicMock, patch
        cfdi = self._make_cfdi_stub("3.2", "ZmFrZXNlbGxv", "ZmFrZWNlcnQ=")
        with patch("satcfdi.models.certificate.Certificate.load_certificate") as mock_load, \
             patch("satcfdi.transform.verify_certificate", return_value=False):
            mock_cert = MagicMock()
            mock_cert.certificate_number = "00000000000000000000"
            mock_cert.rfc = "TEST010101AAA"
            mock_cert.verify_sha256 = MagicMock(return_value=True)
            mock_cert.verify_sha1 = MagicMock(return_value=True)
            mock_load.return_value = mock_cert
            _wrapper.verify_sello(cfdi)
            mock_cert.verify_sha1.assert_called_once()
            mock_cert.verify_sha256.assert_not_called()
