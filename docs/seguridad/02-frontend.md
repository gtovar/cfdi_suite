# 02 — Seguridad Frontend

React 19 + Vite + TypeScript, desplegado en Vercel. App pública sin
autenticación, que sube archivos XML y muestra datos fiscales.

---

## XSS vectors en React

React 19 escapa automáticamente todo contenido interpolado en JSX (`{value}`).
Pero hay escapes explícitos del modelo de seguridad que persisten:

### `dangerouslySetInnerHTML`

En este codebase no se usa `dangerouslySetInnerHTML` directamente en los
componentes principales (`App.tsx`, `BatchAnalysisPage.tsx`). Sin embargo, el
XML de CFDI contiene datos provistos por el emisor (RFC, nombre, dirección) que
se renderizan en la UI. Si en el futuro se añade un visor HTML del XML,
cualquier uso de `dangerouslySetInnerHTML` requeriría sanitización previa con
DOMPurify.

```tsx
// PELIGROSO — nunca hacer esto con XML de usuario:
<div dangerouslySetInnerHTML={{ __html: xmlContent }} />

// SEGURO si es indispensable:
import DOMPurify from 'dompurify';
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(xmlContent) }} />
```

### `eval()` y `new Function()`

No se usa `eval` en el código actual. Verificado con búsqueda en el
codebase — no hay ocurrencias.

### `innerHTML` / `outerHTML` nativos

`triggerBlobDownload` (`pdf-download.ts:54-61`) usa `URL.createObjectURL` y
`a.click()` — seguro, no manipula `innerHTML`.

### Dynamic `href`/`src`

No se construyen URLs con datos de usuario para navegación. La URL más
dinámica es la URL de descarga de GCS (`pdf-download.ts:456-458`), que
proviene del backend y no del usuario:

```typescript
// pdf-download.ts:456-458
export function getBatchDownloadUrl(batchId: string): string {
  return resolveApiBaseUrl() + "/api/cfdi/pdf/batch/" + batchId + "/download";
}
```

`batchId` viene del backend (UUID generado por el servidor), no es controlable
por el usuario para inyectar `javascript:`.

### `iframe` sandbox

`react-doctor` detectó `iframe-missing-sandbox` en `PdfTemplateBuilder`
(`doctor.config.ts:25-28`). El veredicto es "mejorable": los iframes embeben
PDFs propios (blob URLs creadas con `URL.createObjectURL`), no contenido
externo. El riesgo real es clickjacking interno si el PDF contiene
JavaScript — improbable pero posible. La regla se dejó activa a propósito; la
mitigación requiere testing manual (agregar `sandbox` puede romper el visor).

---

## Content-Security-Policy (CSP)

### Qué protege

CSP es la defensa más efectiva contra XSS. Le dice al navegador qué fuentes de
script, estilo, imagen, etc. son legítimas. Sin CSP, un XSS exitoso tiene vía
libre.

### Cómo configurarlo

Este proyecto tiene dos puntos de configuración:

**Opción A — Desde Cloud Run (backend):** middleware en `main.py`:

```python
# backend/app/middleware/security_headers.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://js.pusher.com; "
            "connect-src 'self' https://*.ingest.us.sentry.io wss://ws-*.pusher.com; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "frame-src 'self' blob:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        return response
```

Registrar en `main.py`:

```python
from .middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)
```

Notas sobre la política propuesta:

- `script-src 'unsafe-inline'` es necesario para Vite HMR en desarrollo y
  potencialmente para Sentry/Pusher SDKs que inyectan inline scripts. **Esta
  política no protege contra XSS inline — solo bloquea scripts de orígenes
  externos no autorizados.** Para protección completa contra XSS, se requiere
  CSP con nonces o hashes (requiere backend generando nonces por request).
  Esta es la política inicial pragmática; producción hardened requiere nonces.
  <!-- Updated per red-team finding W1: unsafe-inline CSP provides limited XSS protection -->
