# 02. Analysis Contract

## Propósito

Definir la frontera oficial entre la capa de producto y cualquier motor CFDI.  
La UI solo puede depender de este contrato o de wrappers que preserven este contrato.

## Estado actual

Ya existe una versión operativa del contrato en `src/cfdi/engine/analysisContract.ts` y ya se usa en el flujo principal del análisis. La siguiente iteración del contrato ya no es conceptual; será principalmente para soportar benchmark, capacidades no soportadas y adaptación del motor Python.

## Objetivo final

Que cualquier motor CFDI pueda integrarse detrás del producto sin obligar cambios en:
- vistas,
- hooks de lectura,
- exports,
- worker orchestration,
- navegación de findings.

## Forma mínima del contrato

El contrato actual debe seguir incluyendo:
- `engine`
- `profile`
- `cfdi`
- `ingresoRows`
- `pagoRows`
- `issues`

## Tipos públicos esperados

### `CfdiEngineName`
Motores conocidos:
- `current-ts`
- `python-satcfdi`

### `CfdiAnalysisStage`
Etapas mínimas:
- `profile`
- `parse`
- `extract`

### `CfdiAnalysisIssue`
Debe distinguir:
- código estable
- mensaje
- etapa
- severidad fatal o no fatal

La forma actual ya contempla:
- `UNSUPPORTED_CAPABILITY`
- `ENGINE_RUNTIME_FAILED`

Una evolución futura posible es agregar:
- `VALIDATION_FAILED`

### `CfdiAnalysisContractResult`
Debe modelar:
- motor emisor del resultado
- perfil detectado
- `cfdi` normalizado o `null`
- datasets listos para UI
- lista de issues

### `CfdiAnalysisEngine`
Interfaz objetivo:

- `analyze(xml: string): CfdiAnalysisContractResult | Promise<CfdiAnalysisContractResult>`

No debe exponer internals del motor.

## Reglas por perfil

### `ingreso`
- `ingresoRows` poblado si el motor soporta extracción de ingresos.
- `pagoRows` vacío.

### `pagos`
- `pagoRows` poblado si el motor soporta extracción de pagos.
- `ingresoRows` vacío.

### `unknown`
- ambos datasets vacíos por default.
- no se deduce una extracción alternativa a menos que quede documentada explícitamente.

## Política de errores

### Fatal
Si falla parseo estructural o construcción del `cfdi`:
- `cfdi = null`
- datasets vacíos
- el issue debe marcarse fatal

### No fatal
Si falla una capacidad derivada pero el núcleo del comprobante se pudo construir:
- `cfdi` puede existir
- los datasets afectados van vacíos
- el issue debe marcar el gap sin colapsar el resultado completo

Política actual:
- parseo fallido => fatal
- extracción fallida => no fatal si `cfdi` ya existe
- capacidades no soportadas => no fatales, pero explícitas

## Compatibilidad pública

- `analyzeCFDIContract` es la API pública de análisis.
- `analyzeCFDI` fue retirado al cerrar la fase 07.
- La UI y cualquier integración nueva deben depender del contrato `CfdiAnalysisContractResult`.

## Implementación o ejecución esperada

1. Mantener `CfdiAnalysisEngine` como frontera oficial.
2. Revisar si faltan categorías de issues para benchmark y motor Python.
3. Seguir migrando módulos auxiliares a la API de contrato si aún quedaran supuestos legacy.
4. Agregar tests de benchmark sobre este contrato.

## Validación

El contrato se considera correcto si:
- soporta `current-ts` sin hacks de UI,
- soporta un adaptador Python sin filtrar tipos nativos,
- deja explícito qué dataset corresponde a cada perfil,
- y permite comparar motores en benchmark.

## Criterio de salida

La fase de contrato termina cuando la app principal puede consumir el análisis sin depender de comportamientos accidentales del motor histórico.
