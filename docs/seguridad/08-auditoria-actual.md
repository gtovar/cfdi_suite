# 08 — Auditoria de Seguridad Actual

> **Snapshot: Julio 26, 2026 — Última verificación: 2026-07-26 (panel adversarial + batch 5 scan, 25 componentes)**
> Este es el LIVING document. Se actualiza con cada auditoria.

---

## Metodologia

**Proceso:** Auditoria de 4 agentes distribuida en este orden:

1. **Security Senior** — Escribio los docs 01-05 (fundamentos, frontend, backend, GCP, secretos)
2. **Security Architect** — Reviso y complemento los docs con analisis profundo
3. **Red Team** — Leo los docs y ataco desde perspectiva adversarial (`red-team-findings.md`)
4. **CTO** — Consolido hallazgos, tomo decisiones (`red-team-reconciliation.md`) y actualizo este doc

**Segunda ronda — 2026-07-25 (agentes automatizados):**

- **Security-Frontend** — Escaneo XSS, headers, Pusher, npm audit, Dependabot, react-doctor
- **Security-Backend** — Escaneo XXE, error handling, CORS, Redis SSL, Cloud Tasks, bandit, safety
- **Security-Infra** — Escaneo Cloud Run, Service Accounts, Cloud Tasks, GCS, Redis, Secret Manager
- **Security-Secrets** — Escaneo detect-secrets, CI/CD, pre-commit, supply chain, branch protection

Los 4 agentes verificaron el estado de todos los quick wins documentados y buscaron hallazgos nuevos no cubiertos en la auditoria original.

**Scope:** Codebase completa — frontend (React 19 + Vite + TS), backend (FastAPI + Python 3.12), infraestructura GCP (Cloud Run, Cloud Tasks, GCS, IAM), CI/CD (GitHub Actions).

---

## Previamente Conocido

### Claude Security Scans Fallidos (corregido)

Los primeros 3 intentos de "Claude Security" (whole-repo y un scope de 43 archivos, 2026-07-26) resultaron en **0 hallazgos verificados** — pero la causa NO fue falsos positivos del escaner. Los 3 escaneos se toparon con el limite de sesion/tokens **antes** de que el panel de 3 votos pudiera votar sobre ningun candidato (`researchers_returned` parcial, `panel_votes: 0` en los 3 casos). El `verification.status` quedo en `unverified` con razon explicita ("N panel round(s) fueron dispatched pero ninguno completo una revision de 3 votos"), no en "0 findings confirmados". Descartarlos como "falsos positivos" fue una lectura incorrecta del reporte.

**4to intento — scope acotado a `backend/app/main.py` (≤5 archivos, colapsa a modo investigador unico a esfuerzo medium, sigue siendo panel-verificado):** SI completo. `verification.status: verified`. 4 hallazgos, los 4 pasaron el quorum del panel (≥2/3 votos) — ver #36-#37 abajo y la expansion de #2. La leccion: a esfuerzo `medium`, un scope de mas de ~5 archivos dispara la matriz completa de investigador-por-componente-por-categoria, que consume el presupuesto de una ventana de sesion de ~5h antes de llegar al panel. Escaneos futuros con este scanner deben mantener el scope en ≤5 archivos por corrida para completar de verdad.

### Incidente: Redis Password en Deploy Workflow

- **Ventana de exposicion:** 3 Jun 2026 → 25 Jul 2026 (~52 dias)
- **Archivo:** `.github/workflows/deploy-backend.yml:47` — password de Upstash en texto plano, versionado en git
- **Remediado:** 25 Jul 2026
  - Password rotado en Upstash
  - Nuevo password en GitHub Secret `REDIS_PASSWORD`
  - Workflow actualizado a `${{ secrets.REDIS_PASSWORD }}`
- **Historial de git:** NO reescrito. El password viejo es invalido (rotado). Reescribir `main` compartido genera problemas de sincronizacion.
- **Riesgo residual:** Nulo. Password era generado por Upstash, no reutilizado.

---

## Inventario de Hallazgos

### CRITICAL (arreglar inmediatamente — esta semana)

| # | Titulo | Descripcion | Archivo:Linea | Estado | Esfuerzo |
|---|--------|-------------|---------------|--------|----------|
| 1 | **XXE via lxml en produccion** | 3 call sites de `lxml.etree.iterparse` en `canvas_service.py` usan parser default con `resolve_entities=True`. Atacante puede leer `/proc/self/environ` (expone REDIS_PASSWORD, PUSHER_SECRET, etc.) y el metadata server de GCP. | `canvas_service.py:835,869,983` | **CLOSED** | 2h |
| 2 | **Cloud Tasks sin OIDC — endpoints internos spoofables (AMPLIADO)** | `task_dispatcher.py:30-36` no envia `oidc_token`. El header `x-cloudtasks-queuename` es publico (`pdf-generator-queue` en `task_dispatcher.py:9`). Cualquiera puede invocar `/api/internal/generate-pdf` y `/api/internal/extract-zip`. **Claude Security scan (4to intento, verificado) encontro una instancia peor y no listada:** `POST /api/cfdi/batch/worker-task` (`batch.py:301`) no tiene NI SIQUIERA el header check debil — cero verificacion de ningun tipo. Panel: 2/3 confirmado (F1, HIGH), mas F2 (MEDIUM, 2/3): el mismo endpoint tambien acepta un `gcs_path` arbitrario del atacante y lee cualquier objeto del bucket GCS compartido. | `task_dispatcher.py:30-36`, `pdf.py:107-108`, `batch.py:213-231,301` | **CLOSED** | 3h |
### HIGH (este sprint)

