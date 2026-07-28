# Observaciones de seguridad — detalle ampliado con decisión de fix

> Extraído de `docs/seguridad/EVALUACION.md` (2026-07-27)
> 5 observaciones identificadas por el panel decision-expander sobre 62 fixes
> Cada observación fue **re-evaluada por decision-expander** para validar el fix propuesto

---

## Observación #1 — Leak residual en `pdf.py:354`

### ¿Qué pasa hoy?

Cuando subes un ZIP de CFDI para convertir a PDF, el backend extrae los XMLs del ZIP y los guarda en GCS y Redis. Si algo falla al guardar (GCS sin acceso, Redis caído), el error se muestra así al usuario:

```
Error al almacenar en GCS o Redis: google.api_core.exceptions.Forbidden: caller does not have permission
```

El mensaje expone que usas Google Cloud, qué tipo de error es, y potencialmente nombres de buckets o rutas. No expone contraseñas ni tokens. Pero **rompe la regla del Fix #4**: nunca mostrar `str(exc)` al usuario. Todos los demás 29 lugares del código ya usan `error_reporting.report()` (manda el detalle a Sentry y le muestra al usuario un mensaje genérico). Esta línea es la última que no lo hace.

### ¿Qué propongo?

Cambiar esta línea:

```python
# ANTES
detail=f"Error al almacenar en GCS o Redis: {str(infra_err)}"

# DESPUÉS
report(infra_err, contexto="almacenar_xmls_zip")
raise HTTPException(status_code=500, detail="Error al almacenar los archivos extraídos del ZIP")
```

Son 3 líneas. Mismo patrón que las otras 29 llamadas a `report()`.

### Veredicto de decision-expander: **CORRECTO**

> "El fix no requiere nuevo import, solo agregar la llamada. El patrón está consolidado en 5 routers con 29 llamadas existentes. Este es el último leak de los ~24 originales del Fix #4."

### Pros de hacerlo así

- **Consistente**: mismo patrón que todo el resto del código. Si un dev nuevo ve cómo se manejan errores en `pdf.py`, este es el único lugar que no sigue el estándar.
- **Mínimo riesgo**: `report()` tiene un `try/except` interno que garantiza que NUNCA lanza excepción. Agregar esta línea no puede romper nada.
- **3 líneas**: se aplica en 1 minuto.

### Contras de hacerlo así

- **No previene leaks futuros**: si mañana alguien agrega un endpoint nuevo y escribe `str(exc)`, no hay nada que lo detecte automáticamente. Toca esperar a la próxima auditoría.
- **El mensaje genérico es menos útil para debugging**: "Error al almacenar los archivos" no te dice si fue GCS o Redis. Pero para eso está Sentry — el detalle completo se manda allí.

### ¿Por qué esto existe?

El Fix #4 arregló ~23 lugares donde se filtraban errores. Los arregló uno por uno. Este lugar (#24) se escapó. No es un error grave — son errores de infraestructura, no contraseñas — pero es inconsistente con el estándar que el mismo Fix #4 estableció.

---

## Observación #2 — La auditoría de SSTI no tiene protección contra cambios futuros

### ¿Qué pasa hoy?

Hoy **no hay** vulnerabilidad de Server-Side Template Injection. Punto. Se auditó y se confirmó:

- `canvas_service.py` usa `drawString()` de ReportLab. No hay `str.format()` con input del usuario.
- `shell_service.py` usa `HTML(string=html)` de WeasyPrint. El HTML del usuario va directo al renderizador, sin motor de templates intermedio.

Pero esta conclusión es **estática**. Si mañana alguien cambia el código y agrega un `str.format()` con datos del usuario, o importa `jinja2`, la conclusión "no hay SSTI" se vuelve falsa y nadie se entera.

### ¿Qué propongo?

Un test automático de ~25 líneas que:

1. **Falla el build** si alguien importa `jinja2`, `mako`, o `string.Template` en los archivos de render.
2. **Imprime una advertencia** si alguien usa `.format()`, `.substitute()` o `.Template()` (porque `.format()` puede ser legítimo en strings internos, no queremos bloquear el build por eso).

