# Mesa de decisión: resiliencia Redis/Pusher, a partir del incidente real del 23 de julio

> **Mesa de 4 agentes** (arquitecto-de-software, producto-ux, sre-confiabilidad,
> destructor) corridos en paralelo y ciegos entre sí, más esta síntesis final. Motivada
> por un incidente real (no hipotético): el plan gratuito de Redis (Upstash, 500,000
> peticiones/mes) se agotó por completo durante una sesión de pruebas de carga del
> usuario, tumbando la generación de PDFs individuales y por lote. Continúa la
> exploración de `docs/propuestas-resiliencia-redis-pusher-2026-07-22.md` (de ayer,
> teórica) con evidencia real de hoy.

## El mecanismo real del incidente (convergencia fuerte: arquitecto + SRE, independiente)

No fue solo "Redis falló y no se manejó bien" — fue una **tormenta de reintentos
autoalimentada**:

1. Redis se agota → `internal_generate_pdf` falla en la primera línea de su `try`
   (`pdf.py:124`, escribe estado ANTES de generar el PDF) → excepción → 500.
2. Cloud Tasks solo considera éxito un 2xx — **cualquier no-2xx, incluido un futuro 429,
   se reintenta según el `RetryConfig` de la cola, sin respetar `Retry-After`.**
3. Cada reintento vuelve a golpear Redis (que sigue agotado) → nuevo 500 → nuevo
   reintento.
4. El sistema se muerde la cola: el propio manejo de errores es lo que mantiene la
   cuota clavada al 100%, no solo un síntoma de que ya estaba agotada.

El mismo defecto exacto vive en `batch_shard_worker.py` (el Job de shards), con peor
consecuencia: el tick de error (`publish_batch_tick(..., definitive_error=True)`,
líneas 163/199) no está protegido — si Redis falla justo ahí, la excepción escapa el
loop, sube a `main()`, y `sys.exit(1)` hace que **Cloud Run Job reintente la tarea
completa de hasta 100 XMLs**, amplificando aún más la carga sobre un Redis ya agotado.

## Hallazgo crítico que invalida parte de la narrativa original (Producto + Destructor, convergencia independiente)

La idea de "el trabajo real queda bien, solo se pierde el aviso en tiempo real" **es
falsa tal como está el código hoy**. Verificado en dos lugares distintos, por dos
agentes que no se vieron entre sí:

- `download_pdf` (pdf.py:603-605) y `get_pdf_download_url` (pdf.py:686-688) consultan
  **Redis primero** (`pdf:status == done`) y solo si eso pasa llegan a `blob.exists()`
  en GCS. Si Redis está caído, el usuario NO puede descargar un PDF que ya existe.
- `list_ready_files` (pdf.py:459-478) y `estimated-size` (pdf.py:481-497) — el
  mecanismo de respaldo del frontend para cuando Pusher falla — **también leen Redis
  primero** (`smembers`/`mget`). Es decir, la red de seguridad que debería compensar la
  caída de Pusher depende de la misma pieza que ya está caída.

Esto significa: antes de poder decir honestamente "Redis es opcional, el trabajo
sigue", hay que arreglar esto — es un prerequisito, no un extra.

## Tensión real, resuelta explícitamente (Destructor la exigió; Arquitecto ya la había resuelto sin saberlo)

**El lock de idempotencia de extracción (`pdf:extracting_lock`, `SET NX`) no puede ser
"opcional" — es Redis por definición.** La decisión forzada:

- **Fail-closed** (si no se puede tomar el lock porque Redis no responde, no se
  procede): un batch NUEVO no se puede extraer mientras Redis esté mal. Es una
  degradación real, pero acotada y conocida.
- **Fail-open**: reintroduce el bug de duplicación de extracción del 12 de julio —
  y justo en el escenario donde más duele (cuota agotada a mitad de un batch, con
  reintentos de Cloud Tasks en curso), dos extracciones traslapadas duplicarían la
  carga sobre GCS y Redis, acelerando el propio agotamiento.

**Decisión: fail-closed.** No hay opción gratis; se acepta la degradación acotada
(batches nuevos esperan) a cambio de no repetir un bug de producción ya resuelto.

