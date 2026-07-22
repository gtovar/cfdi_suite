# Mesa de decisión: qué hacer con `investigacion-escalamiento-masivo.md`

> **Este documento es el registro de una mesa de 5 agentes** (arquitecto-solucion,
> experto-proyecto, sre-senior, impacto-negocio, ideas-negocio) corridos en paralelo
> y ciegos entre sí el 2026-07-21, más la síntesis final aplicando `decision-expander`
> sobre sus 4 salidas técnicas. Sigue el mismo patrón de mesa multi-agente ya usado
> antes en este proyecto (ver `PROJECT_STATE.md`, "Mesa de revisión multi-agente").
> No reemplaza `investigacion-escalamiento-masivo.md` ni `propuesta-arquitectura-batch.md`
> — es la capa de veredicto sobre ambos.

## Contexto del encargo

El usuario pidió montar una mesa de decisión para responder: ¿qué hacemos con
`docs/investigacion-escalamiento-masivo.md`? ¿Construimos algo, lo desechamos, en qué
orden, qué le gusta y qué no le gusta a cada agente, con pros y contras? Explícitamente
no quería que la mesa decidiera "hacia dónde va la empresa" — solo qué hacer con esta
investigación puntual.

## Los 5 agentes y sus mandatos

1. **arquitecto-solucion** (Plan): diseñar caminos posibles (no código), incluyendo la
   opción de no construir nada.
2. **experto-proyecto** (general-purpose): confirmar o refutar cada afirmación de los
   documentos contra el código real.
3. **sre-senior** (general-purpose): riesgo operacional y qué falta probar antes de
   decidir.
4. **impacto-negocio** (general-purpose): cuantificar impacto en tiempo/dinero/riesgo
   por cada dirección técnica.
5. **ideas-negocio** (general-purpose): ideas nuevas para enriquecer
   `business-model-conversion-exploration.md`, separado de la decisión técnica.

Los primeros 4 trabajaron ciegos entre sí (no vieron las salidas de los demás),
replicando el patrón que ya funcionó en la mesa de 5 agentes documentada en
`PROJECT_STATE.md`.

---

## Reporte íntegro de cada agente

### arquitecto-solucion

Leyó ambos documentos completos, incluyendo el estado más reciente (Capa 1 construida,
probada en canario, con partes desplegadas). Propuso 4 caminos:

- **Camino A — No construir nada más; solo activar lo ya pagado.** Prender
  `REMOTE_ZIP_SHARD_READ=true` en prod y cerrar pendientes menores (patrón secuencial
  en la subida a GCS, migrar `REDIS_PASSWORD` a Secret Manager). Pros: cero complejidad
  nueva, capitaliza trabajo ya medido. Contras: dos capas completas (typst,
  vectorización) quedan sin explorar.
- **Camino B — Cerrar el ciclo de la Capa 1 + validar el escenario de negocio real que
  falta.** Fase 1 = Camino A. Fase 2 = probar "muchos batches chicos simultáneos"
  (1000 usuarios × 50 facturas), no "un batch grande" — la preocupación original real
  del usuario, nunca probada. Contras: Cloud Run ya demostró 5 veces que su
  comportamiento real diverge del reproducido en local — otra ronda de sorpresas.
- **Camino C — PoC de Capa 2 (typst), acotada y gratuita.** Sin riesgo legal (Ronda 0
  descartó el veto de sello/QR). Contras: el margen ya bajó un tercio por el fix de
  `FontConfiguration`; agrega un motor en Rust que mantener; nunca probado con un CFDI
  real.
- **Camino D — No tocar nada, ni siquiera activar lo ya construido.** Su propia lectura:
  esta es la opción con peor relación beneficio/esfuerzo restante de las cuatro — el
  costo marginal de activar el interruptor es mucho menor que el de haberlo construido.

### experto-proyecto (verificador)

**Confirmado en código (archivo:línea):**
- `concurrency=5`: `backend/cloudbuild.yaml:33` y `.github/workflows/deploy-backend.yml:47`
  — único valor probado (canario Miniso), no subir sin re-probar.
- `2 vCPU / 2 GiB / max-instances=10`: `deploy-backend.yml:43-45`.
- Pool `min(8, cpu_count())`: `pdf_pipeline.py:33-34`.
- `generate()` es función pura reutilizable: `workers/batch_shard_worker.py:74` la llama
  directo sin el pool.
- Fix `FontConfiguration` implementado de verdad: `shell_service.py:27-33` (`threading.local`).

**Refutado / matizado:**
- `maxConcurrentDispatches=8` **no es verificable en el repo** — la cola vive como
  estado runtime de GCP, no en IaC versionado. El propio doc de investigación ya lo
  admite como "inferencia fuerte, no confirmada".
