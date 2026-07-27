# Fase 2, segunda mitad — bloques 6 a 9 (pasos 18–56)

> **Lee este archivo y nada más para arrancar.** No necesitas el contexto de la
> sesión anterior ni de la Fase 1. Todo lo que hay que saber está aquí.
> Escrito el 2026-07-26 al cerrar el bloque 5.
>
> El archivo hermano, `prompt-fase2.md`, cubre los bloques 0–5 y **ya está
> ejecutado**. Sigue siendo útil para dos cosas: la decisión de auth (su sección
> "La decisión de auth que ya se tomó, y su límite") y la tabla "Qué NO se toca
> en la Fase 2". Lo demás de ese archivo ya pasó.

---

## Qué eres y qué NO haces

Aplicas fixes que ya tienen spec escrita. Las specs viven en
`docs/seguridad/plan-fixes.md` — cada una trae **antes/después** y un **comando
de verificación**. Tú aplicas el diff y corres el comando.

**No decides arquitectura.** Si una spec te pide una decisión que no está
escrita, párate y pregunta. **No inventes autenticación.**

---

## Lo que ya está hecho (no lo rehagas)

Estás en la rama **`seguridad/fase-2`**, que tiene **19 commits** sobre `main` y
**no está desplegada**. Los bloques 0 a 5 están cerrados:

| Bloque | Pasos | Hallazgos cerrados |
|---|---|---|
| 0 — preparación | — | rama, baselines, `deploy-backend.yml` a Secrets/Variables |
| 1 — Quick wins | 1–9 | #9, #39, #19, #25, #42, #47, #50, #54 (+#21 stale). **#23 NO aplicado a propósito** |
| 2 — XXE | 10 | #1 |
| 3 — Service account | 11 | #26 |
| 4 — **Borde interno** | 12 | #2, `BATCH6-CANDIDATE-02`, `BATCH6-CANDIDATE-04` |
| 5 — HIGH mecánicos | 13–17 | #38, #35, #8, #4 (+los 14 de batch que colapsan en él), #3, #18 |

**Todos los CRITICAL/HIGH con panel unánime que la Fase 2 debía cerrar están
cerrados, menos dos: #24 (bloque 6) y #7 (bloque 7).** Ésos son tu primer y
segundo objetivo.

### El límite, sin adornos

Al terminar el bloque 9 **la API sigue abierta a internet sin autenticación de
usuario** — cero `Depends()` en `backend/app/`. Eso es esperado, no una
regresión. Cerrarlo requiere B-lite y es una decisión que se toma después (ver
"Dónde se corta", al final).

---

## Antes de tocar nada

```bash
cd /Users/gil/Documents/cfdi_suite
git checkout seguridad/fase-2          # la rama YA EXISTE, no la crees
python3 -m pip install ruff defusedxml # ruff no viene instalado en esta máquina
python3 -m pytest backend/tests/ -q
python3 -m ruff check backend/app/
cd frontend && npm run lint && npm test && cd ..
```

### Los cuatro baselines. Apréndetelos: sin ellos no puedes distinguir "lo rompí yo" de "ya estaba roto"

| Gate | Valor esperado | Nota |
|---|---|---|
| `pytest backend/tests/ -q` | **329 passed** | Eran 299 al empezar; los 30 extra son tests nuevos de los bloques 1–5 |
| `ruff check backend/app/` | **42 errors** | Eran 44. Bajó porque el fix de #4 eliminó dos `F821` reales |
| `npm run lint` (`tsc --noEmit`) | **6 errors** | **Ya estaban rojos antes de empezar**, todos en `src/components/ConversionMasivaPage.test.tsx`. No son tuyos y no entran en esta fase |
| `npm test` (`vitest run`) | **119 passed** | |

Los 42 de ruff son preexistentes (I001, E402, N806, UP045, F401). **No los
arregles**: no son de seguridad y tocarlos ensucia los diffs de los fixes.

### Reglas que valen todo el tiempo

