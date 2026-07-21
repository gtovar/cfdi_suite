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
| button-has-type | 177 | warning | **error-real (parcial)** | Re-verificado 2026-07-21: 14 vivos corregidos (no 15, corregido el conteo); confirmado que ningún `<form>` del repo envuelve alguno de los 177 sitios → resto apto para fix en bloque cuando se retome. Ver §Veredictos 7 |
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
| no-unknown-property | 2 | warning | **en-codigo-desconectado** | Confirmado 2026-07-21: `Toast.jsx:104` y `PdfPreview.jsx:361`, ambos en la lista de cluster Editor de §Veredictos 5. Sintaxis `<style jsx>` (styled-jsx) inválida sin el plugin correspondiente — no llega a ejecutarse porque el cluster no está ruteado. |
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
| control-has-associated-label | 125 total — 39 vivo/86 cluster | warning | **error-real (parcial), corregido** | Re-verificado 2026-07-21 contra el escaneo real: la tabla original tenía vivo/cluster invertidos. 9 sitios fijos hoy (aria-label en checkboxes/inputs icon-only); ~30 vivos restantes con receta ya validada, sin escalar. Ver §Veredictos 10 |
| no-tiny-text | 68 total | warning | **mejorable, no aplicado** | Requiere QA visual en navegador (mayoría en InvoiceDesigner, toolbar denso); riesgo de romper layout compacto. Ver §Veredictos 10 |
| label-has-associated-control | 89 total — 8 vivo/81 cluster | warning | **error-real (parcial), corregido** | Re-verificado 2026-07-21: mismo error de vivo/cluster invertido que la fila anterior. Mismo fix que control-has-associated-label (pares label+input comparten hallazgo). Ver §Veredictos 10 |
| no-static-element-interactions | 17 total — 4 vivo/13 cluster | warning | **error-real (parcial), corregido** | 3 sitios fijos (role+tabIndex+onKeyDown en ConsultasSATPage, InvoiceDesigner/SectionZone, InvoiceDesigner/ToggleRow); 4 restantes (App.tsx, ExtractWorkspaceTable.tsx, InvoiceDesigner.jsx, PdfTemplateBuilder.tsx) quedan `mejorable` (backdrops de modal, afordancia de cierre por teclado). Ver §Veredictos 10 |
| click-events-have-key-events | 13 total — 3 vivo/10 cluster | warning | **error-real (parcial), corregido** | Mismos sitios que la fila anterior (par de reglas). Ver §Veredictos 10 |
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

### 7. Bugs — `button-has-type`, `no-array-index-as-key`, `html-no-nested-interactive` (2026-07-13, escalada team agents; **re-verificado y cerrado 2026-07-21**)

**Nota de proceso**: estos tres veredictos se decidieron en una escalada a
team agents (5 worktrees, uno por familia) cuya sesión coordinadora se quedó
sin contexto antes de escribir esta sección — la tabla resumen quedó llena
pero la evidencia nunca se documentó. El código sí se mezcló correctamente a
`main` (verificado archivo por archivo contra los 5 worktrees, sin pérdidas,
2026-07-21) y ya está en producción. Lo que sigue es la evidencia
re-derivada directamente del código real, no la reconstrucción de lo que el
agente pensó en su momento.

- **`button-has-type` (177, error-real parcial)**: verificado con
  `grep -c` sobre el diff real contra la baseline `e2938ab` — **14** sitios
  vivos recibieron `type="button"` explícito (`BatchCompletionModal.tsx`,
  `BatchAnalysisPage.tsx`, `ConsultasSATPage.tsx`, `ConversionMasivaPage.tsx`,
  `FloatingBatchWidget.tsx`, `ExtractWorkspaceToolbar.tsx`), no 15 como decía
  la tabla original. Ningún `<form>` del repo envuelve alguno de los 177
  sitios (confirmado con `grep -rn "<form"` cruzado contra las rutas del
  hallazgo) — sin `type="button"` explícito, un click dentro de un futuro
  `<form>` dispararía un submit no intencional; con el default de un botón
  fuera de formulario no hay riesgo funcional hoy, solo higiene preventiva.
  Resto del listado (cluster Editor + sitios vivos no tocados en esta pasada)
  queda apto para fix en bloque cuando se retome — mismo patrón mecánico, sin
  necesidad de revisar cada uno por separado.
