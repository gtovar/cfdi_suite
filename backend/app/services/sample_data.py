"""
sample_data.py — Generador de datos de factura sintéticos (Fase 1).

Produce EXACTAMENTE el mismo shape que parse_xml_to_rows() variante ingreso
(_parse_ingreso_sax en canvas_service.py), para poder ejercitar el motor real
(generate_from_data) con datos de ejemplo sin subir un XML de CFDI real.

Determinístico: sin randomness. Mismas entradas → misma salida.
`_sello_8` es interno de parse_xml_to_rows y ya se remueve por pop() antes de
llegar al render; aquí NO se incluye, se produce `verifica_url` directamente.
"""
from __future__ import annotations

from .canvas_service import _VERIFICA_URL, _fmt_mxn

# Descripciones y unidades ficticias deterministas (ciclan por índice de fila).
_DESCRIPCIONES = [
    "Servicio de consultoría en tecnología de la información",
    "Licencia anual de software empresarial (5 usuarios)",
    "Mantenimiento preventivo de equipo de cómputo",
    "Papelería y artículos de oficina surtidos",
    "Capacitación en línea — módulo de facturación",
    "Soporte técnico remoto, bolsa de 10 horas",
]
_UNIDADES = ["Pieza", "Servicio", "Actividad", "Servicio", "Pieza", "Hora"]
_CLAVES_UNIDAD = ["H87", "E48", "ACT", "E48", "H87", "HUR"]


def generar_datos_ejemplo(
    n_rows: int = 6,
    con_descuento: bool = True,
) -> tuple[dict, list[dict]]:
    """
    Devuelve (cfdi_data, rows) con el shape exacto de parse_xml_to_rows ingreso.

    - `n_rows`: cantidad de conceptos a generar.
    - `con_descuento`: si True, filas en índice impar llevan descuento > 0 y las
      pares descuento = 0 (garantiza al menos una de cada, para ver disparar la
      regla condicional). Si False, todas las filas llevan descuento = 0.

    Montos formateados a 2 decimales con la misma función que el pipeline real
    (_fmt_mxn), de modo que las comparaciones de reglas se comporten idéntico.
    """
    n_rows = max(1, int(n_rows))

    rows: list[dict] = []
    subtotal_acc = 0.0
    descuento_acc = 0.0

    for i in range(n_rows):
        cantidad = i + 1
        # Precio unitario determinístico, con variedad de magnitudes.
        valor_unitario = 125.0 + i * 375.5
        base = cantidad * valor_unitario
        if con_descuento and i % 2 == 1:
            descuento = round(base * 0.10, 2)  # 10% de descuento en filas impares
        else:
            descuento = 0.0
        importe = base - descuento

        subtotal_acc += base
        descuento_acc += descuento

        rows.append({
            "num_id":         f"PROD-{1000 + i}",
            "cantidad":       str(cantidad),
            "clave_unidad":   _UNIDADES[i % len(_UNIDADES)],
            "descripcion":    _DESCRIPCIONES[i % len(_DESCRIPCIONES)],
            "valor_unitario": _fmt_mxn(valor_unitario),
            "descuento":      _fmt_mxn(descuento),
            "importe":        _fmt_mxn(importe),
        })

    subtotal = subtotal_acc
    descuento_total = descuento_acc
    base_gravable = subtotal - descuento_total
    iva = round(base_gravable * 0.16, 2)
    total = base_gravable + iva

    cfdi_data: dict = {
        "fecha":            "2026-07-04T12:00:00",
        "serie":            "F",
        "folio":            "1024",
        "moneda":           "MXN",
        "forma_pago":       "03",
        "metodo_pago":      "PUE",
        "lugar_expedicion": "64000",
        "tipo_cambio":      "",
        "totales": {
            "subtotal":  _fmt_mxn(subtotal),
            "descuento": _fmt_mxn(descuento_total),
            "total":     _fmt_mxn(total),
        },
        "emisor": {
            "nombre":       "EMPRESA DEMOSTRATIVA SA DE CV",
            "rfc":          "EDE010101AAA",
            "regimen":      "601",
            "regimen_desc": "601 — General de Ley Personas Morales",
        },
        "receptor": {
            "nombre":                    "CLIENTE EJEMPLO SA DE CV",
            "rfc":                       "CEJ020202BBB",
            "uso":                       "G03",
            "uso_desc":                  "G03 — Gastos en general",
            "domicilio_fiscal_receptor": "64010",
            "regimen_fiscal_receptor":   "601",
            "regimen_receptor_desc":     "601 — General de Ley Personas Morales",
        },
        "timbre": {
            "uuid":            "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
            "fecha_timbrado":  "2026-07-04T12:00:05",
            "no_cert_sat":     "00001000000504465028",
            "rfc_prov_certif": "SAT970701NN3",
            "sello_sat":       "GENERADO_PARA_PREVIEW_DE_DISENO_NO_ES_UN_SELLO_REAL",
        },
        "moneda_desc":      "MXN — Peso Mexicano",
        "forma_pago_desc":  "03 — Transferencia electrónica de fondos",
        "metodo_pago_desc": "PUE — Pago en una sola exhibición",
        "impuestos": [
            {"nombre": "IVA", "importe": _fmt_mxn(iva), "tasa": "0.160000"},
        ],
        "retenciones": [],
    }

    # verifica_url directo (sin _sello_8; ya no existe en esta etapa del pipeline).
    timbre = cfdi_data["timbre"]
    cfdi_data["verifica_url"] = (
        f"{_VERIFICA_URL}?id={timbre['uuid']}"
        f"&re={cfdi_data['emisor']['rfc']}"
        f"&rr={cfdi_data['receptor']['rfc']}"
        f"&tt={cfdi_data['totales']['total']}"
        f"&fe=DEMO0000"
    )

    return cfdi_data, rows
