# Investigación: ¿aguanta la arquitectura actual volúmenes masivos? (30,000+ PDFs/min)

> **Este documento es exploración, no un plan.** Nada aquí está decidido ni en construcción.
> Es un rastro de hipótesis, números y alternativas para retomar y seguir platicando en
> sesiones futuras — no una lista de tareas. Empezó 2026-07-11 con una pregunta honesta: la
> arquitectura actual (Cloud Run + Cloud Tasks + un motor propio de renderizado XML→PDF) se
> decidió en su momento, con el contexto que había entonces. Vale la pena revisitarla de vez en
> cuando en vez de asumir que sigue siendo la mejor opción solo porque ya existe.

## La pregunta que lo disparó

Después de resolver signal 6 (ver `PROJECT_STATE.md`) y confirmar `concurrency=5` en producción,
medimos throughput real: **78 PDFs/minuto** sostenidos, con un lote real mixto (80% XMLs
complejos de Miniso, 20% simples). La reacción honesta fue: "eso es muy poco, ¿aguantaría 30,000
por minuto? ¿o esto fue un error de diseño desde el principio?"

## Lo que sabemos con certeza (verificado, no supuesto)

**Configuración actual de Cloud Run:**
- 2 vCPU / 2 GiB por instancia, `concurrency=5`, hasta 10 instancias, escala a cero en reposo.
- Pool de procesos de renderizado: `min(8, cpu_count())` → 2 workers reales por instancia (refleja
  las 2 vCPU asignadas).
- Techo estructural de renderizado en paralelo hoy: 10 instancias × 2 workers = **20 renders
  simultáneos como máximo**.

**Cloud Tasks (`pdf-generator-queue`):**
- `maxConcurrentDispatches=8` — la cola solo despacha 8 tareas a la vez, sin importar cuántas
  instancias/workers existan disponibles.

**Rendimiento medido (no teórico):**
- PDF complejo (Miniso), worker frío: 5.1s. Mismo worker caliente: 1.7s.
- PDF simple, worker frío: 1.4s.
- Throughput sostenido del batch real de 2,000 archivos: **78 PDFs/min** — y **solo se usaron 7
  de las 10 instancias disponibles** durante toda la prueba.

**Hallazgo clave de esa última observación**: el sistema nunca llegó a topar su capacidad de
cómputo (instancias/workers) — el cuello de botella observado apunta más a la tasa de despacho de
la cola (`maxConcurrentDispatches=8`) que a falta de máquinas. Esto es una **inferencia fuerte**,
no un hecho confirmado con un experimento aislado (no se probó subir solo ese número mientras se
mantenía todo lo demás fijo).

**Precios reales (buscados, no inventados, 2026, `us-central1`):**
- Cloud Run: $0.000024 por vCPU-segundo (facturación por petición).
- Compute Engine on-demand (`e2-standard-2`, 2 vCPU): $0.07/hora ≈ $0.0000097 por vCPU-segundo —
  ya ~2.5x más barato que Cloud Run por el mismo cómputo crudo.
- Spot VMs: Google anuncia hasta 91% de descuento sobre on-demand; no se encontró la tarifa spot
  exacta del día — se usó ~70% de descuento como estimado conservador para los cálculos de abajo
  (⚠️ hipótesis, no tarifa confirmada).
- Cloud Batch en sí no cobra nada extra — solo se paga el cómputo (VMs, discos) que usa.

## Lo que NO sabemos todavía (preguntas abiertas, no resueltas)

1. **¿30,000/minuto es un pico ocasional o un requisito sostenido 24/7?** Esta es LA pregunta que
   más cambia todo el análisis de costo — la diferencia es de órdenes de magnitud (ver tabla
   abajo). Sin esta respuesta, cualquier número de costo es un rango, no una cifra.
2. **¿Dónde se va el tiempo dentro de un solo render?** Nunca se perfiló `generate()` para separar
   cuánto es WeasyPrint (header HTML), cuánto reportlab (tabla), cuánto pypdf (merge), cuánto es
   I/O de red (Redis/GCS). Hipótesis fuerte pero no confirmada: WeasyPrint es el cuello de botella,
   por su reputación conocida de ser lento en el ecosistema Python. Sin perfilar, cualquier
   propuesta de optimización de código es una apuesta, no una decisión informada.
