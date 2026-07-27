# 03 — Seguridad Backend

FastAPI + Python 3.12, desplegado en Google Cloud Run. API REST pública que
recibe archivos XML CFDI, los analiza, genera PDFs, y consulta el SAT vía
Diverza.

---

## Input validation

### Pydantic models — lo que ya existe

`AnalyzeCfdiRequest` (`contracts.py:13-14`):

```python
class AnalyzeCfdiRequest(BaseModel):
    xml: str = Field(min_length=1, max_length=ANALYZE_CFDI_XML_MAX_CHARS)
```

- `ANALYZE_CFDI_XML_MAX_CHARS = 20_000_000` (`policy.py:3`) — 20 MB. Bien: un
  límite explícito es mejor que confiar en el límite del parser HTTP.
- `min_length=1` evita XMLs vacíos.

`EnquiryRequest` (`sat_enquiry.py:32-38`):

```python
class EnquiryRequest(BaseModel):
    uuid: str
    rfc_emisor: str
    rfc_receptor: str
    total_cfdi: str
    motive: str = "01"
```

No hay validación de longitud ni formato para `uuid`, `rfc_emisor`, o
`rfc_receptor`. Un atacante puede enviar strings arbitrariamente largos.

`EmisorCreate` (`emisores.py:13-18`):

```python
class EmisorCreate(BaseModel):
    rfc: str
    credential_id: str
    credential_token: str
    # ...
    @field_validator("rfc")
    def rfc_upper(cls, v: str) -> str:
        return v.strip().upper()
```

Bien: valida formato. Pero `credential_token` solo se valida como no-vacío
(`emisores.py:25-30`), sin max_length.

### Refuerzos recomendados

```python
# backend/app/contracts.py — EnquiryRequest mejorado
from pydantic import BaseModel, Field, field_validator
import re

UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
RFC_RE = re.compile(r'^[A-Z&]{3,4}[0-9]{6}[A-Z0-9]{3}$')

class EnquiryRequestV2(BaseModel):
    uuid: str = Field(min_length=36, max_length=36)
    rfc_emisor: str = Field(min_length=12, max_length=13)
    rfc_receptor: str = Field(min_length=12, max_length=13)
    total_cfdi: str = Field(min_length=1, max_length=50)
    motive: str = Field(default="01", min_length=2, max_length=2)

    @field_validator("uuid")
    @classmethod
    def valid_uuid(cls, v: str) -> str:
        if not UUID_RE.match(v):
            raise ValueError("UUID inválido")
        return v

    @field_validator("rfc_emisor", "rfc_receptor")
    @classmethod
    def valid_rfc(cls, v: str) -> str:
        v = v.strip().upper()
        if not RFC_RE.match(v):
            raise ValueError(f"RFC inválido: {v}")
        return v
```

---

## XXE (XML External Entity) attacks

### El problema

Esta app parsea XML CFDI subido por usuarios con **lxml** en tres lugares:

| Archivo | Línea | API | Riesgo |
|---|---|---|---|---|
| `backend/app/services/canvas_service.py:835` | `etree.iterparse(...)` | lxml | ALTO |
| `backend/app/services/canvas_service.py:869` | `etree.iterparse(...)` | lxml | ALTO |
| `backend/app/services/canvas_service.py:983` | `etree.iterparse(...)` | lxml | ALTO |
| `backend/app/routers/batch.py:83` | `ET.fromstring(...)` | stdlib xml | MEDIO |
| `backend/app/services/batch_reports.py:31` | `ET.fromstring(...)` | stdlib xml | MEDIO |
| `backend/wrappers/python-satcfdi-wrapper.py:406` | `ET.fromstring(...)` | stdlib xml | MEDIO |
<!-- Updated per red-team finding I2: corrected wrapper path from app/services to wrappers -->

Ninguno de estos llamados deshabilita explícitamente entidades externas. lxml
por defecto habilita `resolve_entities=True` y carga DTD. El `xml.etree.ElementTree`
de stdlib es más seguro por defecto (no procesa entidades externas), pero
`defusedxml` es la mejor práctica.

