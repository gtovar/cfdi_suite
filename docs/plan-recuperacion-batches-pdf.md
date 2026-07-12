# Plan de ejecución — Recuperación de PDFs de batches (CFDI Suite)

> Deriva del documento de decisión del panel multidisciplinario (ver `PROJECT_STATE.md` / conversación de origen). Cada fase pasó por un análisis tipo decision-expander antes de fijarse como plan — el objetivo es que no queden puntos pendientes ni "esperar X" como parte del plan de ejecución. Donde el análisis cambió el enfoque original, se documenta el cambio y por qué.

---

## Fase 1 — Auditar la infraestructura fantasma (antes de fijar ningún número)

### Decision-expander

**Qué existe realmente:** la regla de lifecycle de GCS (`age: 1` día sobre `uploads/`, `xml_temp/`, `pdfs/`) solo se infiere de un comentario en `pdf.py:785-786` — no está en ningún IaC del repo. El presupuesto de comandos de Redis Upstash tiene dos cifras contradictorias en el propio repo (10,000/día en `pdf.py:299` vs 500k/mes en `docs/progreso-tiempo-real-pusher.md:10`).

**Mal asumido:** en el plan original, esta auditoría estaba en "Fase 3", después de decidir TTLs y construir. Eso es al revés — la Fase 2 (fijar TTL de Redis a 24h) usa como ancla un número (24h) que a su vez depende de un límite de GCS no verificado. Se está anclando una decisión a una inferencia, no a un hecho.

**Variables omitidas:** no se sabe si el lifecycle aplica igual a las tres carpetas, ni si Upstash aplica eviction bajo presión de memoria antes del TTL nominal.

**Riesgo de no hacer esto primero:** fijar TTL=24h en Redis y descubrir después que el lifecycle real de GCS es menor (ej. 12h) — el síntoma original (404 antes de tiempo) reaparecería en otro punto, sin que quede claro por qué.

**Prueba mínima:** dos comandos, sin esperar nada.

### Plan de la fase

1. Correr `gsutil lifecycle get gs://<bucket>` (o `gcloud storage buckets describe <bucket> --format="default(lifecycle)"`) para obtener la regla real vigente sobre `pdfs/`, `uploads/`, `xml_temp/`.
2. Guardar esa configuración en el repo como archivo versionado (`infra/gcs-lifecycle.json` o similar) — deja de ser infraestructura fantasma.
3. Revisar el dashboard de Upstash (sección de uso/métricas) para confirmar el límite real de comandos vigente en el plan actual.
4. Corregir la constante `UPSTASH_DAILY_COMMANDS_LIMIT` en `pdf.py:299` y el dato en `docs/progreso-tiempo-real-pusher.md:10` para que digan lo mismo, con la cifra confirmada.
5. Con el valor real de lifecycle en mano, definir el TTL objetivo para Fase 2 (si el lifecycle confirma 1 día, se usa 24h como estaba planteado; si es otro valor, se usa ese).

**Sin esperar 24h reales:** este paso es de consulta/lectura de configuración, no de observar expiración en vivo — se resuelve en minutos.

---

## Fase 2 — Fix backend: `blob.exists()` + TTL de batch al valor real

### Decision-expander

**Qué podría estar mal nombrado:** llamar a esto "solo un bug fix" oculta que son dos cambios de naturaleza distinta agrupados: (a) el fix de `blob.exists()` en `/download-url` es un bug puro, sin ambigüedad; (b) extender el TTL de un link no autenticado es, por definición, una decisión de exposición de datos fiscales — ya lo estableció el panel original, pero vale la pena que quede explícito también aquí, no solo en el documento del panel.

**Variables omitidas:** frecuencia real de llamadas a `/download-url` (si se llama en cada tick de polling de progreso, añadir `blob.exists()` mete una llamada extra a GCS por tick — vale la pena revisar si ese endpoint ya se llama solo bajo demanda de descarga o también durante el polling de estado).

**Capacidad no considerada:** el backend ya tiene tracing con OpenTelemetry (`main.py:76-87`) — se puede usar el span existente para confirmar el volumen de llamadas a este endpoint antes de asumir que el costo de latencia es despreciable.

**Alternativa no obvia:** separar en dos commits/PRs aunque se mergeen juntos — deja rastro claro de que el fix de bug y la decisión de TTL son cosas distintas, útil si en el futuro hay que revertir solo una de las dos.

**Riesgo:** ninguno nuevo más allá de lo ya cubierto por el panel original (ventana de exposición de 1h→24h ya evaluada como riesgo aceptable, consistente con lo que ya se acepta hoy para el link individual).

### Plan de la fase

