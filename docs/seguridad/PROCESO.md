# Proceso de corrección de seguridad — estado y siguiente paso

> **Si llegas en frío a este repo y te toca trabajo de seguridad, empieza aquí.**
> Este archivo dice en qué fase va el proceso y qué archivo leer para continuar.
> Cada fase produce el artefacto que arranca la siguiente. No hay contexto que
> viva sólo en una conversación.

---

## Por qué existe este proceso

El registro de seguridad de `cfdi_suite` creció en tres herramientas distintas
(aider, opencode, Claude Code con Sonnet) sin reconciliarse entre sí. Llegó a
tener 160 hallazgos repartidos en siete fuentes, con cero fixes aplicados y sin
manera de saber sobre qué lista trabajar.

El proceso separa el trabajo por lo que cuesta: reconciliar es mecánico y va a
código, decidir arquitectura es caro y va a un modelo capaz, aplicar specs ya
escritas es barato y no justifica un modelo caro.

---

## Estado

| Fase | Qué hace | Estado | Artefacto que produce |
|---|---|---|---|
| **0 — Reconciliación** | Unifica las 7 fuentes en un registro con estado de verificación computado | ✅ Cerrada 2026-07-26 | `registro-unificado.md` |
| **1 — Planeación** | Dedup semántico, subsunción, decisión de arquitectura de auth, plan ordenado | ✅ Cerrada 2026-07-26 | `plan-fixes.md` actualizado + `prompt-fase2.md` |
| **2 — Ejecución** | Aplica los fixes en el orden que fijó la Fase 1 | 🟢 Lista para arrancar | Los fixes aplicados |
| **3 — B-lite (identidad)** | Login real + aislamiento por tenant. Cierra 14 hallazgos que la Fase 2 no puede tocar | ⬜ Bloqueada por una decisión del dueño | Por definir |

---

## Qué decidió la Fase 1 (2026-07-26)

Tres cosas, para que no haya que releer 900 líneas de plan:

1. **Auth: se cierra el borde interno, se rechaza el proxy autenticado de Vercel,
   el login real queda para la Fase 3.** Poner identidad entre Vercel y Cloud Run
   no cierra ni uno de los ~30 endpoints anónimos (el dominio de Vercel también
   es público) y rompería las subidas grandes (el cómputo de Vercel topa el body
   en 4–4.5 MB). Lo que sí se hace ya: `oidc_token` en Cloud Tasks y verificación
   en los tres endpoints internos — mata 3 hallazgos CRITICAL/HIGH.
2. **#36 y #37 (la e.firma usada, sobrescrita y borrada sin autenticación) se
   recalibraron de MEDIUM a HIGH.** El scanner medía radio de explosión en el
   contenedor; una e.firma es la identidad legal del contribuyente ante el SAT.
   Y son justo los hallazgos que ninguna variante de "cerrar el borde" toca.
3. **Los 160 hallazgos colapsaron a ~30 defectos reales** por dedup semántico y
   subsunción. Las 62 filas de auditoría pasaron de 29 a **62 con spec detectada**.

Se descubrió además que el rewrite de `vercel.json` **está muerto** para la mayor
parte del tráfico: `VITE_API_BASE_URL` está configurada en Vercel Production con
la URL de Cloud Run, así que ~13 call sites hablan directo con el backend. Está
documentado como hecho P1 en `plan-fixes.md`.

---

## Cómo continuar

**Estás en Fase 2.** Abre una sesión nueva con un modelo barato y escribe:

```
Lee docs/seguridad/prompt-fase2.md y ejecuta esas instrucciones.
```

Nada más. Ese archivo está escrito para arrancar en frío: trae la decisión de
auth, la lista ordenada de 56 pasos con archivo:línea y puntero a su spec, qué no
se toca y por qué, cómo verificar, y dónde hay que parar.

**El paso 12 (cerrar el borde interno con OIDC) conviene que lo ejecute un modelo
capaz**, no barato: toca el orden de despliegue y la spec original tiene un
comentario que contradice a su propio código. Está marcado como tal en el archivo.

