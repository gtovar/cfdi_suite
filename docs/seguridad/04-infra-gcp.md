# 04 — Hardening de Infraestructura GCP

> Arquitectura: Cloud Run + Cloud Tasks + Cloud Storage + Upstash Redis + Pusher
> Fecha: 2026-07-25
> Scope: cfdi-suite-api (us-central1), cfdi-batch-shard (Cloud Run Job), GCS bucket, Cloud Tasks, IAM

---

## 1. Cloud Run — Servicio `cfdi-suite-api`

**Definición actual** (fuente: `.github/workflows/deploy-backend.yml:61-67`):

```yaml
flags: |
  --allow-unauthenticated
  --cpu=2
  --memory=2Gi
  --max-instances=10
  --timeout=1800
  --concurrency=5
```

### 1.1 `--allow-unauthenticated` — API Pública

La API es completamente pública. Cualquier persona con la URL puede invocar todos los endpoints, incluyendo los rutas `/api/internal/*`.

**Riesgo**: Los endpoints "internos" no tienen ninguna protección real:

- `backend/app/services/task_dispatcher.py:32` — `POST /api/internal/generate-pdf`
- `backend/app/services/task_dispatcher.py:57` — `POST /api/internal/extract-zip`
- `backend/app/routers/pdf.py:717` — `POST /api/internal/extract-zip` (handler)

Cualquier actor externo que conozca la URL `https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app/api/internal/generate-pdf` puede invocar el endpoint de generación de PDF sin autenticación.

**Evaluación**: Para un inspector de CFDI público sin datos de usuario, esto es aceptable en la etapa actual. Los endpoints internos no exponen datos sensibles de otros usuarios (no hay usuarios). Sin embargo, un atacante podría:

1. Saturar la cola de Cloud Tasks con payloads falsos (DoS económico)
2. Generar PDFs arbitrarios consumiendo recursos de cómputo

**Opciones de hardening (en orden de madurez)**:

| Nivel | Solución | Esfuerzo | Cuándo |
|-------|----------|----------|--------|
| 1 | Validar `X-CloudTasks-QueueName` header en `/api/internal/*` | Bajo | Parcial — el header es spoofable (el nombre de cola es público) |
| 2 | Agregar `oidc_token` en el dispatch de Cloud Tasks | Bajo | Pendiente — ver §4.1 |
| 3 | IAP (Identity-Aware Proxy) delante de Cloud Run | Medio | Si hay usuarios autenticados |
| 4 | API Key via `--no-allow-unauthenticated` + `X-API-Key` | Medio | Si se necesita rate-limiting por consumidor |
| 5 | Cloud Armor + IAP + API Keys | Alto | Escala de producción con múltiples consumidores |
<!-- Updated per red-team findings C2, W2: header check is spoofable, OIDC is the real fix -->

**Quick win inmediato**: Los Cloud Tasks de GCP incluyen headers propios cuando despachan. Validar que las peticiones a `/api/internal/*` contengan el header `X-CloudTasks-QueueName: pdf-generator-queue`. Si no está presente, rechazar con 403. Esto protege los endpoints internos sin cambiar la naturaleza pública del resto de la API.

```python
# Middleware sugerido para fastapi
from fastapi import Request, HTTPException

async def cloud_tasks_only(request: Request, call_next):
    if request.url.path.startswith("/api/internal/"):
        if request.headers.get("X-CloudTasks-QueueName") != "pdf-generator-queue":
            raise HTTPException(status_code=403, detail="Forbidden")
    return await call_next(request)
```

### 1.2 Service Account — Principio de Mínimo Privilegio

**Estado actual**: El deploy no especifica `--service-account` explícitamente (`.github/workflows/deploy-backend.yml:61-67`), por lo que Cloud Run usa la **service account por defecto de Compute Engine** (`{project-number}-compute@developer.gserviceaccount.com`).

Esta SA tiene permisos de editor en el proyecto por defecto — es excesivo. Si el contenedor fuera comprometido, el atacante tendría permisos amplios sobre todos los recursos de GCP del proyecto.

**Permisos que realmente necesita `cfdi-suite-api`**:

| Recurso | Permiso | Motivo |
|---------|---------|--------|
| GCS bucket `cfdi-suite-uploads-*` | `storage.objects.create`, `storage.objects.get`, `storage.objects.delete` | Signed URLs y lectura/escritura de XML/PDF |
| Cloud Tasks `pdf-generator-queue` | `cloudtasks.tasks.create` | Encolar tareas de PDF (task_dispatcher.py:38,62,89) |
| Cloud Run Jobs `cfdi-batch-shard` | `run.jobs.run` | Disparar batch shard jobs (batch_job_trigger.py:81) |
| Cloud Trace | `cloudtrace.traces.patch` | OpenTelemetry tracing |
| IAM (solo para firmar URLs) | `iam.serviceAccounts.signBlob` | Signed URLs v4 (pdf.py:662-669) |

**Quick win — Crear SA dedicada**:

```bash
# 1. Crear service account específica para la API
gcloud iam service-accounts create cfdi-suite-api-sa \
  --display-name="Cloud Run API service account" \
  --project=ultra-acre-431617-p0

# 2. Otorgar solo los permisos necesarios
# GCS — lectura/escritura en el bucket específico
gcloud storage buckets add-iam-policy-binding \
  gs://cfdi-suite-uploads-706861124428 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Cloud Tasks — solo crear tareas (no admin)
gcloud projects add-iam-policy-binding ultra-acre-431617-p0 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/cloudtasks.enqueuer"

# Cloud Run Jobs — solo ejecutar (no desplegar)
gcloud projects add-iam-policy-binding ultra-acre-431617-p0 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# Cloud Trace
gcloud projects add-iam-policy-binding ultra-acre-431617-p0 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/cloudtrace.agent"

# IAM signBlob — para signed URLs (necesario si se usa IAM-based signing)
gcloud projects add-iam-policy-binding ultra-acre-431617-p0 \
  --member="serviceAccount:cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"

# 3. Actualizar el deploy para usar esta SA
# Agregar a deploy-backend.yml flags:
#   --service-account=cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com
```

Luego actualizar `.github/workflows/deploy-backend.yml` línea 67, agregando:

```yaml
--service-account=cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com
```

### 1.3 Recursos de Cómputo — Evaluación de Producción

| Parámetro | Valor actual | Recomendación | Justificación |
|-----------|-------------|---------------|---------------|
| CPU | 2 | Mantener | WeasyPrint renderiza HTML→PDF; el CPU extra reduce latencia |
| Memory | 2GiB | Mantener | WeasyPrint es intensivo en memoria. `cloudbuild.yaml:23-33` documenta crashes con concurrencia 5 antes del fix de aislamiento por proceso. |
| Timeout | 1800s (30 min) | Reducir a 600s | El timeout es para batches grandes. Pero batches grandes ya usan Cloud Run Jobs (batch_job_trigger.py:36). Con `concurrency=5`, 30 min es excesivo para requests individuales. |
| Concurrency | 5 | Mantener | Probado en canario con 2000 XMLs reales (cloudbuild.yaml:29-33). El comentario explícito dice "no subir más sin repetir la prueba de canario primero". |
| Max instances | 10 | Mantener | Límite superior razonable para control de costos. Si se necesita escalar más, primero implementar rate limiting. |

**Nota sobre timeout**: El timeout de 1800s se justifica en el comentario de `cloudbuild.yaml:23-33` para la generación de PDFs de batches grandes vía el camino síncrono. Si `BATCH_JOB_ENABLED=true` y el umbral `BATCH_JOB_THRESHOLD=500` están activos, los batches >500 XMLs van por Cloud Run Jobs, y el timeout de 30 min pierde su propósito. Reducir a 600s limita el blast radius de requests individuales maliciosamente lentas.

### 1.4 VPC Egress — Tráfico Saliente

**Estado actual**: No hay configuración de VPC egress. Cloud Run usa la red pública de Google.

**Evaluación**: No hay necesidad inmediata de VPC Connector porque:

- Redis (Upstash) es un servicio externo con TLS — conexión por internet público
- Pusher es un SaaS externo
- GCS se accede via API pública de Google (aunque internamente usa la red de Google)

**Cuándo considerar VPC egress**:

1. Si se migra Redis a Memorystore (Redis gestionado de GCP dentro de VPC)
2. Si se necesita IP de salida fija para whitelisting en servicios externos (ej. si Upstash tuviera IP whitelisting)
3. Si se implementa Cloud SQL o cualquier recurso VPC-only