1. **Gana el código, no el doc.** Si una spec dice que la línea 52 tiene X y no
   lo tiene, corre el `grep`, cree al código y anota la discrepancia. **Esto no
   es teórico: en los bloques 1–5 la spec estuvo equivocada 5 veces, y una de
   ellas habría roto producción.** Ver "Lo que la spec tuvo mal" más abajo.
   Y ojo: **las specs de los bloques 8 y 9 se derivaron de la descripción de la
   auditoría, no se verificaron línea por línea** — `plan-fixes.md` lo dice al
   inicio de `## PR 6`. Sus fragmentos son indicativos. Abre el archivo antes de
   editar, siempre.
2. **Un commit por fix**, con el número de hallazgo en el mensaje:
   `fix(seguridad): #44 límite de tamaño por archivo en batch_analyze`.
   Cuidado al hacer `git add <archivo>`: si tienes dos fixes tocando el mismo
   archivo, arrastras los dos al mismo commit.
3. **No despliegues a producción sin permiso explícito del dueño.** Ni backend
   ni frontend. Los merges a `main` disparan deploy automático — mantente en la
   rama.
4. **Si un fix rompe un test, párate y dile al dueño.** No lo "arregles"
   relajando el test. Actualizar una *fixture* poco realista (un `"abc-123"` que
   debía ser un UUID) no es relajar; bajar una aserción sí lo es.
5. **Mide antes de afirmar.** Si vas a decir que algo es explotable,
   demuéstralo: levanta un listener, construye el payload, corre el `grep`. Dos
   hallazgos de los bloques 1–5 resultaron menos graves de lo escrito y uno más.
   Un control positivo (probar que tu prueba detecta el ataque cuando *sí* está
   presente) vale más que diez párrafos.

### El hook de pre-commit va a interrumpirte, y eso está bien

`.git/hooks/pre-commit` corre 3 etapas: react-doctor → `governance.sh` →
`detect-secrets-hook`. Dos cosas que van a pasar:

- **`detect-secrets` reescribe `.secrets.baseline`** cuando cambian números de
  línea y aborta el commit pidiéndote `git add .secrets.baseline`. Antes de
  añadirlo, **verifica que sólo cambiaron números de línea** y no aparecieron
  secretos nuevos:
  ```bash
  python3 -c "
  import json,subprocess
  a=json.loads(subprocess.run(['git','show','HEAD:.secrets.baseline'],capture_output=True,text=True).stdout)
  b=json.load(open('.secrets.baseline'))
  f=lambda d:{(k,r['type'],r['hashed_secret']) for k,rs in d.get('results',{}).items() for r in rs}
  print('nuevos:', f(b)-f(a) or 'ninguno', '| desaparecidos:', f(a)-f(b) or 'ninguno')"
  ```
- **`detect-secrets` da falsos positivos** con cadenas de 32 hex (UUID de
  prueba). Se resuelven con `# pragma: allowlist secret` en la línea, que es lo
  que el propio hook sugiere.
- **react-doctor imprime 13 hallazgos** (1 error de accesibilidad sobre
  `prefers-reduced-motion` en `package.json`, 12 warnings de mantenibilidad).
  **Son preexistentes del proyecto y no bloquean el commit.** No entran en esta
  fase; no los arregles de paso.

---

## Los pasos que faltan

### Bloque 6 — headers de seguridad en Vercel (paso 18)

| # | Hallazgo | archivo | Spec |
|---|---|---|---|
| 18 | Vercel sin headers de seguridad | `frontend/vercel.json` | `### Fix #24` |

`#24` es **HIGH con panel unánime** y uno de los dos que le faltan a la Fase 2.
Hazlo primero.

Ojo con `frontend/vercel.json`: hoy sólo tiene `buildCommand`, `outputDirectory`
y un `rewrites` que manda `/api/:path*` a la URL de Cloud Run. **No rompas ese
rewrite**: es el camino por el que el frontend habla con el backend.

