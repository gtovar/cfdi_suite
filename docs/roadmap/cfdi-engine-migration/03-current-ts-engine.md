# 03. Current TS Engine

## Propósito

Definir el rol del motor TypeScript actual mientras siga siendo el motor operativo por defecto.

## Estado actual

El motor actual ya está parcialmente encapsulado en:
- `src/cfdi/engine/currentTsEngine.ts`

Produce resultados alineados al contrato, implementa la interfaz formal del motor y mantiene compatibilidad con la API pública legacy.

## Qué cubre hoy

- detección de perfil `ingreso` o `pagos`
- parseo local de XML CFDI
- normalización básica de comprobante
- diagnóstico matemático y findings operativos
- extracción de filas para ingresos
- extracción de filas para pagos

## Qué no debe asumirse

- que sea kernel definitivo del dominio CFDI
- que tenga cobertura de nómina, retenciones, PACs, validación formal SAT o complementos amplios
- que deba crecer en superficie fiscal amplia por inercia solo porque ganó el ownership para este producto

## Decisiones ya cerradas

- Para perfil `pagos`, `ingresoRows` debe quedar vacío.
- Para perfil `ingreso`, `pagoRows` debe quedar vacío.
- Si la extracción falla después de construir `cfdi`, el resultado se degrada con `issues` no fatales.
- La API pública legacy seguirá viva durante transición, pero el motor debe responder primero al contrato.

## Qué preservar

- estabilidad operativa actual
- findings y soporte a la UX existente
- velocidad y simpleza local mientras siga siendo el motor activo

## Qué corregir

- revisar módulos restantes de UI/exportación por supuestos legacy
- retirar gradualmente la compatibilidad legacy que todavía envuelve el contrato
- evitar que la victoria de `current-ts` reactive crecimiento paralelo con `python-satcfdi`

## Qué detener

No agregar nuevas capacidades grandes del dominio SAT en TypeScript sin una decisión explícita de producto que amplíe el alcance actual.

## Implementación o ejecución esperada

1. Mantener `current-ts` como implementación de referencia del contrato.
2. Revisar módulos de app todavía dependientes de compatibilidad legacy.
3. Mantener el benchmark del corpus como regresión comparativa.
4. Congelar expansión de dominio nueva fuera de correcciones puntuales y alcance vigente del producto.

## Validación

El motor TS se considera correctamente encapsulado si:
- puede correrse desde benchmark y desde UI usando la misma interfaz
- no exige supuestos especiales del frontend
- y sus limitaciones quedan visibles como issues o gaps, no como comportamiento implícito

## Criterio de salida

Este documento queda estable cuando `current-ts` ya sea tratado como una implementación de motor y no como el diseño natural del producto.
