# 04. Frontend Adapter

## Propósito

Sustituir el análisis local del browser por llamadas al backend Python.

## Trabajo esperado

- crear cliente HTTP para análisis
- adaptar `useCfdiAnalysis`
- retirar dependencia principal del worker para análisis de dominio
- conservar la UX actual tanto como sea posible

## Regla

La UI debe cambiar lo mínimo necesario durante la migración.

La primera ganancia debe ser cambio de motor, no rediseño visual.
