# 01 — Fundamentos de Seguridad

Guía de fundamentos de seguridad para cfdi-suite: app CFDI pública (sin
autenticación), frontend React 19 + Vite + TypeScript desplegado en Vercel,
backend FastAPI + Python 3.12 en Google Cloud Run.

---

## OWASP Top 10 (2021) — aplicado a cfdi-suite

### A01:2021 — Broken Access Control

**Estado real.** La app no tiene autenticación hoy — todo endpoint es público.
No se está vulnerando control de acceso porque no hay control que vulnerar.

**Riesgo futuro.** Si se añade login (Google OAuth, API keys), aparecerá el
problema real: `GET /api/emisores` (`backend/app/routers/emisores.py:49`)
expone todos los `credential_id` de todos los emisores configurados. Cualquier
usuario autenticado podría ver tokens de credenciales ajenas.

**Mitigación.** El día que se añada autenticación, cada endpoint debe validar
que el `rfc` consultado pertenece al usuario autenticado. No basta con ocultar
el `credential_token` (ya se hace en `credentials.py:38-41`); el
`credential_id` también es sensible.

### A02:2021 — Cryptographic Failures

**Estado real.** Varios hallazgos en el código actual:

1. Fernet key generada al vuelo y almacenada en el filesystem efímero de Cloud
   Run (`credentials.py:16-17`). Si la instancia recicla, se genera una clave
   NUEVA — todo lo encriptado con la anterior queda ilegible. Esto no es un
   fallo criptográfico (Fernet es sólido), pero sí un fallo de gestión de
   claves. Ver §Secrets management en `03-backend.md`.

2. `sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), ...)` en `main.py:51` — si la
   variable no existe, el DSN es `None` y Sentry simplemente no reporta. Está
   bien: no hay hardcodeo del DSN de backend.

3. Frontend: el DSN de Sentry está hardcodeado como fallback en
   `frontend/src/main.tsx:14`. Es aceptable — los DSN de Sentry son públicos
   por diseño (solo permiten ingest, no lectura).

### A03:2021 — Injection

**Estado real.** El vector más relevante es XXE (XML External Entity), que es
inyección vía XML. Ver §XXE en `03-backend.md`. El código actual no tiene
protección explícita: `lxml.etree.iterparse` en `canvas_service.py:835` y
`xml.etree.ElementTree.fromstring` en `batch.py:83` no deshabilitan entidades
externas.

**Mitigación.** Configurar `resolve_entities=False` en lxml y usar
`defusedxml` donde se use `xml.etree.ElementTree`. **Crítico: el XML
entrante no se valida contra el esquema CFDI — solo se verifica tamaño
(`min_length=1, max_length=20_000_000` en `contracts.py:13-14`).**
<!-- Updated per red-team findings C1, F4 -->

### A04:2021 — Insecure Design

La app fue diseñada como herramienta pública sin autenticación. Eso es una
decisión de diseño consciente, no un descuido. Pero tiene consecuencias:

- Cualquiera puede subir archivos ilimitados (no hay rate limiting).
- Cualquiera puede consultar el SAT usando credenciales configuradas en el
  servidor (`sat_enquiry.py:286-306`).
- El endpoint `/api/internal/generate-pdf` (`pdf.py:105-108`) verifica
  `x-cloudtasks-queuename`, pero este header es **spoofable** — la cola se
  llama `pdf-generator-queue` (`task_dispatcher.py:9`), valor público. La
  protección real requiere OIDC token en el despacho del task (ver C2 en
  `red-team-findings.md` y §4.1 de `04-infra-gcp.md`).
  <!-- Updated per red-team findings C2, F5 -->

**Nota sobre LFPDPPP.** Los RFC son datos personales bajo la Ley Federal de
Protección de Datos Personales en Posesión de los Particulares (México). La
app actual no tiene controles de acceso ni bitácoras de consulta. Si el
alcance crece más allá de herramienta personal, se requiere: registro de
accesos, política de privacidad, y mecanismo para ejercer derechos ARCO.
<!-- Updated per red-team finding W5 -->

### A05:2021 — Security Misconfiguration

**Estado real — hallazgos concretos:**

