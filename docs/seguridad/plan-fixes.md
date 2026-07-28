# Plan de Corrección de Seguridad — cfdi_suite

> Fecha: 2026-07-25
> Baseline: `docs/seguridad/08-auditoria-actual.md` (34 hallazgos, 0 fixes aplicados)
> Estrategia: 4 PRs por severidad con specs detalladas por fix

---

## Plan 02 — Cierre de excepciones Bandit de catálogos y metadata (2026-07-28)

### Contexto comprobado

- **Hecho:** el scan de Bandit bloquea por `B310` en
  `app/routers/pdf.py` y por `B608` + `B301` en
  `app/services/catalogs.py`.
- **Hecho:** la URL de metadata no procede de una petición ni de una variable:
  es el endpoint fijo de GCP para el email de la cuenta de servicio y lleva el
  header `Metadata-Flavor: Google`.
- **Hecho:** los únicos catálogos solicitados por el renderer son
  `c_ClaveUnidad`, `c_RegimenFiscal`, `c_UsoCFDI`, `c_Moneda`,
  `c_FormaPago` y `c_MetodoPago`.
- **Hecho:** `satcfdi==4.9.16` está fijado en `backend/requirements.txt`; el
  wheel instalado declara `catalogs.db` en su `RECORD` con SHA-256 y la DB
  instalada mide 45,367,296 bytes. Su SHA-256 en el entorno de referencia es
  `9f257048a3fdd9b9306728c518073b34297c50a368eb4ffa7d35d158b749728b`.

### Decision-expander — cuatro decisiones

#### 1. URL del metadata server

- **Qué existe / intención:** se usa únicamente como fallback cuando ADC no
  expone `service_account_email`, para firmar URLs GCS en Cloud Run.
- **Supuesto débil descartado:** que sea una URL controlable por usuario; no
  lo es. Bandit sólo identifica la llamada HTTP, no esa procedencia fija.
- **Variables y límites:** se requiere HTTP (así opera el metadata server),
  timeout corto y el header obligatorio; eliminar el fallback rompería los
  entornos ADC donde no se publica el email.
- **Alternativas:** omitir el fallback; usar otro cliente de IAM; o encapsular
  el endpoint fijo. Las dos primeras reducen compatibilidad sin mejorar el
  control de entrada.
- **Riesgo y prueba mínima:** una futura edición podría convertirlo en URL
  variable. Extraer constantes privadas, una función dedicada y probar URL,
  header, timeout, éxito y fallo.
- **Recomendación (aprobada):** encapsular en un helper sin parámetros,
  etiquetar sólo esa línea `# nosec B310` con la razón y documentarla.

#### 2. Allowlist de tablas SQL

- **Qué existe / intención:** el nombre de tabla se interpolaba, aunque hoy
  llegaba de literales internos. Las claves sí usan parámetros SQLite.
- **Variable omitida:** una llamada futura a `describe()` podría pasar un
  nombre no esperado y volver peligrosa la interpolación.
- **Alternativas:** construir SQL dinámico como ahora; una tabla por función;
  o allowlist central. Una tabla por función duplica código; la allowlist
  conserva extensibilidad explícita.
- **Riesgo y prueba mínima:** negar una tabla legítima al agregar un catálogo.
  La prueba debe aceptar los seis nombres usados y rechazar cualquier otro
  antes de ejecutar SQL.
- **Recomendación (aprobada):** `_ALLOWED_TABLES` inmutable, validada por una
  sola función antes de toda consulta interpolada; `B608` queda suprimido sólo
  en las dos consultas que ya pasan por esa barrera.

#### 3. `pickle` en la DB de catálogos

- **Qué existe / intención:** el formato del paquete `satcfdi` es pickle, no
  JSON; no hay bytes de usuario ni escritura de DB en producción.
- **Riesgo real:** una sustitución de la DB o de la dependencia comprometida
  antes de arrancar sí podría ejecutar un pickle malicioso. El `try/except`
  actual además ocultaría un error de integridad.
- **Alternativas:** reimplementar/migrar toda la DB a JSON; confiar sólo en
  pip; o autenticar el artefacto antes de deserializar. Migrar requiere fork y
  mantenimiento de los catálogos SAT; pip por sí solo no protege una DB
  reemplazada después de instalarse.
- **Límite:** el hash debe rotar deliberadamente junto con cada actualización
  de `satcfdi`; no se debe aceptar un hash desde entorno, red o input.
- **Prueba mínima:** hash esperado permite la DB; mismatch lanza un error
  específico antes de abrir/deserializar; tal error no se convierte en una
  descripción vacía.
- **Recomendación (aprobada):** verificar SHA-256 y tamaño de la DB desde su
  ruta de paquete, con valores constantes versionados. Mantener `pickle` sólo
  detrás de ese control y marcar cada uso `# nosec B301` con referencia.

#### 4. Configuración Bandit

- **Qué existe / intención:** `bandit -r app/ -ll` es bloqueante en CI. Un
  `skip` global ocultaría regresiones futuras de B301/B608/B310.
- **Alternativas:** desactivar reglas globalmente; ignorar el job; excepciones
  inline revisables. Sólo la última conserva detección para código nuevo.
- **Riesgo y prueba mínima:** que una excepción demasiado amplia tape otra
  línea. Debe ejecutarse Bandit sin skips globales y resultar limpio; el texto
  de cada `nosec` debe decir el invariante que lo hace seguro.
- **Recomendación (aprobada):** no añadir `skips` en workflow ni `.bandit`;
  usar excepciones de regla concretas, documentación y pruebas de los
  invariantes anteriores.

### Plan ejecutable aprobado por decision-expander

1. Encapsular el acceso al metadata server y probar su contrato fijo.
2. Añadir allowlist de los seis catálogos y usarla en todas las consultas.
3. Añadir verificación de tamaño y SHA-256 de `catalogs.db` antes de devolver
   la conexión; propagar el fallo de integridad.
4. Documentar las excepciones exactas de Bandit, aplicar `nosec` acotados y
   añadir pruebas unitarias de metadata, allowlist e integridad.
5. Ejecutar pruebas focalizadas, la suite relevante y Bandit sin exclusiones;
   si todo pasa, subir el cambio y validar el workflow de GitHub.

**Criterio de cierre:** no hay skip global, el artefacto no confiable no llega
a `pickle.loads`, ninguna tabla fuera de allowlist llega a SQL, y Bandit queda
verde con sus excepciones justificadas.

---

## Arquitectura de implementación

```
PR 2 (HIGH) ──────┐
                   ├── Merge en orden: 2 → 1 → 3 → 4
PR 1 (CRITICAL) ──┘  (PR 2 crea la SA que PR 1 necesita para OIDC)

PR 3 (CI/CD) ────── Totalmente independiente

PR 4 (MED/LOW) ──── Totalmente independiente
```

---

## PR 1 — CRITICAL (hallazgos #1, #2, #3)

### Fix #1: XXE via lxml

**Severidad:** CRITICAL
**Archivo:** `backend/app/services/canvas_service.py`
**Esfuerzo:** 30 min
**Riesgo de regresión:** Bajo (cambio de configuración de parser, no de lógica)

**Vulnerabilidad actual:**
3 call sites de `etree.iterparse` usan solo `recover=True`. Sin `resolve_entities=False`, lxml procesa entidades externas. Un atacante puede leer `/proc/self/environ` (expone REDIS_PASSWORD, PUSHER_SECRET, SENTRY_DSN) y el metadata server de GCP.

**Cambio propuesto:**
Agregar `_SAFE_ITERPARSE` y aplicarlo a los 3 call sites.

**Diff:**
```python
# === ANTES (línea 829) ===

def _detect_tipo(xml_bytes: bytes) -> str:
    from lxml import etree
    for _, el in etree.iterparse(io.BytesIO(xml_bytes), events=("start",), recover=True):
        local = etree.QName(el.tag).localname
        return el.get("TipoDeComprobante", "I") if local == "Comprobante" else local
    return "I"

# === DESPUÉS ===

_SAFE_ITERPARSE: dict = dict(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    huge_tree=False,
    recover=True,
)

def _detect_tipo(xml_bytes: bytes) -> str:
    from lxml import etree
    for _, el in etree.iterparse(io.BytesIO(xml_bytes), events=("start",), **_SAFE_ITERPARSE):
        local = etree.QName(el.tag).localname
        return el.get("TipoDeComprobante", "I") if local == "Comprobante" else local
    return "I"

# Línea 869:  etree.iterparse(io.BytesIO(xml_bytes), events=("start", "end"), **_SAFE_ITERPARSE):
# Línea 983:  etree.iterparse(io.BytesIO(xml_bytes), events=("start", "end"), **_SAFE_ITERPARSE):
```

**Verificación post-fix:**
```bash
grep -n "resolve_entities\|no_network\|huge_tree" backend/app/services/canvas_service.py
# Debe mostrar 1 definición de _SAFE_ITERPARSE + 3 usos
```

**Rollback:** Revertir los 3 kwargs a `recover=True`. Sin riesgo estructural.

---

### Fix #2: Cloud Tasks OIDC

**Severidad:** CRITICAL
**Archivos:** `backend/app/services/task_dispatcher.py`, `backend/app/routers/pdf.py`
**Esfuerzo:** 3h
**Riesgo de regresión:** Medio (cambia autenticación de endpoints internos)
**Dependencia:** PR 2 debe mergearse primero (la SA `cfdi-suite-api-sa` debe existir)

**Vulnerabilidad actual:**
Los endpoints `/api/internal/*` se protegen solo con un header check spoofable (`x-cloudtasks-queuename: pdf-generator-queue`). El nombre de la cola es público. El `http_request` dict no incluye `oidc_token`.

**Cambio propuesto — `task_dispatcher.py`:**

```python
# === NUEVA CONSTANTE (después de línea 10) ===
_OIDC_SERVICE_ACCOUNT = os.getenv(
    "OIDC_SERVICE_ACCOUNT",
    "cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com",
)
_SERVICE_URL = os.getenv("API_URL", "")

# === ANTES (líneas 30-36) ===
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{API_URL}/api/internal/generate-pdf",
            "headers": {"Content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8")
        }
    }

# === DESPUÉS ===
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{API_URL}/api/internal/generate-pdf",
            "oidc_token": {
                "service_account_email": _OIDC_SERVICE_ACCOUNT,
                "audience": _SERVICE_URL,
            },
            "headers": {"Content-type": "application/json"},
            "body": json.dumps(payload).encode("utf-8")
        }
    }
```

Mismo cambio en `enqueue_zip_extraction` (línea 54) y `enqueue_cfdi_analysis` (línea 80).

**Cambio propuesto — `pdf.py`:**

```python
# === NUEVA FUNCIÓN DE VERIFICACIÓN (antes de los endpoints) ===
import os
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import sentry_sdk

_AUDIENCE = os.getenv("API_URL", "")

def _verify_cloud_tasks(request: Request) -> bool:
    """Verifica token OIDC de Cloud Tasks. Defense-in-depth: también requiere header."""
    if "x-cloudtasks-queuename" not in request.headers:
        sentry_sdk.capture_message(
            "Intento de acceso a endpoint interno sin header Cloud Tasks",
            level="warning",
        )
        return False
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False  # Sin OIDC configurado aún — aceptar header check temporalmente
    try:
        token = auth.split("Bearer ")[1]
        id_token.verify_oauth2_token(token, google_requests.Request(), audience=_AUDIENCE)
        return True
    except Exception:
        sentry_sdk.capture_message(
            "Token OIDC inválido en endpoint interno",
            level="error",
        )
        return False

# === ANTES (línea 107) ===
@router.post("/internal/generate-pdf")
async def internal_generate_pdf(payload: GeneratePdfPayload, request: Request):
    if "x-cloudtasks-queuename" not in request.headers:
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo Cloud Tasks.")

# === DESPUÉS ===
@router.post("/internal/generate-pdf")
async def internal_generate_pdf(payload: GeneratePdfPayload, request: Request):
    if not _verify_cloud_tasks(request):
        raise HTTPException(status_code=403, detail="Acceso denegado")

# Mismo cambio en línea 725 para /internal/extract-zip
```

**Requisitos previos:**
1. PR 2 mergeado (SA `cfdi-suite-api-sa` existe en GCP)
2. `google-auth` en `requirements.txt`: `google-auth>=2.0,<3`

**Verificación post-fix:**
```bash
# Confirmar oidc_token en los 3 task dicts
grep -c "oidc_token" backend/app/services/task_dispatcher.py
# Debe devolver: 3

# Confirmar función _verify_cloud_tasks
grep -n "_verify_cloud_tasks" backend/app/routers/pdf.py
# Debe mostrar definición + 2 usos
```

**Rollback:** Revertir `pdf.py` al header check simple. Los tasks con `oidc_token` seguirán funcionando (el endpoint ignora el token si no está configurado — ver `return False` temporal sin OIDC).

#### AMPLIACIÓN Fase 1 (2026-07-26) — dos correcciones a esta spec

**(a) Falta el tercer endpoint interno, y es el peor.** La spec de arriba cubre
`/api/internal/generate-pdf` y `/api/internal/extract-zip` (ambos en `pdf.py`).
No cubre `POST /api/cfdi/batch/worker-task` (`backend/app/routers/batch.py:210`),
que **no tiene ni siquiera el header check** — cero verificación de ningún tipo —
y además lee un `gcs_path` arbitrario del atacante contra el bucket compartido
(`batch.py:228`). Es `BATCH6-CANDIDATE-02`, panel unánime 3/3, CRITICAL.

Verificado a mano el 2026-07-26:

```bash
grep -n "x-cloudtasks\|@router.post(\"/worker-task\"" backend/app/routers/batch.py
# 210:@router.post("/worker-task")   ← y ninguna línea de x-cloudtasks
```

El fix es el mismo `_verify_cloud_tasks(request)`, movido a un módulo compartido
(`backend/app/services/internal_auth.py`) e importado por `pdf.py` **y**
`batch.py`. Adicionalmente, validar la forma de `gcs_path` antes de bajarlo:

```python
# batch.py, dentro de batch_worker_task, antes de bucket.blob(gcs_path)
_ALLOWED_GCS_PREFIX = "xml_temp_analysis/"
if not gcs_path or not gcs_path.startswith(_ALLOWED_GCS_PREFIX) or ".." in gcs_path:
    return {"status": "error", "message": "Ruta de objeto inválida"}
```

**(b) El comentario y el código de `_verify_cloud_tasks` se contradicen.** El
comentario dice "Sin OIDC configurado aún — aceptar header check temporalmente"
pero la línea hace `return False`, o sea **rechaza**. Tal como está escrita, si
se despliega `pdf.py` antes que `task_dispatcher.py`, toda la generación de PDF
se cae. **El orden de despliegue no es opcional:** primero `task_dispatcher.py`
(emitir `oidc_token`), verificar que las tareas llegan con `Authorization:
Bearer`, y sólo después `pdf.py` + `batch.py` (exigirlo). Borrar el comentario
engañoso al aplicar.

**Verificación ampliada** (corregida el 2026-07-26 al aplicar el fix — los
comandos de abajo son los que de verdad funcionan contra el código aplicado):
```bash
grep -c '"oidc_token": _oidc_token()' backend/app/services/task_dispatcher.py  # → 3
grep -rn "verify_cloud_tasks" backend/app/routers/             # → pdf.py ×3 + batch.py ×2
grep -n "_ALLOWED_GCS_PREFIX" backend/app/routers/batch.py     # → definición + uso
```

