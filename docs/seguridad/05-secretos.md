# 05 — Política de Gestión de Secretos

> Fecha: 2026-07-25
> Scope: Todo el proyecto — CI/CD (GitHub Actions), runtime (Cloud Run), desarrollo local (`.env`)

---

## 1. Clasificación

Todo valor configurable del proyecto se clasifica en exactamente una de tres categorías.

### 1.1 SECRET

Valor que concede acceso a un recurso o permite suplantar una identidad. Si se filtra, el atacante puede **actuar como el sistema**.

| Secreto | Dónde vive | Formato | Blast radius si se filtra |
|---------|-----------|---------|---------------------------|
| `GCP_SA_KEY` | GitHub Secrets | JSON key de SA | Control total de recursos GCP del proyecto |
| `PUSHER_SECRET` | GitHub Secrets | String | Publicar mensajes falsos en canales Pusher |
| `REDIS_PASSWORD` | GitHub Secrets | String | Lectura/escritura total de Redis (Upstash) |
| `SENTRY_DSN` | GitHub Secrets | URL | Inyectar eventos falsos en Sentry |
| `VERCEL_TOKEN` | GitHub Secrets | Token | Desplegar código arbitrario en Vercel |
| `VERCEL_ORG_ID` | GitHub Secrets | String | Acceso a equipo Vercel |
| `VERCEL_PROJECT_ID` | GitHub Secrets | String | Acceso al proyecto Vercel |
| `PUSHER_APP_ID` | GitHub Secrets | String | Identifica la app Pusher |
| `FIEL passwords` | `~/.cfdi-suite/fiel.enc` | Fernet-encrypted | Suplantar identidad fiscal (RFC) ante el SAT |
| `credential_token` (emisores) | `~/.cfdi-suite/emisores.enc` | Fernet-encrypted | Acceso a APIs del SAT como el RFC |

### 1.2 VARIABLE

Valor de configuración que podría exponer información del entorno, pero no concede acceso por sí mismo. Su filtración es un **problema de reconocimiento** (el atacante sabe dónde están los servicios) pero no de acceso directo.

| Variable | Dónde vive | Valor típico |
|----------|-----------|-------------|
| `REDIS_HOST` | GitHub Variables | `dashing-aphid-43185.upstash.io` |
| `PUSHER_CLUSTER` | GitHub Variables | `us2` |
| `GCS_BUCKET_NAME` | GitHub Variables | `cfdi-suite-uploads-706861124428` |
| `VERCEL_URL` | GitHub Secrets (mal clasificado) | `https://cfdiinspector.vercel.app` |
| `PUSHER_KEY` | GitHub Secrets (mal clasificado) | App key pública de Pusher |
| `API_URL` | `deploy-backend.yml:49` (hardcoded) | `https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app` |

**Hallazgos de clasificación incorrecta**:

1. `VERCEL_URL` (`deploy-backend.yml:44`) está en GitHub Secrets pero es un valor público (es la URL de producción). Debería ser GitHub Variable.
2. `PUSHER_KEY` (`deploy-backend.yml:52`) está en GitHub Secrets pero es una key pública por diseño de Pusher. Podría ser GitHub Variable sin riesgo.
3. `API_URL` está hardcodeado en `deploy-backend.yml:49` como `https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app`. Esto es correcto (es pública), pero si cambia el nombre del servicio, hay que actualizarlo manualmente.

**Decisión:** Los items 1 y 2 se quedan en GitHub Secrets por ahora. Migrarlos a Variables requiere actualizar `deploy-backend.yml:44,52` (referencias `${{ secrets.X }}` → `${{ vars.X }}`). El costo de migración es bajo pero toca el pipeline de deploy. Se hará en el próximo refactor del workflow.
<!-- Updated per red-team finding I4: PUSHER_KEY/VERCEL_URL misclassification -->

### 1.3 CONSTANTE

Valor que es determinista, no cambia entre entornos, o es parte de la lógica del sistema. No es secreto ni variable de configuración.

**Harcodeado en archivos fuente (correcto)**:

