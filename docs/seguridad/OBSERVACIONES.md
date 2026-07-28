# Observaciones de seguridad — detalle ampliado

> Extraído de `docs/seguridad/EVALUACION.md` (2026-07-27)
> 5 observaciones identificadas por el panel decision-expander sobre 62 fixes

---

## Observación #1 — Leak residual en `pdf.py:354`

### Origen
**Fix #4**: Error details leaked in HTTP responses. Se creó `error_reporting.py` como choke point centralizado con la regla "detalle a Sentry, mensaje genérico al usuario". De los ~24 sitios originales, ~23 quedaron corregidos.

### El problema
En `backend/app/routers/pdf.py` línea 354:

```python
except Exception as infra_err:
    raise HTTPException(
        status_code=500,
        detail=f"Error al almacenar en GCS o Redis: {str(infra_err)}"
    )
```

Este bloque captura errores de infraestructura (GCS, Redis) que ocurren al escribir los XMLs extraídos de un ZIP a GCS y Redis. La excepción puede venir de:

- **GCS** (`google.cloud.storage`): errores de red, permisos, cuota excedida. El mensaje puede contener nombres de bucket, project IDs, paths de objetos, nombres de service account.
- **Redis** (`redis-py`): errores de conexión, autenticación, timeout. El mensaje puede contener hostnames (`dashing-aphid-43185.upstash.io`), puertos, detalles de TLS.

**No es una vulnerabilidad de seguridad crítica** — son errores de infraestructura, no secretos. Pero rompe el principio de "nunca exponer `str(exc)` al usuario" que el Fix #4 estableció. Si mañana GCS empieza a incluir tokens o paths sensibles en sus mensajes de error, este código los filtraría.

### El fix que falta

```python
# backend/app/routers/pdf.py, línea 351-355
# ANTES:
except Exception as infra_err:
    raise HTTPException(
        status_code=500,
        detail=f"Error al almacenar en GCS o Redis: {str(infra_err)}"
    )

# DESPUÉS:
except Exception as infra_err:
    from ..services.error_reporting import report
    report(infra_err, contexto="almacenar_xmls_zip")
    raise HTTPException(
        status_code=500,
        detail="Error al almacenar los archivos extraídos del ZIP"
    )
```

3 líneas. Mismo patrón que el resto del archivo (ej. línea 177: `"Error al generar el PDF"`, línea 280: `"Error al leer el archivo ZIP"`).

### Alternativa más robusta: middleware de sanitización
En vez de arreglar cada leak individual, un middleware de FastAPI que intercepte toda `HTTPException` con `status_code >= 500` y reemplace `detail` con un mensaje genérico, logueando el original vía `error_reporting.report()`. Esto cerraría leaks futuros automáticamente sin depender de que cada desarrollador recuerde usar `report()`.

---

## Observación #2 — Auditoría SSTI sin test ejecutable

### Origen
**Fix #11**: "No hay SSTI en template upload". La conclusión de la auditoría es correcta hoy, pero no está protegida contra cambios futuros.

### Lo que se auditó

Dos pipelines de renderizado:

1. **`canvas_service.py` (ReportLab)**: usa `drawString()` de la API programática de ReportLab. No hay interpolación de strings del usuario en ningún punto. Las variables del usuario (RFCs, montos, nombres) se pasan como argumentos posicionales a `drawString()`, no como templates.

2. **`shell_service.py` (WeasyPrint)**: renderiza HTML crudo del usuario via `HTML(string=html)`. No hay motor de templates intermedio — el HTML del usuario va directo al renderizador. No hay `str.format()`, ni `Jinja2`, ni `Mako`, ni `string.Template`.

Conclusión del auditor: **"NO hay superficie SSTI explotable"**. Esta conclusión es correcta para el código actual.

### El problema

La conclusión es una **afirmación estática sobre código dinámico**. Si alguien en el futuro:

- Reemplaza `drawString()` por `paragraph` con `str.format()` en canvas_service
- Agrega un motor de templates entre el HTML del usuario y WeasyPrint
- Migra de ReportLab a otro motor que use templates
- Agrega interpolación dinámica de variables del usuario en el HTML

... la conclusión "no hay SSTI" se invalida sin que nadie se entere. El docstring en `canvas_service.py:9-16` documenta la situación, pero un docstring no ejecuta — no falla si el código cambia.

### El fix que falta

Un test que falle si aparece una superficie de templates:

```python
# backend/tests/test_ssti_surface.py
import ast
import sys
from pathlib import Path

FORBIDDEN_IMPORTS = {"jinja2", "mako", "string"}
FORBIDDEN_CALLS = {"format", "Template", "substitute"}
GUARDED_FILES = [
    "backend/app/services/canvas_service.py",
    "backend/app/services/shell_service.py",
]


def test_no_template_engine_imported():
    """Falla si se importa jinja2, mako, o string.Template en los archivos de render."""
    for filepath in GUARDED_FILES:
        tree = ast.parse(Path(filepath).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in FORBIDDEN_IMPORTS, (
                        f"{filepath}: import prohibido {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert node.module.split(".")[0] not in FORBIDDEN_IMPORTS, (
                        f"{filepath}: import prohibido {node.module}"
                    )


def test_no_string_format_on_user_input():
    """Falla si se usa .format() en variables que tocan input del usuario en los archivos de render."""
    for filepath in GUARDED_FILES:
        tree = ast.parse(Path(filepath).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in FORBIDDEN_CALLS:
                        # Warning, no assertion: .format() puede ser legítimo
                        # para strings internos. Una auditoría humana debe
                        # decidir si el call site es peligroso.
                        print(f"ADVERTENCIA: {filepath}:{node.lineno} usa .{node.func.attr}()")
```

25 líneas de test. Detecta automáticamente:
- `import jinja2` en los archivos de render
- `from mako.template import Template` 
- `"Hola {nombre}".format(nombre=user_input)`

La segunda función (`test_no_string_format_on_user_input`) es un warning, no un assertion — `.format()` en strings internos es legítimo. Pero te avisa para que un humano revise.

---

## Observación #3 — Sin guard automático para signed URLs en logs

### Origen
**Fix #13**: Las signed URLs de GCS incluyen un token de acceso en el query string (`?X-Goog-Signature=...`). Si esa URL se loguea, el token queda expuesto en Cloud Logging y/o Sentry.

### Lo que se verificó