- **`no-array-index-as-key` (13)**: verificado archivo por archivo
  (`grep -rn "key={i}\|key={idx}\|key={index}"`). 7 sitios en
  `XmlNodeViewer.tsx` (tokens de resaltado de sintaxis XML, recalculados
  completos en cada render desde un string fuente — la lista nunca se
  reordena ni se inserta/borra a mitad, key=índice es válido aquí), 1 en
  `ConceptDetailModal.tsx` y 1 en `ResolutionPanel.tsx` (mismo patrón: listas
  derivadas, recalculadas completas). `InvoiceDesigner.jsx:1870` queda
  **mejorable** (lista de reglas de columna que el usuario sí puede
  reordenar — ahí el índice como key sí puede causar que React confunda
  filas al reordenar). Resto en cluster Editor.
- **`html-no-nested-interactive` (1, error-real, corregido)**: confirmado
  leyendo `FloatingBatchWidget.tsx` antes/después del fix — el botón de
  cerrar (`<X>`) vivía como un `<button>` anidado dentro del `<button
  onClick={onNavigate}>` principal, con `e.stopPropagation()` para evitar que
  el click de cerrar disparara la navegación. HTML inválido (un `<button>`
  no puede contener otro) y comportamiento fràgil (dependía de que
  `stopPropagation` se ejecutara antes de que el navegador intentara
  reconciliar el anidamiento). Corregido: el botón de cerrar salió como
  hermano, posicionado con `absolute` sobre el contenedor `fixed` (que ya
  actúa como containing block, confirmado — no se necesitó agregar
  `position: relative`), con `pr-8` en el botón principal para no tapar el
  texto. Componente vivo, usado en 3 pantallas (`App.tsx`,
  `BatchAnalysisPage.tsx`, `ConversionMasivaPage.tsx`).

### 8. Bugs — familia de efectos y estado (`no-event-handler`, `exhaustive-deps`, `no-nested-component-definition`, `prefer-useReducer`, `no-chain-state-updates`, `no-derived-state`, `no-initialize-state`, `no-fetch-in-effect`, `no-pass-live-state-to-parent`, `no-prop-callback-in-effect`, `no-cascading-set-state`, `no-pass-data-to-parent`, `no-effect-chain`, `prefer-use-effect-event`, `no-unstable-nested-components`) — **re-verificado 2026-07-21**

- **`no-event-handler` (22) — confirmado falso-positivo por atribución de
  línea rota, con evidencia directa.** Las 11 líneas únicas que señala el
  escaneo actual en `useExtractGridState.ts` (46, 67, 68, 87, 113-115, 118,
  122) se leyeron una por una: son una declaración `useState`, un predicado
  de filtro de TanStack Table, y líneas dentro del objeto de configuración
  `state: {...}` de `useReactTable` — ninguna tiene la forma que la regla
  describe (prop o estado alimentando un `useEffect` que dispara otro
  `setState`). El único `useEffect` real del archivo vive cerca de la línea
  154, lejos de todas las líneas señaladas. No se abrió issue upstream
  todavía (queda pendiente si se retoma este archivo).
- **`exhaustive-deps` (8) — confirmado mayormente falso-positivo.**
  `grep` sobre el repo encontró exactamente 3 comentarios
  `// eslint-disable-line react-hooks/exhaustive-deps` ya existentes
  (`BatchAnalysisPage.tsx:926,935`, `ConversionMasivaPage.tsx:311`) — el
  linter de ESLint ya los tenía suprimidos a propósito, pero react-doctor usa
  su propio id de regla (`react-doctor/exhaustive-deps`) y no reconoce la
  supresión de un linter distinto, así que los vuelve a reportar. Confirma
  el "mismatch de nombre" que decía la tabla.
- **`no-nested-component-definition` / `no-unstable-nested-components` (1 +
  1) — mismo hallazgo, dos reglas.** Ya documentado con evidencia en
  §Veredictos 6: `BorderControl` definido dentro de `PageBorderControls` en
  `DocumentSettings.jsx:13`, cluster Editor desconectado. Fix propuesto
  (sacar `BorderControl` a scope de módulo) pero no aplicado — no urge
  mientras el cluster no se reconecte.
- **`prefer-useReducer` (5) — confirmado, coincide exacto con el escaneo
  actual.** Los 5 sitios son `App.tsx` (5 `useState`), `BatchAnalysisPage.tsx`
  (16), `ConversionMasivaPage.tsx` (11), `InvoiceDesigner.jsx` (9) y
  `pages/Editor.jsx` (8, cluster). Los 4 vivos son componentes grandes y
  centrales — un refactor a `useReducer` es válido en principio pero es
  cambio estructural de alto riesgo sin beneficio inmediato; queda agendado,
  no se toca sin necesidad concreta.
