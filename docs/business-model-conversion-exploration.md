# Exploración: modelo de negocio y "perillas" de potencia para la conversión CFDI

> **Este documento es exploración, no un plan.** Nada aquí está decidido ni en
> construcción. Es un rastro completo de ideas, sin curar, para retomar en sesiones
> futuras — no una lista de tareas. Empezó 2026-07-21 a partir de una conversación
> que el usuario tuvo por separado con Gemini sobre arquitectura GCP y monetización,
> que pidió documentar íntegramente ("no quiero que omitas nada") y enriquecer antes
> de decidir cualquier cosa.
>
> Complementa, no reemplaza, la exploración técnica ya existente en
> [`investigacion-escalamiento-masivo.md`](./investigacion-escalamiento-masivo.md) y
> [`propuesta-arquitectura-batch.md`](./propuesta-arquitectura-batch.md). Aquellos
> documentos preguntan "¿aguanta la arquitectura actual?" y "¿cómo se vería
> diseñada desde cero?". Este pregunta algo distinto: "¿cómo se cobra esto, y se le
> puede dar al cliente una perilla de tiempo-vs-costo?"

## Origen y una advertencia de traducción

El contenido de las secciones 1-7 viene de una conversación del usuario con Gemini,
centrada en una arquitectura genérica **Fastify (Node.js) + Vercel + Google Cloud**.
**El stack real de CFDI Suite es Python/FastAPI**, no Fastify — todos los snippets
de código citados abajo son ilustrativos de los conceptos, no trasplantables tal
cual. Los conceptos de GCP (Cloud Run, Cloud Tasks, Cloud Batch, cuotas, pricing)
sí aplican igual sin importar el lenguaje del backend.

**Corrección 2026-07-21:** el archivo original que se documentó arriba (secciones 1-7)
resultó ser solo la **cola** de una conversación mucho más larga. El usuario pasó el
archivo completo después (`gemini_chat (1).txt`, 2283 líneas); todo lo de las
secciones 1-7 corresponde a partir de la línea ~1659 de ese archivo completo. La
sección 0 de abajo documenta la parte previa que faltaba — los fundamentos de
concurrencia/capacidad de los que parten todas las decisiones de "pisos" de arriba.
Un tramo del transcript original (líneas ~1100-1198) es un incidente personal ajeno
a la conversación técnica (parece una interrupción de fondo durante una dictado por
voz) — se excluye de esta documentación por no ser relevante.

---

## 0. Fundamentos previos: capacidad, concurrencia y probabilidad de picos

Esta parte de la conversación es anterior a los "pisos" de la sección 1, y es de
donde nacen. Empezó con una pregunta simple del usuario — "¿cuántos usuarios
aguanta mi app?" — y terminó resolviendo, con matemáticas reales, por qué conviene
mantener instancias mínimas encendidas.

### La metáfora central: "el administrador vs. el trabajador"

La pieza que más costó aclarar en toda la conversación (requirió más de 15
intercambios de ida y vuelta): **Cloud Tasks nunca procesa nada.** Es el
"administrador" — decide cuándo, a qué ritmo y con cuántos reintentos se hace el
trabajo. **Cloud Run Jobs / Cloud Batch son "el trabajador"** — el código que
realmente descomprime el ZIP o convierte los XML, sin el límite de 60 minutos que
tiene una petición HTTP normal de Cloud Run.

Por qué existe Cloud Tasks si ya hay un worker: porque el worker por sí solo no
sabe limitar el ritmo (rate limiting), no reintenta solo si falla a medias, y no
sabe programarse para una hora específica — eso es lo que aporta Cloud Tasks
encima del worker, no en vez de él.

### Dos colas distintas que conviven

- **La cola interna de Cloud Run** (tránsito rápido): cuando un usuario real hace
  clic, si las instancias disponibles ya están al tope de su concurrencia, Cloud
  Run guarda la petición en una cola interna por unos segundos (por defecto: el
  mayor entre 10 segundos o 3.5× el tiempo promedio de arranque de una instancia)
  antes de abrir una instancia nueva o de responder 503.
- **La cola de Cloud Tasks** (tránsito diferido): no intercepta tráfico de
  usuarios reales; solo existe para las tareas que el código decide explícitamente
  mandar ahí (ej. "generar este PDF pesado"). Se implementa por endpoint, no como
  capa que envuelve todo Cloud Run.

Ambas conviven — no son alternativas, resuelven problemas distintos.

