# 05. TS Engine Retirement

## Propósito

Retirar el motor TypeScript como camino principal sin perder reversibilidad controlada.

## Estrategia

- mantener fallback temporal mientras el backend madura
- mover el ownership del dominio a Python
- eliminar reglas fiscales duplicadas cuando el backend ya cubra el caso equivalente

## Criterio de salida

El motor TS deja de ser principal cuando:

- el frontend usa backend Python por default
- `ingreso` y `pagos` pasan por backend de forma estable
- los fixtures críticos del repo quedan cubiertos
