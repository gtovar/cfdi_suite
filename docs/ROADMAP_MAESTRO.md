# ROADMAP MAESTRO — CFDI Suite

> Documento vivo. Actualizar en cada sesión de trabajo.
> Responde las preguntas que de otro modo toman 30 minutos de análisis.

---

## Estado actual — 2026-06-01

### Stack
- **Frontend:** React + TypeScript + Vite + TanStack Table + Tailwind (Tailux)
- **Backend:** FastAPI Python con `python-satcfdi` como provider principal, `current-ts` como fallback
- **Motor activo:** TypeScript (`current-ts`) vía backend; el wrapper Python extrae estructura pero no genera findings
- **Contrato HTTP:** v1 cerrado en `backend/app/contracts.py`

### Lo que funciona hoy
| Capacidad | Dónde vive | Estado |
|---|---|---|
| Parsing XML CFDI (ingreso y pagos) | Python wrapper + TS fallback | ✅ |
| Validación matemática (subtotal, total, impuestos por línea) | TypeScript (`cfdiAnalysisService.ts`) | ✅ |
| Findings contextuales con correctionSteps | Frontend (`useFindingContexts.ts`) | ✅ |
| Auditoría de impuestos agrupados | TypeScript (`cfdiAnalysisService.ts`) | ✅ |
| Extracción a tabla (ingresos / pagos) | Python wrapper + TS | ✅ |
| Validación catálogo `claveProdServ` | TypeScript parcial | ✅ parcial |
| Validación de RFC (formato) | Frontend + API SAT | ✅ |
| Consulta estado SAT (vigente/cancelado) | Frontend → API SAT | ✅ |
| XmlNodeViewer (árbol de nodos con edición sugerida) | Frontend | ✅ |
| Findings sidebar con `differenceLabel` para descuadres | Frontend | ✅ |

### Lo que NO existe todavía
- Validación de catálogos completos (usoCFDI, metodoPago, formaPago, moneda, claveUnidad)
- Verificación criptográfica de firma digital (sello SAT/PAC)
- Validación XSD/estructura XML contra esquemas oficiales
- Findings desde el backend Python (siempre llegan vacíos)
- XML → PDF / render del comprobante
- Contabilidad electrónica / DIOT
- Soporte completo de complementos (nómina, carta porte, comercio exterior)

---

## Mapa honesto: nuestra app vs. satcfdi

| Capacidad | Nuestra app | python-satcfdi | Veredicto |
|---|---|---|---|
| Validación matemática (subtotal, total, impuestos) | ✅ TypeScript | ❌ no implementado en wrapper | **Solo en nuestra app** |
| Findings contextuales con correctionSteps | ✅ | ❌ | **Solo en nuestra app** |
| Extracción a tabla CSV/Excel | ✅ | ❌ | **Solo en nuestra app** |
| Catálogo `claveProdServ` | ✅ parcial | ✅ completo y actualizado | **Superconjunto satcfdi** |
| Catálogos usoCFDI, metodoPago, formaPago, moneda, claveUnidad | ❌ | ✅ | **Solo en satcfdi — agregar** |
| Validación XSD / estructura XML | ❌ | ✅ `transform` module | **Solo en satcfdi — agregar** |
| Verificación firma digital (sello SAT/PAC) | ❌ | ✅ `cfdi.verifica_url` / `sign` | **Solo en satcfdi — evaluar** |
| Validación RFC formato | ✅ | ✅ `models/rfc` | **Probablemente duplicado — unificar** |
| Consulta estado SAT | ✅ | ✅ `portal` | **Duplicado — mantener el nuestro** |
| Render CFDI como tabla HTML semántica | ❌ (árbol XML) | ✅ `py2html` | **Diferente — base para PDF** |
| Contabilidad electrónica / DIOT | ❌ | ✅ `accounting` + `diot` | **Solo en satcfdi — flujo diferente** |
| Soporte CFDI 3.2, 3.3, 4.0 + complementos | parcial | ✅ | **Superconjunto satcfdi** |

**Regla:** Antes de implementar algo en TypeScript, verificar si satcfdi ya lo tiene. Si lo tiene, implementarlo en el wrapper Python y consumirlo desde el frontend. No duplicar lógica de dominio fiscal.

---

## Backlog priorizado

### 🔴 Frente A — Findings desde backend Python: catálogos (deuda activa ~34 días)
**Por qué primero:** El wrapper Python ya extrae `claveProdServ`, `usoCFDI`, `metodoPago`, `formaPago`, `moneda` pero no valida ninguno. satcfdi tiene catálogos completos. El canal de findings ya existe en el frontend.

**Archivos:**
- `src/cfdi/engine/python-satcfdi-wrapper.py` — agregar validación via `satcfdi.catalogs`
- `backend/app/services/analyze_cfdi.py` — reemplazar placeholders de `verdict`/`supportText` (líneas 289-294)
- `backend/app/providers/python_satcfdi.py` — flag `findingsImplemented` en línea 114
- `src/app/hooks/useFindingContexts.ts` — ya tiene handler `catalog-clave-prod-serv-*`, extender para otros catálogos

**Qué NO tocar:** `cfdiAnalysisService.ts` (validación matemática en TypeScript) — no hay equivalente Python todavía.

