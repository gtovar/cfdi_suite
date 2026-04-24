# 07. Migration and Retirement

## Propósito

Definir cómo se sustituye o retira un motor sin dejar duplicación estructural ni ambigüedad de ownership.

## Escenario activo

Ganó `current-ts` para el producto actual.

La tarea de esta fase ya no es escoger entre escenarios, sino ejecutar este cierre:
- dejar `python-satcfdi` como benchmark o referencia de dominio
- cerrar formalmente su evaluación como motor del producto
- preparar el retiro gradual de compatibilidad legacy que todavía envuelve el contrato

Estado de cierre de esta fase:
- completado
- `python-satcfdi` queda congelado para benchmark y referencia de dominio, no para crecimiento paralelo del producto
- `current-ts` queda ratificado como único dueño operativo del flujo de la app
- la compatibilidad legacy interna ligada a `analyzeCFDI` ya fue retirada

## Regla central

Cada capability del dominio debe tener un solo dueño.  
No se aceptan dos implementaciones equivalentes activas sin fecha de retiro.

## Capability map vigente

- parseo y perfilado del producto: `current-ts`
- normalización de `cfdi` consumida por UI: `current-ts`
- findings y framing operativo: `current-ts`
- extracción de ingresos y pagos: `current-ts`
- benchmark comparativo entre motores: `current-ts` y `python-satcfdi`
- referencia de dominio SAT amplio fuera del flujo del producto: `python-satcfdi`

Regla derivada:
- no agregar nuevas capacidades equivalentes en ambos motores
- no implementar findings equivalentes en `python-satcfdi` dentro de esta fase
- no mover la app al motor Python salvo reapertura formal de la decisión

Validación contra el código actual:
- `useCfdiAnalysis` consume `CfdiAnalysisContractResult` directamente y no depende del bundle legacy
- `cfdi-worker-client` resuelve `analyzeCFDIContract(...)` tanto en worker como en fallback
- el benchmark comparte el registro de motores `current-ts` y `python-satcfdi`
- `python-satcfdi` no participa en el flujo productivo de UI; solo entra por benchmark o uso explícito del adaptador

## Qué preservar

- UX de inspección
- findings y framing operativo
- navegación y lectura de conceptos impactados
- flujo de carga y exportación del producto

## Qué retirar cuando corresponda

- parseo duplicado
- normalización duplicada
- extracción duplicada
- adapters muertos o benchmark temporal no usado
- wrappers legacy que ya no aporten compatibilidad real

## Remanentes legacy auditados hoy

- `useCfdiAnalysis` ya consume `CfdiAnalysisContractResult` directamente y dejó de depender de `toLegacyAnalysisBundle(...)`
- worker, fallback local y exportación parten del resultado contractual o de `CFDIData` derivado de ese resultado
- `analyzeCFDI` no tenía consumidores internos de producción y ya fue retirado del API pública
- `CFDIAnalysisBundle`, `buildCfdiAnalysisBundle(...)` y `toLegacyAnalysisBundle(...)` fueron retirados junto con ese legado

Lectura:
- el ownership del dominio ya no es ambiguo
- la deuda restante ya no está en el flujo de análisis, sino en sostener la disciplina del contrato y del benchmark

## Implementación o ejecución esperada

1. Publicar decisión de motor y capability map.
2. Congelar `python-satcfdi` como benchmark o referencia de dominio.
3. Mantener la app detrás del contrato con `current-ts` como único dueño operativo.
4. Convertir remanentes legacy en una lista cerrada de cleanup.
5. Retirar wrappers o adapters muertos cuando la UI ya no dependa del bundle histórico.

Lista cerrada de cleanup derivada:
- retirar `analyzeCFDI` del API pública
- retirar `CFDIAnalysisBundle`
- retirar `buildCfdiAnalysisBundle(...)`
- retirar `toLegacyAnalysisBundle(...)`
- conservar `python-satcfdi` solo en benchmark, tests y documentación de referencia

Estado de ejecución de la lista:
- completado

## Validación

La migración se considera sana si:
- la UX no pierde claridad
- el benchmark sigue disponible como regresión
- el ownership del dominio queda inequívoco
- los remanentes legacy quedan identificados como compatibilidad transitoria y no como otra fuente de verdad

Resultado de validación actual:
- se cumple

## Criterio de salida

La fase termina cuando:
- el producto opera con `current-ts` como único dueño real del dominio
- `python-satcfdi` queda relegado formalmente a benchmark o referencia
- y los remanentes legacy quedan retirados o acotados a compatibilidad explícita

Estado:
- criterio satisfecho
- fase cerrada con remanentes legacy ya retirados del flujo activo
