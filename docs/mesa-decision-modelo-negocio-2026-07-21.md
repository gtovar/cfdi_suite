# Mesa de decisión: qué hacer con `business-model-conversion-exploration.md`

> **Segunda mesa de 5 agentes** (2026-07-21), corridos en paralelo y ciegos entre sí,
> sobre `docs/business-model-conversion-exploration.md` como sujeto principal —
> `docs/investigacion-escalamiento-masivo.md` y
> `docs/mesa-decision-escalamiento-masivo-2026-07-21.md` como contexto técnico de
> verificación. Nota de proceso: el usuario originalmente pidió esta mesa sobre
> `investigacion-escalamiento-masivo.md` (ver la primera mesa) y corrigió después que
> el sujeto real debía ser este documento de negocio — de ahí que ambas mesas existan
> y se complementen.

## Los 5 agentes y sus mandatos

1. **bm-arquitecto** (Plan): diseñar caminos/fases para llevar el doc de negocio de
   exploración a decisión ejecutable.
2. **bm-experto** (general-purpose): verificar cada mecanismo técnico que el doc asume
   contra el código real — ¿existe, existe parcial, o es hipotético?
3. **bm-sre** (general-purpose): riesgo operacional/seguridad de construir las
   perillas propuestas.
4. **bm-impacto** (general-purpose): cuantificar impacto tiempo/dinero/riesgo por idea,
   con los números reales ya verificados (no los ilustrativos de Gemini).
5. **bm-verificador-cruzado** (general-purpose): cruzar cada idea de negocio contra los
   hallazgos ya confirmados/desmentidos por la mesa técnica anterior.

---

## Reporte de cada agente

### bm-arquitecto — 4 caminos

- **A — No construir nada; resolver primero el fork B2C vs. B2B2C.** Costo de
  ingeniería cero; es la decisión que más cambia todo lo demás (gatea Stripe Connect).
- **B — Instrumentación mínima antes de diseñar tiers.** Loggear tamaño real de
  ZIP/XML y duración por job; recalibrar tiers con el benchmark real de motores PDF en
  vez de las cifras ilustrativas de Gemini.
- **C — Pilotear la perilla más barata: prioridad de despacho en Cloud Tasks.** Única
  idea del Piso 4 que sobrevivió la corrección anterior — pero bloqueada por la Fase 0
  de la mesa técnica (no tocar la cola sin cerrar DLQ/reconciliación primero).
- **D — Ir directo a Stripe Connect/BYOC (referencia, no recomendado).** Incluido solo
  para descartarlo: ningún pro identificado que no dependa de premisas no verificadas.

Secuencia recomendada: A y B en paralelo; C solo tras cerrar la Fase 0 técnica; D
descartado hasta evidencia de cliente real.

### bm-experto — verificación mecanismo por mecanismo

**Confirmado (existe hoy):** URL firmada de subida/descarga directa a GCS
(`pdf.py:646-712`); cola de Cloud Tasks (`task_dispatcher.py`).

**Parcial / apagado / distinto de lo que dice el doc:** Cloud Run Jobs (NO Cloud
Batch) existe pero apagado (`BATCH_JOB_ENABLED=false`, `BATCH_JOB_THRESHOLD=999999999`,
`batch_job_trigger.py:21-24`) — resuelve la contradicción de la mesa técnica anterior a
favor de "apagado". `task_count` existe pero se deriva de `total_xmls/shard_size`, no
es una perilla por-cliente.

**Hipotético (cero código):** prioridad de despacho en Cloud Tasks, reconfig CPU/RAM
runtime ("Modo Turbo", ya descartado), Stripe Connect/créditos, BYOC/IAM multi-cuenta,
ventana de capacidad reservada, dead-letter queue, load testing.

**Premisa huérfana:** todo lo que justifica cómputo dedicado (Piso 2, perillas de gran
paralelismo, Piso 6) descansa en el escenario de 30,000/min que la mesa técnica ya
encontró sin ticket ni cliente real. Además, la perilla "premium = prioridad de
despacho" apuntaría a un cuello (tasa de despacho) que no es el medido (extracción de
ZIP a 600 Mbps/instancia).

### bm-sre — el hallazgo más fundamental de la mesa

**CFDI Suite es hoy efectivamente mono-tenant, sin identidad ni facturación.**

1. **Manejo de credenciales de terceros ya roto**: `backend/app/credentials.py` guarda
   `credential_token` de emisores en Fernet local, con la llave (`secret.key`) en el
   MISMO directorio que el dato cifrado — el cifrado es teatro. Filesystem efímero de
   Cloud Run, sin persistencia ni aislamiento por tenant. BYOC multiplicaría este fallo,
   no agregaría uno nuevo.
2. **Cero autenticación de usuarios** — grep de `get_current_user`/`OAuth2`/
   `HTTPBearer`/`verify_token`/`Depends(auth)` sin resultados en ningún router. Sin
   identidad no hay a quién cobrar, aislar, ni limitar.
3. **Cero medición de consumo ni facturación** — sin Stripe, metering, plan, tenant ni
   webhooks.

