# PROJECT_STATE — CFDI Suite (antes cfdi_inspector)
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
main

## Último cambio
**2026-07-22: Etapa 4 de remotezip cerrada de verdad en producción, con dos bugs reales
encontrados y corregidos en el camino, más ajuste de `SHARD_SIZE`/`THRESHOLD` y una prueba de
contención de cupo entre batches concurrentes. Detalle completo en "Extracción distribuida vía
remotezip" → "Etapa 4" y "Prueba de contención de cupo entre batches concurrentes" más abajo.**

Resumen: al pedir confirmación para "activar" `REMOTE_ZIP_SHARD_READ`, se descubrió que ya estaba
activo desde el 13 de julio sin documentar (variable pegada de un deploy de canario), y que el Job
real (`cfdi-batch-shard`) nunca se había actualizado con el código que lo soporta — un batch real
de 2000 XMLs falló 2000/2000 al probarlo. Ambos bugs corregidos y reverificados con éxito
(0 errores, PDFs reales). Después, por pedido del usuario: `BATCH_JOB_SHARD_SIZE` bajado de 100 a
20 (~3.4x más rápido, 9m38s→2m53s), `BATCH_JOB_THRESHOLD` subido de 1 a 500 (con el cruce
matemático real calculado en N≈288, umbral puesto con margen arriba de eso a propósito), y una
prueba real de 4 ejecuciones concurrentes confirmó que Cloud Run reparte el cupo de CPU de forma
justa entre "usuarios" distintos, sin acaparamiento.

**Pendiente sin resolver, abierto por el usuario, investigado pero no arreglado**: qué pasa si se
agota el plan gratuito de Redis (Upstash) — investigación completa hecha (agente Explore), con
hallazgo real: la fase de extracción y las tareas del Job de shards pueden perder trabajo o
tumbarse completas si Redis falla a mitad de proceso (varios call sites sin `try/except`, y el
propio aviso de error también depende de Redis — puede fallar en silencio). Detalle completo,
citas de línea exactas, y qué se vería el usuario en cada camino: ver conversación 2026-07-22
completa. **Diagnosticado, no arreglado** — decisión pendiente de si vale la pena la inversión.

**Fix real aplicado 2026-07-22, además de lo de Etapa 4**: `PDF_PROCESS_POOL`
(`backend/app/services/pdf_pipeline.py`) usaba `min(8, cpu_count())` para decidir cuántos procesos
crear — encontrado con una prueba de carga real (`curl` concurrente contra
`/api/internal/generate-pdf`, con `x-cloudtasks-queuename` simulado) que esto está mal fundamentado:
`cpu_count()` reporta 4 en una instancia con `--cpu=2` real (confirmado con un Job de diagnóstico
desechable, 3 formas de medirlo coinciden en 4) — `cpu_count()` refleja afinidad de CPU (cuántos
núcleos VE el proceso), no la cuota real de cómputo que Cloud Run factura y limita (cgroups). Con
carga real, solo ~2 peticiones corren a velocidad normal por instancia; más que eso no hace fila
ordenada, degrada TODAS las peticiones en vuelo (~4x más lentas) en vez de encolar limpio.
Corregido: nueva variable explícita `PDF_POOL_WORKERS` (default `2`, mismo patrón que
`BATCH_JOB_SHARD_SIZE`/`THRESHOLD` — se fija a mano para que coincida con el `--cpu` real del
deploy, no se adivina en código). Aplica tanto a `PDF_PROCESS_POOL` como al `n_workers` interno de
`generate_from_data` (facturas >2000 conceptos), que tenía el mismo problema. 219/227 tests
backend pasan (8 fallos confirmados preexistentes, no relacionados — ver "Hallazgos preexistentes"
más abajo). **`maxConcurrentDispatches` de la cola `pdf-generator-queue` subido de 8 a 20**
(`gcloud tasks queues update`), con este número real como base (10 instancias × ~2 workers reales).
Además, `REMOTE_ZIP_SHARD_READ`, `BATCH_JOB_ENABLED`, `BATCH_JOB_THRESHOLD`,
`BATCH_JOB_SHARD_SIZE`, `BATCH_JOB_NAME` — que solo existían como variables puestas a mano con
`gcloud`, el mismo patrón de fuga que causó el bug de Etapa 4 — se agregaron a `env_vars` en
`.github/workflows/deploy-backend.yml` para que queden versionadas.

**Mejora adicional el mismo día, a petición del usuario**: en vez de dejar `PDF_POOL_WORKERS=2`
fijo a mano (mismo riesgo de "hay que acordarse de cambiarlo el día que suba el `--cpu`"), se
investigó si se puede autodetectar la cuota real de CPU en vez de adivinar con `cpu_count()`.
**Verificado en vivo con otro Job de diagnóstico desechable**: Cloud Run usa cgroup v1 (no v2,
`/sys/fs/cgroup/cpu.max` no existe); `cpu.cfs_quota_us`/`cpu.cfs_period_us` sí son legibles y dieron
`161200/100000 = 1.612` → redondea a 2, coincidiendo con lo medido en la prueba de carga real.
`pdf_pipeline.py` ahora tiene `_detect_real_cpu_quota()` (lee cgroup v2 primero, cae a v1, devuelve
`None` si no puede leer o no hay límite) y `_default_pool_workers()` (redondea la cuota, respaldo
de `2` si la detección falla). `PDF_POOL_WORKERS` sigue siendo una variable de entorno explícita
para poder forzar un valor a mano si algún día la autodetección no aplica, pero ya NO se fija en
`deploy-backend.yml` — así no hay dos números que sincronizar manualmente el día que cambie el
`--cpu` del servicio, solo uno (y ese uno ahora se autoajusta). Probado en Mac local (sin cgroups
de Linux): la detección devuelve `None` correctamente y cae al respaldo de 2 sin tronar. Mismos
8 tests preexistentes fallan (no relacionados, confirmado con y sin este cambio).

**Pendiente de desplegar**: cambio de código listo en local, no subido a `origin/main` todavía —
requiere confirmación explícita antes del push (dispara `deploy-backend.yml`).

## Historial: mesa de revisión watchBatchProgress (2026-07-21, previo a lo de arriba)
**Mesa de revisión multi-agente (5 agentes) sobre un cambio ya codeado sin discusión previa
(reconciliación de progreso en `watchBatchProgress`), y rediseño completo a partir de sus
hallazgos. CONSTRUIDO, 13/13 tests nuevos pasan, `react-doctor --scope lines` 100/100. NO
DESPLEGADO A PRODUCCIÓN TODAVÍA — commits solo locales.**

**Por qué existe esto:** en la misma sesión se había implementado un cambio (reemplazar el
polling fijo de 30s de `watchBatchProgress` por un "reloj de sospecha" de 35s) directamente,
sin pausar a diseñarlo con el usuario primero. El usuario lo notó y lo dijo explícitamente
("te agarraste a codear... no rebotamos nada, no pivoteamos nada") y pidió una mesa de
revisión antes de seguir. Esta entrada documenta ese proceso completo porque el proceso en sí
es el hallazgo más importante, no solo el bug que encontró.

**La mesa — 5 agentes, cada uno con un mandato distinto, corridos en paralelo donde no
dependían entre sí:**
- **Destructor** (revisión adversarial de código): encontró el defecto raíz con línea exacta.
- **Arquitecto**: evaluó si el diseño encajaba con el resto del archivo — encontró el mismo
  defecto por su cuenta, sin ver el reporte del destructor.
- **Producto**: evaluó si el cambio resolvía un problema real — también llegó al mismo defecto
  técnico por un camino completamente distinto (leyendo el código para evaluar riesgo/beneficio,
  no buscando bugs a propósito), y agregó que nunca hubo evidencia de que el polling de 30s le
  doliera a nadie.
- **decision-expander** (skill ya existente en el proyecto, invocado por el agente): expandió la
  decisión en sí — encontró que la justificación técnica original ("un socket sano puede perder
  un mensaje en silencio") no es el modo de falla real y documentado de Pusher (que es el hueco
  de reconexión), y propuso el reencuadre que terminó ganando: no todo silencio es igual de
  peligroso, solo perder el evento TERMINAL es fatal.
- **Árbitro**: no repitió la revisión, la juzgó — verificó cada hallazgo del destructor línea por
  línea, recalibró severidades (subió uno de MEDIA a bloqueador, bajó otro de MEDIA a no
  bloqueante), y dio el veredicto que unificó la mesa.

**El defecto raíz que 4 de 5 agentes encontraron de forma independiente:** el reloj de
"sospecha" (una cadena de `setTimeout` que se reprograma sola con cada dato recibido) se
desarmaba **permanentemente** en tres rutas — pestaña oculta, respuesta HTTP no exitosa (no
una excepción, solo `res.ok: false` — la ruta más probable en producción según el árbitro,
porque esta app ya está documentada como propensa a 429/503 bajo carga), y un `fetch` colgado
sin timeout. El `setInterval` fijo que reemplazaba era inmune a esto porque no dependía de que
su propio callback tuviera éxito para seguir latiendo. Los 10 tests que acompañaban el cambio
original no podían detectar ninguna de estas tres rutas (mocks con `document.hidden` fijo en
`false` y respuestas siempre exitosas) — el árbitro lo llamó compuerta obligatoria, no nota al
pie.

**Decisión del usuario, viendo la lista completa de 13 hallazgos:** en vez del parche mínimo que
recomendaba el árbitro (rearmar el reloj siempre, agregar timeout), eligió el rediseño completo
que proponía decision-expander — reencuadrar el problema por "garantizar el evento terminal", no
"cualquier silencio es sospechoso".

**Diseño final implementado (`frontend/src/lib/pdf-download.ts`, función `watchBatchProgress`):**
tres piezas independientes reemplazan el reloj de sospecha:
1. Reconciliar en cada transición de estado de Pusher (`state_change`, verificado contra el
   código fuente instalado de `pusher-js` — API real, no supuesta) — ataca el hueco de
   reconexión real, no un socket sano perdiendo mensajes sueltos.
2. Red de seguridad de intervalo FIJO (`setInterval` real, 75s, deliberadamente largo porque
   Pusher publica por conteo — cada 5 archivos, `PUBLISH_EVERY_N_JOBS` en
   `backend/app/services/batch_progress.py:26` — no por tiempo) — estructuralmente inmune al
   defecto raíz porque no depende de que su callback tenga éxito.
3. Reconciliar al volver la pestaña a primer plano (`visibilitychange`, mismo patrón ya usado en
   `subscribeWithRetry`, mismo archivo — reutilizado, no reinventado).

**13 tests nuevos, reemplazando los 10 anteriores** — incluyen las dos pruebas de regresión
directa que antes no existían: la red de seguridad sobrevive a una respuesta no exitosa, y
sobrevive a la pestaña oculta (ambas fallarían con el diseño anterior, confirmando que el
rediseño sí cierra el defecto). `react-doctor --scope lines`: 100/100, sin hallazgos nuevos.
Detalle completo del proceso y el diseño: `docs/progreso-tiempo-real-pusher.md`.