| Constante | Archivo | Valor | Motivo |
|-----------|---------|-------|--------|
| `REDIS_PORT=6379` | `deploy-backend.yml:46` | 6379 | Puerto estándar de Redis |
| `BATCH_JOB_THRESHOLD=500` | `deploy-backend.yml:58` | 500 | Umbral de negocio |
| `BATCH_JOB_SHARD_SIZE=20` | `deploy-backend.yml:59` | 20 | Tamaño de shard |
| `BATCH_METADATA_TTL_SECONDS=86400` | `pdf.py:67` | 86400 | 24h — debe coincidir con lifecycle GCS |
| `MAX_FILES=500` | `batch.py:78` | 500 | Límite de archivos por batch |
| `REDIS_TTL=86400` | `batch.py:79` | 86400 | 24h |

---

## 2. Estado Actual (2026-07-25)

### 2.1 GitHub Secrets (10)

```bash
# Listado actual (verificar con: gh secret list --repo <owner>/cfdi_suite)
GCP_SA_KEY           # SA key JSON para autenticación GCP
PUSHER_APP_ID         # App ID de Pusher (identidad, no clave criptográfica)
PUSHER_KEY            # Key pública de Pusher (visible en frontend)
PUSHER_SECRET         # Secret de Pusher (CRÍTICO)
REDIS_PASSWORD        # Contraseña de Upstash Redis (CRÍTICO)
SENTRY_DSN            # URL del proyecto Sentry
VERCEL_TOKEN          # Token de deploy de Vercel
VERCEL_ORG_ID         # ID de organización Vercel
VERCEL_PROJECT_ID     # ID de proyecto Vercel
VERCEL_URL            # URL de producción (https://cfdiinspector.vercel.app)
```

### 2.2 GitHub Variables (3)

```bash
# Listado actual (verificar con: gh variable list --repo <owner>/cfdi_suite)
REDIS_HOST            # dashing-aphid-43185.upstash.io
PUSHER_CLUSTER        # us2
GCS_BUCKET_NAME       # cfdi-suite-uploads-706861124428
```

### 2.3 Archivos `.env` Locales

| Archivo | Git | Estado |
|---------|-----|--------|
| `backend/.env` | gitignored (`.gitignore:7`, `.env*`) | OK |
| `frontend/.env.local` | gitignored (`.gitignore:7`) | OK |
| `frontend/.env.production` | gitignored (`.gitignore:7`) | OK |
| `frontend/.env.example` | VERSIONADO (`.gitignore:8`, `!.env.example`) | OK — sirve como template |

### 2.4 Fernet Encryption — Credenciales FIEL/Emisores

**Archivos** (`backend/app/credentials.py:9-11`, `backend/app/fiel_config.py:9-11`):

```
~/.cfdi-suite/
├── secret.key      # Fernet key (generada automáticamente si no existe)
├── emisores.enc    # Credenciales de emisores (RFC + credential_token)
└── fiel.enc        # FIEL (certificado .cer + llave .key + password)
```

**Mecanismo**: Si `secret.key` no existe, se genera una nueva (`credentials.py:16-17`). Esto significa que en Cloud Run, cada nueva instancia genera una key diferente y no puede descifrar datos cifrados por una instancia anterior.

**Problema**: Cloud Run recicla instancias. Los archivos en `~/.cfdi-suite/` viven en el filesystem efímero del contenedor. Cuando la instancia se recicla:

1. `emisores.enc` y `fiel.enc` se pierden
2. `secret.key` nueva se genera, pero no puede descifrar nada porque los datos ya no existen
3. El usuario tiene que volver a subir FIEL y credenciales de emisores

**Esto es parcialmente aceptable para el diseño actual** — no hay usuarios persistentes, las credenciales se suben por sesión. Pero para producción real:

**Problema de UX silencioso:** Cuando Cloud Run recicla y se genera una nueva key, los emisores previamente configurados desaparecen sin advertencia. El usuario ve `POST /api/emisores` → HTTP 201 (ok), pero luego `GET /api/sat/enquiry` → HTTP 404 "RFC emisor no configurado". No hay log de advertencia, no hay notificación. El usuario no sabe si fue su error o un bug.
<!-- Updated per red-team findings H5, V6: silent credential loss on cold start -->