### Bloque 7 — CI/CD y supply chain (pasos 19–27)

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 19 | Cero escaneo de seguridad en CI | `.github/workflows/` | `### Fix #7` (workflows copy-paste listos en `09-ci-cd-hardening.md`) |
| 20 | Sin pre-commit hooks versionados | raíz del repo | marcador inline `**#29:` en PR 3 |
| 21 | Baseline de detect-secrets | `.secrets.baseline` | marcador inline `**#32:` en PR 3 |
| 22 | `VERCEL_TOKEN` como flag CLI | `.github/workflows/deploy-frontend.yml:22` | marcador inline `**#28:` en PR 3 |
| 23 | `console.log` de variables Vite | `frontend/src/main.tsx:18` | marcador inline `**#20:` en PR 3 |
| 24 | Pusher key hardcodeada | `frontend/src/lib/pdf-download.ts:308` | marcador inline `**#27/#34:` en PR 3 |
| 25 | Hash pinning en `requirements.txt` | `backend/requirements.txt` | `### Fix #16/#34` |
| 26 | `pip install` sin `--require-hashes` ⚠️ | `backend/Dockerfile` | `### Fix #49` |
| 27 | apt sin versión | `backend/Dockerfile` | `### Fix #53` |

`#7` es el otro HIGH con panel que falta.

> ⚠️ **El paso 26 depende del 25**: no puedes exigir hashes antes de generarlos.
>
> **Paso 20 (`#29`) — es migrar, no crear.** El hallazgo dice "sin pre-commit
> hooks" y es media verdad: no hay `.pre-commit-config.yaml`, pero **sí existe
> `.git/hooks/pre-commit`**, escrito a mano, con las tres etapas de arriba.
> Funciona — te va a interrumpir durante esta sesión. El defecto es que **vive
> sólo en `.git/` y no se versiona**: no existe en otro clone, en un worktree
> nuevo ni en CI. El fix es migrarlo a `.pre-commit-config.yaml` **sin perder
> las tres etapas**.
>
> **Paso 21 (`#32`) — el hallazgo está desactualizado, y el hueco real es otro.**
> Dice que el baseline es de 2026-07-06 con 3 hits en 2 archivos inexistentes.
> **Ya no:** hoy cubre 13 archivos (incluidos los `findings.json` de los batches),
> 18 hallazgos, 27 plugins, regenerado el 2026-07-27. Reevalúalo contra ese
> estado, no contra el descrito.
> Lo que **sí** sigue abierto es el hueco de detección, y hay dos datos duros:
> - **Falso negativo sobre un secreto de servidor real:** el valor de
>   `PUSHER_SECRET` estaba literal en `docs/seguridad/batch-7/findings.json:453`
>   y `detect-secrets` **no lo detectó**. Se redactó a mano antes de versionar
>   (nunca llegó a git; no hubo exposición).
> - **Falso positivo sobre un UUID inventado** en un test (32 hex seguidos), que
>   sí bloqueó un commit el 2026-07-26.
>
> O sea: dispara con un UUID de prueba y no con un secreto real dentro de un
> `.json`. El fix tiene que incluir **por qué**: revisar que `KeywordDetector` y
> los plugins de alta entropía corran sobre `.json`, no sólo sobre código y
> `.env`. Un baseline al día con ese hueco abierto sigue dejando pasar secretos.
>
> **Paso 24 (`#27/#34`) — dato que la spec no tenía.** En Vercel Production,
> `VITE_PUSHER_KEY` y `VITE_PUSHER_CLUSTER` están definidas con **cadena vacía**,
> así que el `||` del código las trata como falsy y **la key hardcodeada es la
> que corre en producción**. Verifícalo con
> `vercel env pull /tmp/p.env --environment=production`. El fix no es sólo tocar
> el código: **hay que ponerle valor real a esas dos variables en Vercel, y eso
> lo hace el dueño — pídeselo.**
>
> El paso 27 (`#53`) se vuelve irrelevante si se aplica `### Fix #48`
> (multi-stage), que está en el bloque 8. Si vas a hacer los dos, **haz #48
> primero** y luego evalúa si #53 todavía aplica.
>
> **Contexto del paso 25 (`#16/#34`):** `backend/requirements.txt` ya recibió dos
> dependencias nuevas en el bloque 5, `google-auth>=2.0,<3` y
> `defusedxml>=0.7,<0.8`. Los hashes tienen que incluirlas.

