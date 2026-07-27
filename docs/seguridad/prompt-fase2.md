# Fase 2 — Ejecución de fixes de seguridad

> **Lee este archivo y nada más para arrancar.** No necesitas el contexto de la
> Fase 1. Todo lo que hay que saber para empezar está aquí.
> Escrito el 2026-07-26 al cerrar la Fase 1.

---

## Qué eres y qué NO haces

Aplicas fixes que ya tienen spec escrita. Las specs viven en
`docs/seguridad/plan-fixes.md` — cada una trae **antes/después** y un **comando
de verificación**. Tú aplicas el diff y corres el comando.

**No decides arquitectura.** Si una spec te pide una decisión que no está escrita,
párate y pregunta. **No inventes autenticación** (ver "Dónde se corta" al final).

---

## La decisión de auth que ya se tomó, y su límite

**Se cierra el borde interno (Cloud Tasks con OIDC), se rechaza meter el tráfico
por un proxy autenticado de Vercel, y el login real queda fuera de la Fase 2.**

El porqué, en corto: el backend de Cloud Run responde anónimo a cualquiera en
internet (`GET /openapi.json` → 200) y tiene **cero** `Depends()` en todo
`backend/app/` — o sea, ~30 endpoints sin ninguna autenticación. Poner identidad
entre Vercel y Cloud Run **no arregla eso**, porque el dominio de Vercel también
es público: el atacante pediría `https://cfdiinspector.vercel.app/api/emisores` y
el proxy le adjuntaría la credencial. Además rompería el producto: inyectar una
credencial exige cómputo en Vercel (Middleware/Function), que topa el body del
request en 4–4.5 MB, y el flujo principal sube cientos de XMLs en un solo
multipart. Lo que **sí** se hace ahora es cerrar los endpoints internos que
invoca Cloud Tasks (`/api/internal/*` y `/api/cfdi/batch/worker-task`) con tokens
OIDC — eso mata tres hallazgos CRITICAL/HIGH sin tocar el modelo de producto.

**El límite, dicho sin adornos:** al terminar la Fase 2, **la API sigue abierta
a internet sin autenticación de usuario.** Los fixes de abajo cierran XXE, SSRF,
OOM, fugas de errores, inyección de fórmulas y todo el endurecimiento de infra y
CI/CD — pero no cierran "cualquiera puede llamar a la API". Eso requiere login
real (llamado **B-lite** en el plan) y es una decisión que se toma después.

---

## Antes de tocar nada

```bash
cd /Users/gil/Documents/cfdi_suite
git checkout -b seguridad/fase-2
python3 scripts/reconcile_registry.py --output docs/seguridad/registro-unificado.md
python3 -m pytest backend/tests/ -q          # baseline verde antes de empezar
```

**Reglas que valen todo el tiempo:**

1. **Gana el código, no el doc.** Si una spec dice que la línea 52 tiene X y no
   lo tiene, corre el `grep`, cree al código y anota la discrepancia. Esto no es
   teórico: las specs de los bloques 1–5 se verificaron línea por línea contra el
   archivo, pero **las de los bloques 8 y 9 se derivaron de la descripción de la
   auditoría** y sus fragmentos son indicativos. `plan-fixes.md` lo dice al
   inicio de `## PR 6`. Abre el archivo antes de editar.
2. **Un commit por fix**, con el número de hallazgo en el mensaje:
   `fix(seguridad): #39 openpyxl read_only para evitar OOM por zip bomb`.
3. **No despliegues a producción sin permiso explícito del dueño.** Ni backend
   ni frontend. Los merges a `main` disparan deploy automático — mantente en la
   rama.
4. **Si un fix rompe un test, párate.** No lo "arregles" relajando el test.

---

## Los fixes, en orden

El orden importa: hay dependencias marcadas con ⚠️. Dentro de cada bloque puedes
ir en cualquier orden. Cada fila apunta a su spec — **no la copies, léela ahí**.

