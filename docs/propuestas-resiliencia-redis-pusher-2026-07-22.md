# Propuestas: cómo evitar que Redis/Pusher tumben el trabajo real

> **Este documento es exploración de ideas, no un plan decidido.** Nada aquí está
> construido ni comprometido. Se escribió para poder compartirlo con otro agente/persona
> en paralelo, como insumo de discusión — no como especificación final. Cuatro
> propuestas distintas, no combinadas todavía, cada una resuelve el mismo problema de
> raíz de una forma diferente.

## El problema que las cuatro atacan

El backend de `cfdi_suite` convierte XMLs de facturas a PDF, en lote, de dos formas: vía
Cloud Tasks (un XML a la vez) o vía un Cloud Run Job de "shards" (cada tarea procesa
hasta 100 XMLs seguidos, en el mismo proceso). Redis se usa para varias cosas mezcladas:
qué XMLs pertenecen a un batch, el estado de cada uno (listo/error), un lock de
exclusión mutua real (ya evitó un bug de duplicación de trabajo en producción), y
contadores de progreso que alimentan un aviso en tiempo real vía Pusher.

Confirmado leyendo el código: si Redis falla (caído, timeout, o se agota la cuota del
plan gratuito de Upstash) en el momento equivocado, hoy eso puede **tumbar una tarea
completa del Job de shards (hasta 100 XMLs, no solo el que falló)**, o **abortar el
resto de un batch que aún no se había extraído** — el trabajo real (generar el PDF, ya
generado y subido a GCS) queda bien, pero el sistema de reporte lo arrastra a un estado
de error que no le corresponde.

**Restricción que ninguna propuesta debe romper**: el lock de exclusión mutua
(`pdf:extracting_lock`) ya evitó un bug real de producción — cualquier solución debe
preservar esa garantía, no solo "quitar Redis de en medio" sin reemplazo.

---

## Propuesta 1 — `ProgressReporter`: una interfaz entre el trabajo y el reporte

**Problema que resuelve**: el código que hace el trabajo real (el `for` que procesa cada
XML) hoy llama *directamente* a funciones de Redis/Pusher — sabe que existen, sabe que
pueden fallar, tiene que decidir qué hacer si fallan. Es una violación de Inversión de
Dependencias (SOLID): el trabajo no debería conocer los detalles de cómo se reporta.

**Cómo funciona**: se define una interfaz abstracta (`ProgressReporter`) con métodos
como `mark_done(job_id)` y `mark_error(job_id, exc)`. El código del `for` solo llama a
esos métodos — no sabe ni le importa si por dentro usan Redis, Pusher, ambos, ninguno,
o algo distinto en el futuro. Toda la lógica de "no propagar errores", reintentos, etc.
vive **dentro de la implementación concreta** del reporter, en un solo lugar.

**Qué cambia en el código**: nueva interfaz + una implementación concreta
(`RedisProgressReporter`) que envuelve lo que hoy hacen `publish_batch_tick` y los
`redis_client.set(...)` sueltos. El `for` de `batch_shard_worker.py` deja de importar
nada de Redis directamente.

| | |
|---|---|
| **Pros** | El trabajo real queda genuinamente aislado del reporte, no solo protegido. Fácil de probar (se inyecta un reporter falso en tests, sin mockear Redis). Si el día de mañana se cambia de proveedor de notificaciones, el `for` no cambia una línea. |
| **Contras** | Esfuerzo mayor que un simple `try/except` (definir la interfaz, la implementación, inyectarla en los puntos de entrada). No resuelve por sí sola la latencia de un Redis caído (eso lo resuelve mejor la Propuesta 2). |
| **Esfuerzo estimado** | Medio — una interfaz + una clase, tocar 2-3 archivos existentes para inyectarla. |
| **Cuándo preferirla** | Si el objetivo es la limpieza arquitectónica de fondo, no solo apagar el riesgo inmediato. |

---

## Propuesta 2 — Circuit breaker como pieza de infraestructura reutilizable

**Problema que resuelve**: incluso con reintentos y manejo de errores, si Redis está
*completamente* caído, cada intento individual sigue pagando su timeout completo antes
de rendirse — en una tarea de 100 XMLs, eso puede sumar minutos de espera pura, aunque
el trabajo real no dependa de Redis para nada.

**Cómo funciona**: un "cortacircuitos" — después de N fallos seguidos contra el mismo
servicio, deja de intentar por un tiempo (ej. 30 segundos) y falla instantáneamente sin
ni siquiera intentar la llamada, hasta que ese tiempo pasa y prueba de nuevo. Existen
librerías chicas y ya probadas para Python que implementan esto (ej. `pybreaker`), no
hace falta escribirlo desde cero.

**Qué cambia en el código**: se trata como una capa que se le puede poner "encima" de
*cualquier* llamada externa (Redis, Pusher, y en teoría hasta GCS) — no cambia la forma
del código que hace el trabajo, solo envuelve las llamadas de red con esta protección
adicional.