### Bloque 8 — MEDIUM/LOW mecánicos (pasos 28–43)

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 28 | Inyección de fórmulas (Excel backend + CSV frontend + clipboard) | `backend/app/routers/sat_enquiry.py`, `frontend/src/app/hooks/useCfdiExports.ts:15`, `frontend/src/components/ResolutionPanel.tsx:18` | `### Fix #10` |
| 29 | Respuesta de Diverza → fórmulas | `backend/app/routers/sat_enquiry.py` | `### Fix #46` |
| 30 | Sin validación MIME en uploads | `backend/app/services/zip_manifest.py:21-24`, `backend/app/routers/pdf.py`, `backend/app/routers/batch.py` | `### Fix #43` |
| 31 | Sin límite de tamaño en `batch_analyze` → OOM | `backend/app/routers/batch.py` | `### Fix #44` |
| 32 | Build de una sola etapa | `backend/Dockerfile` | `### Fix #48` |
| 33 | `logoUrl` sin escape | `frontend/src/components/InvoiceDesigner.jsx:519,663` | `### Fix #51` |
| 34 | Blob URLs con `window.open()` | `frontend/src/components/InvoiceDesigner.jsx:677-679,690-691` | `### Fix #52` |
| 35 | `cloudbuild.yaml` sin `--service-account` ⚠️ | `backend/cloudbuild.yaml:22` | `### Fix #55` |
| 36 | Divergencia merge vs overwrite | `backend/cloudbuild.yaml:41` | `### Fix #56` |
| 37 | Filename sin sanitizar hacia GCS | `backend/app/routers/batch.py` | `### Fix #57` |
| 38 | Doc-code mismatch `is_valid_xml_entry` | `backend/app/services/zip_manifest.py:21-24` | `### Fix #58` |
| 39 | `credential_id` en API pública | `backend/app/routers/emisores.py` | `### Fix #59` |
| 40 | `console.log` de la URL de la API | `frontend/src/components/BatchAnalysisPage.tsx:161`, `frontend/src/lib/pdf-download.ts:8` | `### Fix #60` |
| 41 | URL de Cloud Run hardcodeada | `frontend/src/components/BatchAnalysisPage.tsx:160` | `### Fix #61` |
| 42 | `template_id` sin validar (hardening) | `backend/app/routers/templates.py` | `### Fix #62` |
| 43 | Validar forma de `batch_id`/`job_id` | `frontend/src/App.tsx`, `BatchAnalysisPage.tsx`, `pdf-download.ts` | `### Fix NUEVO-BATCHID` |

> ⚠️ **El paso 35 ya NO está bloqueado:** la SA `cfdi-suite-api-sa` existe y
> tiene sus permisos (bloque 3, hecho y verificado el 2026-07-26).
>
> El paso 36 puede terminar en "borrar `cloudbuild.yaml`" — **pregunta antes de
> borrarlo**, no lo borres por tu cuenta.
>
> El paso 41 **no reduce el riesgo**: la URL de Cloud Run es pública de todos
> modos (está en `frontend/vercel.json`, en `deploy-backend.yml` y horneada en
> el bundle desde una variable de Vercel). Se aplica como higiene. La spec lo dice.
>
> **Los números de línea de este bloque están desactualizados** para
> `sat_enquiry.py`, `batch.py` y `pdf.py`: los bloques 1–5 les añadieron entre 20
> y 60 líneas. Usa `grep`, no los números.

### Bloque 9 — MEDIUM restantes (pasos 44–56)

