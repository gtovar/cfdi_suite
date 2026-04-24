# 01. Decision Context

## Propósito

Congelar el contexto que justifica esta ruta para que el trabajo técnico posterior no reabra la discusión base sin evidencia nueva.

## Qué existe realmente

### `cfdi_inspector`
- Producto React/Vite orientado a inspección manual de CFDIs.
- Valor principal: UX, lectura operativa, findings, navegación y explicación.
- Alcance actual de dominio visible: `ingreso` y `pagos`, con motor local TypeScript.

### `python-satcfdi`
- Librería/plataforma Python con cobertura mucho más amplia del dominio CFDI/SAT.
- Valor principal: amplitud y madurez del motor, no experiencia de inspección UX-first.

## Decisión ya cerrada

- No se va a tirar `cfdi_inspector` como producto.
- No se va a asumir que el motor local TS debe seguir siendo el kernel definitivo del dominio.
- `python-satcfdi` se evaluará como candidato a motor canónico.
- No se permite una arquitectura híbrida permanente.

## Qué no debe confundirse

- Un frontend convincente no valida por sí mismo el kernel del dominio.
- Un motor amplio no valida por sí mismo la UX o el producto.
- Integrar el otro repo no significa mezclar ambos árboles de código.
- Migrar de motor no significa migrar de producto.

## Riesgos que esta decisión intenta evitar

- Duplicación permanente de reglas CFDI en TS y Python.
- Seguir ampliando el motor TS por inercia mientras ya existe un candidato de dominio más fuerte.
- Reemplazar el producto actual solo porque el otro repo tiene más cobertura funcional.

## Documento fuente

La base argumental completa está en [2026-04-17-python-satcfdi-decision.md](../../analysis/2026-04-17-python-satcfdi-decision.md).

## Criterio de salida

Este documento se considera estable salvo que aparezca evidencia nueva que cambie una de estas tres cosas:
- quién es el producto,
- quién debe ser dueño del dominio,
- o si la transición híbrida deja de ser temporal.
