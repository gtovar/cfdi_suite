# 02. API Contract

## Propósito

Definir la salida mínima que el frontend necesita para seguir funcionando.

## Endpoint inicial

`POST /api/cfdi/analyze`

## Input mínimo

- XML CFDI como texto

## Output mínimo

- `profile`
- `cfdi`
- `ingresoRows`
- `pagoRows`
- `issues`
- metadatos de motor/backend

## Regla

El contrato de API debe parecerse al contrato actual del frontend tanto como sea razonable.

No debemos obligar a la UI a conocer estructuras internas de `python-satcfdi`.

## Primera decisión técnica

La compatibilidad debe ocurrir en un adaptador del backend, no dispersa en componentes React.