> **Dos correcciones a esta spec, hechas al aplicarla.**
>
> **La función se llama `verify_cloud_tasks`, sin guion bajo.** Vive en
> `backend/app/services/internal_auth.py` y la importan `pdf.py` y `batch.py`;
> un guion bajo inicial significa "privado del módulo" y no se importa entre
> módulos. El `grep` viejo, con guion bajo, devuelve **cero** y se lee como
> regresión cuando en realidad el fix está aplicado.
>
> **El prefijo `xml_temp_analysis/` de la AMPLIACIÓN no existe.** La ruta real
> la construye `batch_analyze` (`batch.py:145`) como
> `f"xml_temp/analysis_{batch_id}/{fname}"`. Aplicar el prefijo de la spec al
> pie de la letra habría rechazado **todas** las tareas legítimas y roto el
> análisis masivo en producción. El valor aplicado es `"xml_temp/analysis_"`,
> que además es más estrecho que `"xml_temp/"` y deja fuera los XML del
> pipeline de PDF (`xml_temp/{job_id}.xml`).
>
> También se eliminó la rama que aceptaba el header a secas cuando no había
> `Authorization`: aceptar el header spoofeable es exactamente el agujero del
> hallazgo. El riesgo de despliegue que esa rama intentaba cubrir se resuelve
> con el split en dos commits/deploys (12a emite el token, 12b lo exige).

---

### Fix #3: Cross-session `_job_results` leak

**Severidad:** CRITICAL
**Archivo:** `backend/app/routers/sat_enquiry.py`
**Esfuerzo:** 2h
**Riesgo de regresión:** Medio (cambia almacenamiento de resultados de memoria a Redis)

**Vulnerabilidad actual:**
`_job_results: dict[str, bytes] = {}` es un dict module-level sin binding a IP o sesión. El SSE stream expone `job_id` en el evento `done`. El endpoint `GET /batch/{job_id}/result` hace `pop()` sin verificar pertenencia. Un atacante que escuche el SSE puede robar el Excel de otra sesión.

**Cambio propuesto:**

```python
# === ANTES (línea 24) ===
_job_results: dict[str, bytes] = {}

# === DESPUÉS ===
# Se elimina el dict module-level. Se usa Redis con TTL de 15 min.
# Key: sat_enquiry:result:{job_id}
# TTL: 900s (15 min) — suficiente para descarga, se limpia solo

# === ANTES (líneas 357-363, dentro de event_stream) ===
        excel_bytes = _build_result_excel(rows, results)
        if len(_job_results) >= 5:
            oldest = next(iter(_job_results))
            del _job_results[oldest]
        _job_results[job_id] = excel_bytes
        yield f"data: {json.dumps({'type': 'done', 'job_id': job_id, 'total': total})}\n\n"

# === DESPUÉS ===
        excel_bytes = _build_result_excel(rows, results)
        # Almacenar en Redis con TTL de 15 min
        redis_client.setex(
            f"sat_enquiry:result:{job_id}",
            900,
            excel_bytes,
        )
        # NO exponer job_id en el SSE — usar download_token
        download_token = secrets.token_urlsafe(32)
        redis_client.setex(
            f"sat_enquiry:token:{download_token}",
            900,
            job_id.encode(),
        )
        yield f"data: {json.dumps({'type': 'done', 'download_token': download_token, 'total': total})}\n\n"

# === ANTES (líneas 372-381, endpoint GET) ===
@router.get("/enquiry/batch/{job_id}/result")
def get_batch_result(job_id: str) -> Response:
    excel_bytes = _job_results.pop(job_id, None)
    if not excel_bytes:
        raise HTTPException(status_code=404, detail="Resultado no encontrado o ya descargado")
    return Response(content=excel_bytes, ...)

# === DESPUÉS ===
@router.get("/enquiry/batch/{job_id}/result")
def get_batch_result(download_token: str) -> Response:
    job_id = redis_client.get(f"sat_enquiry:token:{download_token}")
    if not job_id:
        raise HTTPException(status_code=404, detail="Resultado no encontrado o ya descargado")
    job_id = job_id.decode()
    # Operación atómica: leer y borrar
    excel_bytes = redis_client.getdel(f"sat_enquiry:result:{job_id}")
    if not excel_bytes:
        raise HTTPException(status_code=404, detail="Resultado expirado o ya descargado")
    redis_client.delete(f"sat_enquiry:token:{download_token}")
    return Response(content=excel_bytes, ...)
```

**Requisitos previos:** `redis_client` debe ser accesible en `sat_enquiry.py` (verificar importación actual).

**Verificación post-fix:**
```bash
grep -n "_job_results" backend/app/routers/sat_enquiry.py
# Debe devolver 0 resultados (dict eliminado)

grep -n "download_token" backend/app/routers/sat_enquiry.py
# Debe mostrar generación y uso del token
```

**Rollback:** Revertir a dict module-level + `pop()`. Sin riesgo estructural (Redis es acelerador desechable, no fuente de verdad).

---

## PR 2 — HIGH (hallazgos #4, #5, #6, #8, #9, #24, #25, #26)

### Fix #4: Error handling leaks

**Severidad:** HIGH
**Esfuerzo:** 2h
**Riesgo de regresión:** Bajo (solo cambia mensajes de error, no lógica)

**Vulnerabilidad actual:**
~18 sitios exponen `str(exc)` en respuestas HTTP, filtrando URLs internas, paths de filesystem, y detalles de red de Diverza.

**Cambio propuesto — patrón único para todos los sitios:**

```python
# ANTES en todos los sitios:
except AlgunError as exc:
    raise HTTPException(status_code=XXX, detail=str(exc))
# o:
    raise HTTPException(status_code=XXX, detail=f"Error: {exc}")

# DESPUÉS:
except AlgunError as exc:
    sentry_sdk.capture_exception(exc)
    raise HTTPException(status_code=XXX, detail="[mensaje genérico]")
```

**Mapa de archivos y líneas:**

| # | Archivo | Línea | Código actual | Mensaje genérico |
|---|---|---|---|---|
| 1 | `sat_enquiry.py` | 198 | `"error": str(exc)` en dict de batch | `"error": "Error interno al consultar el SAT"` |
| 2 | `sat_enquiry.py` | 303 | `HTTPException(502, f"Error Diverza: {exc}")` | `"Error al consultar el SAT"` |
| 3 | `main.py` | 75 | `JSONResponse(400, {"message": str(exc)})` | `"Error de parámetro inválido"` |
| 4 | `templates.py` | 330 | `HTTPException(500, detail=str(e))` | `"Error interno al procesar plantilla"` |
| 5 | `templates.py` | 354 | `HTTPException(500, detail=str(e))` | `"Error interno al procesar plantilla"` |
| 6 | `templates.py` | 371 | `HTTPException(500, detail=str(e))` | `"Error interno al procesar plantilla"` |
| 7 | `templates.py` | 417 | `HTTPException(500, detail=str(e))` | `"Error interno al procesar plantilla"` |
| 8 | `templates.py` | 439 | `HTTPException(500, detail=str(e))` | `"Error interno al procesar plantilla"` |
| 9 | `templates.py` | 510 | `HTTPException(500, detail=str(e))` | `"Error interno al procesar plantilla"` |
| 10 | `pdf.py` | 174 | `HTTPException(500, detail=str(e))` | `"Error al generar PDF"` |
| 11 | `pdf.py` | 270 | `HTTPException(500, f"Error ZIP: {str(e)}")` | `"Error al leer archivo ZIP"` |
| 12 | `pdf.py` | 677 | `HTTPException(500, f"Error Signed URL: {str(e)}")` | `"Error al generar enlace de descarga"` |
| 13 | `pdf.py` | 714 | `HTTPException(500, f"Error Signed URL: {str(e)}")` | `"Error al generar enlace de subida"` |
| 14 | `batch.py` | 334 | `HTTPException(400, str(e))` | `"Error al procesar archivo batch"` |
| 15 | `rfc_validation.py` | 77 | `str(exc)` en dict de respuesta | `"Error al validar RFC"` |
| 16 | `rfc_validation.py` | 83 | `str(exc)` en dict de respuesta | `"Error al validar RFC"` |
| 17 | `rfc_validation.py` | 109 | `str(exc)` en dict de respuesta | `"Error al validar RFC"` |
| 18 | `rfc_validation.py` | 114 | `str(exc)` en dict de respuesta | `"Error al validar RFC"` |

**Verificación post-fix:**
```bash
grep -rn "str(exc)\|str(e)" backend/app/routers/ backend/app/main.py
# Debe devolver solo usos en logging/Sentry, no en respuestas HTTP
```

**Rollback:** Revertir cada `detail` al `str(exc)` original. Sin riesgo.

---

### Fix #5: Fernet key env var

**Severidad:** HIGH
**Archivos:** `backend/app/credentials.py`, `backend/app/fiel_config.py`, nuevo `backend/app/fernet_utils.py`
**Esfuerzo:** 2h
**Riesgo de regresión:** Medio (cambia cómo se obtiene la key de encriptación)

**Vulnerabilidad actual:**
`_ensure_key()` genera nueva Fernet key en cada cold start de Cloud Run. Emisores configurados desaparecen sin warning. Código duplicado en `credentials.py` y `fiel_config.py`.

**Cambio propuesto — nuevo archivo `backend/app/fernet_utils.py`:**

```python
from __future__ import annotations

import logging
import os
from pathlib import Path

import sentry_sdk
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_SUITE_DIR = Path.home() / ".cfdi-suite"
_KEY_FILE = _SUITE_DIR / "secret.key"


def _ensure_key() -> Fernet:
    """Obtiene la Fernet key. En Cloud Run usa FERNET_KEY env var.
    En desarrollo local usa ~/.cfdi-suite/secret.key (auto-generado)."""
    env_key = os.getenv("FERNET_KEY")
    if env_key:
        return Fernet(env_key.encode())

    _SUITE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    if not _KEY_FILE.exists():
        _KEY_FILE.write_bytes(Fernet.generate_key())
        _KEY_FILE.chmod(0o600)
        logger.info("Nueva Fernet key generada para desarrollo local")
        # Si hay datos previos encriptados con otra key, advertir
        _warn_if_orphan_data()
    else:
        _warn_if_orphan_data()

    return Fernet(_KEY_FILE.read_bytes())


def _warn_if_orphan_data() -> None:
    """Advierte si hay datos encriptados que no podrán leerse con la key actual."""
    for path in [_SUITE_DIR / "emisores.enc", _SUITE_DIR / "fiel.enc"]:
        if not path.exists():
            continue
        try:
            fernet = Fernet(_KEY_FILE.read_bytes() if _KEY_FILE.exists() else b"")
            fernet.decrypt(path.read_bytes())
        except Exception:
            msg = (
                f"Cold start: {path.name} existe pero no se puede descifrar "
                f"con la key actual. Credenciales perdidas — reconfigurar."
            )
            logger.warning(msg)
            sentry_sdk.capture_message(msg, level="warning")
```

**Cambio en `credentials.py`:**

```python
# === ANTES (líneas 14-19) ===
def _ensure_key() -> Fernet:
    _SUITE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not _KEY_FILE.exists():
        _KEY_FILE.write_bytes(Fernet.generate_key())
        _KEY_FILE.chmod(0o600)
    return Fernet(_KEY_FILE.read_bytes())

# === DESPUÉS ===
from .fernet_utils import _ensure_key  # Reemplaza la definición local
```

**Cambio en `fiel_config.py`:**

```python
# === ANTES (líneas 14-19) ===
def _fernet() -> Fernet:
    _SUITE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not _KEY_FILE.exists():
        _KEY_FILE.write_bytes(Fernet.generate_key())
        _KEY_FILE.chmod(0o600)
    return Fernet(_KEY_FILE.read_bytes())

# === DESPUÉS ===
from .fernet_utils import _ensure_key as _fernet  # Reemplaza la definición local
```

**Cambio en `deploy-backend.yml`:** Agregar `FERNET_KEY` como secreto en `--set-secrets` (requiere crear secreto `fernet-key` en GCP Secret Manager).

**Generación única de la key (manual, antes del deploy):**
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Guardar output en GCP Secret Manager:
echo -n "KEY_GENERADA" | gcloud secrets create fernet-key --data-file=- --project=ultra-acre-431617-p0
```

**Verificación post-fix:**
```bash
grep -rn "_ensure_key\|_fernet" backend/app/ --include="*.py"
# Debe mostrar solo importación en credentials.py y fiel_config.py,
# y definición única en fernet_utils.py

grep -rn "_warn_if_orphan_data" backend/app/ --include="*.py"
# Debe mostrar definición + 1 uso en fernet_utils.py
```

**Rollback:** Revertir imports a definiciones locales duplicadas. El código es compatible hacia atrás (cae a archivo local si no hay `FERNET_KEY` env var).

---

### Fix #6: Rate limiting con slowapi

**Severidad:** HIGH
**Archivos:** `backend/requirements.txt`, `backend/app/main.py`, `backend/app/routers/sat_enquiry.py`, `backend/app/routers/batch.py`
**Esfuerzo:** 3h
**Riesgo de regresión:** Bajo (middleware adicional, no modifica lógica existente)

**Vulnerabilidad actual:**
Cero rate limiting en todos los endpoints. Un atacante puede saturar CPU, Redis, Diverza API, GCS y Cloud Tasks sin límite.

**Cambio propuesto — `requirements.txt`:**

```
slowapi>=0.1,<1
```

**Cambio propuesto — `main.py` (después de imports):**

```python
# === NUEVO ===
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    headers_enabled=True,
)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Demasiadas solicitudes. Intenta de nuevo en unos segundos."},
    )

app.add_middleware(SlowAPIMiddleware)
```

**Cambio propuesto — `sat_enquiry.py`:**

```python
# === Agregar al router ===
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/enquiry")
@limiter.limit("20/minute")
async def single_sat_enquiry(request: Request, body: EnquiryRequest):
    ...

@router.post("/enquiry/batch")
@limiter.limit("5/minute")
async def batch_sat_enquiry(...):
    ...
```

**Cambio propuesto — `main.py` (endpoint `/api/cfdi/analyze`):**

```python
@app.post("/api/cfdi/analyze", response_model=AnalyzeCfdiResponse)
@limiter.limit("30/minute")
def analyze_cfdi(request: Request, payload: AnalyzeCfdiRequest) -> AnalyzeCfdiResponse:
    return run_analyze_cfdi(payload.xml)
```

**Límites por endpoint:**

| Endpoint | Límite | Justificación |
|---|---|---|
| `/api/cfdi/analyze` | 30/min | XML individual, operación costosa en CPU |
| `/api/sat/enquiry` | 20/min | Consume créditos Diverza |
| `/api/sat/enquiry/batch` | 5/min | Batch con hasta 500 consultas SAT |
| `/api/cfdi/batch/analyze` | 5/min | ZIP con hasta 500 archivos |
| Default global | 100/min | Todo lo demás |

**Verificación post-fix:**
```bash
grep -rn "@limiter.limit" backend/app/
# Debe mostrar límites en sat_enquiry.py y main.py

for i in $(seq 1 31); do
  curl -X POST https://API_URL/api/cfdi/analyze -d '{"xml":"<test/>"}' &
done
# El request 31 debe recibir HTTP 429
```

**Rollback:** Eliminar decorators `@limiter.limit` y middleware. Sin riesgo.

---

### Fix #8: defusedxml

**Severidad:** HIGH
**Archivos:** `backend/requirements.txt`, `backend/app/routers/batch.py`, `backend/app/services/batch_reports.py`, `backend/wrappers/python-satcfdi-wrapper.py`
**Esfuerzo:** 30 min
**Riesgo de regresión:** Muy bajo (defusedxml es drop-in replacement de stdlib ET)

**Cambio propuesto:**

```python
# === requirements.txt ===
defusedxml>=0.7,<1

# === batch.py (línea 7) ===
# ANTES: import xml.etree.ElementTree as ET
# DESPUÉS:
import defusedxml.ElementTree as ET

# === batch_reports.py (línea 1) ===
# ANTES: import xml.etree.ElementTree as ET
# DESPUÉS:
import defusedxml.ElementTree as ET

