# Análisis UX/UI — Análisis Masivo

> **Fecha de análisis:** 2026-06-03
> **Basado en:** 10 screenshots capturados + revisión de código fuente
> **Dirigido a:** Diseñador web responsable de mejoras de UX/UI

---

## Mapa de flujo completo

```
IDLE VACÍO
  │  Arrastra XMLs o selecciona archivos
  ▼
IDLE CON PREFLIGHT
  │  "Procesar N facturas"
  ▼
PROCESSING ─────────────────────────────────────────┐
  │  Navega a otra vista                             │
  │                                            FLOATING WIDGET
  │                                                  │ Clic → regresa a PROCESSING
  │  Batch termina (todos procesados)                │
  ▼                                                  │
DONE + MODAL DE COMPLETADO ◄────────────────────────┘
  │
  ├─ Cerrar modal  ──────────────────────┐
  │                                      ▼
  │                               DONE — todas las filas
  │                                      │
  │                                      ├─ Click card/pill filtro → DONE FILTRADO
  │                                      │
  │                                      ├─ Click en fila → INSPECTOR (drill-down)
  │                                      │                      │
  │                                      │                      └─ "← Análisis masivo"
  │                                      │                             → vuelve a DONE
  │                                      ├─ "Reintentar fallidos" → PROCESSING (parcial)
  │                                      └─ "Nueva carga" → IDLE VACÍO
  │
  └─ "Ver hallazgos →"  ──────────────── DONE FILTRADO (Con hallazgos)

DONE SOLO ERRORES
  ├─ "Reintentar fallidos" → PROCESSING
  └─ "Nueva carga" → IDLE VACÍO
```

---

## Análisis por pantalla

### 1. IDLE VACÍO (`masivo-idle`)

**Lo que funciona:**
- El área de drop zone es clara: ícono de upload, texto instructivo, dos botones diferenciados (Archivos / Carpeta)
- Subtítulo "Solo .xml · Cualquier cantidad — se procesa por lotes" establece expectativas correctas
- El sidebar con "Análisis masivo" activo da contexto de ubicación

**Friction:**
- El drop zone está centrado verticalmente en un área enorme de pantalla en blanco — hay ~500px de espacio vacío debajo que no comunica nada. El usuario no sabe qué va a ver cuando procese
- Los botones "Archivos" y "Carpeta" tienen el mismo peso visual. No hay indicación de cuál usar primero (el primario debería ser "Archivos")
- No hay un "preview" o ejemplo de qué ofrece la herramienta — alguien que llega por primera vez no sabe si obtendrá un reporte, una tabla, un PDF, etc.
- El espacio vacío debajo del drop zone podría usarse para mostrar: ejemplo de output, instructivo de qué es un CFDI válido, o el historial de lotes anteriores

**Falta:**
- Indicador de estado del backend (si está caído, el usuario no lo sabrá hasta que procese y falle todo)
- Texto guía para el caso de "¿no tienes XMLs? Así se ven los archivos que necesitas"

---

### 2. IDLE CON PREFLIGHT (`masivo-idle-with-preflight`)

**Lo que funciona:**
- El drop zone cambia a "4 archivos seleccionados" en azul — buen feedback de confirmación
- La `PreflightCard` ("PRE-VUELO") muestra datos útiles: conteo, rango de fechas
- El botón "Procesar 4 facturas" con el número de archivos da seguridad al usuario antes de procesar

**Friction:**
- La etiqueta "PRE-VUELO" es jerga técnica. Para un usuario no técnico, no es intuitivo qué significa. Una alternativa: "Resumen de archivos seleccionados" o simplemente ningún título (solo los datos)
- La `PreflightCard` está muy comprimida — solo una línea de datos ("4 facturas CFDI detectadas, Fechas: Feb 2026 – May 2026"). Para un lote importante, el usuario querría ver más (¿hay duplicados? ¿cuántos emisores?)
- El espacio entre el drop zone y los botones de acción es excesivo. La página sigue teniendo ~400px de blanco debajo de los botones
- El botón "Limpiar" tiene bajo contraste — en un flujo donde el usuario acaba de seleccionar archivos, el botón destructivo no debería competir en visual prominence con "Procesar"

**Falta:**
- Si hay posibles duplicados, la PreflightCard debería resaltarlo más visualmente (badge naranja prominent, no solo un texto inline)
- No hay indicación del tamaño total del lote en MB/GB — para lotes grandes el usuario podría querer saber el tiempo estimado antes de procesar