### El ejercicio de probabilidad (distribución de Poisson)

El usuario pidió explícitamente un cálculo, no una explicación conceptual: dado un
promedio de 500 peticiones/minuto (≈8 peticiones/segundo) y una concurrencia de 5
por instancia, ¿qué tan probable es que en un segundo cualquiera lleguen más de 5
peticiones a la vez (lo que obliga a abrir una segunda instancia)?

- Fórmula usada: `P(X = k) = (λ^k · e^-λ) / k!`, con λ = 8.
- Se suman las probabilidades de 0 a 5 eventos: P(X ≤ 5) ≈ 19.12%.
- Se resta de 1: P(X > 5) ≈ **80.88%**.
- Conclusión de la conversación: con esa probabilidad tan alta, mantener al menos
  1-2 instancias mínimas encendidas (evitando el cold start) queda justificado con
  números, no solo con intuición.

**Advertencia que no está en la conversación original, la agrego yo:** Poisson
asume llegadas **aleatorias e independientes**. Es el modelo correcto para tráfico
de fondo impredecible, pero si un pico es *predecible* (ej. cierre de mes/quincena
contable), ya no es un problema de probabilidad sino de programar `min-instances`
hacia arriba en una ventana conocida de antemano. Esto afina la pregunta abierta #1
de `investigacion-escalamiento-masivo.md` ("¿pico ocasional o sostenido?") — la
pregunta más precisa sería "¿es un pico aleatorio (Poisson) o programable
(agenda)?", porque la solución es distinta en cada caso.

### Otros hallazgos de esta parte previa

- **Cloud Run replica el contenedor completo al escalar**, aunque solo un endpoint
  esté recibiendo tráfico — los demás endpoints "duermen" en esa copia sin gastar
  recursos (el código en disco no consume RAM; solo las peticiones activas sí).
- **Tres capas de throttling posibles, no una**: Nginx/Cloud Armor (portero de
  infraestructura, filtra por IP/volumen antes de tocar la app) → la aplicación
  (reglas de negocio: "este plan solo tiene 100 peticiones/hora") → Cloud Tasks
  (organiza trabajo diferido, no es un escudo contra ataques). Cloud Run ya trae
  su propio balanceador/portero de fábrica; Nginx manual casi nunca hace falta
  salvo para Cloud Armor (WAF) o un gateway de microservicios.
- **Vercel (frontend) y Cloud Run (backend) escalan de forma completamente
  independiente** — uno no le pega recursos al otro.
- **El ejemplo trabajado del "gimnasio"** (10,000 vs. 500,000 miembros a cobrar y
  facturar cada fin de mes — estructuralmente casi idéntico al caso de CFDI Suite
  de miles de XMLs por ZIP) comparó tres arquitecturas con pros/contras explícitos:
  1. Todo en un ciclo dentro de Cloud Run (monolito puro): simple pero se rompe
     por timeout de 60 min y por RAM si el volumen crece.
  2. Cloud Tasks + Cloud Run: "la reina indiscutible" para 1,000-50,000 — cero
     riesgo de timeout, reintentos automáticos, pero el trabajo total tarda más
     por ir en fila controlada.
  3. Cloud Batch: solo para millones de filas / horas continuas — poder
     prácticamente ilimitado, pero caro para volúmenes cortos por el tiempo de
     encendido/apagado de la VM.

---

## 1. Inventario completo, sin curar, organizado en "pisos"

### Piso 0 — Servidor del día a día
- Cloud Run como núcleo: se apaga casi a cero cuando no hay tráfico, escala hacia
  arriba en picos.
- Balanceador de carga gestionado de Google (sustituye Nginx manual): SSL, ráfagas,
  enrutamiento automático.
- **Cloud Armor** (WAF) — mencionado *una sola vez*, solo en el resumen final de la
  conversación, nunca profundizado en el diálogo. Queda como nota suelta, no como
  decisión.

### Piso 1 — Colchón de picos medianos (Cloud Tasks)
- El backend recibe la petición, la mete a una cola, responde 202 de inmediato.
  Cloud Tasks actúa de amortiguador: absorbe el pico, lo deja en fila.
- **Criterio de decisión Tasks vs Batch que propone la conversación**: no es
  "cuántas peticiones entran" sino "cuánto tarda **una sola** tarea en
  procesarse". Caso A (muchas tareas rápidas, ej. 1M peticiones × 100ms c/u) →
  Cloud Tasks. Caso B (una sola tarea gigante, ej. 5M filas en 3h continuas) →
  Cloud Batch.
