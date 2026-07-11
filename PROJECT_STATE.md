# PROJECT_STATE — CFDI Suite (antes cfdi_inspector)
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
main

## Último cambio
**Progreso de descarga 0→100% — implementado, desplegado el 2026-07-11 (`1164fe7`), y VERIFICADO
con datos reales de producción (batch de 150 PDFs, HAR completo auditado).** Backend en Cloud Run
`cfdi-suite-api-00095-78r` (sirviendo 100% vía `LATEST`), frontend en Vercel.

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
- **Bug real encontrado y corregido tras la auditoría**: el ZIP se estimó en 93.3MB pero el ZIP
  comprimido real pesó 62.3MB (los PDFs ya traen su propia compresión interna, así que el DEFLATE
  del ZIP les saca menos jugo del asumido) — la barra de progreso nunca llegaba a mostrar 100%, se
  quedaba en ~67% y el botón desaparecía de golpe en cuanto el navegador terminaba de recibir el
  stream. Corregido: al terminar con éxito (ZIP o PDF individual), se fuerza `loaded = total` y se
  mantiene visible ~400-500ms antes de que el botón vuelva a su estado normal, para que el usuario
  sí vea el 100% en vez de un corte abrupto. Cambio en `frontend/src/components/
  ConversionMasivaPage.tsx` únicamente (no toca backend) — pendiente de commit/push/deploy, esperando
  confirmación explícita del usuario antes de cada paso.
- El PDF individual sí llega exacto a 100% de forma natural (`Content-Length` real de GCS, sin
  estimación de por medio) — el ajuste ahí es solo para que la transición al estado final se vea
  igual de consistente, no porque tuviera el mismo bug.

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
- Confirmado (Cloud Run prod) que `ALLOWED_ORIGINS` ya incluye `https://cfdiinspector.vercel.app`,
  así que el nuevo endpoint `/estimated-size` y el `fetch()` directo al ZIP no deberían chocar con
  CORS en producción — sin verificar aún con un batch real, solo por lectura de config.
- **No probado**: el flujo completo end-to-end vía UI con un batch real subido a través de Cloud
  Tasks (requiere infra que no se puede simular en local sin desplegar a canario). Lo que sí se
  probó: la lógica de Redis (`estimated-size`) vía HTTP real contra el Redis de pruebas, y la
  lógica de `downloadWithProgress` vía tests unitarios con streams mockeados que replican el
  comportamiento real de headers (sin `Content-Length` para el ZIP, con `Content-Length` real para
  el PDF individual vía GCS).

**Durante este deploy se encontró y corrigió un bug real del pipeline (ver detalle completo en
"Riesgos abiertos" → Pin de tráfico de Cloud Run).** Resumen: el push del backend reportó
"success" pero el tráfico no se movió a la revisión nueva — causa raíz: una promoción manual de la
sesión anterior había fijado el tráfico por nombre de revisión en vez del alias `LATEST`, lo que
rompía en silencio todo deploy automático posterior vía `deploy-backend.yml`. Corregido con
`gcloud run services update-traffic cfdi-suite-api --region=us-central1 --to-latest`.

## Próximo paso
1. Cuando se quiera subir `concurrency` por encima de 1: volver a correr una prueba de carga real
   (XMLs con >2000 conceptos incluidos, para ejercitar la rama de signal 6 que la prueba de 2,000
   XMLs nunca activó) antes de tocar `cloudbuild.yaml`/`deploy-backend.yml`.
2. (Baja prioridad, sin dueño) Costo real en dólares de Cloud Run + Redis + GCS + Cloud Tasks —
   pregunta abierta desde 2026-07-10, nunca se consultó Google Cloud Billing. No bloquea nada.
3. (Sugerido, sin empezar) Correr un batch de prueba chico desde la UI real de producción para
   confirmar visualmente que la barra de progreso de descarga se comporta como se espera — es lo
   único del punto anterior que no se verificó en producción real, solo local/unitario.

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
- Signal 6: fix aplicado a la causa con evidencia real (gRPC+fork) y verificado funcionalmente en
  local y en canario para el camino normal, pero la condición exacta de producción (gRPC channel
  vivo + >2000 conceptos) NO se ha reproducido bajo carga real con concurrency>1 — no subir
  concurrency sin verificar primero.
- Límites del plan free de Pusher (conexiones/mensajes) sin verificar contra volumen real.
- Credenciales de Pusher hardcodeadas en `backend/.env` versionado; Redis de pruebas con password expuesta (deliberado, rotar al salir de pruebas).
- `.secrets.baseline` debe actualizarse si se añaden nuevos archivos con valores de alta entropía legítimos
- Obligación "Implement a secrets detection strategy" en governance server requiere cierre manual
- `~/.cfdi-suite/secret.key` es la llave maestra; si se pierde, las credenciales guardadas no son recuperables
- Token personal de Sentry generado en una sesión anterior quedó expuesto en el chat — recomendado revocarlo desde Sentry (Settings → Developer Settings → Personal Tokens) una vez cerrado el diagnóstico de signal 6.

## Historial reciente (ya en producción, para referencia)
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
  siempre apunta a la URL principal, no a la etiquetada `canary` — sigue como riesgo abierto (ver
  arriba) hasta que se pruebe bajo carga real con concurrency>1.
- Frontend (`pdf-download.ts`, `ConversionMasivaPage.tsx`): consumen `readyIds` del tick en vez
  de pedir `/ready-files`, con una reconciliación única al terminar o restaurar batch.
- Vercel: descartado como problema real — no había integración git rota, era un `.vercel/` local
  sobrante (ya borrado). El deploy real es 100% GitHub Actions (`deploy-frontend.yml`).
