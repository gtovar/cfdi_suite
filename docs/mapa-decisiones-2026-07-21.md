# Mapa de decisiones: rutas para CFDI Suite tras las dos mesas del 2026-07-21

> Este documento recoge los "forks" (bifurcaciones de decisión) que emergieron de
> `investigacion-escalamiento-masivo.md`, `mesa-decision-escalamiento-masivo-2026-07-21.md`,
> `business-model-conversion-exploration.md` y `mesa-decision-modelo-negocio-2026-07-21.md`.
> No es un plan — es un mapa de caminos con sus consecuencias, para que se elija una
> ruta (o se combine una nueva) con evidencia, no con adivinanza. El usuario pidió
> explícitamente que esto se resuelva con un equipo de agentes que investigue, no que
> se quede como un menú de opciones sin resolver.

## Fork 0 — el único que es un hecho, no una decisión, y sigue sin verificar

**¿CFDI Suite ya tiene usuarios externos usando el producto hoy (aunque sea gratis), o
sigue siendo interno/pre-lanzamiento?** No es una preferencia — es un dato objetivo
que no se ha verificado contra el repo. Cambia la urgencia de todo lo demás:
- Si ya hay usuarios externos hoy sin auth real (confirmado: cero auth en el código,
  ver `mesa-decision-modelo-negocio-2026-07-21.md`, hallazgo de `bm-sre`) → riesgo de
  abuso/costo HOY, no solo bloqueo de monetización futura.
- Si sigue siendo interno/pre-lanzamiento → no hay urgencia de auth hasta que se
  decida lanzar.

**Esto se puede investigar en el repo** (frontend con pantalla de login/signup,
librerías de auth en `package.json`, tabla de usuarios/clientes en algún modelo de
datos, dominio custom en configuración de Vercel, menciones a "usuarios reales" o
"clientes" en commits/README/CHANGELOG, Sentry configurado para producción real).

## Fork 1 — Alcance: ¿cobrar solo la conversión, o toda la plataforma?

- Solo conversión: medidor atado a "trabajos de conversión" (PDFs generados). Más
  simple, mismo patrón MVP que ya siguió la Capa 1.
- Toda la plataforma (análisis + conversión + lo que venga): medidor cubre todos los
  endpoints desde el día uno. Más caro ahora, evita rehacer el medidor después.
- Esta decisión NO cambia la Fase -1 (auth/tenant/metering) — solo cambia qué se mide
  primero.

## Fork 2 — Modelo de negocio: B2C / B2B2C / Agnóstico-por-ahora

- **B2C directo**: Stripe normal, auth simple, un tenant = un usuario. Créditos de
  cómputo encajan perfecto. Se descarta Stripe Connect.
- **B2B2C/marketplace**: tenant jerárquico (despacho → sub-clientes), Stripe Connect,
  nota fiscal recursiva (comisión propia necesita su propio CFDI ante el SAT). Mucha
  más ingeniería inicial.
- **Agnóstico por ahora**: tenant = "cuenta" sin jerarquía todavía, créditos de
  cómputo (funcionan en ambos modelos, confirmado por `bm-impacto`), posponer
  Stripe Connect vs. normal hasta tener telemetría real de qué cliente predomina.

## Fork 3 — Deuda técnica (Fase 0 de la mesa técnica): ¿cerrar DLQ+load test ya, o esperar?

Recomendación sin bifurcar: cerrarlo ya, sin importar el resto — no depende de si se
monetiza o no, protege contra fallo silencioso hoy mismo con cualquier volumen. Barato
(load test aislado, no toca prod).

## Fork 4 — Fase -1 (auth/tenant/metering): ¿construir ya, o esperar a resolver el Fork 2?

Recomendación sin bifurcar: construir la versión mínima ya (API key/auth simple +
tabla "cuenta" + contador de uso), sin esperar a resolver B2C/B2B2C — el mínimo común
denominador es igual en ambas ramas; si después se elige B2B2C, se agrega jerarquía
ENCIMA de esa base.

## Rutas completas (combinaciones)

1. **"Lean MVP monetizable"** — Fork 1=solo conversión, Fork 2=Agnóstico/créditos,
   Fork 3=cerrar ya, Fork 4=construir mínimo ya. Ruta de menor arrepentimiento.
2. **"Freeze y validar primero"** — Fork 3=cerrar (activar Capa 1 + Etapa 4), Fork
   4=NO construir nada de negocio todavía; validar con clientes reales primero.
3. **"Apuesta B2B2C agresiva"** — Fork 2=B2B2C desde el inicio, Fork 4=tenant
   jerárquico + Stripe Connect directo. Solo si ya hay señal de mercado clara.
4. **"Solo arreglar lo técnico, cero negocio por ahora"** — Fork 3=sí, Fork 4=no,
   punto. Cierra deuda técnica, activa lo ya construido, para ahí.

## Lo que se le pide al equipo de agentes

No repetir el mapa — **resolverlo con evidencia**: investigar el Fork 0 en el repo
real, validar la factibilidad técnica de la Fase -1 mínima, evaluar Fork 2 desde
perfil de cliente real (CFDI = contexto fiscal mexicano, contadores/despachos), y
converger en una recomendación concreta (una ruta, o combinación nueva), no en un
menú.

