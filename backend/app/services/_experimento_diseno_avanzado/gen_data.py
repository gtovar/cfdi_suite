"""
gen_data.py — Genera XML CFDI 4.0 sintéticos para el experimento de diseño avanzado.

Reusa el dataset emisor/receptor de prototype/experimento-cfdi.typ
(TECNOLOGÍA DIGITAL NORTE / INDUSTRIAS GOLONDRINA) para comparación justa con el lado A.

Produce combinaciones de dos bloques condicionales:
  - descuento: con (>0) / sin (=0)
  - moneda:    USD (TipoCambio != 1) / MXN

Los ClaveUnidad incluyen E48 ("Unidad de servicio"), ACT ("Actividad") y HUR ("Hora"),
que decodifican a descripciones largas — dispara el bug de traslape de la columna Unidad
que existe en canvas_service.py (columna de 36pt sin recorte).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def _m(v) -> str:
    return str(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


# Emisor / Receptor — idénticos al prototipo Typst de App A
EMISOR = dict(
    rfc="TDN210615AB3",
    nombre="TECNOLOGÍA DIGITAL NORTE S.A. DE C.V.",
    regimen="601",
)
RECEPTOR = dict(
    rfc="GOLI780901H47",
    nombre="INDUSTRIAS GOLONDRINA INNOVACIÓN S.A. DE C.V.",
    uso="G03",
    regimen="601",
    domicilio="06600",
)

# (clave_prod, no_ident, cantidad, clave_unidad, descripcion, valor_unitario)
# Descripciones deliberadamente >40 chars y ClaveUnidad que decodifican largo.
CONCEPTOS_BASE = [
    ("81112101", "SW-DEV-001", 1, "E48", "Desarrollo de Software a la Medida — Sistema ERP módulo de inventario y logística", 45000.00),
    ("81112104", "CONS-2026-40H", 40, "HUR", "Consultoría en Arquitectura de Nube AWS — diseño e implementación multi-región", 1800.00),
    ("81161500", "LIC-ENT-2026", 1, "E48", "Licencia de Plataforma SaaS Plan Enterprise Anual — usuarios ilimitados soporte 24/7", 18500.00),
    ("43232408", "INT-API-12", 12, "ACT", "Integración de API REST con sistemas de terceros — pasarela de pagos y facturación", 3200.00),
    ("81112500", "MANT-MENS", 6, "MON", "Mantenimiento evolutivo y correctivo mensual de aplicación empresarial", 8500.00),
    ("81111500", "AUD-SEG-01", 1, "E48", "Auditoría de Seguridad Informática y pruebas de penetración OWASP Top 10", 32000.00),
    ("81112200", "TRAIN-3D", 3, "E48", "Capacitación técnica presencial en DevOps y CI/CD — grupo de 15 personas", 12000.00),
    ("43231500", "DB-MIGR-01", 1, "ACT", "Migración de base de datos legada a PostgreSQL con cero downtime", 27500.00),
    ("81112000", "UX-RESEARCH", 80, "HUR", "Investigación UX y diseño de interfaz — entrevistas y prototipado de alta fidelidad", 950.00),
    ("81161700", "BI-DASH-01", 1, "E48", "Implementación de tablero de Business Intelligence con datos en tiempo real", 41000.00),
    ("43233200", "MOBILE-APP", 1, "ACT", "Desarrollo de aplicación móvil híbrida iOS y Android con backend serverless", 68000.00),
    ("81112501", "SLA-PREM", 12, "MON", "Contrato de soporte premium SLA 99.9% con atención prioritaria 24/7", 15000.00),
    ("81111800", "NET-INFRA", 1, "E48", "Diseño de infraestructura de red y configuración de firewall perimetral", 22000.00),
    ("81112300", "DATA-PIPE", 200, "HUR", "Ingeniería de datos — construcción de pipeline ETL y data warehouse en la nube", 1100.00),
    ("43232300", "SEC-TRAIN", 5, "ACT", "Concientización en ciberseguridad para personal administrativo y operativo", 4500.00),
]


def _conceptos(n: int, con_descuento: bool) -> list[dict]:
    out = []
    for i in range(n):
        cp, ni, cant, cu, desc, vu = CONCEPTOS_BASE[i % len(CONCEPTOS_BASE)]
        if n > len(CONCEPTOS_BASE):
            desc = f"{desc} (lote {i // len(CONCEPTOS_BASE) + 1})"
            ni = f"{ni}-{i:04d}"
        importe = Decimal(str(cant)) * Decimal(str(vu))
        descuento = (importe * Decimal("0.10")) if con_descuento and (i % 3 == 0) else Decimal("0")
        out.append(dict(
            clave_prod=cp, no_ident=ni, cantidad=str(cant), clave_unidad=cu,
            descripcion=desc, valor_unitario=Decimal(str(vu)),
            importe=importe, descuento=descuento,
        ))
    return out


def build_xml(n: int = 15, con_descuento: bool = False, moneda: str = "MXN") -> str:
    cs = _conceptos(n, con_descuento)
    subtotal = sum(c["importe"] for c in cs)
    descuento = sum(c["descuento"] for c in cs)
    base = subtotal - descuento
    iva = (base * Decimal("0.16")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = base + iva
    tipo_cambio = "17.1500" if moneda == "USD" else "1"

    concepto_lines = []
    for c in cs:
        desc_attr = f' Descuento="{_m(c["descuento"])}"' if c["descuento"] > 0 else ""
        concepto_lines.append(
            "      <cfdi:Concepto "
            f'ClaveProdServ="{c["clave_prod"]}" '
            f'NoIdentificacion="{_esc(c["no_ident"])}" '
            f'Cantidad="{c["cantidad"]}" '
            f'ClaveUnidad="{c["clave_unidad"]}" '
            f'Descripcion="{_esc(c["descripcion"])}" '
            f'ValorUnitario="{_m(c["valor_unitario"])}" '
            f'Importe="{_m(c["importe"])}"{desc_attr} '
            'ObjetoImp="02"/>'
        )
    conceptos_xml = "\n".join(concepto_lines)

    desc_attr_comp = f' Descuento="{_m(descuento)}"' if descuento > 0 else ""
    tc_attr = f' TipoCambio="{tipo_cambio}"' if moneda != "MXN" else ""

    return f'''<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
    Version="4.0" Fecha="2026-06-29T10:30:00"
    Serie="A" Folio="003142"
    Moneda="{moneda}"{tc_attr} SubTotal="{_m(subtotal)}"{desc_attr_comp} Total="{_m(total)}"
    TipoDeComprobante="I" LugarExpedicion="64650"
    FormaPago="03" MetodoPago="PUE"
    Sello="oTNl3m7YK2Pq8vXzWa0dRhJfCs4Bn9Ew6GiUyLpMkFgHjTlZrVbQxDnWo1Im">
  <cfdi:Emisor Nombre="{_esc(EMISOR["nombre"])}" Rfc="{EMISOR["rfc"]}" RegimenFiscal="{EMISOR["regimen"]}"/>
  <cfdi:Receptor Nombre="{_esc(RECEPTOR["nombre"])}" Rfc="{RECEPTOR["rfc"]}" UsoCFDI="{RECEPTOR["uso"]}" DomicilioFiscalReceptor="{RECEPTOR["domicilio"]}" RegimenFiscalReceptor="{RECEPTOR["regimen"]}"/>
  <cfdi:Conceptos>
{conceptos_xml}
  </cfdi:Conceptos>
  <cfdi:Impuestos TotalImpuestosTrasladados="{_m(iva)}">
    <cfdi:Traslados>
      <cfdi:Traslado Base="{_m(base)}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{_m(iva)}"/>
    </cfdi:Traslados>
  </cfdi:Impuestos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
      UUID="A1B2C3D4-E5F6-7890-ABCD-EF1234567890" FechaTimbrado="2026-06-29T10:30:48"
      NoCertificadoSAT="20001000000300023708" RfcProvCertif="SAT970701NN3"
      SelloSAT="AHl5nWo1ImK5Ap7Ce3Lt8YuRvSqXzPj2BhFdGwO8NkM4TsZrVbQiUyLpCm6Et9FxBkJrTqNgHlDwAoS"/>
  </cfdi:Complemento>
</cfdi:Comprobante>
'''


VARIANTS = [
    ("mxn_sin_descuento", dict(n=15, con_descuento=False, moneda="MXN")),
    ("mxn_con_descuento", dict(n=15, con_descuento=True, moneda="MXN")),
    ("usd_sin_descuento", dict(n=15, con_descuento=False, moneda="USD")),
    ("usd_con_descuento", dict(n=15, con_descuento=True, moneda="USD")),
    ("usd_con_descuento_N100", dict(n=100, con_descuento=True, moneda="USD")),
]
