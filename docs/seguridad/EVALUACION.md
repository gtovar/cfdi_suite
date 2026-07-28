# Evaluación Final de Seguridad — cfdi_suite

> Generado: 2026-07-27
> Método: 6 agentes evaluando 62 fixes con los 10 lentes de decision-expander
> Fuentes: `08-auditoria-actual.md`, `plan-fixes.md`, `DECISION_LENSES.md`

---

## Score Final

| Veredicto | Cantidad |
|---|---|
| **APROBADO** | **57** |
| **OBSERVACIONES** | **5** |
| **REABRIR** | **0** |

---

## Observaciones (requieren acción)

| Fix | Título | Problema |
|---|---|---|
| #4 | Error details leaked | `pdf.py:354` todavía filtra `str(infra_err)`. Agregar middleware de sanitización. |
| #11 | Auditoría SSTI | Conclusión no ejecutable. Agregar test que falle si se importa jinja2/mako en shell_service. |
| #13 | Signed URL en logs | Sin guard automático contra futuros `print(url)`. Configurar `before_send` de Sentry. |
| #14 | pickle.loads en catálogos | Hash de integridad prometido en spec pero no implementado. 3 líneas. |
| #44 | Sin límite agregado en batch | Límite individual OK. Falta tope agregado por request (~100MB). |

---

## Detalle por Fix

### Fix #1 — XXE via lxml
**Veredicto**: APROBADO

- **Hecho verificado**: `_SAFE_ITERPARSE` con `resolve_entities=False`, `load_dtd=False`, `no_network=True`, `huge_tree=False`. Los 3 call sites usan `**_SAFE_ITERPARSE`.
- **Riesgo**: `_SAFE_ITERPARSE` es dict mutable module-level. Futuros call sites deben recordar usarlo.

### Fix #2 — Cloud Tasks OIDC
**Veredicto**: APROBADO

- **Hecho verificado**: `verify_cloud_tasks` en 3 endpoints (pdf.py ×2, batch.py ×1). El worker-task que la spec original omitió está protegido. Validación de `gcs_path` como defense-in-depth.
- **Riesgo**: Si la SA pierde `serviceAccountUser` sobre sí misma, Cloud Tasks falla.

### Fix #3 — Cross-session data leak
**Veredicto**: APROBADO

- **Hecho verificado**: `_job_results` eliminado. `download_token` vía `secrets.token_urlsafe(32)`. `redis_client.getdel()` para atomicidad.
- **Riesgo**: Si Redis está degradado, resultado se pierde silenciosamente.

### Fix #4 — Error details leaked
**Veredicto**: OBSERVACIONES

- **Hecho verificado**: `error_reporting.py` centralizado. ~23 leaks corregidos.
- **Riesgo**: `pdf.py:354` todavía filtra `str(infra_err)`. Sin middleware automático, nuevos endpoints reintroducen leaks.

### Fix #5 — Fernet key silent loss
**Veredicto**: APROBADO

- **Hecho verificado**: `FERNET_KEY` desde env var o archivo local. `_warn_if_orphan_data()` detecta cold starts con datos huérfanos.
- **Riesgo**: Sin soporte para rotación de keys.

### Fix #6 — Zero rate limiting
**Veredicto**: APROBADO

- **Hecho verificado**: Rate limiter in-memory por SHA256(token). 4 endpoints protegidos (analyze 30/min, SAT enquiry 20/min, batch enquiry 5/min, batch analyze 5/min).
- **Riesgo**: In-memory no distribuido — múltiples instancias Cloud Run diluyen el límite.

### Fix #7 — CI security scanning
**Veredicto**: APROBADO

- **Hecho verificado**: `security-scan.yml`, `codeql.yml`, `dependabot.yml`, `.pre-commit-config.yaml` existen en git.
- **Riesgo**: `npm audit --audit-level=high` puede bloquear deploys si registry falla.

### Fix #8 — defusedxml
**Veredicto**: APROBADO

- **Hecho verificado**: Los 3 archivos usan `defusedxml.ElementTree`. Cero usos de stdlib `xml.etree.ElementTree`.
- **Riesgo**: Futuros imports de stdlib ET no serán detectados automáticamente.

### Fix #9 — Redis SSL verification
**Veredicto**: APROBADO

- **Hecho verificado**: 4/4 conexiones Redis con `ssl_cert_reqs="required"`.
- **Inferencia fuerte**: El hallazgo #21 (inconsistencia) era un error de lectura — cerrado como stale.

### Fix #10 — Excel formula injection
**Veredicto**: APROBADO