---

### 3. PROCESSING (`masivo-processing`)

**Lo que funciona:**
- `BatchPipelineIndicator` con 3 pasos es excelente — da orientación clara del flujo
- Las 3 stats cards (Velocidad, Total, Tiempo) son muy útiles y transmiten profesionalismo
- Las `InsightCards` (Emisor más frecuente, Mes más activo) son un diferenciador de valor — el usuario recibe inteligencia en tiempo real, no solo un spinner
- El badge "N hallazgos" en naranja crea anticipación apropiada
- Las filas con animación flash al completarse son un toque elegante

**Friction:**
- Las 3 stats cards tienen exactamente el mismo peso visual — sin jerarquía. "TIEMPO RESTANTE" probablemente es la más importante para el usuario (¿cuánto falta?), pero está en la tercera posición y tiene el mismo tamaño que las otras
- La tabla de progreso muestra filas completadas primero, pero el orden cambia dinámicamente — para lotes grandes el usuario no puede seguir visualmente "dónde va" su archivo específico
- Los skeleton loaders de filas pendientes son grises sin contenido — está bien, pero no está documentado si el orden de las filas es el mismo que el orden de upload (no lo es)
- El contador "N hallazgos" usa un ícono de advertencia naranja pero sin contexto — ¿es eso bueno o malo? Para usuarios nuevos podría causar ansiedad innecesaria

**Falta:**
- No hay forma de pausar el procesamiento (solo cancelar completamente)
- No hay estimación de "tiempo ahorrado" en tiempo real (solo aparece en el modal al terminar)
- Las InsightCards aparecen solo si hay datos suficientes — en los primeros segundos el espacio donde aparecerán está vacío de forma abrupta

---

### 4. DONE — Resultados (`masivo-done`)

**Lo que funciona:**
- El `TriageHeader` con 3 cards (Sin errores, Con hallazgos, Errores) es una solución elegante de triage
- La tabla de 8 columnas cubre todos los datos relevantes
- El badge de "HALLAZGOS" con número en amarillo es claro
- La sección REPORTES DIOT integrada en el mismo flujo es conveniente

**Friction crítica:**
- **Las filas no tienen indicador visual de que son clicables.** No hay chevron, flecha, ni hint de "ver detalle". Un usuario no descubrirá el drill-down al Inspector a menos que haga clic accidentalmente o que alguien se lo enseñe. Es el feature más valioso de la herramienta y está completamente oculto.
- **"Hallazgo" es término técnico.** El campo "HALLAZGOS" en la columna y los badges de "Con hallazgos" pueden confundir a usuarios no técnicos. ¿Es un error? ¿Una alerta? ¿Una discrepancia? La terminología no comunica urgencia ni acción.
- **La sección REPORTES DIOT está enterrada.** Hay que hacer scroll para verla. Para usuarios cuyo flujo principal es generar el DIOT, esta sección debería ser más accesible (tab, ancla, o posición más prominente).
- **Doble mecanismo de filtro.** Las cards del TriageHeader Y los pills de texto ("Todas", "Sin errores", "Con hallazgos", "Solo errores") son redundantes. El usuario no sabe cuál usar — y ambos hacen lo mismo.

**Friction moderada:**
- La columna HALLAZGOS muestra número o vacío (no "0") — inconsistencia con otras columnas que siempre tienen valor
- El botón "⬇ CSV" está en la esquina inferior derecha de la tabla, muy pequeño y difícil de encontrar
- No hay indicación de que "click en fila → Inspector". El único hint es el cursor-pointer al hover, invisible en touch

---

### 5. DONE — Solo Errores (`masivo-done-only-errors`)

**Lo que funciona:**
- El ícono ⚠️ en el paso 3 del pipeline en naranja es apropiado para comunicar "completado con problemas"
- El botón "Reintentar fallidos (N)" en naranja es prominente y accionable

**Friction:**
- El mensaje "Error de lectura" no distingue entre error del usuario (XML inválido) vs error del sistema (backend caído) — el usuario no sabe si debe intentarlo de nuevo o corregir sus archivos
- Las columnas con "—" crean una tabla muy vacía y desoladora — no hay mensaje de ayuda como "¿Por qué falló? Asegúrate de que tus archivos sean CFDI 4.0 válidos"
- El pipeline con "2 con errores" en naranja puede confundirse con "2 con hallazgos" — son conceptualmente diferentes pero visualmente similares

