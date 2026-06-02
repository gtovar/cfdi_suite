from __future__ import annotations

import unittest

from backend.app.services.analyze_cfdi import (
    _build_verdict,
    _collect_catalog_findings,
    _collect_concept_diffs,
    _collect_math_findings,
    _collect_sello_findings,
    _collect_tax_audit_group_findings,
    _map_tax_entry,
    _normalize_cfdi,
    _process_concepts,
    _process_global_taxes,
)


def _make_cfdi(
    subtotal: float = 1000.0,
    total: float = 1160.0,
    descuento: float = 0.0,
    conceptos: list | None = None,
    impuestos_globales: list | None = None,
) -> dict:
    return {
        "version": "4.0",
        "fecha": "2026-01-01T00:00:00",
        "uuid": "TEST-UUID",
        "emisor": "Emisor SA",
        "receptor": "Receptor SA",
        "subtotal": subtotal,
        "descuento": descuento,
        "total": total,
        "conceptos": conceptos or [],
        "impuestosGlobales": impuestos_globales or [],
    }


def _make_concept(
    descripcion: str = "Servicio",
    cantidad: float = 1.0,
    valor_unitario: float = 1000.0,
    importe: float = 1000.0,
    clave: str = "84111506",
    impuestos: list | None = None,
) -> dict:
    return {
        "descripcion": descripcion,
        "cantidad": cantidad,
        "valorUnitario": valor_unitario,
        "importe": importe,
        "claveProdServ": clave,
        "impuestos": impuestos or [],
    }


def _make_tax(
    tipo: str = "Traslado",
    impuesto: str = "002",
    tipo_factor: str = "Tasa",
    tasa: float = 0.16,
    base: float = 1000.0,
    importe: float = 160.0,
) -> dict:
    return {
        "tipo": tipo,
        "impuesto": impuesto,
        "tipoFactor": tipo_factor,
        "tasaOCuota": tasa,
        "base": base,
        "importe": importe,
    }


class TestMapTaxEntry(unittest.TestCase):
    def test_tasa_factor_computes_importe_calculado(self):
        tax = _make_tax(tipo_factor="Tasa", tasa=0.16, base=1000.0, importe=160.0)
        result = _map_tax_entry(tax)
        self.assertEqual(result["importeCalculado"], round(1000.0 * 0.16, 6))
        self.assertEqual(result["diferencia"], 0.0)
        self.assertEqual(result["tipo"], "Traslado")
        self.assertEqual(result["impuesto"], "002")

    def test_exento_factor_has_zero_importe_calculado(self):
        tax = _make_tax(tipo_factor="Exento", tasa=0.0, base=1000.0, importe=0.0)
        result = _map_tax_entry(tax)
        self.assertEqual(result["importeCalculado"], 0)
        self.assertEqual(result["diferencia"], 0.0)

    def test_tasa_mismatch_sets_diferencia(self):
        tax = _make_tax(tipo_factor="Tasa", tasa=0.16, base=1000.0, importe=170.0)
        result = _map_tax_entry(tax)
        self.assertGreater(result["diferencia"], 0)


class TestProcessConcepts(unittest.TestCase):
    def test_concept_with_tax_is_normalized(self):
        source = _make_cfdi(conceptos=[
            _make_concept(impuestos=[_make_tax()])
        ])
        result = _process_concepts(source)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["impuestos"]), 1)
        self.assertEqual(result[0]["importeCalculado"], round(1.0 * 1000.0, 6))

    def test_empty_conceptos_returns_empty_list(self):
        source = _make_cfdi(conceptos=[])
        self.assertEqual(_process_concepts(source), [])


class TestProcessGlobalTaxes(unittest.TestCase):
    def test_global_tax_is_mapped(self):
        source = _make_cfdi(impuestos_globales=[_make_tax()])
        result = _process_global_taxes(source)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["impuesto"], "002")