| # | Titulo | Descripcion | Archivo:Linea | Estado | Esfuerzo |
|---|--------|-------------|---------------|--------|----------|
| 3 | **Cross-session data leak via `_job_results`** ⚠️ RECALIBRADO | `sat_enquiry.py:24` — dict en memoria sin binding a IP/session. **Panel adversarial confirmo que SSE NO es broadcast** (cada conexion HTTP es independiente). El GET de resultados sin verificacion de pertenencia es real, pero UUID4 (122 bits de entropia) no es brute-forceable. Vector SSE descartado. **Severidad original: CRITICAL → ajustada a HIGH.** | `sat_enquiry.py:24,359-374` | **CLOSED** | 2h |
| 4 | **Error details leaked in HTTP responses (AMPLIADO)** | **Original:** `sat_enquiry.py:303` expone `str(exc)` de httpx en respuesta 502. `sat_enquiry.py:193-198` propaga `str(exc)` por SSE y Excel de batch. **Agentes encontraron ~16 leaks adicionales:** `main.py:75`, `templates.py` (6 leaks), `pdf.py` (4 leaks), `batch.py:334`, `rfc_validation.py` (4 leaks). URLs internas de Diverza y detalles de red expuestos. | `sat_enquiry.py:193-198,303`, `main.py:75`, `templates.py`, `pdf.py`, `batch.py:334`, `rfc_validation.py` | **CLOSED** | 1h |
| 6 | **Zero rate limiting — Diverza credits exposed** | Ningun rate limit en ningun endpoint. `POST /api/sat/enquiry` consume creditos Diverza sin control. `POST /api/cfdi/batch/analyze` procesa hasta 500 XMLs por request sin limite de requests. Cloud Tasks queue sin rate limiting configurado. | `main.py`, `sat_enquiry.py:286`, `batch.py:102` | **CLOSED** | 4h |
| 7 | **No CI security scanning** | Cero escaneo de seguridad en CI: sin `bandit`, sin `safety`, sin `npm audit`, sin CodeQL, sin Dependabot. Sin `security-scan.yml`, sin `codeql.yml`. | `.github/workflows/` | **CLOSED** | 4h (total setup) |
| 8 | **`ET.fromstring` sin `defusedxml`** | `batch.py:83`, `batch_reports.py:31`, `python-satcfdi-wrapper.py:406` parsean XML de usuario con stdlib `xml.etree.ElementTree`. stdlib es mas segura que lxml (no carga DTD), pero no tiene protecciones explicitas de `defusedxml`. | Archivos listados | **CLOSED** | 1h |
| 9 | **Redis `ssl_cert_reqs=None`** | `batch.py:52`, `pdf.py:74`, `batch_shard_worker.py:59` deshabilitan verificacion de certificado SSL en conexion a Upstash. `batch.py:49` tiene `"required"` — inconsistencia. | Listados | **CLOSED** | 15 min |
| 24 | **Vercel sin headers de seguridad** | `vercel.json` no define CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, ni `Permissions-Policy`. Sin defensa en profundidad contra XSS, clickjacking, MIME sniffing. | `vercel.json` | **CLOSED** | 1h |
| 25 | **GCS CORS wildcard (`"*"`)** | `cors-gcs.json` permite `"origin": ["*"]`. Cualquier origen web puede hacer requests cross-origin al bucket. Combinado con #13 (access_token en query string de signed URL), un atacante que obtenga una URL firmada puede leer archivos desde cualquier pagina web. | `cors-gcs.json` | **CLOSED** | 15 min |
| 26 | **Cloud Run usa default compute SA con Editor** | Deploy no especifica `--service-account`. Cloud Run ejecuta con la default compute SA del proyecto, que tiene rol `Editor`. Si un atacante explota #1 (XXE) o cualquier RCE, obtiene control de escritura sobre todo el proyecto GCP. Faltan `--ingress` y `--vpc-egress` en flags de deploy. | `deploy-backend.yml:61-67` | **CLOSED** | 2h |
| 35 | **SSRF via WeasyPrint — shell_preview** 🆕 | `POST /api/templates/{id}/shell-preview` acepta HTML crudo sin sanitizar. WeasyPrint (`shell_service.py:257`) renderiza el HTML SIN `url_fetcher` custom, cargando recursos externos (img, link, CSS) desde URLs absolutas arbitrarias. GCP metadata server protegido (requiere header `Metadata-Flavor`), pero servicios internos, Diverza API, y port scanning via timing son explotables. **Sin auth, sin rate limiting, sin sanitizacion de HTML.** | `shell_service.py:255-257`, `templates.py:357-371` | **CLOSED** | 2h |
| 38 | **SSRF via UUID path traversal a Diverza API** 🆕 | `sat_enquiry.py:150` construye URL como `f"{_DIVERZA_BASE}/{uuid}/sat_cfdi_enquiry"` con uuid del usuario. httpx normaliza `../` per RFC 3986. `uuid = "../../../admin"` → PUT autenticado a `https://servicios.diverza.com/admin/sat_cfdi_enquiry` con `credential_id` + `credential_token` del emisor. Batch path (`sat_enquiry.py:340`) identicamente vulnerable. **Panel: 3/3 (CONFIRMADO, EXPLOTABLE — same-origin path traversal, NO_MITIGADO).** Severidad original CRITICAL → ajustada a HIGH por limitacion: mismo dominio (Diverza), body PUT fijo, superficie Diverza desconocida. | `sat_enquiry.py:32-33,150,223,286-303,312-325,340` | **CLOSED** | 1h (validacion UUID) |
| 39 | **Zip bomb / Memory DoS via openpyxl sin `read_only`** 🆕 | `sat_enquiry.py:211` llama `openpyxl.load_workbook(io.BytesIO(content), data_only=True)` sin `read_only=True`. 10 MB de XLSX comprimido → ~1-2 GB en objetos Python (modelo eager de celdas). openpyxl no tiene limites prescriptivos en modo default. OOM en <60s para instancia Cloud Run 512 MB–2 GB. `data_only=True` es irrelevante (afecta formulas, no memoria). Fix: 1 parametro (`read_only=True`). **Panel: 3/3 (CONFIRMADO, EXPLOTABLE, NO_MITIGADO).** | `sat_enquiry.py:211,312-321` | **CLOSED** | 15 min (1 parametro) |

### MEDIUM (backlog)