---

### 6. FLOATING WIDGET (`masivo-floating-widget`)

**Lo que funciona:**
- La posición en esquina inferior derecha es estándar y no invasiva
- El texto "Procesando lote... N/Total facturas 67%" con barra de progreso es claro y preciso
- "Clic para ver el progreso en detalle →" es un CTA explícito
- El botón ✕ permite descartarlo sin cancelar el batch

**Friction:**
- **El botón ✕ es ambiguo.** Los usuarios pueden pensar que cancela el batch. Debería decir "Ocultar" o el ✕ debería tener un tooltip "Ocultar (el lote sigue procesando)"
- Cuando el batch termina y el usuario lo descartó con ✕, no hay ninguna otra notificación. El usuario puede no enterarse de que terminó
- El widget no tiene un estado visual para "completado con errores" diferente del verde — si terminó con 50% errores, el verde puede ser misleading

---

### 7. INSPECTOR DRILL-DOWN (`masivo-inspector-drilldown`)

**Lo que funciona:**
- El breadcrumb "← Análisis masivo / Ingreso / Inspector" da contexto de ubicación clara
- El botón "← Análisis masivo" como call-to-action de regreso es obvio
- El Inspector en sí tiene mucha información de valor

**Friction crítica:**
- **No hay navegación anterior/siguiente.** Para revisar 10 archivos con hallazgos, el usuario tiene que: ver Inspector → clic "← Análisis masivo" → clic en siguiente fila → esperar carga → ver Inspector. Multiplica el tiempo por N archivos. Un simple "← Anterior / Siguiente →" resolvería esto.
- **El inspector tiene 7 acciones en el header** (Auditoria, Nodo XML, Validar RFC, Consultar SAT, PDF, PDF Pro, Exportar). Para un usuario que viene del Masivo y solo quiere revisar hallazgos, esta densidad de opciones es abrumadora.

**Friction moderada:**
- El breadcrumb "← Análisis masivo / Ingreso / Inspector" no incluye el nombre del archivo — el usuario no sabe cuál de los 10 archivos está viendo sin mirarlo en el cuerpo
- No hay indicador de "X de N archivos revisados" para el usuario que está haciendo revisión secuencial del lote

---

## Pain Points Críticos (prioridad para el diseñador)

### 🔴 Alta prioridad

| # | Pain point | Pantalla | Impacto |
|---|-----------|---------|---------|
| P1 | **Las filas de la tabla de resultados no tienen indicador visual de que son clicables** — el drill-down al Inspector es el feature más valioso y está oculto | `masivo-done` | Muy alto — usuarios nunca descubren el Inspector |
| P2 | **No hay navegación anterior/siguiente en el Inspector drill-down** — revisar N archivos requiere N×2 clics + N carga | `masivo-inspector-drilldown` | Muy alto — degrada la eficiencia del flujo principal |
| P3 | **La sección REPORTES DIOT está fuera del fold** — requiere scroll para llegar | `masivo-done` | Alto para usuarios cuyo flujo es DIOT |

### 🟡 Prioridad media

| # | Pain point | Pantalla | Impacto |
|---|-----------|---------|---------|
| P4 | **"PRE-VUELO" es jerga técnica interna** no estándar. "Hallazgos" es terminología estándar en auditoría fiscal mexicana (SAT) — válida para PAC/contadores, potencialmente opaca para el perfil Empresa 1. ⚠️ Validar con usuarios antes de renombrar. | `masivo-idle-with-preflight`, `masivo-done` | Medio — solo afecta al perfil no técnico; no renombrar sin validación con usuarios PAC |
| P5 | **Doble mecanismo de filtro** (cards TriageHeader + pills texto) — redundante y confuso | `masivo-done` | Medio — genera indecisión |
| P6 | **El botón ✕ del FloatingWidget parece cancelar el batch** cuando solo oculta | `masivo-floating-widget` | Medio — riesgo de pérdida de datos percibida |
| P6b | **El modal "¡Lote completado!" con ✓ verde aparece incluso cuando el lote es 100% errores** — tono celebratorio contradice el resultado | `batch-completion-modal` | Medio — genera desconfianza en la herramienta |
| P7 | **"Error de lectura" no distingue entre error del usuario vs sistema** | `masivo-done-only-errors` | Medio — el usuario no sabe si puede corregirlo |
| P8 | **El empty state (idle) no muestra qué esperar** — 500px de blanco vacío | `masivo-idle` | Medio — impacta conversión en primer uso |

