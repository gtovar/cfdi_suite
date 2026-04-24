# 03. Python Service

## Propósito

Montar un backend mínimo y operativo alrededor de `python-satcfdi`.

## Requisitos mínimos

- endpoint HTTP de análisis
- ejecución local reproducible
- manejo explícito de errores de parseo y runtime
- salida JSON alineada al contrato del frontend

## Primera entrega aceptable

- un servicio local capaz de analizar `ingreso` y `pagos`
- integración real con `python-satcfdi`
- pruebas contra fixtures existentes del repo

## Regla

El backend no debe exponer el modelo crudo del motor si eso contamina el frontend.