| # | Hallazgo | archivo:línea | Spec |
|---|---|---|---|
| 44 | Llave Fernet en cold start | `backend/app/credentials.py`, `backend/app/fiel_config.py` | `### Fix #5` |
| 45 | Race en TTL de batch | `backend/app/routers/batch.py` | `### Fix #15` |
| 46 | ~~SRI en scripts de terceros~~ ⛔ **OBSOLETA — sáltala** | — | `### Fix #17` |
| 47 | `PUSHER_KEY`/`VERCEL_URL` a GitHub Variables | `.github/workflows/` | `### Fix #22` |
| 48 | Secretos con `--set-secrets` | `.github/workflows/deploy-backend.yml` | `### Fix #30` |
| 49 | Batch shard job sin SA dedicada | `infra/deploy-batch-shard-job.sh` | `### Fix #31` |
| 50 | `npm audit` roto | `frontend/` | `### Fix #33` |
| 51 | `access_token` de signed URL en logs | `backend/app/routers/pdf.py` | `### Fix #13` |
| 52 | `pickle.loads` en catálogos | `backend/app/services/catalogs.py:31,54` | `### Fix #14` |
| 53 | ~~`_job_results` evicta con 5 entradas~~ ✅ **YA CERRADO** dentro del paso 17 | — | `### Fix #18` |
| 54 | iframe `srcDoc` con `allow-same-origin` | `frontend/src/components/InvoiceDesigner.jsx:1139` | `### Fix #40` |
| 55 | Sin sanitización HTML en plantillas ⚠️ | `backend/app/routers/templates.py`, `backend/app/services/shell_service.py` | `### Fix #41` |
| 56 | Auditoría de SSTI | `backend/app/services/canvas_service.py` | `### Fix #11` |

> ⚠️ El paso 55 va **después** del 54: `#40` define cuál es la defensa que hoy
> sostiene todo el pipeline, y hay que entenderla antes de cambiarla.
>
> El paso 56 es una **auditoría**, no un fix: su entregable es un hallazgo nuevo
> o la confirmación de que no hay SSTI. Si encuentras algo, **no lo arregles sin
> escribir la spec primero**.
>
> **El paso 46 está obsoleto y no se aplica.** La spec asume un
> `<script src="https://js.pusher.com/…">` que no existe: `frontend/index.html`
> sólo carga el entrypoint de Vite y `pusher-js` viene de npm. Compruébalo con
> `grep -n "<script" frontend/index.html` y sigue.
>
> **El paso 53 ya está cerrado** — se resolvió dentro del paso 17 (`#3`), que
> eliminó el dict en memoria. Verifícalo con
> `grep -n "_job_results" backend/app/routers/sat_enquiry.py` (sólo debe salir en
> un comentario histórico) y márcalo, no lo rehagas.
>
> **Contexto del paso 48 (`#30`):** `deploy-backend.yml` ya pasa `REDIS_PASSWORD`
> por `${{ secrets.REDIS_PASSWORD }}` hacia `env_vars`. Eso **no** cierra `#30`,
> que lo quiere vía `--set-secrets` desde GCP Secret Manager. Hay que crear los
> secretos en Secret Manager primero.
>
> **Contexto del paso 44 (`#5`):** el `Dockerfile` ya fija `ENV HOME=/home/app`
> (se añadió en el paso 8 porque `USER app` sin `HOME` explícito rompía el
> arranque: `credentials.py:9` guarda la llave Fernet en `Path.home()`). Ese
> comentario del Dockerfile explica el problema que `#5` viene a resolver de
> raíz: la llave se **genera en cold start** y vive en un filesystem efímero.
>
> **Contexto del paso 51 (`#13`):** `pdf.py` cambió bastante en los bloques 4 y 5.
> Busca el `print` del `access_token` con `grep`, no por número de línea.

---

## Lo que la spec tuvo mal en los bloques 1–5

Esto no es anécdota: es la evidencia de por qué la regla 1 existe. **Cinco
errores, uno de ellos habría roto producción.**

| Spec | Qué decía | Qué era en realidad |
|---|---|---|
| `#2` AMPLIACIÓN | prefijo `xml_temp_analysis/` | **No existe.** La ruta real es `xml_temp/analysis_{batch_id}/{fname}`. Aplicarlo al pie de la letra habría rechazado **todas** las tareas legítimas y roto el análisis masivo en producción |
| `#26` comando 6 | `roles/iam.serviceAccountTokenCreator` a nivel de proyecto | **Escalada de privilegios**: dejaba a la SA pedir un token de la compute SA, que tiene `roles/editor`. Le quitaba el Editor por la puerta y se lo devolvía por la ventana. Corregido: acotado a la SA sobre sí misma |
| `#26` lista de comandos | 6 comandos | **Faltaba un 7º** (`roles/iam.serviceAccountUser` sobre sí misma) sin el cual `create_task` falla con `PermissionDenied` y el paso 12a revienta en su primer deploy |
| `#25` | `http://localhost:5173` | Este proyecto corre dev en **3000** (`vite --port=3000`); `5173` no aparece en el repo |
| Verificación del paso 12 | `grep -rn "_verify_cloud_tasks"` | La función quedó como `verify_cloud_tasks`, **sin guion bajo** (es pública, la importan dos routers). El grep viejo daba **cero** y se leía como regresión. Ya corregido en los dos documentos |