### 🟢 Prioridad baja

| # | Pain point | Pantalla | Impacto |
|---|-----------|---------|---------|
| P9 | **"TIEMPO RESTANTE" no tiene jerarquía visual superior** aunque es la métrica más consultada | `masivo-processing` | Bajo — UX refinement |
| P10 | **La columna HALLAZGOS está vacía en lugar de "0"** para filas sin hallazgos | `masivo-done` | Bajo — inconsistencia tipográfica |
| P11 | **El botón CSV está en la esquina inferior derecha muy pequeño** | `masivo-done` | Bajo — difícil de encontrar |
| P12 | **Ausencia de notificación al terminar si el FloatingWidget fue descartado** | `masivo-floating-widget` | Bajo — flujo edge case |
| P13 | **El color naranja está sobrecargado:** mismo color para "Con hallazgos" (discrepancia fiscal) y para "Error de lectura" (fallo técnico) y para el paso 3 del pipeline en error — el naranja ya no comunica nada específico | `masivo-done`, `masivo-done-only-errors` | Bajo — ruido semántico |

---

## Recomendaciones de diseño

### RD-1: Indicador de acción en filas de la tabla (resuelve P1)

Agregar a cada fila de resultado (status !== 'error') un indicador visual de clickability:
- Chevron derecho `›` en la última columna (o como columna fantasma al hover)
- O: hover state con fondo azul muy suave + cursor-pointer visible
- O: botón explícito "Ver detalle" en la última columna

**Justificación:** El drill-down al Inspector es el diferenciador de la herramienta. Si los usuarios no lo descubren, el valor percibido de Análisis Masivo se reduce a "solo una tabla de Excel".

---

### RD-2: Navegación secuencial en el Inspector (resuelve P2)

> ⚠️ **Esta es una feature de sprint, no un ajuste visual.** Requiere: pasar el array de resultados del Masivo al Inspector, trackear el índice actual, sincronizar el ordenamiento con el filtro activo al momento del click, y manejar el flujo no-batch. No encolar en un sprint de "UX polish" — encolar en un sprint de features.

En el Inspector drill-down, agregar en el breadcrumb o header:
```
← Análisis masivo    [3 / 10]    ← Anterior   Siguiente →
```
- "3 / 10" indica la posición del CFDI actual en el lote
- "Anterior / Siguiente" navega al CFDI previo/siguiente sin regresar al Masivo
- Solo mostrar si `fromMasivo === true`

**Justificación:** Reduce de 2 clics + carga a 1 clic para revisar cada CFDI secuencialmente. Para lotes de 50+ archivos, el impacto en tiempo es significativo.

---

### RD-3: Elevar la sección REPORTES (resuelve P3)

Opción A: Mover REPORTES a un tab al nivel del TriageHeader:
```
[▼ Resultados]  [📋 Reporte DIOT]
```

Opción B: Ancla fija al fondo con indicador "⬇ DIOT disponible" cuando hay datos

Opción C: Agregar "⬇ Descargar DIOT" como botón de acción en el área del TriageHeader cuando `phase === 'done'`

**Justificación:** Para el perfil PAC Diverza (usuario técnico con volumen alto), el DIOT puede ser la acción más frecuente. Que esté fuera del fold obliga a scroll en cada sesión.

---

### RD-4: Ajustar lenguaje para perfil no técnico (resuelve P4 parcialmente)

> ⚠️ Antes de implementar, validar con al menos 1 usuario contador/PAC. "Hallazgo" es terminología estándar SAT — renombrarlo puede dañar credibilidad con usuarios técnicos.

Cambios seguros (afectan solo la UI interna del producto, no terminología SAT):
- "PRE-VUELO" → "Resumen del lote"

Cambios que requieren validación con usuarios:
- "Con hallazgos" → "Requiere revisión" (solo si los usuarios Empresa 1 no reconocen el término)
- "Hallazgos: N" (columna) → "Alertas: N" (solo si se confirma que confunde)

