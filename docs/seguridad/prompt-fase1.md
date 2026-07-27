Eres el planeador de seguridad de cfdi_suite. Tu entregable es un plan.
NO escribas código de la aplicación. NO apliques ningún fix. El único archivo
que actualizas es docs/seguridad/plan-fixes.md, y sólo de forma incremental.

## Punto de partida

Lee `docs/seguridad/registro-unificado.md`. Es la reconciliación mecánica ya
hecha de todas las fuentes (`08-auditoria-actual.md` + `docs/seguridad/batch-4..8/`),
generada por `scripts/reconcile_registry.py` — determinista, sin LLM, con asserts
de completitud. Trabájalo como tu inventario. No releas los `batch-*/findings.json`
salvo que necesites el detalle de un hallazgo específico.

Su contenido, ya verificado. No lo recuentes:

- 160 hallazgos: 98 candidatos de batches + 62 filas de auditoría.
- 33 verificados por panel adversarial (19 unánime 3/3, 14 mayoría 2/3).
- 7 rechazados por panel, en sección aparte al final con su motivo.
- 58 nunca pasaron por panel. Todos MEDIUM/LOW por etiqueta de scanner.
- 29 ya tienen spec de fix escrita en `plan-fixes.md`.

## Hechos verificados del código

Comprobados a mano contra el repo, no contra la columna "Estado" de ningún doc.
Si alguno no cuadra con lo que veas, corre su comando y gana el código. No gastes
exploración re-derivando los que sí cuadran.

| Hecho | Re-verificar con |
|---|---|
| Cero fixes aplicados. `ssl_cert_reqs=None` sigue en `batch.py:52`, `pdf.py:74`, `batch_shard_worker.py:59` | `grep -rn "ssl_cert_reqs" --include="*.py" .` |
| Sin `resolve_entities`, sin `oidc_token`, sin `defusedxml`, sin `slowapi` | `grep -rn "resolve_entities\|oidc_token\|defusedxml\|slowapi" --include="*.py" --include="*.txt" .` |
| Cloud Run acepta invocación anónima | `grep -rn "allow-unauthenticated" --include="*.yml" --include="*.yaml" .` → `cloudbuild.yaml:22`, `deploy-backend.yml:62` |
| Cero `Depends()` en TODO `backend/app/`, no sólo en routers. ~30+ endpoints sin auth | `grep -rc "Depends(" backend/app/` → 0 |
| Vercel reescribe `/api/:path*` → Cloud Run | `cat vercel.json` |
| Un call site se salta el rewrite y pega directo a Cloud Run | `frontend/src/components/BatchAnalysisPage.tsx:160` |
| `plan-fixes.md` cubre #1–#34 (29 specs). `08-auditoria-actual.md` llega a #62. Hueco: #35–#62 | `grep -n '^### Fix #\|^\*\*#[0-9]' docs/seguridad/plan-fixes.md` |
| Batches 6/7/8 nunca se reconciliaron dentro de `08-auditoria-actual.md` | `grep -c "Batch 6\|Batch 7\|Batch 8" docs/seguridad/08-auditoria-actual.md` → 0 |
| #36 y #37 están catalogados MEDIUM: la e.firma se usa contra el portal real del SAT sin auth, y cualquiera puede sobrescribirla o borrarla | `grep -nE '^\| *(36\|37) *\|' docs/seguridad/08-auditoria-actual.md` |

## Tarea 1 — Dedup semántico y subsunción

El registro está deduplicado por id, pero NO semánticamente. Ese es tu trabajo.

- Colapsa los hallazgos que son el mismo defecto descrito por distintos scanners.
  Una fila, varias fuentes. Ejemplo del tipo de cosa que buscas: `#4 Error details
  leaked` y `B8-FINDINGS-AUTH-01 Backend SAT enquiry error details rendered raw`
  son plausiblemente el mismo defecto; ningún string match lo resuelve.
- Construye el árbol de subsunción. Muchos hallazgos dicen literalmente "sin
  autenticación" en su descripción: son hijos de un mismo padre. Un hijo no se
  agenda antes que su padre.
- Los 58 candidatos sin panel: agrúpalos por clase de defecto y triágialos **por
  grupo**, no uno por uno. Para cada grupo, una de tres salidas: subsumido por un
  padre (nómbralo), merece panel real, o cerrable sin panelear con el motivo.
  No los declares "verificados" bajo ninguna circunstancia — eso lo computa el
  panel, no tú. El repo ya tiene esa regla escrita en `scripts/verify.py`.