- Ejemplo dado: cola configurable a 20 tareas/seg (pico de 100k tarda ~80 min,
  protege la base de datos) o 500 tareas/seg + 50 instancias concurrentes (mismo
  pico en ~3 min).

### Piso 2 — El "músculo" para picos extremos (Cloud Batch)
- Cloud Batch = "director de orquesta", no la instancia. Un **Job** se compone de
  **Tasks** (bloques). Cloud Batch le pide VMs a Compute Engine, reparte los
  bloques entre instancias (ej. 100 tasks en instancia A, 100 en instancia B), y
  auto-destruye las instancias al terminar.
- Cloud Batch vs Cloud Run Jobs: Cloud Run Jobs = contenedores ligeros, máx. 24h.
  Cloud Batch = VMs tradicionales (sin Docker si se quiere, scripts bash), discos
  gigantes, GPUs, hasta 14 días corriendo.
- **Costeo — el punto que la conversación remarca más**: el precio por segundo de
  CPU/RAM es casi idéntico entre Cloud Run / Cloud Run Jobs / Cloud Batch. La
  diferencia real está en *cómo se mide el tiempo*:
  - Cloud Run/Tasks: se cobra solo el tiempo activo de procesamiento; no se cobra
    boot ni tiempo vacío.
  - Cloud Batch: se cobra el ciclo de vida completo de la VM — boot (1-2 min),
    descarga de imagen, procesamiento, apagado seguro. Conclusión textual de la
    conversación: para tareas cortas, Cloud Batch es "un desperdicio de dinero
    brutal".
  - Cloud Batch gana en tareas gigantes gracias a: VMs **Spot/preemptible**
    (60-91% descuento, riesgo de que Google la reclame de vuelta), y hardware
    especializado (GPU, AMD más baratos por núcleo) no disponible en Cloud Run.
  - Costo oculto de Cloud Tasks: primeras 1.5M operaciones gratis/mes, luego
    ~$0.40 USD por millón de tareas creadas/reintentadas. En el extremo de
    millones, la conversación recomienda **no** usar Cloud Tasks tarea-por-tarea
    sino volcar un archivo plano a Cloud Storage y correr un solo Cloud Batch Job
    leyendo todo en memoria.

### Piso 3 — Perillas dinámicas a nivel de código (backend)
- Idea de codificar la bifurcación como `if/else` en el endpoint según tamaño de
  la solicitud: umbral de ejemplo, **<50,000 registros → Cloud Tasks; ≥50,000 →
  Cloud Batch** (umbral puramente ilustrativo de la conversación, no calculado
  contra datos reales).
- Parámetros tuneables de **Cloud Tasks**: `max-concurrent-dispatches`,
  `max-dispatches-per-second`, `max-attempts`, `min-backoff`/`max-backoff`
  (exponential backoff).
- Parámetros tuneables de **Cloud Run**: CPU/RAM por instancia (desde 0.08
  CPU/128MB hasta 8 CPU/32GB), `min-instances` (evitar cold start), `max-instances`
  (freno de presupuesto), `concurrency` (máx. 300 peticiones simultáneas por
  instancia), `timeout` (hasta 60 min).
- Recomendación de la conversación: codificar estas perillas en Terraform o
  `service.yaml`, no tocarlas a mano en la consola.

### Piso 4 — Perillas expuestas al usuario final (UI)
- Idea confirmada: sí se puede poner interfaz (sliders/dropdowns) y que el
  backend traduzca la elección a llamadas API de GCP.
- Ejemplo 1 — dropdown "Velocidad de procesamiento" (Lento/Normal/Rápido) →
  backend actualiza `maxDispatchesPerSecond` de la cola en tiempo real.
- Ejemplo 2 — "Modo Turbo" (Plan Básico vs Enterprise) → backend reconfigura
  CPU/RAM del servicio (nota: tarda segundos porque Google redistribuye
  contenedores).
- Ejemplo 3 — "Presupuesto máximo" (candado anti-abuso): UI deja elegir 1-10
  máquinas paralelas; backend valida y rechaza si el usuario pide más de lo que
  su plan permite, incluso si manipula el frontend.