**Sigue sin desplegarse** — commits locales, a la espera de confirmación explícita del usuario
para subir a `origin/main` (lo que dispararía `deploy-frontend.yml`/Vercel).

## Extracción distribuida vía remotezip (cerrado, ver historial abajo)
**Causa raíz real del cuello de botella de extracción encontrada (límite de red de 600 Mbps por
instancia de Cloud Run, confirmado con Cloud Monitoring) y arreglo diseñado + implementado:
extracción distribuida vía lectura remota por rangos del ZIP (remotezip). CONSTRUIDO, 227/227
TESTS PASAN, VERIFICADO EN CANARIO REAL CON RESULTADO LIMPIO (2026-07-13). Interruptor
`REMOTE_ZIP_SHARD_READ` sigue apagado por defecto — NO DESPLEGADO A PRODUCCIÓN TODAVÍA. Detalle
completo en `docs/propuesta-arquitectura-batch.md`, sección "Lectura por rangos del ZIP: causa
raíz real, diseño y despliegue".**

- **Etapa 2 (canario real, aislado, 0% tráfico de producción) — completada, resultado limpio:**
  con el ZIP real de pruebas (2000 XMLs, 367MB), la construcción del manifiesto pasó de los 6-8
  minutos documentados a **~1.5 segundos** (confirmado con logs reales), y el tiempo total de
  punta a punta bajó de **16m41s (camino viejo) a ~10m33s (camino nuevo)** — **2000/2000 XMLs
  procesados, 0 errores, 0 advertencias**. El tiempo real por tarea del shard (~7m49s) quedó
  cómodo dentro del límite de `--task-timeout=600` (10 min) — la incógnita que el plan marcó como
  condición de aprobar/rechazar quedó resuelta sin sorpresas. Infraestructura completamente
  aislada: imagen construida manualmente sin pasar por `origin/main` (nunca disparó
  `deploy-backend.yml`), revisión canario sin tráfico con `API_URL` apuntada a sí misma, Job de
  shards **separado** (`cfdi-batch-shard-canary`, clonado del real sin tocarlo). Producción
  confirmada sin cambios durante toda la prueba.

- **La causa real, con datos de Cloud Monitoring, no teoría:** cada instancia de Cloud Run tiene
  un límite duro de red de 600 Mbps (1 Gbps con Direct VPC Egress, que este proyecto no tiene
  configurado). Durante una extracción lenta real de 2000 XMLs (10 min), la CPU nunca pasó de
  17% mientras la red estuvo saturada todo ese tiempo. Como hoy una sola instancia baja el ZIP
  completo y sube cada XML a `xml_temp/`, esa extracción está atada al límite de esa única
  instancia sin importar cuántas más tenga el servicio (`max-instances=10` no ayuda aquí —
  controla cuántos BATCHES distintos se atienden a la vez, no la velocidad de uno solo).
- **Se descartaron alternativas con evidencia real, no solo lógica:** Cloud Storage FUSE (mismo
  límite de red, además mal documentado para muchos archivos chicos, riesgo real de memoria);
  Direct VPC Egress solo (sube el límite a 1 Gbps pero requiere construir infraestructura VPC
  desde cero, este proyecto nunca ha usado la API de Compute Engine); "1,600 hilos de
  `transfer_manager` ahogando el CPU" (hipótesis de la sesión anterior, refutada con una prueba
  directa: el patrón exacto de producción reproducido en local salió 4.6x más rápido, no más
  lento).
- **La solución, verificada antes de construir nada:** el formato ZIP permite leer solo su
  directorio central (sin bajar el archivo completo) y cada entrada se comprime de forma
  independiente. Se probó `remotezip` contra el bucket real: listar 50 archivos y leer 1 completo
  bajó 0.249 MB de un ZIP de 9.18 MB (2.7%), 2 peticiones HTTP — confirma que funciona de verdad.
- **Implementado (commits locales `e6c27d2`, `1c36c39`, `4023015`, NO subidos a `origin/main`
  todavía):** `zip_manifest.py` y `gcs_range_auth.py` (nuevos, compartidos entre el constructor
  del manifiesto y cada tarea del shard, para que nunca calculen listas de job_id distintas —
  el riesgo real de este diseño). Interruptor `REMOTE_ZIP_SHARD_READ` en `pdf.py` (apagado por
  defecto). `batch_shard_worker.py` ahora puede leer su porción directo del ZIP original por
  rango, sin pasar por `xml_temp/`, cuando `ZIP_GCS_PATH` está presente. `trigger_batch_shard_job`
  propaga esa ruta a cada tarea. El ZIP original ya no se borra en este camino nuevo (N tareas
  concurrentes, sin momento único de "ya terminé") — se deja al lifecycle de GCS existente (1 día).
  227/227 tests pasan, incluidas guardas de regresión explícitas de que el camino viejo (flag
  apagado, o batch chico) queda byte-idéntico.
- **Etapa 3 (push a producción) — completada 2026-07-13, con un incidente encontrado y
  corregido:** el push disparó `deploy-backend.yml` con éxito (revisión `cfdi-suite-api-00119-n6n`,
  commit `53e5871`), pero **se repitió, por cuarta vez en este proyecto, el bug de pin de
  tráfico** — el `--no-traffic --tag` usado para el canario de la Etapa 2 dejó el tráfico fijado
  por nombre, así que el deploy "exitoso" no movió tráfico real a la revisión nueva. Detectado
  verificando `status.traffic` explícitamente (no confiando en el mensaje de éxito de GHA, tal
  como ya decía la regla documentada abajo) y corregido con confirmación explícita:
  `gcloud run services update-traffic cfdi-suite-api --to-latest`. Verificado:
  `latestRevision: True`, 100% en la revisión nueva, `/docs` → 200. **`REMOTE_ZIP_SHARD_READ`
  sigue en `false` en el servicio principal** (solo estuvo en `true` en la revisión aislada del
  canario) — el comportamiento real para usuarios no cambió con este deploy.
- **Etapa 4 — CERRADA 2026-07-22, con un bug real encontrado y corregido en el camino.** Al
  auditar el estado real antes de "activar" el interruptor, se descubrió que
  `REMOTE_ZIP_SHARD_READ=true` **ya estaba activo en el servicio principal desde el 13 de julio**
  (confirmado leyendo directamente la revisión que servía el 100% del tráfico) — esta nota decía
  lo contrario ("sigue en false") y estaba desactualizada desde ese mismo día. Causa: el deploy
  manual del canario (`gcloud run deploy --tag=canary-remotezip --no-traffic
  --update-env-vars=...`) modificó la plantilla base del servicio, no solo la revisión etiquetada
  sin tráfico — como `deploy-backend.yml` usa `env_vars` en modo merge (no reemplaza la lista
  completa), esa variable de prueba quedó pegada en cada deploy automático posterior, sin que
  nadie lo notara, durante 8+ días.
  - **Bug real encontrado en la misma auditoría (más serio que el interruptor mal documentado):**
    `BATCH_JOB_NAME` en el servicio principal apuntaba a `cfdi-batch-shard-canary` (el Job de
    pruebas, imagen `:canary-remotezip` sin mantener desde el 13 de julio) en vez de
    `cfdi-batch-shard` (el Job real). Mismo mecanismo de fuga que el interruptor: el deploy manual
    del canario dejó esa variable pegada en la plantilla base. Cualquier ZIP grande subido en esos
    8+ días se habría despachado al Job canario, no al real — sin que hubiera tráfico de ese tipo
    en la ventana para que se notara (los únicos logs de `_try_remote_manifest_path` en producción
    son 3, todos del 13 de julio, día del propio canario).
  - **Corregido** con `gcloud run services update --update-env-vars=BATCH_JOB_NAME=cfdi-batch-shard`
    (corrido por el usuario vía `!`, bloqueado para el asistente por el clasificador de modo
    automático — acción de producción). Verificado: `latestRevision: True`, 100% en
    `cfdi-suite-api-00121-ggf`, `BATCH_JOB_NAME=cfdi-batch-shard`, `REMOTE_ZIP_SHARD_READ=true`.
  - **Limpieza completada**: etiqueta `canary-remotezip` removida de `cfdi-suite-api-00149-yos`
    (`update-traffic --remove-tags`), Job `cfdi-batch-shard-canary` borrado. Confirmado: tráfico
    solo en `LATEST`, único Job activo es `cfdi-batch-shard`.
  - **Estado final**: la lectura por rangos del ZIP (remotezip) está activa en producción,
    apuntando al Job correcto, sin restos de la infraestructura de prueba. Sin pendientes de esta
    etapa. **Lección para el patrón de "Riesgos abiertos" de pin de tráfico**: no es solo el
    tráfico el que se puede pegar desde un deploy manual de canario — las variables de entorno
    también, vía el modo merge de `env_vars` en `deploy-cloudrun@v2`. Verificar ambos tras
    cualquier canario con `--tag`/`--no-traffic`, no solo `status.traffic`.
  - **Segundo bug real encontrado y corregido el mismo día, más serio que el anterior**: al
    corregir `BATCH_JOB_NAME` de vuelta a `cfdi-batch-shard` (el Job "real"), una prueba en vivo
    con el ZIP real de 2000 XMLs falló: 2000/2000 errores, ZIP final vacío (22KB). Causa
    confirmada en logs reales: `[batch_shard_worker] error procesando <job_id>: xml_temp/<job_id>.xml
    no existe`. El Job real nunca se había redesplegado con el código de remotezip —
    `metadata.creationTimestamp` de `cfdi-batch-shard` marcaba 2026-07-12T08:25:41Z, **11 horas
    antes** de los commits que agregaron el soporte de `ZIP_GCS_PATH` (`e6c27d2`/`1c36c39`/`4023015`,
    esa misma tarde 19:40-19:50). Solo el Job canario (ya borrado) tenía la imagen actualizada,
    construida a propósito para su prueba — nadie había vuelto a correr
    `infra/deploy-batch-shard-job.sh` contra el Job real desde entonces.
    - **Corregido** con `gcloud run jobs update cfdi-batch-shard --image=...:latest` (imagen
      `:latest` de Artifact Registry, confirmada idéntica al digest que corre hoy
      `cfdi-suite-api`) — cambio acotado solo a la imagen, sin tocar las credenciales
      (`REDIS_PASSWORD`, `PUSHER_*`) que el Job ya tenía configuradas a mano desde el 12 de julio.
    - **Reverificado con el mismo ZIP real de 2000 XMLs, de punta a punta vía el sitio**: 20
      tareas, cada una logueando explícitamente `"procesando 100 XMLs... (lectura remota por
      rango, sin xml_temp/)"`, cero errores, ejecución completa en 9m38.75s, PDFs reales
      confirmados en el ZIP descargado por el usuario. **Etapa 4 cerrada de verdad, sin
      pendientes.**
    - **Lección añadida**: el Job de Cloud Run (`cfdi-batch-shard`) es un recurso de despliegue
      manual, no se actualiza solo con cada push a `main` (a diferencia del servicio principal,
      que sí tiene `deploy-backend.yml`). Cualquier cambio de código que afecte
      `batch_shard_worker.py` necesita su propio `gcloud run jobs update --image=...` explícito
      después del push — no asumir que "ya está en `main`" significa "ya está corriendo en el
      Job".

