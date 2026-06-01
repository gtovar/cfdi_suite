# Contrato: Sentinel de Catálogo SAT

## Qué es

El **sentinel de catálogo** es una cadena de texto que el wrapper Python emite cuando un código SAT no existe en el catálogo oficial. Su valor es:

```
"No existe en el catálogo"
```

Esta cadena es el **punto de verdad único** del contrato. Está definida como `SENTINEL_INVALIDO` en `src/cfdi/engine/python-satcfdi-wrapper.py`.

---

## Por qué existe

`python-satcfdi` devuelve un objeto `Code` para cada campo de catálogo. Si el código existe en el catálogo SAT, `Code.description` contiene el nombre del catálogo (ej. `"Gastos en general"`). Si el código **no existe**, `Code.description` es `None`.

El wrapper detecta `description = None` y emite el sentinel en el campo `*Descripcion` correspondiente. Esto permite que el backend detecte el problema sin necesitar acceso directo a satcfdi.

---

## Cómo se propaga por las 3 capas

```
satcfdi → Code.description = None
    ↓
python-satcfdi-wrapper.py → emite SENTINEL_INVALIDO en campo *Descripcion
    ↓
analyze_cfdi.py → _collect_catalog_findings detecta sentinel → genera finding
    ↓
Frontend → useFindingContexts.ts → convierte finding a contexto rich con correctionSteps
```

---

## Catálogos que usan este patrón

| Campo CFDI | Campo wrapper | Campo descripción | Finding ID | Catálogo SAT |
|---|---|---|---|---|
| `Receptor.UsoCFDI` | `usoCfdi` | `usoCfdiDescripcion` | `catalog-uso-cfdi-{code}` | `c_UsoCFDI` |
| `MetodoPago` (header) | `metodoPago` | `metodoPagoDescripcion` | `catalog-metodo-pago-{code}` | `c_MetodoPago` |
| `FormaPago` (header) | `formaPago` | `formaPagoDescripcion` | `catalog-forma-pago-{code}` | `c_FormaPago` |
| `Moneda` | `moneda` | `monedaDescripcion` | `catalog-moneda-{code}` | `c_Moneda` |
| `Concepto.ClaveProdServ` | `claveProdServ` | `claveProdServDescripcion` | `catalog-clave-prod-serv-{code}` | `c_ClaveProdServ` |

---

## Comportamiento según el estado del campo

| Estado del campo | `Code.description` | Valor emitido en `*Descripcion` | Finding generado |
|---|---|---|---|
| Código válido | `"Gastos en general"` | `"Gastos en general"` | No |
| Código inválido | `None` | `"No existe en el catálogo"` | Sí |
| Campo ausente del XML | — (campo es `None`) | `None` | No |

Un campo **ausente** nunca genera finding. La validación es solo de pertenencia al catálogo, no de presencia obligatoria.

---

## Qué NO valida este patrón

- **Validez contextual**: no verifica si el UsoCFDI es válido para el régimen fiscal del receptor.
- **FormaDePagoP** del complemento Pagos (es un campo distinto al `FormaPago` de cabecera).
- **Presencia obligatoria** de campos según el tipo de CFDI (eso es validación XSD, Frente D).
- **claveUnidad**: el patrón existe pero no está implementado todavía.

---

## Regla para agregar un catálogo nuevo

1. En `python-satcfdi-wrapper.py`: agregar `"nuevocampo": code_or_raw(valor)` y `"nuevocampoDescripcion": catalog_desc_or_sentinel(valor)` en `build_cfdi_payload`.
2. En `analyze_cfdi.py`: agregar una fila a `_HEADER_CATALOG_FIELDS` con `(code_field, desc_field, prefix, label, catalog)`.
3. En `useFindingContexts.ts`: agregar una entrada a `HEADER_CATALOG_PREFIXES` (constante de módulo).
4. Crear o actualizar el XML fixture en `backend/test-fixtures/` con el nuevo código inválido.
5. Actualizar esta tabla.

---

## Riesgo clave

Si alguien cambia la cadena `SENTINEL_INVALIDO` en el wrapper sin actualizar `_SENTINEL_INVALIDO` en `analyze_cfdi.py`, todos los findings de catálogo dejan de generarse silenciosamente. Los tests del wrapper y del servicio usan la constante importada del wrapper, por lo que detectarían el cambio si los tests se ejecutan.

**No cambiar la cadena sin actualizar ambos archivos.**
