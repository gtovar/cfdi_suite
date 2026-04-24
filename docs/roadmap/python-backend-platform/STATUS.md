# STATUS

## Fase actual

Cierre del mínimo operativo v1 sobre una base ya implementada de `frontend + backend Python`.

El frente inmediato ya no es "mover fallback al backend". Eso ya existe en el repo.

El frente correcto ahora es:

1. reconciliar roadmap y handoff contra el estado real
2. cerrar el mínimo operativo v1
3. mantener findings ricos fuera del alcance inmediato

## Estado real del repo

- la UI React/Vite sigue siendo la experiencia principal
- ya existe backend FastAPI en `backend/app/`
- ya existe `POST /api/cfdi/analyze`
- el contrato HTTP v1 ya está materializado en `backend/app/contracts.py`
- `meta` ya publica `contractVersion`, `capability`, `provider`, `providerMode`, `degraded`, `requestId`, `providerVersion`, `warnings`, `timingMs` y `fallbackReason`
- la fuente oficial de findings ya es `cfdi.findings`; no existe `findings` top-level en la respuesta v1 del backend
- el provider interno ya usa contrato rico con `ProviderCapabilities`, `ProviderDocumentSignal`, `ProviderIssue`, `ProviderDiagnostics` y `ProviderResult`
- `python-satcfdi` opera como provider `bridge`
- `current-ts` ya existe como provider backend `fallback`
- `backend/app/services/analyze_cfdi.py` ya resuelve `primary + fallback` y publica `meta.providerMode = "fallback"` cuando aplica
- `src/lib/cfdi-api-client.ts` ya consume respuestas contractuales del backend y solo deja fallback local para indisponibilidad real de la API

## Qué ya quedó cerrado

- contrato HTTP v1 explícito
- owner backend de `issues`, `degraded`, `providerMode` y `fallbackReason`
- contract/service tests de backend y tests puntuales del cliente
- catálogo contractual mínimo de `fallbackReason`: `provider_runtime_failure`
- mensajes públicos fatales neutrales: la plataforma no expone detalle interno del provider
- observabilidad mínima real en backend con logs estructurados y métricas locales en memoria
- política efectiva de logging seguro: la observabilidad usa `requestId` y no registra XML crudo

## Mínimo operativo v1 ya aterrizado

- `xml` requerido y limitado a `1_000_000` caracteres
- timeout de provider fijado en `15s`
- request inválido responde con forma contractual segura
- runtime fatal responde con mensaje público neutral
- fallback visible en metadata y medible por `providerMode` + `fallbackReason`
- request, fatales, degradación, fallback y latencia ya quedan medidos en backend local

## Brecha real contra el target

- `cfdi.findings` sigue llegando vacío desde Python
- la observabilidad ya existe localmente, pero no está exportada a un sistema externo de métricas
- la política de datos sensibles ya tiene capa dedicada de logging seguro, pero no una estrategia completa de redaction/hash por campo
- el baseline de tests HTTP del backend depende de ejecutar Python con `backend/requirements.txt` instalado

## Prioridad inmediata

1. consolidar baseline de ejecución del backend en entorno con dependencias instaladas
2. mantener sincronizados `STATUS.md`, `IMPLEMENTATION_PLAN.md`, `API_V1_SEMANTICS_APPENDIX.md`, `OPERATIONAL_MINIMUM_V1.md` e `index.md`
3. pasar después a findings ricos y retiro gradual del fallback local visible

## Siguiente frente recomendado

El siguiente frente correcto ya no es fallback governance.

El siguiente frente correcto es:

1. observar y estabilizar v1 como capability operable
2. enriquecer `cfdi.findings`
3. reemplazar placeholders de `verdict` y `supportText`
4. evaluar retiro del fallback local visible en frontend

## Reentrada mínima

1. leer este `STATUS.md`
2. leer `IMPLEMENTATION_PLAN.md`
3. leer `HANDOFF_2026-04-19_V2.md`
4. leer `API_V1_SEMANTICS_APPENDIX.md`
5. leer `OPERATIONAL_MINIMUM_V1.md`
6. contrastar con `backend/app/contracts.py`
7. contrastar con `backend/app/services/analyze_cfdi.py`
8. contrastar con `backend/app/providers/python_satcfdi.py`
9. contrastar con `backend/app/providers/current_ts.py`
10. contrastar con `src/lib/cfdi-api-client.ts`