## Prueba de contención de cupo entre batches concurrentes (cerrado, 2026-07-22)
**Pregunta real que originó esto: si un usuario sube un ZIP grande y, mientras sus tareas del
Job siguen corriendo, otro usuario sube otro ZIP grande — ¿el segundo usuario espera a que el
primero termine ("reserva todo el estadio"), o Google reparte el cupo de CPU de forma justa entre
ambos? No se adivinó — se probó en vivo.**

- **Contexto necesario primero**: se bajó `BATCH_JOB_SHARD_SIZE` de 100 a 20 (más tareas paralelas
  por batch, cada una con menos XMLs) — verificado con el mismo ZIP real de 2000 XMLs: 100 tareas
  en vez de 20, tiempo total de 9m38.75s → 2m52.68s (~3.4x más rápido), 0 errores. Costo real de
  este cambio: cada tarea paga un costo fijo de arranque (~71s, medido ajustando una recta con los
  dos puntos reales de 100 y 20 XMLs/tarea: `T(k) = 71.16 + 5.076·k` segundos) que se reparte entre
  menos XMLs — por eso el tiempo por XML subió de ~5.79s a ~8.63s aunque el total bajó. Con esta
  fórmula real (no supuesta) se calculó el cruce matemático contra el camino de Cloud Tasks
  (tasa real ya documentada: 2000 XMLs/1198s ≈ 0.599s/XML) en **N≈288 XMLs** — por debajo de eso,
  Cloud Tasks es más rápido de verdad; el umbral recomendado para cambiar de camino debería ser
  más alto que el cruce exacto (ej. 400-500, donde el Job ya gana con margen claro, no un empate),
  no un número arbitrario. **Decidido y aplicado 2026-07-22: `BATCH_JOB_THRESHOLD=500`** (antes
  `1`, decisión original de "enrutar por forma, no tamaño" — ahora revertida a propósito con
  evidencia matemática de que un ZIP chico sale mejor por Cloud Tasks). En N=500 la ganancia real
  del Job es de ~127s (300.1s Cloud Tasks vs. ~172.68s Job), no marginal — a diferencia del cruce
  exacto en N≈290 donde la diferencia es cero por definición. Verificado: `latestRevision: True`,
  revisión `cfdi-suite-api-00123-tr8`, env var confirmada.
- **La prueba real**: 4 ejecuciones del mismo Job (`cfdi-batch-shard`), con `batch_id` distintos e
  inventados (`contention-test-A/B/C/D`, simulando 4 usuarios independientes), disparadas casi
  simultáneamente vía `gcloud run jobs execute --async`, reutilizando el mismo ZIP real de 2000
  XMLs ya subido (sin volver a subirlo). Cada una pidió 100 tareas (`SHARD_SIZE=20`) — 400 tareas
  en total pidiendo 400 vCPUs contra la cuota real confirmada de 200 vCPUs en `us-central1`
  (`gcloud beta quotas info describe CpuAllocPerProjectRegion`), exceso deliberado de 2x para que
  el resultado no pudiera salir ambiguo.
- **Resultado, con timestamps reales**: las 4 ejecuciones arrancaron en el mismo instante exacto
  (mismo timestamp hasta microsegundos) — ninguna esperó a que otra empezara. Las 4 terminaron con
  100/100 tareas exitosas, 0 errores, en tiempos de 4m37.7s, 4m37.7s, 5m18.0s y 5m33.6s (contra
  2m52.68s corriendo sola sin competencia) — es decir, **todas se atrasaron de forma proporcional
  (~1.6x-1.9x más lentas), ninguna se quedó esperando en cero mientras otra acaparaba el cupo.**
- **Veredicto**: Cloud Run reparte el cupo de CPU de forma razonablemente justa entre ejecuciones
  de Job que compiten por la misma cuota regional — el patrón de "el primero reserva todo el
  estadio" no se confirmó. **No hace falta construir un control de admisión propio (cola, límite
  de tareas por ejecución, etc.) para este riesgo** — la plataforma ya lo resuelve razonablemente
  bien. Sin pendientes de esta prueba.

## Auditoría del bug de GCS del 12 de julio (cerrado, historial)
**La medición de "1.7x más lento" estaba contaminada por un bug real de duplicación (nuevo), y ese
bug ya se corrigió en código — CONSTRUIDO, TESTS PASANDO, Y DESPLEGADO (2026-07-12).**

- Auditando `gcloud logging read` sobre `cfdi-suite-api` en la ventana real de la prueba
  (11:05-11:55 UTC, 2026-07-12) se encontró: la extracción que dio 813s corrió sola durante los
  primeros ~10 minutos, y un segundo intento de Cloud Tasks llegó 10m05s después — casi
  exactamente el dispatch deadline default — mientras el primero seguía vivo, duplicando
  descarga+subida en la misma instancia. Esto confirma con evidencia real un bug que ya estaba
  anotado como "cosmético, solo ruido en Sentry" (ver Riesgos abiertos / historial): **no era
  cosmético, causaba trabajo duplicado real.**
- El traslape es consecuencia de que la extracción ya iba tarde, no la causa — el misterio de por
  qué el primer intento, corriendo solo, ya iba camino a 813s sigue sin resolverse. Se intentó
  reproducir local (Mac, Docker con `--cpus=2 --memory=2g`, y ese mismo contenedor con carga de
  CPU concurrente simulando otra petición) — las tres pruebas coincidieron entre sí (paralelo
  4-8x más rápido) y ninguna reprodujo la lentitud real de producción. Detalle completo, incluida
  la corrección honesta de que "paralelizar es malo" nunca quedó probado:
  `docs/propuesta-arquitectura-batch.md`, sección "CORRECCIÓN (2026-07-12, sesión posterior)".
- **Fix real, con evidencia, ya en código y DESPLEGADO:** `process_zip_in_background` (`backend/app/routers/
  pdf.py`) ahora toma un lock de idempotencia en Redis (`pdf:extracting_lock:{batch_id}`, `SET NX
  EX 1800`) antes de tocar GCS — un reintento que llega mientras el original sigue vivo se aborta
  de inmediato en vez de duplicar el trabajo. Se agregó instrumentación mínima (tiempo de
  descarga del ZIP vs. tiempo de extracción+subida, por separado, en logs) para que la próxima
  medición no dependa de un solo número sin desglosar. 209/209 tests pasan (nuevo:
  `test_process_zip_in_background_skips_when_lock_already_held`). **Ya en producción**, se corrigió
  el pin de tráfico que impedía que sirviera peticiones.
- **Medición limpia en producción (2026-07-12):** con el lock de idempotencia protegiendo la
  medición (confirmado: un reintento de Cloud Tasks llegó a los 10m05s y se rechazó en 55ms sin
  duplicar nada), la subida paralela con `transfer_manager` tardó **618.8s (10m18.8s)** en
  extracción+subida — de los cuales **597.5s (96.6%) fueron literalmente dentro de las llamadas a
  `transfer_manager`**, no en Redis/Pusher/lectura del ZIP. El mismo día, con el código viejo
  (secuencial), una extracción comparable tardó 359.87s. **Esta comparación es real y no está
  contaminada** — la subida sí fue más lenta en producción con paralelización, medido con
  instrumentación propia, no solo con cronómetro. Por eso se revirtió a secuencial
  (`85b301b`, ya desplegado) — decisión razonable dado el resultado.
- **CORRECCIÓN (mismo día, sesión posterior): la explicación causal de "1,600 hilos ahogando el
  CPU" se probó y NO explica la magnitud de la regresión — descartada como causa suficiente.**
  Se verificó primero que el mecanismo existe de verdad: `transfer_manager.upload_many` (código
  fuente instalado, `google-cloud-storage` 3.12.1) crea un `ThreadPoolExecutor` nuevo en cada
  llamada (`with pool_class(max_workers=...) as executor`), y como `flush_chunk` lo llama una vez
  por chunk de 20 (no una vez para todo el batch), un batch de 2000 significa ~100 ciclos de
  crear/destruir un pool de 16 hilos — el mecanismo es código real, no una suposición. Pero al
  reproducir ese patrón EXACTO en local (Docker `--cpus=2 --memory=2g`, mismo bucket real,
  N=2000, CHUNK_SIZE=20, MAX_WORKERS=16 — idéntico al código de producción). resultado: **128.0s,
  4.6x MÁS RÁPIDO que secuencial (587.8s)** — sí hay un costo real por recrear el pool (1.88x más
  lento que un solo pool persistente, que dio 68.0s), pero ese costo es demasiado pequeño para
  explicar que producción saliera 618.8s, peor que secuencial. **Ya son 5 reproducciones locales
  distintas (Mac sin límite, Docker 2CPU, Docker 2CPU+carga de CPU simulada, y ahora el patrón
  exacto de chunks) — las 5 coinciden entre sí (paralelo gana) y ninguna reproduce la lentitud
  real de Cloud Run.** Esto apunta a algo específico del entorno real de Cloud Run, no a un
  problema de código.
- **CPU descartado con datos reales de Cloud Monitoring (mismo día, sin desplegar nada nuevo) —
  el cuello de botella es de RED, no de cómputo.** El proyecto ya tiene OpenTelemetry→Cloud Trace y
  Sentry Performance (`traces_sample_rate=1.0`) instalados; además Cloud Run guarda automáticamente
  métricas de CPU/red por instancia sin necesitar ningún cambio de código. Se consultaron esas
  métricas reales (API de Cloud Monitoring) para la revisión `cfdi-suite-api-00115-rmz` durante los
  10 minutos exactos de la subida paralela lenta (22:36-22:46 UTC): **la CPU nunca pasó de 17% de
  las 2 vCPUs asignadas** (la mayoría del tiempo entre 1-15%) — descarta de raíz la hipótesis de
  "1,600 hilos ahogando el CPU". En cambio, **la red de salida (`network/sent_bytes_count`) mostró
  actividad sostenida y pesada durante los mismos 10 minutos**, cayendo a casi cero justo cuando
  terminó la subida — la instancia pasó el tiempo esperando en la red, no calculando. Conclusión:
  el cuello de botella es de red (ancho de banda, latencia de GCS bajo muchas conexiones
  simultáneas, o throttling de la infraestructura interna de Google), no de CPU.
