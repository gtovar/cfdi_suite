# React-doctor — Veredictos por familia de hallazgos

Este documento es la fuente de verdad sobre qué hacemos con cada hallazgo de
react-doctor y **por qué**. La regla central: **no se arregla nada a ciegas**.
Cada familia (regla) recibe un veredicto razonado después de leer el código
señalado, como si tuviéramos que justificar el estado actual ante un auditor.

## Baseline congelada

- **Fecha**: 2026-07-13, sobre el commit `e2938ab` (working tree limpio)
- **Herramienta**: react-doctor 0.7.1 (fijada en `frontend/package.json`)
- **Comando**: `npx react-doctor --verbose` (scope full) desde `frontend/`
- **Score**: 34/100 ("Critical" según la herramienta — ver nota abajo)
- **Total**: 840 hallazgos en 53 reglas — Seguridad 5 · Bugs 8 errores + 267
  warnings · Performance 65 · Accesibilidad 313 · Mantenibilidad 182
- El mismo escaneo corrió dos veces (antes y después del rediseño de
  `watchBatchProgress`) con resultado idéntico: la baseline es estable.

**Nota sobre el score**: es un número del vendor, con sus pesos. Sirve como
tendencia entre corridas de la *misma versión*, no como objetivo. Perseguir el
score deshabilitando reglas sin veredicto es falsificar el reporte.

**Qué significa "baseline congelada"**: todo lo listado aquí es deuda conocida
con dueño (este doc). No bloquea trabajo nuevo. Lo *nuevo* se controla con
`npx react-doctor --scope changed`, que solo reporta lo introducido contra la
rama base — así "es preexistente" deja de ser excusa y se vuelve verificable.

## Los cuatro veredictos

| Veredicto | Significado | Acción que dispara |
|---|---|---|
| `tiene-razon-de-ser` | El código es así a propósito; se puede defender | Justificación aquí + supresión puntual en `doctor.config` para limpiar el score |
| `error-real` | La herramienta tiene razón; hay que corregir | Fix (no necesariamente el que la herramienta sugiere) + tests |
| `mejorable` | Ni error ni intocable; se ajusta cuando toque | Anotar la mejora; se agenda, no urge |
| `falso-positivo` | La regla malinterpretó el código | Evidencia aquí + supresión puntual en config; considerar reportar upstream |

Un veredicto se emite **por regla** (53 familias), no por hallazgo (840). Si
dentro de una familia hay casos mixtos, se parte el veredicto por archivo y se
anota cada parte.

## Política de código no usado (deslop/unused-*) — NUNCA borrar por defecto

Contexto: ya nos pasó que métodos "sin uso" que estuvieron a punto de borrarse
resultaron ser exactamente lo que una feature posterior necesitaba.

Para `unused-file` (19), `unused-export` (5) y `unused-dependency` (5):

1. **Investigar propósito** antes de cualquier veredicto: `git log` del
   archivo, quién lo importó alguna vez, si pertenece a una feature en
   desarrollo (p. ej. el módulo `editor/`), si es alcanzable por vías que el
   análisis estático no ve (imports dinámicos, workers, rutas).
2. Clasificar con evidencia: `feature-en-desarrollo` / `alcanzable-indirecto` /
   `muerto-real`.
3. Borrar **solo** con confirmación explícita del usuario, caso por caso o en
   bloque, nunca como parte de un fix automatizado.

Esta política aplica a cualquier agente que trabaje en este repo (ver
`AGENTS.md`).

## Tabla de familias (baseline 2026-07-13)

Veredicto `pendiente` = aún sin triage. Las tres familias del piloto están
marcadas. Al emitir un veredicto: actualizar la fila y detallar en la sección
"Veredictos emitidos".

### Seguridad

| Regla | # | Sev | Veredicto | Notas |
|---|---|---|---|---|
| iframe-missing-sandbox | 3 | warning | **mejorable** | PDFs propios (blob URLs); fix requiere prueba manual en navegadores — ver §Veredictos 4 |
| postmessage-origin-risk | 1 | warning | **falso-positivo** | Es `EventSource` SSE same-origin — regla off, ver §Veredictos 2 |
| clickjacking-redirect-risk | 1 | warning | **falso-positivo** | Blob URL propio, sin redirect — regla off, ver §Veredictos 3 |

### Bugs