### Explotación XXE con lxml

Un atacante puede subir un XML CFDI que incluya:

```xml
<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<cfdi:Comprobante ...>
  <cfdi:Emisor Rfc="&xxe;" .../>
</cfdi:Comprobante>
```

El contenido de `/etc/passwd` se incrustaría en el campo `Rfc` del emisor, y
podría terminar en logs, respuestas de API, o PDFs generados — exfiltrando
archivos del servidor.

En Cloud Run el filesystem es limitado, pero el atacante podría:

- Leer variables de entorno (`file:///proc/self/environ`) — expone TODAS las
  env vars, incluyendo `SENTRY_DSN`, `PUSHER_SECRET`, `REDIS_PASSWORD`, etc.
- Leer `file:///proc/self/cmdline` — expone el comando de arranque.
- Leer el metadata server de GCP (`http://169.254.169.254/computeMetadata/v1/`) — expone tokens de service account y atributos del proyecto.
- Hacer SSRF vía entidades externas: `<!ENTITY xxe SYSTEM "http://internal-service/">`.
<!-- Updated per red-team finding F1: /proc and metadata server as XXE exfiltration targets -->

### Mitigación para lxml

```python
from lxml import etree

# Parser SEGURO — reemplaza TODO uso actual de iterparse/fromstring
SAFE_PARSER = etree.XMLParser(
    resolve_entities=False,    # Deshabilita entidades externas
    no_network=True,            # Bloquea acceso a red durante parseo
    dtd_validation=False,      # No valida contra DTD externo
    load_dtd=False,             # No carga DTD externo
    huge_tree=False,            # Protege contra XML bomb
)

# Uso:
# from lxml import etree
# for event, el in etree.iterparse(io.BytesIO(xml_bytes), events=("start",), parser=SAFE_PARSER):
#     ...
```

En `canvas_service.py`, agregar `parser=SAFE_PARSER` a las 3 ocurrencias de
`iterparse` (líneas 835, 869, 983).

### Mitigación para stdlib xml.etree.ElementTree

`xml.etree.ElementTree` es más seguro por defecto que lxml (no carga DTD
externo), pero `defusedxml` agrega protecciones adicionales:

```python
# backend/requirements.txt — agregar
defusedxml>=0.7,<1

# En batch.py:7, batch_reports.py:1, python-satcfdi-wrapper.py:6
# Reemplazar: import xml.etree.ElementTree as ET
# Por:       import defusedxml.ElementTree as ET
```

### Openpyxl (Excel) — parseo de batch SAT

`sand_enquiry.py:211` usa `openpyxl.load_workbook(content, data_only=True)`.
Openpyxl no resuelve entidades externas en su configuración actual
(`data_only=True` evita evaluación de fórmulas), y los archivos `.xlsx` son
ZIPs con XML interno. El riesgo de XXE vía Excel es bajo comparado con lxml,
pero XML bombs son teóricamente posibles en el XML interno del workbook.
<!-- Updated per red-team finding H2 -->

---

## XML Bomb / Billion Laughs attack

### Qué es

Un XML pequeño que se expande exponencialmente al parsearse:

```xml
<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!-- ... lol9 = ~1 GB en memoria -->
]>
<lolz>&lol9;</lolz>
```

El límite de `ANALYZE_CFDI_XML_MAX_CHARS = 20_000_000` (`policy.py:3`) **no
protege** contra esto: el XML comprimido/recursivo ocupa pocos KB en disco
pero explota a GB en memoria al expandir entidades.

### Mitigación

lxml con `huge_tree=False` en el parser ya mitiga. Agregar además:

```python
SAFE_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    huge_tree=False,           # Bloquea XML bomb
    max_depth=100,             # Máxima profundidad de anidamiento
)
```

Para `xml.etree.ElementTree` con `defusedxml`, la protección es automática.

---

## Rate limiting — actualmente AUSENTE

No hay rate limiting en ningún endpoint. Un atacante puede:

- `POST /api/cfdi/analyze` en loop con XMLs de 20MB → saturar CPU y cuota de
  Upstash.