- **La propuesta central de "perillas tiempo-vs-costo"** (la que más le gustó al
  usuario): dado un trabajo que requiere, ej., 100 horas-cómputo totales, ofrecer
  3 opciones calculadas y mostradas ANTES de procesar:
  - 🐢 Económico: 1 VM Spot → 100h → "4 días, $5 USD"
  - ⏰ Balanceado: 4 VMs normales en paralelo → 25h → "1 día, $25 USD"
  - 🚀 Premium: 100 VMs en paralelo → 1h → "60 min, $150 USD"
  - Se implementa pasando `taskCount` (máquinas en paralelo) dinámicamente a la
    API de Cloud Batch según la opción elegida.
  - Flujo de usuario dado como ejemplo: sube archivo → "detectamos 500,000 filas,
    elige: Económico $2/30min o Express $15/2min" → paga → se ejecuta.

**Corrección 2026-07-21 (mesa de decisión, agente `ideas-negocio`):** tres partes de
este Piso 4 no resisten el escrutinio y quedan marcadas como descartadas, no como
vigentes:
- **"Modo Turbo" (Ejemplo 2) está mal fundado.** Reconfigurar CPU/RAM de un servicio
  Cloud Run "en tiempo real por usuario" no es por-usuario: es un cambio de TODO el
  servicio que afecta a todos los usuarios simultáneos, y el propio ejemplo admite que
  "tarda segundos". El mecanismo correcto para "premium = más rápido" sin
  infraestructura dedicada es **prioridad de despacho en Cloud Tasks** (ver §4.5,
  punto 5) — descartar Modo Turbo, quedarse con prioridad de cola.
- **La brecha de costo (optimización + spot vs. sin optimizar) es margen interno, NUNCA
  debe exponerse al cliente.** Las perillas mezclan dos cosas distintas: el
  paralelismo es física real que el cliente elige; la brecha de optimización (medida
  en `investigacion-escalamiento-masivo.md` en ~45×: ~$86,000/mes sin optimizar vs.
  ~$1,890/mes optimizado+spot) es margen que sostiene el pricing. Si el precio del
  tier Premium se fija sobre el costo SIN optimizar y se corre optimizado, esos 45×
  son margen bruto — exponerle al cliente "podemos hacerlo 45× más barato" destruye el
  poder de fijar precio.
- **El tier "Premium = 60 min garantizados" se contradice a sí mismo.** Se apoya en
  VMs Spot (60-91% descuento = 60-91% riesgo de reclamo) — no se puede prometer tiempo
  garantizado Y correrlo en Spot barato. El eje facturable no debería ser velocidad
  cruda sino **garantía de tiempo (SLA)**: el tier económico tolera Spot y reinicios;
  el premium exige on-demand (más caro, pero sin riesgo de reclamo). Vender el SLA, no
  los MHz.

**Idea nueva que reemplaza el hueco que deja "Modo Turbo":** un tier de **"ventana de
capacidad reservada"** para picos predecibles (cierre de mes/quincena contable — ver
§0, la distinción Poisson-vs-agenda). Los contadores saben que su pico es el último
día del mes; se les vende una ventana de throughput garantizado reservable, se
pre-calientan instancias, se cobra premium por la reserva. Encaja con el cliente real
mucho mejor que un botón genérico de "turbo". Ver detalle completo del razonamiento en
`docs/mesa-decision-escalamiento-masivo-2026-07-21.md`.

### Piso 5 — Monetización con comisión (Stripe Connect)
- Pregunta original: ¿puede el usuario final pagar directo y que a la plataforma
  le llegue solo una comisión, sin que la plataforma toque el dinero completo?
- Respuesta: no vía Google (Google solo cobra a la plataforma por
  infraestructura) — sí vía **Stripe Connect**, diseñado para
  plataformas/marketplaces.
- Mecanismo: el pago del usuario final entra directo a la cuenta Stripe del
  cliente B2B de la plataforma; Stripe separa automáticamente una "Application
  Fee" (ej. 5%) y la deposita en la cuenta de la plataforma.
- Flujo completo dado: Usuario paga $100 → Stripe Connect divide → Cliente
  recibe $95 / Plataforma recibe $5 → webhook activa Cloud Tasks/Batch → Google
  cobra a la plataforma el costo real de infra (ej. $0.10).
- Ventajas remarcadas: la plataforma nunca toca los $100 completos (ventaja
  fiscal — solo declara los $5 de comisión); el modelo escala automáticamente.

### Piso 6 — Infraestructura dedicada por cliente (aislamiento de cómputo)
- Pregunta original: ¿se pueden abrir 20 VMs/Batch por usuario final en vez de
  infraestructura compartida, para que el cliente tenga "sus propias máquinas"?