- **Instrumentación por chunk agregada al código para acotar más, gated por interruptor apagado
  por defecto (commit `f8e5484`, desplegado, cero riesgo para producción).**
  `EXTRACTION_PARALLEL_UPLOAD` (env var, default `false`, mismo patrón que `BATCH_JOB_ENABLED`):
  apagado, el comportamiento es idéntico al secuencial ya revertido. Activo (solo pensado para un
  canario aislado sin tráfico real), usa `transfer_manager` y loguea el tiempo de CADA uno de los
  100 chunks por separado (min/mediana/p90/max al final) — la medición del 12 de julio solo tenía
  el total (618.8s), no la distribución; esto diría si la lentitud de red es pareja en los 100
  chunks o se concentra en unos pocos (conexión que se cae y reconecta, por ejemplo). 209/209 tests
  pasan. **No corrido en Cloud Run todavía** — el hallazgo de Cloud Monitoring (CPU descartado, red
  como sospechoso) ya es fuerte por sí solo; correr esta instrumentación en un canario real es el
  siguiente paso si se quiere acotar más, pendiente de decisión.

## Capa 1 (Cloud Run Job de shards) — CONSTRUIDA, DESPLEGADA Y ACTIVA EN PRODUCCIÓN
**Permanente desde 2026-07-12. El cuello de botella de extracción del ZIP, que esta sección
marcaba como "lo que queda sin resolver", ya se resolvió el 2026-07-22 (remotezip, ver
"Extracción distribuida vía remotezip" → "Etapa 4" y "Próximo paso" punto 5) — esta entrada queda
como historial de la decisión original de Capa 1, no como estado actual del umbral.**

- `BATCH_JOB_ENABLED=true` sigue vigente. `BATCH_JOB_THRESHOLD` **cambió de `1` a `500` el
  2026-07-22** (ver "Próximo paso" punto 5 para la razón matemática) — la decisión original de
  "enrutar por forma, no por tamaño" (razonamiento original abajo, ya no vigente tal cual) se
  revirtió con evidencia real de que un ZIP chico sale mejor por Cloud Tasks. Razonamiento
  original, para contexto histórico: tras correr `decision-expander`, se decidió enrutar por
  **forma** del trabajo, no por tamaño — un ZIP subido ya es "tipo Job" por definición (viene de
  `start-zip-gcs`), un XML suelto sigue siendo Cloud Tasks (`/cfdi/pdf/start`).
- **Comparación real medida** (no proyectada), mismo ZIP real (`mil_facturas_prueba.zip`, 367MB,
  2000 XMLs reales de Miniso), cronómetro real en los dos caminos, revisiones aisladas sin tráfico
  de producción de por medio:

  | | Extracción | Procesamiento | Total |
  |---|---:|---:|---:|
  | Camino nuevo (Job) | 7m58s | 8m43s | 16m41s |
  | Camino viejo (Cloud Tasks) | 6m13s | 19m58s | 26m11s |

  0 errores en ambos. El procesamiento sí mejoró **~2.3x** (consistente con
  `maxConcurrentDispatches=8` topando el camino viejo, mientras el Job corrió 20 tareas en
  paralelo real para este batch). **La extracción del ZIP es código idéntico en ambos caminos y
  NO mejoró — domina 6-8 de los 16-26 minutos totales.** Ninguna capa de
  `docs/propuesta-arquitectura-batch.md` (Job, motor compilado, vectorización) toca ese paso; el
  estimado original de "~30-40s para 15,000 XMLs" salió falso por un factor de ~13x, en parte por
  no haber contado la extracción como variable aparte.
- **Se intentó arreglar la extracción y salió mal en producción — lección importante.**
  Paralelizar las subidas de XML a GCS dentro de `flush_chunk` (`asyncio.gather` en vez de
  secuencial, commit `04db8cf`) perfiló 4.1x más rápido en local con un ZIP de 100 XMLs
  (62.3s→15.1s). Desplegado y medido con el ZIP real de 2000: **1.7x MÁS LENTO (813s vs 478s)**,
  no más rápido — contradice el perfilado local. Revertido el mismo día (`07b3ddd`, documentado en
  `133e35e`). Causa exacta no confirmada (sospecha: contención en el pool de conexiones a GCS o
  límite de red de la instancia bajo carga real, nunca medido). **No reintentar este approach sin
  evidencia nueva** — el perfilado local con un ZIP chico no predijo el comportamiento a escala.
- **Durante ese mismo diagnóstico se confirmó: el filesystem local de Cloud Run es RAM, no disco
  real.** `gcloud run services describe` no muestra ningún volumen montado — sin eso, `/tmp` (y
  cualquier `NamedTemporaryFile`) es tmpfs respaldado por la misma memoria del contenedor (2GiB),
  no un disco aparte. Por eso se descartó la alternativa "cada tarea del Job lee el ZIP completo
  directamente desde GCS": recrearía el mismo riesgo de OOM que ya hubo con `download_batch_zip`.
  Idea corregida (lectura por rangos/`Range` de GCS, sin bajar el ZIP completo) queda anotada, no
  construida.
- Fix menor, ya desplegado (`b097833`): la barra de progreso durante la fase de EXTRACCIÓN (antes
  de que empiece a convertir) mostraba 0% fijo — ahora muestra avance real vía Pusher (throttled
  cada 5 chunks / 100 XMLs, mismo criterio que el resto del sistema).
- Bugs reales encontrados y corregidos en vivo durante el despliegue de la Capa 1: (1) faltaban
  credenciales de Pusher en el Job — `infra/deploy-batch-shard-job.sh` nunca las incluyó, así que
  el batch se procesaba bien pero la pantalla se quedaba en 0% en silencio (`get_pusher()` se apaga
  sin tronar si faltan credenciales); corregido con `gcloud run jobs update
  --update-env-vars=PUSHER_...` a mitad de la corrida. (2) El mismo bug de pin de tráfico de
  siempre (ver "Riesgos abiertos") volvió a pasar por una tercera vez, esta vez por un tag de
  canario de estas pruebas (`test-old-path`) — corregido con `--to-latest`, verificado.
- Detalle completo (Rondas 0/0.5/1 de decisión, perfilado de `generate()`, el fix de
  `FontConfiguration` de WeasyPrint ya en producción — ~26-35% menos tiempo por PDF — y los números
  que se probaron falsos antes de medir con datos reales): `docs/propuesta-arquitectura-batch.md`.

Ver "Próximo paso" para lo que sigue pendiente (extracción del ZIP a escala, decisiones de negocio
sobre Capa 2/typst).

## Plan de recuperación de PDFs de batches (cerrado, historial)
**Fases 1-5 COMPLETAS Y DESPLEGADAS EN PRODUCCIÓN, 2026-07-12 (previo a la Capa 1 de arriba). Sin
pendientes de código ni de deploy.**

- Backend (Fases 1+2): deploy manual inicial commit `dd6c8ad` (revisión `00102-sfs`), luego
  re-desplegado automáticamente por `deploy-backend.yml` en el push de las Fases 3+4 (mismo
  código, revisión `00103-mpk` final) — `latestRevision: True` confirmado en ambos casos.
- Frontend (Fases 3+4): push a `main` (`8e43cc5`) disparó `deploy-frontend.yml` → Vercel,
  exitoso. Verificado con Playwright **directo contra `cfdiinspector.vercel.app`** (no solo
  local): `?batch=<id>` carga la vista correcta, banner de recuperación, link persistente con la
  URL correcta, botones Copiar/Compartir presentes, 0 mutaciones de DOM en 2s (confirma que el fix
  del loop de render también resiste en producción real).
- Fase 5: solo documentación, ya cumplida por el propio plan.

**Verificación del deploy de backend (`00102-sfs`)**: `status.traffic` confirmó
`{'latestRevision': True, 'percent': 100, 'revisionName': 'cfdi-suite-api-00102-sfs'}` — el deploy
manual vía `cloudbuild.yaml` (sin `--tag`/`--no-traffic`) sí siguió `LATEST` correctamente, no
repitió el bug de pin de tráfico. **Hallazgo nuevo**: el label `commit-sha` de la revisión quedó
con el valor del deploy anterior (`31c6836`, `managed-by=github-actions`) — ese label solo lo
actualiza el pipeline de GitHub Actions (`deploy-backend.yml`), no el path manual de
`cloudbuild.yaml`. Para deploys manuales, verificar por **dígest de imagen** en vez de por ese
label: `gcloud run revisions describe <rev> --format="value(spec.containers[0].image)"` debe
coincidir con el digest que `gcloud builds submit` reportó al hacer push. Confirmado que coincidía
(`sha256:09a5fa6c1...`). Variables de entorno confirmadas intactas (nombres, no valores):
`ALLOWED_ORIGINS, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, MODE, API_URL, SENTRY_DSN, PUSHER_*,
GCS_BUCKET_NAME`. Smoke test: `/docs` → 200, `/download-url` de un job inexistente → 404.

**Bug serio encontrado y corregido tras el commit de Fase 3 (`07c4a3b`)**: el efecto que propaga
progreso de `ConversionMasivaPage` a `App.tsx` incluía `onProgressUpdate` en sus dependencias —
como App.tsx pasa esa prop como arrow function inline (identidad nueva cada render), esto era un
ciclo de render autosostenido mientras hubiera un batch activo, no detectable por el test unitario
(mock estable) ni por el primer smoke test con Playwright (`textContent` se ve normal en pleno
churn). Corregido excluyendo `onProgressUpdate` de las deps, igual que ya hacía
`BatchAnalysisPage` (el patrón que se estaba replicando, con ese detalle no copiado en el primer
intento). Verificado con un segundo chequeo de Playwright: 0 mutaciones DOM en 2s con
`?batch=<id>` activo.

- **Fase 1 (auditoría)**: lifecycle real de GCS confirmado vía `gsutil`/`gcloud` — 1 día, igual en
  `uploads/`, `xml_temp/`, `pdfs/` — versionado en `infra/gcs-lifecycle.json`. Límite real de
  Upstash confirmado vía su Management API (`api.upstash.com/v2/redis/databases`, credencial
  proporcionada por el usuario en esta sesión): el "10,000/día" que decía `pdf.py` era en realidad
  `db_max_commands_per_second` (límite de tasa, no diario) — el número real es
  `db_request_limit=500,000/mes`, que ya coincidía con `docs/progreso-tiempo-real-pusher.md`.
  `eviction: false` confirmado (Upstash no desaloja antes del TTL nominal).
- **Fase 2 (backend)**: `blob.exists()` agregado antes de firmar/servir un PDF en `/download` y
  `/download-url` (bug puro, antes devolvía un link roto en vez de 404). TTL de las claves de
  metadata de batch en Redis (`pdf:batch_ids`, `pdf:extracting_total`, `pdf:ready_recent`,
  `pdf:done_count`, `pdf:error_count`, y el status por-job `pdf:status:{job_id}` para "done"/"error")
  subido de 3600s a 86400s vía constante única `BATCH_METADATA_TTL_SECONDS`. **Bug encontrado en
  revisión (advisor) tras el primer commit de TTL**: el status "error" por-job seguía en 30 min
  mientras `batch_ids` ya vivía 24h — un batch con errores recuperado después de 30 min quedaba
  atascado en "processing" para siempre. Corregido en un commit separado (`b94e301`), con TDD.
  200/200 tests backend pasando.