- `POST /api/sat/enquiry` en loop → consumir créditos de Diverza,
  potencialmente baneando la cuenta.
- `POST /api/cfdi/batch/analyze` con ZIPs de 500 XMLs en loop → saturar Cloud
  Tasks, GCS, Redis.

### Propuesta: slowapi

```bash
# backend/requirements.txt
slowapi>=0.1,<1
```

```python
# backend/app/main.py — agregar al inicio
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Endpoints más expuestos — límites por endpoint:

```python
# backend/app/routers/batch.py
from slowapi import Limiter
from fastapi import Request

limiter = Limiter(key_func=lambda: "global")  # o usar request.client.host

@router.post("/analyze")
@limiter.limit("5/minute")  # Máximo 5 lotes por minuto por IP
async def batch_analyze(request: Request, files: list[UploadFile] = File(...)):
    ...
```

```python
# backend/app/routers/sat_enquiry.py
@router.post("/enquiry")
@limiter.limit("20/minute")  # 20 consultas SAT por minuto por IP
async def single_sat_enquiry(request: Request, body: EnquiryRequest):
    ...
```

```python
# backend/app/main.py — análisis single, el más vulnerable a loops
@app.post("/api/cfdi/analyze")
@limiter.limit("30/minute")
def analyze_cfdi(request: Request, payload: AnalyzeCfdiRequest):
    ...
```

**Atención con Cloud Run:** `get_remote_address` usa `request.client.host`. Si
Cloud Run está detrás de un proxy/LB, la IP del cliente puede estar en
`X-Forwarded-For`. Configurar:

```python
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    headers_enabled=True,  # Usa X-Forwarded-For si está presente
)
```

---

## Security headers — actualmente AUSENTES

El backend no envía headers de seguridad. Esto deja a los usuarios vulnerables
a clickjacking, MIME sniffing, y falta de HSTS.

### Middleware de headers de seguridad

```python
# backend/app/middleware/security_headers.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"  # Deprecado, CSP lo reemplaza
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        # CSP desde backend (alternativa a vercel.json)
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://js.pusher.com; "
                "connect-src 'self' https://*.ingest.us.sentry.io wss://ws-*.pusher.com; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "frame-src 'self' blob:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        return response
```

Registrar en `main.py`:

```python
from .middleware.security_headers import SecurityHeadersMiddleware
# Después de CORS middleware, antes de los routers
app.add_middleware(SecurityHeadersMiddleware)
```

---

## Safe error handling

### Lo que ya existe

`main.py:111-151` maneja `RequestValidationError` con mensajes genéricos:

```python
@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request, exc):
    public_message = "El request de análisis CFDI es inválido."
    for err in exc.errors():
        if err.get("type") == "string_too_long":
            limit = err.get("ctx", {}).get("max_length", 0)
            public_message = f"El XML es demasiado grande. Límite: {limit:,} caracteres."
            break
    return JSONResponse(status_code=422, content=...)
```

Bien: no expone el stack trace ni detalles internos.

### Lo que falta

`sat_enquiry.py:302-303` expone el mensaje de error de httpx directamente:

```python
except httpx.HTTPError as exc:
    raise HTTPException(status_code=502, detail=f"Error Diverza: {exc}")
```

`str(exc)` puede contener detalles de red, URLs internas, o respuestas crudas
de Diverza. Debe devolverse un mensaje genérico y loggear el detalle.

Además, `sat_enquiry.py:193-199` filtra `str(exc)` en resultados de batch:

```python
except Exception as exc:
    return idx, {"uuid": uuid, ..., "error": str(exc)}
```

Este error se propaga por el SSE stream (`event_stream:352`) y termina en el
Excel de resultados (`_build_result_excel:270`). Un atacante puede ver
mensajes de error de Diverza en el Excel descargado.
<!-- Updated per red-team findings V3, V4 -->

Corrección para ambos casos:

```python
except httpx.HTTPError as exc:
    logger.error("Diverza call failed", exc_info=True)
    sentry_sdk.capture_exception(exc)
    raise HTTPException(status_code=502, detail="Error al consultar el SAT")