- **`no-cascading-set-state` (2) y `no-chain-state-updates` (6) —
  confirmado falso-positivo por batching de React 18+/19, con evidencia
  directa.** Verificado `"react": "^19.0.0"` en `package.json`. Leído
  `ConversionMasivaPage.tsx:247-288` (restauración de batch desde
  `localStorage`, guardada con `restoredBatchRef` para correr una sola vez
  al montar): 5 `setState` síncronos seguidos dentro del mismo bloque. Desde
  React 18, todas las actualizaciones de estado dentro del mismo tick —
  incluyendo dentro de `useEffect`, no solo en handlers de evento — se
  agrupan en un solo re-render (batching automático). La premisa de la regla
  ("cada `setState` dispara su propio redraw") ya no aplica a este proyecto.
  `no-chain-state-updates` en `BatchAnalysisPage.tsx:907-909,922` (efecto de
  preflight + auto-detección de RFC) comparte el mismo argumento.
  `ContextMenu.jsx:68` queda en cluster Editor.
- **`no-derived-state` (5) — mixto, confirmado.** `useExtractGridState.ts:156`
  es la única `mejorable` real (valor derivable calculable en render en vez
  de copiado a estado). Los 3 sitios de `ConversionMasivaPage.tsx` (254, 274,
  276) son estado que sí necesita persistir entre renders (progreso de batch,
  no un simple derivado de props). `pages/Editor.jsx:545` es cluster.
- **`no-initialize-state` (4) — mixto, confirmado con lectura de código.**
  `InvoiceDesigner.jsx:1127` (valores "scale"/"fonts") es medición del DOM
  real después de montar — no se puede conocer antes de que el navegador
  calcule layout, patrón sancionado (no hay alternativa sin `useEffect`).
  `BatchAnalysisPage.tsx:746,748` (fases `phase`/`wasRestored` al restaurar
  batch desde `localStorage`) quedan `mejorable` — técnicamente evitable
  pasando el valor inicial a `useState` directo, pero el flash de un frame
  vacío no es perceptible aquí. `pages/Editor.jsx:68` es cluster.
- **`no-fetch-in-effect` (5, 1 corregido) — race condition real,
  confirmada y arreglada.** `InvoiceDesigner.jsx`: al cambiar de plantilla
  rápido, una respuesta vieja podía resolver después de la nueva y pisar el
  estado con datos obsoletos. Fix: bandera `cancelled` de closure + limpieza
  del efecto (`return () => { cancelled = true }`), mismo patrón que React
  documenta para este caso exacto.
- **`no-pass-live-state-to-parent` / `no-prop-callback-in-effect` /
  `no-pass-data-to-parent` (4+4+2) — confirmado, son el mismo código.**
  Las tres reglas señalan literalmente las mismas líneas
  (`BatchAnalysisPage.tsx:931,933` y `ConversionMasivaPage.tsx:303,305`): el
  efecto que propaga progreso a `App.tsx` para `FloatingBatchWidget`. Ya
  tiene un comentario explícito en el código explicando por qué
  `onProgressUpdate` se excluye a propósito de las dependencias (evitar un
  loop, porque `App.tsx` pasa una arrow function nueva cada render). Mejora
  real posible (mover a un Provider compartido) pero requiere tocar
  `App.tsx`, que está protegido de refactors especulativos. `pages/Editor.jsx`
  comparte el mismo patrón, cluster.
- **`no-effect-chain` (1) — matiz sobre el veredicto original.** La cadena
  real es: un efecto consume `pendingFiles` y hace `setFiles`, lo que dispara
  un segundo efecto (preflight) que lee `files`. A diferencia del caso de
  batching de arriba, aquí sí son dos `useEffect` separados encadenados, no
  múltiples `setState` en un mismo bloque — el argumento de "batching de
  React 19" no aplica igual de limpio. La razón real para no tocarlo:
  `runPreflight(files)` es async (lee contenido de archivos), no se puede
  correr durante el render, así que el segundo hop es intrínseco al trabajo,
  no una elección de diseño evitable. Verdicto ajustado a `mejorable`, no
  `falso-positivo`.
- **`prefer-use-effect-event` (1) — confirmado.** Único hallazgo en
  `Toast.jsx:18`, archivo ya clasificado como cluster Editor desconectado en
  §Veredictos 5 (`feature-en-desarrollo`, pausada).

