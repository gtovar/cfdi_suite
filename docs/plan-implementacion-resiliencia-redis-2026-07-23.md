# Plan de implementación: resiliencia Redis/Pusher (post-incidente 2026-07-23)

> **Este documento es ejecutable de punta a punta por una sesión nueva sin contexto
> previo.** Si estás retomando esto en una sesión distinta: lee primero
> `docs/mesa-decision-resiliencia-redis-2026-07-23.md` (el "por qué" completo, con la
> síntesis de una mesa de 4 agentes) y `docs/propuestas-resiliencia-redis-pusher-2026-07-22.md`
> (la exploración original, un día antes). Este documento es el "qué hacer, en qué
> orden, en qué archivos" — no repite el razonamiento completo, lo referencia.

## Contexto mínimo para entender por qué existe esto

El 23 de julio de 2026, el plan gratuito de Redis (Upstash, 500,000 peticiones/mes) se
agotó por completo durante una sesión de pruebas de carga real (varias pestañas de
Chrome, lotes de 150 XMLs cada una). Esto tumbó la generación de PDFs individuales y
por lote en producción. Una mesa de 4 agentes (arquitecto, producto/UX, SRE,
destructor) analizó el incidente y produjo una síntesis con plan de acción — este
documento es ESE plan, ya traducido a pasos de código concretos.

**Nada de esto está implementado todavía** al momento de escribir este documento —
es 100% trabajo pendiente.

## Estado actual confirmado en producción (verificar que sigue así al retomar)

- Backend: revisión `cfdi-suite-api-00126-4d2` o posterior, con los fixes de hoy
  (`PDF_POOL_WORKERS` autodetectado, 8 hallazgos de code review resueltos — ver
  `PROJECT_STATE.md` sección "Segunda ronda... 8 hallazgos").
- `BATCH_JOB_THRESHOLD=500`, `BATCH_JOB_SHARD_SIZE=20`, `REMOTE_ZIP_SHARD_READ=true`.
- **Redis (Upstash) — verificar el estado de la cuota antes de retomar cualquier
  prueba real**: `gcloud logging read 'resource.type="cloud_run_revision"
  resource.labels.service_name="cfdi-suite-api" textPayload=~"max requests limit"'
  `--freshness=1d` — si sigue apareciendo, la cuota sigue agotada, no hagas pruebas de
  carga reales hasta confirmar que se liberó o se subió de plan.

## Restricciones de diseño ya decididas (no las relitigues sin nueva evidencia)

1. **El lock de idempotencia de extracción (`pdf:extracting_lock`, `pdf.py`, `SET NX`)
   se queda fail-closed.** Si Redis no responde al querer tomar el lock, NO se procede
   con la extracción de un batch nuevo. La alternativa (fail-open) reintroduce el bug
   de duplicación de extracción del 12 de julio — no lo cambies sin discutirlo primero.
2. **No implementar `pybreaker`/circuit breaker completo.** El error real de Upstash
   ("max requests limit exceeded") falla rápido, no se cuelga — no hay timeouts que
   acumular, que es el problema que un circuit breaker completo resolvería. La bandera
   de degradación pasiva (paso 5 abajo) da el mismo beneficio práctico.
3. **No construir la abstracción `ProgressReporter` completa todavía.** Es la forma
   arquitectónicamente más limpia a largo plazo (ver Propuesta 1 de
   `propuestas-resiliencia-redis-pusher-2026-07-22.md`), pero sin evidencia de que un
   segundo consumidor real la necesite hoy. Los pasos de abajo logran el mismo
   resultado práctico sin la interfaz nueva.
4. **No recalcular el total de un batch desde GCS en cada consulta de estado.** Sería
   caro y solo mueve el gasto de cuota de Redis a operaciones de GCS.

## Los pasos, en orden — cada uno cita archivo/línea real (verificado 2026-07-23)

### Paso 1 — Invertir el orden en `internal_generate_pdf` (backend/app/routers/pdf.py:118-209)

Estado actual (línea 124, la primera del `try`):
```python
async def internal_generate_pdf(payload: GeneratePdfPayload, request: Request):
    if "x-cloudtasks-queuename" not in request.headers:
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo Cloud Tasks.")

    print(f"Iniciando generación de PDF para Job ID: {payload.job_id}")
    try:
        await redis_client.set(f"pdf:status:{payload.job_id}", b"converting", ex=3600)
        # ... decodificar XML, generar PDF, subir a GCS, TODO dentro del mismo try ...