# En _enquiry_indexed:
except Exception as exc:
    logger.error("Batch SAT enquiry failed", exc_info=True)
    sentry_sdk.capture_exception(exc)
    return idx, {"uuid": uuid, ..., "error": "Error interno al consultar"}
```

### Safe error handler global

Agregar un handler para excepciones no capturadas:

```python
# backend/app/main.py
import traceback

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Loggear completo internamente
    sentry_sdk.capture_exception(exc)
    traceback.print_exc()
    # Devolver genérico al cliente
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
    )
```

---

## Secrets management

### Estado actual: disperso y frágil

| Secreto | Dónde vive | Problema |
|---|---|---|
| `SENTRY_DSN` (backend) | `os.getenv("SENTRY_DSN")` (`main.py:51`) | OK si está en Cloud Run env vars |
| `SENTRY_DSN` (frontend) | Hardcodeado como fallback (`main.tsx:14`) | Aceptable — DSN es público |
| `PUSHER_KEY` (frontend) | Hardcodeado como fallback (`pdf-download.ts:308`) | Aceptable — key es pública |
| `PUSHER_SECRET` (backend) | `os.getenv("PUSHER_SECRET")` (`batch.py:61`) | OK si está en Cloud Run env vars |
| `PUSHER_APP_ID` | `os.getenv("PUSHER_APP_ID")` (`batch.py:59`) | OK |
| Fernet encryption key | Archivo `~/.cfdi-suite/secret.key` (`credentials.py:10`) | **CRÍTICO**: se pierde al reciclar instancia |
| `credential_token` (Diverza) | Archivo `~/.cfdi-suite/emisores.enc` (`credentials.py:11`) | Encriptado, pero la key que lo protege es efímera |
| FIEL (.cer/.key/password) | Archivo `~/.cfdi-suite/fiel.enc` (`fiel_config.py:11`) | Encriptado, mismo problema que arriba |
| Redis password | `os.getenv("REDIS_PASSWORD")` (`batch.py:44`, `pdf.py:59`) | OK si está en Cloud Run env vars |
| GCS credentials | ADC (Application Default Credentials) | OK — Cloud Run los inyecta automáticamente |

### El problema del filesystem efímero

`credentials.py:_ensure_key()` (`credentials.py:14-19`) genera o lee una
Fernet key de `~/.cfdi-suite/secret.key`. En Cloud Run, el filesystem es
**tmpfs en RAM** — cada deploy, cada scale-to-zero, cada reciclaje de
instancia BORRA este archivo. Consecuencia:

1. Se genera una NUEVA Fernet key.
2. `emisores.enc` se desencripta con la key NUEVA → falla → se trata como
   archivo vacío (`_load_raw()` devuelve `{}`).
3. Todas las credenciales de emisores configuradas se PIERDEN silenciosamente.
4. El usuario las vuelve a configurar, se encriptan con la key nueva.
5. Siguiente reciclaje → se pierden otra vez.

### Solución: Google Secret Manager

```python
# backend/app/secrets.py
import os
from google.cloud import secretmanager

def _get_secret(name: str) -> str:
    if os.getenv("K_SERVICE"):  # Running on Cloud Run
        client = secretmanager.SecretManagerServiceClient()
        project = os.getenv("GCP_PROJECT", "ultra-acre-431617-p0")
        path = f"projects/{project}/secrets/{name}/versions/latest"
        return client.access_secret_version(name=path).payload.data.decode()
    return os.getenv(name, "")


def get_fernet_key() -> bytes:
    """Obtiene la Fernet key de Secret Manager en prod, o archivo local en dev."""
    if os.getenv("K_SERVICE"):
        return _get_secret("cfdi-suite-fernet-key").encode()
    # Local dev: usar archivo en ~/.cfdi-suite/ (comportamiento actual)
    from .credentials import _ensure_key
    fernet = _ensure_key()
    # _ensure_key usa _KEY_FILE internamente
    from pathlib import Path
    return Path.home() / ".cfdi-suite" / "secret.key"
