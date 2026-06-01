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
        self.assertEqual(result["claveProdServDescripcion"], "No existe en el catálogo")

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
        findings = _collect_catalog_findings(source)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertIn("catalog-clave-prod-serv-", findings[0]["id"])


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
        self.assertEqual(catalog_desc_or_sentinel(code), "No existe en el catálogo")


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
        self.assertEqual(payload["usoCfdiDescripcion"], "No existe en el catálogo")

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
        self.assertEqual(payload["metodoPagoDescripcion"], "No existe en el catálogo")

    def test_metodo_pago_ausente_devuelve_none(self):
        """Campo MetodoPago ausente (None) → no debe generar sentinel (regresión clave)."""
        cfdi = self._make_cfdi(mp=None)
        payload = build_cfdi_payload(cfdi)
        self.assertIsNone(payload["metodoPagoDescripcion"])

    def test_forma_pago_invalida_emite_sentinel(self):
        cfdi = self._make_cfdi(fp=self._make_code("ZZ", None))
        payload = build_cfdi_payload(cfdi)
        self.assertEqual(payload["formaPago"], "ZZ")
        self.assertEqual(payload["formaPagoDescripcion"], "No existe en el catálogo")

    def test_moneda_invalida_emite_sentinel(self):
        cfdi = self._make_cfdi(mon=self._make_code("ZZZ", None))
        payload = build_cfdi_payload(cfdi)
        self.assertEqual(payload["moneda"], "ZZZ")
        self.assertEqual(payload["monedaDescripcion"], "No existe en el catálogo")

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
        findings = _collect_catalog_findings(source)

        ids = [f["id"] for f in findings]
        self.assertIn("catalog-uso-cfdi-ZZZ", ids)
        finding = next(f for f in findings if f["id"] == "catalog-uso-cfdi-ZZZ")
        self.assertEqual(finding["severity"], "warning")
        self.assertEqual(finding["declared"], "ZZZ")