## Qué se descarta, y por qué (con evidencia, no por reflejo)

- **Circuit breaker completo (pybreaker) — descartado por ahora.** Su beneficio
  clásico es evitar la acumulación de *timeouts*. Pero el error real de Upstash
  ("max requests limit exceeded") **falla rápido**, no se cuelga — no hay timeouts que
  acumular en este incidente específico. Destructor y SRE llegaron a la misma
  conclusión por caminos distintos, sin verse. En su lugar: una **bandera de
  degradación pasiva** (ver abajo) da el mismo beneficio real (dejar de golpear Redis
  durante el outage) con una fracción de la complejidad.
- **`ProgressReporter` (abstracción/interfaz completa) — pospuesta, no descartada
  del todo.** Es la forma arquitectónicamente "correcta" a largo plazo, pero
  Destructor tiene razón en que hoy es una apuesta sin evidencia de necesitarse (dos
  call sites, un usuario, ningún plan de cambiar de proveedor de notificaciones). Los
  arreglos de abajo logran el mismo resultado práctico sin la abstracción nueva.
- **Recalcular el total del batch desde GCS en cada consulta — descartado.**
  Destructor tiene razón: sería caro y solo mueve el gasto de cuota de Redis a
  operaciones de GCS, no lo elimina. (El manifiesto UNA VEZ al extraer, mencionado
  abajo, es distinto — es una escritura, no una re-derivación por consulta.)
- **Reducir el número de operaciones a Redis por XML (~6 hoy) — genuinamente
  pendiente, no resuelto por esta mesa.** Destructor tiene razón en que ninguna
  propuesta baja ese número — todas atacan "qué pasa cuando falla", no "cuánto se
  gasta cuando todo va bien". Se anota como mejora futura (agrupar escrituras en un
  pipeline de Redis), no bloqueante hoy porque el incidente fue causado por pruebas
  agresivas autoinflingidas (varias pestañas, 150 XMLs cada una, sin pausa), no por
  volumen de uso normal.

## La propuesta: qué hacer, en orden

### Ya (bajo riesgo, corta la tormenta, evidencia convergente de 3+ agentes)

1. **Invertir el orden en los dos caminos calientes** (`pdf.py: internal_generate_pdf`,
   `batch_shard_worker.py: _process_one`/`run_shard`): el trabajo real (decodificar →
   generar → subir a GCS) corre primero, sin depender de Redis. Las escrituras de
   Redis/Pusher van después, en su propio bloque que nunca escala a una excepción que
   dispare un 5xx reintentable. Nota de alcance honesta (Destructor): no es una sola
   línea — son varios puntos en ambos archivos (`pdf.py:124,172,176-177,190-191` y sus
   equivalentes en el worker), todos con el mismo patrón.
2. **Una vez que el PDF ya está en GCS, ninguna falla posterior de Redis debe producir
   un 5xx reintentable.** Responder éxito (200) igual — el trabajo ya se hizo. Esto es
   lo que de verdad detiene el bucle de reintentos de Cloud Tasks, no solo la
   reclasificación de errores (ver punto 4).
3. **Suavizar el gate redundante de Redis en `download_pdf`/`get_pdf_download_url`**
   (Producto + Arquitecto lo marcan como ganancia casi gratis, bajo riesgo): revisar
   `blob.exists()` en GCS directamente en vez de exigir `pdf:status == done` primero.