- **Fase 3 (frontend)**: `ACTIVE_BATCH_MAX_AGE_MS` 45min→24h; link persistente y copiable del
  batch (`?batch=<id>`) visible desde que se conoce el batchId; botón compartir nativo
  (`navigator.share`, fallback a copiar); restauración vía URL compartida con prioridad sobre
  localStorage (funciona en otro dispositivo); mensaje explícito de recuperación en
  `ConversionMasivaPage` y `BatchAnalysisPage`; `FloatingBatchWidget` extendido a batches de PDFs
  (montaje persistente + `onProgressUpdate`, mismo patrón que `BatchAnalysisPage`). Verificado con
  Playwright contra el dev server real (no solo unit tests) — encontró y corrigió dos gaps que el
  análisis original no había previsto: el link no aparecía hasta el primer snapshot de progreso
  (movido a un bloque independiente), y el widget flotante no se activaba mientras se esperaba ese
  mismo primer snapshot (el efecto que propaga progreso a `App.tsx` ahora dispara desde que el
  batch arranca, no solo cuando ya hay datos).
- **Fase 4 (código)**: `Sentry.captureMessage` al usar "Copiar link"/"Compartir" (sin PII). La
  decisión de si construir correo transaccional queda pendiente de una respuesta del equipo —
  eso no es código, es una pregunta que solo el usuario puede resolver.
- **Fase 5**: decisión de qué NO se construye, ya documentada en el plan — sin código.

**Pendiente — ya no es deploy, es una decisión de negocio:**
1. Confirmar con el equipo si "necesito el PDF en otro dispositivo, y copiar/compartir no fue
   suficiente" ocurre seguido (telemetría de Sentry ya activa en producción, evento
   `pdf_batch_link_copied`/`pdf_batch_link_shared`) — determina si la Fase 4 termina ahí o si se
   construye correo transaccional. Sin esto no se toma esa decisión ni se construye nada nuevo.
2. Limpieza sin urgencia: dos revisiones canario viejas de la sesión de Signal 6 con tags activos
   sin tráfico (`canary` → `00113-log`, `canary-c5` → `00121-kiy`) — ninguna afecta producción,
   se pueden borrar cuando ya no se necesiten para más pruebas.

## Signal 6 (cerrado, historial)
**Signal 6: RESUELTO DE PUNTA A PUNTA — fix en producción (`e1d8238`) y `concurrency=5` YA
DESPLEGADO Y VERIFICADO en producción (commit `31c6836`, revisión `cfdi-suite-api-00101-tbk`,
2026-07-11). Sin pendientes.**

**Verificación final del deploy de `concurrency=5`**: tras el push, `gcloud run services
describe ... status.traffic` confirmó `latestRevision: true`, 100% en `00101-tbk`, `commit-sha:
31c683676b1ad384d3189ccc14b883b25800158d`, `containerConcurrency: 5`, health check `/docs` → 200.
Esta vez el deploy automático SÍ movió el tráfico correctamente (no hubo canarios manuales de por
medio entre este push y la verificación).

**Incidente durante el despliegue — el pin de tráfico volvió a pasar, esta vez autoinfligido**: el
push activó `deploy-backend.yml` y GitHub Actions reportó "success", pero el tráfico se quedó
100% en la revisión vieja (`00095-78r`, sin el fix) — mis propios deploys manuales del canario
(`gcloud run deploy --tag=canary-c5 --no-traffic`, usados para las pruebas) dejaron el servicio
con el tráfico fijado por nombre de revisión en vez de seguir `LATEST`, exactamente el mismo
patrón de bug ya documentado abajo (Riesgos abiertos → Pin de tráfico), solo que esta vez lo causé
yo con los canarios, no una promoción manual del dashboard. Corregido con
`gcloud run services update-traffic cfdi-suite-api --region=us-central1 --to-latest` (confirmado
por el usuario aparte, como acción de producción). Verificado después: `commit-sha: e1d8238...`,
`concurrency: 1`, servicio saludable (`/docs` 200). **Regla reforzada**: cualquier `gcloud run
deploy` con `--tag`/`--no-traffic` (incluyendo para canarios de prueba) puede repinnear el
tráfico — correr `--to-latest` después de terminar de usar un canario, no solo tras promociones
manuales por nombre.

- Confirmado primero que el riesgo era real: revisión canario `cfdi-suite-api-00120-xud`
  (`concurrency=5`, sin tráfico de producción) con `mil_facturas_prueba.zip` (1,600/2,000 XMLs
  reales de Miniso con miles de conceptos) produjo **3 crashes reales** — `free(): invalid next
  size (fast)` (corrupción de heap real de glibc) seguido de `Uncaught signal: 6` / `Container
  terminated on signal 6` en los logs de Cloud Run.
- **Causa real**: el fix anterior (`mp_context="spawn"` en `canvas_service.py`) solo aislaba el
  render de la tabla de conceptos, y solo cuando el XML tiene >2000 conceptos. Pero `generate()`
  (`pdf_pipeline.py`) también renderiza el header con **WeasyPrint** y hace el merge final con
  **pypdf** — estos pasos corrían SIEMPRE en el proceso compartido de la petición HTTP, sin
  aislar, sin importar la complejidad del XML. Bajo `concurrency>1`, dos peticiones con trabajo
  nativo (WeasyPrint/reportlab/lxml) en vuelo al mismo tiempo, en el mismo proceso, corrompían el
  heap compartido.
- **Fix**: pool de procesos persistente (`PDF_PROCESS_POOL` en `backend/app/services/
  pdf_pipeline.py`, `spawn`, creado una vez, no por petición) que aísla el `generate()` COMPLETO
  (header + tabla + merge) de cada PDF en su propio proceso — no solo el caso >2000 conceptos.
  `internal_generate_pdf` (`pdf.py`) ahora somete el trabajo vía `loop.run_in_executor(...)` en
  vez de llamarlo síncrono in-process (de paso corrige que antes bloqueaba el event loop mientras
  duraba el render). El `ProcessPoolExecutor` anidado que existía dentro de `render_conceptos`
  para >2000 conceptos se eliminó (procesos hijos de un worker no siempre pueden tener sus propios
  hijos) — esos documentos ahora renderizan sus chunks secuencialmente dentro de su worker
  asignado, en vez de repartirlos entre varios núcleos.
- **Costo medido localmente** (XML real de Miniso, 2.17MB): worker "frío" (primera petición,
  paga arrancar Python + reimportar WeasyPrint/reportlab) ≈5.1s; mismo worker ya "caliente"
  ≈1.7s. El pool es persistente, así que solo los primeros `_WORKERS` jobs de una instancia recién
  levantada pagan el costo completo — el resto usa workers ya calientes. XML simple (4.4KB):
  ≈1.4s en frío. No medido aún bajo carga sostenida en producción real.
- **Verificado dos veces en canario, mismo ZIP, mismo `concurrency=5`, comparación directa**:
  - Revisión `00120-xud` (código viejo): 1998/2000, 2 errores, **3 crashes de signal 6**.
  - Revisión `00121-kiy` (código con el fix): **2000/2000, 0 errores, cero signal 6**, 7
    instancias distintas atendieron tráfico real concurrente (confirmado en logs).
- Producción **nunca se tocó** durante ninguna de las dos pruebas — siguió 100% en `00095-78r`,
  `concurrency=1`, todo el tiempo. Ambos canarios usaron `API_URL` y `ALLOWED_ORIGINS` apuntados a
  sí mismos para que ni el tráfico de Cloud Tasks ni las pruebas desde `localhost:3000` tocaran
  producción.
- **`concurrency=5` ya está en producción, confirmado.** Si más adelante se quiere subir a `10` o
  más, eso necesita su propia ronda de canario — `5` es el único valor con evidencia real detrás,
  no asumir que un número mayor se comporta igual sin probarlo.
- **Limpieza pendiente, sin urgencia**: quedan dos revisiones canario con tags activos sin tráfico
  (`canary` → `00113-log`, `canary-c5` → `00121-kiy`) y un servidor local en `localhost:3000`
  (`frontend/.env.canary.local`, gitignored) apuntando al canario — ninguno afecta producción,
  pero se pueden borrar/parar cuando ya no se necesiten para más pruebas.

## Historial (progreso de descarga 0→100%, ya en producción)
**Implementado, desplegado el 2026-07-11 (`1164fe7`), y VERIFICADO con datos reales de producción
(batch de 150 PDFs, HAR completo auditado).** Backend en Cloud Run `cfdi-suite-api-00095-78r`
(sirviendo 100% vía `LATEST`), frontend en Vercel.

**Auditoría del HAR real (batch de 150 archivos) — confirmado con datos, no solo impresión visual:**
- 8 peticiones limpias para el flujo real (`request-upload` → `start-zip-gcs` → 2×`download-url` →
  `estimated-size` → `download`), todas 200, CORS correcto en ambas (Cloud Run: `Access-Control-
  Allow-Origin: https://cfdiinspector.vercel.app`; GCS: `*`). Los ~372 `/ready-files` que se veían
  sospechosos en el HAR NO son de esta prueba — son restos de una sesión de DevTools con "Preserve
  log" activado desde una prueba de horas antes (la de 2,000 XMLs de la sesión pasada); confirmado
  por los timestamps (cluster viejo entre 21:41-21:59 UTC del día anterior, prueba real a las
  05:10-05:12 UTC).
- `pdf:size:{job_id}` se registró para los 150/150 PDFs del batch (`knownCount == totalCount` en la
  respuesta real de `estimated-size`) — confirma que el guardado en `internal_generate_pdf`
  funciona al 100%, no solo en el caso feliz probado en local.
- **Bug real encontrado y corregido tras la auditoría — commiteado (`a028b02`), DESPLEGADO el
  2026-07-11 (solo frontend vía `deploy-frontend.yml`, no tocó backend) y RE-VERIFICADO con un
  segundo HAR real tras el fix**: el ZIP se estimó en 93.3MB pero el ZIP comprimido real pesó
  62.3MB (los PDFs ya traen su propia compresión interna, así que el DEFLATE del ZIP les saca menos
  jugo del asumido) — la barra de progreso nunca llegaba a mostrar 100%, se quedaba en ~67% y el
  botón desaparecía de golpe en cuanto el navegador terminaba de recibir el stream. Corregido: al
  terminar con éxito (ZIP o PDF individual), se fuerza `loaded = total` y se mantiene visible
  ~400-500ms antes de que el botón vuelva a su estado normal. Cambio en
  `frontend/src/components/ConversionMasivaPage.tsx` únicamente.

  **Segunda auditoría post-fix (2026-07-11, batch de 20 archivos, HAR + bundle `index-DdZN1BCM.js`
  confirmado como el deploy nuevo)**: dos descargas completas del ZIP separadas por ~10.4s (clics
  deliberados, no doble-disparo), cero errores HTTP en toda la sesión. El ratio estimado/real se
  repitió casi idéntico al primer batch (11.79MB estimado vs 7.86MB real = 67%, contra 93.3MB vs
  62.3MB = 67% del batch anterior) — confirma que el hueco de compresión es un patrón consistente,
  no una casualidad de un batch en particular, así que el fix aplica de forma general y no es un
  parche para un caso aislado. Con esto la feature completa (barra 0→100% para ZIP y PDF individual)
  queda verificada con datos reales, no solo con impresión visual del usuario.