```

**Cambio**: reestructurar para que el bloque de trabajo real (decodificar XML →
`generate()` vía `PDF_PROCESS_POOL` → subir a GCS) sea el ÚNICO que puede producir un
500. Las escrituras a Redis (líneas actuales 124, 172, 176-177, 190-191) se agrupan en
un bloque posterior, protegido con su propio `try/except Exception: pass` (o mejor,
un helper compartido — ver Paso 5), que NUNCA puede convertir un PDF ya generado y
subido en un error 5xx.

Forma objetivo (pseudocódigo, ajustar al código real):
```python
try:
    # resolver xml_bytes (líneas 126-144, sin cambios en su lógica interna)
    if not xml_bytes:
        # este caso SÍ es un fallo real de trabajo (no hay XML que convertir) -> 204 está bien como hoy
        ...
        return Response(status_code=204)

    with tracer.start_as_current_span("generacion_pdf_intensiva"):
        pdf_bytes = await loop.run_in_executor(PDF_PROCESS_POOL, generate, xml_bytes, payload.template_id, payload.html_shell)

    blob = bucket.blob(f"pdfs/{payload.job_id}.pdf")
    await asyncio.to_thread(blob.upload_from_string, pdf_bytes, content_type="application/pdf")
    # <-- A PARTIR DE AQUÍ, EL TRABAJO YA ESTÁ HECHO. Nada de lo que sigue puede producir un 500.

except Exception as e:
    # SOLO fallos reales de decodificar/generar/subir llegan aquí -> 500 legítimo, Cloud Tasks reintenta con razón
    print(f"Error generando PDF {payload.job_id}: {e}")
    _safe_redis_set_status(payload.job_id, "error")  # ver Paso 5, nunca propaga
    raise HTTPException(status_code=500, detail=str(e))

# Reporte best-effort, fuera del try de arriba, nunca produce 5xx:
_safe_redis_set_status(payload.job_id, "done")  # ver Paso 5
_safe_redis_set_size(payload.job_id, len(pdf_bytes))  # ver Paso 5
_safe_cleanup_temp_xml(payload.job_id)  # try/except ya existente, líneas 177-185, mantener
if payload.batch_id:
    _safe_batch_tick(payload.batch_id)  # ver Paso 5, envuelve rpush+expire+_publish_batch_tick