**Recomendación inmediata:** Agregar un log WARNING cuando `secret.key` no existe pero `emisores.enc` sí — indicando que las credenciales previas son ilegibles (key rotada). Y cuando no hay emisores configurados, el endpoint de enquiry debería devolver un mensaje más informativo que distinga "nunca configurado" de "configurado pero la key se perdió".

### Opciones de migración para Fernet

**Opción A — Mover la key a variable de entorno (más simple)**:

```python
# En vez de leer de ~/.cfdi-suite/secret.key, leer de FERNET_KEY env var
import os
from cryptography.fernet import Fernet

def _fernet() -> Fernet:
    key = os.getenv("FERNET_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        # En desarrollo local, guardarla para no perderla
        _SUITE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        _KEY_FILE.write_text(key)
    return Fernet(key.encode() if isinstance(key, str) else key)
```

Y en el deploy:
```bash
# Generar key una vez
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Guardar en Secret Manager
echo -n "KEY_GENERADA" | gcloud secrets create fernet-key --data-file=-

# En deploy-backend.yml, agregar:
# --set-secrets=FERNET_KEY=fernet-key:latest
```

**Opción B — Mover archivos a GCS (persistente pero más lento)**:

Leer/escribir `emisores.enc` y `fiel.enc` desde/hacia un bucket GCS con acceso autenticado por SA. La key sigue en env var. Más complejo pero permite persistencia across deploys.

**Opción C — Aceptar efímero (estado actual)**:

Si las credenciales FIEL siempre se suben por sesión y no hay expectativa de persistencia, el diseño actual es suficiente. Documentarlo explícitamente.

**Recomendación**: Opción A para `FERNET_KEY`. Mantener los archivos `.enc` en filesystem efímero (se suben por sesión). Si en el futuro se necesita persistencia de credenciales entre deploys, pasar a Opción B.

---

## 3. Exposición Previa y Remediación

### 3.1 Incidente: Redis Password Hardcodeado

**Ventana de exposición**: 3 de junio 2026 → 25 de julio 2026 (~52 días)

**Archivo afectado**: `.github/workflows/deploy-backend.yml:47` (histórico — ya no está en HEAD)

**Qué se expuso**: La contraseña de Redis (Upstash) estaba en texto plano en el workflow de deploy, versionada en git. Cualquiera con acceso al repositorio (público o privado) podía leerla del historial de git.

**Remediación completada**:

1. ✔ Contraseña rotada en Upstash
2. ✔ Nueva contraseña almacenada en GitHub Secret `REDIS_PASSWORD`
3. ✔ Workflow actualizado para usar `${{ secrets.REDIS_PASSWORD }}` (`.github/workflows/deploy-backend.yml:47`)
4. ✔ Cloud Run redeployado con la nueva contraseña

**Decisión sobre el historial de git**: NO se reescribió el historial. Motivos:

- La credencial ya fue rotada y es inválida
- Reescribir historial en un branch `main` compartido causa problemas de sincronización
- El valor real en el historial es inútil para un atacante

**Riesgo residual**: Si Upstash reusa contraseñas (poco probable), alguien con acceso al historial de git podría intentar la contraseña vieja en otros servicios. Como la contraseña era generada por Upstash (no reutilizada por un humano), este riesgo es nulo.

### 3.2 Lección Aprendida

> Todo valor que conceda acceso a un recurso externo DEBE ser GitHub Secret desde el día 1, nunca hardcodeado. El costo de migrar después (rotar, redeploy, verificar) es 10x el costo de hacerlo bien desde el inicio.

---

## 4. Patrones de Almacenamiento

### 4.1 GitHub Secrets → CI/CD

Secrets que la pipeline de deploy necesita para inyectar en el entorno de ejecución:

```
GCP_SA_KEY          → google-github-actions/auth@v2 (deploy-backend.yml:20)
REDIS_PASSWORD      → env_var de Cloud Run (deploy-backend.yml:47)
PUSHER_*            → env_var de Cloud Run (deploy-backend.yml:51-53)
SENTRY_DSN          → env_var de Cloud Run (deploy-backend.yml:50)
VERCEL_*            → vercel CLI (deploy-frontend.yml:22-25)
```