3. **¿Cloud Run puede siquiera escalar a cientos/miles de instancias en segundos?** No se verificó
   la tasa real de ramp-up de instancias nuevas ni los cuotas por proyecto/región — es posible que
   el límite real no sea de dinero sino de la plataforma misma bajo una ráfaga muy agresiva.
4. **¿Cuál es la tarifa spot exacta hoy?** Se usó un estimado conservador (70% de descuento); el
   número real podría ser mejor o peor.

## Hipótesis de costo para llegar a 30,000/min (cálculos de servilleta, no cotización)

Con el tiempo de render actual (~2.5s promedio, sin optimizar código): se necesitarían ~1,250
vCPUs trabajando al mismo tiempo, sin parar, para sostener 500 PDFs/seg.

| Escenario | Sostenido 24/7 | Pico de 5 minutos |
|---|---|---|
| Fuerza bruta en Cloud Run, sin optimizar código | ~$86,000/mes | ~$10 esa vez |
| Mismo cómputo en Compute Engine on-demand | ~$31,500/mes | ~$3.60 esa vez |
| Mismo cómputo en spot (~70% descuento estimado) | ~$9,450/mes | ~$1.09 esa vez |
| Si WeasyPrint se optimiza 5x (hipotético, sin confirmar) + spot | ~$1,890/mes | ~$0.22 esa vez |

La brecha entre "sostenido" y "pico" es la diferencia entre un problema serio de negocio y algo
casi gratis — de ahí que la pregunta 1 de arriba sea la más importante de todas.

## La idea que se discutió: separar el camino interactivo del camino masivo

No forzar que una sola arquitectura sirva para uso normal (usuarios subiendo ZIPs de cientos de
archivos, como hoy) Y para ráfagas masivas (30,000+). Son problemas de forma distinta:

- **Camino interactivo (hoy, sin cambios)**: Cloud Run + Cloud Tasks, como está. Sirve bien el
  volumen normal, barato, escala a cero.
- **Camino masivo (hipotético, no construido)**: Cloud Batch + VMs spot, disparado explícitamente
  solo cuando hay un lote genuinamente enorme. Sin trabajo que hacer, cuesta $0 — no es una flota
  esperando "por si acaso".

**Qué del código actual se reutilizaría tal cual** (verificado leyendo el código, no supuesto):
- `generate()` completo (`pdf_pipeline.py`) — función pura, XML→PDF, no sabe ni le importa quién
  la llama.
- El patrón de aislamiento por proceso (`PDF_PROCESS_POOL`, `spawn`) — encaja igual o mejor en un
  worker de batch que en un servidor HTTP.
- Lectura/escritura a GCS y Redis — mismo bucket, mismo Redis, no atado a Cloud Run.
- Probablemente la misma imagen de Docker, con un comando de arranque distinto.

**Qué NO es compatible tal cual, sería trabajo nuevo**:
- `internal_generate_pdf` es un endpoint HTTP de FastAPI disparado por Cloud Tasks — Cloud Batch no
  dispara HTTP requests, corre un job que procesa una lista de trabajo directamente. Habría que
  extraer la lógica de adentro y ponerla en un script que recorra una cola.
- Un job spec de Cloud Batch (infraestructura nueva, no el motor de PDFs).
- Manejo de interrupciones de VMs spot — nota a favor: el diseño actual (estado por job en Redis,
  no en memoria de la instancia) ya está parcialmente preparado para esto por el mismo patrón que
  ya usa para que Cloud Tasks reintente si una instancia de Cloud Run muere.

## Para la próxima sesión que retome esto

- Si se quiere avanzar en la pregunta técnica: perfilar `generate()` (barato, rápido, no toca
  producción) para saber de verdad si WeasyPrint es el cuello de botella.
- Si se quiere avanzar en la pregunta de negocio: definir si 30,000/min es un número real
  (¿hay un cliente/caso de uso concreto detrás?) y si es pico o sostenido — sin esto, seguir
  afinando costos es especular sobre un requisito que quizás no exista todavía.
- Verificar la tarifa spot exacta (hoy es un estimado) antes de tomar cualquier decisión basada en
  el costo.
- Nada de esto bloquea el estado actual del proyecto — la app funciona bien para el volumen de hoy.
  Esto es exploración de qué pasaría SI el volumen creciera mucho, no un problema activo.
