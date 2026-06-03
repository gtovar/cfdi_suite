import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal
from io import BytesIO

from satcfdi.diot import DIOT, DatosIdentificacion, ProveedorTercero, TipoOperacion, TipoTercero
from satcfdi.diot.code import Periodo

_PERIODOS = list(Periodo)  # índice 0 = ENERO, ..., 11 = DICIEMBRE

_RFC_GLOBAL = "XAXX010101000"
_RFC_EXTRANJERO = "XEXX010101000"

# IVA tasa thresholds
_TASA_RFN_LOW = Decimal("0.07")   # Región Fronteriza Norte: tasa == 0.08
_TASA_RFN_HIGH = Decimal("0.15")  # 16% standard: tasa >= 0.16


def _extract_iva_from_xml(xml_bytes: bytes) -> dict:
    """Parse a CFDI XML and return RFC emisor/receptor plus IVA amounts."""
    result = {
        "rfc_emisor": "",
        "rfc_receptor": "",
        "iva16": Decimal(0),
        "iva0": Decimal(0),
        "iva_rfn": Decimal(0),   # IVA Región Fronteriza Norte (tasa 8%)
        "retenido": Decimal(0),
    }

    try:
        root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))
    except Exception:
        return result

    for node in root.iter():
        tag = node.tag.split("}", 1)[-1]
        if tag == "Emisor":
            result["rfc_emisor"] = node.attrib.get("Rfc", "").strip()
        elif tag == "Receptor":
            result["rfc_receptor"] = node.attrib.get("Rfc", "").strip()
        elif tag == "Traslado":
            if node.attrib.get("Impuesto") != "002":
                continue
            try:
                tasa = Decimal(node.attrib.get("TasaOCuota", "0"))
                base = Decimal(node.attrib.get("Base", "0"))
            except Exception:
                continue
            if tasa >= _TASA_RFN_HIGH:
                result["iva16"] += base
            elif tasa == Decimal(0):
                result["iva0"] += base
            elif _TASA_RFN_LOW < tasa < _TASA_RFN_HIGH:
                # Región Fronteriza Norte (Decreto 2019): tasa = 0.08
                result["iva_rfn"] += base
        elif tag == "Retencion":
            if node.attrib.get("Impuesto") != "002":
                continue
            try:
                result["retenido"] += Decimal(node.attrib.get("Importe", "0"))
            except Exception:
                pass

    return result


def generate_diot(
    xml_list: list[bytes],
    year: int,
    month: int,
    rfc_presentante: str | None = None,
    razon_social: str | None = None,
) -> bytes:
    """
    Generate a DIOT pipe-delimited .txt from a list of CFDI XMLs.

    Returns the bytes of the file encoded in windows-1252.
    rfc_presentante is auto-detected from the RFC receptor of the first XML if not provided.
    """
    extractions = [_extract_iva_from_xml(xml) for xml in xml_list]

    # Auto-detect RFC presentante from first XML that has a receptor
    if not rfc_presentante:
        for e in extractions:
            if e["rfc_receptor"]:
                rfc_presentante = e["rfc_receptor"]
                break

    if not rfc_presentante:
        raise ValueError(
            "No se pudo detectar el RFC del presentante. "
            "Asegúrate de que los XMLs tengan el campo Receptor.Rfc o proporciona el RFC manualmente."
        )

    rfc_presentante = rfc_presentante.strip().upper()

    # Aggregate IVA amounts by RFC emisor
    by_rfc: dict[str, dict] = defaultdict(lambda: {
        "iva16": Decimal(0),
        "iva0": Decimal(0),
        "iva_rfn": Decimal(0),
        "retenido": Decimal(0),
    })

    for e in extractions:
        rfc = e["rfc_emisor"].strip().upper()
        if rfc:
            by_rfc[rfc]["iva16"] += e["iva16"]
            by_rfc[rfc]["iva0"] += e["iva0"]
            by_rfc[rfc]["iva_rfn"] += e["iva_rfn"]
            by_rfc[rfc]["retenido"] += e["retenido"]

    # Build ProveedorTercero list
    proveedores = []
    for rfc, totals in by_rfc.items():
        if rfc == _RFC_GLOBAL:
            tipo_tercero = TipoTercero.PROVEEDOR_GLOBAL
            rfc_arg = None
        elif rfc == _RFC_EXTRANJERO:
            tipo_tercero = TipoTercero.PROVEEDOR_EXTRANJERO
            rfc_arg = None
        else:
            tipo_tercero = TipoTercero.PROVEEDOR_NACIONAL
            rfc_arg = rfc

        iva16 = int(round(totals["iva16"])) if totals["iva16"] else None
        iva0 = int(round(totals["iva0"])) if totals["iva0"] else None
        iva_rfn = int(round(totals["iva_rfn"])) if totals["iva_rfn"] else None
        retenido = int(round(totals["retenido"])) if totals["retenido"] else None

        # Skip proveedores with no IVA amounts at all
        if iva16 is None and iva0 is None and iva_rfn is None and retenido is None:
            continue

        proveedores.append(ProveedorTercero(
            tipo_tercero=tipo_tercero,
            tipo_operacion=TipoOperacion.OTROS,
            rfc=rfc_arg,
            iva16=iva16,
            iva0=iva0,
            iva_rfn=iva_rfn,
            retenido=retenido,
        ))

    datos_ident = DatosIdentificacion(
        rfc=rfc_presentante,
        ejercicio=year,
        razon_social=(razon_social or rfc_presentante).upper(),
    )

    periodo = _PERIODOS[month - 1]
    diot = DIOT(datos_identificacion=datos_ident, periodo=periodo, proveedores=proveedores)

    buf = BytesIO()
    diot.export(buf)
    return buf.getvalue()