**Regla**: Nunca hacer `echo $SECRET` en un step del workflow. GitHub Actions auto-maskea los valores de secrets en logs, pero si el valor pasa por un comando que lo transforma (ej. `echo $SECRET | base64`), el valor transformado no está maskedo.

### 4.2 GitHub Variables → CI/CD

Variables que no son secretas pero cambian entre entornos:

```
REDIS_HOST      → deploy-backend.yml:45
PUSHER_CLUSTER  → deploy-backend.yml:54
GCS_BUCKET_NAME → deploy-backend.yml:55
```

### 4.3 `.env` → Desarrollo Local

- `backend/.env`: contiene `REDIS_PASSWORD`, `PUSHER_SECRET`, etc. para desarrollo local
- `frontend/.env.local`: variables de Next.js para desarrollo
- Las credenciales reales NUNCA deben copiarse de producción — usar credenciales de desarrollo (Upstash tiene DBs de prueba gratuitas)

### 4.4 Fernet → Credenciales FIEL en Runtime

- `~/.cfdi-suite/secret.key`: Fernet key (ver §2.4 para el problema de persistencia)
- `~/.cfdi-suite/emisores.enc`: credenciales de emisores
- `~/.cfdi-suite/fiel.enc`: certificado FIEL + llave + password

---

## 5. Política de Rotación

### 5.1 Frecuencia

| Secreto | Rotación | Justificación |
|---------|----------|---------------|
| `REDIS_PASSWORD` | 90 días o tras sospecha | Acceso total a Redis (datos temporales, pero si se filtrara, un atacante podría corromper batches activos) |
| `PUSHER_SECRET` | 90 días o tras sospecha | Permite publicar mensajes falsos en canales |
| `GCP_SA_KEY` | 90 días | Acceso a GCP; si se filtrara, el atacante controla Cloud Run, GCS y Cloud Tasks |
| `VERCEL_TOKEN` | Solo tras sospecha | Vercel gestiona su propia rotación; el token no da acceso a datos de usuario (no hay) |
| `SENTRY_DSN` | NO rotar | El DSN es público por diseño — solo permite enviar eventos a Sentry, no leerlos |

### 5.2 Checklist de Rotación

Cuando rotes un secreto, seguí este orden exacto:

```
□ 1. Generar nuevo valor en el proveedor upstream
     - Upstash: Dashboard → Database → Password → Regenerate
     - Pusher: Dashboard → App → Keys → Regenerate
     - GCP: gcloud iam service-accounts keys create
□ 2. Actualizar GitHub Secret
     gh secret set REDIS_PASSWORD --repo <owner>/cfdi_suite --body "NUEVA"
□ 3. Redeploy del servicio
     git push (si el workflow es on push) o workflow_dispatch manual
□ 4. Verificar que el deploy funcionó
     curl -s https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app/health
□ 5. Eliminar credencial vieja del proveedor upstream
     - No hacerlo antes del paso 4 — si el deploy falla, te quedás sin acceso
□ 6. Anotar fecha de rotación
     Agregar entrada en PROJECT_STATE.md o un log de rotaciones
```

### 5.3 Rotación de FIEL

La FIEL (Firma Electrónica Avanzada) tiene vigencia de 4 años emitida por el SAT. Su rotación no es por seguridad sino por expiración legal. Procedimiento:

1. Obtener nueva FIEL del SAT (certificado `.cer` + llave `.key` + password)
2. Cifrar nueva FIEL: `python backend/app/fiel_config.py save_fiel(...)`
3. Verificar que `fiel_rfc()` devuelve el RFC correcto
4. Eliminar FIEL anterior del filesystem: `rm ~/.cfdi-suite/fiel.enc`

---

## 6. Prevención de Fugas

### 6.1 `detect-secrets` — Baseline Stale

**Estado actual**: `.secrets.baseline` existe (última actualización: 2026-07-06T22:24:28Z) pero está **stale**:

- Referencia archivos que posiblemente ya no existen: `backend/app/services/_experimento_diseno_avanzado/gen_data.py` (líneas 141-155 del baseline)
- Referencia un archivo de frontend con detección de Private Key que podría ser falsa positiva o código eliminado: `frontend/src/components/editor/DocumentSettings.jsx` (línea 157-165 del baseline)

**Regenerar el baseline**:

```bash
# Instalar detect-secrets si no está
pip install detect-secrets

# Escanear todo el repo y generar nuevo baseline
detect-secrets scan --all-files --exclude-files ".*\.(lock|json)$" > .secrets.baseline

# Auditar los resultados manualmente
detect-secrets audit .secrets.baseline
```

**Mantener**:

```bash
# En cada PR, correr:
detect-secrets scan --baseline .secrets.baseline
# Si encuentra algo nuevo, falla — el desarrollador debe auditarlo
```

### 6.2 Pre-commit Hook

Crear `.pre-commit-config.yaml` para prevenir commits con secretos:

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: '\.(lock|json)$'
```

Instalar:

```bash
pip install pre-commit
pre-commit install
```

### 6.3 GitHub Push Protection

GitHub tiene escaneo de secretos built-in. Verificar que esté activado:

```bash
# Verificar configuración actual
gh api repos/{owner}/{repo}/secret-scanning/alerts --jq '.[].state'

# Si no hay datos, activar en Settings → Code security → Secret scanning
```

GitHub detecta patrones como claves de GCP, tokens de Vercel, URLs de Sentry, etc. Las alertas aparecen en la pestaña Security del repositorio.

### 6.4 `.gitignore` — Cobertura de `.env`

**Revisión de `.gitignore:7-8`**:

```gitignore
.env*         # Ignora TODOS los archivos que empiezan con .env
!.env.example # EXCEPTO .env.example (template documentado)
```

Esto cubre:
- `.env` ✔
- `.env.local` ✔
- `.env.production` ✔
- `.env.development` ✔
- `.env.test` ✔

No hay gaps. El patrón es correcto.

**Verificación adicional**:

```bash
# Confirmar que ningún .env (excepto .example) está versionado
git ls-files | grep '\.env' | grep -v '\.env\.example'
# Debe devolver vacío
```

### 6.5 `cors-gcs.json` en `.gitignore`

`.gitignore:46` excluye `cors-gcs.json` del versionamiento. Esto es correcto — la configuración de CORS de GCS no debe versionarse en crudo porque podría contener orígenes de desarrollo. Sin embargo, se recomienda versionar un template `cors-gcs.json.example` (ver `04-infra-gcp.md` §3.1).

---

## 7. Secretos en CI/CD

### 7.1 Reglas de Uso en Workflows

**SIEMPRE**:

```yaml
# Correcto — GitHub auto-maskea el valor en logs
env:
  REDIS_PASSWORD: ${{ secrets.REDIS_PASSWORD }}
```

**NUNCA**:

```yaml
# PELIGRO — expone el secreto en logs
- run: echo "La contraseña es ${{ secrets.REDIS_PASSWORD }}"

# PELIGRO — si el script imprime la variable, se filtra
- run: printenv | grep REDIS
```

### 7.2 Enmascaramiento Indirecto

Si pasás un secreto como argumento a un script, y ese script hace `echo` del argumento, el secreto aparece en logs. GitHub Actions solo enmascara el valor literal del secreto, no transformaciones.

```bash
# PELIGRO — el secreto transformado a base64 NO está maskedo
- run: echo ${{ secrets.GCP_SA_KEY }} | base64
```

### 7.3 Permisos del Workflow de Deploy

**`deploy-backend.yml`** usa:

- `google-github-actions/auth@v2` (línea 18): autentica con `${{ secrets.GCP_SA_KEY }}`. Esta acción maneja la key de forma segura (no la imprime en logs).
- `google-github-actions/deploy-cloudrun@v2` (línea 24): despliega con las env vars definidas en el workflow. Las env vars incluyen secretos (Redis password, Pusher secret, etc.) que se pasan directamente al servicio de Cloud Run. Estos valores NO aparecen en logs de GitHub Actions porque se pasan como argumentos a la acción, no como comandos shell.

**`deploy-frontend.yml`** usa:

- `vercel --prod --token=${{ secrets.VERCEL_TOKEN }}` (línea 22): el token se pasa como flag de CLI. Vercel CLI no imprime el token en stdout, pero cualquier error del CLI que incluya los argumentos podría filtrarlo.

**Recomendación para `deploy-frontend.yml`**: usar variable de entorno en vez de flag:

```yaml
- name: Deploy to Vercel
  working-directory: ./frontend
  run: vercel --prod
  env:
    VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
    VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
    VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