**Cuando la Fase 2 llegue a su corte**, el siguiente movimiento no es otro prompt:
es una decisión del dueño sobre el mecanismo de identidad (B-lite). Ver "Dónde se
corta la Fase 2" en `prompt-fase2.md`.

> `prompt-fase1.md` se conserva como registro de lo que se le pidió a la Fase 1.
> Ya no hay que ejecutarlo.

---

## Reglas que valen en todas las fases

1. **El modelo nunca se autodeclara verificado.** El estado de verificación de un
   hallazgo lo computa código que cuenta votos de panel — `scripts/verify.py`,
   `scripts/compute_votes.py`. Un modelo puede triagear y recomendar; no puede
   declarar algo "verificado".

2. **`plan-fixes.md` se actualiza de forma incremental, nunca se regenera.**
   Tiene 1,396 líneas de specs con antes/después y comandos de verificación. Si
   una spec queda obsoleta se marca obsoleta con el motivo; no se borra.

3. **Gana el código, no el doc.** Las columnas "Estado" de las tablas de
   auditoría no son fuente de verdad. Si un doc dice que algo está arreglado, se
   comprueba con `grep` contra el código antes de creerle.

4. **Cuidado con el formato al escribir en `plan-fixes.md`.** PR 1, 2 y 4 usan
   encabezados `### Fix #N`; PR 3 usa marcadores inline `**#N:`. Escribir con la
   convención equivocada rompe la detección de specs de `reconcile_registry.py`
   en la siguiente corrida. Ya pasó una vez: 5 specs quedaron invisibles.

5. **Lo que se deja fuera se dice.** Omitir en silencio es peor que dejar fuera
   con motivo.

---

## Qué hay en cada archivo

| Archivo | Qué es |
|---|---|
| `registro-unificado.md` | Los 160 hallazgos, generados por script. 33 verificados por panel, 58 sin panelear, 7 rechazados, 29 con spec ya escrita. |
| `plan-fixes.md` | Las specs de fix con antes/después y comandos de verificación. |
| `08-auditoria-actual.md` | La auditoría original. Llega al hallazgo #62. **No incluye los batches 6, 7 y 8** — por eso existe el registro unificado. |
| `batch-4/` … `batch-8/` | Salida cruda de los scans: `findings.json`, `votes.json`, `coverage.json`. |
| `scripts/reconcile_registry.py` | Regenera el registro unificado. Determinista, sin LLM, con asserts de completitud. Correr cuando aparezca un batch nuevo. |

---

## Deuda conocida

- `README.md` de esta carpeta dice "34 hallazgos". El conteo real es 160.
- Los batches 6, 7 y 8 nunca se reconciliaron dentro de `08-auditoria-actual.md`.
  El registro unificado los cubre, pero `08` sigue incompleto como documento.
  **Consecuencia práctica:** `reconcile_registry.py` detecta specs sólo por
  número (`#N`), así que los hallazgos con id de batch van a mostrar `—` en la
  columna `spec` para siempre, aunque su fix esté escrito. Cerrarlo requiere
  asignarles números #63+ dentro de `08-auditoria-actual.md` — mecánico, barato,
  y hasta entonces esa columna no mide cobertura para las filas de batch.
- **7 hallazgos esperan panel adversarial** después de la Fase 1:
  `BATCH6-CANDIDATE-12` (llave Fernet compartida FIEL↔PAC), `BATCH6-CANDIDATE-09`
  y `-10` (inyección en headers de respuesta), y los 3 de estado sensible en
  React DevTools. Se panelean con modelo barato por el pipeline que ya existe;
  no bloquean la Fase 2.
- **La API sigue anónima al terminar la Fase 2, y es a propósito.** Cloud Run
  responde a cualquiera en internet (`GET /openapi.json` → 200) y hay cero
  `Depends()` en `backend/app/`. Eso sólo lo cierra la Fase 3.
