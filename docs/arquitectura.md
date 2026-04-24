# Arquitectura de `cfdi_inspector`

## Propósito

`cfdi_inspector` es un producto de inspección manual de XML CFDI. Su valor principal no es cubrir todo el universo SAT, sino volver legible y operable un CFDI cargado por el usuario.

La arquitectura actual separa tres preocupaciones:

- experiencia de producto
- orquestación de análisis
- lógica de dominio CFDI

## Capas principales

### 1. Producto y experiencia

Archivos principales:

- `src/App.tsx`
- `src/components/`
- `src/app/`

Responsabilidades:

- flujo de carga del XML
- estado de la sesión de análisis
- resumen, findings y navegación de conceptos impactados
- tablas de extracción y controles de UI

La UI no debería reimplementar reglas fiscales. Consume contratos ya procesados.

### 2. Aplicación CFDI

Archivos principales:

- `src/cfdi/application/cfdiAnalysisService.ts`
- `src/cfdi/application/cfdiExtractionService.ts`
- `src/cfdi/application/cfdiAnalysisAdapter.ts`
- `src/cfdi/application/cfdiTypes.ts`

Responsabilidades:

- parsear XML
- detectar perfil (`ingreso`, `pagos`, `unknown`)
- construir `CFDIData`
- producir filas de extracción
- adaptar estructuras canónicas del dominio a formatos consumibles por la UI

Esta capa traduce entre el XML crudo y los contratos de producto.

### 3. Dominio CFDI

Archivos principales:

- `src/cfdi/domain/normalizeCfdi.ts`
- `src/cfdi/domain/canonicalCfdi.ts`
- `src/cfdi/domain/diagnoseCfdiMath.ts`
- `src/cfdi/domain/explainCfdiField.ts`
- `src/cfdi/domain/cfdiCatalogs.ts`

Responsabilidades:

- normalizar el CFDI a una forma canónica
- aplicar reglas matemáticas de consistencia
- explicar códigos SAT en términos legibles
- mantener catálogos y semántica fiscal local

Aquí vive la parte más cercana al conocimiento del dominio.

### 4. Frontera de motor

Archivos principales:

- `src/cfdi/engine/analysisContract.ts`
- `src/cfdi/engine/currentTsEngine.ts`
- `src/cfdi/public/index.ts`

Responsabilidades:

- definir el contrato entre producto y motor
- encapsular el motor TypeScript vigente
- preparar el terreno para un motor alterno sin contaminar la UI

Esta frontera existe para que `cfdi_inspector` siga siendo el producto aunque cambie el motor canónico del dominio.

### 5. Ejecución en worker

Archivos principales:

- `src/lib/cfdi-worker.ts`
- `src/lib/cfdi-worker-client.ts`
- `src/app/hooks/useCfdiAnalysis.ts`

Responsabilidades:

- mover el análisis fuera del hilo principal cuando sea posible
- reportar progreso y razón del engine usado
- permitir fallback si el worker falla

## Flujo principal

1. El usuario carga un XML.
2. `useCfdiAnalysis` delega el análisis al worker.
3. El worker ejecuta el motor actual mediante el contrato del engine.
4. El resultado vuelve como bundle de análisis.
5. La UI renderiza resumen, findings, auditoría fiscal y tablas de extracción.

## Contratos visibles del producto

Los artefactos clave que la UI consume son:

- `profile`
- `cfdi`
- `ingresoRows`
- `pagoRows`
- `findings`
- `taxAuditGroups`

Si cambia el motor, estos contratos deben mantenerse estables o versionarse explícitamente.

## Decisiones arquitectónicas vigentes

- El producto visible es `cfdi_inspector`.
- El motor CFDI es una dependencia intercambiable, no la identidad del producto.
- El motor TypeScript actual sigue operativo, pero ya no debe asumirse como dueño definitivo del dominio.
- La convivencia permanente de dos motores con reglas equivalentes está descartada.

La decisión base está documentada en [analysis/2026-04-17-python-satcfdi-decision.md](./analysis/2026-04-17-python-satcfdi-decision.md).

## Riesgos actuales

- Parte del repo todavía conserva rastros del template original.
- El archivo `.env.example` ya no representa el flujo real del producto.
- La documentación de alto nivel existía fragmentada en decisiones y roadmap, pero no en un mapa único de arquitectura.
- Durante la migración del motor, es fácil mezclar cambios de producto con cambios de dominio si no se respeta la frontera `src/cfdi/engine/`.

## Regla operativa para cambios

Antes de modificar lógica CFDI, identifica primero en qué capa cae el cambio:

- si cambia experiencia o navegación, toca producto
- si cambia parsing o armado de contratos, toca aplicación
- si cambia reglas fiscales o matemáticas, toca dominio
- si cambia la forma de enchufar motores, toca engine

Esa separación evita refactors ambiguos y hace que la documentación siga siendo útil.