### 9. Performance — familia completa (`no-transition-all`, `js-combine-iterations`, `rerender-state-only-in-handlers`, `js-flatmap-filter`, `use-lazy-motion`, `no-long-transition-duration`, `async-parallel`, `no-usememo-simple-expression`, `rerender-lazy-ref-init`, `no-layout-transition-inline`, `async-defer-await`) — **re-verificado 2026-07-21**

- **`rerender-state-only-in-handlers` (6, 4 corregidos) — confirmado con
  lectura de cada sitio.** `useState`→`useRef` en `BatchAnalysisPage.tsx`
  (`activeBatchId`, escrito una sola vez al restaurar desde localStorage,
  nunca leído en render), `ConsultasSATPage.tsx` (`jobId`, solo
  leído/escrito dentro de handlers), y `EmisoresPage.tsx` (`cerFile`/
  `keyFile`, inputs de archivo no controlados — el navegador no permite
  bindear `value` a un `File`, así que el estado nunca pintaba nada
  distinto). Los 4 cambios son comportamiento-preservador: mismos valores,
  mismos momentos de lectura, solo sin el re-render que no cambiaba nada
  visible.
- **`async-defer-await` (1, corregido) — confirmado.**
  `pdf-download.ts:220`: el código leía el body de la respuesta con
  `.text()` ANTES de revisar si el status era 429 (que no usa ese body).
  Reordenado: primero el chequeo de status, luego el `.text()` solo si hace
  falta. Mismo mensaje de error en todos los casos, un `await` menos en el
  camino más común.
- **`async-parallel` (1) — verificado directamente contra el código, no
  solo el config.** `App.tsx:248-288` (`handleDownloadPdf`): `POST
  /start` → esperar el `jobId` → suscribirse a `EventSource` y esperar el
  evento `done` → `GET /download` con ese `jobId`. Cada paso necesita el
  resultado del anterior — no son operaciones independientes que
  `Promise.all` pudiera paralelizar. Supresión en `doctor.config.ts`
  confirmada correcta.
- **`no-usememo-simple-expression` (1, corregido) — confirmado.**
  `useExtractGridState.ts`: `activeExtractBaseRows` era un `useMemo` sobre
  un ternario simple (`activeDatasetType === 'ingresos' ? ingresoRows :
  pagoRows`) — leer dos referencias y comparar un string cuesta menos que el
  overhead de memoización. Quitado el `useMemo`, mismo resultado
  referencial en cada render.
- **`rerender-lazy-ref-init` (1) — confirmado, verdicto correcto.**
  `BatchAnalysisPage.tsx:591`: `useRef<Map...>(new Map())` — JS evalúa
  `new Map()` en cada render aunque `useRef` solo use el primero, así que se
  crea y descarta un Map vacío de más en cada render. El fix (inicialización
  perezosa con `ref.current ??= new Map()` o similar) complicaría el tipo en
  cada sitio de lectura para un ahorro real pero mínimo (`new Map()` vacío es
  barato). `mejorable`, no urge.
- **`no-long-transition-duration` (2) — confirmado `tiene-razon-de-ser`
  con lectura de código.** `XmlNodeViewer.tsx:38,59`: `animation:
  'xml-highlight 1.4s ease-out forwards'` en los tokens de error/warning del
  visor XML — es un "flash de atención" deliberado para que el usuario note
  el hallazgo, no una transición de UI genérica que debiera ser corta.
- **`no-layout-transition-inline` (1) — confirmado, verdicto correcto.**
  `InvoiceDesigner.jsx:1826`: `transition: 'width 0.15s'` en la barra de
  "espacio usado" de columnas — anima una propiedad de layout (real, la
  regla tiene razón técnica), pero es una barra decorativa pequeña, 0.15s,
  de uso poco frecuente; migrar a `transform: scaleX` requeriría
  reestructurar el posicionamiento para un beneficio perceptualmente nulo.
- **`no-transition-all`, `js-combine-iterations`, `js-flatmap-filter`,
  `use-lazy-motion` — no re-verificados línea por línea en esta pasada**
  (30, 15, 2 y 2 hallazgos respectivamente en el escaneo actual). La lógica
  de los veredictos existentes (mayoría en cluster Editor o código de
  cálculo/parsing donde el riesgo de tocar supera la ganancia) es plausible
  pero queda marcada `pendiente de re-verificación individual` si se retoma
  esta familia — no se quiere repetir el error de transcribir un veredicto
  sin leer el código correspondiente.