### Bloque 1 — Quick wins (≈2h, todos mecánicos)

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 1 | Redis `ssl_cert_reqs=None` | `backend/app/routers/batch.py:52`, `backend/app/routers/pdf.py:74`, `backend/app/workers/batch_shard_worker.py:59` | `### Fix #9` |
| 2 | Zip bomb / OOM en `openpyxl` | `backend/app/routers/sat_enquiry.py:211` | `### Fix #39` |
| 3 | CORS `allow_methods=["*"]` | `backend/app/main.py:98` | `### Fix #19` |
| 4 | GCS CORS wildcard | `cors-gcs.json` | `### Fix #25` |
| 5 | Timeout de Cloud Run a 600s | `.github/workflows/deploy-backend.yml:66` | `### Fix #23` |
| 6 | `.dockerignore` ausente | `backend/Dockerfile:22` | `### Fix #42` |
| 7 | Imagen base sin digest | `backend/Dockerfile:1` | `### Fix #47` |
| 8 | Contenedor como root | `backend/Dockerfile` | `### Fix #50` |
| 9 | Sin `HEALTHCHECK` | `backend/Dockerfile` | `### Fix #54` |

> **#21 no se arregla: está mal escrito.** Dice que `batch.py:49` tiene
> `ssl_cert_reqs="required"` y eso **no existe en el código**. Los tres sitios
> son `None`. Lo cubre Fix #9. Ver `### Fix #21` en el plan.

### Bloque 2 — CRITICAL con spec

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 10 | XXE via `lxml` (3 call sites) | `backend/app/services/canvas_service.py:835,869,983` | `### Fix #1` |

### Bloque 3 — Prerequisito de infra ⚠️

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 11 | Cloud Run con default compute SA (Editor) | `.github/workflows/deploy-backend.yml:61-67` | `### Fix #26` |

> ⚠️ **El setup de GCP lo hace un humano.** La spec trae los 6 comandos
> `gcloud`. Tú aplicas el YAML; **no corras `gcloud` tú mismo** — pide que los
> corra el dueño y espera confirmación de que la SA existe.
> El paso 12 depende de esto.

### Bloque 4 — Cerrar el borde interno ⚠️ (lo más importante de la Fase 2)

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 12 | Cloud Tasks sin OIDC + `worker-task` sin ninguna verificación | `backend/app/services/task_dispatcher.py:30-36`, `backend/app/routers/pdf.py:107,725`, `backend/app/routers/batch.py:210` | `### Fix #2` **y su sección "AMPLIACIÓN Fase 1"** |

> ⚠️ **Lee la AMPLIACIÓN, no sólo la spec original.** Dos cosas que la spec
> original no trae: (a) le falta el tercer endpoint, `batch.py:210`, que es el
> peor de los tres; (b) el comentario de `_verify_cloud_tasks` contradice al
> código y, tal como está, desplegar `pdf.py` antes que `task_dispatcher.py`
> **rompe la generación de PDF**. El orden de despliegue está escrito ahí.
> Este es el único paso de la Fase 2 que probablemente convenga que ejecute un
> modelo capaz, no uno barato.

### Bloque 5 — HIGH mecánicos (≈7h)

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 13 | SSRF via path traversal del UUID hacia Diverza | `backend/app/routers/sat_enquiry.py:150,340` | `### Fix #38` |
| 14 | SSRF via WeasyPrint en `shell-preview` | `backend/app/services/shell_service.py:255-257` | `### Fix #35` |
| 15 | `ET.fromstring` sin `defusedxml` | `backend/app/routers/batch.py:83`, `backend/app/services/batch_reports.py:31`, `backend/wrappers/python-satcfdi-wrapper.py:406` | `### Fix #8` |
| 16 | Detalles de excepción en respuestas (14 sitios) | `backend/app/routers/sat_enquiry.py:193-198,303`, `backend/app/main.py:75`, `templates.py`, `pdf.py`, `batch.py:334`, `rfc_validation.py` + frontend `InspectorHeader.tsx:210`, `batch-api-client.ts:56`, `useCfdiAnalysis.ts:78`, `useRfcValidation.ts:53`, `useSatEnquiry.ts:30` | `### Fix #4` |
| 17 | Fuga entre sesiones via `_job_results` | `backend/app/routers/sat_enquiry.py:24,359-374` | `### Fix #3` |