Y dos **matices de severidad** que sólo aparecieron al medir en vez de asumir:

- **`#1` (XXE, CRITICAL):** `iterparse(recover=True)` sí expande entidades
  externas hacia el **texto** de los elementos (probado con un control
  positivo), pero **no** hacia valores de atributo — y los 3 call sites de
  `canvas_service.py` leen **únicamente atributos**. El defecto del parser era
  real; la ruta a `/proc/self/environ` no era alcanzable por ahí. Se aplicó
  igual, como defensa en profundidad.
- **`#8` (defusedxml):** `xml.etree` **no** fuga archivos (un `file://` da
  `ParseError`), pero **sí** expande entidades internas: ~400 bytes con 9 niveles
  → ~1 GB en memoria. El riesgo real era OOM, no exfiltración.

Y **dos bugs reales encontrados de rebote**, que no eran hallazgos de seguridad:

- **`ENV HOME`**: `USER app` sin `HOME` explícito rompía los flujos de emisores y
  FIEL, porque la llave Fernet vive en `Path.home()`.
- **Dos `F821` en `pdf.py`**: `str(e)` dentro de un `lambda`, fuera del alcance
  donde Python borra el nombre al salir del `except`. Por eso ruff bajó de 44 a 42.

---

## Estado de la infraestructura (verificado en vivo, no supuesto)

| Recurso | Estado |
|---|---|
| SA `cfdi-suite-api-sa` | **Existe.** Proyecto: `cloudtasks.enqueuer`, `cloudtrace.agent`, `run.invoker`. Sobre sí misma: `serviceAccountTokenCreator`, `serviceAccountUser`. Bucket: `storage.objectAdmin` |
| Servicio Cloud Run | Sigue corriendo con `706861124428-compute@developer.gserviceaccount.com` (Editor). **El cambio a la SA nueva está comiteado pero NO desplegado** |
| CORS del bucket | **Cerrado**: `['https://cfdiinspector.vercel.app', 'http://localhost:3000', 'http://127.0.0.1:3000']` |
| GitHub Secrets | `GCP_SA_KEY`, `PUSHER_APP_ID/KEY/SECRET`, `REDIS_PASSWORD`, `SENTRY_DSN`, `VERCEL_ORG_ID/PROJECT_ID/TOKEN/URL` |
| GitHub Variables | `GCS_BUCKET_NAME`, `PUSHER_CLUSTER`, `REDIS_HOST` |
| `cors-gcs.json` | Está en `.gitignore` **a propósito** (comentario explícito). Corregido en local, no versionado. Respeta esa decisión |
| Docker daemon | **Apagado en esta máquina.** Las verificaciones de #42, #47, #50 y #54 que necesitan `docker build`/`docker run` quedaron **pendientes** |

---

## Deuda de despliegue — LÉELA ANTES DE QUE ALGUIEN DESPLIEGUE

**Nada de la rama está desplegado.** Cuando el dueño lo autorice, el paso 12
(`#2`) exige un orden que **no es opcional**:

1. Desplegar **sólo el commit `1bfb1b6`** (12a: Cloud Tasks emite el token).
2. Confirmar en los logs que las tareas llegan con `Authorization: Bearer`.
3. **Drenar la cola de Cloud Tasks.** Una tarea encolada antes de 12a no lleva
   token y 12b la rechazaría.
4. Sólo entonces desplegar `5d8067a` (12b: los endpoints lo exigen).

**Al revés se cae la generación de PDF y el análisis por lotes en producción.**
La razón es que `task_dispatcher.py` y los routers viven en la **misma imagen**
de Cloud Run: "primero uno y luego el otro" son dos **deploys**, no dos archivos.

También pendiente de deploy: el `--service-account` de `#26` (`82b7c28`).