| Regla | # | Sev | Veredicto | Notas |
|---|---|---|---|---|
| button-has-type | 177 | warning | **error-real (parcial)** | 15 vivos corregidos; confirmado que ningún `<form>` del repo envuelve alguno de los 177 sitios → resto (85 vivos) apto para fix en bloque; 77 en cluster Editor. Ver §Veredictos 7 |
| no-event-handler | 22 | warning | **mixto** | Mayormente `tiene-razon-de-ser` (hidratación/reset legítimos); 10 de 12 hallazgos en `useExtractGridState.ts` tienen atribución de línea rota del tool (reportar upstream). Ver §Veredictos 8 |
| no-array-index-as-key | 13 | warning | **mixto** | 10 `tiene-razon-de-ser` (listas estáticas), 1 `mejorable` (InvoiceDesigner), 2 cluster. Ver §Veredictos 7 |
| exhaustive-deps | 8 | warning | **falso-positivo (mayormente)** | Todas las exclusiones ya estaban documentadas en comentarios; 3 no silencian por mismatch de nombre de linter (hallazgo preexistente nuevo). Ver §Veredictos 8 |
| no-adjust-state-on-prop-change | 8 | **error** | **falso-positivo** | Efecto de restauración mount-only blindado con ref — regla off, ver §Veredictos 1 |
| no-nested-component-definition | 1 | **error** | **error-real, propuesto (no aplicado)** | `DocumentSettings.jsx:13` — cluster Editor desconectado, fix propuesto sin aplicar. Ver §Veredictos 6, 8 |
| prefer-useReducer | 7 | warning | **mejorable** | Sugerencia estructural válida, sin refactor (archivos vivos protegidos: App.tsx, BatchAnalysisPage, ConversionMasivaPage, InvoiceDesigner). Ver §Veredictos 8 |
| no-chain-state-updates | 6 | warning | **falso-positivo** | React 19 con batching automático cubre los casos señalados. Ver §Veredictos 8 |
| no-derived-state | 5 | warning | **mixto** | Mayormente protegido/no urgente; 1 mejorable en `useExtractGridState.ts`. Ver §Veredictos 8 |
| no-initialize-state | 5 | warning | **mixto** | 1 falso-positivo (medición de DOM post-montaje, patrón sancionado), resto mejorable. Ver §Veredictos 8 |
| no-fetch-in-effect | 5 | warning | **error-real (1), corregido** | Race condition real en `InvoiceDesigner.jsx` (cambio rápido de plantilla) corregida con guard `cancelled`. Ver §Veredictos 8 |
| no-pass-live-state-to-parent | 4 | warning | **mejorable** | Patrón "propagar progreso a App.tsx"; mejora propuesta sin aplicar (archivos protegidos). Ver §Veredictos 8 |
| no-prop-callback-in-effect | 4 | warning | **mejorable** | Mismo hallazgo que la fila anterior (dos reglas, mismo código). Ver §Veredictos 8 |
| no-cascading-set-state | 2 | warning | **falso-positivo** | Batching de React 19. Ver §Veredictos 8 |
| no-pass-data-to-parent | 2 | warning | **mejorable** | Mismo patrón de propagación de progreso. Ver §Veredictos 8 |
| no-unknown-property | 2 | warning | **en-codigo-desconectado** | Sintaxis `styled-jsx` inválida, ambos en cluster Editor. Ver §Veredictos 7 |
| no-effect-chain | 1 | warning | **falso-positivo** | Mismo efecto de preflight ya analizado en no-chain-state-updates. Ver §Veredictos 8 |
| html-no-nested-interactive | 1 | warning | **error-real, corregido** | `<button>` anidado dentro de otro `<button>` en `FloatingBatchWidget.tsx` (componente vivo, 3 pantallas) — HTML inválido, reestructurado. Ver §Veredictos 7 |
| prefer-use-effect-event | 1 | warning | **tiene-razon-de-ser** | Único caso en cluster Editor desconectado, no aplica. Ver §Veredictos 8 |
| no-unstable-nested-components | 1 | **error** | **error-real, propuesto (no aplicado)** | Nueva regla detectada durante la escalada, mismo root-cause que no-nested-component-definition (`DocumentSettings.jsx:13`). Ver §Veredictos 8 |

### Performance