Si alguien introduce un template engine, el test truena en CI. La auditoría deja de ser una opinión estática y se vuelve un guardia automático.

### Veredicto de decision-expander: **CORREGIR** (la idea es correcta, la implementación necesita ajustes)

> "El test no cubre `__import__()`, `importlib.import_module()`, `eval()`, `exec()`. Un desarrollador que quiera introducir un template engine puede hacerlo sin disparar el test."

### Pros de hacerlo así

- **Automático**: no depende de que alguien recuerde re-auditar. CI lo detecta.
- **Sin dependencias**: usa `ast` de la stdlib de Python.
- **Dirigido**: solo escanea los 2 archivos de render, no dispara falsos positivos en otros módulos.

### Contras de hacerlo así

- **No detecta `__import__("jinja2")` ni `eval()`**: un dev que quiera bypassearlo puede. Pero un dev que quiere bypassear un test de seguridad tiene problemas más grandes que este test.
- **Las rutas de los archivos son frágiles**: si pytest se ejecuta desde otro directorio, `GUARDED_FILES` falla. Hay que usar rutas relativas a `__file__`.
- **La mitad del test solo imprime warnings, no falla**: la parte de `.format()` es informativa, no bloqueante. Un `.format()` con input del usuario pasaría desapercibido.

### Cambios necesarios antes de aplicar (según decision-expander)

1. Usar `Path(__file__).parent.parent / "app" / "services" / "canvas_service.py"` para rutas robustas.
2. Agregar detección de `__import__`, `importlib`, `eval`, y `exec`.
3. Convertir los warnings de `.format()` en assertions reales para strings que contengan `{` (indicio de interpolación).
4. Evaluar si ruff o bandit ya cubren esto con menos código.

---

## Observación #3 — Signed URLs pueden filtrarse en logs sin que nadie lo detecte

### ¿Qué pasa hoy?

Cuando generas un PDF, el backend crea una "signed URL" de GCS para que el frontend pueda descargarlo. Esa URL tiene un token en el query string:

```
https://storage.googleapis.com/bucket/pdf-abc.pdf?X-Goog-Signature=A7f3b9c2...
```

Hoy **no se está logueando** esa URL. Se verificó: los `print()` existentes solo muestran `job_id`, no URLs. Las excepciones se capturan después de generar la URL — si falla, la URL nunca se generó. Si funciona, no hay excepción que loguear.

Pero **no hay nada que prevenga** que en el futuro alguien agregue:

```python
signed_url = blob.generate_signed_url(...)
print(f"URL generada: {signed_url}")       # ← esto filtraría el token
logger.info(f"Descarga lista: {signed_url}")  # ← esto también
```

Y el token quedaría expuesto en Cloud Logging. Con ese token, cualquiera puede descargar el PDF durante ~1 hora.

### ¿Qué propongo?

Dos capas:

**Capa 1 — Sentry**: extender `_sentry_strip_sensitive` (ya existente) para redactar query params de GCS en cualquier mensaje que llegue a Sentry.

**Capa 2 — Lint**: prohibir `print()` en `pdf.py` y `batch.py` (donde se generan signed URLs) usando ruff.

### Veredicto de decision-expander: **CORREGIR** (la idea es correcta, las capas son insuficientes)

> "La Capa 1 solo cubre Sentry, no Cloud Logging. La Capa 2 solo bloquea `print()`, no `logging.info()`. Un `logger.info(url)` no es detectado por ninguna de las dos capas."

### Pros de hacerlo así

- **La Capa 1 usa infraestructura existente**: `_sentry_strip_sensitive` ya está configurado.
- **La Capa 2 es barata**: ruff T201 es una regla de 1 línea.
- **Dos capas independientes**: si una falla, la otra cubre.

### Contras de hacerlo así