# === python-satcfdi-wrapper.py (línea 6) ===
# ANTES: import xml.etree.ElementTree as ET
# DESPUÉS:
import defusedxml.ElementTree as ET
```

**Verificación post-fix:**
```bash
grep -rn "import xml.etree.ElementTree" backend/ --include="*.py"
# Debe devolver 0 resultados (ningún uso directo de stdlib ET)

grep -rn "defusedxml.ElementTree" backend/ --include="*.py"
# Debe devolver 3 resultados
```

**Rollback:** Revertir imports. La API de defusedxml es idéntica a stdlib.

---

### Fix #9: Redis SSL verification

**Severidad:** HIGH
**Archivos:** `backend/app/routers/batch.py`, `backend/app/routers/pdf.py`, `backend/app/workers/batch_shard_worker.py`
**Esfuerzo:** 15 min
**Riesgo de regresión:** Bajo (solo cambia nivel de verificación SSL)

**Vulnerabilidad actual:**
`ssl_cert_reqs=None` en 3 archivos deshabilita verificación de certificado SSL en conexiones a Upstash. MITM posible entre Cloud Run y Redis.

**Cambio propuesto:**

```python
# === batch.py (línea 52) ===
# ANTES:  ssl_cert_reqs=None,
# DESPUÉS: ssl_cert_reqs="required",

# === pdf.py (línea 74) ===
# ANTES:  ssl_cert_reqs=None,
# DESPUÉS: ssl_cert_reqs="required",

# === workers/batch_shard_worker.py (línea 59) ===
# ANTES:  ssl_cert_reqs=None,
# DESPUÉS: ssl_cert_reqs="required",
```

Nota: `batch.py:49` ya tiene `ssl_cert_reqs="required"` — inconsistencia interna del mismo archivo que se corrige.

**Verificación post-fix:**
```bash
grep -rn "ssl_cert_reqs" backend/ --include="*.py"
# Todas las ocurrencias deben decir "required"
# Ninguna debe decir None
```

**Rollback:** Revertir a `None`. Si Upstash tiene certificados que fallan verificación, documentar explícitamente en vez de deshabilitar.

---

### Fix #24: Vercel security headers

**Severidad:** HIGH
**Archivo:** `frontend/vercel.json`
**Esfuerzo:** 15 min
**Riesgo de regresión:** Bajo (headers adicionales, no modifican existentes)

**Vulnerabilidad actual:**
`vercel.json` no define ningún header de seguridad. Sin defensa contra XSS, clickjacking, MIME sniffing.

**Cambio propuesto:**

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app/api/:path*" }
  ],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "SAMEORIGIN" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
        { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" },
        { "key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains; preload" }
      ]
    }
  ]
}
```

Nota: CSP no se incluye en este fix — requiere nonces para `'unsafe-inline'` (effort: medium, PR 4 o long-term).

**Verificación post-fix:**
```bash
curl -I https://cfdiinspector.vercel.app | grep -E "X-Content-Type-Options|X-Frame-Options|Referrer-Policy|Permissions-Policy|Strict-Transport-Security"
# Debe mostrar los 5 headers
```

**Rollback:** Eliminar el array `headers` de `vercel.json`.

---

### Fix #25: GCS CORS wildcard

**Severidad:** HIGH
**Archivo:** `cors-gcs.json`
**Esfuerzo:** 5 min
**Riesgo de regresión:** Bajo (restringe orígenes, no agrega)

**Vulnerabilidad actual:**
`"origin": ["*"]` permite requests CORS desde cualquier dominio al bucket GCS. Combinado con signed URL access_token en query string, un atacante que obtenga una URL firmada puede leer archivos desde cualquier página web.

**Cambio propuesto:**

```json
[
  {
    "origin": ["https://cfdiinspector.vercel.app", "http://localhost:5173"],
    "method": ["PUT", "GET"],
    "responseHeader": ["Content-Type", "Access-Control-Allow-Origin"],
    "maxAgeSeconds": 3600
  }
]
```

**Aplicación del cambio (manual, post-merge):**
```bash
gsutil cors set cors-gcs.json gs://cfdi-suite-uploads-706861124428
```

**Verificación post-fix:**
```bash
gsutil cors get gs://cfdi-suite-uploads-706861124428
# Debe mostrar los orígenes restringidos, no "*"
```

**Rollback:** Revertir a `"*"` en `cors-gcs.json` y re-ejecutar `gsutil cors set`.

> ✅ **ESTADO 2026-07-26 — CERRADO Y APLICADO AL BUCKET.**
>
> Al empezar la Fase 2 el bucket seguía con `origin: ['*']` (verificado en vivo,
> no supuesto). El dueño corrió `gsutil cors set` y quedó:
> ```
> gcloud storage buckets describe gs://cfdi-suite-uploads-706861124428 \
>   --format="value(cors_config)"
> → origin: ['https://cfdiinspector.vercel.app',
>            'http://localhost:3000', 'http://127.0.0.1:3000']
> ```
>
> **Lección para futuros fixes de infra:** editar `cors-gcs.json` no cambia
> nada por sí solo -- GCS no lee ese archivo. El hallazgo se cierra con
> `gsutil cors set`, no con un commit. Al verificar, preguntarle al bucket, no
> al archivo.
>
> `cors-gcs.json` está corregido en el working tree local (de `["*"]` a los 3
> orígenes reales) pero **no se versionó**: está en `.gitignore:46` con el
> comentario deliberado "Config local de CORS para el bucket de GCS, no
> versionar", y nunca estuvo en git. Se respetó esa decisión en vez de forzarla.
>
> **Discrepancia con la spec, gana el código:** la spec propone
> `"http://localhost:5173"` (el puerto por defecto de Vite). Este proyecto corre
> el dev server en **3000** (`"dev": "vite --port=3000"` en
> `frontend/package.json`) y el backend usa
> `"http://localhost:3000,http://127.0.0.1:3000"` como `ALLOWED_ORIGINS` por
> defecto (`main.py:92`). `5173` no aparece en ninguna parte del repo. El
> archivo local usa los mismos orígenes que el backend, para que las dos listas
> digan lo mismo.
>
> Para cerrarlo hace falta un solo comando, y lo corre el dueño:
> ```bash
> gsutil cors set cors-gcs.json gs://cfdi-suite-uploads-706861124428
> ```

---

### Fix #26: Cloud Run service account

**Severidad:** HIGH
**Archivo:** `.github/workflows/deploy-backend.yml`
**Esfuerzo:** 15 min (código) + 1h (setup GCP manual)
**Riesgo de regresión:** Medio (cambia permisos del servicio — puede romper acceso a recursos GCP)

**Vulnerabilidad actual:**
El deploy no especifica `--service-account`. Cloud Run usa la default compute SA con rol `Editor`. Si se explota XXE, el atacante obtiene control de escritura sobre todo el proyecto GCP.

**Cambio propuesto — `deploy-backend.yml` (línea 67):**

```yaml
# === ANTES ===
          flags: |
            --allow-unauthenticated
            --cpu=2
            --memory=2Gi
            --max-instances=10
            --timeout=1800
            --concurrency=5

# === DESPUÉS ===
          flags: |
            --allow-unauthenticated
            --cpu=2
            --memory=2Gi
            --max-instances=10
            --timeout=1800
            --concurrency=5
            --service-account=cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com
```

**Setup manual GCP (antes del merge):**
```bash
# 1. Crear SA
gcloud iam service-accounts create cfdi-suite-api-sa \
  --display-name="Cloud Run API service account" \
  --project=ultra-acre-431617-p0

# 2. GCS — lectura/escritura en bucket específico
gcloud storage buckets add-iam-policy-binding \
  gs://cfdi-suite-uploads-706861124428 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# 3. Cloud Tasks — solo crear tareas
gcloud projects add-iam-policy-binding ultra-acre-431617-p0 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/cloudtasks.enqueuer"

# 4. Cloud Run Jobs — solo ejecutar
gcloud projects add-iam-policy-binding ultra-acre-431617-p0 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# 5. Cloud Trace
gcloud projects add-iam-policy-binding ultra-acre-431617-p0 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/cloudtrace.agent"

# 6. IAM signBlob — para signed URLs
#    ⚠️ VER ABAJO: este comando, tal como está, es una escalada de privilegios.
gcloud projects add-iam-policy-binding ultra-acre-431617-p0 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"

# 7. FALTABA EN LA SPEC — actAs sobre sí misma.
#    Sin esto, Cloud Tasks no puede crear tareas con oidc_token firmado por
#    esta SA y create_task falla con PermissionDenied. Rompe el Fix #2 en su
#    PRIMER deploy (12a), antes de lo que advierte la AMPLIACIÓN.
gcloud iam service-accounts add-iam-policy-binding \
  cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser" \
  --project=ultra-acre-431617-p0
```

> ⚠️ **El comando 6 anula el propósito de este mismo fix. Corregirlo.**
> Detectado el 2026-07-26 al aplicar la Fase 2, después de correr los 7 comandos.
>
> `roles/iam.serviceAccountTokenCreator` **a nivel de proyecto** deja que
> `cfdi-suite-api-sa` genere tokens de acceso para **cualquier** service account
> del proyecto — incluida `706861124428-compute@developer.gserviceaccount.com`,
> que conserva `roles/editor`. O sea: quien comprometa Cloud Run pide un token
> de la compute SA y **recupera Editor sobre todo el proyecto**. Este fix le
> quita el Editor al servicio por la puerta y se lo devuelve por la ventana.
>
> Y ese alcance no hace falta: `pdf.py:624-644` (`_get_signing_credentials`)
> firma con `google.auth.default()` y saca el email del metadata server, así
> que la SA **siempre se firma a sí misma**. Basta el binding sobre sí misma:
>
> ```bash
> gcloud projects remove-iam-policy-binding ultra-acre-431617-p0 \
>   --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
>   --role="roles/iam.serviceAccountTokenCreator"
>
> gcloud iam service-accounts add-iam-policy-binding \
>   cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com \
>   --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
>   --role="roles/iam.serviceAccountTokenCreator" \
>   --project=ultra-acre-431617-p0
> ```
>
> **Estado 2026-07-26: RESUELTO.** Los dos comandos de arriba corrieron.
> Verificado de forma independiente:
> ```
> gcloud projects get-iam-policy ultra-acre-431617-p0 \
>   --flatten="bindings[].members" \
>   --filter="bindings.members:cfdi-suite-api-sa@..." \
>   --format="value(bindings.role)"
> → cloudtasks.enqueuer, cloudtrace.agent, run.invoker   (SIN tokenCreator)
>
> gcloud iam service-accounts get-iam-policy cfdi-suite-api-sa@... \
>   --format="value(bindings.role)"
> → roles/iam.serviceAccountTokenCreator;roles/iam.serviceAccountUser
> ```
> La SA ya no puede pedir tokens de la compute SA, así que #26 por fin hace lo
> que promete: quitarle el Editor al servicio sin devolverlo por otra vía.

**Verificación post-fix:**
```bash
gcloud run services describe cfdi-suite-api --region=us-central1 \
  --format="value(spec.template.spec.serviceAccountName)"
# Debe mostrar: cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com
```

**Rollback:** Quitar `--service-account` del deploy (vuelve a default compute SA). Re-deploy.

---

## PR 3 — CI/CD + SUPPLY CHAIN (hallazgos #7, #20, #27, #28, #29, #32, #34 parcial)

### Fix #7: CI security scanning

**Severidad:** HIGH
**Archivos nuevos:** `.github/workflows/security-scan.yml`, `.github/workflows/codeql.yml`, `.github/dependabot.yml`
**Esfuerzo:** 1h
**Riesgo de regresión:** Nulo (workflows nuevos, no modifican existentes)

**1. `.github/workflows/security-scan.yml`:**

```yaml
name: Security Scan

on:
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - 'frontend/**'
      - '.github/workflows/security-scan.yml'
  pull_request:
    types: [opened, synchronize, reopened]
    paths:
      - 'backend/**'
      - 'frontend/**'
      - '.github/workflows/security-scan.yml'

jobs:
  python-sast:
    name: Python — bandit + safety
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install bandit safety

      - name: Run bandit (static analysis)
        run: |
          bandit -r app/ -ll -f json -o bandit-report.json

      - name: Run safety (dependency vulns)
        run: |
          safety check -r requirements.txt --output json --save-json safety-report.json
        continue-on-error: false

  npm-audit:
    name: Frontend — npm audit
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Run npm audit
        run: npm audit --audit-level=high
```

**2. `.github/workflows/codeql.yml`:**

```yaml
name: CodeQL

on:
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - 'frontend/**'
      - '.github/workflows/codeql.yml'
  pull_request:
    types: [opened, synchronize, reopened]
    paths:
      - 'backend/**'
      - 'frontend/**'
      - '.github/workflows/codeql.yml'
  schedule:
    - cron: '30 2 * * 1'  # Every Monday at 2:30 UTC

jobs:
  analyze:
    name: Analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read

    strategy:
      fail-fast: false
      matrix:
        language: ['python', 'javascript-typescript']

    steps:
      - uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: security-extended,security-and-quality

      - name: Auto-build
        uses: github/codeql-action/autobuild@v3

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
        with:
          category: "/language:${{ matrix.language }}"
```

**3. `.github/dependabot.yml`:**

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "America/Mexico_City"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "security"
    versioning-strategy: "increase"
    reviewers:
      - "gil"
    commit-message:
      prefix: "chore(deps)"
      prefix-development: "chore(deps-dev)"
      include: "scope"

  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "America/Mexico_City"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "security"
    versioning-strategy: "increase"
    reviewers:
      - "gil"
    commit-message:
      prefix: "chore(deps)"
      prefix-development: "chore(deps-dev)"
      include: "scope"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    labels:
      - "dependencies"
      - "ci"
```

---

### Fixes adicionales en PR 3

**#29: Pre-commit hooks** — Crear `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: '\.(lock|json|baseline)$'

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: ['--fix']
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-merge-conflict
      - id: detect-private-key
      - id: check-added-large-files
        args: ['--maxkb=5000']

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        types_or: [javascript, jsx, typescript, tsx, css, json, yaml]
        additional_dependencies: ['prettier@3.4.0']
```

**Instalación (manual, post-merge):**
```bash
pip install pre-commit && pre-commit install
```

**#32: detect-secrets baseline** — Regenerar con:
```bash
detect-secrets scan --all-files --exclude-files ".*\.(lock|json|baseline)$" > .secrets.baseline
detect-secrets audit .secrets.baseline
```

**#28: VERCEL_TOKEN env var** — `deploy-frontend.yml:22`:

```yaml
# === ANTES ===
        run: vercel --prod --token=${{ secrets.VERCEL_TOKEN }}
        env:
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}

# === DESPUÉS ===
        run: vercel --prod
        env:
          VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
```

**#20: Vite console.log** — `frontend/src/main.tsx:18`:

```typescript
// === ANTES ===
console.log("📡 TODAS LAS VARIABLES VISIBLES POR VITE:", (import.meta as any).env);

// === DESPUÉS ===
if (import.meta.env.DEV) {
  console.log("📡 TODAS LAS VARIABLES VISIBLES POR VITE:", (import.meta as any).env);
}
```

**#27/#34: Frontend fixes rápidos:**

```typescript
// frontend/src/pdf-download.ts:308 — quitar fallback hardcodeado
// === ANTES ===
const key = (import.meta as any).env.VITE_PUSHER_KEY || 'ec582a031473e2da1654';