return {"status": "success", "message": "PDF generado"}
```

Aplica el mismo tratamiento al branch de "XML ya no existe" (líneas 144-152) y al
`except Exception as e:` general (líneas 199-209) — sus propias escrituras a Redis
(línea 149, línea 202) también deben usar el helper del Paso 5.

### Paso 2 — Mismo tratamiento en `batch_shard_worker.py` (el defecto gemelo, peor blast radius)

Archivo: `backend/app/workers/batch_shard_worker.py`. Dos branches casi idénticas
(`zip_gcs_path` alrededor de líneas 126-166, y la normal alrededor de líneas 168-199).
En ambas, dentro del `except Exception as exc:` del loop `for job_id in my_shard:`,
la llamada a `publish_batch_tick(..., definitive_error=True)` (líneas ~163 y ~199) NO
tiene su propio `try/except` — si Redis falla justo ahí, la excepción escapa el `for`,
sube a `run_shard()`, sube a `main()`, dispara `sys.exit(1)`, y Cloud Run Job
**reintenta la tarea completa de hasta 100 XMLs**.

**Cambio**: envolver esa llamada específica (y toda escritura de Redis en el loop) con
el mismo helper del Paso 5, para que un fallo de Redis durante el reporte de un XML
individual jamás tumbe el resto del shard.

### Paso 3 — Quitar el gate redundante de Redis en las descargas individuales

Archivo: `backend/app/routers/pdf.py`.
- `download_pdf` (línea 601, función completa hasta ~621) — hoy consulta
  `pdf:status` en Redis primero (líneas ~603-605) y solo si es `"done"` llega a
  `blob.exists()` (línea ~612). **Cambio**: verificar `blob.exists()` en GCS
  directamente como la señal principal de "¿está listo?" — el chequeo de Redis puede
  quedarse como optimización/caché si responde, pero nunca como bloqueo si Redis no
  responde o dice que no está listo pero el blob SÍ existe.
- `get_pdf_download_url` (línea 680, función completa hasta ~712) — mismo patrón,
  mismo cambio (líneas ~686-688 y ~696).

**Por qué este paso es prerequisito de todo lo demás**: sin este cambio, aunque el
Paso 1 garantice que el PDF se genera y sube a GCS con Redis caído, el usuario
SEGUIRÍA sin poder descargarlo — el gate de lectura es el cuello de botella real, no
solo la escritura.

### Paso 4 — Corregir la clasificación de error de cuota de Upstash

Archivo: `backend/app/routers/pdf.py`, líneas 206-208 actuales:
```python
error_str = str(e).lower()
if "quota exceeded" in error_str or "oom" in error_str:
    raise HTTPException(status_code=429, detail="El motor de procesamiento está a máxima capacidad.")
```
El mensaje real de Upstash es `"max requests limit exceeded"` — no coincide con
ninguna de las dos cadenas buscadas, así que esta rama nunca se activa hoy.

**Cambio**: crear un helper compartido (sugerido: nuevo archivo
`backend/app/services/redis_errors.py`, o una función en `cpu_quota.py`-adyacente si
se prefiere no crear otro archivo — decisión de quien implemente) `is_redis_quota_error(exc) -> bool`
que reconozca los patrones reales: `"max requests limit exceeded"`,
`"max daily request limit"`, `"max_requests_limit"`. Usarlo en los tres lugares que
instancian cliente Redis (`pdf.py:64` aprox., `batch.py`, `batch_shard_worker.py:53`)
para decidir tanto el código de respuesta (429) como para activar la bandera del
Paso 5.

**Nota de alcance honesta (ya la dio SRE en la mesa)**: este fix por sí solo NO
detiene la tormenta de reintentos — un 429 sigue siendo no-2xx, Cloud Tasks lo
reintenta igual. Es necesario pero no suficiente; el Paso 1 es el que de verdad corta
el bucle.

### Paso 5 — Bandera de degradación pasiva + helper de reporte seguro

Nuevo módulo sugerido: `backend/app/services/redis_safety.py` (nombre angosto, mismo
criterio que `cpu_quota.py` de hoy — no un "utils.py" genérico).

```python
"""redis_safety.py — bandera de degradación pasiva + wrapper de reporte que nunca
propaga. Ver docs/mesa-decision-resiliencia-redis-2026-07-23.md para el porqué."""
import time

_degraded_until: float = 0.0
_COOLDOWN_SECONDS = 60

def mark_degraded() -> None:
    global _degraded_until
    _degraded_until = time.monotonic() + _COOLDOWN_SECONDS

def is_degraded() -> bool:
    return time.monotonic() < _degraded_until

async def safe_redis_call(coro_factory, *, on_quota_error=mark_degraded):
    """Ejecuta una llamada a Redis; nunca propaga. Si el error es de cuota
    (is_redis_quota_error), activa la bandera de degradación."""
    try:
        return await coro_factory()
    except Exception as e:
        if is_redis_quota_error(e):  # del Paso 4
            on_quota_error()
        print(f"[redis_safety] aviso: operación de Redis no completada: {e}")
        return None