> El paso 16 toca 14 sitios y hay que decidir **qué mensaje ve el usuario** en
> cada uno. Si la spec no lo dice para algún sitio, usa un mensaje genérico en
> español y registra el detalle en Sentry. No inventes mensajes distintos por
> sitio. El paso 16 cierra también los 14 hallazgos de batch que colapsan en #4
> (ver la tabla de dedup en `plan-fixes.md`).

### Bloque 6 — HIGH de infra sin código

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 18 | Vercel sin headers de seguridad | `frontend/vercel.json` | `### Fix #24` |

### Bloque 7 — CI/CD y supply chain (≈7h)

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 19 | Cero escaneo de seguridad en CI | `.github/workflows/` | `### Fix #7` (workflows copy-paste listos en `09-ci-cd-hardening.md`) |
| 20 | Sin pre-commit hooks | raíz del repo | marcador inline `**#29:` en PR 3 |
| 21 | Baseline de detect-secrets stale | `.secrets.baseline` | marcador inline `**#32:` en PR 3 |
| 22 | `VERCEL_TOKEN` como flag CLI | `.github/workflows/deploy-frontend.yml:22` | marcador inline `**#28:` en PR 3 |
| 23 | `console.log` de variables Vite | `frontend/src/main.tsx:18` | marcador inline `**#20:` en PR 3 |
| 24 | Pusher key hardcodeada | `frontend/src/lib/pdf-download.ts:308` | marcador inline `**#27/#34:` en PR 3 |
| 25 | Hash pinning en `requirements.txt` | `backend/requirements.txt` | `### Fix #16/#34` |
| 26 | `pip install` sin `--require-hashes` ⚠️ | `backend/Dockerfile:20` | `### Fix #49` |
| 27 | apt sin versión | `backend/Dockerfile:5-16` | `### Fix #53` |

> ⚠️ El paso 26 **depende del 25**: no puedes exigir hashes antes de generarlos.
>
> **Corrección al paso 20 (`#29`), verificada el 2026-07-26.** El hallazgo dice
> "sin pre-commit hooks" y eso es media verdad: no hay `.pre-commit-config.yaml`,
> pero **sí existe `.git/hooks/pre-commit`**, escrito a mano, con tres etapas
> (react-doctor → `.claude/hooks/governance.sh` → `detect-secrets-hook --baseline`).
> Funciona: bloqueó un commit real ese día. El defecto no es "no hay hooks" sino
> que **viven sólo en `.git/` y no se versionan**: no existen en otro clone, en un
> worktree nuevo ni en CI. El fix es migrarlos a `.pre-commit-config.yaml` sin
> perder las tres etapas, no crearlos desde cero.
>
> **Corrección al paso 21 (`#32`), verificada el 2026-07-26 — es peor de lo
> escrito.** El baseline no sólo está viejo (generado 2026-07-06, 3 hits en 2
> archivos que ya ni existen). Tiene un **falso negativo sobre un secreto de
> servidor real**: el valor de `PUSHER_SECRET` estaba copiado literal desde
> `backend/.env` en `docs/seguridad/batch-7/findings.json:453` y `detect-secrets`
> **no lo detectó** — pasó el hook sin una sola alerta. Se redactó a mano antes
> de versionar el archivo (nunca llegó a git; no hubo exposición). El fix tiene
> que incluir **por qué** no lo vio: revisar que `KeywordDetector` y los plugins
> de alta entropía corran sobre `.json`, no sólo sobre código y `.env`. Un
> baseline al día con ese hueco abierto sigue dejando pasar secretos.
>
> **Sobre el paso 24 — hay un dato que la spec original no tenía.** En Vercel
> Production, `VITE_PUSHER_KEY` y `VITE_PUSHER_CLUSTER` están definidas con valor
> **cadena vacía**, así que el `||` del código las trata como falsy y **la key
> hardcodeada es la que corre en producción**. Verifícalo con
> `vercel env pull /tmp/p.env --environment=production`. El fix no es sólo tocar
> el código: hay que poner valor real a las variables en Vercel — eso lo hace el
> dueño, tú pídelo.
>
> El paso 27 se vuelve irrelevante si se aplica `### Fix #48` (multi-stage), que
> está en el bloque 8. Si vas a hacer los dos, haz #48 primero y luego evalúa si
> #53 todavía aplica.