---

## RESUELTO (2026-07-21) — equipo de 4 agentes + síntesis

**Fork 0**: interno/pre-lanzamiento, cero usuarios externos reales (evidencia:
`getAuthHeaders`/`triggerLogin` vacíos en `frontend/src/pages/Editor.jsx:27-28`, cero
libs de auth, cero modelo de usuario/cliente, dominio preview de Vercel, cero mención
a "clientes"/"beta" en commits). Matiz que no se resuelve limpio: la app es alcanzable
por cualquiera con la URL, sin ningún candado — barrera de entrada al abuso es cero
aunque no haya evidencia de que se haya explotado.

**Fork 2**: **B2C directo**, con evidencia real de producto (`README.md`,
`arquitectura.md`) — CFDI Suite no emite CFDIs ni integra PAC/SAT, es herramienta de
revisión para quien recibe XML de terceros. El despacho es cliente directo, no
intermediario de cobro. Se descarta Stripe Connect por ausencia total de señal.

**Fork 4 corregido**: la Fase -1 "mínima" NO es un fin de semana. El costo real no es
la autenticación (barata: ~3 módulos, metering casi gratis sobre Redis ya persistente)
sino la **autorización/scoping** — los recursos viven hoy en un namespace global sin
dueño (emisores enumerables por RFC, jobs/batches/templates sin verificación de
propietario, URLs firmadas sin scope antes de emitirse). Toca los 7 routers del
backend.

**Hallazgo nuevo, independiente**: `credentials.py` ya está roto en producción (la
llave Fernet se regenera por instancia de Cloud Run — una instancia no descifra lo que
escribió otra, se pierde al reiniciar). Bug de correctness activo hoy, no decisión de
negocio.

### Ruta final recomendada — secuencia corregida

1. **Ahora, sin condición**: arreglar `credentials.py` (Secret Manager) — bug de
   pérdida de datos activo, desacoplado de todo lo demás.
2. **Ahora, sin condición**: cerrar la Fase 0 técnica (DLQ + load test +
   `REDIS_PASSWORD`).
3. **Construir la Fase -1 completa (auth + scoping por cuenta) antes de cualquier
   lanzamiento externo real** — rediseño deliberado de los 7 routers, no parche. Hoy
   es la ventana barata para hacerlo bien (pre-lanzamiento, sin datos de clientes
   reales encima todavía).
4. **Mientras se construye lo anterior**: candado barato interino (API-key compartida
   o allowlist de IP) para cerrar la barrera de entrada cero sin esperar el sistema
   completo.
5. **Destino de negocio declarado: B2C directo** — tenant plano + créditos de
   cómputo + Stripe normal. No Stripe Connect, no jerarquía.
6. **No lanzar públicamente hasta que 1-3 estén cerrados.**

---

## Corrección (2026-07-21): cómo saber si un pico es aleatorio o agendable, sin que un humano lo adivine

Surgió la pregunta de si se puede automatizar/instrumentar la respuesta a "¿el tráfico
es aleatorio (Poisson) o programable (agenda, ej. cierre de mes)?", en vez de que un
humano la responda a ojo. Primera respuesta propuesta (mirar el historial ya existente
de Cloud Monitoring) **tenía un defecto real, detectado por el usuario**: ese
historial es 100% de pruebas propias — no hay usuarios externos reales todavía
(consistente con el Fork 0 de arriba, "interno/pre-lanzamiento"). Mirar esa gráfica no
revela nada sobre el comportamiento de un contador real, solo revela cuándo se hicieron
pruebas.

**Conclusión corregida: hoy esta pregunta no se puede contestar con datos, porque no
existe la señal.** No hay script ni instrumento que la responda antes de que exista
tráfico real. Con eso claro, quedan tres caminos, no uno:

1. **Conocimiento del dominio, sin datos propios (hipótesis de trabajo, no hecho).**
   No hace falta tráfico propio para saber que México tiene fechas fiscales fijas
   (declaraciones mensuales, cierres de quincena/mes) — es información pública del
   calendario contable. Válida para diseñar, pero sigue siendo **hipótesis** hasta
   verse en tráfico real.
2. **Instrumentar ahora, para que la pregunta se conteste sola después.** No genera
   señal hoy, pero si el logging/telemetría de uso (ver pregunta abierta de
   telemetría) corre desde antes de lanzar, el día que entre el primer usuario real
   la pregunta se vuelve contestable automáticamente, sin trabajo extra. Sin esto, la
   pregunta nunca se contesta, sin importar cuánto tiempo pase.
3. **Descubrimiento de cliente directo — hablar con 2-3 contadores/despachos reales
   antes de lanzar** y preguntarles cuándo procesan sus facturas en bulto. Más rápido
   y más barato que esperar telemetría de producción.

**Recomendación**: usar (1) como hipótesis de diseño inicial, construir (2) ya (es
parte de la telemetría ya pendiente), y perseguir (3) si hay acceso a usuarios reales
antes del lanzamiento — es la señal de mayor calidad de las tres.
