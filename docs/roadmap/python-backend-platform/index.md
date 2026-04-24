# Python Backend Platform

## Objetivo

Convertir `cfdi_inspector` en un sistema de dos capas:

- frontend React/Vite para inspección
- backend Python basado en `python-satcfdi` como motor principal

## Estado actual

- la UI actual existe y ya resuelve inspección operativa
- el backend FastAPI en `backend/app/` ya expone `POST /api/cfdi/analyze`
- el frontend ya consume el contrato HTTP v1 del backend
- `python-satcfdi` ya opera como provider backend `bridge`
- `current-ts` queda como fallback backend transicional
- esta ruta reemplaza la dirección estratégica previa del roadmap `cfdi-engine-migration`

## Secuencia recomendada

1. [01-target-architecture.md](./01-target-architecture.md)
   Qué sistema queremos construir y qué queda fuera.
2. [02-api-contract.md](./02-api-contract.md)
   Qué debe pedir y recibir el frontend.
3. [DECISION_EXPANSION.md](./DECISION_EXPANSION.md)
   Variables omitidas, supuestos débiles, límites reales y alternativas no obvias antes de cerrar arquitectura y roadmap.
4. [DECISION_VALIDATION_PASS_2.md](./DECISION_VALIDATION_PASS_2.md)
   Segunda validación crítica sobre los refuerzos agregados al plan para distinguir criterio útil de decisión operativa cerrada.
5. [ANALYZE_CFDI_OWNERSHIP_MATRIX.md](./ANALYZE_CFDI_OWNERSHIP_MATRIX.md)
   Ownership operativo por subresponsabilidad, política de fallback y límites de degradación de `analyze_cfdi`.
6. [API_V1_SEMANTICS_APPENDIX.md](./API_V1_SEMANTICS_APPENDIX.md)
   Semántica exacta de `meta`, `issues`, `degraded`, `providerMode` y compatibilidad del contrato v1.
7. [OPERATIONAL_MINIMUM_V1.md](./OPERATIONAL_MINIMUM_V1.md)
   Mínimo operativo para observabilidad, errores seguros, datos sensibles y trazabilidad.
8. [03-python-service.md](./03-python-service.md)
   Cómo montar el backend mínimo sobre `python-satcfdi`.
9. [04-frontend-adapter.md](./04-frontend-adapter.md)
   Cómo conectar la UI actual al backend sin reescribir toda la app.
10. [05-ts-engine-retirement.md](./05-ts-engine-retirement.md)
   Cómo retirar el motor TS como runtime principal.
11. [STATUS.md](./STATUS.md)
   Estado operativo corto y siguiente frente real.

## Regla central

La UI sigue siendo `cfdi_inspector`.

El dominio fiscal amplio vive en Python.

TypeScript deja de ser la dirección principal del motor CFDI.

El siguiente frente ya no es construir el backend, sino estabilizar e instrumentar la capability v1 y luego enriquecer findings.