// === DESPUÉS ===
const key = (import.meta as any).env.VITE_PUSHER_KEY;
if (!key) throw new Error("VITE_PUSHER_KEY no configurada");
```

```json
// frontend/package.json — agregar script audit
"scripts": {
  "audit": "npm audit --audit-level=high",
  "audit:fix": "npm audit fix"
}
```

---

## PR 4 — MEDIUM + LOW (hallazgos #10, #11, #15, #16, #17, #19, #22, #23, #30, #31, #33, #34 resto)

### Fix #10: Excel formula injection

**Severidad:** MEDIUM
**Archivo:** `backend/app/routers/sat_enquiry.py` (función `_build_result_excel`)
**Esfuerzo:** 30 min

**Cambio propuesto:**
```python
# === ANTES (línea 261) ===
        ws.append(
            [
                row["uuid"],
                row["rfc_emisor"],
                row["rfc_receptor"],
                row["motive"],
                r.get("estado", ""),
                r.get("es_cancelable", ""),
                r.get("estatus_cancelacion", ""),
                now,
                r.get("error", "") or "",
            ]
        )

# === DESPUÉS ===
        def _sanitize_xlsx(val: str) -> str:
            """Previene Excel formula injection."""
            if not val or not isinstance(val, str):
                return str(val) if val else ""
            if val.startswith(("=", "+", "-", "@")):
                return "'" + val
            return val

        ws.append(
            [
                _sanitize_xlsx(row["uuid"]),
                _sanitize_xlsx(row["rfc_emisor"]),
                _sanitize_xlsx(row["rfc_receptor"]),
                _sanitize_xlsx(row["motive"]),
                _sanitize_xlsx(r.get("estado", "")),
                _sanitize_xlsx(r.get("es_cancelable", "")),
                _sanitize_xlsx(r.get("estatus_cancelacion", "")),
                now,
                _sanitize_xlsx(r.get("error", "") or ""),
            ]
        )
```

---

### Fix #15: Race condition batch TTL

**Severidad:** MEDIUM
**Archivo:** `backend/app/routers/batch.py` (líneas 116-123)
**Esfuerzo:** 30 min

```python
# === ANTES ===
redis_client.hmset(hash_key, data)
redis_client.expire(hash_key, REDIS_TTL)

# === DESPUÉS ===
# Usar pipeline para atomicidad
pipe = redis_client.pipeline()
pipe.hmset(hash_key, data)
pipe.expire(hash_key, REDIS_TTL)
pipe.execute()
```

---

### Fix #16/#34: Hash pinning en requirements.txt

**Severidad:** MEDIUM/LOW
**Archivo:** `backend/requirements.txt`
**Esfuerzo:** 1h

```bash
# Generar hashes para todos los paquetes
pip install pip-tools
pip-compile --generate-hashes requirements.in -o requirements.txt

# O alternativamente, agregar --hash manualmente a los paquetes críticos:
# lxml, redis, cryptography, pusher, sentry-sdk, openpyxl
```

---

### Fix #17: SRI hashes

> ## ⛔ OBSOLETA — no aplicar (marcada en Fase 1, 2026-07-26)
>
> **Motivo:** la spec asume un `<script>` de CDN que **no existe**.
> `frontend/index.html` tiene exactamente una etiqueta script, y es el entrypoint
> de Vite:
>
> ```bash
> grep -n "<script" frontend/index.html
> # 10:    <script type="module" src="/src/main.tsx"></script>
> ```
>
> `pusher-js` y `@sentry/react` son dependencias de npm (`frontend/package.json`)
> que Vite empaqueta en el bundle. No se cargan desde `js.pusher.com` ni desde
> ningún CDN, así que **no hay superficie donde poner un hash SRI**.
>
> El riesgo que #17 quería cubrir (compromiso de un CDN) no aplica; el que sí
> aplica —compromiso de un paquete de npm— lo cubren #7 (escaneo en CI) y
> #16/#34 (pinning). **No se borra la spec: se marca, con el comando que lo
> demuestra.** Si algún día se agrega un `<script src="https://…">` al HTML,
> esta spec vuelve a ser válida tal cual está escrita abajo.

*Contenido original, conservado por historia:*

**Severidad:** LOW
**Archivo:** `frontend/index.html`
**Esfuerzo:** 30 min

```bash
# Generar hashes:
curl -s https://js.pusher.com/8.0/pusher.min.js | openssl dgst -sha384 -binary | openssl base64 -A
```

```html
<script src="https://js.pusher.com/8.0/pusher.min.js"
        integrity="sha384-[HASH_GENERADO]"
        crossorigin="anonymous"></script>
```

---

### Fix #19: CORS allow_methods

**Severidad:** LOW
**Archivo:** `backend/app/main.py` (línea 98)
**Esfuerzo:** 5 min

```python
# === ANTES ===
    allow_methods=["*"],

# === DESPUÉS ===
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
```

---

### Fix #22: PUSHER_KEY/VERCEL_URL a vars

**Severidad:** LOW
**Archivo:** `.github/workflows/deploy-backend.yml` (líneas 44, 52)
**Esfuerzo:** 15 min código + GitHub Settings manual

```yaml
# === ANTES ===
            ALLOWED_ORIGINS=${{ secrets.VERCEL_URL }}
            ...
            PUSHER_KEY=${{ secrets.PUSHER_KEY }}

# === DESPUÉS ===
            ALLOWED_ORIGINS=${{ vars.VERCEL_URL }}
            ...
            PUSHER_KEY=${{ vars.PUSHER_KEY }}
```

Luego mover `VERCEL_URL` y `PUSHER_KEY` de Secrets a Variables en GitHub Settings.

---

### Fix #23: Cloud Run timeout

**Severidad:** LOW
**Archivo:** `.github/workflows/deploy-backend.yml` (línea 65)
**Esfuerzo:** 5 min

```yaml
# === ANTES ===
            --timeout=1800

# === DESPUÉS ===
            --timeout=600
```

> ⛔ **NO APLICADO — decisión del dueño, 2026-07-26. El timeout no es la
> palanca.**
>
> El trabajo que corre dentro de un request de este servicio **no tiene cota
> superior conocida**: puede ser un ZIP de un millón de XMLs, o muchas
> solicitudes grandes a la vez. Ningún número fijo resuelve eso — 600 corta
> trabajo legítimo y 1800 tampoco detiene a un atacante, sólo le pone un techo
> arbitrario más alto.
>
> Y hay evidencia medida de que 600 rompe producción: `PROJECT_STATE.md:972`
> documenta una extracción **real** de 2000 XMLs que tardó **10 minutos** (600s
> exactos) saturando la red de la instancia todo ese tiempo, en un solo
> request. El corte quedaría justo encima de un caso observado.
>
> Lo que sí acota de verdad, y son fixes de esta misma fase:
> - **`### Fix #44`** (paso 31) — límite de tamaño por archivo en `batch_analyze`.
> - **`### Fix #43`** (paso 30) — validación de MIME/magic bytes en uploads.
> - Sacar el trabajo largo del request hacia el Cloud Run Job `cfdi-batch-shard`,
>   que ya existe (`BATCH_JOB_THRESHOLD`).
>
> `--timeout=1800` se deja como está, en `deploy-backend.yml:66` y en
> `cloudbuild.yaml:23`. Si algún día se toca, hay que tocarlo en los **dos**:
> `cloudbuild.yaml:34-36` documenta que divergir entre los dos pipelines ya
> causó incidentes.

---

### Fix #30: Secretos en --set-secrets

**Severidad:** MEDIUM
**Archivo:** `.github/workflows/deploy-backend.yml`
**Esfuerzo:** 1h código + setup Secret Manager

```yaml
# === ANTES ===
          env_vars: |
            ...
            REDIS_PASSWORD=${{ secrets.REDIS_PASSWORD }}
            ...
            PUSHER_SECRET=${{ secrets.PUSHER_SECRET }}

# === DESPUÉS (mover a --set-secrets) ===
          env_vars: |
            ...
            # REDIS_PASSWORD y PUSHER_SECRET se pasan vía --set-secrets
            ...
          secrets: |
            REDIS_PASSWORD=redis-password:latest
            PUSHER_SECRET=pusher-secret:latest
```

Requisito: crear secretos `redis-password` y `pusher-secret` en GCP Secret Manager.

---

### Fix #31: Batch shard job SA

**Severidad:** MEDIUM
**Archivo:** `infra/deploy-batch-shard-job.sh`
**Esfuerzo:** 1h

```bash
# === ANTES (línea 56-66) ===
gcloud run jobs deploy "${JOB_NAME}" \
  --cpu=1 \
  --memory=2Gi \
  --task-timeout=600 \
  --max-retries=1 \
  --set-env-vars="..."

# === DESPUÉS ===
gcloud run jobs deploy "${JOB_NAME}" \
  --cpu=1 \
  --memory=2Gi \
  --task-timeout=600 \
  --max-retries=1 \
  --service-account=cfdi-batch-shard-sa@ultra-acre-431617-p0.iam.gserviceaccount.com \
  --set-secrets="REDIS_PASSWORD=redis-password:latest,PUSHER_APP_ID=pusher-app-id:latest,PUSHER_KEY=pusher-key:latest,PUSHER_SECRET=pusher-secret:latest"
```

---

### Fix #33: npm audit roto

**Severidad:** LOW
**Archivo:** N/A (investigación)
**Esfuerzo:** 30 min

Diagnóstico: el registry de npm devuelve JSON inválido al ejecutar `npm audit`. Posibles causas:
1. Proxy corporativo que modifica la respuesta
2. Versión de npm incompatible con el registry
3. Problema de red transitorio

Pasos de diagnóstico:
```bash
npm config get registry
curl -s https://registry.npmjs.org/ | head -c 200
npm --version
npm audit --prefer-online
```

---

### Fix #11: SSTI audit

**Severidad:** MEDIUM
**Esfuerzo:** 3h (investigación, no fix directo)

Auditar la ruta de renderizado de templates WeasyPrint en `canvas_service.py`. Verificar si la interpolación usa `str.format()` con user input. Si es vulnerable, migrar a renderizado paramétrico.

---

## Resumen de esfuerzo

| PR | Fixes | Esfuerzo código | Setup manual | Total |
|---|---|---|---|---|
| PR 1 | #1, #2, #3 | 5.5h | 0 | 5.5h |
| PR 2 | #4, #5, #6, #8, #9, #24, #25, #26 | 9h | 1h (GCP SA setup) | 10h |
| PR 3 | #7, #20, #27, #28, #29, #32, #34-parcial | 5h | 2h (registrar workflows, branch protection) | 7h |
| PR 4 | #10, #11, #15, #16, #17, #19, #22, #23, #30, #31, #33, #34-resto | 10.5h | 1h (GitHub Settings: vars migration) | 11.5h |
| **Total** | **34** | **30h** | **4h** | **~34h** |

---

## Dependencias entre PRs

```
PR 2 (HIGH)
  ├── Fix #26: Crea SA cfdi-suite-api-sa ──► PR 1 Fix #2 la usa para OIDC
  ├── Independiente del resto

PR 1 (CRITICAL)
  ├── Fix #2 depende de PR 2 (SA debe existir)
  ├── Fix #1 y #3 son independientes

PR 3 (CI/CD)
  └── Totalmente independiente

PR 4 (MEDIUM/LOW)
  └── Totalmente independiente
```

**Orden recomendado de merge:** PR 2 → PR 1 → PR 3 → PR 4

---

## Verificación global post-implementación

Al completar los 4 PRs, ejecutar:

```bash
# 1. Re-ejecutar los 4 agentes de seguridad
# (desde Claude Code):
#   /security-frontend
#   /security-backend
#   /security-infra
#   /security-secrets

# 2. Verificar que los 34 hallazgos pasan de OPEN a FIXED
grep -c "OPEN" docs/seguridad/08-auditoria-actual.md
# Debe devolver 0

# 3. Actualizar living document
# Fecha de última verificación: [fecha del último PR mergeado]
# Todos los estados: FIXED

# 4. Deploy a producción
git push  # Dispara deploy-backend.yml y deploy-frontend.yml

# 5. Verificar deploy
curl -s https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app/health
curl -s -I https://cfdiinspector.vercel.app | grep -E "X-Content-Type-Options|X-Frame-Options"

# 6. OWASP ZAP baseline scan contra staging
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app \
  -z "-config api.disablekey=true" \
  -r zap-report.html
```

> **Nota Fase 1 (2026-07-26):** el paso 2 de esta verificación global
> (`grep -c "OPEN" 08-auditoria-actual.md` → 0) ya no es alcanzable con los 4 PRs
> originales: el registro creció de 34 a 160 hallazgos y hay hallazgos que
> quedan deliberadamente fuera de alcance (ver "Qué queda fuera" más abajo).
> No es un criterio de aceptación válido; se conserva por historia.

---
---

# Fase 1 — Reconciliación semántica, subsunción y decisión de auth

> Fecha: 2026-07-26
> Entrada: `registro-unificado.md` (160 hallazgos, generado por `scripts/reconcile_registry.py`)
> Todo lo de abajo es **incremental**. Nada de las 29 specs anteriores se borró.

---

## Hechos de producción verificados en esta fase

Estos no estaban en ningún doc y cambian el análisis. Se verificaron contra
producción y contra el bundle desplegado, no contra la columna "Estado" de nadie.

| # | Hecho | Cómo se verificó |
|---|---|---|
| P1 | **El rewrite de `vercel.json` está muerto para la mayor parte del tráfico.** `VITE_API_BASE_URL` **sí está configurada en Vercel Production** con el valor `https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app`. Vite la hornea en build time, así que todo call site que use `resolveApiBaseUrl()` habla **directo con Cloud Run**, cross-origin, sin pasar por Vercel. | `vercel env ls` + `vercel env pull` |
| P2 | La URL de Cloud Run aparece **4 veces** en el bundle de producción servido por `cfdiinspector.vercel.app`. No es un fallback teórico: es el camino real. | `curl .../assets/index-*.js \| grep -c "…run.app"` → 4 |
| P3 | Cloud Run responde **anónimo** a cualquiera en internet: `GET /openapi.json` → 200, `GET /api/emisores` → 200. La superficie completa de la API está publicada y auto-documentada. | `curl -o /dev/null -w '%{http_code}'` contra ambas URLs |
| P4 | `VITE_PUSHER_KEY` y `VITE_PUSHER_CLUSTER` están en Vercel Production con valor **cadena vacía**. El `||` de `pdf-download.ts:308` las trata como falsy → **la key hardcodeada es la que corre en producción** (3 ocurrencias en el bundle). El override que el comentario del código promete no funciona. | `vercel env pull` + `grep -c` sobre el bundle |
| P5 | `ssl_cert_reqs=None` en **los tres** sitios (`batch.py:52`, `pdf.py:74`, `batch_shard_worker.py:59`). **No existe** el `"required"` de `batch.py:49` que afirma el hallazgo #21. | `grep -rn "ssl_cert_reqs" --include="*.py" .` |
| P6 | `POST /api/cfdi/batch/worker-task` (`batch.py:210`) no tiene **ninguna** verificación — ni el header check débil que sí tienen los dos endpoints de `pdf.py`. | `grep -n "x-cloudtasks" backend/app/routers/batch.py` → sin resultados |
| P7 | El motor `pythonSatcfdiEngine` (subprocess con `pythonBinary`/`wrapperPath`) **no entra al bundle**: su único importador es `src/cfdi/benchmark/runBenchmark.ts`, un script de Node. `pythonBinary` y `child_process` tienen 0 ocurrencias en el bundle desplegado. | `grep -rn pythonSatcfdiEngine src/` + `grep -c` sobre el bundle |
| P8 | Cero `Depends()` en todo `backend/app/`. No hay ni el esqueleto de un sistema de identidad. | `grep -rc "Depends(" backend/app/` → 0 |

**P1 es el hecho que reordena la Tarea 2.** El diagrama mental "navegador →
Vercel → Cloud Run" es falso para las rutas que más datos mueven. Hoy hay **dos
caminos vivos y divergentes** hacia el mismo backend:

| Camino | Call sites | Pasa por Vercel |
|---|---|---|
| Absoluto (`resolveApiBaseUrl()` → URL de Cloud Run) | `BatchAnalysisPage.tsx:770,864,1150`, `cfdi-api-client.ts:49`, `pdf-download.ts:198,238,310,355,437,457,463,472,484` | **No** |
| Relativo (`/api/...` literal) | `App.tsx:250,259,276`, `batch-api-client.ts:46,156`, `sat-enquiry-api-client.ts:22,39,61`, `rfc-validation-api-client.ts:23,55`, `emisores-api-client.ts:19`, `PdfTemplateBuilder.tsx:109` | Sí |

El prompt de Fase 1 pedía enumerar "cuántos call sites se saltan el rewrite".
La respuesta no es 1 (`BatchAnalysisPage.tsx:160`): son **tres módulos y ~13
call sites**, porque la variable de entorno de Vercel activa el camino absoluto
en los tres. `BatchAnalysisPage.tsx:160` es sólo el único que además tiene la
URL escrita a mano en el fuente versionado.

### ¿Puede un rewrite de `vercel.json` inyectar una credencial upstream?

**No.** Un `rewrite` es enrutamiento de CDN: acepta `source`, `destination`,
`has`/`missing`. La clave `headers` de `vercel.json` define **headers de
respuesta**, no del request upstream. Para adjuntar un `Authorization` hace
falta cómputo: Routing Middleware (`middleware.ts` en la raíz del proyecto —
sí funciona en un SPA de Vite, es una feature de plataforma, no de Next.js) o
una Vercel Function. Hoy no existe ninguno de los dos (`ls frontend/middleware.ts
frontend/api/` → nada).

Y ese cómputo trae un límite duro: **Routing Middleware topa el body del request
en 4 MB** (Vercel Functions, ~4.5 MB). `POST /api/cfdi/batch/analyze` sube hasta
500 XMLs en un multipart — el backend incluso sube `MultiPartParser.max_part_size`
a 100 MB (`main.py:38`). Meter ese tráfico por cómputo de Vercel **rompe la
funcionalidad principal del producto**. Es la razón técnica, no de gusto, por la
que la opción (A2) se rechaza abajo.

---

## Tarea 1 — Dedup semántico

Un defecto, una fila. La columna "gana" dice qué severidad sobrevive al colapso.

| Fila superviviente | Absorbe | Evidencia del colapso | Gana |
|---|---|---|---|
| **#45** Batch status sin auth | `B7-BE-AUTH-01` | mismo `batch.py:183` | **HIGH** (panel unánime) sobre MEDIUM (etiqueta de scanner) |
| **#2** Cloud Tasks sin OIDC | `BATCH6-CANDIDATE-02`, `BATCH6-CANDIDATE-04` | el texto de #2 ya nombra `batch.py:301`; -04 es el mismo endpoint alcanzable vía el rewrite | CRITICAL |
| **#4** Error details leaked | `B8-FINDINGS-AUTH-01`, `B8-FINDINGS-AUTH-02`, `B8-BATCH-AUTH-01`, `B7-BE-AUTH-02..05`, `B7-CFDI-AUTH-03`, `B7-CFDI-AUTH-06`, `B7-HOOKS-AUTH-01..03`, `B7-HOOKS-AUTH-05` | mismo defecto (`str(exc)` cruza a la respuesta/DOM) en 14 sitios, backend y frontend | HIGH |
| **#10** Excel/CSV formula injection | `#46`, `B7-HOOKS-INJ-01`, `B8-EXTW-INJ-01`, `B8-FINDINGS-INJ-01`, `B8-FINDINGS-INJ-03`, `B7-UI-AUTH-01`, `BATCH6-CANDIDATE-06`, `BATCH6-CANDIDATE-15` | mismo defecto (falta guardia de `= + - @`) en XLSX del backend, `escapeCsv` del frontend y clipboard | MEDIUM |
| **#8** `ET.fromstring` sin defusedxml | `B7-BE-INJ-01`, `BATCH6-CANDIDATE-25` | mismos archivos ya listados en #8 | HIGH |
| **#9** Redis `ssl_cert_reqs=None` | **#21** | ver P5: #21 describe una inconsistencia que **no existe**; los tres sitios son `None` | HIGH; #21 se cierra como *stale*, no como fix |
| **#16/#34** Supply chain | `B7-CI-CRYPTO-02`, `#49` | hash pinning de pip, mismo defecto en `requirements.txt` y en `Dockerfile:20` | MEDIUM |
| **#20** `console.log` en prod | `#60`, `B8-SHELL-AUTH-01`, `B8-BATCH-CRYPTO-01` | mismo defecto en `main.tsx:18`, `BatchAnalysisPage.tsx:161`, `pdf-download.ts:8` | LOW |
| **#27** Pusher key hardcodeada | `B7-CI-CRYPTO-04`, `B8-SHELL-CRYPTO-01` | mismo patrón `env || 'literal'`; el DSN de Sentry es el mismo defecto que la key de Pusher | MEDIUM (ver P4) |
| **#61** URL de Cloud Run hardcodeada | `BATCH6-CANDIDATE-32` | mismo literal, `vercel.json:5` y `BatchAnalysisPage.tsx:160` | LOW |
| **#62** Path traversal `template_id` | `TEMPLATE-PATH-TRAVERSAL-01` | ambos rechazados por panel, ambos reclasificados LOW | LOW (hardening) |
| **#56** merge vs overwrite | `BATCH6-CANDIDATE-20` | mismo `cloudbuild.yaml` vs `deploy-backend.yml` | LOW |
| **#12** Pusher canales públicos | `BATCH6-CANDIDATE-18` | mismo `pdf-download.ts:412` | MEDIUM |
| **#13** `access_token` en query de signed URL | `BATCH6-CANDIDATE-31` | mismo `pdf.py:668` | MEDIUM |
| **#28** `VERCEL_TOKEN` como flag | `B7-CI-CRYPTO-06` | mismo `deploy-frontend.yml:22` | MEDIUM |
| **#32** baseline stale | `B7-CI-AUTH-04`, `B7-CI-CRYPTO-10` | mismo `.secrets.baseline` con entradas huérfanas | LOW |
| **#57** filename sin sanitizar → GCS | `BATCH6-CANDIDATE-09` | mismo `batch.py:137` | LOW |
| **NUEVO-BATCHID** Validación de forma de `batch_id`/`job_id` | `B8-SHELL-INJ-01`, `B8-SHELL-INJ-03`, `B8-BATCH-INJ-01`, `BATCH6-CANDIDATE-29` | un solo defecto: identificadores no validados como UUID antes de entrar a URLs y a nombres de canal Pusher. Cuatro scanners lo vieron en cuatro archivos | LOW; se resuelve con **un** guard compartido |
| **NUEVO-NAN** Números no finitos desde XML no confiable | `B8-FINDINGS-INJ-02`, `B8-XML-INJ-01`, `B8-XML-INJ-02`, `B8-XML-INJ-03`, `B7-CFDI-INJ-02`, `B7-CFDI-INJ-03` | `parseFloat` sin `Number.isFinite` en 6 sitios | LOW; es robustez, no seguridad (ver triage G7) |
| **NUEVO-DEVTOOLS** Datos sensibles en estado de React | `B7-HOOKS-AUTH-04`, `B8-SHELL-AUTH-04`, `BATCH6-CANDIDATE-16`, `BATCH6-CANDIDATE-17` | mismo modelo de amenaza (atacante con acceso al navegador de la víctima) | LOW; ver triage G6 |
| **#5** Fernet key | `BATCH6-CANDIDATE-11`, `-21`, `-22`, `-23`, `-24` | todos son `fiel_config.py`/`credentials.py`: misma llave, mismo tmpfs, mismas races | MEDIUM |

**Contradicciones que se dejan anotadas, no resueltas** (el veredicto del panel
manda; el modelo no recalifica lo que votó el panel):

- `B7-CI-INJ-01` (opentelemetry sin pin) fue **rechazado 1/3**, mientras que
  `B7-CI-CRYPTO-09` describe el mismo defecto y nunca pasó por panel. Gana el
  panel: el defecto se trata como higiene de dependencias dentro de #16/#34, no
  como hallazgo propio.
- `B7-CFDI-INJ-01` (XXE en `python-satcfdi-wrapper.py:406`) fue **rechazado 0/3**,
  pero ese mismo archivo está listado dentro de #8, que sigue OPEN y con spec.
  Se aplica el fix de #8 al archivo — no porque el hallazgo de batch sobreviva,
  sino porque #8 nunca fue refutado y el costo es una línea de import.

---

## Tarea 1 — Árbol de subsunción

Regla: **un hijo no se agenda antes que su padre.** Arreglar un hijo mientras el
padre vive es trabajo que no cambia el riesgo.

```
PADRE-AUTH — BATCH6-CANDIDATE-01: la API entera (~30+ endpoints) sin autenticación
│            [CRITICAL, panel unánime] · backend/app/main.py:55 · 0 Depends() en todo backend/app/
│
├── BATCH6-CANDIDATE-03  Emisor CRUD sin auth            [CRITICAL, unánime]
├── B8-XML-AUTH-02       Cliente emisores sin auth       [HIGH, mayoría]  (cara frontend del anterior)
├── BATCH6-CANDIDATE-05  Batch SAT enquiry sin auth      [HIGH, unánime]
├── B8-SHELL-AUTH-02     URL ?batch=<id> como único token[HIGH, mayoría]
├── #45 / B7-BE-AUTH-01  Batch status sin auth           [HIGH, unánime]
├── #36                  FIEL usado sin auth contra SAT  [→ recalibrado HIGH]
├── #37                  FIEL sobrescribible/borrable    [→ recalibrado HIGH]
├── #12                  Pusher canales públicos         [MEDIUM]
├── B8-SHELL-AUTH-03     SSE sin validación de sesión    [MEDIUM, mayoría]
├── BATCH6-CANDIDATE-07  Resultado SAT enquiry sin auth  [MEDIUM]
├── BATCH6-CANDIDATE-08  /api/cfdi/analyze sin auth      [MEDIUM]
├── BATCH6-CANDIDATE-13  /api/fiel/status expone RFC     [MEDIUM]
├── BATCH6-CANDIDATE-19  URL de lote compartible         [MEDIUM]
└── #6                   Cero rate limiting              [HIGH]  ← hermano, no hijo:
                         se puede aplicar por IP sin identidad, pero sólo
                         adquiere sentido pleno cuando hay a quién limitar.

PADRE-INTERNO — #2: endpoints internos sin OIDC
│               [CRITICAL, panel] · task_dispatcher.py + pdf.py + batch.py
├── BATCH6-CANDIDATE-02  /api/cfdi/batch/worker-task, cero verificación [CRITICAL, unánime]
└── BATCH6-CANDIDATE-04  el rewrite de Vercel hace same-origin lo interno [HIGH, unánime]

PADRE-ERRLEAK — #4: detalles de excepción en respuestas   (14 hijos, ver dedup)
PADRE-FORMULA — #10: inyección de fórmulas                (8 hijos, ver dedup)
PADRE-XML     — #8: XML sin defusedxml                    (2 hijos)
PADRE-SUPPLY  — #16/#34: sin hash pinning                 (#47, #49, #53, B7-CI-CRYPTO-02/05/08/09, B7-CI-INJ-02)
PADRE-CI      — #7: cero escaneo de seguridad en CI       (B7-CI-AUTH-01..06, B7-CI-INJ-03, #29, #32)
PADRE-FERNET  — #5: gestión de la llave Fernet            (BATCH6-CANDIDATE-11/21/22/23/24)
PADRE-CONSOLE — #20: console.log en producción            (#60, B8-SHELL-AUTH-01, B8-BATCH-CRYPTO-01)
PADRE-DOCKER  — #42/#47/#48/#49/#50/#53/#54: imagen        (sin padre único; se agrupan por PR)
```

**Dónde chocan severidad y dependencia** — la regla dice que gana la dependencia,
y aquí es donde ocurre:

1. **`BATCH6-CANDIDATE-03` es CRITICAL y no se toca en Fase 2.** Es hijo directo
   de PADRE-AUTH. "Poner auth al CRUD de emisores" sin un sistema de identidad
   significa inventar uno ad-hoc en un router, que es exactamente la deuda que
   este proceso quiere evitar. Espera a B-lite.
2. **#36/#37 se recalibran a HIGH y aun así no se tocan en Fase 2.** Misma razón:
   el fix real es identidad, no un parche en `rfc_validation.py`.
3. **#6 (rate limiting, HIGH) va después de fixes LOW mecánicos.** No por
   severidad sino porque `slowapi` sobre una API sin identidad limita por IP, y
   la mitad del tráfico llega por el CDN de Vercel (IP compartida) y la otra
   mitad directo a Cloud Run (IP real). Sin resolver P1 primero, el rate limit
   se aplica de forma asimétrica y desigual entre los dos caminos.
4. **#2 (CRITICAL) depende de #26 (HIGH)**, que crea la SA. Esa dependencia ya
   estaba documentada y sigue vigente.

---

## Tarea 1 — Triage por grupo de los 58 sin panelear

Ninguno de estos se declara verificado. Eso lo computa `scripts/verify.py`
contando votos, no un modelo. Cada grupo sale por una de tres puertas:
**subsumido** (nombra al padre), **merece panel**, o **cerrable sin panel**.