class TestCollectMathFindings(unittest.TestCase):
    def test_matching_subtotal_and_total_produce_no_findings(self):
        conceptos = [{"importe": 1000.0, "impuestos": []}]
        findings, hallazgos, impacted = _collect_math_findings(
            conceptos, subtotal=1000.0, subtotal_calculado=1000.0,
            total=1000.0, total_calculado=1000.0,
        )
        self.assertEqual(findings, [])
        self.assertEqual(hallazgos, [])
        self.assertEqual(impacted, [])

    def test_subtotal_mismatch_creates_critical_finding(self):
        conceptos = [{"importe": 1000.0, "impuestos": []}]
        findings, hallazgos, _ = _collect_math_findings(
            conceptos, subtotal=999.0, subtotal_calculado=1000.0,
            total=999.0, total_calculado=1000.0,
        )
        ids = [f["id"] for f in findings]
        self.assertIn("math-SUBTOTAL_MISMATCH-comprobante-na-na", ids)
        self.assertTrue(any("subtotal" in h.lower() for h in hallazgos))

    def test_total_mismatch_creates_critical_finding(self):
        conceptos = [{"importe": 1000.0, "impuestos": []}]
        findings, _, _ = _collect_math_findings(
            conceptos, subtotal=1000.0, subtotal_calculado=1000.0,
            total=999.0, total_calculado=1000.0,
        )
        ids = [f["id"] for f in findings]
        self.assertIn("math-TOTAL_MISMATCH-comprobante-na-na", ids)

    def test_tax_rate_mismatch_creates_line_tax_finding(self):
        impuesto = {
            "tipo": "Traslado",
            "impuesto": "002",
            "tipoFactor": "Tasa",
            "tasaOCuota": 0.16,
            "base": 1000.0,
            "importe": 200.0,  # wrong: should be 160
            "importeCalculado": 160.0,
            "diferencia": 40.0,
        }
        conceptos = [{"importe": 1000.0, "impuestos": [impuesto]}]
        findings, hallazgos, impacted = _collect_math_findings(
            conceptos, subtotal=1000.0, subtotal_calculado=1000.0,
            total=1000.0, total_calculado=1000.0,
        )
        self.assertTrue(any("LINE_TAX_MISMATCH" in f["id"] for f in findings))
        self.assertEqual(findings[0]["severity"], "critical")
        self.assertIn(0, impacted)
        self.assertTrue(any("Traslado inconsistente" in h for h in hallazgos))


class TestCollectConceptDiffs(unittest.TestCase):
    def test_no_diff_returns_empty(self):
        conceptos = [{"descripcion": "A", "importe": 100.0, "importeCalculado": 100.0, "diferencia": 0.0}]
        findings, impacted = _collect_concept_diffs(conceptos)
        self.assertEqual(findings, [])
        self.assertEqual(impacted, [])

    def test_small_diff_is_warning(self):
        conceptos = [{
            "descripcion": "A", "importe": 100.0,
            "importeCalculado": 100.005, "diferencia": 0.005,
        }]
        findings, impacted = _collect_concept_diffs(conceptos)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertIn(0, impacted)

    def test_large_diff_is_critical(self):
        conceptos = [{
            "descripcion": "A", "importe": 100.0,
            "importeCalculado": 110.0, "diferencia": 10.0,
        }]
        findings, _ = _collect_concept_diffs(conceptos)
        self.assertEqual(findings[0]["severity"], "critical")

    def test_max_concept_diffs_shown_is_respected(self):
        conceptos = [
            {"descripcion": f"C{i}", "importe": float(i), "importeCalculado": 0.0, "diferencia": float(i)}
            for i in range(1, 10)
        ]
        findings, _ = _collect_concept_diffs(conceptos)
        self.assertLessEqual(len(findings), 3)