```

Cosas que van a Secret Manager:

- `cfdi-suite-fernet-key` — la key de encriptación
- `cfdi-suite-pusher-secret` — Pusher secret
- `cfdi-suite-sentry-dsn` — DSN de Sentry (aunque es público, centralizarlo
  es buena práctica)

Cosas que se quedan en Cloud Run env vars (son públicas o no críticas):

- `ALLOWED_ORIGINS` — lista de orígenes CORS
- `GCS_BUCKET_NAME` — nombre del bucket
- `REDIS_HOST`, `REDIS_PORT` — endpoint de Redis

Cosas que deberían estar en GitHub Secrets pero NO en env vars de Cloud Run:

- `PUSHER_SECRET` — si ya está en GH Secrets para CI/CD, debe reflejarse en
  Secret Manager para runtime.

---

## Redis connection

### Configuración actual

```python
# batch.py:47-56, pdf.py:69-78
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=True,
    ssl_cert_reqs=None,  # ⚠️ No verifica certificado
    max_connections=30,
    health_check_interval=25,
    decode_responses=True,
)
```

**Bien:**
- `ssl=True` — conexión encriptada a Upstash.
- `password` desde variable de entorno.
- `health_check_interval=25` — detecta conexiones muertas.

**Mal:**
- `ssl_cert_reqs=None` deshabilita la verificación del certificado SSL. En un
  entorno de producción, debería ser `ssl_cert_reqs="required"`. Si Upstash
  usa certificados que fallan la verificación por alguna razón, documentarlo
  explícitamente.
- `max_connections=30` con concurrencia de Cloud Run de 5 (`deploy-backend.yml`,
  mencionado en `pdf.py:50`) es 6x la concurrencia. Está bien como margen, pero
  en picos de escala (Cloud Run puede escalar >5 instancias) podría agotar
  conexiones de Upstash.

### Mejores prácticas

```python
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=True,
    ssl_cert_reqs="required",  # Verificar certificado
    max_connections=20,         # Más conservador
    health_check_interval=25,
    socket_connect_timeout=5,   # No colgarse si Redis no responde
    socket_keepalive=True,
    retry_on_timeout=True,
    decode_responses=True,
)
```

---

## CORS middleware

### Configuración actual

```python
# main.py:92-100
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,...")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Bien:** `allow_origins` es una lista explícita de orígenes, no `["*"]`.

**Mejorable:**

- `allow_methods=["*"]` — solo se usan GET, POST, PUT, OPTIONS. Restringir a
  `["GET", "POST", "PUT", "OPTIONS", "DELETE"]`.
- `allow_headers=["*"]` — permitir solo los headers necesarios:
  `["Content-Type", "Authorization", "X-Request-ID"]`.

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID",
                   "X-Cloud-Trace-Context"],
    allow_credentials=False,  # Sin cookies de sesión
    max_age=3600,
)
```

---

## File upload security

### XML file upload (flujo individual)

`POST /api/cfdi/analyze` (`main.py:164-166`) y `POST /api/cfdi/pdf/start`
(`pdf.py:200-236`) aceptan `UploadFile`. Seguridad aplicada:

- **Límite de tamaño:** `ANALYZE_CFDI_XML_MAX_CHARS = 20_000_000` (20 MB) en
  `policy.py:3`, aplicado vía Pydantic `Field(max_length=...)` en
  `contracts.py:14`.
- **Límite de parte multipart:** `MultiPartParser.max_part_size = 100 MB`
  (`main.py:38`). Este es el límite REAL por archivo — si un atacante manda un
  archivo de 99 MB en un campo que Pydantic limita a 20M, Pydantic lo rechaza
  DESPUÉS de que Starlette ya recibió los 99 MB en memoria.
- **Validación de tipo:** `startZipConversion` verifica `.zip` por extensión
  (`pdf.py:243`). `BatchAnalysisPage` filtra por `.xml` en el frontend
  (`handleFileSelect`, `BatchAnalysisPage.tsx:958`), pero esto es client-side
  y no es seguridad.

### ZIP file upload (flujo batch)

`POST /api/cfdi/pdf/start-zip` (`pdf.py:238-369`) y
`POST /api/cfdi/batch/analyze` (`batch.py:102-145`):

- **Límite de archivos:** `MAX_FILES = 500` (`batch.py:78`).
- **Validación de ZIP:** `zipfile.BadZipFile` (`pdf.py:267`) rechaza ZIPs
  corruptos.
- **Validación de entradas:** `is_valid_xml_entry` (`zip_manifest.py`)
  verifica que cada entrada sea archivo (no directorio) y termine en `.xml`.
- **Path traversal:** El código actual lee entradas ZIP a memoria (`z.read()` en
  `pdf.py:264`) y nunca extrae a disco — seguro hoy. Pero
  `is_valid_xml_entry` (`zip_manifest.py:21-24`) solo verifica
  `filename.endswith(".xml")` — una entrada llamada
  `../../../tmp/evil.xml` pasaría el filtro. Si código futuro usa
  `extract()`/`extractall()`, debe sanitizar cada `member.filename` con
  `os.path.realpath()` o usar `zipfile.Path`. La afirmación "zipfile no
  permite escritura fuera del directorio" es incorrecta para extracción
  manual.
<!-- Updated per red-team finding H1: corrected misleading path-traversal claim -->

### Verificación adicional recomendada

```python
# En pdf.py start_pdf_zip_generation, validar tamaño del ZIP ANTES de procesar
MAX_ZIP_COMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB comprimido