| Configuración | Estado | Ubicación |
|---|---|---|
| CORS `allow_methods=["*"]` | Demasiado abierto | `main.py:98` |
| CORS `allow_headers=["*"]` | Demasiado abierto | `main.py:99` |
| Security headers (CSP, HSTS, etc.) | Ausentes | N/A |
| Rate limiting | Ausente | N/A |
| `MultiPartParser.max_part_size` | 100 MB | `main.py:38` |
| Vercel rewrites expone URL de Cloud Run | Hardcodeada | `vercel.json:5` |

**Mitigación.** Ver §Security headers y §Rate limiting en `03-backend.md`.

### A06:2021 — Vulnerable and Outdated Components

**Estado real.** Dependencias monitoreadas parcialmente:

- `requirements.txt` (`backend/requirements.txt:1-33`) usa versiones pinnadas
  con rangos (`>=`/`<`). Bien.
- `package.json` (`frontend/package.json:23-52`) usa `^` (caret ranges).
  Aceptable para frontend con `npm audit`.
- No hay `safety`/`pip-audit`/`bandit` en CI. No hay Dependabot configurado
  en GitHub para Python.

### A07:2021 — Identification and Authentication Failures

No aplica hoy. Si se añade autenticación, atención a `credentials.py`: las
credenciales de emisores (incluyendo `credential_token` para Diverza) se
guardan encriptadas con Fernet en `~/.cfdi-suite/emisores.enc`. Cualquier
compromiso del filesystem de Cloud Run expone estos tokens.

### A08:2021 — Software and Data Integrity Failures

- Frontend: `startZipConversion` (`pdf-download.ts:198`) pide una URL firmada
  a `/api/cfdi/pdf/request-upload` y luego hace `PUT` a GCS directamente. La
  URL firmada es de corta duración (15 min, `pdf.py:664`). Bien.

- El pipeline `xml->PDF->download` no verifica integridad del XML después de
  subirlo (no hay hash/checksum). Un atacante MiTM en la subida a GCS podría
  alterar el contenido. La conexión es HTTPS (GCS), riesgo bajo.

### A09:2021 — Security Logging and Monitoring Failures

**Estado real.** Hay logging y monitoreo presente:

- Sentry: `main.py:50-52` y `frontend/src/main.tsx:12-16`
- Cloud Trace: `main.py:77-88`
- Métricas internas: `observability.py:34-83`
- `safe_redis_call` loggea avisos: `redis_safety.py:65`

**Falta.** No hay log de auditoría de quién subió qué archivo (imposible sin
autenticación), pero tampoco hay log estructurado de intentos de acceder a
rutas internas (`/api/internal/*`). Cloud Tasks llega con header
`x-cloudtasks-queuename`, los rechazos (403) deberían loggearse y alertar vía
Sentry. Actualmente un atacante puede probar los endpoints internos
indefinidamente sin detección.
<!-- Updated per red-team finding "No audit log of Cloud Tasks header bypass attempts" -->

### A10:2021 — Server-Side Request Forgery (SSRF)

**Estado real.** La app hace requests HTTPS salientes a:

- Diverza API: `sat_enquiry.py:150` — URL base hardcodeada
  (`https://servicios.diverza.com/api/v2/documents`), pero el UUID se
  interpola en la URL.

- Google Cloud APIs (Tasks, Storage): SDK oficial, URLs controladas por
  Google.

Ver §SSRF en `03-backend.md` para análisis detallado.

---

## OWASP API Security Top 10 — items relevantes

De los 10 items de OWASP API Security (2023), estos aplican directamente:

### API1:2023 — Broken Object Level Authorization

Cada endpoint que recibe `batch_id` o `job_id` como parámetro de ruta no
verifica pertenencia. Hoy no importa (sin usuarios), pero si se añade
autenticación, `GET /api/cfdi/pdf/batch/{batch_id}/download` (`pdf.py:488`)
permitiría a cualquier usuario descargar PDFs de cualquier lote.

### API2:2023 — Broken Authentication

No aplica hoy. Riesgo futuro: tokens JWT sin expiración, sin refresh, sin
revocación.

### API3:2023 — Broken Object Property Level Authorization