class TestCollectTaxAuditGroupFindings(unittest.TestCase):
    def test_no_difference_returns_empty(self):
        groups = [{"diferencia": 0.0, "impuesto": "002", "tasaOCuota": 0.16, "key": "k", "conceptos": []}]
        findings, impacted = _collect_tax_audit_group_findings(groups)
        self.assertEqual(findings, [])

    def test_small_difference_is_warning(self):
        groups = [{
            "diferencia": 0.005, "impuesto": "002", "tasaOCuota": 0.16,
            "key": "002|Tasa|0.16", "importeDetalle": 160.0, "importeAgrupado": 160.005,
            "conceptos": [0],
        }]
        findings, impacted = _collect_tax_audit_group_findings(groups)
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertIn(0, impacted)

    def test_large_difference_is_critical(self):
        groups = [{
            "diferencia": 10.0, "impuesto": "002", "tasaOCuota": 0.16,
            "key": "002|Tasa|0.16", "importeDetalle": 150.0, "importeAgrupado": 160.0,
            "conceptos": [],
        }]
        findings, _ = _collect_tax_audit_group_findings(groups)
        self.assertEqual(findings[0]["severity"], "critical")


class TestCollectCatalogFindings(unittest.TestCase):
    def test_invalid_clave_creates_warning(self):
        source = _make_cfdi(conceptos=[{
            "claveProdServ": "99999999",
            "claveProdServDescripcion": "No existe en el catálogo",
        }])
        findings, _ = _collect_catalog_findings(source)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertIn("99999999", findings[0]["title"])

    def test_valid_clave_returns_empty(self):
        source = _make_cfdi(conceptos=[{
            "claveProdServ": "84111506",
            "claveProdServDescripcion": "Servicios de tecnología",
        }])
        findings, impacted = _collect_catalog_findings(source)
        self.assertEqual(findings, [])
        self.assertEqual(impacted, [])

    def test_invalid_clave_unidad_creates_warning(self):
        source = _make_cfdi(conceptos=[{
            "claveProdServ": "84111506",
            "claveUnidad": "ZZZZ",
            "claveUnidadDescripcion": "No existe en el catálogo",
        }])
        findings, _ = _collect_catalog_findings(source)
        ids = [f["id"] for f in findings]
        self.assertIn("catalog-clave-unidad-ZZZZ", ids)
        finding = next(f for f in findings if f["id"] == "catalog-clave-unidad-ZZZZ")
        self.assertEqual(finding["severity"], "warning")
        self.assertEqual(finding["declared"], "ZZZZ")

    def test_valid_clave_unidad_no_creates_finding(self):
        source = _make_cfdi(conceptos=[{
            "claveProdServ": "84111506",
            "claveUnidad": "ACT",
            "claveUnidadDescripcion": "Actividad",
        }])
        findings, _ = _collect_catalog_findings(source)
        unidad_findings = [f for f in findings if f["id"].startswith("catalog-clave-unidad-")]
        self.assertEqual(unidad_findings, [])

    def test_absent_clave_unidad_no_creates_finding(self):
        """Concepto sin claveUnidad → no debe generar finding."""
        source = _make_cfdi(conceptos=[{
            "claveProdServ": "84111506",
        }])
        findings, _ = _collect_catalog_findings(source)
        unidad_findings = [f for f in findings if f["id"].startswith("catalog-clave-unidad-")]
        self.assertEqual(unidad_findings, [])

    def test_two_concepts_same_invalid_clave_unidad_one_finding(self):
        source = _make_cfdi(conceptos=[
            {"claveProdServ": "84111506", "claveUnidad": "ZZZZ", "claveUnidadDescripcion": "No existe en el catálogo"},
            {"claveProdServ": "84111506", "claveUnidad": "ZZZZ", "claveUnidadDescripcion": "No existe en el catálogo"},
        ])
        findings, _ = _collect_catalog_findings(source)
        unidad_findings = [f for f in findings if f["id"].startswith("catalog-clave-unidad-")]
        self.assertEqual(len(unidad_findings), 1)
        self.assertIn("2 concepto(s)", unidad_findings[0]["summary"])

    def test_two_concepts_different_invalid_clave_unidad_two_findings(self):
        source = _make_cfdi(conceptos=[
            {"claveProdServ": "84111506", "claveUnidad": "AAAA", "claveUnidadDescripcion": "No existe en el catálogo"},
            {"claveProdServ": "84111506", "claveUnidad": "BBBB", "claveUnidadDescripcion": "No existe en el catálogo"},
        ])
        findings, _ = _collect_catalog_findings(source)
        unidad_findings = [f for f in findings if f["id"].startswith("catalog-clave-unidad-")]
        self.assertEqual(len(unidad_findings), 2)
        ids = {f["id"] for f in unidad_findings}
        self.assertIn("catalog-clave-unidad-AAAA", ids)
        self.assertIn("catalog-clave-unidad-BBBB", ids)

    def test_invalid_clave_prod_serv_populates_impacted(self):
        source = _make_cfdi(conceptos=[{
            "claveProdServ": "99999999",
            "claveProdServDescripcion": "No existe en el catálogo",
        }])
        _, impacted = _collect_catalog_findings(source)
        self.assertIn(0, impacted)

    def test_invalid_clave_unidad_populates_impacted(self):
        source = _make_cfdi(conceptos=[{
            "claveProdServ": "84111506",
            "claveUnidad": "ZZZZ",
            "claveUnidadDescripcion": "No existe en el catálogo",
        }])
        _, impacted = _collect_catalog_findings(source)
        self.assertIn(0, impacted)

    def test_valid_catalogs_no_impacted(self):
        source = _make_cfdi(conceptos=[{
            "claveProdServ": "84111506",
            "claveProdServDescripcion": "TI",
            "claveUnidad": "ACT",
            "claveUnidadDescripcion": "Actividad",
        }])
        _, impacted = _collect_catalog_findings(source)
        self.assertEqual(impacted, [])