1. En `backend/app/routers/pdf.py`, endpoint `/download-url` (líneas ~663-691): agregar verificación `blob.exists()` antes de generar la signed URL; si no existe, devolver 404 explícito en vez de un link roto.
2. Cambiar el TTL de `pdf:batch_ids`, `pdf:extracting_total`, `pdf:ready_recent`, `pdf:done_count`, `pdf:error_count` de `3600` al valor confirmado en Fase 1 (líneas 335-337, 731, 743-744, 810).
3. Verificación sin esperar tiempo real: usar `redis-cli EXPIRE pdf:batch_ids:<id> 5` (o el cliente async del proyecto) sobre un batch de prueba para forzar expiración en segundos y confirmar el comportamiento antes/después del fix, en vez de esperar 1h o 24h reales.

**Sobre la latencia de `blob.exists()`: no es una condición para lanzar esta fase.** `blob.exists()` es una llamada HEAD de bajo costo (decenas de milisegundos) — se agrega sin gate ni investigación previa. El monitoreo ya existente (OpenTelemetry/Sentry) queda corriendo de fondo por defecto; si algún día ese endpoint aparece como hotspot ahí, se cachea el resultado entonces. No hay una pregunta abierta aquí, solo una fase de observación pasiva que no bloquea ni retrasa el fix.

**Hallazgo de verificación (no estaba en el análisis original, se encontró al revisar el código antes de dar por cerrado el documento):** `_batch_progress_snapshot` (`backend/app/routers/pdf.py:368-421`) — la función que alimenta tanto `/status` como el snapshot inicial que usa el frontend al reconectar — depende de `pdf:extracting_total:{batch_id}`. Si esa clave ya expiró, la función devuelve `{"status": "error", "message": "Lote no encontrado"}` de forma explícita (línea 386), aunque el lote haya terminado bien y los PDFs sigan existiendo. Esto confirma que el TTL de `pdf:extracting_total` **debe** corregirse en esta fase (ya estaba en el alcance del paso 2), y establece una **dependencia dura de orden de despliegue con la Fase 3**: la Fase 3 no debe desplegarse en producción antes que esta fase, porque extender la ventana de recuperación del frontend sin haber corregido este TTL primero cambiaría el síntoma de "silenciosamente ya no recupera" (hoy) a "muestra explícitamente 'Lote no encontrado'" (peor, no mejor).

---

## Fase 3 — Frontend: link persistente + compartir + alinear expiración visible

### Decision-expander

**Mal asumido en la versión original del plan:** "unificar" el mecanismo de `ConversionMasivaPage` (PDFs, TTL 45min) con el de `BatchAnalysisPage` (análisis DIOT/IVA-ISR, sin TTL) partía de asumir que la ausencia de tope en `BatchAnalysisPage` es un bug. Al revisar `backend/app/routers/batch.py`, ese módulo ya usa TTL uniforme de 24h desde el backend — el frontend sin tope de expiración simplemente refleja correctamente que su backend vive 24h fijo. No es un bug que arreglar por igualar a la fuerza; es un frontend que nunca mostró mensaje de expiración, cosa distinta.

**Variable omitida:** cada vista de batch (PDFs vs análisis) tiene su propio backend con su propia semántica de vida — igualar los dos frontends a ciegas podría introducir una regresión en una feature que hoy funciona correctamente para su propio caso.

**Capacidad no considerada:** `FloatingBatchWidget` ya existe y hoy solo está cableado a la vista de análisis (`App.tsx:500-503`) — extenderlo a `conversion-masiva` evita construir un componente de notificación nuevo desde cero.

**Alternativa no obvia:** en vez de "unificar comportamiento", alinear el TTL de `localStorage` de `ConversionMasivaPage` al TTL real de su propio backend (24h, tras Fase 2) — igual que `BatchAnalysisPage` ya hace correctamente con el suyo.

**Precondición dura, verificada al revisar el código (no asumida):** esta fase depende de que la Fase 2 ya esté desplegada en producción. Se confirmó que `watchBatchProgress` (`frontend/src/lib/pdf-download.ts:238-301`) sí hace un fetch de snapshot inmediato al reconectar (línea 298, no solo escucha eventos futuros de Pusher) — así que el código de reconexión en sí ya está bien hecho para detectar un batch terminado hace horas y resolverlo de inmediato. El único motivo por el que hoy no falla es que `ACTIVE_BATCH_MAX_AGE_MS` (45 min) es más corto que el TTL de Redis que consume ese snapshot (1h) — si se extiende la constante del frontend sin haber corregido antes el TTL del backend, el usuario vería explícitamente "Lote no encontrado" en vez de que el link simplemente dejara de aparecer. No requiere ningún cambio de código adicional en esta fase más allá del ya planeado — solo requiere respetar el orden de despliegue.

### Plan de la fase