`EmisorCreate` (`emisores.py:13-18`) acepta `credential_token` sin filtrar.
`load_all()` (`credentials.py:35-41`) filtra el token al serializar, pero el
endpoint `POST /api/emisores` recibe y almacena el token sin validación
adicional del caller.

### API4:2023 — Unrestricted Resource Consumption

Crítico: no hay rate limiting. Un atacante puede subir XMLs de 20MB
(`policy.py:3`) en bucle, saturando CPU, memoria, y cuota de Upstash/Cloud
Tasks. Ver §Rate limiting en `03-backend.md`.

### API8:2023 — Security Misconfiguration

CORS con wildcards (`main.py:98-99`), sin security headers, sin rate limiting.
MultiPartParser en 100MB (`main.py:38`).

---

## Principios de seguridad

### Defense in Depth

La app ya aplica este principio en algunas capas:

1. **Capa 1 — Transporte:** HTTPS everywhere (Vercel -> Cloud Run -> GCS,
   todo TLS).
2. **Capa 2 — Validación de entrada:** Pydantic en `contracts.py:13-14`
   (`min_length=1, max_length=20_000_000`).
3. **Capa 3 — Aislamiento de workers:** PDF generation en pool de procesos
   separado (`pdf_pipeline.py`, `PDF_PROCESS_POOL`).
4. **Capa 4 — Cloud Tasks header check:** `pdf.py:107` verifica
   `x-cloudtasks-queuename` para endpoints internos.
5. **Capa 5 — Safe error handling:** `main.py:111-151` captura
   `RequestValidationError` y devuelve mensajes genéricos.

**Falta:**

- Security headers (Capa HTTP)
- Rate limiting (Capa de red)
- WAF (Web Application Firewall) — Cloud Armor en GCP
- CSP (Content-Security-Policy) en frontend

### Principle of Least Privilege

**Aplicado:**

- Redis: `safe_redis_call` degrada gracefully — Redis es acelerador
  desechable, no fuente de verdad. `batch_state_store.py:17-24`.
- GCS: lifecycle de 1 día en archivos temporales reduce costo y acumulación,
  pero **no es un mecanismo de contención de breach** — un atacante con
  acceso al bucket tiene 24h para exfiltrar datos.
- Fernet key con permisos `0o600` (`credentials.py:18`, `fiel_config.py:18`).
<!-- Updated per red-team finding F3: lifecycle != breach containment -->

**Violado:**

- `allow_methods=["*"]` y `allow_headers=["*"]` en CORS (`main.py:98-99`).
  El backend acepta cualquier método HTTP y cualquier header.
- `MultiPartParser.max_part_size = 100MB` (`main.py:38`) — generoso, sin
  justificación documentada de por qué 100MB y no 50MB o 20MB.

### "Shift Left" Security

Recomendaciones para mover seguridad al inicio del ciclo:

1. **Pre-commit:** `bandit` para Python, `npm audit --audit-level=high` para
   frontend.
2. **CI (GitHub Actions):** `safety check` o `pip-audit` en cada push.
3. **TypeScript strict mode:** ya activado vía `tsc --noEmit` en lint
   (`package.json:15`).
4. **react-doctor:** ya configurado (`doctor.config.ts:1-37`), corre en CI.
   Las reglas deshabilitadas tienen veredictos documentados.
5. **Secret scanning:** GitHub secret scanning ya detectaría DSNs y API keys
   hardcodeadas.

---

## Threat modeling — CFDI inspector app

### Activos a proteger

| Activo | Criticidad | Ubicación |
|---|---|---|
| XMLs CFDI (contienen RFC, montos, direcciones) | ALTA | Tránsito HTTPS, memoria Cloud Run, GCS `xml_temp/` |
| PDFs generados | ALTA | GCS `pdfs/` |
| Credenciales Diverza (credential_token) | CRÍTICA | `~/.cfdi-suite/emisores.enc` |
| FIEL (.cer, .key, password) | CRÍTICA | `~/.cfdi-suite/fiel.enc` |
| Fernet encryption key | CRÍTICA | `~/.cfdi-suite/secret.key` |
| Sentry DSN | BAJA | Variables de entorno + hardcodeo |
| Pusher key | BAJA | Variables de entorno + hardcodeo |