### Bloque 8 — MEDIUM/LOW mecánicos (≈8h)

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 28 | Inyección de fórmulas (Excel backend + CSV frontend + clipboard) | `backend/app/routers/sat_enquiry.py:259-273`, `frontend/src/app/hooks/useCfdiExports.ts:15`, `frontend/src/components/ResolutionPanel.tsx:18` | `### Fix #10` |
| 29 | Respuesta de Diverza → fórmulas | `backend/app/routers/sat_enquiry.py:259-272` | `### Fix #46` |
| 30 | Sin validación MIME en uploads | `backend/app/services/zip_manifest.py:21-24`, `backend/app/routers/pdf.py:240-243`, `backend/app/routers/batch.py:102-110` | `### Fix #43` |
| 31 | Sin límite de tamaño en `batch_analyze` → OOM | `backend/app/routers/batch.py:78,102-110` | `### Fix #44` |
| 32 | Build de una sola etapa | `backend/Dockerfile:1-27` | `### Fix #48` |
| 33 | `logoUrl` sin escape | `frontend/src/components/InvoiceDesigner.jsx:519,663` | `### Fix #51` |
| 34 | Blob URLs con `window.open()` | `frontend/src/components/InvoiceDesigner.jsx:677-679,690-691` | `### Fix #52` |
| 35 | `cloudbuild.yaml` sin `--service-account` ⚠️ | `backend/cloudbuild.yaml:22` | `### Fix #55` |
| 36 | Divergencia merge vs overwrite | `backend/cloudbuild.yaml:41` | `### Fix #56` |
| 37 | Filename sin sanitizar hacia GCS | `backend/app/routers/batch.py:100,128,137` | `### Fix #57` |
| 38 | Doc-code mismatch `is_valid_xml_entry` | `backend/app/services/zip_manifest.py:21-24` | `### Fix #58` |
| 39 | `credential_id` en API pública | `backend/app/routers/emisores.py` | `### Fix #59` |
| 40 | `console.log` de la URL de la API | `frontend/src/components/BatchAnalysisPage.tsx:161`, `frontend/src/lib/pdf-download.ts:8` | `### Fix #60` |
| 41 | URL de Cloud Run hardcodeada | `frontend/src/components/BatchAnalysisPage.tsx:160` | `### Fix #61` |
| 42 | `template_id` sin validar (hardening) | `backend/app/routers/templates.py:304,317,335,341,357,421` | `### Fix #62` |
| 43 | Validar forma de `batch_id`/`job_id` | `frontend/src/App.tsx:106,259,283`, `BatchAnalysisPage.tsx:770`, `pdf-download.ts:412` | `### Fix NUEVO-BATCHID` |

> ⚠️ El paso 35 depende del bloque 3 (la SA tiene que existir).
> El paso 36 puede terminar en "borrar `cloudbuild.yaml`" — **pregunta antes de
> borrarlo**, no lo borres por tu cuenta.
> El paso 41 **no reduce el riesgo**: la URL de Cloud Run es pública de todos
> modos (está en `vercel.json:5`, en `deploy-backend.yml:49` y horneada en el
> bundle desde una variable de Vercel). Se aplica como higiene. La spec lo dice.