- **Solo cubre Sentry, no Cloud Logging**: si el mensaje va a stdout/stderr (que es como Cloud Run captura logs), Sentry no lo ve.
- **Solo bloquea `print()`, no `logging.info()`**: un dev que use el logger estándar de Python no es detectado.
- **El regex `X-Goog-Signature` es específico de GCS**: si en el futuro se migra a S3 (`X-Amz-Signature`), el regex no cubre.
- **Las reglas de lint solo aplican a 2 archivos**: si se genera una signed URL en otro lugar, no hay protección.

### Cambios necesarios antes de aplicar (según decision-expander)

1. Usar `url.split("?")[0] + "?[REDACTED]"` para TODA URL con query params (no solo GCS). Más simple y cubre cualquier proveedor.
2. Agregar un `logging.Filter` que redacte query params a nivel del handler raíz de Python. Esto cubre stdout → Cloud Logging.
3. Crear un **wrapper** alrededor de `generate_signed_url` que haga que la URL sea opaca a logging accidental (su `__repr__` redacta el token).
4. Extender las reglas de lint a cualquier archivo que importe `generate_signed_url`.

---

## Observación #4 — Hash de integridad del catálogo pickle no implementado

### ¿Qué pasa hoy?

El archivo `catalogs.py` usa `pickle.loads()` para leer la base de datos de catálogos del SAT que viene en el paquete `satcfdi`. El código **documenta** que confía en estos datos porque vienen del paquete instalado, no del usuario. Pero no **verifica** que el archivo no fue manipulado.

### ¿Qué propuse originalmente?

Embeber un hash SHA256 del archivo `catalogs.db` en el código y verificarlo antes del primer `pickle.loads()`. Si el hash no coincide, la app se niega a cargar catálogos (fail-closed).

### Veredicto de decision-expander: **RECHAZAR**

> "Pip `--require-hashes` ya verifica la integridad del `.whl` completo (incluyendo `catalogs.db`). Si un atacante modifica el DB, el hash del `.whl` cambia y pip lo rechaza. Cloud Run tiene filesystem inmutable — no se puede modificar en runtime. El fix es redundante y añade complejidad sin mejorar materialmente la seguridad."

### Por qué mi fix era mala idea