- `connect-src` incluye `wss://ws-*.pusher.com` para WebSocket de Pusher
  (`pdf-download.ts:308-309`).
- `connect-src` incluye `https://*.ingest.us.sentry.io` para Sentry
  (`main.tsx:14`).
- `frame-src blob:` permite los iframes de preview de PDF mencionados arriba.

**Opción B — Desde Vercel (`vercel.json`):** headers estáticos para assets
  servidos por Vercel:

```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Content-Security-Policy", "value": "default-src 'self'; script-src 'self' 'unsafe-inline' https://js.pusher.com; connect-src 'self' https://*.ingest.us.sentry.io wss://ws-*.pusher.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "SAMEORIGIN" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
        { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" }
      ]
    }
  ]
}
```

> La Opción B es más simple de desplegar hoy. La Opción A es más correcta
> porque el backend puede ajustar CSP dinámicamente (ej. nonces). Para un MVP
> rápido, la Opción B es suficiente.

---

## Sanitización: DOMPurify

El único contenido que podría llegar a renderizarse como HTML es el CFDI
XML — pero actualmente el visor es el `XmlNodeViewer` (`App.tsx:460`), que
muestra XML como texto/código, no como HTML renderizado. No hay necesidad de
DOMPurify hoy.

**Cuándo agregarlo.** Si se implementa un "visor bonito" del XML que convierta
nodos a HTML (ej. un árbol colapsable con syntax highlighting), sanitizar con
DOMPurify.

```typescript
import DOMPurify from 'dompurify';

function renderXmlNode(xmlString: string): string {
  // Sanitizar ANTES de dangerouslySetInnerHTML
  return DOMPurify.sanitize(xmlString, {
    ALLOWED_TAGS: ['span', 'div', 'b', 'i', 'pre', 'code'],
    ALLOWED_ATTR: ['class'],
  });
}
```

---

## CSRF — no aplica hoy, riesgo futuro

### Por qué no aplica hoy

CSRF requiere que el navegador envíe automáticamente credenciales de sesión
(cookies) con cada request. Esta app NO usa cookies de sesión ni
autenticación. Cada request es anónimo. No hay token que un atacante pueda
explotar vía CSRF.

### Qué cambia si se añade autenticación

Si se implementa Google OAuth con cookies de sesión (JWT en `httpOnly` cookie):

1. El backend DEBE implementar CSRF tokens (doble-submit cookie o
   `SameSite=Strict`).
2. FastAPI no tiene CSRF protection built-in — agregar `fastapi-csrf-protect`
   o middleware propio.
3. Todas las mutaciones (`POST`, `PUT`, `DELETE`) deben requerir el token.
4. El frontend debe enviar el token en un header (`X-CSRF-Token`) que no sea
   automático (a diferencia de las cookies).

Ejemplo si se añade autenticación:

```python
from fastapi_csrf_protect import CsrfProtect

@app.post("/api/cfdi/analyze")
def analyze(payload: Request, csrf: CsrfProtect = Depends()):
    csrf.validate_csrf(request)  # rechaza sin token válido
```

---

## VITE_* environment variables: públicas por diseño

**Regla de oro: TODO lo que empiece con `VITE_` se empaqueta en el bundle y es
visible en el navegador.** El prefijo es la forma en que Vite señala "esta
variable es pública".

### Lo que está bien como `VITE_*`

- `VITE_API_BASE_URL` — apunta a Cloud Run (`BatchAnalysisPage.tsx:160`,
  `pdf-download.ts:7`). Es pública, cualquiera puede ver a dónde apunta el
  frontend.
- `VITE_PUSHER_KEY` — clave pública de Pusher (`pdf-download.ts:308`). Por
  diseño, la key es pública en Pusher.
- `VITE_PUSHER_CLUSTER` — igual que arriba (`pdf-download.ts:309`).
- `VITE_SENTRY_DSN` — DSN público de Sentry (`main.tsx:13`).

