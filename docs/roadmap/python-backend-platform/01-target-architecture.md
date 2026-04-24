# 01. Target Architecture

## Propósito

Fijar la arquitectura objetivo antes de tocar implementación.

## Sistema objetivo

### Frontend

- React/Vite
- carga de XML
- visualización de resumen, findings, auditoría y tablas
- estado de sesión y experiencia de uso

### Backend

- servicio Python
- integración con `python-satcfdi`
- parsing, clasificación, normalización y cobertura de dominio
- contrato JSON consumible por la UI

## Flujo objetivo

1. El usuario carga un XML en la UI.
2. El frontend envía el XML al backend.
3. El backend procesa con `python-satcfdi`.
4. El backend devuelve un contrato estable.
5. El frontend renderiza sin saber detalles internos del dominio.

## Lo que queda fuera de esta primera etapa

- autenticación
- persistencia
- multiusuario
- PACs o SAT en línea como requisito inicial
- reescritura completa del frontend

## Principio operativo

No moveremos la complejidad del dominio al browser.

Si una regla fiscal importante aparece, su primer hogar debe ser el backend Python.