### Bloque 9 — MEDIUM restantes (≈10h)

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 44 | Llave Fernet en cold start | `backend/app/credentials.py:16-17`, `backend/app/fiel_config.py` | `### Fix #5` |
| 45 | Race en TTL de batch | `backend/app/routers/batch.py:116-123` | `### Fix #15` |
| 46 | ~~SRI en scripts de terceros~~ ⛔ **OBSOLETA — sáltala** | — | `### Fix #17`, marcada obsoleta |
| 47 | `PUSHER_KEY`/`VERCEL_URL` a GitHub Variables | `.github/workflows/` | `### Fix #22` |
| 48 | Secretos con `--set-secrets` | `.github/workflows/deploy-backend.yml:61-67` | `### Fix #30` |
| 49 | Batch shard job sin SA dedicada | `infra/deploy-batch-shard-job.sh` | `### Fix #31` |
| 50 | `npm audit` roto | `frontend/` | `### Fix #33` |
| 51 | `access_token` de signed URL en logs | `backend/app/routers/pdf.py:668` | `### Fix #13` |
| 52 | `pickle.loads` en catálogos | `backend/app/services/catalogs.py:31,54` | `### Fix #14` |
| 53 | `_job_results` evicta con 5 entradas | `backend/app/routers/sat_enquiry.py:359` | `### Fix #18` (se resuelve dentro del paso 17) |
| 54 | iframe `srcDoc` con `allow-same-origin` | `frontend/src/components/InvoiceDesigner.jsx:1139` | `### Fix #40` |
| 55 | Sin sanitización HTML en plantillas ⚠️ | `templates.py:341-349`, `shell_service.py:175-178` | `### Fix #41` |
| 56 | Auditoría de SSTI | `backend/app/services/canvas_service.py` | `### Fix #11` |

> ⚠️ El paso 55 va **después** del 54: #40 define cuál es la defensa que hoy
> sostiene todo el pipeline, y hay que entenderla antes de cambiarla.
> El paso 56 es una **auditoría**, no un fix: su entregable es un hallazgo
> nuevo o la confirmación de que no hay SSTI. Si encuentras algo, no lo
> arregles sin escribir la spec primero.
>
> **El paso 46 está marcado obsoleto y no se aplica.** La spec asume un
> `<script src="https://js.pusher.com/…">` que no existe: `frontend/index.html`
> sólo carga el entrypoint de Vite, y `pusher-js` viene de npm. Compruébalo con
> `grep -n "<script" frontend/index.html` y sigue adelante. Son **55 pasos
> reales**, no 56.

---

## Qué cierra cada paso

Un fix no cierra un hallazgo: cierra un hallazgo **y todos los que colapsan en
él**. Esta es la cuenta real de lo que compras con cada bloque.

| Bloque | Pasos | Cierra directo | Cierra por subsunción (hallazgos de batch y duplicados) | Total |
|---|---|---|---|---|
| 1 — Quick wins | 1–9 | #9, #39, #19, #25, #23, #42, #47, #50, #54 | #21 (stale), `BATCH6-CANDIDATE-31` | ~11 |
| 2 — XXE | 10 | #1 | — | 1 |
| 3 — SA de Cloud Run | 11 | #26 | — | 1 |
| 4 — **Borde interno** | 12 | #2 | `BATCH6-CANDIDATE-02` (CRITICAL), `BATCH6-CANDIDATE-04` (HIGH) | **3** |
| 5 — HIGH mecánicos | 13–17 | #38, #35, #8, #4, #3 | `B7-BE-INJ-01`, `BATCH6-CANDIDATE-25`; y en #4: `B7-BE-AUTH-02..05`, `B7-CFDI-AUTH-03`, `B7-CFDI-AUTH-06`, `B7-HOOKS-AUTH-01..03`, `B7-HOOKS-AUTH-05`, `B8-BATCH-AUTH-01`, `B8-FINDINGS-AUTH-01`, `B8-FINDINGS-AUTH-02`, #18 | **~21** |
| 6 — Headers | 18 | #24 | — | 1 |
| 7 — CI/CD | 19–27 | #7, #29, #32, #28, #16/#34, #49, #53, #20, #27 | `B7-CI-AUTH-01..06`, `B7-CI-INJ-03`, `B7-CI-AUTH-04`, `B7-CI-CRYPTO-04,05,06,08,09,10`, `B7-CI-INJ-02`, `B8-SHELL-AUTH-01`, `B8-SHELL-CRYPTO-01`, `B8-BATCH-CRYPTO-01`, #60 | **~26** |
| 8 — MEDIUM/LOW | 28–43 | #10, #46, #43, #44, #48, #51, #52, #55, #56, #57, #58, #59, #60, #61, #62 | `B7-HOOKS-INJ-01`, `B8-EXTW-INJ-01`, `B8-FINDINGS-INJ-01`, `B8-FINDINGS-INJ-03`, `B7-UI-AUTH-01`, `BATCH6-CANDIDATE-06,09,15,20,28,29,32`, `B8-SHELL-INJ-01/02/03`, `B8-BATCH-INJ-01`, `TEMPLATE-PATH-TRAVERSAL-01` | **~33** |
| 9 — MEDIUM restantes | 44–56 | #5, #15, #22, #30, #31, #33, #13, #14, #40, #41, #11 | `BATCH6-CANDIDATE-11,21,22,23,24` | **~16** |
| — | | | **#17 obsoleta, no cuenta** | |