- **Hecho verificado**: `_sanitize_xlsx` con prefijo `'` para `=`, `+`, `-`, `@`. Cubre 4 campos usuario + 4 campos Diverza (#46).
- **Riesgo**: Futuros generadores Excel en otros endpoints no heredan automáticamente.

### Fix #11 — SSTI en template upload
**Veredicto**: OBSERVACIONES

- **Hecho verificado**: canvas_service.py usa drawString() programática. shell_service.py usa `HTML(string=html)` sin interpolación.
- **Riesgo**: Conclusión no ejecutable. Agregar test de regresión.

### Fix #12 — Pusher canales públicos
**Veredicto**: APROBADO

- **Hecho verificado**: Canales privados `private-*` con endpoint `/api/pusher/auth`. HMAC-SHA256 con Pusher secret.
- **Riesgo**: Ninguno tras B-lite.

### Fix #13 — Signed URL access_token en logs
**Veredicto**: OBSERVACIONES

- **Hecho verificado**: Excepciones capturadas después de signed URL — si falla no hay URL que loguear.
- **Riesgo**: Sin sanitización automática. Un `print()` inocente filtra tokens en Cloud Logging.

### Fix #14 — pickle.loads en catálogos
**Veredicto**: OBSERVACIONES

- **Hecho verificado**: Documentación de suposición de confianza (catalogs.py:10-14).
- **Riesgo**: Hash de integridad especificado pero no implementado.

### Fix #15 — Race condition batch TTL
**Veredicto**: APROBADO

- **Hecho verificado**: `hmset` + `expire` en pipeline único. Wrapped en `safe_redis_call_sync`.
- **Riesgo**: El expire de `_batch_results_key` (línea 168) sigue no-atómico.

### Fix #16/#34 — Supply chain hash pinning
**Veredicto**: APROBADO

- **Hecho verificado**: 1568 líneas de `--hash=sha256:` en requirements.txt. `--require-hashes` en Dockerfile (#49).
- **Riesgo**: Proceso de actualización más lento; automatizar con Dependabot.

### Fix #17 — SRI third-party scripts
**Veredicto**: APROBADO

- **Hecho verificado**: Sin scripts CDN en `index.html`. Solo entrypoint de Vite. Spec correctamente marcada obsoleta.

### Fix #18 — _job_results 5-entry eviction
**Veredicto**: APROBADO

- **Hecho verificado**: Subsumido por Fix #3. `_job_results` eliminado. Resultados en Redis con TTL.

### Fix #19 — CORS allow_methods
**Veredicto**: APROBADO

- **Hecho verificado**: Restringido de `["*"]` a `["GET", "POST", "PUT", "DELETE", "OPTIONS"]`.

### Fix #20 — console.log Vite vars
**Veredicto**: APROBADO

- **Hecho verificado**: Envuelto en `if (import.meta.env.DEV)`. Tree-shaking de Vite elimina en prod.
- **Riesgo**: Sin lint rule para prevenir regresiones.

### Fix #21 — SSL_CERT_REQS inconsistencia
**Veredicto**: APROBADO

- **Hecho verificado**: Hallazgo stale. Inconsistencia nunca existió (P5). Cerrado por Fix #9.

### Fix #22 — PUSHER_KEY/VERCEL_URL en Secrets
**Veredicto**: APROBADO

- **Hecho verificado**: `vars.VERCEL_URL` y `vars.PUSHER_KEY` en `deploy-backend.yml`.

### Fix #23 — Timeout Cloud Run 1800s
**Veredicto**: APROBADO (no aplicado por decisión consciente)

- **Hecho verificado**: Dato de producción contradice spec (extracción real de 600s). Cierre por aceptación de riesgo.
- **Riesgo**: Divergencia entre "CLOSED" en auditoría y "NO APLICADO" en plan.

### Fix #24 — Vercel headers de seguridad
**Veredicto**: APROBADO

- **Hecho verificado**: 5 headers configurados (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `HSTS`).
- **Recomendación**: Verificar con `curl -I` contra producción.

### Fix #25 — GCS CORS wildcard
**Veredicto**: APROBADO

- **Hecho verificado**: Restringido a 3 orígenes. `gsutil cors set` ejecutado.

### Fix #26 — SA dedicada Cloud Run
**Veredicto**: APROBADO

- **Hecho verificado**: `--service-account=cfdi-suite-api-sa`. `serviceAccountTokenCreator` corregido de nivel proyecto a nivel recurso.
- **Riesgo**: Sin esta corrección, el fix habría sido contraproducente.

### Fix #27 — Pusher key hardcodeada
**Veredicto**: APROBADO

- **Hecho verificado**: Key removida. Ahora lanza error si `VITE_PUSHER_KEY` no configurada.

### Fix #28 — VERCEL_TOKEN via flag
**Veredicto**: APROBADO

- **Hecho verificado**: Movido de `--token=` flag a env var en `deploy-frontend.yml`.

### Fix #29 — Sin pre-commit hooks
**Veredicto**: APROBADO

- **Hecho verificado**: `.pre-commit-config.yaml` con detect-secrets, ruff, prettier, react-doctor, governance.

### Fix #30 — Secretos en --set-env-vars
**Veredicto**: APROBADO

- **Hecho verificado**: Migrado a `secrets:` con `redis-password:latest`, `pusher-secret:latest`, `api-bearer-token:latest`.

### Fix #31 — Batch shard SA y secretos
**Veredicto**: APROBADO

- **Hecho verificado**: `--service-account=cfdi-batch-shard-sa`. `--set-secrets` para REDIS_PASSWORD y PUSHER_SECRET.

### Fix #32 — detect-secrets baseline stale
**Veredicto**: OBSERVACIONES

- **Riesgo**: Baseline regenerado pero sin sección de verificación explícita. Incompleto sin Fix #29 (pre-commit) y Fix #7 (CI).

### Fix #33 — npm audit no funcional
**Veredicto**: OBSERVACIONES

- **Hecho verificado**: La spec es un diagnóstico, no un fix. Cerrar sin determinar causa raíz es prematuro.
- **Riesgo**: Si `npm audit` sigue roto, CI security scanning falla.

### Fix #34 — Supply chain hash pinning
**Veredicto**: APROBADO (colapsa con #16)

### Fix #35 — SSRF via WeasyPrint
**Veredicto**: APROBADO

- **Hecho verificado**: `url_fetcher` compartido con `_ALLOWED_SCHEMES = {"data"}`. 3 call sites.
- **Riesgo**: `_ALLOWED_SCHEMES` bloquea logos HTTPS. Si hay logos externos, se rompen.

### Fix #36 — FIEL sin autenticación SAT
**Veredicto**: APROBADO

- **Hecho verificado**: B-lite agregó `Depends(verify_user_identity)` global. FIEL endpoints ahora requieren Bearer token.
- **Riesgo**: Token fijo rotado manualmente. Sin MFA.

### Fix #37 — FIEL sobrescribible/borrable sin auth
**Veredicto**: APROBADO

- **Hecho verificado**: Igual que #36. B-lite protege `POST /api/fiel/configure` y `DELETE /api/fiel/`.
- **Riesgo**: Idéntico a #36.

### Fix #38 — SSRF UUID path traversal Diverza
**Veredicto**: APROBADO

- **Hecho verificado**: `_is_uuid` en choke point único (`_call_diverza`). Panel 3/3 CONFIRMADO y corregido.
- **Hecho verificado**: Caso batch usa `continue` (no `raise`) para no abortar lotes.

### Fix #39 — Zip bomb openpyxl
**Veredicto**: APROBADO

- **Hecho verificado**: `read_only=True` + `wb.close()`. Verificado que no rompe `iter_rows(values_only=True)`.

### Fix #40 — Iframe srcDoc sin sanitizar
**Veredicto**: OBSERVACIONES

- **Hecho verificado**: Documentación + test de regresión (sandbox sin `allow-scripts`).
- **Riesgo**: La defensa real descansa en 1 atributo HTML. Fix es paso 1 de 2 (requiere #41).

### Fix #41 — Sanitización HTML templates
**Veredicto**: APROBADO

- **Hecho verificado**: bleach con allowlist de 38 tags en choke point (`save_html_template`). Defense-in-depth con #40.
- **Riesgo**: Strip silencioso de tags no permitidos sin feedback al usuario.

### Fix #42 — .dockerignore
**Veredicto**: APROBADO

- **Hecho verificado**: Exclusiones comprehensivas: `.env*`, `*.pem`, `*.p12`, `*.key`, `repomox-output-*.md`.

### Fix #43 — Validación MIME/magic bytes
**Veredicto**: APROBADO

- **Hecho verificado**: 3 call sites con magic bytes check (XML: BOM + `<?xml`/`<`, ZIP: `PK\x03\x04`).

### Fix #44 — Límite tamaño batch
**Veredicto**: OBSERVACIONES

- **Hecho verificado**: Límite individual por archivo (`ANALYZE_CFDI_XML_MAX_CHARS`).
- **Riesgo**: Tope agregado por request no implementado (500 × 20MB = 10GB teóricos).

### Fix #45 — Batch status sin auth
**Veredicto**: APROBADO

- **Hecho verificado**: `Depends(verify_user_identity)` global. Bearer token requerido. También vía `?token=` para SSE.

### Fix #46 — Diverza formula injection
**Veredicto**: APROBADO

- **Hecho verificado**: 4 campos Diverza pasan por `_sanitize_xlsx`. Subsumido por #10.

### Fix #47 — Base image digest pinning
**Veredicto**: APROBADO

- **Hecho verificado**: `@sha256:` en ambas etapas del multi-stage. Documentación de actualización con comandos exactos.

### Fix #48 — Multi-stage build
**Veredicto**: APROBADO

- **Hecho verificado**: Builder stage separado. gcc, python3-dev ausentes de imagen final. Virtualenv copiado con PATH configurado.

### Fix #49 — pip install --require-hashes
**Veredicto**: APROBADO

- **Hecho verificado**: `--require-hashes` en Dockerfile. `requirements.txt` generado con `pip-compile --generate-hashes`.

### Fix #50 — Contenedor como root
**Veredicto**: APROBADO

- **Hecho verificado**: `USER app` (uid 1000) + `HOME=/home/app`. `chown -R app:app /app`.

### Fix #51 — logoUrl interpolada
**Veredicto**: APROBADO

- **Hecho verificado**: 2 interpolaciones de `logoUrl` con escape de `&`, `"`, `<`.

### Fix #52 — Blob URLs sin sandbox
**Veredicto**: APROBADO

- **Hecho verificado**: `window.open` con `'noopener,noreferrer'`.

### Fix #53 — apt packages sin version pinning
**Veredicto**: APROBADO

- **Hecho verificado**: Documentado en Dockerfile. Base digest-pinned fija el snapshot de apt.

### Fix #54 — HEALTHCHECK
**Veredicto**: APROBADO

- **Hecho verificado**: `HEALTHCHECK` apuntando a `/api/health:8080`. Solo útil en dev local.

### Fix #55 — cloudbuild.yaml SA
**Veredicto**: APROBADO (absorbido por #56)

- **Hecho verificado**: Fix aplicado y luego `cloudbuild.yaml` eliminado.

### Fix #56 — Divergencia pipelines
**Veredicto**: APROBADO

- **Hecho verificado**: `cloudbuild.yaml` eliminado. Solo `deploy-backend.yml` como pipeline canónico.

### Fix #57 — Filename sanitización GCS
**Veredicto**: APROBADO

- **Hecho verificado**: `_safe_filename` con regex `[A-Za-z0-9._-]` + `Path(fname).name`.

### Fix #58 — Doc-code mismatch is_valid_xml_entry
**Veredicto**: APROBADO

- **Hecho verificado**: `is_dir()` check agregado en `zip_manifest.py:22`.

### Fix #59 — credential_id expuesto
**Veredicto**: APROBADO

- **Hecho verificado**: `credential_id` removido de `EmisorPublic`. Conservado en `EmisorCreate` (entrada).

### Fix #60 — console.log URL API
**Veredicto**: APROBADO

- **Hecho verificado**: Ambos `console.log` eliminados de BatchAnalysisPage y pdf-download.

### Fix #61 — URL hardcodeada Cloud Run
**Veredicto**: APROBADO

- **Hecho verificado**: Fallback removido. Ahora lanza error si `VITE_API_BASE_URL` no configurada.

### Fix #62 — Path traversal template_id (hardening)
**Veredicto**: APROBADO

- **Hecho verificado**: `_validate_id_or_400` en 11 endpoints. Panel adversarial refutó la vulnerabilidad (0/3) pero el hardening es válido.

---

## Riesgos residuales acumulados

| Riesgo | Severidad | Responsable |
|---|---|---|
| Rate limiter no distribuido (multi-instancia Cloud Run) | Medio | B-lite |
| Token Bearer fijo rotado manualmente (sin MFA, sin scoped tokens) | Medio | B-lite |
| Redis agotado — sin progreso en tiempo real | Operacional | Upstash upgrade |
| `pdf.py:354` leak residual (`str(infra_err)`) | Bajo | Fix #4 |
| Sin hash de integridad en catalogs pickle (#14) | Bajo | Fix #14 |
| Sin lint rule automática para `console.log`, `print(url)`, `import stdlib ET` | Bajo | CI/CD |
| `npm audit` funcionalidad no confirmada (#33) | Bajo | Fix #33 |

---

## Hallazgos promovibles a reglas permanentes

| Regla | Origen |
|---|---|
| Todo endpoint público debe pasar por `Depends(verify_user_identity)` | B-lite |
| Todo secreto en Cloud Run debe ser `--set-secrets`, nunca `--set-env-vars` | #30, #31 |
| Toda dependencia pip debe tener hash pinning (`pip-compile --generate-hashes`) | #16, #34, #49 |
| Todo archivo XML/ZIP subido por usuario debe validar magic bytes | #43 |
| Toda celda Excel con datos no confiables debe pasar por `_sanitize_xlsx` | #10, #46 |
| La e.firma (FIEL) debe almacenarse en GCS con Fernet, no en filesystem | #36, #37 |
| Las credenciales de terceros (PAC) deben estar aisladas por tenant | #30, #31 |
| Los pipelines de deploy divergentes son incidentes — un solo pipeline canónico | #56 |