```bash
# Si se necesita en el futuro: tráfico saliente solo a rangos privados de Google
gcloud run services update cfdi-suite-api \
  --region=us-central1 \
  --vpc-egress=private-ranges-only \
  --vpc-connector=cfdi-suite-connector
```

### 1.5 Cloud Trace + OpenTelemetry — Post-incidente

Ya instrumentado. Esto es correcto y debe mantenerse. Permite tracing distribuido Cloud Run → Cloud Tasks → Redis → GCS para análisis forense post-incidente.

---

## 2. Cloud Run Job — `cfdi-batch-shard`

**Definición actual** (fuente: `infra/deploy-batch-shard-job.sh:56-66`):

```bash
gcloud run jobs deploy "${JOB_NAME}" \
  --cpu=1 \
  --memory=2Gi \
  --task-timeout=600 \
  --max-retries=1 \
  --set-env-vars="GCS_BUCKET_NAME=...,REDIS_HOST=...,REDIS_PORT=6379,PUSHER_CLUSTER=us2"
```

### 2.1 Service Account

Mismo problema que la API: usa la SA por defecto de Compute Engine. La buena noticia: el batch shard worker es significativamente menos peligroso porque no expone endpoints HTTP. Pero igual debería tener SA dedicada.

**Permisos que necesita el job**:

| Recurso | Permiso | Motivo |
|---------|---------|--------|
| GCS bucket | `storage.objects.get` | Leer XMLs (`batch_shard_worker.py:65-68`) |
| Redis (Upstash) | — | Conexión externa, no usa IAM |

Crear SA para el job:

```bash
gcloud iam service-accounts create cfdi-batch-shard-sa \
  --display-name="Cloud Run Job batch shard" \
  --project=ultra-acre-431617-p0

gcloud storage buckets add-iam-policy-binding \
  gs://cfdi-suite-uploads-706861124428 \
  --member="serviceAccount:cfdi-batch-shard-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

Luego agregar `--service-account` al script `infra/deploy-batch-shard-job.sh:56`.

### 2.2 Secret Manager — TODO Crítico

**`infra/deploy-batch-shard-job.sh:36-41`** documenta explícitamente que `REDIS_PASSWORD`, `PUSHER_APP_ID`, `PUSHER_KEY`, `PUSHER_SECRET` NO están configurados en el script (está versionado, no debe contener secretos en texto plano). El TODO indica usar Secret Manager.

**Solución recomendada**:

```bash
# 1. Crear secretos en Secret Manager
echo -n "$REDIS_PASSWORD" | gcloud secrets create redis-password \
  --data-file=- --replication-policy=automatic --project=ultra-acre-431617-p0

echo -n "$PUSHER_APP_ID" | gcloud secrets create pusher-app-id \
  --data-file=- --replication-policy=automatic --project=ultra-acre-431617-p0

echo -n "$PUSHER_KEY" | gcloud secrets create pusher-key \
  --data-file=- --replication-policy=automatic --project=ultra-acre-431617-p0

echo -n "$PUSHER_SECRET" | gcloud secrets create pusher-secret \
  --data-file=- --replication-policy=automatic --project=ultra-acre-431617-p0

# 2. Otorgar acceso a las SAs
gcloud secrets add-iam-policy-binding redis-password \
  --member="serviceAccount:cfdi-batch-shard-sa@ultra-acre-431617-p0.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 3. En el deploy del job, reemplazar --set-env-vars por --set-secrets
gcloud run jobs deploy "${JOB_NAME}" \
  --set-secrets="REDIS_PASSWORD=redis-password:latest" \
  --set-secrets="PUSHER_APP_ID=pusher-app-id:latest" \
  --set-secrets="PUSHER_KEY=pusher-key:latest" \
  --set-secrets="PUSHER_SECRET=pusher-secret:latest"
