"""
Tests para src/cfdi/engine/python-satcfdi-wrapper.py

Cubre el comportamiento de normalize_concept frente a claves SAT
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