- "Capa 1 hipotética, no construida" (investigación línea 89) está **desactualizado**:
  sí está construida (`batch_job_trigger.py`, `workers/batch_shard_worker.py`,
  `REMOTE_ZIP_SHARD_READ` en `pdf.py:747`), solo apagada por defecto
  (`BATCH_JOB_ENABLED=false`, threshold=999999999).

**¿El escalamiento de 30,000/min le dolió a un usuario real? No.** Los batches reales
documentados son de 150 y 20 archivos. El único stress real fue un canario de 2,000
XMLs sin tráfico real. Los incidentes que sí ocurrieron (signal 6, OOM en
`download_batch_zip`) eran bugs de aislamiento de procesos/memoria, **ortogonales** al
throughput de render. El escenario de 15,000 XMLs (cliente grande + demo a
inversionistas) es una afirmación de negocio en prosa del propio documento, sin ticket,
log ni artefacto de cliente.

**Dato que el propio documento se autocorrige:** la estimación de "15,000 en ~30-40s
por <$1" resultó falsa al probarse — el test real de 2,000 XMLs dio ~16-17 min
totales. El cuello real fue la extracción del ZIP, atada al límite de red de 600 Mbps
por instancia (evidencia dura de Cloud Monitoring: CPU 17%, red saturada). Este cuello
(extracción) y el supuesto cuello de despacho (`maxConcurrentDispatches`) son etapas
distintas — el repo tiene evidencia dura solo para el primero.

**Veredicto:** el problema es **anticipatorio, no urgente**. Cero fuego hoy. El caso
más fuerte para construir la Capa 1 es económico (build cuesta igual ahora que
después, idle=$0), no de dolor. Advertencia menor: el "techo de 20 renders" asume que
`cpu_count()` devuelve 2 dentro del contenedor; en varios runtimes devuelve los cores
del nodo, lo que rompería esa aritmética — no verificable desde código.

### sre-senior

Confirmó contra código real (`routers/batch.py`, `routers/pdf.py`,
`workers/batch_shard_worker.py`, `services/batch_job_trigger.py`,
`services/batch_progress.py`) que la Capa 1 está escrita y commiteada pero apagada por
gate.

**Top 3 riesgos:**
1. **Batches atorados en silencio, sin DLQ.** Si un job_id nunca escribe su status, el
   batch queda "processing" hasta que expira el TTL de Redis (~24h), sin alerta. Con
   `--max-retries=1` en el shard worker, un solo crash fatal puede dejar ~100 job_ids
   colgados de golpe. No existe dead-letter queue (confirma que el "creo que sí tengo"
   era falso).
2. **Cuello de botella central sigue siendo inferencia, no dato** — no hay load test
   aislado que lo confirme.
3. **Observabilidad de un solo lado**: Sentry solo cableado en el path de análisis, no
   en generación de PDF (depende de `print()` a stdout). Hoy no hay forma de detectar
   el riesgo 1 sin que se queje un usuario.

**Qué haría primero:** load test aislado (`locust`/`k6`) + cerrar el hueco de
reconciliación/DLQ, en ese orden, antes de encender cualquier capa.

### impacto-negocio

Marco de costo: el número que domina es pico-vs-sostenido (a 30,000/min sostenido
24/7: ~$86,000/mes sin optimizar vs. ~$1,890/mes optimizado+spot; como pico de 5 min,
entre ~$10 y ~$0.22 esa vez — nadie confirmó si el volumen es real/pico/sostenido, así
que esto es rango, no cifra).

Por dirección técnica:
- **Capa 1**: 2.3× más rápido en procesamiento puro; batch de 15,000 XMLs ~$0.15-1 USD;
  riesgo operacional alto hoy porque *(nota: esta afirmación de threshold quedó
  contradicha por sre-senior/experto-proyecto, ver "Contradicción sin resolver" abajo)*.
- **Lectura por rangos (Etapa 4)**: el mayor golpe medido — manifiesto de 6-8 min a
  1.5s; ~37% más rápido que Capa 1 sola. Riesgo bajo, inerte hasta activar.
- **Fix FontConfiguration**: 26-35% menos por factura típica, mejor relación
  esfuerzo/impacto de todo el trabajo.
- **Capa 2 (typst)**: margen restante ~170ms/factura — no cuantificable si justifica la
  complejidad sin volumen real confirmado.
- **Capa 3 (vectorización)**: solo relevante en facturas de 1000+ conceptos.
- **Paralelización GCS (revertida)**: salió 1.7× más lenta en prod real.
- **Progreso en pantalla**: pura UX, no cuantificable en $/tiempo, pero batches chicos
  son más lentos por XML que los grandes (13.3s/XML a 20 archivos vs 5.2s/XML a 2000)
  por arranque en frío — el problema inverso al escenario "ZIP pequeño" original del
  usuario.