4. **Corregir la clasificación de errores** (`pdf.py:206-208`): el patrón buscado
   ("quota exceeded") no coincide con el mensaje real de Upstash ("max requests limit
   exceeded"). Centralizar en un helper `is_redis_quota_error()` reusado en los tres
   lugares que instancian cliente Redis. **Nota honesta de SRE: esto es necesario pero
   cosmético — no detiene la tormenta por sí solo**, porque un 429 sigue siendo
   no-2xx y Cloud Tasks lo reintenta igual.
5. **Bandera de degradación pasiva** (`redis_degraded`, booleano + timestamp en
   memoria del proceso): se activa sola cuando una llamada a Redis lanza el error de
   cuota (sin ninguna llamada extra — se cuelga del tráfico que ya existe), se
   autorresetea tras un cooldown. Una vez activa, las rutas no críticas (ticks de
   progreso) se saltan Redis por completo durante el cooldown — este ES el circuit
   breaker barato que reemplaza a pybreaker.
6. **`GET /api/health` expone la bandera** (`{"status":"degraded","realtime":"unavailable"}`
   en vez del estático `{"status":"ok"}` de hoy, `main.py:153-155`) — el frontend la
   consulta y muestra el aviso correcto. **Importante: este endpoint NUNCA debe hacer
   ping a Redis** (el presupuesto de cuota son ~11 peticiones/min — un health check que
   consulte Redis se comería la cuota él solo). Solo lee la bandera en memoria.

### Frontend — portar un patrón que ya existe, no inventar uno nuevo

7. El flujo de **lote (ZIP)** ya tiene el 80% de esto bien: banner ámbar persistente
   ("se perdió la conexión de progreso, tu lote sigue procesándose") + botón
   "Reintentar conexión" (`ConversionMasivaPage.tsx:684-696`). **El flujo individual
   (XML suelto) no tiene nada de esto** — al agotar el timeout tira un `alert()` crudo
   ("Tiempo de espera agotado en el navegador"). Portar el mismo patrón del lote al
   flujo individual.
8. **Reescribir el mensaje de timeout individual** de "error" a "verificación
   pendiente": *"No pudimos mostrarte el avance en vivo, pero tu PDF pudo haberse
   generado ya. [Verificar ahora] · [Reintentar conversión]"* — con un botón que haga
   una sola consulta puntual de estado (no el stream), con 3 desenlaces claros: listo /
   aún no / falló de verdad. **Esto depende del punto 3 (fallback a GCS)** — sin eso,
   el botón "verificar" no puede funcionar durante una caída real de Redis.
9. Regla de color: **ámbar = degradado, sigue operando; rojo = solo cuando el trabajo
   realmente falló.** Hoy el timeout individual se lee como rojo/fatal aunque no lo sea.

### Runbook operacional (SRE) — para cuando esto vuelva a pasar

10. **Pausar la cola de Cloud Tasks** (`maxConcurrentDispatches=0`) es la palanca
    humana más rápida para cortar la quema de cuota — el backlog reintentándose es lo
    que mantiene la cuota clavada al 100%. El trabajo ya hecho (PDFs en GCS) no se
    pierde al pausar.
11. **Alertamiento proactivo, no solo Sentry reactivo**: un cron que lea el uso real
    vía la REST API de Upstash (no consume cuota de comandos Redis) y avise al
    80-90% de la cuota mensual — para reaccionar con horas/días de margen, no cuando
    ya se cayó.

### Bugs de UX encontrados de paso (Producto, confirmados en código, separados de Redis)

12. **Dos pestañas muestran el mismo progreso**: `ACTIVE_BATCH_KEY` en `localStorage`
    (`ConversionMasivaPage.tsx:98`) no está aislado por pestaña — la segunda pestaña
    restaura el batch de la primera al montar. Fix: mover a `sessionStorage` o una
    llave por `batchId`. El link compartible ya es el mecanismo real de recuperación
    entre sesiones/dispositivos, así que perder el auto-restore de `localStorage`
    entre pestañas probablemente esté bien — **decisión de producto a confirmar con
    el usuario, no solo técnica**.
13. **XMLs sueltos vs. ZIP se comportan distinto** porque son dos pipelines
    completamente separados (150 streams SSE individuales vs. 1 batch en servidor) —
    y ambos dependen de Redis, así que ninguno es inmune a esto. Con 150 streams SSE
    simultáneos, el flujo de sueltos probablemente contribuyó más al consumo de cuota
    de hoy que el de ZIP. Anotado, no resuelto en esta mesa.

## Lo que esta mesa deja abierto a propósito

- Reducir operaciones de Redis por XML (~6 hoy) — mejora futura, no bloqueante.
- Mover el lock de extracción a un sentinel de GCS (sin dependencia de Redis del
  todo) — estructural, opcional, con su propio costo (los objetos GCS no expiran
  como `EX`, necesitaría regla de reclamo por timestamp).
- Unificar el pipeline de XMLs sueltos con el de batch — cambio de arquitectura
  aparte, no parte de este incidente.