1. **Ya está cubierto por pip**: `--require-hashes` en `requirements.txt` (Fix #16/#34) verifica que el paquete `.whl` completo no fue manipulado. Si alguien toca `catalogs.db`, el hash del `.whl` cambia y pip rechaza la instalación.

2. **Cloud Run es inmutable**: el filesystem del contenedor es de solo lectura. Nadie puede modificar `catalogs.db` en runtime.

3. **El `except Exception: pass` que propuse es peligroso**: si la verificación de hash tiene un bug (error de índice, PRAGMA fallido), el `except` lo silencia y la app opera sin verificación. Es peor que no tener verificación — crea falsa seguridad.

4. **El hash se desactualiza**: cada vez que `satcfdi` se actualiza, hay que regenerar el hash manualmente. Es deuda de mantenimiento.

### Pros de NO hacerlo

- **No se agrega código innecesario**: menos superficie de bugs.
- **No hay falso sentido de seguridad**: si la verificación fallara silenciosamente (por el `except`), creeríamos que estamos protegidos cuando no.
- **La protección real ya existe**: pip hashes + filesystem inmutable.

### Contras de NO hacerlo

- Si Cloud Run algún día permitiera escritura en el filesystem (poco probable), o si el proyecto se migra a un entorno sin filesystem inmutable, el hash sería útil. Pero ese día se puede implementar.

### ¿Entonces qué?

**No hacer nada**. El riesgo ya está mitigado por otras capas. Si en el futuro se migra a un entorno sin pip hashing o sin filesystem inmutable, se reconsidera.

---

## Observación #5 — Sin tope agregado de tamaño en batch analyze

### ¿Qué pasa hoy?

Imagina que subes 500 archivos XML. El backend hace esto:

```
Paso 1: Lee los 500 archivos SIMULTÁNEAMENTE en RAM (asyncio.gather)
Paso 2: Verifica que cada uno pese menos de 20 MB (límite individual)
```

El problema: si cada archivo pesa 19 MB (justo debajo del límite individual), el Paso 1 ya metió 500 × 19 MB = **9.5 GB en RAM** antes de que el Paso 2 pueda rechazar algo. Cloud Run tiene **2 GB de RAM**. El proceso muere por OOM.

En la práctica esto es difícil de explotar porque:
- Los CFDI reales pesan 5-100 KB. 500 × 100 KB = 50 MB — cabe perfecto.
- Cloud Run tiene un límite de request size (~32 MB por defecto). Un request de 9.5 GB ni siquiera llegaría al backend.
- Fabricar 500 XMLs de 19 MB deliberadamente es un ataque, no un accidente.

Pero el código no tiene **ninguna** protección contra este escenario.

### ¿Qué propongo?

**Opción A (3 líneas)**: verificar el header `Content-Length` del request antes de leer. Si el request completo pesa más de 100 MB, rechazar inmediatamente.

**Opción B (~10 líneas)**: durante la lectura, ir sumando el tamaño acumulado. Si en algún momento supera 100 MB, abortar.

El documento recomienda la Opción B porque no depende de que el header `Content-Length` esté presente (aunque en multipart siempre lo está).

### Veredicto de decision-expander: **CORREGIR** (la idea es correcta, faltan salvaguardas)

> "La Opción B usa `asyncio.gather` que lanza todas las lecturas concurrentemente. Aunque el stream HTTP subyacente es secuencial, múltiples archivos pueden estar en RAM antes de que el acumulador detecte el exceso."

### Pros de hacerlo así

- **La Opción A es trivial**: 3 líneas, rechazo temprano, cero consumo de RAM.
- **La Opción B funciona sin `Content-Length`**: cubre edge cases donde el header no está.
- **100 MB es conservador**: 500 CFDIs reales (~50 MB) caben con margen. Un ataque necesitaría archivos artificialmente inflados.
- **Combinadas son defensa en profundidad**: pre-check + in-flight check.

### Contras de hacerlo así

- **`asyncio.gather` es concurrente**: las 500 lecturas se disparan al mismo tiempo. Aunque el stream HTTP es secuencial, varios archivos pueden acumularse en RAM antes del primer check. El acumulador llega tarde.
- **La Opción A requiere modificar la firma de la función**: `batch_analyze` actualmente no recibe `request: Request`.
- **Cloud Run ya tiene un límite de ~32 MB por request**: los 9.5 GB del escenario teórico nunca llegarían al backend. El fix cubre un caso más realista: muchos archivos medianos (ej. 500 × 1 MB = 500 MB).

### Cambios necesarios antes de aplicar (según decision-expander)

1. **Primero verificar** el `max-request-size` de Cloud Run. Si ya es ~32 MB, documentarlo.
2. **Implementar A + B combinadas**: `Content-Length` como pre-filtro, acumulador como safety net.
3. **Agregar un semáforo** (`asyncio.Semaphore(8)`) para limitar cuántos archivos se leen simultáneamente. Esto garantiza que el acumulador tenga tiempo de reaccionar.
4. **Reemplazar `total_bytes = [0]`** (lista mutable compartida, patrón incómodo) por un closure con `nonlocal`.

---

## Resumen de decisiones

| Obs | Decisión | Acción |
|---|---|---|
| #1 | **APLICAR** | 3 líneas. Sin cambios. |
| #2 | **APLICAR CON CAMBIOS** | Corregir rutas, agregar `__import__`/`eval`, convertir warnings en assertions. |
| #3 | **APLICAR CON CAMBIOS** | Agregar `logging.Filter`, wrapper `__repr__`, cambiar regex por `split("?")[0]`. |
| #4 | **NO APLICAR** | El riesgo ya está cubierto por pip hashes + filesystem inmutable de Cloud Run. |
| #5 | **APLICAR CON CAMBIOS** | Agregar semáforo de concurrencia, verificar límite de Cloud Run, combinar A+B. |

**Total**: 3 fixes que sí se aplican con ajustes menores, 1 que se aplica tal cual, 1 que se rechaza.