content = await file.read()
if len(content) > MAX_ZIP_COMPRESSED_BYTES:
    raise HTTPException(413, "El ZIP excede el límite de 100 MB")

# Volver a poner el cursor al inicio para zipfile
import io
file.file = io.BytesIO(content)
```

---

## SSRF risks

### Diverza API — UUID interpolado en URL

```python
# sat_enquiry.py:150
url = f"{_DIVERZA_BASE}/{uuid}/sat_cfdi_enquiry"
```

`_DIVERZA_BASE = "https://servicios.diverza.com/api/v2/documents"` — dominio
hardcodeado. El `uuid` se valida contra Pydantic (`EnquiryRequest`). Si se
agrega validación de formato UUID (ver §Input validation arriba), el riesgo
SSRF aquí es **bajo**: no se puede forzar una URL arbitraria.

### Cloud Tasks — URL interna

```python
# task_dispatcher.py:33
"url": f"{API_URL}/api/internal/generate-pdf"
```

`API_URL` viene de `os.getenv("API_URL")` (`task_dispatcher.py:10`). Si no
está configurada, cae a `"https://TU_URL_DE_CLOUD_RUN.a.run.app"` — un
placeholder inofensivo. El riesgo aquí es **muy bajo**: la URL la controla el
despliegue, no el usuario.

### Google Cloud APIs

Todas las llamadas a Google Cloud usan el SDK oficial (`google-cloud-storage`,
`google-cloud-tasks`). Las URLs son internas del SDK y no manipulables por el
usuario. Riesgo **nulo**.

### Recomendación general

Si en el futuro se agregan más integraciones externas (nuevos PACs,
validadores, APIs de terceros):

1. Siempre validar/whitelistear el destino (no permitir URLs arbitrarias del
   usuario).
2. Usar timeouts explícitos (`httpx.Timeout`), no el default infinito.
3. No seguir redirects automáticamente sin validar el destino del redirect.

---

## Dependency auditing

### Herramientas

```bash
# Seguridad de dependencias Python
pip install safety pip-audit bandit
safety check                    # vulnerabilidades conocidas
pip-audit                       # alternativo, gratis sin API key
bandit -r backend/app/          # static analysis de seguridad
```

### Integración CI (GitHub Actions)

```yaml
# .github/workflows/security.yml
name: Security Scan
on: [push, pull_request]

jobs:
  python-security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install bandit safety
      - run: bandit -r backend/app/ -f json -o bandit-report.json
      - run: safety check --ignore=70612  # ignorar CVEs con fix no disponible
        continue-on-error: true
  npm-security:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm ci
      - run: npm audit --audit-level=high