- Confirmado, con **dos formas**:
  - **Forma 1 — plataforma dueña de la cuenta GCP, etiquetado por cliente**:
    Jobs con etiqueta `cliente: cliente_a`; Google cobra a la plataforma; la
    plataforma lee los reportes de facturación por etiqueta y recobra al cliente
    vía Stripe + margen.
    - Pros: UX perfecta (un clic), control total del código/seguridad.
    - Contras: si el cliente no tiene fondos después de que las máquinas ya
      corrieron, **la plataforma absorbe el costo** (riesgo de crédito).
  - **Forma 2 — BYOC (Bring Your Own Cloud)**: el cliente conecta su propia
    cuenta GCP (credenciales/IAM); el backend llama la API del proyecto GCP del
    cliente; las VMs se encienden dentro de la cuenta del cliente; Google le
    factura directo a él; la plataforma solo cobra una suscripción de software.
    - Pros: riesgo financiero CERO para la plataforma; privacidad extrema (los
      datos nunca salen de la cuenta del cliente) — bueno para verticales
      regulados (bancos, hospitales).
    - Contras: configuración compleja (el cliente necesita conocimiento
      técnico/equipo de sistemas para dar permisos IAM correctos).
  - Confirmado que Cloud Batch soporta `taskCount: 20, parallelism: 20` (20 VMs
    simultáneas independientes), y que dos clientes pueden tener cada uno sus 20
    VMs corriendo en paralelo sin interferirse — **con la salvedad explícita de
    que esto depende de que la cuenta tenga cuota suficiente** (límite real de
    GCP, no ilimitado, no verificado contra las cuotas reales del proyecto).

### Meta — Exportar la conversación
- El usuario preguntó cómo bajar el chat a txt/md; Gemini ofreció exportar a
  Docs, copiar/pegar, o generar un bloque markdown; se generó un resumen final en
  5 secciones (el que se documenta arriba), y es justo ahí donde aparece la única
  mención de Cloud Armor.

---

## 2. Enriquecimiento — ideas nuevas, más allá de la conversación con Gemini

1. **El Piso 1 ya existe en producción, no es hipotético.** Según
   `investigacion-escalamiento-masivo.md`, la cola `pdf-generator-queue` de Cloud
   Tasks ya corre con tuning real medido (`maxConcurrentDispatches=8`,
   `concurrency=5` en Cloud Run, hasta 10 instancias, 2 workers/instancia → techo
   estructural de **20 renders simultáneos**). No hay que decidir construir el
   Piso 1: ya existe, y ya se sabe que el cuello de botella observado (78
   PDFs/min con solo 7/10 instancias usadas) apunta más a la tasa de despacho de
   la cola que a falta de máquinas — aunque eso mismo está marcado ahí como
   **inferencia fuerte, no hecho confirmado** (no se aisló el experimento).

2. **El proyecto ya tiene una propuesta interna que compite con "Cloud Batch" y
   dice algo distinto.** `propuesta-arquitectura-batch.md` propone **Cloud Run
   Jobs** (no Cloud Batch) como capa de distribución para el batch rediseñado —
   justamente para evitar la "cola central que alguien tiene que sintonizar"
   (backoff, profundidad, `maxConcurrentDispatches`) que ya causó un bug real
   documentado. Ese documento separa el problema en tres capas independientes:
   distribución (Cloud Run Jobs), velocidad por unidad (motor de render — ya se
   sabe que ReportLab es 10-15× más rápido que WeasyPrint), y algoritmo interno
   (vectorizado vs ciclo por fila). **Vale la pena resolver la tensión Cloud
   Batch (propuesta de Gemini) vs Cloud Run Jobs (propuesta interna) antes de
   construir cualquiera de las dos.**

3. **El benchmark real de motores PDF es un input de costo mucho mejor que las
   "horas de cómputo genéricas" del ejemplo de Gemini.** En vez de inventar tiers
   basados en VMs de Cloud Batch, el Piso 4 (perillas al usuario) podría
   calibrarse con datos ya medidos: ReportLab como opción "económica/rápida",
   `canvas_pipeline` (con diseño) como "premium". Esto es más barato de construir
   que todo el aparato de Cloud Batch + Stripe Connect, y reutiliza un hallazgo
   que ya se pagó (ver `project_benchmark_motores_pdf` en memoria).