### 10. Accesibilidad — familia completa (`control-has-associated-label`, `no-tiny-text`, `label-has-associated-control`, `no-static-element-interactions`, `click-events-have-key-events`, `no-outline-none`, `no-autofocus`, `prefer-tag-over-role`) — **re-verificado 2026-07-21**

- **Conteos vivo/cluster corregidos en la tabla de arriba** —
  `control-has-associated-label` y `label-has-associated-control` tenían
  vivo/cluster invertidos en la versión original (decía "~86 vivo/38
  cluster" cuando el desglose real por archivo, corrido hoy contra el
  escaneo actual, es 39 vivo/86 cluster; mismo error en la otra regla, real
  8 vivo/81 cluster). El cluster Editor concentra la enorme mayoría
  (`editor/PropertiesPanel.jsx`, `editor/DocumentSettings.jsx` y el resto de
  `editor/*`, ya confirmados desconectados en §Veredictos 5 — nada en
  `App.tsx` ni en las rutas activas los importa).
- **9 sitios vivos corregidos hoy** (checkboxes/inputs icon-only con
  `aria-label`, pares `<label htmlFor>`/`id` en `EmisoresPage.tsx` y
  `BatchAnalysisPage.tsx`), confirmados leyendo cada diff. Falso-positivo
  sistemático real: los spacers de columna de las tablas virtualizadas
  (`ExtractWorkspaceTable.tsx`) son `<input>` decorativos sin rol
  interactivo real — no se tocaron, correcto dejarlos.
- **`no-static-element-interactions` + `click-events-have-key-events` (3
  sitios fijos hoy, confirmados con lectura antes/después):**
  `ConsultasSATPage.tsx` (zona de drop de archivo), `InvoiceDesigner.jsx`
  `SectionZone` y `ToggleRow` — los tres recibieron `role`, `tabIndex={0}`,
  `aria-label`/`aria-pressed`/`aria-checked` y un `onKeyDown` que dispara la
  misma acción que el click con Enter/Espacio. Quedan 4 sitios vivos sin
  tocar (`App.tsx`, `ExtractWorkspaceTable.tsx`, `InvoiceDesigner.jsx` un
  sitio adicional, `PdfTemplateBuilder.tsx`) — no confirmados uno por uno en
  esta pasada, quedan `mejorable`.
- **`prefer-tag-over-role` (2, nueva) — confirmado que apareció por los
  fixes de hoy, con la razón correcta.** Los 2 hallazgos son exactamente los
  2 `div role="button"` que se acaban de agregar (`ConsultasSATPage.tsx:140`,
  zona de drop; `InvoiceDesigner.jsx:1072`, `SectionZone`). Ambos envuelven
  contenido rico — una zona de drag-and-drop con `onDrop`/`onDragOver` y una
  sección editable con hijos arbitrarios — que no cabe dentro de un
  `<button>` real (restricciones de contenido: un `<button>` no puede
  contener elementos interactivos anidados). El patrón `div role="button"` +
  `tabIndex` + manejo de teclado es exactamente lo que WAI-ARIA APG
  recomienda para este caso. Supresión puntual propuesta en
  `doctor.config.ts`, sin aplicar — decisión del usuario.
- **`no-outline-none` (5, corregido) — confirmado.** 5 `<input>` de
  `InvoiceDesigner.jsx` (color de marca, URL de logo, y 3 más) tenían
  `outline: 'none'` sin ningún indicador de foco alternativo — invisibles
  para navegación por teclado. Se quitó la propiedad, queda el outline
  nativo del navegador.
- **`no-autofocus` (1) — no re-verificado en detalle.** `InvoiceDesigner.jsx:959`.
  El veredicto original ("falta un componente Modal accesible completo,
  fuera de alcance") es plausible pero no se leyó el código en esta pasada —
  queda `pendiente de re-verificación` si se retoma.
- **`no-tiny-text` (68) — no re-verificado línea por línea.** Mismo
  criterio que el resto de "no re-verificado": requiere QA visual real en
  navegador, no solo lectura de código, y no se hizo en esta pasada.

## Relación con "Hallazgos preexistentes" (PROJECT_STATE.md)

- `PROJECT_STATE.md §Hallazgos preexistentes` registra lo que se encuentra
  roto *de paso* durante cualquier tarea (con evidencia, p. ej. `git stash`).
- Si el hallazgo preexistente es de react-doctor, además se refleja aquí en la
  familia correspondiente.
- La política que obliga a anotar en vez de descartar vive en `AGENTS.md`.
