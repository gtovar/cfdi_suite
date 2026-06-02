# ROADMAP MAESTRO — CFDI Suite

> Documento vivo. Actualizar en cada sesión de trabajo.
> Responde las preguntas que de otro modo toman 30 minutos de análisis.

---

## Estado actual — 2026-06-02

### Stack
- **Frontend:** React + TypeScript + Vite + TanStack Table + Tailwind (Tailux)
- **Backend:** FastAPI Python con `python-satcfdi` como provider principal, `current-ts` como fallback
- **Motor activo:** Python wrapper + TypeScript para validación matemática
- **Contrato HTTP:** v1 cerrado en `backend/app/contracts.py`

### Contratos internos de diseño

**Sentinel de catálogo inválido:** La cadena `"No existe en el catálogo"` es el valor que el wrapper Python emite en `claveProdServDescripcion` cuando satcfdi reconoce el campo pero no encuentra el código en su base de datos. `analyze_cfdi.py → _collect_catalog_findings()` detecta ese valor para generar el finding. Este patrón debe seguirse para todos los catálogos futuros que se agreguen (usoCFDI, metodoPago, formaPago, etc.).

### Lo que funciona hoy
| Capacidad | Dónde vive | Estado |
|---|---|---|
| Parsing XML CFDI (ingreso y pagos) | Python wrapper + TS fallback | ✅ |
| Validación matemática (subtotal, total, impuestos por línea) | TypeScript (`cfdiAnalysisService.ts`) | ✅ |
| Findings contextuales con correctionSteps | Frontend (`useFindingContexts.ts`) | ✅ |
| Auditoría de impuestos agrupados | TypeScript (`cfdiAnalysisService.ts`) | ✅ |
| Extracción a tabla (ingresos / pagos) | Python wrapper + TS | ✅ |
| Validación catálogo `claveProdServ` | TypeScript parcial | ✅ parcial |
| Validación catálogos `usoCFDI`, `metodoPago`, `formaPago`, `moneda` | Python wrapper + backend | ✅ (pertenencia al catálogo) |
| Validación de RFC (formato) | Frontend + API SAT | ✅ |
| Consulta estado SAT (vigente/cancelado) | Frontend → API SAT | ✅ |
| XmlNodeViewer (árbol de nodos con edición sugerida) | Frontend | ✅ |
| Findings sidebar con `differenceLabel` para descuadres | Frontend | ✅ |
| XML → PDF Engine A (layout SAT exacto via Playwright) | `backend/app/routers/pdf.py` | ✅ ~16s para 15k conceptos |
| XML → PDF Engine B (layout personalizable via ReportLab) | `backend/app/services/pdf_reportlab.py` | ✅ ~7s para 15k conceptos, <1s normal |

### Lo que NO existe todavía
- Validación XSD/estructura XML contra esquemas oficiales
- Contabilidad electrónica / DIOT
- Soporte completo de complementos (nómina, carta porte, comercio exterior)
- Verificación sello del PAC/SAT (TimbreFiscalDigital) — requiere conexión SAT; fuera de alcance offline
- PDF Engine B: builder visual de templates (V2 — logo, zonas drag-and-drop, campos configurables por empresa)

---

## Mapa honesto: nuestra app vs. satcfdi

| Capacidad | Nuestra app | python-satcfdi | Veredicto |
|---|---|---|---|
| Validación matemática (subtotal, total, impuestos) | ✅ TypeScript | ❌ no implementado en wrapper | **Solo en nuestra app** |
| Findings contextuales con correctionSteps | ✅ | ❌ | **Solo en nuestra app** |
| Extracción a tabla CSV/Excel | ✅ | ❌ | **Solo en nuestra app** |
| Catálogo `claveProdServ` | ✅ parcial | ✅ completo y actualizado | **Superconjunto satcfdi** |
| Catálogos usoCFDI, metodoPago, formaPago, moneda | ✅ pertenencia | ✅ | **Implementado via wrapper** |
| Catálogo claveUnidad | ✅ pertenencia | ✅ | **Implementado via wrapper** |
| Validación XSD / estructura XML | ❌ | ✅ `transform` module | **Solo en satcfdi — agregar** |
| Verificación firma digital (sello emisor) | ✅ offline | ✅ | **Implementado via wrapper** |
| Validación RFC formato | ✅ | ✅ `models/rfc` | **Probablemente duplicado — unificar** |
| Consulta estado SAT | ✅ | ✅ `portal` | **Duplicado — mantener el nuestro** |
| Render CFDI como tabla HTML semántica | ❌ (árbol XML) | ✅ `py2html` | **Diferente — base para PDF** |
| Contabilidad electrónica / DIOT | ❌ | ✅ `accounting` + `diot` | **Solo en satcfdi — flujo diferente** |
| Soporte CFDI 3.2, 3.3, 4.0 + complementos | parcial | ✅ | **Superconjunto satcfdi** |