```

### 7.4 `env_vars_update_strategy: overwrite`

`deploy-backend.yml:42` configura `overwrite` (no merge). Esto es una decisión de seguridad positiva:

- Si alguien agrega una variable de entorno manualmente con `gcloud`, el siguiente deploy la borra
- La fuente de verdad es el workflow versionado
- Previene que variables "fantasma" persistan en producción (ver comentario en líneas 29-41)

**Riesgo**: Si se agrega una variable nueva al workflow sin el valor correcto, sobreescribe la variable en producción. Siempre verificar con:

```bash
gcloud run services describe cfdi-suite-api --region=us-central1 \
  --format="json(spec.template.spec.containers[0].env)" | jq .
```

---

## 8. Monitoreo y Alertas

### 8.1 Alertas de GitHub Secret Scanning

Configurar notificaciones para alertas de secretos:

1. Repository Settings → Code security → Secret scanning
2. Enable "Push protection" (bloquea commits que contengan secretos detectados)
3. Suscribirse a notificaciones de nuevas alertas

### 8.2 Auditoría de Acceso a Secrets

GitHub no provee logs de quién accedió a qué secreto. Lo que sí se puede monitorear:

- Quién modificó secrets (Settings → Secrets → Actions secrets management)
- Workflow runs que usaron secrets (visible en cada run)

### 8.3 Alertas de Rotación

Configurar recordatorios cada 90 días para rotar `GCP_SA_KEY`, `REDIS_PASSWORD`, `PUSHER_SECRET`. Forma simple:

```bash
# Agregar a cron local o GitHub Scheduled Reminder
echo "Rotar secretos cfdi_suite: GCP_SA_KEY, REDIS_PASSWORD, PUSHER_SECRET" | \
  mail -s "Rotación de secretos vence en 7 días" security@example.com
```

---

## Checklists

### Quick Wins (hoy)

- [ ] Reclasificar `VERCEL_URL` de GitHub Secret a GitHub Variable (ver §1.2)
- [ ] Reclasificar `PUSHER_KEY` de GitHub Secret a GitHub Variable (ver §1.2)
- [ ] Regenerar `.secrets.baseline` y verificar falsos positivos (ver §6.1)
- [ ] Instalar pre-commit hook con `detect-secrets` (ver §6.2)
- [ ] Activar GitHub push protection en el repositorio (ver §6.3)
- [ ] Verificar que ningún `.env` está versionado (ver §6.4)
- [ ] Cambiar `deploy-frontend.yml` para pasar `VERCEL_TOKEN` por env var, no flag (ver §7.3)

### Medium Effort (esta semana)

- [ ] Migrar `FERNET_KEY` a variable de entorno desde `~/.cfdi-suite/secret.key` (ver §2.4, Opción A)
- [ ] Documentar que credenciales FIEL son efímeras (se pierden al reciclar Cloud Run)
- [ ] Crear `.pre-commit-config.yaml` en la raíz del repo
- [ ] Auditoría de IAM para la SA de GitHub Actions (`GCP_SA_KEY`)

### Long Term (próximo mes)

- [ ] Workload Identity Federation para GitHub Actions (eliminar `GCP_SA_KEY`)
- [ ] Rotación programada de `REDIS_PASSWORD`, `PUSHER_SECRET`, `GCP_SA_KEY`
- [ ] Mover `FERNET_KEY` a Secret Manager si se necesita persistencia entre deploys
- [ ] Evaluar Vault o similar si el número de secretos crece >20