class TestBuildVerdict(unittest.TestCase):
    def test_critical_findings_produce_critical_verdict(self):
        findings = [{"severity": "critical", "title": "X", "summary": "Y"}]
        verdict = _build_verdict(findings)
        self.assertEqual(verdict["status"], "critical")

    def test_warning_only_produces_review_verdict(self):
        findings = [{"severity": "warning", "title": "X", "summary": "Y"}]
        verdict = _build_verdict(findings)
        self.assertEqual(verdict["status"], "review")

    def test_no_findings_produces_clean_verdict(self):
        verdict = _build_verdict([])
        self.assertEqual(verdict["status"], "clean")


class TestNormalizeCfdiIntegration(unittest.TestCase):
    def test_none_source_returns_none(self):
        self.assertIsNone(_normalize_cfdi(None))

    def test_empty_source_returns_none(self):
        self.assertIsNone(_normalize_cfdi({}))

    def test_clean_cfdi_with_taxes_returns_clean_verdict(self):
        source = _make_cfdi(
            subtotal=1000.0,
            total=1160.0,
            conceptos=[_make_concept(impuestos=[_make_tax()])],
            impuestos_globales=[_make_tax()],
        )
        result = _normalize_cfdi(source)
        self.assertIsNotNone(result)
        self.assertEqual(result["verdict"]["status"], "clean")
        self.assertEqual(len(result["findings"]), 0)
        self.assertEqual(len(result["conceptos"]), 1)
        self.assertEqual(len(result["conceptos"][0]["impuestos"]), 1)
        self.assertEqual(len(result["impuestosGlobales"]), 1)

    def test_cfdi_with_wrong_total_returns_critical_verdict(self):
        source = _make_cfdi(subtotal=1000.0, total=999.0)
        result = _normalize_cfdi(source)
        self.assertIsNotNone(result)
        self.assertEqual(result["verdict"]["status"], "critical")
        self.assertTrue(any("TOTAL" in f["id"] for f in result["findings"]))

    def test_cfdi_fields_are_preserved_in_output(self):
        source = _make_cfdi()
        result = _normalize_cfdi(source)
        self.assertEqual(result["uuid"], "TEST-UUID")
        self.assertEqual(result["version"], "4.0")
        self.assertIn("supportText", result)
        self.assertIn("taxAuditGroups", result)