1. En `frontend/src/components/ConversionMasivaPage.tsx`, cambiar `ACTIVE_BATCH_MAX_AGE_MS` de 45 min a 24h (línea 85), consistente con el TTL real del backend tras la Fase 2.
2. Mostrar el `batch_id` como URL persistente y copiable en la UI (hoy no se muestra en ningún punto) — un campo de texto con botón "Copiar link".
3. Agregar botón de compartir nativo (`navigator.share()` con fallback a copiar-al-portapapeles si el navegador no lo soporta) junto al link — cubre el caso "llevar el link a otro dispositivo" sin construir infraestructura de correo.
4. Mostrar mensaje explícito al recuperar un batch desde `localStorage` ("Recuperamos tu lote anterior") en vez de la reconstrucción silenciosa actual (`ConversionMasivaPage.tsx:236-251`).
5. Extender `FloatingBatchWidget` para que también se muestre cuando hay un batch de PDFs corriendo y el usuario navega a otra vista (hoy solo está atado a `'masivo'`, `App.tsx:500-503`).
6. En `BatchAnalysisPage.tsx`, agregar el mismo mensaje explícito de recuperación (mejora de consistencia de UX, no un fix de bug) — no se toca su TTL, porque ya es correcto respecto a su backend.

---

## Fase 4 — Medición mínima antes de considerar correo

### Decision-expander

**Mal asumido:** el plan original proponía construir envío de correo (con proveedor Resend elegido de forma unilateral, sin validar contra restricciones reales del proyecto: dominio verificado, cuenta existente, volumen esperado) como Fase 2, antes de confirmar que el botón de compartir/copiar de Fase 3 no fuera suficiente. Eso es sobre-construir: mete un proveedor externo nuevo, una superficie de PII nueva (emails, dato personal que hoy el sistema no maneja en absoluto), y lógica de fallback de entrega — para un problema que el botón nativo de compartir probablemente ya resuelve en la mayoría de los casos reales.

**Variable omitida:** el tamaño real de la audiencia de esta herramienta. Es interna — si la usa un equipo pequeño, "medir uso durante semanas" tiene una señal más lenta que simplemente preguntar directamente al equipo si el caso "necesito el PDF en otro dispositivo" ocurre seguido.

**Capacidad no considerada:** ya existe Sentry integrado (`main.py:49-52`) — capturar un evento simple (`sentry_sdk.capture_message`) al usar el botón de compartir/copiar no requiere ninguna infraestructura de analítica nueva.

**Riesgo de sobreestimar la necesidad:** construir correo transaccional sin evidencia de que el botón de compartir es insuficiente es exactamente el tipo de gasto que el usuario pidió evitar (cosas a medio resolver o construidas sin necesidad confirmada).

### Plan de la fase

1. Agregar un evento simple (Sentry `capture_message` o log estructurado) cada vez que se usa el botón "Compartir"/"Copiar link" de la Fase 3.
2. Preguntar directamente al equipo/usuarios reales de la herramienta si el escenario "necesito el PDF en otro dispositivo, y copiar/compartir el link no fue suficiente" ocurre con frecuencia — más rápido y más confiable que esperar señal de telemetría en una herramienta de bajo volumen interno.
3. Decisión de salida de esta fase, tomada con la evidencia de los dos puntos anteriores:
   - Si el botón de compartir/copiar cubre el caso real → **no se construye correo.** Fin del trabajo de recuperación cross-device.
   - Si se confirma que no es suficiente → recién ahí se decide proveedor de correo transaccional, validando primero si existe ya alguna cuenta/dominio corporativo antes de asumir uno nuevo.

Esta fase reemplaza la idea original de "construir correo directo" — no es un punto pendiente sin resolver, es una decisión de secuencia: no se construye infraestructura nueva de comunicación sin evidencia mínima de que la alternativa gratuita (compartir nativo) no alcanza.

---

## Fase 5 — Decisión firme: qué no se construye

### Decision-expander

Ya cubierto en profundidad por el panel original (ver documento de decisión previo). Aquí solo se nombra la condición explícita de reapertura, para que no se pierda como contexto implícito.

### Plan de la fase (no es una fase de construcción, es de cierre y documentación)

**No se construye, como decisión tomada — no como bloqueo pendiente:**
- Historial completo cross-device de batches.
- Migración a Postgres/Firestore.
- Autenticación de usuarios.
- Envío de correo transaccional (salvo que la Fase 4 confirme que es necesario).

**Razón:** sin autenticación, un historial completo expondría datos fiscales de terceros sin control de acceso real; el link persistente + compartir nativo (Fase 3) ya cubre el caso de uso reportado.

**Única condición de reapertura, nombrada explícitamente para no perderla:** si la audiencia de la herramienta cambia de "equipo interno" a "clientes externos/multi-organización", o si aparece un mandato regulatorio nuevo sobre retención de CFDIs, esta decisión completa debe revisarse desde cero — no es válida indefinidamente bajo cualquier contexto futuro.

**Acción de esta fase:** dejar este documento como registro de la decisión (ya cumplido con este archivo) — no requiere ningún cambio de código.