No cambiar:
- "Error de lectura" — es descriptivo y técnicamente preciso

---

### RD-5: Unificar el mecanismo de filtro (resuelve P5)

Eliminar uno de los dos mecanismos de filtro. Propuesta:
- **Mantener:** las cards del TriageHeader como botones de filtro (tienen los números y son visualmente ricas)
- **Eliminar:** los pills de texto redundantes ("Todas", "Sin errores", "Con hallazgos", "Solo errores")
- **Agregar:** pill "Todas" solo como opción de limpiar filtro cuando uno está activo (CTA contextual, no siempre visible)

```
[✓ 0 Sin errores  ·  0%]  [⚠ 6 Requiere revisión  ·  100%]
                                                                 [Limpiar filtro ×]  ← solo cuando hay filtro activo
```

---

### RD-6: Mejorar el FloatingWidget (resuelve P6, P12)

- Cambiar ✕ a "Ocultar" (texto) o agregar tooltip: "Ocultar — el lote sigue procesando"
- Al terminar mientras el widget fue ocultado: mostrar brevemente un toast/snackbar "✓ Lote completado — Ver resultados" que desaparece en 5s
- Diferenciar estado done-con-errores: en lugar de verde ✓, usar ámbar ⚠️

---

### RD-7: Mejorar el empty state del idle (resuelve P8)

El espacio vacío debajo del drop zone puede usarse para:
```
┌──────────────────────────────────────────────────────────────┐
│   Arrastra XMLs o carpetas aquí, o selecciona:               │
│          [Archivos]  [Carpeta]                                │
│   Solo .xml · Cualquier cantidad — se procesa por lotes      │
└──────────────────────────────────────────────────────────────┘

¿Qué obtendrás?
  📊  Tabla de resultados con status por archivo
  🔍  Análisis de discrepancias por CFDI
  📋  Reporte DIOT descargable
  ⚡  Procesamiento paralelo — 100s de archivos en segundos
```

---

### RD-8: Jerarquía visual en stats cards (resuelve P9)

En la fase de processing, "TIEMPO RESTANTE" debería tener mayor jerarquía visual:
- Tamaño de fuente más grande para el valor (~2.5rem vs 2rem de las otras)
- O: posición primero (izquierda) en lugar de último (derecha)
- O: fondo levemente diferente para destacarla

---

## Patrones inconsistentes con el sistema de diseño

| Área | Inconsistencia | Recomendación |
|------|---------------|---------------|
| **Breadcrumb del drill-down** | "← Análisis masivo / Ingreso / Inspector" usa `/` como separador; el AppHeader usa `·` | Unificar separador |
| **Sidebar en drill-down** | Muestra "Reprint" y "Cancelaciones" tachados/grises sin explicación | Ocultar si no aplican al contexto actual |
| **Logo en drill-down** | El header del Inspector muestra "CFDI Suite" pequeño + "Inspector" como texto plano; en Masivo muestra el breadcrumb "Operaciones / Análisis masivo" en el AppHeader — son patrones diferentes | Unificar el header de contexto |
| **Botón CSV** | Los botones de exportar en otras vistas (e.g., Inspector tiene "Exportar") son prominentes; en Masivo el CSV está como texto pequeño en el footer de la tabla | Elevar a botón de acción estándar |
| **Terminología de estados** | "Error de lectura" (tabla) vs "Reintentar fallidos" (botón) — el mismo concepto con dos nombres | Unificar a "Error de lectura" o "No procesado" en ambos contextos |

---

## Resumen ejecutivo para el diseñador

El Análisis Masivo tiene una base técnica sólida y features de alto valor (insights en tiempo real, drill-down al Inspector, DIOT integrado). Los problemas de UX son principalmente de **descubrimiento** y **flujo**:

1. **El feature más valioso está oculto:** el drill-down al Inspector no tiene indicador de clickability (P1)
2. **El flujo de revisión secuencial es ineficiente:** sin anterior/siguiente en el Inspector (P2)
3. **El lenguaje es técnico:** "hallazgos", "PRE-VUELO" no conectan con usuarios no técnicos (P4)
4. **El empty state no convence:** la pantalla idle no vende la herramienta (P8)

Los pain points P1 y P2 son los que más impactan la eficiencia del flujo principal. Si solo se puede abordar una cosa, agregar el indicador de clickability en las filas (RD-1) tiene el ROI más alto.