- El PDF individual sí llega exacto a 100% de forma natural (`Content-Length` real de GCS, sin
  estimación de por medio) — el ajuste ahí es solo para que la transición al estado final se vea
  igual de consistente, no porque tuviera el mismo bug.
- **CONFIRMADO — feature cerrada, sin pendientes.** El usuario preguntó cómo verificar por su
  cuenta (sin depender de que Claude lea el hash del bundle en consola) qué versión está probando.
  Respuesta que queda como referencia: frontend → pestaña "Deployments" en vercel.com, el marcado
  "Production" muestra el commit SHA exacto; backend →
  `gcloud run revisions describe <revisión-activa> --region=us-central1 --format="value(metadata.labels.'commit-sha')"`
  (la revisión activa se ve con `gcloud run services describe cfdi-suite-api --region=us-central1
  --format="table(status.traffic[0].revisionName, status.traffic[0].percent)"`). Confirmado así que
  la revisión `00095-78r` (100% del tráfico) tiene `commit-sha: 1164fe74e98db84bd88832eb7f1770e444b713ab`,
  exactamente el commit de la feature.

Detalle de lo implementado:
- `backend/app/routers/pdf.py`: `internal_generate_pdf` guarda `pdf:size:{job_id}` (bytes del PDF,
  TTL 86400s, mismo patrón que `pdf:status:{job_id}`) justo tras generarlo. Nuevo endpoint
  `GET /cfdi/pdf/batch/{batch_id}/estimated-size` que suma esos tamaños vía `mget` (mismo patrón
  que `list_ready_files`) — necesario porque la asunción original de esta nota estaba mal:
  `download_batch_zip` es un `StreamingResponse` que arma el ZIP al vuelo, así que nunca tiene
  `Content-Length` real (el tamaño final no se conoce hasta terminar de comprimir el último PDF).
  Verificado con HTTP real contra el Redis de pruebas (`estimated-size` devuelve la suma correcta,
  ignorando jobs sin tamaño registrado).
- `frontend/src/lib/pdf-download.ts`: `downloadWithProgress(url, knownTotal, onProgress)` — fetch
  + `ReadableStream`/`getReader()`, usa `Content-Length` si existe o el `knownTotal` externo si no
  (caso del ZIP). `fetchZipEstimatedSize(batchId)` pega al endpoint nuevo. Cubierto por
  `pdf-download.test.ts` (nuevo, 5 tests, mockeando `fetch`/`ReadableStream`).
- `frontend/src/components/ConversionMasivaPage.tsx`: `handleDownloadReadyFile` usa
  `downloadWithProgress` siempre (el PDF individual es una signed URL de GCS que sí trae
  `Content-Length` real — confirmado que el bucket ya tiene CORS `origin: "*"` para GET).
  `handleDownloadBatchZip` primero pide el tamaño estimado; si se desconoce (batches con PDFs
  generados antes de este deploy, sin `pdf:size`) o supera `ZIP_PROGRESS_SIZE_LIMIT_BYTES` (500MB),
  cae a la navegación directa de siempre (sin barra) — decisión explícita del usuario, porque
  fetch+ReadableStream retiene el ZIP completo en memoria del navegador antes de poder guardarlo
  (a diferencia de `window.open`, que deja al navegador nativo ir escribiendo a disco), y un lote
  muy grande podría tronar la pestaña.
- Bug encontrado y corregido durante la verificación: la primera versión del fallback usaba
  `window.open()` después de un `await` — ya no cuenta como gesto del usuario y el popup blocker
  lo cancela en silencio (mismo motivo por el que `handleDownloadReadyFile` ya usaba
  `window.location.assign` en vez de `open`). Corregido antes de probar.
- `ALLOWED_ORIGINS` (Cloud Run prod) incluye `https://cfdiinspector.vercel.app` — confirmado tanto
  por lectura de config como, después, por los dos HAR reales (headers `access-control-allow-origin`
  correctos en ambas descargas de prueba, ver arriba). Sin sorpresas de CORS en producción.
- El flujo completo end-to-end vía UI con batches reales (Cloud Tasks real, no simulado) SÍ se
  probó — dos veces, con HAR auditado, ver el bloque de arriba. Antes del primer deploy solo se
  había probado local/unitario (Redis de pruebas + tests con streams mockeados); la verificación
  end-to-end con Cloud Tasks real solo era posible una vez desplegado, y ya se hizo.

**Durante este deploy se encontró y corrigió un bug real del pipeline (ver detalle completo en
"Riesgos abiertos" → Pin de tráfico de Cloud Run).** Resumen: el push del backend reportó
"success" pero el tráfico no se movió a la revisión nueva — causa raíz: una promoción manual de la
sesión anterior había fijado el tráfico por nombre de revisión en vez del alias `LATEST`, lo que
rompía en silencio todo deploy automático posterior vía `deploy-backend.yml`. Corregido con
`gcloud run services update-traffic cfdi-suite-api --region=us-central1 --to-latest`.

## Próximo paso
0. **Plan de recuperación de PDFs de batches — código listo en local, falta desplegar.** Pedir
   confirmación explícita antes de cada deploy: primero Fase 2 (backend, commits `be07d0b` +
   `b94e301`), verificar en producción, y solo entonces Fase 3 (frontend, `5c29a27`) + Fase 4
   (`93d48c1`). Ver "Último cambio" arriba para el detalle completo y por qué el orden importa.
1. **Signal 6 cerrado — sin pendientes.** Fix y `concurrency=5` confirmados en producción (ver
   "Signal 6 (cerrado, historial)"). Si se quiere subir a `10`+ en el futuro, correr su propia
   ronda de canario primero (no asumir que se comporta igual que `5`).
2. (Baja prioridad, sin dueño) Costo real en dólares de Cloud Run + Redis + GCS + Cloud Tasks —
   pregunta abierta desde 2026-07-10, nunca se consultó Google Cloud Billing. No bloquea nada.