```

### 2.3 Despliegue Manual — Riesgo de Divergencia

El job se despliega **manualmente** — no hay pipeline de CI/CD (`infra/deploy-batch-shard-job.sh:5`: "NO SE EJECUTA AUTOMÁTICAMENTE POR NINGÚN PIPELINE"). Esto es aceptable porque:

- El job se reimplementa muy raramente (solo cuando cambia la lógica del worker)
- Reutiliza la misma imagen de contenedor que la API (línea 34), por lo que los cambios de código se reflejan automáticamente al hacer deploy de la API

Riesgo latente: si se modifica el worker (`backend/app/workers/batch_shard_worker.py`) y se olvida redeploy del job, la API usa una imagen nueva pero el job usa una vieja. Mitigación: después de cada deploy de la API, verificar con:

```bash
gcloud run jobs describe cfdi-batch-shard --region=us-central1 \
  --format="value(spec.template.spec.containers[0].image)"
```

---

## 3. Cloud Storage — `cfdi-suite-uploads-706861124428`

### 3.1 CORS — `["*"]` es Demasiado Amplio

**`cors-gcs.json:3`**: `"origin": ["*"]` permite que cualquier dominio haga `PUT` y `GET` al bucket.

**Riesgo**: Un sitio malicioso `https://evil.example.com` puede hacer peticiones CORS al bucket GCS si el usuario está autenticado. Con signed URLs el riesgo se mitiga parcialmente (la URL tiene expiración), pero el bucket sigue aceptando CORS de cualquier origen.

**Corrección** — restringir al dominio de producción:

```bash
cat > cors-gcs-production.json << 'EOF'
[
  {
    "origin": ["https://cfdiinspector.vercel.app"],
    "method": ["PUT", "GET"],
    "responseHeader": ["Content-Type", "Access-Control-Allow-Origin"],
    "maxAgeSeconds": 3600
  }
]
EOF

gsutil cors set cors-gcs-production.json gs://cfdi-suite-uploads-706861124428
```

Para desarrollo local, agregar `http://localhost:5173` (o el puerto que use Vite):

```json
"origin": [
  "https://cfdiinspector.vercel.app",
  "http://localhost:5173"
]
```

**Nota**: `cors-gcs.json` está en `.gitignore` línea 46 (`# Config local de CORS para el bucket de GCS, no versionar`). Esto es correcto. Pero debería haber un `cors-gcs-production.json.example` versionado como referencia de la configuración de producción.

### 3.2 Lifecycle — Correcto para control de costos

**`infra/gcs-lifecycle.json`**: reglas de 1 día para `uploads/`, `xml_temp/`, `pdfs/`. Esto reduce costo de almacenamiento y limita la superficie de datos acumulados, pero **no previene exfiltración en caso de breach** — un atacante que obtenga acceso al bucket tiene 24 horas para descargar todo.
<!-- Updated per red-team finding F3: lifecycle is cost control, not breach containment -->

Mantener.

### 3.3 Signed URLs — Evaluación

**Implementación** (`backend/app/routers/pdf.py:624-714`):

- **Subida** (`/cfdi/pdf/request-upload`): V4 signed URL, 15 minutos, `PUT`, `content_type="application/zip"`, con `access_token` (no private key — usa IAM signing) (línea 662-669)
- **Descarga** (`/cfdi/pdf/{job_id}/download-url`): V4 signed URL, 15 minutos, `GET`, con `response_disposition` para download (línea 701-707)

**Hallazgos**:

| Aspecto | Estado | Evaluación |
|---------|--------|------------|
| Versión de firma | V4 | Correcto — V4 es la versión recomendada |
| Expiración | 15 min | Correcto — ventana de exposición corta |
| Método HTTP | PUT/GET restringido | Correcto — la URL solo permite el método especificado |
| Content-Type | `application/zip` en upload | Correcto — restringe el tipo de contenido aceptado |
| Firma | IAM token (no private key) | Correcto para Cloud Run — evita almacenar private key en el filesystem |
| Verificación existencia | `blob.exists` en descarga | Correcto — no genera URL para archivos inexistentes |

### 3.4 Bucket Público vs Signed URLs

**Estado actual**: El bucket NO es público. Todo el acceso es via signed URLs. Esto es correcto.

Verificar con:

```bash
gsutil iam get gs://cfdi-suite-uploads-706861124428
```

Si hubiera `allUsers` con `roles/storage.objectViewer`, remover inmediatamente.

### 3.5 Encriptación en Reposo

GCS encripta por defecto con Google-managed encryption keys (sin costo adicional). Para este proyecto no se justifica CMEK (Customer-Managed Encryption Keys) porque:

