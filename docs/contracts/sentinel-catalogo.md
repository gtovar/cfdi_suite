# Contrato: Sentinel de Catálogo SAT

---

## Historia y contexto: por qué nació esto

### El problema original

CFDI Suite es un inspector de facturas XML del SAT mexicano. Una de sus capacidades centrales es detectar errores en CFDIs antes de que el SAT los rechace o antes de que un auditor los señale.

Los CFDIs usan catálogos oficiales SAT para campos como `ClaveProdServ` (qué bien o servicio se factura), `UsoCFDI` (para qué se usará la factura), `FormaPago` (cómo se pagó), `MetodoPago` (si se pagó en una o varias exhibiciones) y `Moneda`. Estos catálogos tienen centenares de claves válidas. Si alguien pone `UsoCFDI="ZZZ"` o `ClaveProdServ="99999999"` en el XML, el CFDI puede parecer técnicamente bien formado pero el SAT lo rechazará o marcará como inválido porque esa clave no existe.

Detectar esto manualmente es tedioso. Es exactamente el tipo de error que un inspector automatizado debería atrapar.

### Por qué delegamos los catálogos a `python-satcfdi` y no los reimplementamos

En abril 2026 se tomó la decisión de adoptar `python-satcfdi` como motor de dominio fiscal (ver `docs/analysis/2026-04-17-python-satcfdi-decision.md`). Una de las razones principales: `python-satcfdi` mantiene los catálogos SAT actualizados en una base de datos SQLite que forma parte del paquete. Reimplementar esos catálogos en TypeScript hubiera significado mantener cientos de claves por nuestra cuenta — exactamente el tipo de duplicación que queríamos evitar.

La regla quedó documentada en `docs/ROADMAP_MAESTRO.md`: "Antes de implementar algo en TypeScript, verificar si satcfdi ya lo tiene. Si lo tiene, implementarlo en el wrapper Python."

### El problema de arquitectura: 3 capas, 1 señal

La arquitectura tiene 3 capas separadas:

```
Frontend (TypeScript/React)
    ↕ HTTP JSON
Backend FastAPI (Python)
    ↕ subprocess stdin/stdout
Wrapper Python (script standalone)
    ↕ import
python-satcfdi
```

El wrapper es un **script independiente** que se ejecuta como subproceso. No puede importar del backend, no puede compartir clases Python con el backend. Se comunica exclusivamente a través de JSON en stdout.

Cuando `python-satcfdi` parsea un CFDI, devuelve objetos `Code` para los campos de catálogo:
- Si el código existe: `Code(code="G03", description="Gastos en general")`
- Si el código no existe: `Code(code="ZZZ", description=None)`

El wrapper necesita comunicar al backend "este código no está en el catálogo" sin poder pasar el objeto `Code` directamente (JSON no soporta objetos Python arbitrarios).

### La decisión: usar un sentinel de texto, no un array separado

**Opción A (la que se adoptó):** Emitir una cadena especial `"No existe en el catálogo"` en el campo `*Descripcion` del campo afectado. El backend la detecta y genera el finding.

**Opción B (descartada):** Agregar un array separado `"invalidCatalogCodes": ["ZZZ"]` al payload JSON. Más explícito, pero rompe la separación: el wrapper tendría que saber qué campos son catálogos, qué finding generar, y cómo nombrarlos — lógica que pertenece al backend.

**Opción C (descartada):** Hacer que el backend llame directamente a satcfdi para validar catálogos. Más limpio en teoría, pero el backend corre en Python con FastAPI y tiene su propia lógica de análisis. Agregar una dependencia directa a satcfdi desde el backend mezclaría capas: el backend interpretaría el CFDI, no solo analizaría el resultado del wrapper.

La Opción A ganó porque:
1. El patrón ya existía para `claveProdServ` (`claveProdServDescripcion` con el sentinel)
2. Es simple: el backend solo busca la cadena en el campo, no necesita saber nada de satcfdi
3. El frontend no necesita cambios de contrato HTTP — los campos de descripción ya estaban planeados

### La evolución: de claveProdServ a los catálogos de cabecera

El patrón se implementó primero solo para `ClaveProdServ` (Frente A, junio 2026). El wrapper ya emitía `claveProdServDescripcion`, y `_collect_catalog_findings` en el backend detectaba el sentinel.

En la misma sesión (Frente B-ext, junio 2026) se extendió a los 4 campos de cabecera: `UsoCFDI`, `MetodoPago`, `FormaPago` y `Moneda`. El patrón era idéntico, solo faltaba replicarlo. Se agregó `catalog_desc_or_sentinel()` como función helper en el wrapper para evitar duplicar la lógica de detección de `description=None` en cada campo.

---

## Qué es el sentinel

El **sentinel de catálogo** es una cadena de texto que el wrapper Python emite cuando un código SAT no existe en el catálogo oficial:

```
"No existe en el catálogo"
```

Esta cadena es el **punto de verdad único** del contrato entre el wrapper y el backend. Está definida como `SENTINEL_INVALIDO` en `src/cfdi/engine/python-satcfdi-wrapper.py` y referenciada como `_SENTINEL_INVALIDO` en `backend/app/services/analyze_cfdi.py`.

---

## Cómo funciona `python-satcfdi` internamente

Cuando satcfdi parsea un CFDI, resuelve cada código de catálogo contra su base de datos SQLite local. El resultado es siempre un objeto `Code`:

```python
Code(code="G03", description="Gastos en general")  # código válido
Code(code="ZZZ", description=None)                  # código inválido
```

La clave: `description=None` es la señal de satcfdi para "este código no existe". El wrapper lee esa señal y la convierte al sentinel de texto para que el backend la pueda detectar en JSON.

---

## Cómo se propaga por las 3 capas

```
XML con UsoCFDI="ZZZ"
    ↓
python-satcfdi → Code(code="ZZZ", description=None)
    ↓
python-satcfdi-wrapper.py
    catalog_desc_or_sentinel(uso_cfdi)
    → description is None → SENTINEL_INVALIDO
    → emite "usoCfdiDescripcion": "No existe en el catálogo"
    ↓
analyze_cfdi.py → _collect_catalog_findings(source)
    → source["usoCfdiDescripcion"] == _SENTINEL_INVALIDO
    → genera finding: {id: "catalog-uso-cfdi-ZZZ", severity: "warning", ...}
    ↓
Frontend → useFindingContexts.ts
    → finding.id.startsWith("catalog-uso-cfdi-")
    → devuelve FindingContext con explanation + correctionSteps
    ↓
FindingsSidebar → muestra "Uso de CFDI inválido: ZZZ" con guía de corrección
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
| Código inválido | `None` | `"No existe en el catálogo"` | Sí (warning) |
| Campo ausente del XML | — (campo es `None` en satcfdi) | `None` | No |

Un campo **ausente** nunca genera finding. La validación es solo de pertenencia al catálogo, no de presencia obligatoria del campo en el XML.

---

## Qué NO valida este patrón

- **Validez contextual**: no verifica si el UsoCFDI es válido para el régimen fiscal del receptor (ej. "CN01 - Nómina" solo es válido cuando el receptor es persona física con actividad empresarial). Eso requeriría lógica de cruce entre catálogos, que satcfdi no expone directamente.
- **FormaDePagoP** del complemento Pagos (es un campo distinto al `FormaPago` de cabecera; vive dentro de `cfdi:Complemento/pago20:Pagos/pago20:Pago`).
- **Presencia obligatoria** de campos según el tipo de CFDI (si un CFDI tipo I debe o no llevar MetodoPago). Eso corresponde a validación XSD (Frente D del roadmap).
- **claveUnidad**: el patrón está listo para extenderse, pero la implementación queda pendiente.

---

## Regla para agregar un catálogo nuevo

1. En `python-satcfdi-wrapper.py`: agregar dentro de `build_cfdi_payload`:
   ```python
   mi_campo = cfdi.get("MiCampo")
   # ... en el return dict:
   "miCampo": code_or_raw(mi_campo),
   "miCampoDescripcion": catalog_desc_or_sentinel(mi_campo),
   ```
2. En `analyze_cfdi.py`: agregar una fila a `_HEADER_CATALOG_FIELDS`:
   ```python
   ("miCampo", "miCampoDescripcion", "catalog-mi-campo", "Mi campo", "c_MiCampo"),
   ```
3. En `useFindingContexts.ts`: agregar una entrada a `HEADER_CATALOG_PREFIXES`:
   ```ts
   'catalog-mi-campo-': { label: 'Mi campo', catalog: 'c_MiCampo' },
   ```
4. Crear o actualizar el XML fixture en `backend/test-fixtures/cfdi-catalogo-invalido-cabecera.xml` con el nuevo código inválido.
5. Actualizar la tabla de catálogos de este documento.

---

## Riesgo conocido y mitigación

**El riesgo:** si alguien cambia la cadena `SENTINEL_INVALIDO` en el wrapper sin actualizar `_SENTINEL_INVALIDO` en `analyze_cfdi.py`, todos los findings de catálogo dejan de generarse **silenciosamente** — sin error, sin excepción, sin test rojo inmediato.

**La mitigación actual:** los tests del wrapper y del servicio importan `SENTINEL_INVALIDO` directamente del módulo del wrapper (`_wrapper.SENTINEL_INVALIDO`). Si la cadena cambia en el wrapper, los tests que verifican que el sentinel activa un finding seguirán pasando (usan la misma constante), pero el backend seguirá buscando el valor antiguo → los tests de integración en `test_catalog_integration.py` fallarían porque `_normalize_cfdi` no encontraría el sentinel y no generaría findings.

**No cambiar la cadena sin actualizar `_SENTINEL_INVALIDO` en `analyze_cfdi.py` y ejecutar `npm run test:api`.**

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `src/cfdi/engine/python-satcfdi-wrapper.py` | Define `SENTINEL_INVALIDO`, `catalog_desc_or_sentinel()`, `build_cfdi_payload()` |
| `backend/app/services/analyze_cfdi.py` | Define `_SENTINEL_INVALIDO`, `_HEADER_CATALOG_FIELDS`, `_collect_catalog_findings()` |
| `src/app/hooks/useFindingContexts.ts` | Define `HEADER_CATALOG_PREFIXES`, maneja findings `catalog-*` |
| `backend/tests/test_python_satcfdi_wrapper.py` | Tests unitarios del wrapper y de la función helper |
| `backend/tests/test_catalog_integration.py` | Test de integración con satcfdi real y XML fixture real |
| `backend/test-fixtures/cfdi-catalogo-invalido-cabecera.xml` | XML con `UsoCFDI="ZZZ"` y `FormaPago="ZZ"` para prueba manual y tests |