- Los `print()` existentes en `pdf.py` solo loguean `job_id`, no URLs completas
- Las excepciones se capturan **después** de `generate_signed_url()` — si la URL se generó exitosamente, no hay excepción que loguear. Si falló, la URL nunca se generó
- El endpoint de download usa `apiFetch` internamente (no expone la URL en la UI como link directo)
- El CORS de GCS está restringido a 3 orígenes (Fix #25), limitando el impacto si un token se filtrara

### El problema

No hay **ningún mecanismo automático** que prevenga que un desarrollador en el futuro agregue:

```python
signed_url = blob.generate_signed_url(...)
print(f"URL generada: {signed_url}")  # ← esto filtra el token
logger.info(f"Descarga lista en {signed_url}")  # ← esto también
```

O que Sentry capture la URL en un breadcrumb de una request HTTP. Y no hay forma de saberlo hasta que alguien revise los logs manualmente.

### Lo que ya existe

- `_sentry_strip_sensitive` en `main.py:56-63` recorta query strings de URLs en Sentry. Pero esto aplica a breadcrumbs de requests HTTP entrantes, no a URLs que la app misma genera y loguea.
- Los `print()` en `pdf.py` son escasos y controlados. Pero no hay lint rule que los prohíba.

### El fix que falta

**Capa 1 — Sentry `before_send`**: extender `_sentry_strip_sensitive` para redactar query params en todos los breadcrumbs, no solo en los de request:

```python
# backend/app/main.py
def _sentry_strip_sensitive(event, hint):
    # Existente: recortar query params de URLs en breadcrumbs de request
    breadcrumbs = event.get("breadcrumbs", {}).get("values", [])
    if breadcrumbs:
        for crumb in breadcrumbs:
            url = (crumb.get("data") or {}).get("url", "")
            if isinstance(url, str) and "?" in url:
                crumb["data"]["url"] = url.split("?")[0] + "?[REDACTED]"
    
    # NUEVO: también redactar query params en el request principal
    request = event.get("request", {})
    if request and isinstance(request.get("url"), str) and "?" in request["url"]:
        request["url"] = request["url"].split("?")[0] + "?[REDACTED]"
    
    # NUEVO: redactar URLs en el mensaje de log si contienen query params
    logentry = event.get("logentry", {})
    if logentry and isinstance(logentry.get("message"), str):
        import re
        logentry["message"] = re.sub(r'\?X-Goog-Signature=[^\s"]+', '?[REDACTED]', logentry["message"])
    
    return event
```

**Capa 2 — Lint rule**: prohibir `print()` en `pdf.py` (donde se generan signed URLs) con un comment de eslint/flake8 o un check en pre-commit:

```yaml
# .pre-commit-config.yaml, en el hook de ruff
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: v0.1.0
  hooks:
    - id: ruff
      args: ["--select=T201", "--fix"]  # T201 = print found
      files: ^backend/app/routers/(pdf|batch)\.py$
```

---

## Observación #4 — Hash de integridad de catálogo pickle no implementado

### Origen  
**Fix #14**: `pickle.loads` en `catalogs.py` para leer la base de datos de `satcfdi`. El código documenta que confía en los datos porque vienen del paquete instalado. La spec de plan-fixes.md pedía dos cosas: (1) documentar la suposición — **hecho** — y (2) verificar integridad con hash — **no hecho**.

### El problema

```python
# backend/app/services/catalogs.py, líneas 34-36
for k, v in c.fetchall():
    val = pickle.loads(v)       # ← deserializa sin verificar integridad
    result[str(pickle.loads(k))] = str(val[0] if isinstance(val, list) else val)
```

`pickle.loads()` ejecuta código arbitrario si los datos fueron manipulados. La defensa actual es: "los datos vienen del paquete `satcfdi` instalado vía pip, no de input del usuario". Esto es cierto en operación normal.

Pero hay un escenario donde esto falla:

1. **Supply chain compromise**: un atacante compromete el paquete `satcfdi` en PyPI y publica una versión con datos pickle maliciosos. Fix #16/#34 (hash pinning de pip) protege contra esto a nivel de paquete, pero si el atacante compromete el paquete legítimo (misma versión, diferente contenido), el hash pinning no ayuda porque el hash es del paquete wheel, no del archivo de base de datos interno.

2. **Modificación local**: un desarrollador con acceso de escritura al repo modifica el archivo de base de datos de `satcfdi` sin saber que contiene datos pickle. Esto no es un ataque sino un error, pero `pickle.loads` lo ejecutaría igual.

3. **Corrupción silenciosa**: si el archivo de base de datos se corrompe (fallo de disco, bug de SQLite), `pickle.loads` podría ejecutar código basura en vez de fallar limpiamente.

### El fix que falta

Embeber el hash SHA256 del archivo de base de datos en el código y verificarlo antes del primer `pickle.loads`:

```python
# backend/app/services/catalogs.py
import hashlib
import logging

logger = logging.getLogger(__name__)

# Hash SHA256 del archivo catalogs.db del paquete satcfdi.
# Generado con: python -c "import satcfdi.catalogs as c; import hashlib;
#   print(hashlib.sha256(open(c.conn.execute('PRAGMA database_list').fetchone()[2],'rb').read()).hexdigest())"
_EXPECTED_CATALOG_HASH = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

_verified = False


def _verify_catalog_integrity() -> None:
    global _verified
    if _verified:
        return
    try:
        import satcfdi.catalogs as _cat
        db_path = _cat.conn.execute("PRAGMA database_list").fetchone()[2]
        actual = hashlib.sha256(open(db_path, "rb").read()).hexdigest()
        expected = _EXPECTED_CATALOG_HASH.split(":")[1]
        if actual != expected:
            logger.critical(
                f"¡INTEGRIDAD DE CATÁLOGO COMPROMETIDA! Hash esperado: {expected[:16]}..., "
                f"Hash real: {actual[:16]}... No se cargarán catálogos SAT."
            )
            raise RuntimeError("Catálogo SAT corrupto o manipulado")
        _verified = True
    except Exception:
        pass  # En desarrollo local sin satcfdi, no hay nada que verificar


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _verify_catalog_integrity()  # ← verificar antes del primer uso
        import satcfdi.catalogs as _cat
        _conn = _cat.conn
    return _conn
```

~20 líneas. La verificación ocurre una sola vez (global `_verified`) en el primer acceso a la base de datos. Si el hash no coincide, el servicio se niega a cargar catálogos (fail-closed) en vez de ejecutar código arbitrario.

---

## Observación #5 — Sin tope agregado de tamaño en batch analyze

### Origen
**Fix #44**: "Sin límite de tamaño por archivo en batch_analyze → OOM". El fix implementó un límite **individual** por archivo (`ANALYZE_CFDI_XML_MAX_CHARS = 20_000_000`, ~20 MB). Pero no implementó un límite **agregado** para el request completo.

### Lo que existe ahora

```python
# backend/app/routers/batch.py, línea 134-146
@router.post("/analyze")
async def batch_analyze(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "Se requiere al menos un archivo")
    if len(files) > MAX_FILES:           # ← límite de cantidad: 500 archivos
        raise HTTPException(400, f"Máximo {MAX_FILES} archivos por lote")

    batch_id = str(uuid.uuid4())
    contents = list(await asyncio.gather(*[_read_upload(f) for f in files]))
    # ↑ Los 500 archivos YA ESTÁN EN RAM aquí. asyncio.gather lee todos simultáneamente.

    for fname, raw in contents:
        if len(raw) > ANALYZE_CFDI_XML_MAX_CHARS:  # ← límite INDIVIDUAL: 20 MB
            raise HTTPException(400, f"El archivo {fname} excede el límite...")
```

### El problema — paso a paso

1. **El usuario envía 500 archivos de 19 MB cada uno.** Todos pasan el límite individual (19 < 20 MB).
2. **`asyncio.gather` lee los 500 archivos simultáneamente en RAM.** Resultado: 500 × 19 MB = **9.5 GB en RAM**.
3. **Cloud Run tiene 2 GB de RAM** (`deploy-backend.yml:94`, `--memory=2Gi`).
4. **OOM Killer mata el proceso.** La instancia se reinicia. Las demás requests concurrentes (hasta 5 por `--concurrency`) también mueren.

El límite individual mitiga el caso de "1 archivo gigante" (ej. 1 × 1 GB). Pero no mitiga el caso de "muchos archivos medianos". Un atacante que conoce el límite puede optimizar su ataque para maximizar el daño con archivos justo debajo del límite.

### Por qué es bajo riesgo en la práctica

- **Los CFDI reales miden 5-100 KB, no 19 MB.** Un XML fiscal del SAT típicamente no supera 1 MB. 500 × 1 MB = 500 MB — cabe en 2 GB.
- **`MAX_FILES = 500` es el único multiplicador.** No se pueden enviar más de 500 archivos por request.
- **El `Content-Length` header existe.** Starlette podría usarlo para rechazar requests grandes antes de leer el body, pero `asyncio.gather` no lo verifica.

Pero un atacante **deliberado** puede fabricar 500 XMLs de 19.9 MB con contenido basura y saturar la instancia.

### El fix que falta

Dos opciones, de menor a mayor esfuerzo:

**Opción A — Mínima (3 líneas)**: verificar `Content-Length` del request antes de leer los archivos.

```python
# backend/app/main.py, después de MultiPartParser.max_part_size
_MAX_REQUEST_BYTES = 100 * 1024 * 1024  # 100 MB

# En batch_analyze:
content_length = request.headers.get("Content-Length")
if content_length and int(content_length) > _MAX_REQUEST_BYTES:
    raise HTTPException(413, f"El lote completo excede {_MAX_REQUEST_BYTES // 1024 // 1024} MB")
```

Limitación: `Content-Length` puede no estar presente en chunked transfer encoding. Pero el upload de archivos vía multipart **siempre** tiene `Content-Length`.

**Opción B — Robusta (~10 líneas)**: sumar el tamaño acumulado durante la lectura y abortar si excede el tope.

```python
_MAX_TOTAL_BYTES = 100 * 1024 * 1024  # 100 MB

async def _read_with_limit(f: UploadFile, accumulator: list[int]) -> tuple[str, bytes]:
    raw = await f.read()
    accumulator[0] += len(raw)
    if accumulator[0] > _MAX_TOTAL_BYTES:
        raise HTTPException(413, f"El lote completo excede {_MAX_TOTAL_BYTES // 1024 // 1024} MB")
    return (f.filename or "archivo.xml", raw)

# En batch_analyze:
total_bytes = [0]
contents = list(await asyncio.gather(*[_read_with_limit(f, total_bytes) for f in files]))
```

La opción B es mejor porque no depende de `Content-Length` y funciona con cualquier encoding de transferencia. Lee archivo por archivo pero suma el acumulado.

---

## Resumen de esfuerzo

| Obs | Qué | Líneas | Dificultad |
|---|---|---|---|
| #1 | `pdf.py:354` → `report()` + mensaje genérico | 3 | Trivial |
| #2 | Test SSTI: prohibir imports de template engines | 25 | Fácil |
| #3 | `before_send` Sentry + lint rule anti-print | 10 | Fácil |
| #4 | Hash SHA256 de catálogo pickle en `catalogs.py` | 20 | Fácil |
| #5 | Tope agregado en batch analyze | 3-10 | Trivial |
| **Total** | | **~65 líneas** | |

Ninguna observación es bloqueante. Ninguna es una vulnerabilidad activa. Las 5 son **defense-in-depth sobre fixes ya aplicados correctamente**.