4. **Fork de modelo de negocio sin resolver — el más importante de todos.**
   Stripe Connect (Piso 5) solo tiene sentido si CFDI Suite es un modelo
   **B2B2C/marketplace** (ej. despachos contables que a su vez tienen sus propios
   clientes finales que pagan). Si el modelo real es **B2C directo** (la
   empresa/contador paga directo a CFDI Suite), Stripe Connect es
   sobre-ingeniería — bastaría Stripe normal (Billing/Checkout con planes o
   medidor de uso). La conversación con Gemini nunca preguntó esto, asumió
   marketplace porque el usuario preguntó por "comisión".

5. **Modelo alternativo a "3 botones de tiempo/costo": créditos de cómputo
   desacoplados de usuario.** En vez de cotizar cada trabajo individualmente
   (como propone Gemini), vender un saldo de "créditos" recargable, donde el modo
   Premium consume créditos más rápido y el Económico más lento. Es más fácil de
   facturar (Stripe suscripción/recarga simple) y evita cotizar y cobrar por
   transacción cada vez.

6. **Cloud Armor no debería quedar como nota de pie de página.** CFDI Suite
   procesa datos fiscales de terceros (RFC, montos) — si algún día se expone un
   API pública con cobro por uso, la superficie de abuso (scraping, DDoS,
   cuentas fantasma probando el free tier) es real. Vale la pena evaluarlo, no
   descartarlo por default.