---

## Cómo verificar

**Cada spec trae su propio comando al final, en un bloque
`**Verificación post-fix:**`.** Córrelo después de aplicar el fix. Es el que
cuenta.

Además, después de cada bloque:

```bash
python3 -m pytest backend/tests/ -q          # >= 329 passed
python3 -m ruff check backend/app/           # 42, no más
cd frontend && npm run lint && npm test && cd ..   # 6 errores TS preexistentes, 119 tests
```

Y al terminar el bloque 9:

```bash
# 1. Regenerar el registro
python3 scripts/reconcile_registry.py --output docs/seguridad/registro-unificado.md

# 2. Los hechos que definen que el borde interno sigue cerrado
grep -c '"oidc_token": _oidc_token()' backend/app/services/task_dispatcher.py  # → 3
grep -rn "verify_cloud_tasks" backend/app/routers/       # → pdf.py ×3 + batch.py ×2
grep -n "_ALLOWED_GCS_PREFIX" backend/app/routers/batch.py  # → definición + uso
grep -rn "ssl_cert_reqs" --include="*.py" .              # → 3 líneas, todas "required"

# 3. Y el que define lo que NO se cerró (debe seguir dando 0 — es esperado)
grep -rc "Depends(" backend/app/
```

**No uses `grep -c "OPEN" docs/seguridad/08-auditoria-actual.md` → 0 como
criterio de aceptación.** Es un criterio viejo de cuando había 34 hallazgos; hoy
hay 160 y varios quedan fuera de alcance a propósito.

**Los hallazgos con id de batch (`B7-…`, `B8-…`, `BATCH6-CANDIDATE-…`) van a
seguir apareciendo con `—` en la columna `spec` del registro aunque los
arregles.** `reconcile_registry.py` detecta specs sólo por número (`#N`). No es
un error tuyo ni una regresión.

---

## Qué NO se toca

Está en `prompt-fase2.md`, sección "Qué NO se toca en la Fase 2". En corto:
**#36 y #37** (FIEL usada, sobrescrita y borrada sin auth — HIGH, requieren
B-lite), **#45**, **#12**, **#6** (rate limiting), `BATCH6-CANDIDATE-12`, los
datos visibles en React DevTools, la inyección en headers de respuesta, los
`NaN`/`Infinity` desde XML, las opciones de subprocess del engine y el render
del XML en el DOM. **Y `#23`** (timeout de Cloud Run): decisión del dueño el
2026-07-26, ver la nota en su spec — el timeout no es la palanca porque el
trabajo no tiene cota superior conocida, y hay evidencia medida de que 600s
corta trabajo legítimo.

---

## Dónde se corta

**El corte es al terminar el bloque 9. No sigas.**

Lo siguiente es **B-lite: identidad real en el backend** — un `Depends()` global
de identidad verificada, más aislamiento por tenant del material de FIEL y de
los emisores. Cierra 14 hallazgos abiertos, incluidos dos CRITICAL con panel
unánime y la e.firma.

**Es una decisión de arquitectura y de producto, no una spec.** Depende de:

- **El plan de Vercel.** Un token OIDC local dice `"plan":"hobby"`, y la
  Deployment Protection de Vercel es de plan Pro. Si es Hobby, la vía barata
  "protege el deployment y ya" **no existe** y hay que implementar identidad en
  la aplicación o poner IAP. **Confírmalo en la consola de Vercel** — el dato
  viene de un token de entorno de desarrollo, no es concluyente.
- **Los tres llamadores que no son un navegador**: Cloud Tasks (resuelto con
  OIDC en el paso 12), el Cloud Run Job `cfdi-batch-shard`, y el propio backend
  que se auto-invoca vía `API_URL`.
- **Cuántos usuarios va a haber.** "Una identidad" y "múltiples tenants
  aislados" son sistemas distintos, y hoy no está definido cuál se necesita.

**Cuando llegues aquí: para, escribe qué quedó aplicado y qué falta, y devuelve
la decisión al dueño.** No elijas mecanismo de autenticación por tu cuenta y no
improvises un guard "temporal" en un router — esa es exactamente la deuda que
este proceso existe para evitar.