**Los CRITICAL/HIGH con panel unánime que cierra la Fase 2** son: #1, #2,
`BATCH6-CANDIDATE-02`, `BATCH6-CANDIDATE-04`, #38, #39, #35, #8, #4, #3, #24,
#25, #26, #7.

**Los CRITICAL/HIGH con panel que la Fase 2 NO cierra** — y por eso existe la
Fase 3 — son: `BATCH6-CANDIDATE-01` (CRITICAL), `BATCH6-CANDIDATE-03` (CRITICAL),
`BATCH6-CANDIDATE-05` (HIGH), `B8-SHELL-AUTH-02` (HIGH), `B8-XML-AUTH-02` (HIGH),
#45 (HIGH), #36 y #37 (HIGH tras recalibración), #6 (HIGH).

---

## Cómo verificar

**Cada spec trae su propio comando de verificación al final, en un bloque
`**Verificación post-fix:**`.** Córrelo después de aplicar el fix. Es la
verificación que cuenta.

Además, después de cada bloque:

```bash
python3 -m pytest backend/tests/ -q
python3 -m ruff check backend/app/
cd frontend && npm run lint && npm test && cd ..
```

Y al terminar toda la Fase 2:

```bash
# 1. Regenerar el registro y confirmar que el script sigue corriendo
python3 scripts/reconcile_registry.py --output docs/seguridad/registro-unificado.md

# 2. Los tres hechos que definen si el borde interno quedó cerrado
# OJO: sin el guion bajo. La función quedó como `verify_cloud_tasks` (pública),
# porque vive en services/internal_auth.py y la importan dos routers -- un
# nombre con guion bajo inicial señala "privado del módulo" y no se importa
# entre módulos. Con el nombre viejo estos greps dan CERO y parecen regresión.
grep -c '"oidc_token": _oidc_token()' backend/app/services/task_dispatcher.py  # → 3
grep -rn "verify_cloud_tasks" backend/app/routers/               # → pdf.py ×3 + batch.py ×2 (import + usos)
grep -n "_ALLOWED_GCS_PREFIX" backend/app/routers/batch.py       # → definición + uso
grep -rn "ssl_cert_reqs" --include="*.py" .                      # → 3 líneas, todas "required"

# 3. Y el que define lo que NO se cerró (debe seguir dando 0 — es esperado)
grep -rc "Depends(" backend/app/
```

**No uses `grep -c "OPEN" docs/seguridad/08-auditoria-actual.md` → 0 como
criterio de aceptación.** Es un criterio viejo de cuando había 34 hallazgos;
hoy hay 160 y varios quedan fuera de alcance a propósito.

---

## Qué NO se toca en la Fase 2

