# 05. Python SAT-CFDI Adapter

## Propósito

Integrar `python-satcfdi` como motor candidato detrás del contrato del producto, sin absorber su árbol funcional completo dentro de `cfdi_inspector`.

## Regla base

Este adaptador no convierte `python-satcfdi` en el producto.  
Solo lo convierte en una implementación del motor CFDI comparable con `current-ts`.

## Qué sí entra en esta fase

- carga de XML
- perfilado
- parseo estructural útil para el contrato
- metadatos esenciales del comprobante
- conceptos e impuestos normalizados si están disponibles
- datasets equivalentes si el motor puede construirlos
- issues y capacidades no soportadas

## Qué no entra todavía

- CLI de usuario final
- render PDF/HTML/JSON como feature del producto
- PACs
- descargas SAT
- DIOT, contabilidad, CSF y utilidades periféricas
- cualquier superficie ajena al contrato del producto actual

## Estrategia de invocación inicial

La integración inicial debe ser local y orientada a benchmark, no a despliegue productivo.

Ruta recomendada:
- script puente o proceso controlado
- salida serializada a formato consumible por el contrato
- aislamiento del runtime Python respecto a React/UI

## Mapeo esperado al contrato

El adaptador debe llenar, como mínimo:
- `engine = "python-satcfdi"`
- `profile`
- `cfdi` o `null`
- datasets vacíos si no se soportan todavía
- `issues` honestos cuando falte capacidad

No debe fingir equivalencia donde aún no exista.

## Gaps tolerables al inicio

Se permite que la primera versión:
- no construya todos los datasets
- no replique findings exactos del motor TS
- deje campos vacíos mientras lo haga explícito como gap

No se permite:
- salida ambigua
- errores silenciosos
- o mezclar estructuras nativas de Python dentro de la UI

## Implementación o ejecución esperada

1. Elegir una forma simple de invocar Python desde benchmark.
2. Construir mapeo mínimo a contrato.
3. Correr smoke tests con fixtures del corpus.
4. Identificar qué capacidades reales aporta frente al motor TS.

## Implementación actual en este repo

- Adaptador TS: `src/cfdi/engine/pythonSatcfdiEngine.ts`
- Wrapper Python: `src/cfdi/engine/python-satcfdi-wrapper.py`
- Runner compartido: `src/cfdi/benchmark/runBenchmark.ts`
- Script CLI:

```bash
npm run benchmark:python-satcfdi
```

Salida JSON:

```bash
npm run benchmark:python-satcfdi:json
```

## Estado del adaptador actual

- ya corre sobre el mismo corpus que `current-ts`
- ya reporta `profile`
- ya construye `cfdi` mínimo y datasets básicos de ingresos/pagos sobre el corpus actual
- usa `.venv-satcfdi/` local por defecto cuando existe
- si `satcfdi` no está instalado, clasifica el gap como `UNSUPPORTED_CAPABILITY`
- si el wrapper falla o devuelve salida inválida, clasifica el problema como `ENGINE_RUNTIME_FAILED`
- findings equivalentes al motor TS siguen pendientes y se reportan como `UNSUPPORTED_CAPABILITY`

## Validación

El adaptador se considera útil si:
- corre con el benchmark existente
- aporta evidencia sobre cobertura del dominio
- y no obliga a tocar la UI para integrarse

## Criterio de salida

La fase termina cuando `python-satcfdi` ya puede medirse contra el mismo corpus y la misma forma de salida que `current-ts`.
