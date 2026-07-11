# PROJECT_STATE — CFDI Suite (antes cfdi_inspector)
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
main

## Último cambio
Prueba de carga de Fase C con 2,000 XMLs PASÓ (2026-07-10, concurrency=1: 2000/2000 sin error,
cero signal 6/429/500). A partir de ahí, tres fixes escritos; **fix 1 de 3 ya desplegado y
promovido a 100% en producción**, los otros dos siguen en el working tree sin commitear:

**Desplegado (commit `81b3b84`, revisión Cloud Run `cfdi-suite-api-00111-huy`, 100% tráfico):**
- `backend/app/routers/pdf.py` → `download_batch_zip` reescrito con streaming real (antes
  bufferaba TODO el lote 2 veces en RAM → OOM/503 con lotes grandes, confirmado en la prueba de
  2,000 XMLs). Verificado local (2,000 PDFs reales, ~800MB, RSS pico ~115MB) y en canario contra
  GCS/Redis reales antes de promover. La verificación local encontró y corrigió un bug real de la
  primera versión del fix: `asyncio.create_task(asyncio.gather(...))` lanza `TypeError` porque
  `gather()` devuelve un Future, no una corrutina — habría roto el 100% de las descargas si se
  hubiera desplegado sin probar.

**Pendientes (sin commitear, working tree):**
- `backend/app/routers/pdf.py` (resto) — IDs de PDFs listos viajan dentro del tick de Pusher
  (`readyIds`) en vez de que el frontend pida `/ready-files` en cada tick (antes: 371 llamadas
  O(n) sobre Redis en 18 min → ahora ~2).
- `backend/app/services/canvas_service.py` — causa raíz de signal 6 encontrada (evento real en
  Sentry: `TSI_DATA_CORRUPTED` en gRPC) y fix aplicado: `ProcessPoolExecutor` ahora fuerza
  `mp_context="spawn"` en vez del `fork` por default de Linux, que copiaba el canal gRPC ya
  abierto de `CloudTasksClient` — gRPC no soporta fork con un canal vivo. Probado funcionalmente
  (2,500 filas sintéticas, PDF válido de 46 páginas), pero la rama que lo dispara (CFDI con >2000
  conceptos) nunca se activó en la prueba de 2,000 XMLs reales — puede no ser la única causa.
- `frontend/src/lib/pdf-download.ts` y `frontend/src/components/ConversionMasivaPage.tsx` —
  contraparte del fix de `readyIds`.
- Vercel: **descartado como problema real** — no había integración git rota, era un `.vercel/`
  local sobrante en la raíz del repo (ya borrado, cero impacto en producción). El deploy real
  sigue siendo 100% GitHub Actions (`deploy-frontend.yml`), que ya funcionaba bien.

## Próximo paso
Desplegar los 2 fixes restantes, con verificación entre cada uno — pedir confirmación explícita
antes de cada deploy real:
1. ~~Probar `download_batch_zip` localmente contra GCS real antes de desplegar.~~ Hecho.
2. ~~Deploy aislado del fix del ZIP → canary → verificar descarga real → promover.~~ Hecho
   (commit `81b3b84`, revisión `00111-huy`, 100% tráfico).
3. Deploy aislado de `readyIds`/Pusher + signal 6 (van juntos porque ambos tocan `pdf.py` y
   `canvas_service.py`) → canary → batch de prueba → confirmar en logs que `/ready-files` casi no
   se llama y que no hay signal 6.
4. Progreso de descarga 0→100% (punto 11 de la bitácora, sigue sin tocarse).

## Riesgos abiertos
- Signal 6: fix aplicado a la causa con evidencia real (gRPC+fork), pero NO se ha re-probado bajo
  carga real con concurrency>1 — no subir concurrency sin verificar primero con el fix desplegado.
- readyIds y signal 6 aún no están desplegados — el estado en producción para esos dos sigue
  siendo el de antes (`ready-files` O(n) por tick, signal 6 sin mitigar).
- Límites del plan free de Pusher (conexiones/mensajes) sin verificar contra volumen real.
- Credenciales de Pusher hardcodeadas en `backend/.env` versionado; Redis de pruebas con password expuesta (deliberado, rotar al salir de pruebas).
- `.secrets.baseline` debe actualizarse si se añaden nuevos archivos con valores de alta entropía legítimos
- Obligación "Implement a secrets detection strategy" en governance server requiere cierre manual
- `~/.cfdi-suite/secret.key` es la llave maestra; si se pierde, las credenciales guardadas no son recuperables
- Token personal de Sentry generado en esta sesión quedó expuesto en el chat — recomendado revocarlo desde Sentry (Settings → Developer Settings → Personal Tokens) una vez cerrado el diagnóstico de signal 6.