**Regla:** Antes de implementar algo en TypeScript, verificar si satcfdi ya lo tiene. Si lo tiene, implementarlo en el wrapper Python y consumirlo desde el frontend. No duplicar lógica de dominio fiscal.

---

## Backlog priorizado

### ✅ Frente A — Findings desde backend Python: catálogos (completado 2026-06-01)

### ✅ Frente B-ext — Ampliar catálogos de cabecera (completado 2026-06-01)
**Qué se hizo:** Se extendió el patrón sentinel de `claveProdServ` a `usoCFDI`, `metodoPago`, `formaPago` y `moneda`.

**Contrato:** El wrapper emite `"No existe en el catálogo"` en el campo `*Descripcion` cuando satcfdi devuelve `description=None`. El backend detecta el sentinel en `_collect_catalog_findings`. El frontend maneja los IDs `catalog-uso-cfdi-*`, `catalog-metodo-pago-*`, `catalog-forma-pago-*`, `catalog-moneda-*`.

**Alcance:** Valida pertenencia al catálogo (el código existe), NO validez contextual (p. ej. usoCFDI válido para el régimen del receptor). Valida solo a nivel header; `FormaDePagoP` del complemento Pagos queda pendiente.

**Tests:** 120 pasando.

---
**Por qué primero:** El wrapper Python ya extrae `claveProdServ`, `usoCFDI`, `metodoPago`, `formaPago`, `moneda` pero no valida ninguno. satcfdi tiene catálogos completos. El canal de findings ya existe en el frontend.

**Archivos:**
- `src/cfdi/engine/python-satcfdi-wrapper.py` — agregar validación via `satcfdi.catalogs`
- `backend/app/services/analyze_cfdi.py` — reemplazar placeholders de `verdict`/`supportText` (líneas 289-294)
- `backend/app/providers/python_satcfdi.py` — flag `findingsImplemented` en línea 114
- `src/app/hooks/useFindingContexts.ts` — ya tiene handler `catalog-clave-prod-serv-*`, extender para otros catálogos

**Qué NO tocar:** `cfdiAnalysisService.ts` (validación matemática en TypeScript) — no hay equivalente Python todavía.

**Verificación:** POST `/api/cfdi/analyze` con CFDI con `claveProdServ` inválida → finding `catalog-*` aparece en sidebar con correctionSteps.

---

### ✅ Frente B — Verificación de firma digital (completado 2026-06-01)

**Qué se implementó:** Verificación offline del sello del emisor (atributo `Sello` del `cfdi:Comprobante`) usando `Certificate.verify_sha256()` y `verify_certificate()` de satcfdi con certificados raíz del SAT incluidos en la librería (`CertsProd.zip`).

**Alcance:** Solo sello del emisor. El `TimbreFiscalDigital` (sello del PAC/SAT) requiere conexión SAT → fuera de alcance.

**Resultado para CFDIs UAT/pruebas:** `certificadoSAT: false` (cert de pruebas no está en producción), `selloFirma: true` (firma válida). **Status: `invalid`** — comportamiento correcto.

**Archivos modificados:**
- `src/cfdi/engine/python-satcfdi-wrapper.py` — `verify_sello(cfdi)` + `"selloVerificacion"` en `build_cfdi_payload`
- `backend/app/services/analyze_cfdi.py` — `_collect_sello_findings(source)` + llamada en `_normalize_cfdi`
- `src/app/hooks/useFindingContexts.ts` — handler para findings `firma-*`

**Tests:** 120 pasando al cierre (17 nuevos de sello + 12 de claveUnidad).

---

### ✅ Frente C — XML → PDF dual-engine (completado 2026-06-02)

**Arquitectura dual-engine:**
```
POST /api/cfdi/pdf/start
  engine = "playwright"   → Engine A: layout SAT exacto (lento, fidelidad máxima)
  engine = "reportlab"    → Engine B: layout personalizable (rápido, feature estrella)
  template = <JSON>       → config de Engine B: primary_color, logo_url, show_columns, footer_note
```
UI: botón partido **"PDF | ⚡ PDF Pro"** en `InspectorHeader`.