```

### Dependencias actuales con riesgo conocido

| Paquete | Uso | Riesgo |
|---|---|---|
| `lxml>=5.0,<6` | Parseo de XML | XXE (ver §XXE arriba) |
| `redis>=5.0,<6` | Caché de progreso | Exposición si SSL no se verifica |
| `cryptography>=46,<48` | Fernet encryption | OK (biblioteca estándar) |
| `pusher>=3.3,<4` | Eventos en tiempo real | Secret debe estar en Secret Manager |
| `sentry-sdk>=2.0.0,<3` | Error tracking | DSN público es aceptable |
| `openpyxl>=3.1,<4` | Lectura de Excel (SAT batch) | XXE vía Excel es teóricamente posible |

---

## Endpoints internos — Cloud Tasks header check

Los endpoints `/api/internal/generate-pdf` (`pdf.py:105-108`) y
`/api/internal/extract-zip` (`pdf.py:717-726`) verifican:

```python
if "x-cloudtasks-queuename" not in request.headers:
    raise HTTPException(status_code=403, detail="Acceso denegado.")
```

Esto es correcto pero **poco robusto**: el header `x-cloudtasks-queuename` es
inyectado por el proxy de Cloud Tasks, pero si un atacante lo conoce (es el
nombre de la cola, que puede ser predecible: `pdf-generator-queue` en
`task_dispatcher.py:9`), puede falsificarlo.

**Mejora:** En Cloud Run, además del header check, verificar que la IP de
origen sea de Cloud Tasks (usar la anotación `ingress: internal` en el
servicio de Cloud Run). La solución real es OIDC: agregar `oidc_token` en
`task_dispatcher.py:30-36` para que Cloud Tasks autentique
criptográficamente cada despacho:

```python
# task_dispatcher.py — agregar al task dict
"oidc_token": {
    "service_account_email": "cfdi-suite-api-sa@...iam.gserviceaccount.com",
}
```

Y en los endpoints internos, además del header check, verificar el token OIDC
de Google (usar `google-auth` para validar el `Authorization: Bearer`).

Además: loggear a Sentry todo intento de acceso a `/api/internal/*` que falle
la verificación — actualmente un atacante puede probar sin detección.
<!-- Updated per red-team findings C2, F2 -->

---

## Checklist

### Quick wins

- [ ] Agregar `resolve_entities=False, no_network=True, huge_tree=False` al
      parser lxml en `canvas_service.py:835,869,983`.
- [ ] Reemplazar `xml.etree.ElementTree` por `defusedxml.ElementTree` en
      `batch.py:7,83` y `batch_reports.py:1,31`.
- [ ] Agregar `X-Content-Type-Options: nosniff` y `X-Frame-Options: DENY`
      como headers mínimos.
- [ ] Cambiar CORS `allow_methods` de `["*"]` a `["GET", "POST", "PUT",
      "DELETE", "OPTIONS"]`.
- [ ] Cambiar Redis `ssl_cert_reqs=None` a `ssl_cert_reqs="required"`.
- [ ] Quitar `str(exc)` de respuestas HTTP 502 en `sat_enquiry.py:303` y
      reemplazar con mensaje genérico + log interno.

### Medium effort

- [ ] Implementar rate limiting con `slowapi` en endpoints batch y SAT.
- [ ] Agregar middleware de security headers completo (CSP, HSTS, etc.).
- [ ] Migrar Fernet key a Google Secret Manager (`cfdi-suite-fernet-key`).
- [ ] Configurar `bandit` y `safety` en CI.
- [ ] Agregar handler global de errores 500 con mensaje genérico.

### Long term

- [ ] Migrar `pusher_secret` y `sentry_dsn` a Secret Manager.
- [ ] Restringir `ingress: internal` en Cloud Run para endpoints `/api/internal/*`.
- [ ] Implementar audit logging estructurado (quién consultó qué UUID en SAT).
- [ ] Usar `defusedxml` en TODOS los puntos de parseo XML (incluyendo
      `python-satcfdi-wrapper.py`).
- [ ] Agregar CAPTCHA (Cloudflare Turnstile) en endpoints de upload para
      prevenir abuso automatizado.

---

> Referencia externa: https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html