| Regla | # | Sev | Veredicto | Notas |
|---|---|---|---|---|
| no-transition-all | 25 | warning | **mejorable/diseño** | 3 vivos en InvoiceDesigner (efecto visual intencional), 22 cluster. Tag "design" no existe en el rule set (es `test-noise`) — no se suprimió. Ver §Veredictos 9 |
| js-combine-iterations | 15 | warning | **mejorable** | Ganancia despreciable (arrays pequeños o en handlers, no en loop caliente); riesgo de tocar código de cálculo fiscal. Ver §Veredictos 9 |
| rerender-state-only-in-handlers | 6 | warning | **error-real (4), corregido** | `useState`→`useRef` en 4 sitios (BatchAnalysisPage, ConsultasSATPage, EmisoresPage); 1 no tocado por ser dead code entrelazado. Ver §Veredictos 9 |
| no-inline-bounce-easing | 3 | warning | **en-codigo-desconectado** | 100% cluster Editor. |
| no-json-parse-stringify-clone | 3 | warning | **en-codigo-desconectado** | 100% `PropertiesPanel.jsx` (cluster Editor, confirmado). |
| js-flatmap-filter | 2 | warning | **mejorable** | Arrays acotados en handlers, no en render caliente. Ver §Veredictos 9 |
| use-lazy-motion | 2 | warning | **mejorable** | Requiere refactor coordinado con `main.tsx` (MotionConfig global) para que el fix sirva. Ver §Veredictos 9 |
| no-long-transition-duration | 2 | warning | **tiene-razon-de-ser** | Animación de "flash de atención" deliberada en `XmlNodeViewer.tsx`. Ver §Veredictos 9 |
| async-parallel | 1 | warning | **falso-positivo** | Pipeline start→poll→download con awaits dependientes, no paralelizable — regla off. Ver §Veredictos 9 |
| no-usememo-simple-expression | 1 | warning | **error-real, corregido** | `useMemo` sin cómputo real en `useExtractGridState.ts`. Ver §Veredictos 9 |
| rerender-lazy-ref-init | 1 | warning | **mejorable** | Ganancia despreciable, fix empeora tipos. Ver §Veredictos 9 |
| no-layout-transition-inline | 1 | warning | **mejorable** | Requiere reestructurar a `transform:scaleX`, más invasivo que el beneficio. Ver §Veredictos 9 |
| rerender-memo-with-default-value | 1 | warning | **en-codigo-desconectado** | Cluster Editor. |
| async-defer-await | 1 | warning | **error-real, corregido** | `pdf-download.ts:220` — veredicto definitivo (no era falso positivo como se sospechaba): el 429 no usaba el body. Ver §Veredictos 9 |
| rendering-hydration-no-flicker | 1 | warning | **en-codigo-desconectado** | Cluster Editor. |

### Accesibilidad

| Regla | # | Sev | Veredicto | Notas |
|---|---|---|---|---|
| control-has-associated-label | ~86 vivo/38 cluster | warning | **error-real (parcial), corregido** | 9 sitios fijos (aria-label en checkboxes/inputs icon-only); falso-positivo sistemático detectado en spacers de tablas virtualizadas (no tocado, correcto); ~39 vivos restantes con receta ya validada, sin escalar. Ver §Veredictos 10 |
| no-tiny-text | 43 vivo/29 cluster | warning | **mejorable, no aplicado** | Requiere QA visual en navegador (43 sitios en InvoiceDesigner, toolbar denso); riesgo de romper layout compacto. Ver §Veredictos 10 |
| label-has-associated-control | ~73 vivo/8 cluster | warning | **error-real (parcial), corregido** | Mismo fix que control-has-associated-label (pares label+input comparten hallazgo). Ver §Veredictos 10 |
| no-static-element-interactions | 7 vivo/6 cluster | warning | **error-real (parcial), corregido** | 3 sitios fijos (role+tabIndex+onKeyDown); 4 backdrops de modal quedan `mejorable` (afordancia de cierre por teclado). Ver §Veredictos 10 |
| click-events-have-key-events | 6 vivo/4 cluster | warning | **error-real (parcial), corregido** | Mismos 3 sitios que la fila anterior. Ver §Veredictos 10 |
| no-outline-none | 5 vivo/2 cluster | warning | **error-real, corregido** | 5 inputs de InvoiceDesigner sin alternativa de foco — removido `outline:none`, restaurado outline nativo. Ver §Veredictos 10 |
| no-autofocus | 1 | warning | **mejorable, no aplicado** | El problema real es la falta de un componente Modal accesible completo — decisión de arquitectura, fuera de alcance. Ver §Veredictos 10 |
| prefer-tag-over-role | 2 (nueva) | warning | **tiene-razon-de-ser** | Apareció por los propios fixes de a11y; los `div role="button"` envuelven contenido rico que no cabe en un `<button>` real — patrón WAI-ARIA APG correcto. Propuesta de supresión puntual pendiente de tu decisión (no aplicada). Ver §Veredictos 10 |

### Mantenibilidad