**Engine A — Playwright (backup / PDF oficial):**
- `satcfdi.render.html_str()` → Playwright/Chromium con pipeline html→render
- CHUNK_SIZE=1500, MAX_PARALLEL_PAGES=4, merge con pypdf
- **~16s** para 15k conceptos. Límite real del approach Playwright+Chromium.
- Hallazgo clave: page.pdf() es el cuello (73%), no set_content(). Más workers empeoran (contención CPU).

**Engine B — ReportLab (feature estrella):**
- Genera PDF directamente desde el objeto CFDI, sin HTML ni browser
- Layout: header (logo+color), emisor/receptor, conceptos paginados, impuestos, totales, QR SAT verificable
- Tablas pre-chunked (55 filas/chunk) para evitar paginación interna lenta de ReportLab
- **~7s** para 15k conceptos, **<1s** para CFDIs normales (<500 conceptos)
- Configurable: `primary_color` (hex), `logo_url` (URL o base64), `show_columns`, `footer_note`

**Benchmarks definitivos (MINISO 6.6MB / 15,404 conceptos):**
| Motor | Tiempo total | Notas |
|---|---|---|
| Playwright original | ~20-25s | Sin pipeline |
| Playwright + pipeline | ~16s | Commit `6cd2b8c` |
| **ReportLab** | **~7s** | Sin chunking, sin browser |

**Próximo paso natural — Engine B V2:**
- Builder visual de templates: el usuario configura logo, color, qué campos mostrar, qué columnas en conceptos
- Guardar templates por empresa (requiere auth/multi-tenant)
- Posible: exportar template como JSON que el usuario puede compartir

**Archivos clave:**
- `backend/app/routers/pdf.py` — router dual-engine, SSE jobs, endpoint `/status`
- `backend/app/services/pdf_reportlab.py` — motor ReportLab completo
- `src/components/InspectorHeader.tsx` — botón partido PDF | ⚡ PDF Pro
- `src/App.tsx` — `handleDownloadPdf(engine)` con parámetro

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
| 2026-06-02 | Playwright es herramienta de testing, no motor de producción PDF — no escala con workers | Benchmark exhaustivo; migrar features a Engine B (ReportLab) |
| 2026-06-02 | Dual-engine: Playwright para fidelidad SAT, ReportLab para feature estrella personalizable | ReportLab genera desde datos, sin HTML, sin browser; 2.3× más rápido |
| 2026-06-02 | Engine B V2 = builder visual de templates, no HTML libre — modelo de zonas estructuradas | HTML libre regresa a tiempos Playwright; zonas estructuradas mantienen velocidad |

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
| 2026-06-01 | Frente A: fix wrapper Python para emitir sentinel "No existe en el catálogo" en claveProdServ inválida | `38989e8` |
| 2026-06-01 | Frente B-ext: ampliar catálogos de cabecera (usoCFDI, metodoPago, formaPago, moneda) via sentinel pattern | `1148e08` |
| 2026-06-01 | claveUnidad + sello offline: catálogo en conceptos, verificación criptográfica offline, handlers frontend, 29 tests nuevos | `b36576b` |
| 2026-06-01 | Frente C: PDF con SSE progress, Playwright+chunking paralelo, lxml header-fix. ~20-25s para 6.6MB | `696d9af`→`a319e40` |
| 2026-06-02 | Frente C optimización: benchmark por fase, pipeline html→render, endpoint /status. 18.6s→16.2s | `6cd2b8c` |
| 2026-06-02 | Engine B ReportLab: dual-engine PDF, layout personalizable, QR SAT. 7.2s para 15k conceptos | `138c761` |

---

## Reentrada mínima para nueva sesión

Leer en este orden:
1. Este archivo (`docs/ROADMAP_MAESTRO.md`) — estado y prioridades
2. `docs/roadmap/python-backend-platform/STATUS.md` — estado del backend
3. `backend/app/contracts.py` — contrato HTTP v1
4. `src/cfdi/engine/python-satcfdi-wrapper.py` — estado del wrapper Python

Si se va a tocar PDF Engine B: leer `backend/app/services/pdf_reportlab.py` y `backend/app/routers/pdf.py`.
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
