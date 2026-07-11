# PROJECT_STATE — CFDI Suite (antes cfdi_inspector)
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
main

## Último cambio
Prueba de carga de Fase C con 2,000 XMLs PASÓ (2026-07-10, concurrency=1: 2000/2000 sin error,
cero signal 6/429/500). A partir de ahí, tres fixes escritos — **los 3 ya están desplegados y
promovidos a 100% en producción** (backend + frontend):

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
  de 46 páginas, sin `BrokenProcessPool`). **No se pudo reproducir en canario la condición exacta
  de producción** (canal gRPC ya abierto + >2000 conceptos en el mismo proceso) porque Cloud
  Tasks siempre apunta a la URL principal, no a la etiquetada `canary` — sigue como riesgo
  abierto hasta que se pruebe bajo carga real con concurrency>1.
- Frontend (`pdf-download.ts`, `ConversionMasivaPage.tsx`): consumen `readyIds` del tick en vez
  de pedir `/ready-files`, con una reconciliación única al terminar o restaurar batch.
- Vercel: **descartado como problema real** — no había integración git rota, era un `.vercel/`
  local sobrante (ya borrado). El deploy real es 100% GitHub Actions (`deploy-frontend.yml`).

**Nota sobre el pipeline de deploy:** el repo tiene DOS mecanismos de deploy de backend
(`gcloud builds submit` manual con canary, y `deploy-backend.yml` disparado por cualquier
`git push` a `main` que toque `backend/**`, sin canario — despliega directo a 100%). Al pushear
el commit `fc26374` (toca backend Y frontend a la vez) para desplegar el frontend, se disparó
también un redeploy redundante de backend vía GitHub Actions — mismo código ya verificado, así
que no representó riesgo, pero generó una revisión (`00094-t9b`) que quedó "Retired" sin servir
tráfico real (0 requests en sus logs) mientras la revisión ya promovida manualmente (`00113-log`)
se mantuvo sirviendo 100%. Comportamiento no explicado del todo — vigilar si se repite.

## Próximo paso
Los 3 fixes de la sesión anterior ya están en producción. Sigue pendiente (sin empezar):

1. **Progreso de descarga 0→100%.** Origen: bitácora de sesión del 2026-07-10 (artifact
   `claude.ai/code/artifact/ee641292-593b-4f89-874e-4a394ca37b76`, 11 puntos — los otros 10 ya se
   verificaron resueltos el 2026-07-11 releyendo el código, así que esta referencia ya no hace
   falta mantenerla viva). El problema exacto, confirmado leyendo el código actual: tanto
   `handleDownloadBatchZip` como `handleDownloadReadyFile` en `ConversionMasivaPage.tsx` disparan
   la descarga con `window.open`/`window.location.assign` a una URL directa — eso delega el 100%
   del progreso al navegador nativo, sin ningún hook hacia la app. No hay barra, spinner ni
   porcentaje mientras se descarga un ZIP grande o un PDF individual. La *subida* del ZIP sí tiene
   esto resuelto (`XMLHttpRequest` + `xhr.upload.onprogress`) — es el mismo patrón, pero para
   descarga: reemplazar la navegación directa por `fetch` + `ReadableStream`/`response.body.getReader()`
   leyendo `Content-Length` para calcular el porcentaje, y usar `triggerBlobDownload` (ya existe en
   `pdf-download.ts`) para entregar el blob al terminar. Ver si aplica igual a ZIP consolidado
   (streaming, tamaño total conocido por `Content-Length`) y a PDF individual (mismo patrón, blob
   más chico).
2. Cuando se quiera subir `concurrency` por encima de 1: volver a correr una prueba de carga real
   (XMLs con >2000 conceptos incluidos, para ejercitar la rama de signal 6 que la prueba de 2,000
   XMLs nunca activó) antes de tocar `cloudbuild.yaml`/`deploy-backend.yml`.
3. (Baja prioridad, sin dueño) Costo real en dólares de Cloud Run + Redis + GCS + Cloud Tasks —
   pregunta abierta desde 2026-07-10, nunca se consultó Google Cloud Billing. No bloquea nada.

## Riesgos abiertos
- Signal 6: fix aplicado a la causa con evidencia real (gRPC+fork) y verificado funcionalmente en
  local y en canario para el camino normal, pero la condición exacta de producción (gRPC channel
  vivo + >2000 conceptos) NO se ha reproducido bajo carga real con concurrency>1 — no subir
  concurrency sin verificar primero.
- Límites del plan free de Pusher (conexiones/mensajes) sin verificar contra volumen real.
- Credenciales de Pusher hardcodeadas en `backend/.env` versionado; Redis de pruebas con password expuesta (deliberado, rotar al salir de pruebas).
- `.secrets.baseline` debe actualizarse si se añaden nuevos archivos con valores de alta entropía legítimos
- Obligación "Implement a secrets detection strategy" en governance server requiere cierre manual
- `~/.cfdi-suite/secret.key` es la llave maestra; si se pierde, las credenciales guardadas no son recuperables
- Token personal de Sentry generado en esta sesión quedó expuesto en el chat — recomendado revocarlo desde Sentry (Settings → Developer Settings → Personal Tokens) una vez cerrado el diagnóstico de signal 6.