| Regla | # | Sev | Veredicto | Notas |
|---|---|---|---|---|
| no-inline-exhaustive-style | 121 | warning | pendiente | |
| unused-file | 19 | warning | **clasificado** | 14 = feature Editor pausada (conservar); 1 = usado por el BACKEND (`current-ts-wrapper.ts`, nunca borrar); 4 = candidatos a borrar pendientes de confirmación del usuario — ver §Veredictos 5 |
| no-giant-component | 10 | warning | pendiente | |
| prefer-module-scope-static-value | 10 | warning | pendiente | |
| prefer-module-scope-pure-function | 8 | warning | pendiente | |
| unused-dependency | 5 | warning | pendiente | **Política de código no usado aplica** — `@dnd-kit/*` ×3, `dotenv`, +1 |
| unused-export | 5 | warning | pendiente | **Política de código no usado aplica** |
| only-export-components | 2 | warning | pendiente | |
| no-many-boolean-props | 1 | warning | pendiente | |
| no-render-in-render | 1 | warning | pendiente | |

## Actualización post-piloto (2026-07-13)

Tras el piloto, el escaneo cambió a **36/100 con 921 hallazgos**. No es una
regresión: al corregir el error de sintaxis de `DocumentSettings.jsx` (que
impedía parsearlo), react-doctor pudo analizar por fin ese archivo y le
encontró ~91 hallazgos que estaban **invisibles** (+54 accesibilidad, +23
mantenibilidad, +6 performance, +1 error nuevo anotado abajo). A la vez, las
3 supresiones por falso positivo quitaron 10. Lección registrada: un archivo
que no parsea es un punto ciego del escáner, no un archivo limpio.

## Veredictos emitidos

### 1. `no-adjust-state-on-prop-change` — **falso-positivo** (2026-07-13)

- **Evidencia**: los 8 errores señalan `ConversionMasivaPage.tsx:248-272`,
  dentro del efecto de restauración (líneas 243-288) blindado con
  `restoredBatchRef` (`:244-245`): corre exactamente una vez, en el montaje.
  Es hidratación desde `?batch=` / `localStorage` + arranque de suscripciones
  asíncronas (`fetchReadyFileIds`, `listenToBatch`) — trabajo que DEBE vivir
  en un efecto. No es "ajustar estado cuando cambia un prop": si
  `restoreBatchId` cambiara después, el guard hace return inmediato.
- **Acción**: regla `off` en `doctor.config.ts`. Reactivar si aparece código
  nuevo con estado derivado de props de verdad.

### 2. `postmessage-origin-risk` — **falso-positivo** (2026-07-13)

- **Evidencia**: `App.tsx:267` es `es.onmessage` de un `EventSource` sobre
  `/api/cfdi/pdf/<jobId>/progress` (same-origin, URL relativa). La regla
  apunta a handlers de `window.postMessage` entre ventanas/iframes hostiles;
  un stream SSE de nuestro propio backend no tiene ese modelo de amenaza.
- **Acción**: regla `off` en `doctor.config.ts`. Reactivar si se agrega
  mensajería cross-window real.

### 3. `clickjacking-redirect-risk` — **falso-positivo** (2026-07-13)

- **Evidencia**: `PdfTemplateBuilder.tsx:432` es el iframe de preview cuyo
  `src` es un blob URL creado por nosotros (`URL.createObjectURL(blob)` en
  `:112` tras fetch a nuestra API). No hay redirect, no hay URL controlable
  por un atacante, no es UI privilegiada enmarcable.
- **Acción**: regla `off` en `doctor.config.ts`.

### 4. `iframe-missing-sandbox` — **mejorable** (2026-07-13)

- **Evidencia**: los 3 iframes (`InvoiceDesigner.jsx:1109`,
  `PdfPreview.jsx:348`, `PdfTemplateBuilder.tsx:432`) embeben PDFs generados
  por nuestro backend vía blob URLs — no páginas de terceros. El riesgo que
  la regla ataca (página embebida hostil con acceso total) es mínimo aquí.
- **Por qué no se arregló a ciegas**: agregar `sandbox` a un iframe que
  muestra PDF puede romper el visor nativo según navegador. Requiere prueba
  manual (Chrome/Firefox/Safari) antes de aplicarse.
- **Acción**: la regla queda ACTIVA (es defensa en profundidad legítima); el
  fix se agenda como tarea con verificación manual en navegador. Nota:
  `PdfPreview.jsx` está en el cluster Editor desconectado — si ese cluster se
  archiva, solo quedan 2 sitios.

### 5. `deslop/unused-file` (19 archivos) — **clasificación, cero borrados** (2026-07-13)