| G | Grupo | Ids | Salida |
|---|---|---|---|
| G1 | Excepción cruda al cliente | `B7-BE-AUTH-02,03,04,05`, `B7-CFDI-AUTH-03,06`, `B7-HOOKS-AUTH-01,02,03,05` (10) | **Subsumido** por #4. El padre ya está verificado como HIGH; panelear a los hijos no cambia nada. |
| G2 | Inyección de fórmulas | `BATCH6-CANDIDATE-06`, `BATCH6-CANDIDATE-15` (2) | **Subsumido** por #10. |
| G3 | Endpoints sin auth | `BATCH6-CANDIDATE-07,08,13,19` (4) | **Subsumido** por PADRE-AUTH (`BATCH6-CANDIDATE-01`, unánime). |
| G4 | Rate limiting | `BATCH6-CANDIDATE-14` (1) | **Subsumido** por #6. |
| G5 | Llave Fernet y races de credenciales | `BATCH6-CANDIDATE-11,21,22,23,24` (5) | **Subsumido** por #5. |
| G6 | Llave Fernet compartida FIEL↔PAC | `BATCH6-CANDIDATE-12` (1) | **Merece panel.** Se separa de G5 a propósito: no es una race, es una decisión de diseño criptográfico (una sola llave protege material de e.firma y credenciales de PAC). Que sea o no un hallazgo real depende del modelo de amenaza, y eso es exactamente lo que vota un panel. |
| G7 | Estado sensible en React | `B7-HOOKS-AUTH-04`, `BATCH6-CANDIDATE-16,17` (3) | **Merece panel.** El modelo de amenaza es "atacante con acceso al navegador de la víctima". Si eso se acepta como amenaza, media docena de hallazgos LOW cambian; si no, se cierran juntos. No lo decide un modelo. |
| G8 | Inyección en headers de respuesta | `BATCH6-CANDIDATE-09,10` (2) | **Merece panel.** `-10` (`rfc_presentante` sin sanitizar en `Content-Disposition`, `batch.py:339`) es CRLF/header injection potencialmente real y ningún panel lo ha visto. `-09` es el mismo input hacia rutas de GCS (= #57). |
| G9 | Números no finitos desde XML | `B7-CFDI-INJ-02,03`, `BATCH6-CANDIDATE-26` (3) | **Cerrable sin panel.** `NaN`/`Infinity` propagados a una tabla que el propio usuario subió no cruzan frontera de confianza: el atacante y la víctima son la misma persona. Es un bug de robustez de UI. Se documenta como deuda de calidad, no de seguridad. |
| G10 | Opciones de engine con subprocess | `B7-CFDI-AUTH-01,02` (2) | **Cerrable sin panel.** P7: `pythonSatcfdiEngine` sólo lo importa `runBenchmark.ts` (script de Node); `pythonBinary` y `child_process` tienen 0 ocurrencias en el bundle desplegado. No hay superficie en producción. |
| G11 | Validación de esquema en eventos | `BATCH6-CANDIDATE-27` (1) | **Cerrable sin panel.** Subsumido de facto por NUEVO-BATCHID: validar la forma del identificador es el guard que importa; el resto es `try/catch` alrededor de un `JSON.parse`. |
| G12 | Uploads sin MIME | `BATCH6-CANDIDATE-28` (1) | **Subsumido** por #43. |
| G13 | Permisos y gates de CI | `B7-CI-AUTH-01,02,03,05,06`, `B7-CI-INJ-03` (6) | **Subsumido** por #7 (+#29). `B7-CI-AUTH-06` (`--allow-unauthenticated`) es además la cara CI de la decisión de arquitectura de abajo, y muere o sobrevive con ella. |
| G14 | Baseline de detect-secrets | `B7-CI-AUTH-04`, `B7-CI-CRYPTO-10` (2) | **Subsumido** por #32. |
| G15 | Pinning de dependencias e imágenes | `B7-CI-CRYPTO-05,08,09`, `B7-CI-INJ-02` (4) | **Subsumido** por #16/#34 y #47. |
| G16 | Secretos en pipeline | `B7-CI-CRYPTO-06` (1) | **Subsumido** por #28. |
| G17 | Reconocimiento en scripts de infra | `B7-CI-CRYPTO-07` (1) | **Cerrable sin panel.** Nombres de proyecto, región y bucket ya están en `deploy-backend.yml` versionado y en `vercel.json`. No hay secreto que proteger; es seguridad por oscuridad. |
| G18 | Pragma de allowlist sobre key de Pusher | `B7-CI-CRYPTO-04` (1) | **Subsumido** por #27, con corrección: el pragma es **correcto** (la key de Pusher es pública por diseño), pero P4 muestra que el override de Vercel está vacío, así que el literal es lo que corre. Lo que hay que arreglar es la variable, no el pragma. |
| G19 | Divergencia entre pipelines | `BATCH6-CANDIDATE-20` (1) | **Subsumido** por #56. |
| G20 | Proxy de Vite / CORS en dev | `BATCH6-CANDIDATE-30` (1) | **Cerrable sin panel.** `vite.config.ts` no se despliega; `changeOrigin` sólo aplica al dev server local. |
| G21 | Signed URL con token en query | `BATCH6-CANDIDATE-31` (1) | **Subsumido** por #13 (+#25). |
| G22 | URL de Cloud Run en fuentes versionados | `BATCH6-CANDIDATE-32` (1) | **Subsumido** por #61. |
| G23 | `batch_id` sin validar hacia URLs y canales | `BATCH6-CANDIDATE-29` (1) | **Subsumido** por NUEVO-BATCHID. |
| G24 | Clipboard con valores de XML | `B7-UI-AUTH-01` (1) | **Subsumido** por #10 (es el mismo defecto que `B8-FINDINGS-INJ-01`, que sí tiene panel unánime). |
| G25 | XML del wrapper sin defusedxml | `BATCH6-CANDIDATE-25` (1) | **Subsumido** por #8. |
| G26 | Export masivo a disco | (ninguno sin panelear; `B8-EXTW-AUTH-01` sí tiene panel) | — |

**Total triageado: 58.** Subsumidos: 42. Merecen panel: 7 (G6 ×1, G7 ×3, G8 ×2 — más `BATCH6-CANDIDATE-12` contado en G6). Cerrables sin panel: 9.

**Lo que merece panel se panelea después, con modelo barato, por el pipeline que
ya existe.** No es trabajo de Fase 2 y no bloquea nada de lo que Fase 2 aplica.

---

## Tarea 2 — Decisión de arquitectura de autenticación

### La decisión

**(A1) Sí, ahora. (A2) No, se rechaza. (B) Sí, es la decisión que importa, y es
la línea donde se corta la Fase 2.**

### (A1) Cerrar el borde *interno* — se hace, y es el mejor retorno del tramo

Poner `oidc_token` en el dispatch de Cloud Tasks, verificarlo en los tres
endpoints internos, y validar el `gcs_path` que llega en el payload.

Esto **mata** — no atenúa:

- **#2** (CRITICAL, panel)
- **BATCH6-CANDIDATE-02** (CRITICAL, unánime): el endpoint que hoy lee cualquier
  objeto del bucket compartido con un `gcs_path` que manda el atacante
- **BATCH6-CANDIDATE-04** (HIGH, unánime): que el rewrite de Vercel vuelva
  same-origin a los endpoints internos deja de importar cuando el endpoint exige
  un token OIDC que el navegador no puede fabricar

No necesita identidad Vercel→Cloud Run, no necesita quitar
`--allow-unauthenticated`, y la spec ya está escrita (Fix #2 + su ampliación).

### (A2) Identidad Vercel→Cloud Run y quitar `--allow-unauthenticated` — se rechaza

Tres razones, en orden de peso:

1. **No cierra ni uno de los ~30 endpoints sin auth.** El dominio de Vercel es
   público. Un atacante pide `https://cfdiinspector.vercel.app/api/emisores` y
   el proxy le adjunta la credencial. Se pasa de "cualquiera llega a Cloud Run"
   a "cualquiera llega a Cloud Run a través de Vercel". El riesgo no se mueve.
2. **Rompe el producto.** Adjuntar una credencial exige cómputo en Vercel
   (Middleware o Function), y ese cómputo topa el body en 4–4.5 MB. El flujo
   principal sube cientos de XMLs en un solo multipart y el backend está
   configurado para partes de hasta 100 MB. Hoy ese tráfico va **directo** a
   Cloud Run (P1) precisamente porque el camino de Vercel no lo aguanta.
3. **Es prerequisito de un diseño que no elegimos.** (A2) sólo tiene sentido si
   Vercel es la única puerta. Con (B) la puerta es la identidad del usuario, y
   Cloud Run puede seguir siendo público-pero-autenticado a nivel de aplicación.

**Lo que sí se rescata de (A2)**: quitar el literal `https://cfdi-suite-api-…`
de `BatchAnalysisPage.tsx:160` (#61) y los `console.log` de la URL (#20/#60).
Eso es higiene, y hay que decir su límite con todas sus letras: **la URL de Cloud
Run es pública de todos modos** (está en `vercel.json` versionado, en
`deploy-backend.yml:49`, y hornedada 4 veces en el bundle que cualquiera puede
descargar). Borrarla del fuente no reduce el riesgo — evita que el fallback
enmascare una mala configuración de entorno. **No se cuenta como fix de
seguridad.**

### (B) Login real con aislamiento por tenant — sí, y es lo único que mueve la aguja

Es lo único que cierra PADRE-AUTH y sus 13 hijos. **No entra en Fase 2** porque
es arquitectura, no una spec de antes/después, y este proceso separa el trabajo
por lo que cuesta.

Lo que sí se fija ahora, para que Fase 3 no vuelva a empezar de cero:

- **Alcance mínimo (B-lite), no el sistema completo.** Una sola identidad
  verificada en el backend, aplicada con un `Depends()` global —
  hoy hay **cero** `Depends()` en todo `backend/app/` (P8), así que no hay nada
  que migrar: es greenfield. Aislamiento por tenant de FIEL y emisores viene
  después, cuando exista más de un usuario.
- **Los tres llamadores no-navegador hay que acreditarlos por separado**, y
  ninguno puede pasar por un login humano:
  1. **Cloud Tasks** → OIDC (eso es A1, ya resuelto).
  2. **El batch shard worker** (Cloud Run Job `cfdi-batch-shard`) → SA dedicada
     con `run.invoker` (es #31, que ya tiene spec).
  3. **El propio backend**, que se auto-invoca vía `API_URL`
     (`deploy-backend.yml:49` apunta a la URL pública de Cloud Run) → misma SA.
- **Restricción de plataforma a verificar antes de elegir mecanismo:** el token
  OIDC local dice `"plan":"hobby"`, y la Deployment Protection de Vercel
  (password / Vercel Authentication) es de plan Pro. Si el plan es Hobby, la vía
  barata "protege el deployment y listo" **no está disponible** y hay que
  implementar identidad en la aplicación o poner IAP delante de Cloud Run.
  Esto se leyó de un token de entorno de desarrollo; **confírmalo en la consola
  de Vercel antes de comprometerte con un mecanismo.**

### Calibración de #36 y #37: MEDIUM está mal. Son HIGH.

El scanner los puso MEDIUM midiendo radio de explosión en términos de
infraestructura: "el impacto se limita al contenedor efímero que atiende la
request". Esa medición no ve la dimensión que importa.

Una e.firma **es** la identidad legal del contribuyente ante el SAT. Hoy,
cualquiera en internet puede, sin ninguna credencial:

- **usarla** — `POST /api/rfc/validate/sat` (`rfc_validation.py:100`) carga la
  FIEL guardada e inicia sesión en el portal real del SAT (#36, panel 3/3);
- **reemplazarla** — `POST /api/fiel/configure` acepta una FIEL ajena, que pasa
  a ser la que el servicio usa (#37, panel 3/3);
- **borrarla** — `DELETE /api/fiel/` (#37).

Que el contenedor sea efímero no cambia nada: lo efímero es el proceso, no la
consecuencia de haber firmado. Y el dato es material de firma electrónica
avanzada sujeto a LFPDPPP, con obligación de aviso de vulneración.

**Recalibración: #36 y #37 pasan de MEDIUM a HIGH.** No a CRITICAL sólo porque
requieren que haya una FIEL cargada en ese momento — pero esa condición se
cumple exactamente cuando el producto se está usando.

Y el punto que ata la calibración a la decisión: **(A1) no ayuda en nada aquí, y
(A2) tampoco.** El actor de amenaza es "cualquier usuario anónimo", y ninguna de
las dos introduce un concepto de usuario. Sólo (B) las cierra. Eso es lo que
hace que B-lite deje de ser un "algún día" y pase a ser el bloqueo real del
proyecto.

---

## Recalibraciones y specs afectadas

Nada se borra. Se marca.

| Spec / hallazgo | Cambio | Motivo |
|---|---|---|
| **Fix #2** | **Ampliada**, no obsoleta | Le faltaba `batch.py:210` (el peor de los tres) y su comentario contradice al código. Ver "AMPLIACIÓN Fase 1" dentro de la spec. |
| **#21** | **Cerrado como *stale*** — no requiere fix | P5: la inconsistencia que describe no existe. Los tres sitios son `None`. Lo que hay que arreglar está en Fix #9. |
| **#36, #37** | **MEDIUM → HIGH** | Ver calibración arriba. |
| **#45** | **MEDIUM → HIGH** | Colapsa con `B7-BE-AUTH-01`, panel unánime HIGH. |
| **Fix #17** (SRI) | ⛔ **OBSOLETA** | `frontend/index.html` no tiene ningún `<script src="https://…">`: su única etiqueta script es el entrypoint de Vite. `pusher-js` y `@sentry/react` son dependencias de npm empaquetadas en el bundle. No hay superficie donde poner un hash SRI. Marcada en su lugar con el comando que lo demuestra; no borrada. |
| **Fix #26** | Sin cambios | Se revisaron las 29 specs buscando alguna que asumiera que `--allow-unauthenticated` desaparece. Sólo Fix #26 toca esos flags y **los conserva** — coincide con el rechazo de (A2). Ninguna spec previa queda obsoleta por esta decisión. |
| **"Verificación global"** | Criterio de aceptación invalidado | `grep -c "OPEN" → 0` ya no es alcanzable ni deseable. Ver nota arriba. |
| **#62** | Ya estaba reclasificado LOW por panel | Se conserva como hardening, no como vulnerabilidad. |

---

## Orden de ejecución — severidad verificada × subsunción × esfuerzo

Dentro de cada nivel, agrupado por esfuerzo para que se pueda decidir qué cabe
en una sesión.

| Orden | Bloque | Hallazgos | Esfuerzo | Quién debería ejecutarlo |
|---|---|---|---|---|
| 1 | **Quick wins mecánicos** — specs con antes/después ya escritas, cero decisiones | #9 (+#21 stale), #39, #19, #25, #23, #42, #47, #50, #54 | 15 min c/u · ~2h total | **Modelo barato.** Diff literal en la spec. |
| 2 | **CRITICAL con spec** | #1 (XXE lxml) | 30 min | Modelo barato; la spec trae los 3 call sites. |
| 3 | **Prerequisito de infra** | #26 (SA dedicada) | 15 min código + 1h GCP | Humano para el setup GCP; modelo barato para el YAML. |
| 4 | **A1 — cerrar el borde interno** | #2 ampliado (+ `BATCH6-CANDIDATE-02`, `-04`) | 3h | **Modelo capaz.** Toca el orden de despliegue y una verificación de token; la ampliación no es copiar un diff. |
| 5 | **HIGH mecánicos** | #38 (SSRF Diverza), #35 (SSRF WeasyPrint), #8, #4, #3 | ~7h | Modelo barato para #38/#8; **capaz** para #4 (14 sitios, hay que decidir qué se dice al usuario) y #3 (cambia almacenamiento). |
| 6 | **HIGH de infra sin código** | #24 (headers Vercel), #25 (CORS GCS) | 1h | Modelo barato. |
| 7 | **Sprint CI/CD** | #7, #29, #32, #28, #16/#34, #49, #53 | ~7h | Modelo barato; los workflows están copy-paste listos en `09-ci-cd-hardening.md`. |
| 8 | **MEDIUM/LOW mecánicos** | #10 ampliado, #43, #44, #46, #48, #51, #52, #55, #56, #57, #58, #59, #60, #61, #62, NUEVO-BATCHID | ~8h | Modelo barato. |
| 9 | **MEDIUM restantes** | #5, #11, #13, #14, #15, #17, #18, #22, #27, #30, #31, #33 | ~10h | Modelo barato salvo #11 (auditoría de SSTI) y #5. |
| — | **CORTE. Aquí se para y se decide.** | | | |
| 10 | **B-lite: identidad real** | PADRE-AUTH + 13 hijos, #36, #37, #45, #12, #6 | Arquitectura | **Humano decide el mecanismo; modelo capaz implementa.** |
| 11 | **Panel pendiente** | `BATCH6-CANDIDATE-12`, G7 (3), G8 (2) | — | Pipeline de panel existente, modelo barato. |

**Dónde chocó la severidad con la dependencia** (una línea por choque, como pide
la regla):

- `BATCH6-CANDIDATE-03` es CRITICAL y quedó en el bloque 10, detrás de fixes LOW,
  porque es hijo de PADRE-AUTH y no tiene fix que no sea inventar identidad.
- #36/#37 se recalibraron a HIGH y quedaron en el bloque 10 por la misma razón.
- #6 es HIGH y quedó en el bloque 10 porque rate-limitar por IP con dos caminos
  de red divergentes (P1) produce un límite desigual entre ellos.
- #2 es CRITICAL y va **después** de #26 (HIGH) porque necesita la SA que #26 crea.

---

## PR 5 — HIGH nuevos con panel (hallazgos #35, #38, #39)

Los tres estaban en `08-auditoria-actual.md` sin spec. #38 y #39 tienen panel
3/3 CONFIRMADO/EXPLOTABLE y son de los mejores retornos del plan entero.

### Fix #38: SSRF via path traversal en el UUID hacia Diverza

**Severidad:** HIGH · **Panel:** 3/3 CONFIRMADO, EXPLOTABLE, NO_MITIGADO
**Archivo:** `backend/app/routers/sat_enquiry.py:150` (y el batch en `:340`)
**Esfuerzo:** 1h · **Riesgo de regresión:** Bajo

**Vulnerabilidad actual (leída del archivo, 2026-07-26):**
`_DIVERZA_BASE = "https://servicios.diverza.com/api/v2/documents"` (línea 20), y
la URL se arma en `_call_diverza`:

```python
# sat_enquiry.py:150
url = f"{_DIVERZA_BASE}/{uuid}/sat_cfdi_enquiry"
```

httpx normaliza `../` per RFC 3986, así que `uuid = "../../../admin"` produce un
`PUT` **autenticado con el `credential_id` y `credential_token` del emisor**
contra `https://servicios.diverza.com/admin/…`.

**Precisión sobre la línea 340:** la auditoría dice que la ruta batch es
"idénticamente vulnerable". Lo es, pero **no es un segundo sitio de
interpolación**: `:340` pasa `row["uuid"]` a `_enquiry_indexed`, que llama a
`_call_diverza`. Los dos flujos (single `:301` y batch `:340`) pasan por la
**misma línea 150**. Validar ahí cierra ambos.

**Cambio propuesto — un choke point, más un rechazo temprano:**

```python
# === NUEVO (arriba del módulo, junto a los imports) ===
import re
from fastapi import HTTPException

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

def _is_uuid(value: str) -> bool:
    return bool(value) and bool(_UUID_RE.match(value))

def _require_uuid(value: str) -> str:
    """El UUID entra a una URL de un tercero, autenticada con las credenciales
    del emisor. Validar la forma; no basta con confiar en que httpx escape,
    porque httpx normaliza '../' per RFC 3986."""
    if not _is_uuid(value):
        raise HTTPException(status_code=400, detail="UUID de CFDI inválido")
    return value

# === ANTES (línea 150) ===
    url = f"{_DIVERZA_BASE}/{uuid}/sat_cfdi_enquiry"

# === DESPUÉS ===
    url = f"{_DIVERZA_BASE}/{_require_uuid(uuid)}/sat_cfdi_enquiry"
```

Y en `_parse_excel_input` (línea 223), **descartar la fila en vez de reventar el
lote** — un UUID malformado en la fila 300 de un Excel no debe abortar las otras
499:

```python
# === ANTES (líneas 223-225) ===
        uuid = str(row.get("UUID") or "").strip()
        if not uuid:
            continue

# === DESPUÉS ===
        uuid = str(row.get("UUID") or "").strip()
        if not _is_uuid(uuid):
            continue   # fila con UUID ausente o malformado: se omite del lote
```

**Verificación post-fix:**
```bash
grep -c "_require_uuid\|_is_uuid" backend/app/routers/sat_enquiry.py
# ≥4 (2 definiciones + uso en :150 + uso en :223)

grep -n "_DIVERZA_BASE}/" backend/app/routers/sat_enquiry.py
# La única línea que interpola el uuid debe pasarlo por _require_uuid

python3 -m pytest backend/tests/ -q -k "enquiry"
```

**Rollback:** Quitar la llamada a `_require_uuid` de la f-string. Sin cambio estructural.

---

### Fix #39: Zip bomb / OOM via `openpyxl` sin `read_only`

**Severidad:** HIGH · **Panel:** 3/3 CONFIRMADO, EXPLOTABLE, NO_MITIGADO
**Archivo:** `backend/app/routers/sat_enquiry.py:211`
**Esfuerzo:** 15 min · **Riesgo de regresión:** Bajo, con una condición (abajo)

**Vulnerabilidad actual:**
`load_workbook(io.BytesIO(content), data_only=True)` usa el modelo eager de
celdas: 10 MB de XLSX comprimido se expanden a ~1–2 GB de objetos Python. La
instancia de Cloud Run (2 GB, `--concurrency=5`) muere por OOM en menos de un
minuto. `data_only=True` no ayuda: afecta fórmulas, no memoria.

**Cambio propuesto — `_parse_excel_input`, único call site:**

```python
# === ANTES (líneas 210-212) ===
def _parse_excel_input(content: bytes) -> list[dict[str, str]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active

# === DESPUÉS ===
def _parse_excel_input(content: bytes) -> list[dict[str, str]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    ws = wb.active
```

y cerrar el workbook antes de cada `return` de la función (hay dos: el `return []`
de la línea 215 y el `return rows` del final), o envolver el cuerpo en
`try: ... finally: wb.close()`. En modo `read_only` openpyxl deja handles del ZIP
abiertos si no se cierra.

**La condición de regresión está resuelta, no diferida.** Se leyó
`sat_enquiry.py:210-235`: el código sólo hace `ws.iter_rows(values_only=True)`
— que funciona igual en modo `read_only` — y **no escribe en `wb` ni consulta
`ws.max_row`/`ws.max_column`**, que son las dos cosas que rompen en ese modo.
El cambio es seguro tal como está escrito. Hay **un solo** `load_workbook` en el
módulo; el otro flujo de Excel (`_build_result_workbook`, escritura) usa
`Workbook()` y no se toca.

**Verificación post-fix:**
```bash
grep -n "load_workbook" backend/app/routers/sat_enquiry.py
# 1 sola línea, con read_only=True

grep -n "wb.close()" backend/app/routers/sat_enquiry.py
# presente en _parse_excel_input

python3 -m pytest backend/tests/ -q -k "enquiry or excel or xlsx"
```

**Rollback:** Quitar `read_only=True`. Vuelve el riesgo de OOM.

---

### Fix #35: SSRF via WeasyPrint en `shell-preview`

**Severidad:** HIGH
**Archivos:** `backend/app/services/shell_service.py:255-257`, `backend/app/routers/templates.py:357-371`
**Esfuerzo:** 2h · **Riesgo de regresión:** Medio (puede romper carga de logos externos)

**Vulnerabilidad actual (leída del archivo, 2026-07-26):**
`POST /api/templates/{id}/shell-preview` acepta HTML crudo y WeasyPrint lo
renderiza **sin `url_fetcher` propio**, así que resuelve `<img src>`, `<link>` y
`@import`. Hay **3 call sites**, todos con la misma forma:

```python
# shell_service.py:12  (import actual)
from weasyprint import HTML

# shell_service.py:252
return HTML(string=filled, base_url=None).write_pdf(font_config=_get_font_config())
# shell_service.py:257
return HTML(string=html, base_url=None).write_pdf(font_config=_get_font_config())
# shell_service.py:273
return HTML(string=filled_html, base_url=None).write_pdf()
```

**Precisión importante:** `base_url=None` **ya está puesto**, así que las URLs
*relativas* no resuelven. Lo que sigue abierto son las **absolutas**
(`http://`, `https://`, `file://`). El metadata server de GCP está protegido por
el requisito del header `Metadata-Flavor`, pero servicios internos, la API de
Diverza y el port scanning por diferencia de tiempos sí son explotables.

**Cambio propuesto — `shell_service.py`:**

```python
# === NUEVO, junto a los imports de la línea 12 ===
from urllib.parse import urlparse
from weasyprint import HTML
from weasyprint.urls import default_url_fetcher   # confirmar la ruta del import
                                                  # con `python -c "import weasyprint.urls"`
                                                  # antes de aplicar; ha cambiado entre versiones

_ALLOWED_SCHEMES = {"data"}       # data: URIs para logos embebidos
_ALLOWED_HOSTS: set[str] = set()  # vacío = nada de red. Poblar si se necesita un CDN.

def _restricted_url_fetcher(url: str, *args, **kwargs):
    parsed = urlparse(url)
    if parsed.scheme in _ALLOWED_SCHEMES:
        return default_url_fetcher(url, *args, **kwargs)
    if parsed.scheme in ("http", "https") and parsed.hostname in _ALLOWED_HOSTS:
        return default_url_fetcher(url, *args, **kwargs)
    raise ValueError(
        f"Recurso externo bloqueado en render de plantilla: {parsed.scheme}://{parsed.hostname}"
    )

# === ANTES / DESPUÉS — el mismo cambio en las 3 líneas (252, 257, 273) ===
- return HTML(string=filled, base_url=None).write_pdf(font_config=_get_font_config())
+ return HTML(string=filled, base_url=None,
+             url_fetcher=_restricted_url_fetcher).write_pdf(font_config=_get_font_config())
```

**Verificación post-fix:**
```bash
grep -n "HTML(" backend/app/services/shell_service.py
# Debe mostrar 3 call sites, cada uno con url_fetcher=_restricted_url_fetcher

grep -c "_restricted_url_fetcher" backend/app/services/shell_service.py
# → 4 (1 definición + 3 usos)

python3 -m pytest backend/tests/ -q -k "pdf or template or shell"
```

**Rollback:** Quitar el kwarg `url_fetcher`. Vuelve el SSRF.

**Límite del fix:** cierra la salida de red del renderer. **No** cierra que el
endpoint sea anónimo (PADRE-AUTH) ni que el HTML no se sanitice (#41).

---

## PR 6 — MEDIUM y LOW pendientes (hallazgos #13, #14, #18, #21, #40, #41, #42, #43, #44, #46, #47, #48, #49, #50, #51, #52, #53, #54, #55, #56, #57, #58, #59, #60, #61, #62)

Specs compactas: qué se cambia, dónde, y cómo se verifica. Casi todas son de
15–30 minutos y ninguna requiere una decisión.

> ⚠️ **Nivel de fidelidad de las specs de este PR.** Se leyeron del archivo real
> y traen líneas exactas: #21, #42, #47, #48, #50, #53, #54, #59, #61, #62.
> Las demás se derivaron de la descripción de `08-auditoria-actual.md` y sus
> fragmentos son **indicativos**: nombres de variable y números de línea pueden
> haberse movido. **Antes de editar, abre el archivo y confirma el "antes".**
> Si no coincide, gana el código: aplica el cambio equivalente y anota la
> discrepancia en el commit. Las specs de PR 1–PR 5 sí están verificadas contra
> el archivo.

### Fix #13: `access_token` de signed URL en logs

`backend/app/routers/pdf.py:668` · MEDIUM · 1h. Generar las signed URLs con
`version="v4"` y **no loguear la URL completa**: loguear sólo el nombre del blob.
Revisar además que Sentry no capture la URL en breadcrumbs (`before_send` que
recorte `?`). Se cierra junto con #25 (CORS wildcard), que es lo que amplifica el
riesgo.
**Verificación:** `grep -rn "signed_url\|generate_signed_url" backend/app/ | grep -i "log\|print"` → sin resultados.

### Fix #14: `pickle.loads` sobre la DB de `satcfdi`

`backend/app/services/catalogs.py:31,54` · MEDIUM · 1h. No es user input: el
archivo viene del paquete instalado. El fix es **documentar la suposición** y
añadir una verificación de integridad (hash del archivo comparado contra un valor
fijado en el repo) que falle ruidosamente si el archivo cambia.
**Verificación:** `grep -n "pickle" backend/app/services/catalogs.py` → cada uso con su comentario de suposición y su check de hash.

### Fix #18: `_job_results` evicta con 5 entradas

`backend/app/routers/sat_enquiry.py:359` · MEDIUM · 15 min. **Es funcional, no de
seguridad**, y desaparece con Fix #3 (mover a Redis). Acción: documentarlo dentro
de Fix #3 como razón adicional del cambio. No requiere fix propio.
**Verificación:** que Fix #3 mencione el límite de 5 y lo elimine.

### Fix #21: `SSL_CERT_REQS` inconsistente — CERRADO COMO STALE

`backend/app/routers/batch.py:49` · LOW · 0 min. **No requiere fix: el hallazgo
está mal.** P5 verificó que los tres sitios tienen `ssl_cert_reqs=None`; el
`"required"` que el hallazgo dice ver en `batch.py:49` no existe en el código.
El problema real (verificación de certificado deshabilitada en los tres) es Fix #9.
**Verificación:** `grep -rn "ssl_cert_reqs" --include="*.py" .` → 3 líneas, todas `None` antes del fix, todas `"required"` después de Fix #9.

### Fix #40: iframe `srcDoc` con `allow-same-origin`

`frontend/src/components/InvoiceDesigner.jsx:1139` · MEDIUM · 1h. No quitar
`allow-same-origin` a ciegas (puede romper la carga del logo). Acción: (1)
comentar en el código **por qué** está y qué lo rompería quitarlo; (2) asegurar
que `allow-scripts` **nunca** esté presente; (3) añadir un test que falle si
alguien agrega `allow-scripts` al atributo `sandbox`.
**Verificación:** `grep -n "sandbox=" frontend/src/components/InvoiceDesigner.jsx` → sin `allow-scripts`; test presente.

### Fix #41: cero sanitización HTML en el pipeline de plantillas

`InvoiceDesigner.jsx:1458`, `templates.py:341-349`, `shell_service.py:175-178` ·
MEDIUM · 1h. Añadir `bleach` (backend) en el `PUT` de la plantilla con una
allowlist de tags/atributos de maquetación. Se aplica **después** de #40, porque
#40 define cuál es la defensa que hoy sostiene todo.
**Verificación:** `grep -n "bleach" backend/requirements.txt backend/app/routers/templates.py` → presente en ambos.

### Fix #42: `.dockerignore` ausente

`backend/Dockerfile:22` · MEDIUM · 15 min. Crear `backend/.dockerignore` con al
menos: `.env*`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`,
`tests/`, `.git/`.
**Verificación:** `docker build -t t backend/ && docker run --rm t sh -c 'ls -a /app | grep -c "^\.env"'` → 0.

### Fix #43: sin validación de MIME/content-type en uploads

`zip_manifest.py:21-24`, `pdf.py:240-243`, `batch.py:102-110` · MEDIUM · 1h.
Añadir verificación de magic bytes además de la extensión: XML debe empezar con
`<?xml` o `<` tras strip de BOM; ZIP con `PK\x03\x04`. Rechazar con 400.
**Verificación:** `grep -rn "PK\\\\x03\|_MAGIC\|magic" backend/app/` → guard presente en los 3 sitios.

### Fix #44: sin límite de tamaño por archivo en `batch_analyze` → OOM

`backend/app/routers/batch.py:78,102-110` · MEDIUM · 1h. `batch_analyze` lee
todos los archivos con `asyncio.gather` y no aplica el límite
`ANALYZE_CFDI_XML_MAX_CHARS` (`policy.py:3`) que sí aplica el flujo individual.
Aplicar el mismo límite por archivo y un tope agregado por request.
**Verificación:** `grep -n "ANALYZE_CFDI_XML_MAX_CHARS" backend/app/routers/batch.py` → presente.

### Fix #46: respuesta de Diverza → inyección de fórmulas en Excel

`backend/app/routers/sat_enquiry.py:259-272` · MEDIUM · 30 min. **Subsumido por
Fix #10**: el mismo helper de escape que #10 introduce se aplica también a los
campos que vienen de Diverza (`estado`, `es_cancelable`, `estatus_cancelacion`,
`error`). Lo que agrega #46 es el principio: no confiar tampoco en el tercero.
**Verificación:** `grep -n "_escape_formula\|_sanitize_cell" backend/app/routers/sat_enquiry.py` → aplicado a los campos de usuario **y** a los de Diverza.

### Fix #47: imagen base sin digest pinning

`backend/Dockerfile:1` · MEDIUM · 15 min. `FROM python:3.12-slim@sha256:<digest>`.
Obtener el digest con `docker buildx imagetools inspect python:3.12-slim`.
Documentar en un comentario cómo actualizarlo.
**Verificación:** `grep -n "^FROM" backend/Dockerfile` → contiene `@sha256:`.

### Fix #48: build de una sola etapa retiene toolchain

`backend/Dockerfile:5-17` · MEDIUM · 1h. Leído del archivo el 2026-07-26: el
`apt-get install` de las líneas 5-17 mezcla dos cosas distintas y hay que separarlas.

| Sólo build (van a la etapa `builder`) | Runtime — **no se pueden quitar** de la etapa final |
|---|---|
| `gcc`, `python3-dev`, `libxml2-dev`, `libxslt-dev` (líneas 6-9) | `libxml2`, `libxslt1.1` (10-11) para lxml; `libgobject-2.0-0`, `libglib2.0-0`, `libpango-1.0-0`, `libpangocairo-1.0-0`, `libcairo2` (12-16) para WeasyPrint |

Multi-stage: etapa `builder` con las 4 de build que compila las wheels en un
virtualenv; etapa final `FROM python:3.12-slim@sha256:…` (ver Fix #47) que instala
sólo las 7 de runtime y copia el virtualenv.
**Verificación:** `docker run --rm <img> which gcc` → vacío; `docker run --rm <img> python -c "import lxml.etree, weasyprint"` → sin error; generar un PDF de prueba sigue funcionando.

### Fix #49: `pip install` sin `--require-hashes`

`backend/Dockerfile:20` · MEDIUM · 30 min. **Depende de Fix #16/#34**: primero
hay que generar el `requirements.txt` con hashes (`pip-compile --generate-hashes`),
después añadir `--require-hashes` al `pip install`.
**Verificación:** `grep -n "require-hashes" backend/Dockerfile` y `grep -c -- "--hash=sha256:" backend/requirements.txt` → > 0.

### Fix #50: el contenedor corre como root

`backend/Dockerfile` · LOW · 15 min. Verificado: el Dockerfile **no tiene ninguna
directiva `USER`** (27 líneas, termina en `CMD` en la 27). Panel: NO_EXPLOTABLE
en Cloud Run (gVisor). Se aplica igual porque cuesta dos líneas y es lo que
protege si algún día se migra a GKE. Insertar **entre la línea 22 (`COPY . .`) y
la 24 (`ENV`)**:

```dockerfile
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app
```

**Verificación:** `docker run --rm <img> id -u` → `1000`; el servicio sigue
levantando en el puerto 8080.

### Fix #51: `logoUrl` interpolada en HTML sin escape

`frontend/src/components/InvoiceDesigner.jsx:519,663` · LOW · 30 min. Escapar
comillas y `<` antes de interpolar, o mejor: construir el nodo con
`document.createElement` + `setAttribute` en vez de armar el string.
**Verificación:** `grep -n 'src="\${' frontend/src/components/InvoiceDesigner.jsx` → sin resultados.

### Fix #52: blob URLs abiertas con `window.open()`

`frontend/src/components/InvoiceDesigner.jsx:677-679,690-691` · LOW · 15 min.
Cambiar a un `<a download>` con `URL.createObjectURL` y `revokeObjectURL` después,
en vez de abrir la pestaña. Si hay que abrirla, `window.open(url, '_blank', 'noopener,noreferrer')`.
**Verificación:** `grep -n "window.open" frontend/src/components/InvoiceDesigner.jsx` → cada uso con `noopener,noreferrer` o migrado a `<a download>`.

### Fix #53: paquetes apt sin versión

`backend/Dockerfile:5-17` · LOW · 30 min. Los 11 paquetes del `apt-get install`
van sin versión. Fijarlas (`gcc=4:12.2.0-3`, etc., obteniéndolas con
`docker run --rm python:3.12-slim apt-cache policy <pkg>`) o aceptar el riesgo y
documentarlo. **Aplicar después de Fix #48**: si el multi-stage se hace primero,
los 4 paquetes de build salen de la imagen final y sólo quedan 7 por fijar.
**Verificación:** `grep -n "apt-get install" -A12 backend/Dockerfile` → cada paquete con `=versión`.

### Fix #54: sin `HEALTHCHECK`

`backend/Dockerfile` · LOW · 15 min. Verificado: no hay `HEALTHCHECK` en las 27
líneas. El `CMD` de la línea 27 sirve en el puerto **8080**. Añadir antes del `CMD`:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1
```

Cloud Run no lo usa (tiene sus propios probes); sirve para local y CI.
**La ruta es `/api/health`, no `/health`** — verificado en `backend/app/main.py:154`
(`@app.get("/api/health")`). El bloque "Verificación global post-implementación"
de este mismo documento usa `/health` y está mal; usar `/api/health`.
**Verificación:** `grep -n "HEALTHCHECK" backend/Dockerfile` y `docker inspect --format='{{.Config.Healthcheck}}' <img>`.

### Fix #55: `cloudbuild.yaml` sin `--service-account`

`backend/cloudbuild.yaml:22` · LOW · 15 min. Añadir el mismo
`--service-account=cfdi-suite-api-sa@…` que Fix #26 pone en `deploy-backend.yml`.
**Depende de Fix #26** (la SA tiene que existir).
**Verificación:** `grep -n "service-account" backend/cloudbuild.yaml`.

### Fix #56: divergencia merge vs overwrite entre pipelines

`backend/cloudbuild.yaml:41` vs `.github/workflows/deploy-backend.yml:40` · LOW ·
30 min. Dos caminos de deploy al mismo servicio con estrategias opuestas de env
vars. La decisión ya está tomada y documentada en `deploy-backend.yml`: **overwrite**.
Alinear `cloudbuild.yaml` o **borrarlo** si el pipeline de Cloud Build ya no se usa
— preguntar antes de borrar.
**Verificación:** `grep -n "update-env-vars\|set-env-vars" backend/cloudbuild.yaml` → consistente con `deploy-backend.yml`.

### Fix #57: filename del usuario interpolado en rutas de GCS

`backend/app/routers/batch.py:100,128,137` · LOW · 30 min. GCS tiene claves
planas, así que no hay traversal hoy. Sanitizar de todos modos: quedarse con
`Path(fname).name` y una allowlist `[A-Za-z0-9._-]`, sustituyendo el resto.
Cierra también `BATCH6-CANDIDATE-09`.
**Verificación:** `grep -n "_safe_filename" backend/app/routers/batch.py` → definición + los 3 usos.

### Fix #58: doc-code mismatch en `is_valid_xml_entry`

`docs/seguridad/03-backend.md` vs `backend/app/services/zip_manifest.py:21-24` ·
LOW · 15 min. La doc afirma que la función verifica `is_dir()` y el código no lo
hace. **Arreglar el código** (agregar el check de directorio, que es lo que se
quería) y luego la doc — no al revés.
**Verificación:** `grep -n "is_dir" backend/app/services/zip_manifest.py`.

### Fix #59: `credential_id` expuesto en `GET /api/emisores`

`backend/app/routers/emisores.py:33-44` · LOW · 30 min. Leído del archivo: el
modelo `EmisorPublic` (línea 33) declara `credential_id: str` (línea 36) y se
puebla en la línea 44 (`credential_id=entry.get("credential_id", "")`). Lo usan
los 4 endpoints (`:49` GET, `:54` POST, `:63` PUT). Quitar el campo del modelo y
del constructor.

**Ojo, toca el frontend:** `frontend/src/lib/emisores-api-client.ts:1-6` declara
`credential_id` en la interfaz `Emisor`. Hay que quitarlo ahí también o `npm run
lint` (tsc) falla. Verificar con `grep -rn "credential_id" frontend/src/` que
ningún componente lo lea antes de quitarlo.

**Nota de subsunción:** mientras el endpoint sea anónimo (PADRE-AUTH), esto no
cambia el riesgo — se aplica porque el campo simplemente no debería viajar.
**Verificación:** `grep -n "credential_id" backend/app/routers/emisores.py` → sólo en `EmisorCreate` (entrada), nunca en `EmisorPublic`; y `cd frontend && npm run lint`.

### Fix #60: `console.log` de la URL de la API

`frontend/src/components/BatchAnalysisPage.tsx:161`, `frontend/src/lib/pdf-download.ts:8` ·
LOW · 15 min. Borrar ambos `console.log`. Mismo defecto que #20 (`main.tsx:18`),
que ya tiene spec en PR 3 — aplicar los tres juntos.
**Verificación:** `grep -rn "console.log" frontend/src/ | grep -i "url\|env"` → sin resultados.

### Fix #61: URL de Cloud Run hardcodeada como fallback

`frontend/src/components/BatchAnalysisPage.tsx:160` · LOW · 15 min. Quitar el
literal y dejar sólo `import.meta.env.VITE_API_BASE_URL`, fallando ruidosamente
si no está definida.

```ts
// === ANTES ===
const url = import.meta.env.VITE_API_BASE_URL || 'https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app';
console.log("📡 URL BASE DE LA API DETECTADA EN EL NAVEGADOR:", url);
return url;

// === DESPUÉS ===
const url = import.meta.env.VITE_API_BASE_URL;
if (!url) throw new Error('VITE_API_BASE_URL no está configurada');
return url;
```

**Lo que este fix NO hace, y hay que decirlo:** la URL sigue en el bundle
desplegado (viene de la variable de Vercel, P1/P2) y sigue en `vercel.json:5` y
en `deploy-backend.yml:49`, ambos versionados. **No reduce el riesgo.** Evita que
un fallback silencioso enmascare una variable mal configurada.
**Verificación:** `grep -rn "run.app" frontend/src/` → sin resultados.

### Fix #62: `template_id` sin validar — hardening

`backend/app/routers/templates.py:304,317,335-338,341-349,357-371,421-439` · LOW ·
30 min. **Refutado 0/3 por el panel** (FastAPI captura un solo segmento, la
extensión es fija, y el GFE normaliza el path). Se aplica igual como higiene:
llamar `_validate_id_or_400` en los 7 endpoints que hoy no lo hacen.
**Verificación:** `grep -c "_validate_id_or_400" backend/app/routers/templates.py` → ≥8 (definición + 7 usos).

### Fix NUEVO-BATCHID: validar la forma de `batch_id` y `job_id` en el frontend

`App.tsx:106,259,283`, `BatchAnalysisPage.tsx:770`, `pdf-download.ts:412` · LOW ·
30 min. Cinco scanners vieron el mismo defecto en cuatro archivos
(`B8-SHELL-INJ-01/02/03`, `B8-BATCH-INJ-01`, `BATCH6-CANDIDATE-29`): identificadores
que vienen de la URL o de `localStorage` entran sin validar a URLs de API y a
nombres de canal de Pusher. Un solo guard compartido:

```ts
// frontend/src/lib/ids.ts
const UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
export function assertBatchId(v: unknown): string {
  if (typeof v !== 'string' || !UUID_RE.test(v)) throw new Error('Identificador de lote inválido');
  return v;
}
```

**Verificación:** `grep -rn "assertBatchId" frontend/src/` → definición + los 5 call sites.
**Nota:** `B8-SHELL-INJ-02` (filename de `Content-Disposition`) usa el mismo
principio pero sobre otro valor: sanear el nombre antes de usarlo como nombre de
descarga.

---

## PR 7 — Bloqueados por identidad, NO se aplican en Fase 2 (hallazgos #12, #36, #37, #45)

Estas cuatro entradas existen para que la próxima corrida de
`reconcile_registry.py` deje de reportarlas como "sin spec". **La spec es
deliberadamente "no aplicar todavía"**, con el motivo. Ninguna se toca hasta que
exista B-lite.

### Fix #36/#37: FIEL usada, sobrescrita y borrada sin autenticación

**Severidad: HIGH** (recalibrado desde MEDIUM en Fase 1 — ver la justificación en
la sección de calibración) · **Panel:** 3/3 unánime en ambos ·
`backend/app/routers/rfc_validation.py:100,143`

**No hay fix mecánico.** Un guard ad-hoc en estos dos routers deja la e.firma
protegida y los otros ~28 endpoints abiertos, e inventa un sistema de identidad
paralelo que después hay que desmontar. El fix es B-lite: `Depends()` global de
identidad verificada, más aislamiento por tenant del material de FIEL.

**Mitigación provisional disponible hoy, si la exposición es inaceptable antes de
B-lite:** borrar la FIEL configurada (`DELETE /api/fiel/`) y no cargarla hasta
que exista auth. Desactiva la validación contra el SAT, que es la funcionalidad
afectada. **Es una decisión de producto, no técnica — la toma el dueño.**

**Verificación de que sigue abierto:**
```bash
grep -rc "Depends(" backend/app/     # mientras dé 0, esto sigue abierto
```

### Fix #45: batch status sin autenticación

**Severidad: HIGH** (recalibrado desde MEDIUM: colapsa con `B7-BE-AUTH-01`, panel
unánime) · `backend/app/routers/batch.py:183`

Hijo de PADRE-AUTH. `GET /api/cfdi/batch/status/{batch_id}` devuelve RFCs,
montos, nombres y hallazgos completos del lote; el UUID es toda la defensa, y
`B8-SHELL-AUTH-02` (panel mayoría, HIGH) documenta que ese UUID viaja en una URL
compartible y vive en `localStorage`. **No se parchea por separado.**

### Fix #12: canales de Pusher públicos

MEDIUM · `frontend/src/lib/pdf-download.ts:412` (+ `BATCH6-CANDIDATE-18`).
Los private channels de Pusher necesitan un endpoint de autorización — es decir,
necesitan identidad. La decisión del CTO del 25 Jul ("Pusher se queda público
hasta que auth exista") sigue siendo la correcta y ahora tiene un bloqueo
nombrado: B-lite. Se implementa **con** B-lite, no antes ni después.

---

## Qué queda fuera de alcance, y por qué

Dicho explícitamente, porque omitir en silencio es peor que dejar fuera con motivo.

| Queda fuera | Cuántos | Motivo |
|---|---|---|
| PADRE-AUTH y sus 13 hijos | 14 | Requieren B-lite. Es la decisión que corta la Fase 2. |
| `BATCH6-CANDIDATE-12` (llave Fernet compartida FIEL↔PAC) | 1 | Merece panel adversarial real; no lo decide un modelo. |
| G7 — estado sensible en React DevTools | 3 | Merece panel: depende de si "atacante con acceso al navegador" cuenta como amenaza. |
| G8 — inyección en headers de respuesta | 2 | Merece panel; `BATCH6-CANDIDATE-10` (CRLF en `Content-Disposition`) nunca fue evaluado. |
| G9 — `NaN`/`Infinity` desde XML | 3 | Cerrable: el atacante y la víctima son la misma persona. Deuda de calidad de UI, no de seguridad. |
| G10 — opciones de engine con subprocess | 2 | Cerrable: verificado que no entra al bundle (P7). |
| G17 — reconocimiento en scripts de infra | 1 | Cerrable: la información ya es pública en archivos versionados. |
| G20 — proxy de Vite | 1 | Cerrable: `vite.config.ts` no se despliega. |
| `B8-XML-AUTH-01`, `B8-XML-AUTH-03` | 2 | Renderizar el XML del CFDI en el DOM y permitir descargarlo **es el producto**. No es un defecto; es la función de un inspector de CFDI. Se anota como decisión, no como riesgo aceptado. |
| `B8-EXTW-AUTH-01` | 1 | Exportar a la carpeta de descargas es una acción explícita del usuario sobre datos que él mismo cargó. Sin identidad no hay "control de acceso" que aplicarle. |
| Los 7 rechazados por panel | 7 | Ya tienen su sección en `registro-unificado.md` con el motivo. No se re-triagean hasta que un scan nuevo los vuelva a levantar. |

**Limitación conocida de la herramienta, para que nadie la interprete mal:**
`reconcile_registry.py` detecta specs **sólo por número** (`### Fix #N` o `**#N:`).
Los hallazgos con id de batch (`B7-…`, `B8-…`, `BATCH6-CANDIDATE-…`) van a seguir
mostrando `—` en la columna `spec` **aunque su fix esté escrito aquí**, porque no
tienen número de auditoría. La Fase 1 no editó `08-auditoria-actual.md` (fuera de
su alcance), así que esa columna no es un indicador de cobertura para las filas de
batch. El mapa real está en la tabla de dedup y en el árbol de subsunción de
arriba. Cerrar esta brecha requiere asignarles números #63+ en
`08-auditoria-actual.md` — trabajo mecánico, candidato para un modelo barato.