- Los datos son CFDI (documentos fiscales) — sensibles pero no información de tarjetas de crédito ni PII de usuarios
- El lifecycle de 1 día minimiza la ventana de exposición
- CMEK añade complejidad operativa (rotación de claves, dependencia de Cloud KMS)

Si en el futuro se procesan CFDI con datos personales visibles (ej. nóminas con RFC de empleados), reconsiderar CMEK.

---

## 4. Cloud Tasks — `pdf-generator-queue`

### 4.1 Autenticación en Despacho

**Estado actual**: Las tareas se despachan a la URL pública de Cloud Run **sin autenticación** (`backend/app/services/task_dispatcher.py:33`):

```python
task = {
    "http_request": {
        "http_method": tasks_v2.HttpMethod.POST,
        "url": f"{API_URL}/api/internal/generate-pdf",
        "headers": {"Content-type": "application/json"},
        "body": json.dumps(payload).encode("utf-8")
    }
}
```

No hay `oidc_token` ni `oidc_service_account_email` configurado. Esto significa:

1. La URL `/api/internal/generate-pdf` es accesible para **cualquiera** (ver §1.1)
2. Cloud Tasks no está usando el mecanismo de autenticación built-in de GCP

**Corrección — Agregar OIDC token al task**:

```python
task = {
    "http_request": {
        "http_method": tasks_v2.HttpMethod.POST,
        "url": f"{API_URL}/api/internal/generate-pdf",
        "oidc_token": {
            "service_account_email": "cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com",
        },
        "headers": {"Content-type": "application/json"},
        "body": json.dumps(payload).encode("utf-8")
    }
}
```

Y en el lado Cloud Run, validar el token OIDC (Google injecta un `Authorization: Bearer` header). Código del middleware:

```python
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

def verify_cloud_tasks_token(request: Request) -> bool:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return False
    try:
        token = auth_header.split("Bearer ")[1]
        id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=os.getenv("API_URL")
        )
        return True
    except Exception:
        return False
```

**Alternativa pragmática (recomendada para este proyecto)**: Mantener
`--allow-unauthenticated` (API pública es válida para este caso de uso) pero
con OIDC en Cloud Tasks + validación de token en los handlers internos. Esto
cierra el bypass documentado en `red-team-findings.md` §C2.
<!-- Updated per red-team finding C2: OIDC is the real fix, header check is spoofable -->

### 4.2 Rate Limiting

Cloud Tasks tiene rate limiting built-in. Revisar configuración actual:

```bash
gcloud tasks queues describe pdf-generator-queue --project=ultra-acre-431617-p0
```

Configuración recomendada:

```bash
gcloud tasks queues update pdf-generator-queue \
  --max-dispatches-per-second=50 \
  --max-concurrent-dispatches=5 \
  --max-attempts=3 \
  --min-backoff=10s \
  --max-backoff=60s
```

---

## 5. Redis — Upstash

### 5.1 Conexión TLS

**Estado actual**: `ssl=True` en todas las conexiones (pdf.py:73, batch_shard_worker.py:58, batch.py:48). Correcto.

**Hallazgo**: `ssl_cert_reqs=None` en pdf.py:74 y batch_shard_worker.py:59 — esto deshabilita la verificación del certificado. En un entorno de producción, debería ser `ssl_cert_reqs="required"` (o el valor por defecto del cliente Redis). Upstash emite certificados válidos.

**Corrección**: Eliminar `ssl_cert_reqs=None` de las conexiones Redis o cambiarlo explícitamente a `ssl_cert_reqs="required"`.

**Nota sobre fail-open en Redis**: `pdf.py:887-888` documenta una decisión explícita: cuando Redis no responde, el lock de extracción se saltea y el procesamiento continúa ("best-effort en vez de fail-closed"). Esto es un trade-off de disponibilidad aceptable para una herramienta pública sin SLA. En un servicio con usuarios autenticados y datos persistentes, esto sería inaceptable y debería ser fail-closed.
<!-- Updated per red-team finding W3: best-effort is a deliberate business decision -->

### 5.2 Connection Pooling

| Archivo | `max_connections` | Motivo |
|---------|-------------------|--------|
| `backend/app/routers/pdf.py:75` | 30 | API principal — múltiples requests concurrentes (concurrency=5) |
| `backend/app/workers/batch_shard_worker.py:60` | 10 | Worker de batch — proceso único |