## Tarea 2 — Decide la arquitectura de autenticación

Es la decisión que reordena todo lo demás. Tienes autoridad para elegir; no la
implementas. Separa y evalúa por separado:

- **(A) Cerrar el borde:** identidad entre el proxy de Vercel y Cloud Run, quitar
  `--allow-unauthenticated`, y eliminar la URL directa hardcodeada de
  `BatchAnalysisPage.tsx:160`. Sin login de usuario, sin cambio de producto.
- **(B) Login real** con aislamiento por tenant de FIEL y emisores.

Verifica en el repo antes de estimar, no razones en abstracto:

- ¿Un rewrite de `vercel.json` puede inyectar una credencial en el request
  upstream, o hace falta una Vercel Function / middleware? Compruébalo.
- ¿Cuántos call sites del frontend van directo a Cloud Run en vez de por el
  rewrite? Enuméralos todos.
- ¿Qué otros llamadores hay que acreditar? Cloud Tasks y el batch shard worker
  también invocan al backend.

Elige, y escribe el porqué. Sé explícito sobre el límite de lo que elegiste: si
eliges (A) sin (B), un atacante sigue llegando a la API por el dominio de Vercel.
Di qué hallazgos mueren con tu elección y cuáles sólo se atenúan.

Considera además si #36/#37 están bien calibrados como MEDIUM. Una FIEL es una
credencial de firma legalmente vinculante ante el SAT. Da tu lectura.

## Tarea 3 — El plan de ataque

Actualiza `docs/seguridad/plan-fixes.md` de forma **incremental**. Ya tiene 1,396
líneas con 29 specs (antes/después + comandos de verificación) para #1–#34, y
siguen siendo válidas porque nada se implementó. Agrega lo que falta: #35–#62 y
lo que venga de los batches. Si una spec queda obsoleta por tu decisión de auth,
márcala obsoleta con el motivo. No la borres.

Ojo con el formato: PR 1, 2 y 4 usan encabezados `### Fix #N`; PR 3 usa marcadores
inline `**#N:`. Respeta la convención de la sección donde escribas, o rompes la
detección de specs de `reconcile_registry.py` en la próxima corrida.

Ordena por severidad verificada × subsunción. Cuando severidad y dependencia
choquen, gana la dependencia, y escribes una línea diciendo dónde chocaron. Dentro
de cada nivel agrupa por esfuerzo (quick win / sprint / arquitectura), porque eso
sirve para decidir qué cabe en una sesión.

Marca cada ítem con quién debería ejecutarlo. Los que ya tienen spec mecánica con
antes/después no necesitan un modelo caro.

## Entrega

Tres cosas.

**1.** El `plan-fixes.md` actualizado.

**2.** Una tabla de una página: qué se hace primero, qué hallazgos cierra cada
paso, y qué queda fuera de alcance con el motivo. Si dejas algo fuera, dilo. No
lo omitas en silencio.

**3.** `docs/seguridad/prompt-fase2.md` — el encargo ejecutable para quien
implemente, escrito para que una sesión **en frío**, sin este contexto y con un
modelo barato, pueda arrancar leyéndolo y nada más. Esto no es opcional: sin
este archivo, la Fase 2 no tiene de dónde agarrarse.

Debe contener:

- **Qué decidiste sobre auth y por qué**, en un párrafo. Quien implemente no va
  a releer tu razonamiento completo, pero necesita saber qué está construyendo
  y qué límite tiene.
- **La lista ordenada de fixes a aplicar**, cada uno con: número de hallazgo,
  archivo:línea, y puntero a su spec en `plan-fixes.md` (`### Fix #N` o el
  marcador inline `**#N:`, según la sección). No copies las specs; apunta a ellas.
- **Qué NO se toca en Fase 2** y por qué. Los hallazgos que dependen de una
  decisión aún no tomada, los que esperan panel, los que subsumiste.
- **Cómo verificar cada fix**, reusando los comandos que ya existen en las specs
  de `plan-fixes.md`.
- **Dónde se corta la Fase 2.** Nombra explícitamente el punto donde hay que
  volver a parar y decidir en vez de seguir aplicando.

Al terminar todo, actualiza `docs/seguridad/PROCESO.md`: marca Fase 1 como
cerrada con la fecha, y Fase 2 como lista para arrancar.
