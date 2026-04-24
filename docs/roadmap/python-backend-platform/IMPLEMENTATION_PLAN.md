# Implementation Plan

## Objetivo

Consolidar `cfdi_inspector` como plataforma `frontend + backend Python` con estas reglas:

- React/Vite sigue siendo la experiencia de producto
- el backend Python es la frontera estable del dominio
- `python-satcfdi` es el provider inicial, no el contrato del producto
- `current-ts` queda como fallback backend transicional
- findings ricos siguen siendo trabajo posterior

## Punto de partida real

La base principal ya existe y esta vez debe asumirse como implementada:

- FastAPI ya expone `POST /api/cfdi/analyze`
- el contrato HTTP v1 ya está tipado en `backend/app/contracts.py`
- el service `run_analyze_cfdi` ya ensambla `issues` y `meta` v1
- el backend ya resuelve `primary + fallback`
- el frontend ya consume el resultado contractual del backend
- el fallback local solo queda como escape hatch por indisponibilidad real de la API

Por lo tanto, el frente actual ya no es "crear backend" ni "mover fallback al backend".

## Estado implementado que el plan debe asumir

### Contrato HTTP v1 ya materializado

La respuesta actual ya incluye:

- `profile`
- `cfdi`
- `ingresoRows`
- `pagoRows`
- `issues`
- `meta`

Y `meta` ya publica:

- `contractVersion = "v1"`
- `capability = "analyze_cfdi"`
- `provider`
- `providerMode`
- `degraded`
- `requestId`
- `providerVersion`
- `warnings`
- `timingMs`
- `fallbackReason`

### Contrato interno de provider ya materializado

La capability ya depende de:

- `ProviderCapabilities`
- `ProviderDocumentSignal`
- `ProviderIssue`
- `ProviderDiagnostics`
- `ProviderResult`

### Mínimo operativo v1 ya materializado

Queda cerrado en código:

- `xml` requerido con límite de `1_000_000` caracteres
- timeout de providers de `15s`
- request inválido con respuesta contractual segura
- runtime fatal con mensaje público neutral
- fallback reason contractual mínimo: `provider_runtime_failure`

## Frente actual correcto

La prioridad inmediata es:

1. consolidar el baseline operable de v1
2. mantener contrato y docs sincronizados
3. preparar la siguiente etapa de findings ricos

No es prioridad inmediata:

- nuevas capabilities
- expansión del dominio CFDI
- reabrir fallback governance ya cerrado

## Secuencia recomendada

### Paso 1. Operación y baseline del backend

- ejecutar backend con `backend/requirements.txt` instalado
- usar `npm run test:api` como baseline local de backend
- mantener contract tests HTTP y service tests como criterio mínimo de estabilidad v1

### Paso 2. Observabilidad mínima documentada

- usar `requestId`, `provider`, `providerMode`, `degraded` y `fallbackReason` como semántica estable
- usar esas señales como base de logs estructurados y métricas locales reales
- no cambiar shape ni significado contractual de esos campos

### Paso 3. Mantener v1 seguro

- no exponer tracebacks, rutas internas ni contenido sensible del XML
- preservar mensajes públicos neutrales
- mantener request inválido y runtime fatal con respuestas coherentes para la UI actual

### Paso 4. Findings ricos después

Solo después de estabilizar v1:

- enriquecer `cfdi.findings`
- reemplazar placeholders de `verdict` y `supportText`
- evaluar retiro del fallback local visible

## Criterios de aceptación de esta etapa

Esta etapa queda razonablemente cerrada cuando:

- la documentación ya no describe fallback backend como trabajo pendiente
- el backend tiene baseline explícito de ejecución y pruebas
- el mínimo operativo v1 está cerrado en docs y código
- findings ricos siguen explícitamente fuera del alcance inmediato

## Riesgo a evitar

Que el roadmap siga guiando trabajo con un estado histórico y no con el estado real del repo.

Ese desfase vuelve ambiguas las siguientes decisiones aunque el código ya funcione.