### Lo que NUNCA debe ser `VITE_*`

- `VITE_PUSHER_SECRET` — la clave secreta de Pusher JAMÁS debe ser `VITE_*`.
  Actualmente se lee de variables de entorno del backend (`batch.py:61`), no
  del frontend. Correcto.
- `VITE_DIVERZA_TOKEN` — tokens de API de terceros.
- `VITE_SENTRY_AUTH_TOKEN` — token de auth de Sentry para releases.
- `VITE_ANY_SECRET` — cualquier clave privada, token, o password.

### verificación actual

`main.tsx:18` loggea TODAS las variables de Vite al cargar la app:

```typescript
console.log("📡 TODAS LAS VARIABLES VISIBLES POR VITE:", (import.meta as any).env);
```

Este `console.log` es útil en desarrollo pero **debe eliminarse en
producción** — un usuario técnico puede leer la consola y ver todas las
variables expuestas. Aunque sean públicas, exponer la lista completa facilita
el reconocimiento.

---

## CORS desde la perspectiva del frontend

### Lo que CORS realmente es

CORS es una política del **navegador**, no del servidor. El navegador bloquea
requests cross-origin que el servidor no autoriza explícitamente. El backend
de cfdi-suite configura:

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

### Lo que CORS NO es

CORS **no es** un mecanismo de seguridad del servidor. Cualquier herramienta
que no sea un navegador (curl, Postman, un script Python) ignora CORS por
completo. Si el endpoint no tiene autenticación, CORS no protege nada.

### Cómo funciona con Vercel rewrites

`vercel.json:5` reescribe `/api/:path*` a Cloud Run. Para el navegador, todas
las requests a `/api/*` son same-origin (mismo dominio de Vercel). Esto
significa que CORS ni siquiera entra en juego para el flujo normal — el
navegador ve todo como `https://cfdi-suite.vercel.app/api/*`.

**Riesgo:** Un XSS en la app de Vercel podría hacer requests a CUALQUIER
endpoint `/api/*` incluyendo `/api/internal/*`. Como la app es same-origin, el
navegador no bloquea nada. La única defensa para endpoints internos desde un
ataque browser-based es autenticación real (OIDC), no el header de Cloud Tasks
que un script XSS puede forjar.
<!-- Updated per red-team finding F2: same-origin XSS via Vercel rewrites -->

Si el frontend hace requests DIRECTAS a Cloud Run (como en
`pdf-download.ts:198` con `resolveApiBaseUrl()`), ahí SÍ aplica CORS. La
variable `VITE_API_BASE_URL` default apunta a
`https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app` (`BatchAnalysisPage.tsx:160`).
Esto requiere que ese dominio esté en `ALLOWED_ORIGINS` del backend.

---

## Dependency auditing

### npm audit

```bash
# Frontend
cd frontend && npm audit
```

Actualmente `package.json` no tiene script de audit. Agregar:

```json
// frontend/package.json, en "scripts"
"audit": "npm audit --audit-level=high",
"audit:fix": "npm audit fix"
```

### Dependabot