```

Usar `safe_redis_call` para envolver CADA escritura de reporte no esencial en los
Pasos 1 y 2 (status "converting"/"done", contadores, ticks). Además, cuando
`is_degraded()` sea `True`, las rutas no críticas pueden saltarse Redis por completo
sin siquiera intentarlo (reduce carga durante el cooldown) — esto reemplaza al
circuit breaker completo, ver restricción #2 arriba.

### Paso 6 — `/api/health` expone la bandera

Archivo: `backend/app/main.py`, líneas 153-155 actuales:
```python
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

**Cambio**:
```python
@app.get("/api/health")
def health() -> dict[str, str]:
    if redis_safety.is_degraded():
        return {"status": "degraded", "realtime": "unavailable"}
    return {"status": "ok"}
```

**Restricción crítica (ya la marcó SRE)**: este endpoint NUNCA debe hacer una llamada
real a Redis — el presupuesto de cuota son ~11 peticiones/min, un health check que
consulte Redis se comería la cuota él solo. Solo lee la bandera en memoria
(`is_degraded()`, sin `await`, sin red).

### Paso 7 — Frontend: portar el aviso ámbar del flujo de lote al flujo individual

Archivos: `frontend/src/lib/pdf-download.ts`, `frontend/src/components/ConversionMasivaPage.tsx`.