class TestCollectSelloFindings(unittest.TestCase):
    def _sv(self, status, checks=None, error=None):
        return {"selloVerificacion": {"status": status, "checks": checks or {}, "error": error}}

    def test_missing_sello_returns_empty(self):
        findings = _collect_sello_findings(self._sv("missing"))
        self.assertEqual(findings, [])

    def test_none_sello_verif_returns_empty(self):
        findings = _collect_sello_findings({})
        self.assertEqual(findings, [])

    def test_valid_all_checks_true_returns_empty(self):
        checks = {"certificadoSAT": True, "selloFirma": True, "numeroCertificado": True, "rfcEmisor": True}
        findings = _collect_sello_findings(self._sv("valid", checks))
        self.assertEqual(findings, [])

    def test_error_status_emits_warning_finding(self):
        findings = _collect_sello_findings(self._sv("error", error="algo salió mal"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "firma-error-verificacion")
        self.assertEqual(findings[0]["severity"], "warning")
        self.assertIn("algo salió mal", findings[0]["summary"])

    def test_sello_firma_false_emits_critical(self):
        checks = {"certificadoSAT": True, "selloFirma": False, "numeroCertificado": True, "rfcEmisor": True}
        findings = _collect_sello_findings(self._sv("invalid", checks))
        ids = [f["id"] for f in findings]
        self.assertIn("firma-sello-invalido", ids)
        finding = next(f for f in findings if f["id"] == "firma-sello-invalido")
        self.assertEqual(finding["severity"], "critical")

    def test_certificado_sat_false_sello_valido_emits_warning(self):
        """Cert no en trust store pero firma válida → probablemente UAT → warning, no critical."""
        checks = {"certificadoSAT": False, "selloFirma": True, "numeroCertificado": True, "rfcEmisor": True}
        findings = _collect_sello_findings(self._sv("invalid", checks))
        ids = [f["id"] for f in findings]
        self.assertIn("firma-certificado-invalido", ids)
        finding = next(f for f in findings if f["id"] == "firma-certificado-invalido")
        self.assertEqual(finding["severity"], "warning")

    def test_certificado_sat_false_sello_invalido_emits_critical(self):
        """Cert no en trust store Y firma inválida → critical."""
        checks = {"certificadoSAT": False, "selloFirma": False, "numeroCertificado": True, "rfcEmisor": True}
        findings = _collect_sello_findings(self._sv("invalid", checks))
        cert_finding = next(f for f in findings if f["id"] == "firma-certificado-invalido")
        self.assertEqual(cert_finding["severity"], "critical")

    def test_numero_certificado_false_emits_warning(self):
        checks = {"certificadoSAT": True, "selloFirma": True, "numeroCertificado": False, "rfcEmisor": True}
        findings = _collect_sello_findings(self._sv("invalid", checks))
        ids = [f["id"] for f in findings]
        self.assertIn("firma-numero-certificado-invalido", ids)
        finding = next(f for f in findings if f["id"] == "firma-numero-certificado-invalido")
        self.assertEqual(finding["severity"], "warning")

    def test_rfc_emisor_false_emits_warning(self):
        checks = {"certificadoSAT": True, "selloFirma": True, "numeroCertificado": True, "rfcEmisor": False}
        findings = _collect_sello_findings(self._sv("invalid", checks))
        ids = [f["id"] for f in findings]
        self.assertIn("firma-rfc-emisor-invalido", ids)

    def test_multiple_checks_false_emits_multiple_findings(self):
        checks = {"certificadoSAT": False, "selloFirma": False, "numeroCertificado": True, "rfcEmisor": True}
        findings = _collect_sello_findings(self._sv("invalid", checks))
        ids = {f["id"] for f in findings}
        self.assertIn("firma-sello-invalido", ids)
        self.assertIn("firma-certificado-invalido", ids)
        self.assertEqual(len(findings), 2)


if __name__ == "__main__":
    unittest.main()