Estos valores son razonables. El plan gratuito de Upstash tiene límite de conexiones concurrentes — verificar el tier contratado. Si es el plan free (30 conexiones), `max_connections=30` en la API agota el pool para el worker (10 conexiones) si ambos están activos simultáneamente.

**Recomendación**: Si ambos corren al mismo tiempo, reducir `max_connections` en la API a 20 para dejar espacio al worker.

### 5.3 ACLs — Separación de Roles

**Estado actual**: Una sola contraseña con acceso read/write total a todas las keys.

**Riesgo**: Un bug en un path de solo lectura podría accidentalmente modificar o borrar keys. Un atacante que obtenga acceso al worker podría borrar todas las keys de Redis.

Upstash soporta ACLs (Redis 6+). Recomendación:

```
# Usuario read-write (API — necesita escribir status de jobs, resultados)
user api on >{api-password} ~* +@all -@dangerous

# Usuario read-only (futuro — dashboards, monitoreo)
user readonly on >{readonly-password} ~* +@read
```

Esto no está implementado — es deuda técnica para el mediano plazo.

### 5.4 Health Check

`health_check_interval=25` en pdf.py:76 — correcto, mantiene vivas las conexiones.

---

## 6. Pusher Channels

### 6.1 Secretos

`PUSHER_SECRET` ahora en GitHub Secrets (`.github/workflows/deploy-backend.yml:53`). Correcto.

`PUSHER_KEY` es público por diseño — el cliente frontend lo necesita para inicializar la conexión WebSocket. Esto es el modelo estándar de Pusher. No es un problema de seguridad.

### 6.2 Channel Scoping

Revisando el uso de canales:

- `backend/app/routers/batch.py:307`: `f"batch_{batch_id}"` — canal específico por batch
- `backend/app/services/realtime.py:80`: `f"pdf-batch-{batch_id}"` — canal específico por batch

Los canales están correctamente scoped a `batch_id` (UUID). No hay wildcards. Esto es seguro.

### 6.3 Auth Endpoint

Pusher puede configurarse con `authorizer` en el frontend para canales privados. Si los canales actuales (batch_uuid) no contienen datos sensibles visibles solo por su nombre, no es necesario. Pero si se considera que el `batch_id` es semi-secreto (solo visible para quien inició el batch), debería usarse un canal privado con auth endpoint.

Para este proyecto, con usuarios no autenticados, canales públicos con UUID como nombre de canal es una seguridad por oscuridad aceptable.

---

## 7. Google Cloud IAM

### 7.1 Service Accounts Inventariadas

| Service Account | Uso | Privilegio actual | Privilegio mínimo |
|----------------|-----|-------------------|-------------------|
| Default compute SA | Cloud Run API + Job | Editor (por defecto) | `storage.objectAdmin` (bucket específico), `cloudtasks.enqueuer`, `run.invoker`, `cloudtrace.agent` |
| GitHub Actions SA (`GCP_SA_KEY`) | CI/CD deploy | `roles/run.admin`, `roles/iam.serviceAccountUser` | Puede ser más restrictivo: `run.developer` + permisos específicos |

### 7.2 Auditoría de Principio de Mínimo Privilegio

```bash
# Listar todas las SAs
gcloud iam service-accounts list --project=ultra-acre-431617-p0

# Ver los roles de cada SA
gcloud projects get-iam-policy ultra-acre-431617-p0 \
  --flatten="bindings[].members" \
  --format="table(bindings.role,bindings.members)" \
  | grep serviceAccount

# Verificar si la SA de GitHub Actions tiene más permisos de los necesarios
gcloud iam service-accounts get-iam-policy \
  GITHUB_SA_EMAIL \
  --project=ultra-acre-431617-p0
```

### 7.3 Workload Identity Federation

No implementado actualmente. Permite que GitHub Actions se autentique sin almacenar una SA key JSON. Recomendado como reemplazo de `GCP_SA_KEY` a mediano plazo:

```bash
# Crear pool de identidad
gcloud iam workload-identity-pools create github-pool \
  --location="global" --project=ultra-acre-431617-p0

# Crear proveedor GitHub
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --workload-identity-pool=github-pool --location="global" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Reemplazar credentials_json por workload_identity_provider en el workflow
```

