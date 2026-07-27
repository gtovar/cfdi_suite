# 09 — CI/CD Security Hardening

> Guia completa para asegurar el pipeline de CI/CD de cfdi-suite.
> Todos los YAML son copy-paste ready para GitHub Actions.

---

## Estado Actual del CI/CD

| Workflow | Archivo | Trigger | Que hace |
|----------|---------|---------|----------|
| Deploy Backend | `deploy-backend.yml` | Push a main (backend/**) | Despliega a Cloud Run con gcloud |
| Deploy Frontend | `deploy-frontend.yml` | Push a main (frontend/**) | Despliega a Vercel con vercel CLI |
| React Doctor | `react-doctor.yml` | PR + push a main | Escanea frontend, advisory mode |
| Cloud Build | `cloudbuild.yaml` | Manual | Build alternativo via gcloud |

**Gaps:** Zero security scanning. Zero dependency monitoring. Zero secret detection in CI.

---

## Nuevos Workflows (Copy-Paste Ready)

### 1. `security-scan.yml` — SAST + Dependency Scan

Crear `.github/workflows/security-scan.yml`:

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
          # -ll = low severity and above; fails on HIGH/MEDIUM by default

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
        # Fails on HIGH or CRITICAL vulns; MODERATE passes
```

**Que falla el build:**

- `bandit`: findings de severidad HIGH o MEDIUM (default de `-ll`)
- `safety`: cualquier CVE conocido sin fix
- `npm audit`: HIGH o CRITICAL

**Que no falla:** bandit LOW, npm audit MODERATE, npm audit LOW.

---

### 2. `codeql.yml` — GitHub CodeQL Analysis

Crear `.github/workflows/codeql.yml`:

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

**Nota:** CodeQL es gratuito para repositorios publicos. El scan toma 2-5 min para este size de repo.

---

## Dependabot

### `.github/dependabot.yml`

Crear en la raiz del repo:

```yaml
version: 2
updates:
  # Python backend
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
      - "gil"  # Replace with actual GitHub username
    commit-message:
      prefix: "chore(deps)"
      prefix-development: "chore(deps-dev)"
      include: "scope"

  # NPM frontend
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
      - "gil"  # Replace with actual GitHub username
    commit-message:
      prefix: "chore(deps)"
      prefix-development: "chore(deps-dev)"
      include: "scope"

  # GitHub Actions (workflow dependencies)
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    labels:
      - "dependencies"
      - "ci"
```

**Auto-merge policy:** NO auto-merge. Todas las PRs de Dependabot requieren:
1. CI verde (security-scan + react-doctor + build)
2. Review manual del changelog de la dependencia
3. Security fixes: merge inmediato tras review
4. Minor/patch bumps: pueden esperar al dia siguiente

---

## Pre-commit Hooks

### `.pre-commit-config.yaml`

Crear en la raiz del repo:

```yaml
repos:
  # Secret detection — bloquea commits con secretos
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: '\.(lock|json|baseline)$'

  # Python linter
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: ['--fix']
      - id: ruff-format

  # Generic checks
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

  # Frontend formatting
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        types_or: [javascript, jsx, typescript, tsx, css, json, yaml]
        additional_dependencies: ['prettier@3.4.0']
```

**Instalacion:**

```bash
pip install pre-commit
pre-commit install
# Ahora cada git commit ejecuta automaticamente estos hooks
```

**Actualizar baseline despues de nuevo codigo:**

```bash
detect-secrets scan --all-files --baseline .secrets.baseline
detect-secrets audit .secrets.baseline  # Revisar hallazgos nuevos manualmente
```

---

## Branch Protection Rules

Configurar en GitHub repo → Settings → Branches → Add rule:

**Target:** `main`

```
[x] Require a pull request before merging
    [x] Require approvals: 1
    [x] Dismiss stale pull request approvals when new commits are pushed

[x] Require status checks to pass before merging
    [x] Require branches to be up to date before merging
    Status checks:
    - security-scan / python-sast
    - security-scan / npm-audit
    - react-doctor / react-doctor
    - CodeQL / Analyze (python)
    - CodeQL / Analyze (javascript-typescript)
    - deploy-backend / deploy (si se puede — solo corre en main)
    - deploy-frontend / deploy (solo corre en main — usar "build" job en PR)

[x] Require conversation resolution before merging

[ ] Do not allow bypassing the above settings
    [x] Include administrators

[x] Restrict who can push to matching branches
    (solo maintainers)

[ ] Allow force pushes          ← DEBE estar DESHABILITADO
[ ] Allow deletions              ← DEBE estar DESHABILITADO
```

---

## GitHub Secret Scanning Push Protection

**Activar:** Settings → Code security → Secret scanning → Push protection → Enable.

Esto bloquea commits que contengan:
- GCP service account keys
- Vercel tokens
- Sentry DSNs
- AWS keys
- Generic private keys
- Y otros 200+ patrones

Los desarrolladores pueden bypassear con un comentario en el commit si es falso positivo.

---

## Deployment Safeguards

### Cloud Run Gradual Rollout

Actualmente `deploy-backend.yml` hace deploy directo (100% trafico a la nueva revision). Para produccion con usuarios reales, considerar despliegue gradual:

```yaml
# deploy-backend.yml — flags:
flags: |
  --allow-unauthenticated
  --cpu=2
  --memory=2Gi
  --max-instances=10
  --timeout=1800
  --concurrency=5
  --service-account=cfdi-suite-api-sa@ultra-acre-431617-p0.iam.gserviceaccount.com
  --no-traffic  # Desplegar sin enviar tráfico (manual roll-out)

# Y después del deploy, migrar tráfico gradual:
# gcloud run services update-traffic cfdi-suite-api \
#   --region=us-central1 \
#   --to-revisions=LATEST=10  # 10% a nueva, 90% a estable
```

Para el MVP actual (sin usuarios), deploy directo es aceptable. Gradual rollout se necesita cuando haya trafico real.

### Vercel Preview Deployments

Ya funciona automaticamente: cada PR genera un preview deployment con URL unica. Esto es correcto — no necesita cambios.

### Redis Key Migration (cuando se modifiquen estructuras)

No hay SQL, pero si se cambia la estructura de keys de Redis (ej. `batch:{id}:*` → `v2:batch:{id}:*`):

```python
# Patrón de migración sin downtime:
# 1. Escribir en ambos formatos (viejo y nuevo) durante N días
# 2. Leer del nuevo primero, fallback al viejo
# 3. N días después, dejar de escribir el viejo
# 4. N+7 días después, TTL del viejo expira naturalmente
```

---

## Pipeline Integration Map (Final)

```
┌─ git commit (local) ──────────────────────────┐
│  pre-commit: detect-secrets + ruff + prettier  │
└────────────────────────────────────────────────┘
                    │
                    ▼
┌─ git push → PR open ──────────────────────────────────────────┐
│  ✓ security-scan (bandit + safety + npm audit)  ← BLOCKS      │
│  ✓ CodeQL (python + javascript-typescript)      ← BLOCKS      │
│  ✓ react-doctor                                ← advisory → error │
│  ✓ Vercel preview deployment (automatic)         ← INFO        │
└────────────────────────────────────────────────────────────────┘
                    │
                    ▼ (merge a main)
┌─ push to main ────────────────────────────────────────────────┐
│  ✓ security-scan (same as PR)                   ← BLOCKS      │
│  ✓ CodeQL (same as PR)                          ← BLOCKS      │
│  ✓ react-doctor (full scan)                     ← advisory    │
│  ✓ deploy-backend → Cloud Run                    ← AUTO        │
│  ✓ deploy-frontend → Vercel                      ← AUTO        │
│  ✓ Dependabot (weekly, opens PRs)                ← AUTO        │
└────────────────────────────────────────────────────────────────┘
                    │
                    ▼ (sprint — manual)
┌─ post-deploy ──────────────────────────────────────────────────┐
│  ○ OWASP ZAP baseline scan (staging URL)                      │
│  ○ Pentest manual checklist (cada 6 meses)                    │
└────────────────────────────────────────────────────────────────┘
```

**Leyenda:**
- ✓ = Ejecutandose automaticamente
- ○ = Ejecucion manual
- ← BLOCKS = Falla el build / bloquea merge
- ← advisory → error = Advisorio hoy, planeado blocking en <30 dias
- ← AUTO = Automatico, no bloqueante

---

## Setup Checklist (Nuevos Workflows)

```
□ Crear .github/workflows/security-scan.yml (copy-paste arriba)
□ Crear .github/workflows/codeql.yml (copy-paste arriba)
□ Crear .github/dependabot.yml (copy-paste arriba)
□ Crear .pre-commit-config.yaml (copy-paste arriba)
□ Ejecutar: pre-commit install (local)
□ Regenerar .secrets.baseline (local)
□ Crear PR con todos estos archivos
□ Verificar que security-scan y CodeQL corren en el PR
□ Mergear el PR
□ Configurar branch protection en GitHub Settings
□ Activar push protection en GitHub Settings
□ Verificar que Dependabot abre PRs (esperar hasta el proximo lunes)

Tiempo total estimado: 4h
```

---

> Todos los YAML en este doc son copy-paste listos. Ajustar `reviewers` en `dependabot.yml` al username real de GitHub.