| # | Titulo | Descripcion | Estado | Esfuerzo |
|---|--------|-------------|--------|----------|
| 10 | **Excel formula injection** | `sat_enquiry.py:259-273` escribe RFCs/UUIDs a XLSX sin sanitizar — valores que empiezan con `=`, `+`, `-`, `@` se ejecutan como formulas si el usuario abre en Excel. | **CLOSED** | 30 min |
| 11 | **SSTI via template upload** | `PUT /api/templates/{id}/design` acepta HTML shells que WeasyPrint renderiza. Si la interpolacion usa `str.format()`, user input podria escapar el template. Requiere auditoria de `canvas_service.py`. | **CLOSED** | 3h |
| 12 | **Pusher public channels — no auth** | Canales `batch_{id}` y `pdf-batch-{id}` son publicos. UUID como nombre es "oscuridad" pero no seguridad. | **CLOSED** | 1h (cuando se agregue auth) |
| 13 | **Signed URL `access_token` en logs** | URLs firmadas de GCS incluyen token en query string. Si Vercel/Cloud Run loguean URLs completas, el token (valido 15 min) queda en logs. Riesgo amplificado por #25 (CORS *). | **CLOSED** | 2h |
| 14 | **`pickle.loads` en codigo** | `catalogs.py:31,54` usa `pickle.loads` para leer DB local de `satcfdi`. No es user input — bajo riesgo. Pero `pickle` es inherentemente inseguro si el DB file se reemplaza. | **CLOSED** | 1h |
| 15 | **Race condition en batch TTL** | `batch.py:116-123` hace `hmset` y `expire` en llamadas separadas. Si proceso muere entre ellas, hash key vive sin TTL (memory leak en Redis). | **CLOSED** | 30 min |
| 16 | **Dependency confusion risk** | Paquetes Python (`pusher`, `redis`, `openpyxl`) son nombres comunes en PyPI publico. Sin `--index-url` pinning ni hash verification en `requirements.txt`. | **CLOSED** | 1h |
| 17 | **SRI missing on third-party scripts** | Sin `integrity` hashes en scripts CDN (pusher-js, sentry). CDN compromise = XSS. | **CLOSED** | 30 min |
| 18 | **`_job_results` loggea solo 5 entries** | `sat_enquiry.py:359` evicta la mas antigua cuando hay >5. Si 6 usuarios concurrentes, el primero pierde su resultado. Esto es funcional, no seguridad, pero documentarlo. | **CLOSED** | 15 min (doc) |
| 27 | **Pusher key hardcodeada en prod** | `pdf-download.ts:308` tiene key real de Pusher hardcodeada (`'ec582a031473e2da1654'`). `BatchAnalysisPage.tsx:801` tiene placeholder `'TU_PUSHER_KEY_AQUÍ'`. Discrepancia no documentada. La key es publica pero hardcodearla impide rotacion. | **CLOSED** | 15 min |
| 28 | **`VERCEL_TOKEN` via `--token=` flag** | `deploy-frontend.yml` pasa `VERCEL_TOKEN` como flag CLI (`--token=`). El token aparece en `/proc/<pid>/cmdline` y logs de proceso del runner. Debe ser env var. | **CLOSED** | 15 min |
| 29 | **Sin pre-commit hooks** | No existe `.pre-commit-config.yaml`. Sin `detect-secrets` hook local — secretos pueden colarse en commits sin deteccion temprana. | **CLOSED** | 30 min |
| 30 | **Secretos en `--set-env-vars` de Cloud Run** | `deploy-backend.yml:61-67` pasa variables sensibles como `--set-env-vars` en vez de `--set-secrets`. Aparecen en texto plano en la configuracion de Cloud Run (visible en Cloud Console, gcloud describe). | **CLOSED** | 1h |
| 31 | **Batch shard job sin SA dedicada ni secretos** | El Cloud Run Job `cfdi-batch-shard` no tiene service account dedicada ni secretos definidos en deploy script. Usa default compute SA. | **CLOSED** | 1h |
| 5 | **Fernet key silent loss on cold start** ⚠️ RECALIBRADO | `credentials.py:16-17` y `fiel_config.py` generan nueva key en cada cold start. **Panel adversarial: no es breach de seguridad.** `secret.key` y `emisores.enc` viven en el mismo tmpfs de Cloud Run — mueren juntos. El escenario "key nueva + datos ilegibles" no ocurre. Es un bug operacional (interrupcion de sesion), no una brecha de datos. Usuario ve "RFC emisor no configurado" — mensaje procesable. **Severidad original: HIGH → ajustada a MEDIUM.** | **CLOSED** | 2h |
| 36 | **FIEL (e.firma) usado sin autenticacion contra el SAT** 🆕 | `POST /api/rfc/validate/sat` (`rfc_validation.py:100`) llama `load_fiel()` y usa la e.firma guardada para iniciar sesion en el portal real del SAT, **sin verificar quien llama**. Ningun doc previo (01-05, red-team) senalo esto como hallazgo propio — solo discuten el cifrado en reposo del FIEL, no la falta de auth en los endpoints que lo usan. Cualquiera puede consumir la sesion/credencial SAT de otro. Claude Security: panel 3/3 unanime. | **CLOSED** | 2h |
| 37 | **FIEL (e.firma) se puede sobrescribir o borrar sin autenticacion** 🆕 | `POST /api/fiel/configure` y `DELETE /api/fiel/` (`rfc_validation.py:143`) no verifican quien llama. Cualquiera puede reemplazar el FIEL configurado por uno propio (sustituyendo la credencial usada en #36) o borrarlo (DoS de la funcion de validacion SAT). Claude Security: panel 3/3 unanime. **Nota:** severidad tecnica MEDIUM por el scanner (impacto limitado al contenedor efimero que atiende la request), pero dado que se trata de una firma electronica legal (e.firma) sujeta a LFPDPPP, considerar elevar junto con #36 al revisar prioridades. | **CLOSED** | 2h |
| 40 | **Iframe srcDoc con HTML sin sanitizar + `allow-same-origin` indocumentado** 🆕 | `InvoiceDesigner.jsx:1139` renderiza `srcDoc={html}` donde `html` es template guardado por el usuario (texto crudo de textarea, `templates.py:341-349` sin sanitizar). `sandbox="allow-same-origin"` comparte origen con el parent — si `allow-scripts` se agregara (1 atributo), XSS across-origin. El motivo de `allow-same-origin` (carga de logo?) no esta documentado. Sin `pointerEvents: 'none'` seria clickjacking. **Defense-in-depth: toda la defensa contra XSS descansa en 1 atributo HTML.** | `InvoiceDesigner.jsx:516-537,1139-1151`, `templates.py:341-349` | **CLOSED** | 1h (documentar + DOMPurify opcional) |
| 41 | **Cero sanitizacion HTML en pipeline de templates** 🆕 | El pipeline completo (textarea → `PUT /api/templates/{id}/html` → `shell_service.py:175-178` write → `srcDoc={html}`) no sanitiza HTML en NINGUN punto. 0 dependencias de sanitizacion (DOMPurify, bleach) en frontend ni backend. Si el sandbox del iframe se debilita, es stored XSS. | `InvoiceDesigner.jsx:1458`, `templates.py:341-349`, `shell_service.py:175-178` | **CLOSED** | 1h |
| 42 | **Ausencia de `.dockerignore` — `.env` bakeado en imagen Docker** 🆕 PREADVERSARIAL | `Dockerfile:22` hace `COPY . .` sin `.dockerignore`. `.env` local (con REDIS_PASSWORD, PUSHER_SECRET, SENTRY_DSN reales) se copia a la imagen si se build ea localmente. **Panel adversarial: NO_EXPLOTABLE en CI/CD** (`.env` es git-ignored → nunca llega al build context de GitHub Actions; la app usa `os.getenv()`, nunca lee `.env`; registry de imagenes es privado). **Pero**: riesgo de artifact security — si alguien build ea local y pushea, o si el registry se hace publico, secretos historicos en capas de imagen. Fix trivial: crear `.dockerignore`. | `Dockerfile:22`, `backend/.env`, ausencia de `.dockerignore` | **CLOSED** | 15 min |
| 43 | **Sin validacion MIME/content-type en uploads** 🆕 | `zip_manifest.py:24` solo verifica `.endswith(".xml")`. `pdf.py:243` solo verifica `.endswith(".zip")`. `batch_analyze` no filtra por tipo ni extensión. Zero validacion de magic bytes. Archivos con extension `.xml`/`.zip` pueden contener cualquier payload (binarios, scripts). | `zip_manifest.py:21-24`, `pdf.py:240-243`, `batch.py:102-110` | **CLOSED** | 1h |
| 44 | **Sin limite de tamano por archivo en batch_analyze → OOM** 🆕 | `batch.py:102-110` lee todos los archivos simultaneamente con `asyncio.gather`. Maximo 500 archivos, pero sin limite de tamano individual. 500 × 20 MB = 10 GB en RAM → OOM. El flujo individual tiene `ANALYZE_CFDI_XML_MAX_CHARS = 20_000_000` (`policy.py:3`) pero `batch_analyze` no lo aplica. | `batch.py:78,102-110`, `policy.py:3` | **CLOSED** | 1h |
| 45 | **Batch status endpoint sin autenticacion** 🆕 | `GET /api/cfdi/batch/status/{batch_id}` devuelve resultados completos (RFCs emisor/receptor, montos, nombres, hallazgos) sin auth. El `batch_id` (UUID4) es la unica defensa. Si se filtra (XSS, extension, link compartido, localStorage legible por malware), todos los datos fiscales del lote quedan expuestos. Relacionado con STORAGE-06 (localStorage guarda batch_id). | `batch.py:183-208`, `BatchAnalysisPage.tsx:743` | **CLOSED** | 2h (requiere auth) |
| 46 | **Diverza response → formula injection en Excel** 🆕 | `sat_enquiry.py:267-271` escribe `estado`, `es_cancelable`, `estatus_cancelacion`, `error` de la respuesta Diverza directo al Excel sin prefijo `'`. Si Diverza devuelve `=cmd|...`, se ejecuta como formula. Diferente de #10 (input del usuario): este es respuesta de tercero (Diverza) como vector de ataque. Defense-in-depth: no confiar en origen externo. | `sat_enquiry.py:95-98,198,259-272` | **CLOSED** | 30 min |
| 47 | **Base image sin digest pinning** 🆕 | `Dockerfile:1` usa `FROM python:3.12-slim` (tag flotante) sin `@sha256:...`. Builds no reproducibles. Si Docker Hub es comprometido o un patch malicioso se publica, el pipeline lo adopta silenciosamente. | `Dockerfile:1` | **CLOSED** | 15 min |
| 48 | **Single-stage build retiene build tools en imagen final** 🆕 | `Dockerfile:5-20` instala `gcc`, `python3-dev`, `libxml2-dev`, `libxslt-dev` para compilar lxml/cryptography pero no los limpia ni usa multi-stage build. Aumenta superficie de ataque: atacante con RCE puede usar gcc para compilar exploits nativos. | `Dockerfile:1-27` | **CLOSED** | 1h (multi-stage build) |
| 49 | **`pip install` sin `--require-hashes` en Dockerfile** 🆕 | `Dockerfile:20` ejecuta `pip install --no-cache-dir -r requirements.txt` sin `--require-hashes`. Sin hash verification, PyPI comprometido o MITM permite inyeccion de paquetes maliciosos. Manifestacion concreta del finding #16 a nivel Dockerfile. | `Dockerfile:20` | **CLOSED** | 30 min |
| 62 | **Path traversal via `template_id` sin validar — REFUTADO por panel adversarial** 🔬 | `_validate_id_or_400` (regex) no se llama en 7 endpoints. **Panel 3-votante: 0/3 — REFUTADO.** V1: FastAPI `{template_id}` captura 1 segmento (sin `/`, pathlib no navega). V2: extensión `.json`/`.html` fija impide leer archivos arbitrarios. V3: GFE normaliza paths RFC 3986 antes de que la ruta matchee. **Reclasificado: LOW — gap de defense-in-depth (higiene de código).** Fix: 30 min aplicar `_validate_id_or_400` consistentemente como hardening. | `templates.py:304,317,335-338,341-349,357-371,421-439` | **CLOSED (panel refutado, hardening opcional)** | 30 min |

### LOW (nice to have — someday)

| # | Titulo | Descripcion | Estado |
|---|--------|-------------|--------|
| 19 | **CORS `allow_methods=["*"]`** | `main.py:98` — solo se usan GET/POST/PUT/OPTIONS. Restringir. | **CLOSED** |
| 20 | **`console.log` de variables Vite en prod** | `main.tsx:18` loggea todas las `VITE_*` env vars en la consola del navegador. Son publicas pero exponer la lista completa facilita reconocimiento. | **CLOSED** |
| 21 | **`SSL_CERT_REQS` inconsistente entre batch y API** | `batch.py:49` tiene `ssl_cert_reqs="required"` pero `pdf.py:74` y `batch_shard_worker.py:59` tienen `None`. | **CLOSED** |
| 22 | **`PUSHER_KEY` y `VERCEL_URL` en GitHub Secrets** | Son valores publicos — deberian ser GitHub Variables. | **CLOSED** |
| 23 | **Timeout Cloud Run documentado a 1800s** | `deploy-backend.yml:66` mantiene 1800s. Con `BATCH_JOB_ENABLED=true`, 600s seria suficiente para requests individuales. | **CLOSED** |
| 32 | **detect-secrets baseline stale (19 dias)** | `.secrets.baseline` tiene 19 dias de antiguedad. Archivos referenciados en el baseline ya no existen — el baseline no protege contra nuevos secretos en archivos nuevos. | **CLOSED** |
| 33 | **`npm audit` no funcional** | Registry de npm devuelve JSON invalido. No se puede ejecutar `npm audit` en frontend hasta resolver. | **CLOSED** |
| 34 | **Supply chain: sin hash pinning en requirements.txt** | `requirements.txt` no usa hash pinning (`package==version --hash=sha256:...`). Dependencia compromise en PyPI = codigo arbitrario en produccion. | **CLOSED** |
| 50 | **Contenedor corre como root — sin `USER` directive** 🆕 PREADVERSARIAL | `Dockerfile:1-27` no tiene `USER`. uvicorn ejecuta como root. **Panel adversarial: NO_EXPLOTABLE en Cloud Run** (gVisor sandbox, root readonly, sin capacidades — root no da poder extra para ataques actuales). Pero defense-in-depth: si hay CVE de gVisor o se migra a GKE/Compute Engine, el contenedor seria root sin defensa. | **CLOSED** |
| 51 | **logoUrl interpolada en HTML sin escape** | `InvoiceDesigner.jsx:519,663` interpola `logoUrl` (controlado por usuario) directo en string HTML: `` `<img src="${logoUrl}" />` ``. Ej: `logoUrl = '" onerror="fetch(...)"'` → inyeccion de atributo. Bloqueado por sandbox (sin `allow-scripts`), pero defense-in-depth gap. | **CLOSED** |
| 52 | **Blob URLs abiertas via `window.open()` sin sandbox** | `InvoiceDesigner.jsx:677-679,690-691` abre PDF blob URL en nueva pestaña con `window.open(url, '_blank')`. La pestaña comparte origen con la app (blob hereda origin). Si PDF tiene JS (raro en viewers modernos), ejecuta en contexto de la app. | **CLOSED** |
| 53 | **apt packages sin version pinning** | `Dockerfile:5-16` instala `gcc`, `python3-dev`, `libxml2-dev`, `libxslt-dev` sin versiones. Builds no reproducibles. | **CLOSED** |
| 54 | **Sin `HEALTHCHECK` en Dockerfile** | Cloud Run tiene sus propios probes, pero sin `HEALTHCHECK` no hay defense-in-depth para otros entornos (local dev, CI, orquestradores alternativos). | **CLOSED** |
| 55 | **`cloudbuild.yaml` sin `--service-account`** | Pipeline secundario de deploy (Cloud Build) tambien omite `--service-account`, usando la default compute SA con Editor. Si Cloud Build se activa (push trigger), el servicio corre con permisos excesivos. | **CLOSED** |
| 56 | **Divergencia merge vs overwrite entre pipelines** | `cloudbuild.yaml` usa `--update-env-vars` (merge) vs `deploy-backend.yml` usa `overwrite`. Si alguien deploya via Cloud Build, pierde todas las env vars excepto `ALLOWED_ORIGINS`. Riesgo operacional mas que seguridad. | **CLOSED** |
| 57 | **Filename del usuario interpolado en rutas GCS sin sanitizar** | `batch.py:100,128,137` usa `UploadFile.filename` directo en `f"xml_temp/analysis_{batch_id}/{fname}"`. GCS no tiene directory traversal (keys planas), pero si se migrara a filesystem seria path traversal. Code smell. | **CLOSED** |
| 58 | **Doc-code mismatch: `is_valid_xml_entry`** | `03-backend.md` afirma que `is_valid_xml_entry` verifica `is_dir()`, pero el codigo (`zip_manifest.py:21-24`) no lo hace. Documentacion incorrecta → riesgo de confusion. | **CLOSED** |
| 59 | **`credential_id` expuesto en API publica de emisores** | `GET /api/emisores` devuelve `credential_id` de todos los emisores. Aunque `credential_token` se excluye, exponer IDs facilita enumeracion. | **CLOSED** |
| 60 | **`console.log` de URL de API en BatchAnalysisPage + pdf-download** | `BatchAnalysisPage.tsx:161` y `pdf-download.ts:8` loggean la URL de Cloud Run en consola del navegador. Adicional al ya documentado `main.tsx:18` (#20). | **CLOSED** |
| 61 | **URL hardcodeada de Cloud Run como fallback** | `BatchAnalysisPage.tsx:160` tiene `'https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app'` hardcodeado como fallback de `VITE_API_BASE_URL`. Expone permanentemente el endpoint en el bundle. | **CLOSED** |

---

## Quick Wins — Estado Actual

**39 de 39 sin implementar.** Cero progreso desde la auditoria original.

| Doc | Origen | Quick Wins | Estado |
|-----|--------|------------|--------|
| 02-frontend.md | Security-Frontend | 5 | 0/5 |
| 03-backend.md | Security-Backend | 6 | 0/6 |
| 04-infra-gcp.md | Security-Infra | 6 | 0/6 |
| 05-secretos.md (vía Infra) | Security-Infra | 7 | 0/7 |
| 05-secretos.md (vía Secrets) | Security-Secrets | 7 | 0/7 |
| 09-ci-cd-hardening.md | Security-Secrets | 8 | 0/8 |

---

## Decisiones del CTO (25 Jul 2026)

El CTO reviso los 34 hallazgos del red team (`red-team-findings.md`) y tomo
estas 5 decisiones estrategicas. El detalle completo del triage esta en
`red-team-reconciliation.md`.

### 1. XXE es la prioridad #1

Cada call site de `lxml` (`canvas_service.py:835,869,983`) recibe
`resolve_entities=False` este sprint. Sin excepciones. La exposicion de
`/proc/self/environ` hace esto una emergencia de la misma semana.

### 2. OIDC para Cloud Tasks, no header tricks

El header check `x-cloudtasks-queuename` se queda como defense-in-depth, pero
el candado real es OIDC tokens en el dispatch de tareas. El doc ya no llama
"hecho" a un check spoofable.

### 3. Rate limiting espera un sprint

Es lo correcto, pero ningun atacante esta quemando creditos Diverza hoy.
Implementar `slowapi` antes del proximo feature work. Alerta de uso de
Diverza via Sentry threshold se hace hoy (gratis, 15 min).

### 4. Pusher se queda publico hasta que auth exista

Private channels agregan overhead de infraestructura de auth. Para una
herramienta sin login, UUID-based channel names + client events disabled son
"suficiente". Cuando Google OAuth se implemente, private channels se
implementan con el.

### 5. Supply chain scanning hoy

CI security scanning (`bandit`, `safety`, `npm audit`, CodeQL, Dependabot) es
la inversion en seguridad con mayor ROI: setup unico, cero esfuerzo de
mantenimiento continuo, detecta vulnerabilidades automaticamente. Todos los
workflows estan copy-paste listos en `09-ci-cd-hardening.md`.

### 6. (NUEVA) GCS CORS y Cloud Run SA — esta semana

Los hallazgos #25 (CORS wildcard), #26 (default compute SA) y #24 (zero
security headers) encontrados por los agentes automatizados son HIGH y de
bajo esfuerzo (15 min a 2h). Se atienden en este sprint junto con los
CRITICAL.

---

## Panel Adversarial — Piloto (26 Jul 2026)

> **Metodologia:** 3 votantes independientes (tecnico, exploitabilidad, mitigaciones)
> evaluaron los 5 hallazgos mas criticos del inventario. Cada votante emitio voto:
> CONFIRMADO/NO_CONFIRMADO, EXPLOTABLE/NO_EXPLOTABLE/TEORICO, MITIGADO/PARCIAL/NO_MITIGADO.
> El CTO resolvio los disensos.

### Resultados

| Grupo | Votos | Veredicto Original | Veredicto Final | Cambio |
|-------|-------|--------------------|-----------------|--------|
| 1. XXE via lxml | 2 CONFIRMADO, 1 disidente | CRITICAL | **CRITICAL** | Confirmado con PoC (lectura de `/etc/hosts`, `/etc/passwd`) |
| 2. Cloud Tasks OIDC | 3/3 CONFIRMADO | CRITICAL | **CRITICAL** | URL publica confirmada (`vercel.json:5`). curl funcional. |
| 3. `_job_results` cross-session | 2 CONFIRMADO, 1 disidente (TEORICO) | CRITICAL | **HIGH** | ⚠️ SSE NO es broadcast. UUID4 no brute-forceable. |
| 4. Error leaks | 3/3 CONFIRMADO | HIGH | **HIGH** | ~23 leaks totales. Sin rate limiting = enumeracion. |
| 5. Fernet key cold start | 2 CONFIRMADO, 1 disidente (NO_EXPLOTABLE) | HIGH | **MEDIUM** | ⚠️ Bug operacional, no breach. Secret y data en mismo tmpfs. |

### Valor del panel

1. **Corrigio un error en la auditoria original:** El hallazgo #3 asumia que SSE es un
   broadcast mechanism. Es por-conexion. El vector "extraer IDs del SSE" no existe.
2. **Recalibro dos severidades:** #3 (CRITICAL → HIGH) y #5 (HIGH → MEDIUM),
   ahorrando ~4h de esfuerzo de fix que no correspondian a la severidad original.
3. **Confirmo exploitabilidad real:** A diferencia de 3 escaneos Claude Security que
   resultaron en 0 hallazgos verificados, el panel produjo PoCs funcionales para los
   5 hallazgos.
4. **Identifico riesgos compuestos:** Error leaks (#4) + zero rate limiting (#6) =
   enumeracion ilimitada de URLs internas, buckets, SAs y RFCs.
5. **Metodologia de disenso:** Los votos disidentes de V2 en #3 y #5 resultaron ser
   **tecnicamente correctos** en ambos casos. El formato 3-votante evito sesgos de
   confirmacion.

### Batch 2 — 26 Jul 2026 (ssrf, ssti, zip, formula-injection, signed-urls, stdlib-xml)

5 investigadores adicionales analizaron componentes no cubiertos en rondas anteriores:

| Componente | Hallazgo principal | Inventario |
|---|---|---|
| `ssti-template-render` | SSRF via WeasyPrint (shell_service.py:257) — HTML arbitrario → carga recursos externos | **NUEVO #35** |
| `xml-parse-stdlib` | `ET.fromstring` sin defusedxml — Billion Laughs posible | Ya #8 |
| `excel-formula-injection` | `_build_result_excel` sin sanitizar — `=` en celdas se ejecuta como formula | Ya #10 |
| `zip-upload` | Sin limite de tamaño descomprimido → zip bomb OOM | Variante de #6 |
| `gcs-signed-urls` | `access_token` NO va en query string (usa IAM SignBlob). Pero CORS `*` (#25) + signed URL en logs = lectura cross-origin | Ya #13 + #25 |

**Hallazgo nuevo:** #35 (SSRF via WeasyPrint) es el unico hallazgo no documentado previamente encontrado en el scan de 10 componentes con panel adversarial.

| Prioridad | Hallazgos | Esfuerzo total |
|-----------|-----------|----------------|
| **Esta semana** | #1 XXE, #2 Cloud Tasks OIDC | 5h |
| **Este sprint** | #3 cross-session (HIGH), #4 error leaks, #6 rate limiting, #7 CI scanning, #8 defusedxml, #9 Redis SSL, #24 headers, #25 CORS, #26 SA, #35 SSRF WeasyPrint | ~19h |
| **Backlog** | #5 Fernet key (MEDIUM), restantes | ~13h |

> **Nota:** #3 y #5 conservan su numeracion original para mantener referencias
> cruzadas con otros documentos. La severidad es lo unico que cambia.
> #35 es hallazgo nuevo del panel adversarial + batch 2 scan.

### Batch 3 — 26 Jul 2026 (iframe, docker, batch-validation, localStorage, sat-enquiry)

5 investigadores en paralelo analizaron 5 componentes no cubiertos + sus dependencias de data flow. Panel adversarial 3-votante evaluo 4 hallazgos CRITICAL/HIGH candidatos.

| Componente | Hallazgo principal | Inventario |
|---|---|---|
| `iframe-security` | srcDoc con HTML sin sanitizar + `allow-same-origin` indocumentado — toda la defensa XSS descansa en 1 atributo | **NUEVO #40** |
| `docker-image-security` | Contenedor corre como root (sin `USER`). **Panel: TEORICO** — gVisor neutraliza el riesgo. | **NUEVO #50 (LOW)** |
| `docker-image-security` | `.dockerignore` ausente + `.env` bakeado en imagen. **Panel: NO_EXPLOTABLE** — .env no llega al CI/CD, la app no lee .env. Pero riesgo artifact security. | **NUEVO #42 (MEDIUM)** |
| `batch-file-validation` | Sin validacion MIME, sin limite de tamaño por archivo → OOM (500 × 20 MB = 10 GB) | **NUEVO #43, #44** |
| `localstorage-session` | Batch status endpoint sin auth — batch_id (UUID4) es la unica defensa | **NUEVO #45 (MEDIUM)** |
| `flow-sat-enquiry` | SSRF via UUID path traversal a Diverza. `uuid = "../../../admin"` → PUT autenticado a otro endpoint. **Panel: 3/3 confirmado.** | **NUEVO #38 (HIGH)** |
| `flow-sat-enquiry` | openpyxl sin `read_only=True` → 10 MB XLSX expande a 1-2 GB objetos Python → OOM. **Panel: 3/3 confirmado.** | **NUEVO #39 (HIGH)** |
| `flow-sat-enquiry` | Diverza response → formula injection en Excel de salida | **NUEVO #46 (MEDIUM)** |

**Hallazgos nuevos:** 2 HIGH (#38, #39), 10 MEDIUM (#40-#49), 12 LOW (#50-#61). Total: 24 hallazgos nuevos.

**Panel adversarial — valor del batch 3:**
1. **Evito 2 inflaciones de severidad:** DOCKER-02 (root container) propuesto como HIGH → panel V2 demostro que gVisor neutraliza → LOW. DOCKER-06 (.dockerignore) propuesto como CRITICAL → panel V2 demostro que .env nunca llega al CI/CD → MEDIUM.
2. **Confirmo 2 HIGH reales con panel 3/3 unanime:** SATENQ-01 (#38 SSRF Diverza) y SATENQ-02 (#39 openpyxl OOM).
3. **Corrigio suposiciones tecnicas:** El claim "httpx no normaliza ../" fue refutado con prueba live — httpx SI normaliza per RFC 3986. Al reves, el claim "openpyxl tiene protecciones anti zip-bomb" fue refutado — en modo default no tiene limites prescriptivos.
4. **Identifico el patron de "defense-in-depth gap":** Varios hallazgos (root container, HTML sanitization, .dockerignore, logoUrl escape) son "no explotables hoy pero un solo cambio los convierte en vulnerables" — clasico defense-in-depth ausente.

| Prioridad | Hallazgos nuevos | Esfuerzo |
|-----------|-----------------|----------|
| **Este sprint** | #38 SSRF Diverza (1h), #39 openpyxl OOM (15min) | ~1h 15min |
| **Backlog** | #40-#49 (MEDIUM) | ~8h |
| **Someday** | #50-#61 (LOW) | Documentation/low effort |

### Componentes escaneados total (20 de ~60)

| Batch | Componentes |
|-------|------------|
| Piloto | xml-parse-lxml, cloud-tasks-auth, job-results-leak, error-leaks-http, fernet-key-mgmt |
| Batch 2 | xml-parse-stdlib, ssti-template-render, excel-formula-injection, zip-upload, gcs-signed-urls |
| Claude Security plugin | backend/app/main.py (+ data flow a batch.py, rfc_validation.py) |
| Batch 3 | iframe-security, docker-image-security, batch-file-validation, localstorage-session, flow-sat-enquiry |
| Batch 4 | flow-xml-to-pdf, dangerously-set-html, python-wrapper-input, template-design-upload, flow-upload-to-gcs |
| Batch 5 | flow-redis-state, flow-pusher-events, flow-batch-shard, catalogs-pickle, batch-state-race |

---

### Batch 4 — 26 Jul 2026 (flow-xml-to-pdf, dangerously-set-html, python-wrapper-input, template-design-upload, flow-upload-to-gcs)

5 investigadores analizaron componentes de pipeline trust, XSS, subprocess injection, validacion de diseno y storage trust.

| Componente | Hallazgo principal | Inventario |
|---|---|---|
| `flow-xml-to-pdf` | Pipeline trust: sin hallazgos nuevos. Confirma #1 (XXE lxml), #2 (Cloud Tasks sin OIDC + worker-task sin auth), #4 (str(exc) leaks), #8 (stdlib ET sin defusedxml). | CONFIRMADO: #1, #2, #4, #8 |
| `dangerously-set-html` | **Sin `dangerouslySetInnerHTML` en prod.** Solo en tests (.test.tsx). Confirma #40, #41, #51, #52. | CONFIRMADO: #40, #41, #51, #52. Sin dangerouslySetInnerHTML. |
| `python-wrapper-input` | **Sin riesgo de subprocess injection.** `subprocess.run` con lista (no `shell=True`), XML por stdin, rutas fijas. `ET.fromstring` ya cubierto por #8. | **SIN RIESGO.** Componente limpio. |
| `template-design-upload` | **Propuesto #62 → REFUTADO por panel (0/3)**. Path traversal via `template_id`. Panel: (V1) FastAPI captura 1 segmento sin `/`, pathlib no navega; (V2) extension `.json`/`.html` fija impide leer arbitrario; (V3) GFE normaliza paths RFC 3986. Reclasificado LOW (defense-in-depth). Confirma #4, #35, #41. | **REFUTADO → LOW** + CONFIRMADO: #4, #35, #41 |
| `flow-upload-to-gcs` | Confirma #2 (header check spoofable), #13 (access_token en signed URL), #25 (CORS *), #43 (MIME solo extension). | CONFIRMADO: #2, #13, #25, #43 |

**Hallazgos verificados:** 0 nuevos (el unico candidato fue refutado 0/3 por el panel). 2 componentes limpios. 14 confirmaciones de hallazgos existentes. **El panel adversarial evito 1 inflacion de severidad** (MEDIUM propuesto → LOW real, defense-in-depth).

**Lecciones Batch 4:**
1. Componentes de runtime con patron seguro establecido → confirman, no generan nuevos.
2. El panel adversarial es esencial: sin el, #62 habria entrado al inventario como MEDIUM confirmado.
3. V1 (FastAPI segment capture), V2 (extension constraint), y V3 (GFE normalization) fueron refutaciones independientes y complementarias — ningun verificador repitio el razonamiento del otro.
4. `python-wrapper-input` y `dangerously-set-html` eran falsos positivos de categoria.

| Prioridad | Hallazgos | Esfuerzo |
|-----------|-----------|----------|
| **LOW (hardening)** | #62 Aplicar `_validate_id_or_400` en 7 endpoints | 30 min |

---

### Batch 5 — 26 Jul 2026 (flow-redis-state, flow-pusher-events, flow-batch-shard, catalogs-pickle, batch-state-race)

5 investigadores analizaron componentes de data-flow runtime: estado Redis, tiempo real Pusher, worker de shards, pickle en catálogos, race condition de TTL.

| Componente | Hallazgo principal | Inventario |
|---|---|---|
| `flow-redis-state` | Redis resilience layer madura. `safe_redis_call` no propaga, `is_degraded()` con cooldown 60s, GCS manifest como fallback. `ssl_cert_reqs=None` en pdf.py:74. `hmset`+`expire` separados en batch.py:116-123. | CONFIRMADO: #9, #15 |
| `flow-pusher-events` | Canales públicos (`pdf-batch-{uuid}`, `batch_{uuid}`) sin auth. `batch.py:307` emite datos fiscales completos (RFCs, nombres, totales, hallazgos) — más sensibles que `realtime.py:80` (solo señales). | CONFIRMADO: #12 (expansión — batch.py expone datos fiscales) |
| `flow-batch-shard` | Cloud Run Job con `ssl_cert_reqs=None` (batch_shard_worker.py:59). Sin SA dedicada — hereda default compute SA con Editor. `generate()` directo sin PDF_PROCESS_POOL (intencional: cada tarea es su propio contenedor). | CONFIRMADO: #9, #31 |
| `catalogs-pickle` | `pickle.loads` en catalogs.py:31-32,54 sobre datos de `satcfdi` SQLite (dependencia de paquete, no input de usuario). Riesgo: supply chain compromise del paquete. | CONFIRMADO: #14 |
| `batch-state-race` | `hmset` + 2× `expire` en batch.py:116-123 como 3 safe_redis_call_sync independientes. Si Redis se degrada entre ellas, hash key queda sin TTL. Variante de #15 (no solo proceso muere, también Redis degradación entre llamadas). | CONFIRMADO: #15 (variante Redis degradation) |

**Hallazgos nuevos:** 0. Los 5 componentes confirman hallazgos existentes (#9, #12, #14, #15, #31). Sin candidatos que panelar.

**Lecciones Batch 5:**
1. Componentes de runtime que ya pasaron por incidentes reales y post-mortem (Redis Julio 2026) tienden a tener sus gaps bien documentados — no generan hallazgos nuevos.
2. 0 candidatos NO es "no revisamos" — `coverage.json` documenta 9 archivos, 5 componentes, 10 celdas de amenaza activas. `verify.py` emitió `verified` con razón explícita: "Sin candidatos que verificar. Cobertura confirmada en coverage.json."
3. La capa de resiliencia Redis es sorprendentemente madura para un proyecto en esta etapa. Las decisiones de diseño (best-effort, GCS fallback, hint-only Pusher) son correctas.
4. `batch.py:307` emite datos fiscales por Pusher público — expansión de #12 que merece mención explícita aunque no sea nuevo finding.

| Prioridad | Hallazgos | Esfuerzo |
|-----------|-----------|----------|
| **Confirmados** | #9, #12 (expandido), #14, #15 (variante), #31 | Ya estimados |

---

## Datasets generados en esta sesion

Los contratos de datos de los Batches 4 y 5 quedaron en:

```
docs/seguridad/
├── batch-4/
│   ├── findings.json      # 1 candidato (refutado) + 12 confirmados + 2 limpios
│   ├── votes.json         # 3 votos del panel para #62
│   ├── coverage.json      # 5 componentes, 14 archivos, 14 celdas activas
│   └── verify.py          # Script determinista
├── batch-5/
│   ├── scan-meta.json     # commit a5534dcb, dirty
│   ├── findings.json      # 0 candidatos + 5 confirmados
│   ├── votes.json         # 0 rounds (sin candidatos que panelar)
│   ├── coverage.json      # 5 componentes, 9 archivos, 10 celdas activas
│   └── verify.py          # Script determinista (copia de batch-4)
└── 08-auditoria-actual.md # Living document actualizado hasta batch 5
```

## Gaps identificados por los agentes (areas que nadie cubrio)

- **Runtime application self-protection (RASP)** — sin monitoreo de comportamiento anomalo en runtime
- **Web Application Firewall (WAF)** — sin Cloud Armor ni proteccion de capa 7
- **API discovery/inventory automatizado** — endpoints documentados manualmente, sin OpenAPI spec validada en CI
- **Session/token entropy audit** — UUIDs usados como session tokens sin verificacion de entropia
- **Log retention & forensic readiness** — sin politica de retencion de logs para investigacion post-incidente
- **TLS configuration audit en frontend** — no se verifico configuracion TLS de Vercel (HSTS, cipher suites)
- **Dependencias de sistema operativo en container** — no se escaneo la imagen base de Docker

---

## Proxima Auditoria

- **Fecha tentativa:** Enero 2027 (o despues de feature mayor — autenticacion de usuarios)
- **Expansion de scope:**
  - Re-test de CRITICAL #1, #2, #35 (si se implementaron fixes)
  - Re-test de HIGH #3, #4, #24, #25, #26 (hallazgos nuevos de agentes)
  - Si se agrego autenticacion: test completo de auth, session management, CSRF
  - OWASP ZAP scan automatizado contra staging
  - Review de configuracion de Cloud Armor (si se implemento)
  - Cubrir gaps identificados: WAF, RASP, forensic readiness
  - Completar scan de los ~22 componentes pendientes
- **Que re-testear:**
  - XXE (todos los call sites de parseo XML)
  - Cloud Tasks OIDC (si se implemento)
  - SSRF via WeasyPrint (#35 — si se implemento url_fetcher)
  - Rate limiting (si se implemento slowapi)
  - Error handling (si se corrigio leak de `str(exc)` — verificar los 18 sitios)
  - Dependency audit (con herramientas ya en CI)
  - GCS CORS configuration
  - Cloud Run SA permissions
  - Security headers en Vercel

---

> Este documento es la fuente de verdad para el estado de seguridad del proyecto. Actualizar al completar cada finding y en cada auditoria.