7. **Cuotas de proyecto GCP**: antes de prometerle a un cliente "tus propias 20
   VMs en paralelo" (Piso 6), verificar las cuotas reales del proyecto de GCP de
   CFDI Suite. `investigacion-escalamiento-masivo.md` ya señala esta misma duda
   sin resolver para el escalamiento general ("¿Cloud Run puede escalar a
   cientos/miles de instancias en segundos? No se verificó la tasa real de
   ramp-up ni las cuotas por proyecto/región").

8. **BYOC (Forma 2 del Piso 6) es la opción de menor riesgo financiero pero de
   mayor costo de ingeniería.** Manejar credenciales de terceros, multi-cuenta
   GCP, IAM cruzado, es un proyecto de integración serio, típicamente solo
   justificado por clientes enterprise reales que ya lo piden, no como default.

9. **Nota fiscal, recursiva y algo irónica.** Si la plataforma cobra comisión
   (Piso 5) por generar CFDIs de terceros, la propia plataforma —al ser mexicana
   y facturar— probablemente necesita emitir sus propios CFDIs por esa comisión
   ante el SAT. No perder de vista este detalle al diseñar el flujo de Stripe
   Connect.

---

## 3. Clasificación decision-expander (hechos vs hipótesis vs riesgos)

**Hechos verificados (código/memoria/docs reales del proyecto):**
- Cloud Tasks ya está en producción para el batch masivo, con tuning real medido:
  `maxConcurrentDispatches=8`, `concurrency=5`, hasta 10 instancias, 20 renders
  simultáneos como techo estructural (`investigacion-escalamiento-masivo.md`).
- Redis + Pusher ya dan progreso en tiempo real del batch.
- El benchmark de motores PDF ya midió costo-por-XML con precisión real: todos
  los motores monolíticos son superlineales; ReportLab 10-15× más rápido que
  WeasyPrint; chunk+merge linealiza (~10× speedup medido).
- El backend real es Python/FastAPI — los snippets JS/Fastify de la conversación
  con Gemini son ilustrativos, no trasplantables.
- Ya existe una propuesta interna (`propuesta-arquitectura-batch.md`) que elige
  **Cloud Run Jobs**, no Cloud Batch, para el batch rediseñado.
- Precios reales de Cloud Run buscados (no inventados): $0.000024 por
  vCPU-segundo; Compute Engine on-demand ~$0.0000097 por vCPU-segundo (~2.5×
  más barato por cómputo crudo); Cloud Batch en sí no cobra extra, solo el
  cómputo que usa.

**Inferencia fuerte (documentación pública de GCP, o razonamiento del propio
proyecto, no hecho aislado):**
- Los parámetros de Cloud Tasks/Cloud Run que da la conversación con Gemini son
  reales y consistentes con la configuración de producción ya conocida.
- El modelo de costos (Cloud Batch cobra ciclo de vida completo de VM; Cloud
  Run/Tasks solo tiempo activo) es correcto y públicamente documentado.
- El cuello de botella del throughput actual (78 PDFs/min con solo 7/10
  instancias usadas) probablemente es la tasa de despacho de la cola, no falta
  de cómputo — pero no aislado experimentalmente.

**Hipótesis útil (razonable, pero sin validar para CFDI Suite específicamente):**
- Que Cloud Batch sea la pieza que falta — no está definido cuál es el "caso
  extremo" real del negocio (¿ha pasado alguna vez un batch de horas continuas?).
- Que el modelo de negocio sea marketplace (Stripe Connect) — depende del fork
  B2C vs B2B2C sin resolver.
- Los montos de ejemplo de Gemini ($5/$25/$150) son ilustrativos, no calculados
  con costos reales de CFDI Suite.
- Que abrir 20 VMs por cliente en paralelo para 2+ clientes simultáneos sea
  viable sin chocar cuota — no verificado.
- La tarifa Spot exacta usada en los cálculos de costo (`investigacion-
  escalamiento-masivo.md` usa ~70% de descuento como estimado conservador, no
  confirmado con la tarifa real del día).

**Riesgos:**
- Construir la UI de perillas sin telemetría real de qué tamaños suben los
  usuarios hoy → tiers mal calibrados.
- Invertir en Stripe Connect antes de resolver si el modelo es B2C o B2B2C →
  trabajo desechable.
- Subestimar el costo de ingeniería de BYOC por parecer "la opción financiera
  segura".
- Tratar Cloud Armor como ya evaluado cuando solo se mencionó una vez de pasada.
- Avanzar con "Cloud Batch" (idea de Gemini) sin resolver primero contra "Cloud
  Run Jobs" (propuesta interna ya escrita) — riesgo de construir dos soluciones
  para el mismo problema.

**Prueba mínima para salir de la duda:**
1. ¿Ha existido ya, o se anticipa, un escenario real de "una sola tarea de horas
   continuas" en CFDI Suite? Si nunca ha pasado, el Piso 2 (Cloud Batch) es
   prematuro — y la pregunta 1 de `investigacion-escalamiento-masivo.md` ("¿es
   pico ocasional o sostenido 24/7?") ya apunta a esto mismo sin resolver.
2. Resolver el fork de modelo de negocio (B2C directo vs B2B2C/despachos
   revendiendo) — decisión de producto, no técnica, y la que más cambia todo lo
   demás.
3. Simular el pricing de 3 niveles con los números REALES del benchmark de
   motores y de `investigacion-escalamiento-masivo.md` (no las horas-VM
   genéricas de Gemini) para ver si los precios resultantes tienen sentido de
   negocio.
4. Reconciliar explícitamente Cloud Batch vs Cloud Run Jobs como capa de
   distribución antes de tocar código.

---

## 4. La brecha entre el mensaje original del usuario y la conversación completa

El mensaje inicial del usuario (el que abrió esta exploración) pidió medir "por
cuántas zips o xml o transformación de PDF" en vez de por usuario, y mencionó
"lo de las perillas me gustó" sin especificar cuáles. Comparado con la
conversación completa:

**Cosas presentes en la conversación con Gemini que el mensaje original nunca
mencionó:**
- Ningún servicio específico de GCP (Cloud Run, Cloud Tasks, Cloud Batch por
  nombre).
- El mecanismo de Stripe Connect / comisión de marketplace.
- Infraestructura dedicada por cliente / BYOC — un "piso" entero ausente del
  framing original.
- Las perillas concretas: dropdown de velocidad, botón de "modo turbo", candado
  de presupuesto, y el menú de 3 opciones (Económico/Balanceado/Premium) con
  tiempo y precio mostrados antes de procesar.
- Cloud Armor.
- Quién asume el riesgo financiero si un cliente no paga (Forma 1 vs BYOC).

**La tensión más importante encontrada:** el mensaje original propuso medir por
**volumen** (conteo de zips/xml). Pero el criterio real que usa la conversación
con Gemini para decidir entre Cloud Tasks vs Cloud Batch es distinto: no es
cuántas peticiones entran, sino **cuánto tarda una sola tarea en procesarse**.
Son dos métricas diferentes que pueden apuntar a arquitecturas distintas — el
conteo apunta a un modelo de "créditos por unidad procesada"; la duración por
tarea apunta a decidir el motor/infra según el tamaño de UN documento. No quedó
resuelto ni en el mensaje original ni en la conversación con Gemini.

---

## 4.5. Hilos sueltos: cosas mencionadas una vez y nunca resueltas

Peinando la conversación completa (2,283 líneas) buscando específicamente ideas que
Gemini propuso y que el usuario nunca volvió a preguntar ni a confirmar. Donde fue
posible, se verificó contra el código real de CFDI Suite en vez de asumir.

1. **Pruebas de carga (Load Testing) — el hilo más importante.** Es la primerísima
   respuesta de Gemini a la pregunta de apertura ("¿cuántos usuarios aguanta mi
   app?"): *"para saber el límite real, hacemos Pruebas de Estrés"*. Nunca se
   volvió a mencionar en el resto de la conversación. **Verificado: no hay
   `locust`, `k6` ni ningún script de stress-test en el repo.** Sigue
   completamente abierto — es la respuesta más directa a la pregunta original y
   nunca se ejecutó.
2. **URL firmada para subir directo a Cloud Storage (bypass del backend).**
   Mencionado una sola vez; la conversación se desvió de inmediato a otra
   pregunta y nunca se retomó. **Verificado en código: YA ESTÁ CONSTRUIDO.**
   `backend/app/routers/pdf.py:646-676` (`request_upload_url()`) y `pdf.py:679-707`
   generan signed URLs v4 para subida y descarga directas, con un comentario en
   el código casi idéntico al razonamiento de Gemini ("evita el límite de 120s de
   proxies externos para lotes grandes"). Caso donde la idea "no perseguida" en
   la charla ya estaba resuelta en producción.
3. **Dead-letter queue para tareas que fallan repetidamente.** El usuario
   respondió "creo que sí tengo, necesito checarlo" y nunca lo confirmó.
   **Verificado: no hay rastro de dead-letter queue en el código.** A diferencia
   del punto 2, aquí la suposición del usuario no está respaldada por el código —
   vale la pena revisarlo de verdad.
4. **Verificación de integridad del ZIP subido (hash MD5/SHA-256).** Propuesto y
   bien recibido ("está excelente esa idea"), pero sin rastro en el código.
   Abierto, sin implementar.
5. **Prioridad de tareas en Cloud Tasks.** El usuario dijo que quería saber más,
   pero la conversación pivoteó a pedir "trucos generales" y nunca se profundizó.
   No hay uso de prioridad en el código. **Conexión que nunca se hizo en la charla
   misma**: esto es el mecanismo técnico que haría funcionar la perilla
   "premium = más rápido" (Piso 4/5) sin necesitar infraestructura dedicada — un
   cliente que paga más podría simplemente obtener prioridad de despacho.
6. **Optimización de cold start** (imagen de contenedor más pequeña, inicializar
   conexiones pesadas de forma perezosa) — mencionado, nunca verificado si se
   aplica hoy.
7. **Cloud Functions como disparador event-driven** (activar Cloud Batch
   automáticamente al detectar una subida a Storage) — a diferencia de los demás,
   este **fue rechazado explícitamente** por el usuario en el momento ("no, no,
   no, estamos enfocándonos en Tasks"), no simplemente olvidado.
8. **Buenas prácticas de Cloud Storage** (bucket en la misma región que el
   cómputo, clase de almacenamiento según frecuencia de acceso, operaciones en
   lotes para archivos grandes) — aceptado sin objeción, nunca verificado si ya
   se cumple.

---

## 5. Preguntas abiertas pendientes de decidir con el usuario

1. **Alcance**: ¿esto es solo sobre la feature de conversión (XML→PDF, ZIP
   masivo), o sobre el modelo de negocio completo de CFDI Suite? Son proyectos de
   tamaño muy distinto.
2. **Métrica de pricing**: ¿conteo de documentos procesados, o duración/costo de
   cómputo por tarea? ¿O ambos, en ejes distintos (uno para routing técnico, otro
   para facturación)?
3. **Modelo de negocio**: ¿B2C directo (el contador/empresa paga directo) o
   B2B2C/marketplace (despachos que revenden a sus propios clientes, ameritando
   Stripe Connect)?
4. **Cloud Batch vs Cloud Run Jobs**: ¿cuál captura mejor el "caso extremo" de
   CFDI Suite, si es que existe ese caso hoy?
5. **Telemetría**: ¿existe ya un registro de la distribución real de tamaños de
   ZIP/XML que suben los usuarios? Sin eso, cualquier definición de tier es
   arbitraria.
6. **Deuda técnica destapada por los hilos sueltos (§4.5)**: ¿se corre un load
   test real antes de seguir? ¿Existe de verdad el dead-letter queue que el
   usuario creía tener, o hay que construirlo?