3. (Sugerido, sin empezar) **Indicador de versión visible en la app** — hoy verificar qué commit
   está sirviendo producción requiere `gcloud`/Vercel dashboard (ver comandos exactos en "Último
   cambio" arriba). El usuario preguntó cómo confirmarlo sin depender de que Claude lea el hash del
   bundle en la consola del navegador; decidió dejarlo pendiente por ahora. Si se retoma: backend
   `/api/version` devolviendo `commit-sha` (ya viaja como label de Cloud Run, ver
   `deploy-backend.yml`) + mostrarlo en el frontend (footer o similar, usando
   `VERCEL_GIT_COMMIT_SHA` que Vercel expone automáticamente en el build).
4. **YA NO es "menor, solo ruido en Sentry" — era síntoma de duplicación real de trabajo, ya
   corregido en código (ver "Último cambio" arriba).** Lo que se pensaba cosmético (`internal_
   extract_zip` reintentando contra un ZIP ya borrado, 404 "No such object") resultó ser el rastro
   de que Cloud Tasks duplica una extracción lenta mientras la original sigue viva. Fix con lock de
   idempotencia listo y con tests, pendiente de desplegar (confirmación explícita antes de tocar
   GCP).
5. **Escalamiento masivo — CERRADO 2026-07-22, ya no es exploración.** La Capa 1 (Cloud Run Job de
   shards) se construyó, desplegó y quedó permanente en producción. Config final:
   `BATCH_JOB_ENABLED=true`, `BATCH_JOB_THRESHOLD=500` (no `1` — revertido con evidencia
   matemática, ver "Extracción distribuida vía remotezip" → "Etapa 4"), `BATCH_JOB_SHARD_SIZE=20`,
   `REMOTE_ZIP_SHARD_READ=true`, `BATCH_JOB_NAME=cfdi-batch-shard`.
   - **Cuello de botella de extracción del ZIP a escala — RESUELTO.** La lectura por rangos
     (remotezip) que este documento anotaba como "idea corregida, no construida" ya está
     construida, desplegada y verificada de punta a punta con el ZIP real de 2000 XMLs (ver
     "Etapa 4" para los dos bugs reales que se encontraron y corrigieron en el camino). Tiempo
     total del batch de 2000: ~2m52s (antes 16-26min con el camino viejo).
   - **Cuota real de paralelismo de Cloud Run Jobs**: 200 vCPUs por región (confirmado exacto vía
     `gcloud beta quotas info describe CpuAllocPerProjectRegion`, no el "~150-200" aproximado de
     antes) — con `cpu=1` por tarea, ~200 tareas simultáneas. **Probado en vivo, no solo por
     cuota**: 4 ejecuciones concurrentes de 100 tareas cada una (400 vs 200 de cupo, 2x exceso
     deliberado) confirmaron que Cloud Run reparte el cupo de forma justa entre "usuarios"
     distintos, sin que uno acapare mientras otro espera en cero (ver "Prueba de contención de
     cupo"). No hace falta control de admisión propio.
   - **Ronda 2 (Capa 2, motor tipográfico compilado tipo typst)**: sigue viable técnicamente
     (veredicto de Ronda 0, incluye SAT/Anexo 20), pospuesta a propósito — no hay volumen real hoy
     que la justifique frente al costo de mantener un motor nuevo en Rust. Decisión de negocio, no
     técnica. Sin cambios respecto a antes.
   - **Pendiente real, sin resolver**: qué pasa si se agota el plan gratuito de Redis (Upstash) —
     pregunta del usuario, aún no investigada en el código (manejo de errores de Redis en los
     endpoints de batch). No confundir con "cerrado" — es un hueco genuino todavía abierto.

(El progreso de descarga 0→100% ya no tiene pendientes — implementado, desplegado y verificado dos
veces con HAR real, ver "Último cambio" arriba.)

## Riesgos abiertos
- **Deploys manuales de canario (`--tag`/`--no-traffic`) también pegan variables de entorno en la
  plantilla base, no solo tráfico (encontrado y corregido 2026-07-22)**: además del pin de
  tráfico ya documentado abajo, un `gcloud run deploy --tag=X --no-traffic --update-env-vars=...`
  modifica la plantilla base del servicio (`spec.template`). Como `deploy-cloudrun@v2` aplica
  `env_vars` en modo merge (no reemplaza la lista completa), cualquier variable de prueba puesta
  ahí para el canario sobrevive a todos los deploys automáticos posteriores hasta que alguien la
  quite a mano. Pasó con el canario `canary-remotezip` del 13 de julio: `REMOTE_ZIP_SHARD_READ` y
  `BATCH_JOB_NAME=cfdi-batch-shard-canary` quedaron activos en producción real durante 8+ días sin
  que nadie lo notara (ver "Extracción distribuida vía remotezip" → "Etapa 4" para el detalle
  completo y la corrección). **Regla añadida**: tras cualquier canario con `--tag`/`--no-traffic`,
  verificar no solo `status.traffic` sino también
  `gcloud run services describe <servicio> --format="value(spec.template.spec.containers[0].env)"`
  contra lo que el servicio principal debería tener — y quitar/borrar el canario en cuanto termine
  de usarse, no dejarlo "sin costo, sin prisa".
- **Pin de tráfico de Cloud Run (causa raíz encontrada y corregida 2026-07-11)**: promover tráfico
  manualmente por nombre de revisión (`gcloud run services update-traffic --to-revisions=<rev>=100`)
  deja el servicio fuera del alias `LATEST`. Efecto colateral no obvio: cada deploy automático
  posterior vía `deploy-backend.yml` (disparado por cualquier push a `main` que toque `backend/**`)
  construye una revisión nueva, pero el `ReplaceService` que emite `deploy-cloudrun@v2` reenvía el
  mismo pin explícito de tráfico en vez de moverlo a la revisión recién creada — la revisión nueva
  queda "Retired" sin servir una sola petición, y el workflow igual reporta "success". Pasó dos
  veces sin que nadie lo notara (revisión `00094-t9b` en la sesión del 07-10/07-11, y `00095-78r`
  el 07-11, esta última con código genuinamente nuevo que por este bug no llegó a producción pese
  al push exitoso) hasta que se comparó el `status.traffic` real contra lo que el deploy debía
  haber hecho, leyendo el request body real de `ReplaceService` en el audit log de Cloud Run
  (`gcloud logging read`). Corregido con
  `gcloud run services update-traffic cfdi-suite-api --region=us-central1 --to-latest` — el
  servicio ahora sigue siempre a la revisión más nueva; el tag `canary` quedó apuntando a
  `00113-log` sin tráfico, disponible para pruebas manuales vía su URL etiquetada.
  **Regla para el futuro**: después de cualquier promoción manual por nombre, o si un push a main
  "exitoso" no parece reflejarse en producción, correr
  `gcloud run services describe cfdi-suite-api --region=us-central1 --format="value(status.traffic)"`
  y confirmar que diga `latestRevision: True` — si no, repetir `--to-latest`.
  **Pasó una tercera vez** durante las pruebas de la Capa 1 (2026-07-12), esta vez por el tag
  `test-old-path` usado para la comparación medida — mismo fix, ya corregido y verificado.
  **Pasó una cuarta vez** el 2026-07-13, por el tag `canary-remotezip` del canario de extracción
  distribuida — mismo patrón exacto (deploy automático "exitoso" que no movió tráfico real), mismo
  fix. Cuatro repeticiones del mismo patrón confirman que la regla de verificar `status.traffic`
  después de CUALQUIER uso de `--tag`/`--no-traffic` (no solo tras promociones manuales) sigue
  siendo necesaria — no es un caso aislado, es predecible cada vez que se usa un canario.
- **Paralelizar I/O que perfila rápido en local puede salir más lento en producción — pero la
  medición original de "1.7x más lento" resultó contaminada, no concluyente (actualizado
  2026-07-12).** Paralelizar las subidas de XML a GCS durante la extracción del ZIP perfiló 4.1x
  más rápido en local con 100 XMLs — desplegado y medido con el ZIP real de 2000 en producción,
  salió 1.7x más lento, y se revirtió (`07b3ddd`/`133e35e`). Auditando los logs reales de Cloud
  Run después se encontró que esa medición coincidió con un reintento real de Cloud Tasks
  duplicando la extracción a medio camino (ver "Último cambio" — el bug de idempotencia, ya
  corregido). **No está probado que paralelizar sea malo en producción** — tres intentos de
  reproducir la lentitud localmente (Mac, Docker con `--cpus=2`, y con carga de CPU concurrente
  simulada) coincidieron entre sí (paralelo 4-8x más rápido) y ninguno reprodujo el resultado real.
  Regla que sí queda en pie: cualquier medición de este pipeline en producción necesita el lock de
  idempotencia activo primero (para no repetir esta contaminación) y, si es posible, desglose de
  tiempo por sub-paso, no solo latencia total — un solo número no distingue "es lento" de "se
  duplicó y por eso parece lento".
- **El filesystem local de Cloud Run (`/tmp`, cualquier `NamedTemporaryFile`) es RAM, no disco
  real — confirmado 2026-07-12.** Sin un volumen montado explícito (este servicio no tiene
  ninguno, verificado con `gcloud run services describe`), escribir a "disco" consume el mismo
  presupuesto de memoria del contenedor. Relevante para cualquier diseño futuro donde un worker
  (Job o instancia) descargue un ZIP completo a archivo temporal — a partir de cierto tamaño es el
  mismo riesgo de OOM que ya causó el rediseño de `download_batch_zip` a streaming.
- ~~Signal 6~~ — **RESUELTO 2026-07-11, ya no es un riesgo abierto.** Fix (`e1d8238`) +
  `concurrency=5` (`31c6836`) confirmados en producción (revisión `00101-tbk`). Causa real:
  `mp_context="spawn"` (fix anterior) solo aislaba la tabla de conceptos cuando el XML tenía
  >2000 conceptos — WeasyPrint (header) y pypdf (merge) seguían corriendo siempre en el proceso
  compartido de la petición. Verificado con canario real, comparación directa: código viejo
  crasheó 3 veces bajo `concurrency=5` con `mil_facturas_prueba.zip`; código con el fix, mismo
  ZIP, mismo `concurrency=5`, 2000/2000 sin error. Ver "Último cambio" para el detalle completo.
  Si se sube a `concurrency>5` en el futuro, correr su propia ronda de canario — `5` es el único
  valor probado.
- Límites del plan free de Pusher (conexiones/mensajes) sin verificar contra volumen real.
- Credenciales de Pusher hardcodeadas en `backend/.env` versionado; Redis de pruebas con password expuesta (deliberado, rotar al salir de pruebas).
- `.secrets.baseline` debe actualizarse si se añaden nuevos archivos con valores de alta entropía legítimos
- Obligación "Implement a secrets detection strategy" en governance server requiere cierre manual
- `~/.cfdi-suite/secret.key` es la llave maestra; si se pierde, las credenciales guardadas no son recuperables
- Token personal de Sentry generado en una sesión anterior quedó expuesto en el chat — recomendado revocarlo desde Sentry (Settings → Developer Settings → Personal Tokens) una vez cerrado el diagnóstico de signal 6.

## Iniciativa react-doctor — veredictos por familia (iniciada 2026-07-13)

Fuente de verdad: **`docs/react-doctor-veredictos.md`**. Baseline congelada
34/100 con 840 hallazgos en 53 reglas (post-piloto: 36/100 con 921 — el fix
del parse error de `DocumentSettings.jsx` destapó ~91 hallazgos invisibles).
Regla central: ningún hallazgo se arregla a ciegas — veredicto razonado por
familia (tiene-razón-de-ser / error-real / mejorable / falso-positivo).

Estado del piloto (completado): 6 familias veredictadas — 3 falsos positivos
suprimidos en `frontend/doctor.config.ts` (con justificación), 1 mejorable
agendado (iframe sandbox, requiere prueba en navegador), los 19 archivos
"unused" clasificados con investigación de propósito (1 resultó ser crítico
para el backend y su ruta rota se corrigió; 4 se borraron con confirmación
del usuario; 14 se conservan como feature Editor pausada), y el error TS
preexistente corregido (lint verde). Post-borrados: 36/100, 877. Política
anti-preexistentes y de código no usado ahora en `AGENTS.md`. Script
`npm run doctor` fijado a la versión local (antes `@latest`, scores no
comparables).

**Escalada a team agents (5 worktrees, una familia por agente) — código
mezclado y en producción, documentación cerrada 2026-07-21 tras quedar
incompleta por corte de contexto.** La sesión coordinadora que mezcló el
trabajo de los 5 agentes a `main` se quedó sin tokens antes de: (a) limpiar
los 5 worktrees/ramas huérfanas (`.claude/worktrees/agent-*`,
`worktree-agent-*`) y (b) escribir la evidencia de las secciones
"§Veredictos 7-10" que la tabla de `docs/react-doctor-veredictos.md` ya
referenciaba — la tabla tenía veredictos y números, pero las secciones de
evidencia no existían en ningún lado (ni en main, ni en los 5 worktrees).
Verificado 2026-07-21 que el código de main es un superset exacto de los 5
worktrees (comparado archivo por archivo, sin pérdidas) antes de borrarlos.
Al re-derivar la evidencia contra el código real se encontraron y
corrigieron 3 errores en la tabla original: conteo de `button-has-type`
(decía 15 vivos corregidos, son 14), y `control-has-associated-label` /
`label-has-associated-control` con vivo/cluster invertidos.

**Cierre completo 2026-07-21 (segunda pasada, mismo día):** las 7 familias
que habían quedado `pendiente de re-verificación individual` (`no-transition-
all`, `js-combine-iterations`, `js-flatmap-filter`, `use-lazy-motion`,
`no-autofocus`, `no-tiny-text`, y los 4 sitios vivos de
`no-static-element-interactions`/`click-events-have-key-events`) ya se
releyeron contra el código real — todas confirmadas, con una corrección de
detalle (los "4 backdrops de modal" eran en realidad 3 backdrops + 1 handle
de resize de columna, que necesita un fix distinto). Como parte de esta
pasada se encontró y corrigió además un hallazgo que **no** era parte de las
53 familias originales: el aviso de `require-reduced-motion` del hook de
pre-commit (documentado como brecha real más abajo en "Hallazgos
preexistentes") resultó ser un **falso positivo** — `main.tsx` ya tiene
`<MotionConfig reducedMotion="user">`, la regla solo no lo vio en modo
`--staged`. Sin pendientes de esta escalada. Detalle completo en
`docs/react-doctor-veredictos.md` §Veredictos 7-10. El resto de las 48
familias originales (fuera de esta escalada de 5 agentes) sigue sin
veredicto (`pendiente`) — nueva escalada futura se decide con el usuario.

## Hallazgos preexistentes encontrados al pasar (no arreglados, solo anotados)

Esta sección existe porque, en la sesión del 2026-07-12 (batch masivo/Cloud
Run Job), varias veces se dijo "esto ya fallaba antes, no es de este cambio"
sin dejar rastro en ningún lado — quedaba solo en la conversación, no en un
documento. A partir de ahora, cualquier cosa que se encuentre rota "de paso"
(no relacionada con lo que se está construyendo) se anota aquí, verificada
con evidencia (no solo "creo que ya estaba así"), para poder decidir después
si vale la pena arreglarla.

- ~~**`frontend/src/components/editor/DocumentSettings.jsx:295`** — error de
  TypeScript (`TS1005: '...' expected`) que hace fallar `npm run lint`~~
  **RESUELTO 2026-07-13** (piloto react-doctor): era un comentario JSX en
  posición de atributo. Corregido junto con la creación del
  `src/vite-env.d.ts` faltante — `npx tsc --noEmit` en verde por primera
  vez. El archivo resultó ser parte del cluster Editor desconectado (feature
  pausada). Detalle en `docs/react-doctor-veredictos.md` §Veredictos 6.
- ~~**`backend/app/providers/current_ts.py:19` — ruta rota al wrapper del
  provider fallback `current-ts`**~~ **RESUELTO 2026-07-13** (mismo día en
  que se encontró, con confirmación del usuario): `WRAPPER_PATH` apuntaba a
  `<repo>/src/...` pero el archivo vive en `<repo>/frontend/src/...` desde
  el movimiento del frontend (2026-06-03) — el provider fallback tronaba en
  silencio desde entonces. Corregidos `WRAPPER_PATH` y `cwd` (tsx vive en
  `frontend/node_modules`); probado de punta a punta con
  `CurrentTsProvider().analyze()`. Encontrado gracias a la política de
  código no usado: react-doctor marcaba el wrapper como "unused file" y la
  investigación de propósito reveló al consumidor del backend.
- **`frontend/src/components/extract-workspace/ExtractWorkspaceToolbar.test.tsx`**
  — 2 de sus tests fallan (`shows the no-search summary when the global
  search is empty` y otro similar): esperan el texto "sin busqueda global
  (todas las columnas)" pero el componente renderiza otra cosa. Confirmado
  preexistente con `git stash` (fallan igual sin los cambios de batch
  masivo). Sugiere que el componente cambió de texto/comportamiento y el
  test no se actualizó, o viceversa — no investigado cuál de los dos está
  "mal".
- ~~**Accesibilidad, proyecto completo**: el hook de pre-commit `react-doctor`
  reporta "Project uses a motion library but has no prefers-reduced-motion
  handling — required for accessibility (WCAG 2.3.3)"~~ **FALSO POSITIVO,
  cerrado 2026-07-21.** `main.tsx:22` ya tiene
  `<MotionConfig reducedMotion="user">` envolviendo toda la app — la forma
  correcta y documentada de Motion de respetar la preferencia de
  accesibilidad del sistema operativo. Confirmado leyendo la implementación
  real de la regla (`checkReducedMotion` en
  `node_modules/react-doctor/dist/index.js`): busca ese patrón exacto en
  todo el árbol vía `git grep` y, si lo encuentra en cualquier archivo, no
  reporta nada. Dos escaneos completos (`--verbose`, sin `--staged`)
  corridos el 2026-07-21 nunca mostraron este aviso; solo apareció una vez,
  en modo `--staged` del hook de commit — el modo usado por el pre-commit
  parece no incluir `main.tsx` en su barrido cuando ese archivo no es parte
  del commit. La brecha de WCAG 2.3.3 no existe; el proyecto ya la resuelve.
  Detalle en `docs/react-doctor-veredictos.md` §Veredictos 9.
- **3 tests más que fallan, encontrados al correr la suite completa del
  frontend (2026-07-13), no relacionados con el cambio de esa sesión
  (reconciliación por sospecha en `watchBatchProgress`):**
  `src/App.test.tsx` ("opens concept detail when the sidebar selects an
  impacted concept"), `src/lib/cfdi-api-client.test.ts` (2 tests, sobre
  errores HTTP sin cuerpo contractual y fallback contractual), y
  `src/components/BatchCompletionModal.test.tsx` ("icono amarillo cuando
  hay errores pero totalFiles es 0"). Confirmados preexistentes con
  `git stash` (fallan igual sin el cambio de esa sesión aplicado). No
  investigados a fondo — se suman a `ExtractWorkspaceToolbar.test.tsx` ya
  anotado arriba.
- **`frontend/src/components/ConversionMasivaPage.tsx`** — `react-doctor`
  (`--scope changed`) reporta 24 hallazgos (componente de +300 líneas,
  candidato a `useReducer` por 5 `useState` relacionados, llave de
  `localStorage` sin versión, entre otros) — confirmados preexistentes
  corriendo `--scope lines` sobre el mismo cambio (2026-07-13): "No issues
  found!", es decir, el cambio real (un comentario de una línea en ese
  archivo, más la lógica nueva en `pdf-download.ts`) no introduce nada
  nuevo — los 24 son deuda ya existente en un archivo grande, capturados
  solo porque el archivo aparece en el diff.
- **`frontend/src/lib/pdf-download.ts:220`** — `react-doctor` marca un
  `await` antes de una guarda de retorno anticipado (`async-defer-await`)
  dentro de `processGcsZip`/`startPdfZipGcs` (función existente, no tocada
  en la sesión del 2026-07-13). Probable falso positivo (el valor sí se usa,
  en el `throw` de las líneas siguientes) — no investigado a fondo, mismo
  patrón que los hallazgos de `ConversionMasivaPage.tsx`: aparece solo
  porque el archivo tiene otro cambio real más abajo, confirmado ajeno con
  `--scope lines`.

**Nota para revisar en el futuro**: si esta lista crece mucho, vale la pena
decidir si alguno de estos vale la pena arreglar, o si se quedan así a
propósito (deuda técnica aceptada). Por ahora son solo hallazgos anotados,
ninguno bloqueó ni bloqueará trabajo en curso.

## Historial reciente (ya en producción, para referencia)

**0. Arquitectura Fase C — progreso en tiempo real vía Pusher (commits `8dc4a6e`, `24cfef6`,
2026-07-10 15:07-15:29). Esta entrada se había perdido de este documento en una reescritura
posterior (`6a46c81`) y se restauró tras auditar el historial de commits — todo lo siguiente
sigue vigente en el código y la infra, reverificado en vivo:**
- Diagnóstico con logs del batch que se atoraba en 98%: saturación de cola (100 tareas despachadas
  contra 10 instancias × `concurrency=1`; con `maxAttempts=3` y backoff de 0.1s las tareas morían
  en <1s). Cola de Cloud Tasks (`pdf-generator-queue`) ajustada a
  `maxConcurrentDispatches=8, maxAttempts=10, minBackoff=5s` — confirmado en vivo con
  `gcloud tasks queues describe`, sigue exacto.
- `concurrency=1` es obligatorio: `concurrency=5` bajo carga reprodujo signal 6 (heap nativo
  corrupto) a los ~4 min. Documentado en `backend/cloudbuild.yaml` y `deploy-backend.yml`
  (`--max-instances=10` alineado entre ambos).
- Workers publican avance a Pusher (canal `pdf-batch-{batch_id}`, cada 5 archivos):
  `_publish_batch_tick` (`backend/app/routers/pdf.py`) cuenta el progreso con `INCR` atómico y
  llama a `publish_batch_progress` (`backend/app/services/realtime.py`), que dispara el evento a
  Pusher. Frontend usa `watchBatchProgress` (`frontend/src/lib/pdf-download.ts`): snapshot vía
  `GET /api/cfdi/pdf/batch/{id}/status` + eventos Pusher + reconciliación cada 30s. SSE se
  conserva como fallback. Detalle de arquitectura en `docs/progreso-tiempo-real-pusher.md`.
- Techo de 600s a streams SSE (`SSE_MAX_STREAM_SECONDS` en `backend/app/routers/pdf.py`), y
  pausa de `EventSource` cuando la pestaña queda oculta (`visibilitychange` en `pdf-download.ts`)
  — evita quemar conexiones con pestañas olvidadas abiertas.
- **`batchId` persistido en `localStorage` (`cfdi-active-batch`, tope 45 min,
  `ConversionMasivaPage.tsx`): si el usuario recarga la página a medio batch, el frontend detecta
  el lote en curso y reconecta a su progreso vía Pusher en vez de obligarlo a resubir el ZIP.**
- Fix de popup blocker en descargas: `window.location.assign` en vez de `window.open` (los
  navegadores cancelan `open()` en silencio si no sigue directo a un gesto del usuario).
- `Sentry.init` en frontend (`frontend/src/main.tsx`), con el DSN del backend como fallback.

Prueba de carga de Fase C con 2,000 XMLs PASÓ (2026-07-10, concurrency=1: 2000/2000 sin error,
cero signal 6/429/500). A partir de ahí, tres fixes escritos y desplegados antes del cambio de
arriba:

**1. Commit `81b3b84`, revisión Cloud Run `cfdi-suite-api-00111-huy`:**
`download_batch_zip` reescrito con streaming real (antes bufferaba TODO el lote 2 veces en RAM →
OOM/503 con lotes grandes). Verificado local (2,000 PDFs reales, ~800MB, RSS pico ~115MB) y en
canario contra GCS/Redis reales antes de promover. La verificación local encontró y corrigió un
bug real de la primera versión del fix: `asyncio.create_task(asyncio.gather(...))` lanza
`TypeError` porque `gather()` devuelve un Future, no una corrutina — habría roto el 100% de las
descargas si se hubiera desplegado sin probar.

**2. Commit `fc26374`, revisión Cloud Run `cfdi-suite-api-00113-log` + Vercel (deploy frontend
2026-07-11 03:29 UTC):**
- `pdf.py`: IDs de PDFs listos viajan dentro del tick de Pusher (`readyIds`) en vez de que el
  frontend pida `/ready-files` en cada tick (antes: 371 llamadas O(n) sobre Redis en 18 min).
  Verificado end-to-end contra el contenedor canario real (llamada directa a
  `/api/internal/generate-pdf` simulando Cloud Tasks): el rpush respeta el umbral de publicación
  y `_publish_batch_tick` drena `ready_recent` correctamente al completar el batch.
- `canvas_service.py`: `ProcessPoolExecutor` fuerza `mp_context="spawn"` en vez de `fork` (que
  copiaba el canal gRPC ya abierto de `CloudTasksClient` — causa raíz confirmada en Sentry,
  `TSI_DATA_CORRUPTED`). Verificado localmente con 2,500 filas sintéticas bajo spawn (PDF válido
  de 46 páginas, sin `BrokenProcessPool`). No se pudo reproducir en canario la condición exacta de
  producción (canal gRPC ya abierto + >2000 conceptos en el mismo proceso) porque Cloud Tasks
  siempre apunta a la URL principal, no a la etiquetada `canary`. **Nota 2026-07-11**: esto seguía
  siendo cierto para la prueba en canario específica, pero la prueba de carga real de 2,000 XMLs
  (no canario, tráfico principal) sí incluyó la condición completa vía `mil_facturas_prueba.zip`
  — ver corrección en "Riesgos abiertos" → Signal 6. Sigue como riesgo abierto únicamente para
  `concurrency>1`.
- Frontend (`pdf-download.ts`, `ConversionMasivaPage.tsx`): consumen `readyIds` del tick en vez
  de pedir `/ready-files`, con una reconciliación única al terminar o restaurar batch.
- Vercel: descartado como problema real — no había integración git rota, era un `.vercel/` local
  sobrante (ya borrado). El deploy real es 100% GitHub Actions (`deploy-frontend.yml`).