### Actores de amenaza

1. **Usuario anónimo malintencionado** — sube XMLs maliciosos (XXE, XML bomb),
   hace web scraping, abusa de recursos.
2. **Usuario legítimo descuidado** — sube XML con datos de terceros sin
   consentimiento.
3. **Atacante con acceso a red** — MiTM entre Vercel y Cloud Run (HTTPS
   mitiga).
4. **Atacante con acceso a GCS** — si las credenciales de service account se
   filtran.

### Flujos críticos

1. **Upload XML -> Análisis:** `POST /api/cfdi/analyze` (`main.py:164-166`).
   El XML viaja en el body. Validado por Pydantic solo en tamaño
   (`contracts.py:13-14`: `min_length=1, max_length=ANALYZE_CFDI_XML_MAX_CHARS`).
   **No hay validación de esquema CFDI, no hay detección de XXE, no hay
   sanitización de contenido.** El XML se pasa crudo a `run_analyze_cfdi`.
<!-- Updated per red-team finding F4: Pydantic validates size only, not content -->

2. **Upload ZIP -> Extracción -> PDF:** Cadena `request-upload -> PUT a GCS ->
   start-zip-gcs -> Cloud Task extracción -> N Cloud Tasks generate-pdf`.
   Múltiples superficies: el ZIP puede contener XMLs maliciosos, paths
   traversal en entradas ZIP, etc.

3. **Consulta SAT:** `POST /api/sat/enquiry` (`sat_enquiry.py:286-306`). Usa
   credenciales almacenadas para consultar Diverza. Cualquier usuario puede
   consultar cualquier UUID si el RFC emisor está configurado.

---

## Common attack vectors relevantes

### 1. XXE (XML External Entity Injection)

Ver detalle en `03-backend.md` §XXE. Los XMLs CFDI son parseados con lxml sin
deshabilitar entidades externas. Un atacante puede incluir `<!ENTITY xxe
SYSTEM "file:///etc/passwd">` en el XML y exfiltrar archivos del servidor.

### 2. XML Bomb / Billion Laughs

Un XML de 500 bytes que se expande a gigabytes en memoria. El límite de
`ANALYZE_CFDI_XML_MAX_CHARS = 20_000_000` (`policy.py:3`) no protege contra
esto — el XML comprimido/recursivo es pequeño en disco pero enorme al
parsearse.

### 3. Resource Exhaustion

- Subir ZIPs con miles de XMLs legítimos (el límite es 500 archivos en
  `batch.py:78`, pero un ZIP de 500 XMLs de 20MB cada uno = 10GB expandido).
- Crear batches masivos en loop (sin rate limiting, sin CAPTCHA).

### 4. Data exfiltration vía timing

Un atacante podría inferir si un RFC está configurado en el sistema midiendo
tiempos de respuesta del endpoint de consulta SAT (el que busca
`get_cred(rfc_emisor)` primero vs. el que va directo a Diverza).

### 5. Supply chain

`pip install` sin hash checking (`requirements.txt` no usa `--hash`).
`npm install` sin `--audit` en CI.

---

## Checklists

### Quick wins (esta semana)

- [ ] Agregar `resolve_entities=False` en todo uso de lxml (ver
      `03-backend.md`).
- [ ] Cambiar CORS de `allow_methods=["*"]` a `["GET", "POST", "OPTIONS"]`.
- [ ] Agregar `X-Content-Type-Options: nosniff` header.
- [ ] Ejecutar `safety check` y `npm audit` y revisar hallazgos.

### Medium effort (este mes)

- [ ] Implementar rate limiting con `slowapi` en endpoints más expuestos.
- [ ] Configurar CSP headers desde backend o Vercel.
- [ ] Agregar `bandit` y `safety` a CI (GitHub Actions).
- [ ] Migrar Fernet key a Google Secret Manager.

### Long term

- [ ] Implementar autenticación (Google OAuth) con control de acceso por RFC.
- [ ] Agregar WAF (Cloud Armor) frente a Cloud Run.
- [ ] Implementar audit logging estructurado.
- [ ] Usar `defusedxml` en todo parseo de XML de usuario.

---

> Referencia externa: https://cheatsheetseries.owasp.org/