**Prerequisitos en orden estricto antes de cualquier perilla:** (1) autenticación +
modelo de tenant; (2) gestión de secretos real (bloqueante para BYOC); (3) medición de
consumo por tenant; (4) recién entonces facturación (Stripe normal, no Connect, hasta
resolver el fork).

### bm-impacto — cuantificación

El fork B2C vs. B2B2C **no está resuelto** — gatea Stripe Connect, la comisión de BYOC,
y la nota fiscal recursiva del §9.

- **Perillas tiempo-vs-costo**: tiempo no cuantificable y contradicho por la única
  prueba real (mueven VMs de render; el cuello real fue extracción de ZIP). Montos
  $5/$25/$150 son ilustrativos, no reales — el margen implícito ahí (15-680× sobre
  costo real de $0.22-$10) es la brecha de 45× que debe quedar interna.
- **Stripe Connect**: no cuantificable en $, riesgo binario — solo tiene sentido si
  B2B2C.
- **Créditos de cómputo**: la cobertura real medida es **2.56×** (no el 9× que afirmó
  `ideas-negocio` sin derivación visible) — corrección a la mesa anterior. Ventaja
  real: agnóstico al modelo de negocio (funciona en B2C y B2B2C).
- **Ventana de capacidad reservada**: fundada en un pico programable real (cierre de
  mes), pero disposición a pagar y tamaño del pico no cuantificables sin telemetría.
- **Infra dedicada/BYOC**: no cuantificable sin cliente real; solo justificable por
  enterprise que ya lo pida (ninguno existe hoy).

### bm-verificador-cruzado — huérfanas vs. sólidas

**Huérfanas (premisa técnica se cayó):** Piso 2 (Cloud Batch), Piso 6 (infra
dedicada/BYOC/20 VMs por cliente), el menú de 3 tiers con cifras concretas actuales.

**Recalibrar (idea viva, premisa cambió):** perillas de paralelismo (calibrar sobre
throughput de shard medido, no horas-cómputo genéricas), "premium = prioridad de
despacho" (depende del load test pendiente — puede no atacar el cuello real), "premium
= SLA" (prematuro sin conocer el throughput real ni tener DLQ).

**Sólidas (no dependen de lo debilitado):** ventana de capacidad reservada, calibrar
tiers con el benchmark real de motores, créditos de cómputo, Stripe Connect (su
bloqueo es el fork de negocio, no un hallazgo técnico).

**Patrón de fondo:** toda idea cuyo valor nace del throughput de conversión masiva
quedó debilitada — ese nunca fue el cuello real. Sobreviven las ancladas en costos ya
medidos o en la agenda del cliente, no en capacidad especulativa.

---

## Síntesis final (Árbitro)

### Hechos verificados
- Cero autenticación, credenciales de terceros ya mal manejadas, cero metering/
  facturación (bm-sre).
- No es Cloud Batch, es Cloud Run Jobs, apagado — threshold=999999999 confirmado,
  resuelve la contradicción de la mesa técnica anterior (bm-experto).
- **Convergencia de 3 agentes independientes**: la perilla "premium = prioridad de
  despacho" apunta al cuello equivocado (despacho, no extracción de ZIP).
- Montos ilustrativos inválidos (estimación base ya falsificada).
- Corrección: la volatilidad de costo real es 2.56×, no 9×.

### Riesgo
Construir cualquier perilla antes de auth+tenant+metering es construir sobre nada —
literalmente no hay a quién cobrarle ni a quién aislar. BYOC multiplicaría un fallo de
seguridad ya existente.

### Recomendación — fases

**Fase -1 (más fundamental que todo lo demás) — infraestructura de producto
inexistente:**
1. Autenticación de usuarios + modelo de tenant.
2. Gestión de secretos real (Secret Manager, llave≠dato) — bloqueante para BYOC.
3. Medición de consumo por tenant.

**Fase 0 (de la mesa técnica, en paralelo donde no compita):**
4. DLQ + reconciliación.
5. Load test aislado — decide también si "prioridad de despacho" tiene algún valor.
6. Migrar `REDIS_PASSWORD` a Secret Manager.

**Fase 1 — barato, no bloqueado:**
7. Resolver el fork B2C vs. B2B2C.
8. Instrumentar telemetría real de tamaños de ZIP/XML.
9. Recalibrar tiers con el benchmark real de motores PDF.

**Fase 2 — condicionada a evidencia:**
10. Créditos de cómputo (2.56×, agnóstico al modelo).
11. Ventana de capacidad reservada (requiere telemetría del punto 8).
12. Prioridad de despacho — solo si el load test confirma que el despacho es un cuello
    real.
13. Stripe Connect — solo si el fork resuelve a B2B2C.

**Descartar (premisa debilitada, no reabrir sin evidencia de cliente):**
14. Piso 2 (Cloud Batch).
15. Piso 6 (BYOC / infraestructura dedicada).
16. El menú de 3 tiers con las cifras actuales ($5/$25/$150).