| Qué | Por qué |
|---|---|
| **#36 y #37 — FIEL (e.firma) usada, sobrescrita y borrada sin auth** | Panel 3/3 unánime, **recalibrados de MEDIUM a HIGH en la Fase 1**. Cualquiera en internet puede hoy hacer que el servicio firme en el portal del SAT con la e.firma guardada, reemplazarla por otra, o borrarla. **No hay fix mecánico:** un guard ad-hoc en dos routers deja los otros ~28 endpoints abiertos e inventa un sistema de identidad paralelo. Requiere B-lite. Si la exposición es inaceptable antes de eso, la mitigación disponible hoy es borrar la FIEL configurada — pero **eso lo decide el dueño**, no tú. |
| **#45 (batch status sin auth), #12 (canales Pusher públicos)** y los 13 hijos de PADRE-AUTH | Todos requieren identidad. Ver `## PR 7` en `plan-fixes.md`. |
| **#6 — rate limiting** | Es HIGH pero se pospuso: `slowapi` sin identidad limita por IP, y hoy la mitad del tráfico llega por el CDN de Vercel (IP compartida) y la otra mitad directo a Cloud Run (IP real). El límite saldría desigual entre los dos caminos. |
| **`BATCH6-CANDIDATE-12`** (una sola llave Fernet protege FIEL y credenciales de PAC) | Espera panel adversarial. No es una race, es una decisión de diseño criptográfico; lo vota el panel, no un modelo. |
| **Datos sensibles visibles en React DevTools** (`B7-HOOKS-AUTH-04`, `B8-SHELL-AUTH-04`, `BATCH6-CANDIDATE-16/17`) | Esperan panel: depende de si "atacante con acceso al navegador de la víctima" cuenta como amenaza en este producto. |
| **Inyección en headers de respuesta** (`BATCH6-CANDIDATE-09/10`) | Espera panel. `-10` (`rfc_presentante` sin sanitizar en `Content-Disposition`, `batch.py:339`) podría ser CRLF injection real y ningún panel lo ha visto. |
| **`NaN`/`Infinity` desde XML** (6 hallazgos) | Cerrados sin panel: el atacante y la víctima son la misma persona (el usuario sube su propio XML). Deuda de calidad de UI, no de seguridad. |
| **Opciones de subprocess del engine** (`B7-CFDI-AUTH-01/02/03`) | Cerrados sin panel: `pythonSatcfdiEngine` sólo lo importa `runBenchmark.ts` (script de Node) y no entra al bundle desplegado. Sin superficie en producción. |
| **Renderizar el XML del CFDI en el DOM** (`B8-XML-AUTH-01/03`) | No es un defecto: es la función de un inspector de CFDI. |
| **Los 7 rechazados por panel** | Ya tienen su sección con motivo en `registro-unificado.md`. |

**Los hallazgos con id de batch (`B7-…`, `B8-…`, `BATCH6-CANDIDATE-…`) van a
seguir apareciendo con `—` en la columna `spec` del registro aunque los arregles.**
`reconcile_registry.py` detecta specs sólo por número (`#N`), y esos hallazgos no
tienen número de auditoría. No es un error tuyo ni una regresión. El mapa de qué
hallazgo de batch cae en qué fix está en la tabla de dedup de `plan-fixes.md`.

---

## Dónde se corta la Fase 2

**El corte es al terminar el bloque 9. No sigas.**

Lo siguiente en la lista es **B-lite: identidad real en el backend** — un
`Depends()` global de identidad verificada, más aislamiento por tenant del
material de FIEL y de los emisores. Eso cierra 14 hallazgos que hoy están
abiertos, incluyendo dos CRITICAL con panel unánime y la e.firma.

**Es una decisión de arquitectura y de producto, no una spec.** Hay que elegir
mecanismo (Google OAuth en la app, IAP delante de Cloud Run, otra cosa) y esa
elección depende de cosas que no están resueltas:

- **El plan de Vercel.** Un token OIDC local dice `"plan":"hobby"`, y la
  Deployment Protection de Vercel es de plan Pro. Si es Hobby, la vía barata
  "protege el deployment y ya" **no existe** y hay que implementar identidad en
  la aplicación o poner IAP. **Confírmalo en la consola de Vercel** — el dato
  viene de un token de entorno de desarrollo, no es concluyente.
- **Los tres llamadores que no son un navegador** y no pueden pasar por un login
  humano: Cloud Tasks (resuelto con OIDC en el paso 12), el Cloud Run Job
  `cfdi-batch-shard`, y el propio backend que se auto-invoca vía `API_URL`
  (`deploy-backend.yml:49`).
- **Cuántos usuarios va a haber.** "Una identidad" y "múltiples tenants
  aislados" son sistemas distintos, y hoy no está definido cuál se necesita.

**Cuando llegues aquí: para, escribe qué quedó aplicado y qué falta, y devuelve
la decisión al dueño.** No elijas mecanismo de autenticación por tu cuenta y no
improvises un guard "temporal" en un router — esa es exactamente la deuda que
este proceso existe para evitar.