### ideas-negocio

Ver sección correspondiente ya aplicada a `business-model-conversion-exploration.md`
(Piso 4 corregido). Resumen de sus 5 ideas + 1 crítica bonus:
1. La brecha de 45× en costo es margen interno, no debe exponerse al cliente.
2. "Crédito por documento" es cobertura contra la volatilidad de 9× en costo, no solo
   conveniencia de facturación.
3. Spot VMs contradicen la promesa de "Premium = tiempo garantizado" — vender SLA, no
   velocidad cruda.
4. Tier nuevo: "ventana de capacidad reservada" para picos predecibles (cierre de
   mes/quincena) — más realista que un botón genérico de turbo.
5. "Modo Turbo" (reconfigurar CPU/RAM de todo el servicio) está mal fundado — afecta a
   todos los usuarios, no es por-cliente. El mecanismo correcto ya identificado es
   prioridad de despacho en Cloud Tasks.
6. Bonus: el escenario "$86k/mes sostenido" que justificaría Cloud Batch/BYOC podría
   ser un número sin cliente real detrás.

---

## Síntesis final (Árbitro — decision-expander aplicado por el orquestador)

### Hechos verificados (convergencia independiente de 2+ agentes)
- Capa 1 escrita y commiteada, apagada por gate — confirmado por sre-senior y
  experto-proyecto con archivo:línea.
- No existe dead-letter queue — confirmado 3 veces por métodos distintos.
- Nunca se corrió load test real — confirmado 2 veces.
- El cuello de extracción (600 Mbps/instancia) tiene evidencia dura (Cloud Monitoring);
  el cuello de despacho (`maxConcurrentDispatches=8`) no.
- La estimación "15k en 30-40s" fue falsa — el propio documento se autocorrigió.
- Ningún incidente real ligado a volumen de 30,000/min.

### Contradicción sin resolver entre agentes
`impacto-negocio` afirmó `BATCH_JOB_THRESHOLD=1` (enruta todo ZIP de producción).
`sre-senior` y `experto-proyecto` —ambos citando archivo:línea— dicen threshold=999999999
y `BATCH_JOB_ENABLED=false` (prácticamente apagado). No pueden ser ciertas ambas. Dos
agentes con cita concreta pesan más que uno sin cita específica, pero esto merece
verificación directa antes de actuar, no resolverse por conteo de votos.

### Inferencia fuerte
- Construir/activar la Capa 1 se justifica por economía (idle=$0, cuesta igual ahora
  que después), no por urgencia.
- El escenario de 15k/30k por minuto descansa en prosa sin ticket ni artefacto de
  cliente — probablemente inflado o al menos no confirmado como driver de negocio
  presente.

### Hipótesis útil
- Tier de "ventana de capacidad reservada" para picos predecibles.
- Reframe de "Premium" como garantía de SLA, no de velocidad cruda.
- `cpu_count()` podría romper la aritmética del "techo de 20 renders" si devuelve
  cores del nodo — no probado.

### Riesgos
- Encender la Capa 1 sin reconciliación/DLQ multiplica ~100× el radio de falla
  silenciosa ya existente.
- `REDIS_PASSWORD` en texto plano.
- Observabilidad de un solo lado (Sentry solo en path de análisis).
- Ideas del Piso 4 del doc de negocio que no resisten escrutinio (Modo Turbo, exponer
  la brecha de 45×, Premium vía Spot).

### Prueba mínima
Load test aislado (`locust`/`k6`) que mida `maxConcurrentDispatches` como única
variable — barato, no toca producción, convierte la inferencia central del documento
en hecho.

### Recomendación — fases

**Fase 0 — antes de tocar cualquier arquitectura:**
1. Resolver la contradicción de threshold con una verificación directa.
2. Construir la barrida de reconciliación + DLQ (prerequisito, no lujo).
3. Correr el load test aislado de `maxConcurrentDispatches`.
4. Migrar `REDIS_PASSWORD` a Secret Manager.

**Fase 1 — activar lo ya pagado, con la red de seguridad puesta:**
5. Encender `REMOTE_ZIP_SHARD_READ` (evidencia más dura de toda la investigación).
6. Activar la Capa 1 solo después de cerrada la Fase 0.

**Fase 2 — condicionada a evidencia, no a suposición:**
7. No construir Cloud Batch, BYOC, ni infraestructura dedicada todavía.
8. No construir el motor typst todavía (margen pequeño, sin urgencia).
9. Descartar vectorización salvo facturas reales de 1,000+ conceptos.

**Para el documento de negocio:** corregir Piso 4 con las críticas de ideas-negocio
(ya aplicado en `business-model-conversion-exploration.md`).
