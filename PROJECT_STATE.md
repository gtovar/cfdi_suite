# PROJECT_STATE — CFDI Suite (antes cfdi_inspector)
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
main

## Último cambio
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
1. **Signal 6 cerrado — sin pendientes.** Fix y `concurrency=5` confirmados en producción (ver
   "Último cambio"). Si se quiere subir a `10`+ en el futuro, correr su propia ronda de canario
   primero (no asumir que se comporta igual que `5`).
2. (Baja prioridad, sin dueño) Costo real en dólares de Cloud Run + Redis + GCS + Cloud Tasks —
   pregunta abierta desde 2026-07-10, nunca se consultó Google Cloud Billing. No bloquea nada.
3. (Sugerido, sin empezar) **Indicador de versión visible en la app** — hoy verificar qué commit
   está sirviendo producción requiere `gcloud`/Vercel dashboard (ver comandos exactos en "Último
   cambio" arriba). El usuario preguntó cómo confirmarlo sin depender de que Claude lea el hash del
   bundle en la consola del navegador; decidió dejarlo pendiente por ahora. Si se retoma: backend
   `/api/version` devolviendo `commit-sha` (ya viaja como label de Cloud Run, ver
   `deploy-backend.yml`) + mostrarlo en el frontend (footer o similar, usando
   `VERCEL_GIT_COMMIT_SHA` que Vercel expone automáticamente en el build).
4. (Menor, no bloquea) El bug cosmético de `internal_extract_zip` reintentando contra un ZIP ya
   borrado por un primer intento exitoso (`free() ` no, este es distinto — 404 "No such object")
   sigue sin corregirse; no afecta el resultado del batch (Cloud Tasks lo absorbe), solo genera
   ruido en Sentry. Ver detalle en el historial de la sesión del 2026-07-11 si se retoma.

(El progreso de descarga 0→100% ya no tiene pendientes — implementado, desplegado y verificado dos
veces con HAR real, ver "Último cambio" arriba.)

## Riesgos abiertos
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
