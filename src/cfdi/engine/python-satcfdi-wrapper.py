#!/usr/bin/env python3
import json
import sys
import traceback
import xml.etree.ElementTree as ET
from decimal import Decimal
from datetime import date, datetime


def detect_profile(root):
    complemento = find_child_by_local_name(root, "Complemento")
    if complemento is not None:
        for child in list(complemento):
            local_name = child.tag.split("}", 1)[-1].lower()
            if "pagos" in local_name:
                return "pagos"

    tipo = root.attrib.get("TipoDeComprobante")
    if tipo == "I":
        return "ingreso"

    conceptos = find_child_by_local_name(root, "Conceptos")
    if conceptos is not None and len(list(conceptos)) > 0:
        return "ingreso"

    return "unknown"


def find_child_by_local_name(node, local_name):
    for child in list(node):
        if child.tag.split("}", 1)[-1] == local_name:
            return child
    return None


def code_or_raw(value):
    if value is None:
        return ""
    if hasattr(value, "code"):
        return value.code
    return str(value)


def decimal_to_number(value):
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def decimal_to_string(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def scalar_to_json(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "code"):
        return value.code
    return value


def extract_uuid(complemento):
    if not complemento:
        return ""
    timbre = complemento.get("TimbreFiscalDigital")
    if not timbre:
        return ""
    return timbre.get("UUID", "")


def normalize_tax_lines(container, tax_type):
    if not container:
        return []

    lines = []
    for values in container.values():
        lines.append({
            "tipo": tax_type,
            "impuesto": code_or_raw(values.get("Impuesto")),
            "base": decimal_to_number(values.get("Base")),
            "tipoFactor": code_or_raw(values.get("TipoFactor")),
            "tasaOCuota": decimal_to_number(values.get("TasaOCuota")) if values.get("TasaOCuota") is not None else 0,
            "importe": decimal_to_number(values.get("Importe")) if values.get("Importe") is not None else 0,
        })
    return lines


def normalize_concept(concepto):
    impuestos = concepto.get("Impuestos", {})
    cprod = concepto.get("ClaveProdServ")
    return {
        "descripcion": concepto.get("Descripcion", ""),
        "cantidad": decimal_to_number(concepto.get("Cantidad")),
        "valorUnitario": decimal_to_number(concepto.get("ValorUnitario")),
        "importe": decimal_to_number(concepto.get("Importe")),
        "claveProdServ": code_or_raw(cprod),
        "claveProdServDescripcion": (getattr(cprod, "description", None) or "No existe en el catálogo") if cprod else None,
        "impuestos": (
            normalize_tax_lines(impuestos.get("Traslados"), "Traslado")
            + normalize_tax_lines(impuestos.get("Retenciones"), "Retencion")
        ),
        "objetoImp": code_or_raw(concepto.get("ObjetoImp")),
    }


def catalog_desc_or_sentinel(field_value):
    """Returns description string if valid, sentinel if code unknown, None if field absent."""
    if field_value is None:
        return None
    desc = getattr(field_value, "description", None)
    return desc if desc is not None else "No existe en el catálogo"


def build_cfdi_payload(cfdi):
    complemento = cfdi.get("Complemento", {})
    conceptos = [normalize_concept(concepto) for concepto in cfdi.get("Conceptos", [])]
    impuestos_globales = []
    if cfdi.get("Impuestos"):
        impuestos_globales.extend(normalize_tax_lines(cfdi["Impuestos"].get("Traslados"), "Traslado"))
        impuestos_globales.extend(normalize_tax_lines(cfdi["Impuestos"].get("Retenciones"), "Retencion"))

    receptor = cfdi.get("Receptor", {})
    uso_cfdi = receptor.get("UsoCFDI")
    mp = cfdi.get("MetodoPago")
    fp = cfdi.get("FormaPago")
    mon = cfdi.get("Moneda")

    return {
        "version": cfdi.get("Version", ""),
        "fecha": scalar_to_json(cfdi.get("Fecha")) or "",
        "uuid": extract_uuid(complemento),
        "emisor": cfdi.get("Emisor", {}).get("Nombre") or cfdi.get("Emisor", {}).get("Rfc", ""),
        "receptor": receptor.get("Nombre") or receptor.get("Rfc", ""),
        "subtotal": decimal_to_number(cfdi.get("SubTotal")),
        "descuento": decimal_to_number(cfdi.get("Descuento")) if cfdi.get("Descuento") is not None else 0,
        "total": decimal_to_number(cfdi.get("Total")),
        "conceptos": conceptos,
        "impuestosGlobales": impuestos_globales,
        "usoCfdi": code_or_raw(uso_cfdi),
        "usoCfdiDescripcion": catalog_desc_or_sentinel(uso_cfdi),
        "metodoPago": code_or_raw(mp),
        "metodoPagoDescripcion": catalog_desc_or_sentinel(mp),
        "formaPago": code_or_raw(fp),
        "formaPagoDescripcion": catalog_desc_or_sentinel(fp),
        "moneda": code_or_raw(mon),
        "monedaDescripcion": catalog_desc_or_sentinel(mon),
    }


def build_ingreso_row_header(cfdi):
    uuid = extract_uuid(cfdi.get("Complemento", {}))
    emisor = cfdi.get("Emisor", {})
    receptor = cfdi.get("Receptor", {})
    return {
        "uuid": uuid,
        "fecha": scalar_to_json(cfdi.get("Fecha")) or "",
        "serie": cfdi.get("Serie", "") or "",
        "folio": cfdi.get("Folio", "") or "",
        "rfcEmisor": emisor.get("Rfc", ""),
        "nombreEmisor": emisor.get("Nombre", ""),
        "rfcReceptor": receptor.get("Rfc", ""),
        "nombreReceptor": receptor.get("Nombre", ""),
        "usoCfdi": code_or_raw(receptor.get("UsoCFDI")),
        "metodoPago": code_or_raw(cfdi.get("MetodoPago")),
        "formaPago": code_or_raw(cfdi.get("FormaPago")),
        "moneda": code_or_raw(cfdi.get("Moneda")),
        "tipoCambio": decimal_to_string(cfdi.get("TipoCambio")),
        "subtotal": decimal_to_string(cfdi.get("SubTotal")),
        "descuento": decimal_to_string(cfdi.get("Descuento")),
        "total": decimal_to_string(cfdi.get("Total")),
    }


def build_ingreso_rows(cfdi):
    rows = []

    for concepto in cfdi.get("Conceptos", []):
        concept_base = {
            "claveProdServ": code_or_raw(concepto.get("ClaveProdServ")),
            "cantidad": decimal_to_string(concepto.get("Cantidad")),
            "descripcion": concepto.get("Descripcion", ""),
            "valorUnitario": decimal_to_string(concepto.get("ValorUnitario")),
            "importe": decimal_to_string(concepto.get("Importe")),
            "objetoImp": code_or_raw(concepto.get("ObjetoImp")),
        }
        impuestos = concepto.get("Impuestos", {})
        traslados = list((impuestos.get("Traslados") or {}).values())
        retenciones = list((impuestos.get("Retenciones") or {}).values())

        if not traslados and not retenciones:
            rows.append({
                **concept_base,
                "tipoImp": "",
                "baseImp": "",
                "impuesto": "",
                "tipoFactor": "",
                "tasaCuota": "",
                "importeImp": "",
            })
            continue

        for tax in traslados:
            rows.append({
                **concept_base,
                "tipoImp": "Traslado",
                "baseImp": decimal_to_string(tax.get("Base")),
                "impuesto": code_or_raw(tax.get("Impuesto")),
                "tipoFactor": code_or_raw(tax.get("TipoFactor")),
                "tasaCuota": decimal_to_string(tax.get("TasaOCuota")),
                "importeImp": decimal_to_string(tax.get("Importe")),
            })

        for tax in retenciones:
            rows.append({
                **concept_base,
                "tipoImp": "Retención",
                "baseImp": decimal_to_string(tax.get("Base")),
                "impuesto": code_or_raw(tax.get("Impuesto")),
                "tipoFactor": code_or_raw(tax.get("TipoFactor")),
                "tasaCuota": decimal_to_string(tax.get("TasaOCuota")),
                "importeImp": decimal_to_string(tax.get("Importe")),
            })

    return rows


def build_pago_rows(cfdi):
    complemento = cfdi.get("Complemento", {})
    pagos = complemento.get("Pagos", {})
    pago_items = pagos.get("Pago", [])
    if isinstance(pago_items, dict):
        pago_items = [pago_items]

    uuid = extract_uuid(complemento)
    emisor = cfdi.get("Emisor", {})
    receptor = cfdi.get("Receptor", {})
    rows = []

    for pago in pago_items:
        doctos = pago.get("DoctoRelacionado", [])
        if isinstance(doctos, dict):
            doctos = [doctos]

        base_row = {
            "uuidCFDI": uuid,
            "fechaCFDI": scalar_to_json(cfdi.get("Fecha")) or "",
            "rfcEmisor": emisor.get("Rfc", ""),
            "rfcReceptor": receptor.get("Rfc", ""),
            "fechaPago": scalar_to_json(pago.get("FechaPago")) or "",
            "formaPago": code_or_raw(pago.get("FormaDePagoP")),
            "monedaP": code_or_raw(pago.get("MonedaP")),
            "monto": decimal_to_string(pago.get("Monto")),
        }

        if not doctos:
            rows.append({
                **base_row,
                "uuidDR": "",
                "serieFolio": "",
                "parcialidad": "",
                "impPagado": "",
                "saldoInsoluto": "",
                "baseDR": "",
                "impuestoDR": "",
                "tipoFactorDR": "",
                "tasaCuotaDR": "",
                "importeDR": "",
            })
            continue

        for docto in doctos:
            impuestos_dr = docto.get("ImpuestosDR", {})
            traslados_dr = list((impuestos_dr.get("TrasladosDR") or {}).values())
            retenciones_dr = list((impuestos_dr.get("RetencionesDR") or {}).values())
            serial = {
                **base_row,
                "uuidDR": docto.get("IdDocumento", ""),
                "serieFolio": "-".join([part for part in [docto.get("Serie", ""), docto.get("Folio", "")] if part]) or "N/A",
                "parcialidad": str(docto.get("NumParcialidad", "")),
                "impPagado": decimal_to_string(docto.get("ImpPagado")),
                "saldoInsoluto": decimal_to_string(docto.get("ImpSaldoInsoluto")),
            }

            if not traslados_dr and not retenciones_dr:
                rows.append({
                    **serial,
                    "baseDR": "",
                    "impuestoDR": "",
                    "tipoFactorDR": "",
                    "tasaCuotaDR": "",
                    "importeDR": "",
                })
                continue

            for tax in traslados_dr + retenciones_dr:
                rows.append({
                    **serial,
                    "baseDR": decimal_to_string(tax.get("BaseDR")),
                    "impuestoDR": code_or_raw(tax.get("ImpuestoDR")),
                    "tipoFactorDR": code_or_raw(tax.get("TipoFactorDR")),
                    "tasaCuotaDR": decimal_to_string(tax.get("TasaOCuotaDR")),
                    "importeDR": decimal_to_string(tax.get("ImporteDR")),
                })

    return rows


def detect_profile_from_cfdi(cfdi):
    complemento = cfdi.get("Complemento", {}) or {}
    if complemento.get("Pagos"):
        return "pagos"
    tipo = cfdi.get("TipoDeComprobante")
    tipo_code = tipo.code if hasattr(tipo, "code") else str(tipo or "")
    if tipo_code == "I":
        return "ingreso"
    if cfdi.get("Conceptos"):
        return "ingreso"
    return "unknown"


def parse_payload(xml):
    try:
        from satcfdi.cfdi import CFDI
        satcfdi_available = True
    except ModuleNotFoundError:
        satcfdi_available = False

    if not satcfdi_available:
        root = ET.fromstring(xml)
        local_name = root.tag.split("}", 1)[-1]
        if local_name != "Comprobante":
            raise ValueError("No se encontró el nodo Comprobante")
        return {
            "ok": False,
            "profile": detect_profile(root),
            "satcfdiAvailable": False,
            "unsupportedCapabilities": [
                "python-satcfdi no está instalado en este entorno"
            ],
        }

    # Un solo parse: cualquier fallo de CFDI.from_string es un error de parseo
    try:
        cfdi = CFDI.from_string(xml.encode())
    except ET.ParseError:
        raise  # capturado en main() como errorType: "parse"
    except Exception as e:
        raise ValueError(f"No se pudo parsear el CFDI: {e}") from e
    profile = detect_profile_from_cfdi(cfdi)
    cfdi_payload = build_cfdi_payload(cfdi)

    return {
        "ok": True,
        "profile": profile,
        "satcfdiAvailable": True,
        "cfdi": cfdi_payload,
        "ingresoRows": build_ingreso_rows(cfdi) if profile == "ingreso" else [],
        "ingresoRowHeader": build_ingreso_row_header(cfdi) if profile == "ingreso" else {},
        "pagoRows": build_pago_rows(cfdi) if profile == "pagos" else [],
        "unsupportedCapabilities": [],
        "findingsImplemented": True,
    }


def main():
    xml = sys.stdin.read()
    try:
        payload = parse_payload(xml)
        sys.stdout.write(json.dumps(payload))
    except ET.ParseError as error:
        sys.stdout.write(json.dumps({
            "ok": False,
            "profile": "unknown",
            "errorType": "parse",
            "errorMessage": f"XML inválido: {error}",
        }))
    except ValueError as error:
        sys.stdout.write(json.dumps({
            "ok": False,
            "profile": "unknown",
            "errorType": "parse",
            "errorMessage": str(error),
        }))
    except Exception as error:  # pragma: no cover - runtime bridge
        sys.stdout.write(json.dumps({
            "ok": False,
            "profile": "unknown",
            "errorType": "runtime",
            "errorMessage": str(error),
            "traceback": traceback.format_exc(),
        }))


if __name__ == "__main__":
    main()