Configurar `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    versioning-strategy: "increase"

  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

### react-doctor

Ya corre en CI. Las supresiones están documentadas en
`frontend/doctor.config.ts:1-37` con veredictos razonados en
`docs/react-doctor-veredictos.md`. Reglas actualmente suprimidas:

| Regla | Razón | Línea |
|---|---|---|
| `no-adjust-state-on-prop-change` | Restauración mount-only, falso positivo | `doctor.config.ts:11` |
| `postmessage-origin-risk` | SSE same-origin, no cross-window messaging | `doctor.config.ts:17` |
| `clickjacking-redirect-risk` | Blob URL propia en iframe de preview | `doctor.config.ts:23` |
| `async-parallel` | Awaits secuenciales dependientes, no paralelos | `doctor.config.ts:35` |

---

## Client-side storage risks

### localStorage

`BatchAnalysisPage.tsx:743,874,1160` guarda `cfdi_active_batch_id` en
localStorage para restaurar el estado tras recargar la página. Esto es seguro:

- Solo guarda un UUID (batch_id), no datos fiscales.
- El batch_id no es secreto.
- Se limpia al terminar (`clearAll()` en `BatchAnalysisPage.tsx:964`).

**Riesgos generales de localStorage:**

- Accesible desde cualquier script en el mismo origen (XSS lo lee).
- No tiene expiración automática (hay que limpiarlo manualmente).
- Persiste entre pestañas y sesiones.

### sessionStorage

No se usa actualmente. Sería preferible a localStorage si no se necesita
persistencia entre sesiones (al cerrar la pestaña se borra).

### Cookies

No se usan. Si se añade autenticación, usar cookies `httpOnly` + `Secure` +
`SameSite=Strict` para JWT, NUNCA localStorage.

---

## Pusher key exposure

### Es pública por diseño

```typescript
// pdf-download.ts:308
const key = (import.meta as any).env.VITE_PUSHER_KEY || 'ec582a031473e2da1654';
```

La Pusher key es pública. El modelo de seguridad de Pusher depende de:

1. **App Secret** (servidor): solo el backend la tiene (`batch.py:61`,
   `realtime.py:19`). Sirve para firmar/autenticar eventos.
2. **App Key** (cliente): va en el bundle. Identifica la app pero no permite
   publicar eventos.
3. **Canales privados:** requieren autenticación del servidor. Este proyecto
   no los usa — todos los canales son públicos (`pdf-batch-{id}`,
   `batch_{id}`).

### Scope adecuado

Lo que SÍ hay que hacer en el dashboard de Pusher:

- Habilitar "Encrypted channels" (ya se usa `forceTLS: true`,
  `pdf-download.ts:403`).
- **Deshabilitar "Enable client events"** — si está activado, cualquier
  cliente puede publicar eventos en canales públicos, potencialmente
  falseando el progreso de un batch.
- Restringir CORS origins en dashboard de Pusher al dominio de Vercel.

### Canales públicos vs privados

Los canales actuales (`batch_{id}`, `pdf-batch-{id}`) son públicos — cualquiera
que conozca el `batch_id` puede suscribirse y recibir eventos de progreso. Dado
que no hay autenticación, esto es un riesgo aceptado (UUID como seguridad por
oscuridad). Si se añade autenticación de usuarios, todos los canales deben
migrarse a canales privados con `authorizer` en el backend.
<!-- Updated per red-team finding H4 -->

---

## Checklist

### Quick wins

- [ ] Quitar `console.log` de variables Vite en producción (`main.tsx:18`).
- [ ] Ejecutar `npm audit` y resolver hallazgos críticos/high.
- [ ] Agregar `X-Content-Type-Options: nosniff` en `vercel.json`.
- [ ] Agregar `Referrer-Policy: strict-origin-when-cross-origin` en
      `vercel.json`.
- [ ] Deshabilitar "Enable client events" en dashboard de Pusher.

### Medium effort

- [ ] Configurar CSP headers (Opción B vía `vercel.json`).
- [ ] Agregar `X-Frame-Options: SAMEORIGIN`.
- [ ] Configurar Dependabot para npm (`dependabot.yml`).
- [ ] Agregar `sandbox` attribute a iframes de preview de PDF
      (`PdfTemplateBuilder`).
- [ ] Migrar `cfdi_active_batch_id` de localStorage a sessionStorage (reducir
      persistencia).

### Long term

- [ ] CSP con nonces en vez de `'unsafe-inline'` (requiere backend).
- [ ] Implementar Trusted Types para eliminar `innerHTML` y `eval` como
      vectores.
- [ ] DOMPurify si se implementa visor HTML de XML.
- [ ] CSRF protection si se añade autenticación.

---

> Referencia externa: https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html