| | |
|---|---|
| **Pros** | Ataca la falla *lenta* (no solo la que tumba trabajo, sino la que lo hace todo más lento de lo necesario). Reutilizable para cualquier dependencia externa futura, no solo Redis. Librería madura, no hay que inventar el mecanismo. |
| **Contras** | Introduce estado (cuántos fallos van, cuándo reintentar) — una pieza más para razonar/probar. No resuelve por sí sola el problema de "quién sabe de Redis" (complementa mejor a la Propuesta 1 que reemplazarla). |
| **Esfuerzo estimado** | Bajo-medio — agregar una dependencia y envolver los puntos de llamada real a Redis/Pusher. |
| **Cuándo preferirla** | Junto con la 1, para que la implementación concreta del reporter falle rápido, no solo falle seguro. |

---

## Propuesta 3 — GCS como fuente de la pregunta "¿ya está listo?", no Redis

**Problema que resuelve**: hoy, saber si un XML ya se convirtió depende de un flag en
Redis (`pdf:status:{job_id}`). Pero el PDF mismo, una vez generado, **ya existe en GCS**
— una señal real, gratis, que no depende de que Redis esté sano.

**Cómo funciona**: en vez de (o adicional a) escribir el estado en Redis, la pregunta
"¿el job X ya terminó?" se resuelve verificando si `pdfs/{job_id}.pdf` existe en GCS.
Redis quedaría solo para lo que de verdad necesita coordinación entre tareas paralelas
(el lock) y para el avance en tiempo real (que es mucho menos grave perder).

**Qué cambia en el código**: los endpoints que hoy consultan `pdf:status` para decidir
si servir un PDF podrían, como respaldo o reemplazo, verificar la existencia del archivo
en GCS directamente.

| | |
|---|---|
| **Pros** | Reduce cuánto depende el sistema de Redis para la pregunta más importante ("¿ya puedo descargar mi PDF?"). Usa algo que el sistema ya tiene (el PDF en GCS), no agrega infraestructura nueva. |
| **Contras** | Verificar existencia en GCS por cada consulta puede ser más lento/costoso que leer un flag en Redis si se hace con mucha frecuencia (habría que medir, no asumir). No resuelve el problema para el *progreso en tiempo real* (eso sigue siendo Redis/Pusher). Es un cambio más profundo — toca cómo se decide el estado, no solo cómo se reporta. |
| **Esfuerzo estimado** | Medio-alto — es la propuesta que más se acerca a "repensar la fuente de verdad", que explícitamente se dejó fuera del alcance inmediato en esta misma conversación. |
| **Cuándo preferirla** | Si en algún momento se decide sí atacar el problema de fondo (no solo el reporte), no como parte de un arreglo rápido. |

---

## Propuesta 4 — Reconciliación periódica en vez de perfección por evento

**Problema que resuelve**: hoy se intenta que *cada* aviso individual a Redis/Pusher
tenga éxito. Pero no hace falta — lo que de verdad importa es que el estado agregado
final sea correcto, no que cada tick individual llegue.

**Cómo funciona**: **este patrón ya existe en este mismo proyecto, no es una idea
importada** — el frontend (`watchBatchProgress`) ya se rediseñó con esta misma
filosofía tras una mesa de revisión anterior: en vez de depender de que cada evento
individual llegue, se agregó una "red de seguridad" de intervalo fijo que reconcilia el
estado real sin importar cuántos avisos puntuales se perdieron en el camino. La
propuesta es aplicar la misma idea del lado del backend: al terminar una tarea del
shard (o cada cierto intervalo), un paso de reconciliación recalcula el estado real
comparando contra GCS/el manifiesto, sin importar cuántas escrituras individuales a
Redis fallaron durante el proceso.

**Qué cambia en el código**: un paso adicional, al final de `run_shard()` (o
periódico), que reconcilia el conteo real de éxitos/errores contra lo que de verdad
pasó (ej. cuántos PDFs existen en GCS para ese batch), en vez de confiar en que el
contador incremental de Redis nunca se saltó un tick.

| | |
|---|---|
| **Pros** | Reutiliza un patrón ya validado con éxito en este mismo proyecto — no es una apuesta nueva. Tolera perder ticks individuales sin ansiedad, porque hay una corrección final. |
| **Contras** | No evita que un fallo de Redis *a mitad* del proceso cause el problema original (tumbar la tarea) — resuelve la *consistencia final*, no necesariamente el *crash a mitad de camino*. Se complementa mejor con la Propuesta 1 o 2 que reemplazarlas. |
| **Esfuerzo estimado** | Bajo-medio — un paso de reconciliación al final de la tarea, reutilizando lógica de conteo que ya existe. |
| **Cuándo preferirla** | Como complemento casi obligado de cualquiera de las otras tres, dado que ya probó funcionar en este proyecto. |

---

## Nota final

Estas cuatro no son excluyentes. Una combinación razonable (mencionada pero no
desarrollada aquí a propósito, para no precomprometer la conversación): **Propuesta 1
(la interfaz) + Propuesta 2 (circuit breaker dentro de su implementación concreta) +
Propuesta 4 (reconciliación final como red de seguridad)** — dejando la Propuesta 3
(mover la fuente de verdad a GCS) como una decisión aparte, más grande, para otro
momento.
