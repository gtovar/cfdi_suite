# Progreso en tiempo real del batch ZIP→PDF: de SSE+polling a Pusher

> Última actualización: 2026-07-10. Estado: en producción (backend rev `cfdi-suite-api-00091-ldf`, frontend deploy manual de Vercel).

## El problema que esto resuelve

El flujo de conversión masiva (subir ZIP → N Cloud Tasks convierten XMLs → descargar PDFs) necesita mostrar una barra de progreso. La primera implementación usaba **SSE (Server-Sent Events) con polling interno a Redis**, y tenía dos costos estructurales medidos en producción:

1. **Cada espectador ocupaba una instancia entera de Cloud Run.** El servicio corre con `concurrency=1` (obligatorio: un bug de corrupción de heap nativo — signal 6 — reaparece con concurrency>1; verificado empíricamente el 2026-07-10 con concurrency=5, crash a los ~4 min de carga). Un stream SSE es una request HTTP que vive 15+ minutos → 1 espectador = 1 de las 10 instancias máximas bloqueada sin hacer trabajo real. En la prueba del batch de 2,000 XMLs esto produjo 462 errores 429 "no available instance", ~40 tareas descartadas por reintentos agotados (batch atorado en 98%), y descargas muertas (el 429 del balanceador no lleva headers CORS, el navegador lo reporta como error CORS).
2. **Cada espectador quemaba Redis.** El generador SSE consultaba Redis cada segundo (~4-5 comandos: GET×2 + SMEMBERS + MGET) → ~4,000 comandos por batch por espectador, contra un límite de Upstash free tier de 500k/mes (`db_request_limit`, confirmado 2026-07-11 vía Management API — no eran 10,000/día como decía por error un comentario en `pdf.py`, esa cifra es en realidad `db_max_commands_per_second`, un límite de tasa distinto).

Ninguno de los dos costos escala: 500 usuarios mirando barras = 500 instancias + ~2,250 comandos Redis/segundo.

## Arquitectura actual

```
worker (Cloud Task)          Pusher (infra externa)         navegador
internal_generate_pdf ──────► canal pdf-batch-{id} ────────► pusher-js
  └ cada 5 PDFs: INCR          evento "progress"              actualiza barra
    done_count + trigger
                              GET /batch/{id}/status  ◄────── snapshot inicial
                              (request corta, ~5 cmds)        + reconciliación cada 30s
```

- **Publicación** (`backend/app/services/realtime.py` + `_publish_batch_tick` en `routers/pdf.py`): cada worker, al terminar un PDF, incrementa `pdf:done_count:{batch_id}` (INCR atómico) y publica el avance al canal `pdf-batch-{batch_id}` **cada 5 archivos** y siempre al llegar al total (~400 mensajes por batch de 2,000). Los errores solo se cuentan cuando son definitivos (XML desaparecido) — los transitorios no, porque Cloud Tasks los reintenta y sobrecontarían.
- **Suscripción** (`frontend/src/lib/pdf-download.ts` → `watchBatchProgress`): el navegador se conecta a Pusher (la conexión persistente vive en la infraestructura de Pusher, no en Cloud Run), se hidrata con un snapshot inicial vía `GET /api/cfdi/pdf/batch/{id}/status`, y reconcilia cada 30s con el mismo endpoint. Guard monotónico: la barra nunca retrocede aunque los eventos lleguen fuera de orden.
- **Fuente de verdad**: sigue siendo Redis (`_batch_progress_snapshot` calcula el estado exacto con MGET de statuses). Los contadores de Pusher son aproximados para los ticks; el snapshot corrige cualquier deriva en ≤30s.
- **Fallback**: el endpoint SSE (`/batch/{id}/progress`) sigue vivo, refactorizado sobre el mismo helper. Si Pusher está caído, la reconciliación de 30s mantiene la barra avanzando (lenta pero viva).

## Por qué no se hizo así desde el principio

SSE era la opción razonable para la primera versión: cero dependencias nuevas, un solo actor (backend), patrón estándar. Sus costos son invisibles con un usuario de prueba y un servicio sin `concurrency=1` — se volvieron dominantes cuando (a) el bug de heap forzó `concurrency=1` y (b) las pruebas con batches reales de 2,000 XMLs saturaron las instancias. Pusher ya estaba integrado en el flujo de análisis (`routers/batch.py` + `BatchAnalysisPage.tsx`), así que el costo de adopción fue bajo.

## Pros / contras (evaluación al 2026-07-10)

| | Detalle | ¿Se sostiene? |
|---|---|---|
| ✅ Cero instancias retenidas por espectadores | La conexión vive en Pusher | Sí, estructural |
| ✅ Redis: de ~4,000 a ~30-40 comandos por espectador/batch | Solo snapshot + reconciliación | Sí, estructural |
| ✅ Sin código de reconexión propio | pusher-js reconecta solo | Sí |
| ⚠️ Dependencia de un tercero | Si Pusher cae, la barra avanza a ritmo de 30s (degradación, no falla) | Mitigado por reconciliación |
| ⚠️ Límites del plan de Pusher | Free tier: del orden de 100 conexiones concurrentes y 200k mensajes/día — verificar en dashboard antes de salir de pruebas | **Pendiente de verificar** |
| ⚠️ Granularidad de 5 archivos | La barra salta de 5 en 5 | Deliberado (ajustable en `PUBLISH_EVERY_N_JOBS`) |
| ❌ No resuelve el OOM del ZIP consolidado | `download_batch_zip` bufferea todo en RAM | Problema aparte, pendiente |
| ❌ No resuelve signal 6 | Solo lo esquiva; investigarlo sigue pendiente | Problema aparte, pendiente |

## Compatibilidad con React

`pusher-js` es agnóstico de framework (WebSocket + callbacks). `watchBatchProgress` expone el mismo contrato Promise+callbacks que tenía el SSE (`waitForBatchJob`), así que `ConversionMasivaPage` no cambió su modelo de estado — solo la función que llama. El mismo patrón ya operaba en `BatchAnalysisPage` desde antes.

## Claves y canales

- La **key** de Pusher es pública por diseño (viaja en el bundle); `VITE_PUSHER_KEY`/`VITE_PUSHER_CLUSTER` en Vercel la sobreescriben. El **secret** solo vive en el backend (env vars de Cloud Run).
- Canales públicos `pdf-batch-{uuid}`: cualquiera con el batch_id (un UUID no adivinable) podría suscribirse. Aceptable en fase de pruebas; si se vuelve multi-tenant real, migrar a canales privados con endpoint de auth.