**Verificación:** POST `/api/cfdi/analyze` con CFDI con `claveProdServ` inválida → finding `catalog-*` aparece en sidebar con correctionSteps.

---

### 🟡 Frente B — Verificación de firma digital
**Por qué segundo:** Alto valor para perfil técnico (Diverza/PAC). Capacidad completamente ausente en nuestra app.

**Precondición:** Verificar si `satcfdi.transform` puede verificar firma offline (sin credenciales SAT). Si requiere conexión SAT activa → es un flujo diferente con auth, no aplica al inspector sin login.

**Archivos (si es offline):**
- `src/cfdi/engine/python-satcfdi-wrapper.py` — llamada a verificación de sello
- `src/app/hooks/useFindingContexts.ts` — handler para findings `firma-*`

---

### 🟡 Frente C — XML → PDF (exploración primero)
**Qué es:** satcfdi tiene `py2html` que renderiza CFDI como tabla HTML semántica. Base potencial para flujo XML → PDF con layouts personalizables.

**Esto NO es extensión del inspector — es un segundo flujo** dentro de la app.

**Experimento mínimo antes de planear:**
1. Llamar `satcfdi.models.py2html.dumps()` con un CFDI real
2. Ver si el HTML contiene emisor, receptor, UUID, conceptos y totales de forma legible
3. Decidir: ¿es base viable para PDF con CSS encima, o necesitamos renderer propio?

**Criterio go/no-go:** HTML generado es semántico y legible sin post-procesamiento.

---

### 🟢 Frente D — Validación XSD / estructura XML
**Por qué después:** Menor urgencia que catálogos. Detecta errores de estructura que los PACs ya deberían rechazar.

**Implementación:** `satcfdi.transform` con esquemas XSD oficiales SAT vía wrapper Python.

---

### 🟢 Frente E — DIOT / Contabilidad electrónica
**Por qué al final:** Flujo completamente nuevo, no extensión del inspector. Requiere procesar múltiples CFDIs en batch. Alta complejidad UX. Candidato a sección separada de la app.

---

## Decision Log

| Fecha | Decisión | Contexto |
|---|---|---|
| 2026-04-17 | python-satcfdi como motor de dominio, cfdi_inspector como producto UX-first | Ver `docs/analysis/2026-04-17-python-satcfdi-decision.md` |
| 2026-04-18 | Backend FastAPI como capa entre frontend y python-satcfdi | Ver `docs/analysis/2026-04-18-python-backend-platform-decision.md` |
| 2026-04-19 | Contrato HTTP v1 cerrado; fallback `current-ts` en backend | Ver `docs/roadmap/python-backend-platform/HANDOFF_2026-04-19_V2.md` |
| 2026-04-27 | Sesión C: fallback local frontend removido | Commit `7292a44` |
| 2026-06-01 | `FinancialSummaryCard` eliminado; validación matemática solo via findings | Commit `7463296` — duplicación arquitectónica resuelta |
| 2026-06-01 | Catálogos completos: delegar a satcfdi/backend, no reimplementar en TypeScript | Decisión de esta sesión — ver `docs/ROADMAP_MAESTRO.md` |

---

## Bitácora de sesiones

| Fecha | Qué se hizo | Commits |
|---|---|---|
| ~2026-01-xx | Adoptar TanStack Table como motor de grilla | `80d6888` |
| ~2026-04-xx | Refactor App.tsx: extraer hooks `useDiagnoseState`, `useFindingContexts` | `d2a6f98` |
| ~2026-04-xx | Introducir backend FastAPI + contrato multi-motor Python/TS | `a585766` |
| 2026-04-27 | Sesión C: remover fallback local del frontend | `7292a44` |
| ~2026-05-xx | Rediseño visual inspector con Tailux | `bd40ab3` |
| ~2026-05-xx | Mover pills de columnas a dropdown en toolbar | `1b8b49d` |
| ~2026-05-xx | XmlNodeViewer con virtual scroll para XMLs pesados | `48d127d` |
| 2026-06-01 | Eliminar `FinancialSummaryCard`; integrar `differenceLabel` en findings globales | `7463296` |
| 2026-06-01 | Análisis satcfdi vs nuestra app; definir roadmap maestro; priorizar catálogos como Frente A | este doc |

---

## Reentrada mínima para nueva sesión

Leer en este orden:
1. Este archivo (`docs/ROADMAP_MAESTRO.md`) — estado y prioridades
2. `docs/roadmap/python-backend-platform/STATUS.md` — estado del backend
3. `backend/app/contracts.py` — contrato HTTP v1
4. `src/cfdi/engine/python-satcfdi-wrapper.py` — estado del wrapper Python

Si se va a tocar findings: leer también `src/cfdi/application/cfdiAnalysisAdapter.ts` y `src/app/hooks/useFindingContexts.ts`.

---

## Arquitectura en una línea

```
XML → Frontend → POST /api/cfdi/analyze → Backend FastAPI
                                          ├─ python-satcfdi (provider primario)
                                          └─ current-ts TypeScript (fallback)
                                          → cfdi.findings → FindingsSidebar
```

Ver `docs/arquitectura.md` para el detalle completo de capas.