| Grupo | Archivos | Clasificación | Evidencia |
|---|---|---|---|
| Cluster Editor (14) | `pages/Editor.jsx` + `editor/*` (8) + `shortcut/*` (2) + `Toast.jsx`, `PdfPreview.jsx`, `HtmlTemplateEditor.jsx` | `feature-en-desarrollo` (pausada/desconectada) | `Editor.jsx` estuvo ruteado desde App.tsx (commits `386372d`, `6200d16`) — es el editor visual de plantillas de la era canvas_pipeline. Todos los demás archivos del grupo son alcanzables desde él. **Conservar.** |
| `PdfTemplateDesigner.jsx` | 1 | `probable-reemplazado` | Desconectado en `7129d01` (migración PDF async); `PdfTemplateBuilder.tsx` (vivo) cumple ese rol hoy. Decisión de borrado: usuario. |
| `cfdi/engine/current-ts-wrapper.ts` | 1 | **`alcanzable-indirecto` — NUNCA borrar por análisis estático** | Lo invoca el **backend** como subproceso: `backend/app/providers/current_ts.py:19,34` (`node --import tsx <wrapper>`). Invisible para el grafo de imports del frontend. Además se descubrió que la ruta del backend quedó ROTA (ver preexistentes). |
| `lib/cfdi-worker-client.ts` + `lib/cfdi-worker.ts` | 2 | `desconectado-histórico` | Cadena de análisis CFDI en Web Worker (navegador), desconectada cuando el análisis migró a la API con fallback (commits `a585766`, `ff0e64b`). Decisión de borrado: usuario. |
| `ConversionMasiva.tsx` | 1 | `suplantado` | `ConversionMasivaPage.tsx` (vivo, mismo checkpoint `386372d`) es la versión actual. El viejo siguió recibiendo ediciones de estilo hasta 2026-07-09 ("Fix ux") — riesgo activo de editar el archivo equivocado. Decisión de borrado: usuario. |

Este caso valida la política: **1 de los 19 "unused" era crítico para el
backend**. El análisis estático de frontend no puede ver subprocess spawns,
workers ni consumidores externos.

**Resolución (2026-07-13, con confirmación explícita del usuario):**
- Borrados los 4 candidatos: `ConversionMasiva.tsx`, `PdfTemplateDesigner.jsx`,
  `cfdi-worker-client.ts`, `cfdi-worker.ts` (recuperables del historial git).
  Verificado después: `tsc --noEmit` exit 0 y la suite de tests con los mismos
  6 fallos preexistentes ya documentados, cero nuevos.
- La ruta rota del backend hacia `current-ts-wrapper.ts` se corrigió
  (`current_ts.py`: `WRAPPER_PATH` y `cwd` ahora apuntan a `frontend/`) y se
  probó de punta a punta: el provider ejecuta el wrapper y devuelve
  `ProviderResult`.
- Post-borrados el escaneo queda en **36/100 con 877 hallazgos** (−44 que
  vivían en los archivos borrados).

### 6. Error TS en `DocumentSettings.jsx:295` — **error-real, corregido** (2026-07-13)

- **Evidencia**: comentario JSX `{/* pragma: allowlist secret */}` colocado en
  posición de atributo del `<textarea>` — JSX interpreta `{` ahí como spread
  (`TS1005: '...' expected`). Tumbaba `npm run lint` (tsc) de TODO el
  proyecto. Era el preexistente #1 de PROJECT_STATE.
- **Fix**: mover el pragma dentro de la expresión del `placeholder`
  (misma línea, para que detect-secrets lo siga honrando). Al desbloquear el
  parseo aparecieron 2 errores más que estaban tapados (`import.meta.env` sin
  tipos de Vite en `BatchAnalysisPage.tsx`) — se resolvieron creando el
  `src/vite-env.d.ts` canónico que el proyecto nunca tuvo.
- **Resultado**: `npx tsc --noEmit` exit 0 — lint verde por primera vez desde
  que se documentó el preexistente.
- **Anotado nuevo**: con el archivo ya parseable, react-doctor encontró 1
  error real dentro (`no-nested-component-definition`,
  `DocumentSettings.jsx:13`: `BorderControl` definido dentro de
  `PageBorderControls` pierde estado en cada render). Está en el cluster
  Editor desconectado → se arregla si/cuando el editor se reconecte, no
  urge. Queda `pendiente` en la tabla de Bugs.

## Relación con "Hallazgos preexistentes" (PROJECT_STATE.md)

- `PROJECT_STATE.md §Hallazgos preexistentes` registra lo que se encuentra
  roto *de paso* durante cualquier tarea (con evidencia, p. ej. `git stash`).
- Si el hallazgo preexistente es de react-doctor, además se refleja aquí en la
  familia correspondiente.
- La política que obliga a anotar en vez de descartar vive en `AGENTS.md`.