El flujo de lote ya tiene el patrón correcto: banner ámbar persistente ("se perdió la
conexión de progreso, tu lote sigue procesándose") + botón "Reintentar conexión"
(`ConversionMasivaPage.tsx:684-696` aprox., verificar línea exacta al implementar). El
flujo individual (`waitForPdfJob` en `pdf-download.ts`, usado por `convertFileToPdf`)
al agotar su timeout (180s, `overallTimeoutMs`) lanza un `alert()` crudo con el texto
"Tiempo de espera agotado en el navegador".

**Cambio**: en vez de escalar a `alert()`, mostrar el mismo patrón de banner ámbar con
el texto: *"No pudimos mostrarte el avance en vivo, pero tu PDF pudo haberse generado
ya. [Verificar ahora] · [Reintentar conversión]"*. El botón "Verificar ahora" hace una
consulta puntual de estado (no reabre el stream SSE) — para esto se necesita un
`GET /pdf/{job_id}/status` de una sola lectura si no existe ya uno equivalente
(revisar si `_batch_progress_snapshot` o similar ya cubre el caso individual antes de
crear uno nuevo). **Este paso depende del Paso 3** (sin el fallback a GCS en las
descargas, el botón "verificar" no puede confirmar nada durante una caída real de
Redis).

Consulta también `GET /api/health` (Paso 6) para decidir si mostrar el banner de
degradación de entrada, no solo al agotar el timeout.

### Paso 8 (opcional, bajo, no bloqueante) — Runbook operacional

Documentar en `PROJECT_STATE.md` o un runbook aparte: ante una notificación de cuota
de Redis agotada, la acción humana más rápida es pausar la cola de Cloud Tasks
(`gcloud tasks queues pause pdf-generator-queue --location=us-central1` o
`--max-concurrent-dispatches=0`) — corta la quema de cuota causada por reintentos,
sin perder trabajo ya hecho (los PDFs ya están en GCS). Reanudar cuando la cuota se
libere o se suba de plan.

### Paso 9 (opcional, bajo, no bloqueante) — Bugs de UX encontrados de paso

- `ACTIVE_BATCH_KEY` en `localStorage` (`ConversionMasivaPage.tsx:98` aprox.) no está
  aislado por pestaña — dos pestañas del navegador comparten el mismo batch activo
  restaurado al montar. Fix sugerido: `sessionStorage` o llave por `batchId`. **Pedir
  confirmación al usuario antes de implementar** — cambia el comportamiento de
  recuperación entre pestañas, que hoy es (probablemente sin querer) un feature.
- XMLs sueltos vs. ZIP usan pipelines completamente distintos (150 streams SSE
  individuales vs. 1 batch en servidor) — ambos dependen de Redis. No es un bug per
  se, pero vale la pena que el usuario sepa que no son intercambiables en
  comportamiento. No se propone unificarlos en este plan.

## Plan de pruebas

Seguir el patrón ya establecido hoy en `backend/tests/test_cpu_quota.py`
(`patch.object`/`patch("builtins.open", ...)`, clases `Test*` para que pytest las
descubra). Casos mínimos a cubrir:

- `internal_generate_pdf`: mockear `redis_client.set` con
  `side_effect=redis.exceptions.ResponseError("max requests limit exceeded")` en la
  escritura de "converting" — el PDF debe generarse y subirse a GCS de todas formas, y
  la respuesta debe ser 200 (o el equivalente actual de éxito), no 500.
- `batch_shard_worker.run_shard`: mockear el tick de error para que lance — el resto
  del shard (los demás `job_id` del `for`) debe seguir procesándose, `run_shard()` no
  debe propagar la excepción ni llamar a `sys.exit`.
- `download_pdf`/`get_pdf_download_url`: con Redis mockeado para fallar, y el blob
  existiendo en GCS (mock), debe devolver el PDF/URL igual, no 404.
- `redis_safety.safe_redis_call`: nunca propaga, activa `is_degraded()` solo ante el
  error de cuota real (no ante cualquier excepción).
- `is_redis_quota_error`: reconoce "max requests limit exceeded" (el caso real de
  hoy), no reconoce excepciones no relacionadas.
- `/api/health`: refleja `degraded` cuando la bandera está activa, sin llamar a Redis
  (verificar con un mock que asegure CERO llamadas a `redis_client` durante la prueba
  de este endpoint).

## Verificación end-to-end antes de dar por cerrado

1. `python3 -m pytest backend/tests/ -q` — confirmar que los 8 fallos preexistentes
   de siempre (documentados en `PROJECT_STATE.md`, sección "Hallazgos preexistentes")
   siguen siendo los únicos, sin nuevos rotos.
2. Probar en un entorno virtual limpio (mismo patrón de hoy) que el import de los
   módulos nuevos no rompe nada.
3. Deploy real: confirmar health check limpio de la revisión nueva (mismo patrón de
   hoy — `gcloud logging read` sobre la revisión activa, buscar errores de arranque).
4. **Prueba deliberada de degradación**: si es posible sin gastar cuota real de Redis,
   simular el error (ej. apagando temporalmente las credenciales de Redis en un
   canario aislado, NUNCA en producción con tráfico real) y confirmar que un PDF se
   genera y se puede descargar igual.
5. Confirmar en el frontend real (Vercel) que el banner de degradación aparece
   correctamente cuando `/api/health` reporta `degraded`.

## Archivos que este plan toca (índice rápido)

- `backend/app/routers/pdf.py` — Pasos 1, 3, 4.
- `backend/app/workers/batch_shard_worker.py` — Paso 2.
- `backend/app/services/redis_safety.py` (nuevo) — Paso 5.
- `backend/app/services/redis_errors.py` (nuevo, o adjunto donde se prefiera) — Paso 4.
- `backend/app/main.py` — Paso 6.
- `frontend/src/lib/pdf-download.ts`, `frontend/src/components/ConversionMasivaPage.tsx` — Paso 7.
- `backend/tests/` — nuevos tests, ver "Plan de pruebas".
- `PROJECT_STATE.md` — Paso 8 (runbook), y actualizar al cerrar cada paso.

## Documentos relacionados, en orden de lectura si hace falta más contexto

1. `docs/propuestas-resiliencia-redis-pusher-2026-07-22.md` — exploración original (un día antes del incidente).
2. `docs/mesa-decision-resiliencia-redis-2026-07-23.md` — síntesis completa de la mesa de 4 agentes, con todo el razonamiento detrás de cada decisión de este plan.
3. Este documento — el "qué hacer" ejecutable.
4. `PROJECT_STATE.md` — estado general del proyecto, actualizar conforme se avance.
