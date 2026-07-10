# PROJECT_STATE — CFDI Suite (antes cfdi_inspector)
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
main

## Último cambio
Conversión masiva ZIP→PDF estabilizada (2026-07-10): progreso en tiempo real vía Pusher (Fase C).
- Diagnóstico con logs: el batch atorado en 98% fue saturación (cola despachaba 100 tareas contra
  10 instancias × concurrency=1; con maxAttempts=3 y backoff 0.1s las tareas morían en <1s).
  Cola ajustada: `--max-concurrent-dispatches=8 --max-attempts=10 --min-backoff=5s`.
- `concurrency=1` es OBLIGATORIO: probado concurrency=5 bajo carga → signal 6 (heap nativo corrupto)
  reapareció a los ~4 min. Documentado en `backend/cloudbuild.yaml`.
- Fase C: workers publican avance a Pusher (canal `pdf-batch-{id}`, cada 5 archivos) vía
  `services/realtime.py` + `_publish_batch_tick`; frontend usa `watchBatchProgress`
  (snapshot vía nuevo GET /batch/{id}/status + eventos Pusher + reconciliación 30s).
  SSE conservado como fallback. Ver `docs/progreso-tiempo-real-pusher.md`.
- Además: techo de 600s a streams SSE, pausa de EventSource con pestaña oculta, batchId persistido
  en localStorage (sobrevive refresh), fix popup blocker en descargas (`location.assign`),
  Sentry.init en frontend, `--max-instances=10` alineado entre cloudbuild.yaml y deploy-backend.yml.

## Próximo paso
1. Probar Fase C con batch grande (barra vía Pusher hasta 100%, consumo Redis mínimo).
2. OOM del ZIP consolidado: streaming real en `download_batch_zip` (hoy bufferea ~1,800 PDFs en RAM → 503).
3. Investigar causa raíz de signal 6 (única salida para subir concurrency).
4. Arreglar integración git de Vercel (deploys por push fallan en 0ms; usar `vercel deploy --prod` manual).
5. Progreso de descarga 0→100% (punto 11 de la bitácora).

## Riesgos abiertos
- Signal 6 (heap nativo) sin causa raíz — bloquea concurrency>1; NO subir concurrency sin re-probar.
- `download_batch_zip` truena por OOM con lotes grandes (2Gi de RAM insuficientes).
- Límites del plan free de Pusher (conexiones/mensajes) sin verificar contra volumen real.
- Credenciales de Pusher hardcodeadas en `backend/.env` versionado; Redis de pruebas con password expuesta (deliberado, rotar al salir de pruebas).
- `.secrets.baseline` debe actualizarse si se añaden nuevos archivos con valores de alta entropía legítimos
- Obligación "Implement a secrets detection strategy" en governance server requiere cierre manual
- `~/.cfdi-suite/secret.key` es la llave maestra; si se pierde, las credenciales guardadas no son recuperables