Esto elimina la necesidad de rotar `GCP_SA_KEY` periódicamente (el token OIDC de GitHub es efímero).

---

## 8. Cloud Armor (Futuro)

No implementado. Cloud Armor es un WAF (Web Application Firewall) que provee:

- Protección DDoS (capa 3/4 y capa 7)
- Rate limiting por IP
- Reglas de filtrado geográfico
- Integración con reCAPTCHA
- Protección OWASP Top 10 (SQLi, XSS)

**¿Cuándo vale la pena?**

| Señal | Acción |
|-------|--------|
| Tráfico > 100 req/s sostenido | Evaluar Cloud Armor para DDoS |
| Abuso de endpoints costosos (generación PDF) | Rate limiting por IP |
| Ataques dirigidos a México (tráfico geográfico inusual) | Geo-fencing |
| Spam de uploads de ZIP | Rate limiting en `/cfdi/pdf/request-upload` |

Cloud Armor requiere un Load Balancer delante — no se puede aplicar directamente a Cloud Run sin LB. Costo base: ~$20-30/mes más tráfico.

**Arquitectura objetivo con Cloud Armor**:

```
Internet → Cloud Armor → Load Balancer → Cloud Run (internal)
```

Para implementar, Cloud Run debe cambiar a `--ingress=internal-and-cloud-load-balancing` y quitar `--allow-unauthenticated`.

---

## 9. Network Security

### 9.1 Ingress Settings

**Estado actual**: Ingress no está configurado explícitamente. Cloud Run acepta tráfico de todas las fuentes (all).

**Opciones**:

| Setting | Acceso desde |
|---------|------------|
| `all` (default) | Cualquier IP de internet |
| `internal` | Solo VPC y recursos dentro de Google Cloud |
| `internal-and-cloud-load-balancing` | VPC + tráfico que pase por un Cloud Load Balancer |

Para este proyecto (API pública), `all` es correcto. No hay beneficio en restringir el ingress mientras `--allow-unauthenticated` esté activo.

Si se implementa Cloud Armor en el futuro, el flujo sería:
1. Activar `--ingress=internal-and-cloud-load-balancing`
2. Poner un Load Balancer delante
3. Configurar Cloud Armor en el LB
4. El LB forwardea a Cloud Run por la red interna de Google

### 9.2 VPC Connector

No hay VPC Connector configurado. No se necesita actualmente porque todos los servicios externos (Redis, Pusher) son accesibles por internet público.

---

## Checklists

### Quick Wins (semana 1)

- [ ] Validar header `X-CloudTasks-QueueName` en endpoints `/api/internal/*` (ver §1.1)
- [ ] Crear SA dedicada `cfdi-suite-api-sa` con mínimos privilegios (ver §1.2)
- [ ] Actualizar `deploy-backend.yml` para usar la SA dedicada
- [ ] Restringir CORS de GCS a `https://cfdiinspector.vercel.app` (ver §3.1)
- [ ] Eliminar `ssl_cert_reqs=None` de conexiones Redis (ver §5.1)
- [ ] Verificar que el bucket GCS NO sea público (`gsutil iam get`) (ver §3.4)

### Medium Effort (mes 1-2)

- [ ] Migrar credenciales del job batch a Secret Manager (ver §2.2)
- [ ] Crear SA dedicada `cfdi-batch-shard-sa` para el job
- [ ] Agregar OIDC token en dispatch de Cloud Tasks (ver §4.1)
- [ ] Configurar rate limiting en Cloud Tasks queue (ver §4.2)
- [ ] Auditar IAM de SAs existentes con `gcloud projects get-iam-policy` (ver §7.2)
- [ ] Verificar límite de conexiones de Upstash vs `max_connections` configurado (ver §5.2)

### Long Term (trimestre 2+)

- [ ] Implementar Workload Identity Federation para GitHub Actions (ver §7.3)
- [ ] Redis ACLs: separar usuario read-write de read-only (ver §5.3)
- [ ] Evaluar Cloud Armor + Load Balancer cuando el tráfico lo justifique (ver §8)
- [ ] Migrar Fernet key de filesystem efímero a Secret Manager (ver `05-secretos.md`)
- [ ] Implementar rate limiting en la capa de aplicación (no solo Cloud Tasks)
