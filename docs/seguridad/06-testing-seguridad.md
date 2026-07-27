# 06 — Estrategia de Testing de Seguridad

> Stack: FastAPI + Python 3.12 (backend), React 19 + Vite + TypeScript (frontend)
> Scope: SAST, DAST, dependency monitoring, secret detection, CI/CD integration

---

## SAST (Static Application Security Testing)

### 1. `bandit` — Python Static Analysis

**Instalación:**

```bash
pip install bandit
```

**Ejecución local:**

```bash
# Escanear todo el backend, severidad medium en adelante
bandit -r backend/ -ll -f screen

# Salida JSON para CI
bandit -r backend/ -f json -o bandit-report.json

# Suprimir falsos positivos con inline comment
bandit -r backend/ --skip B101,B601  # o: # nosec B101 en el código
```

**Reglas relevantes para este proyecto:**

| Bandit ID | Descripción | Probabilidad en cfdi-suite |
|-----------|-------------|---------------------------|
| B108 | `hardcoded_tmp_directory` | Baja — se usa `tempfile` |
| B301 | `pickle` usage | MEDIA — `catalogs.py:31,54` usa `pickle.loads` sobre DB local (bajo riesgo, ver `red-team-findings.md` V7) |
| B303 | `hashlib.md5` | Baja |
| B307 | `eval` usage | Baja — no detectado |
| B322 | `input()` | Nula |
| B501 | `ssl_cert_reqs` check | ALTA — `pdf.py:74` tiene `ssl_cert_reqs=None` |
| B506 | `yaml.load` | Baja |
| B602 | `subprocess_shell=True` | MEDIA — hay llamadas a subprocess en el wrapper Python |
| B608 | `SQL injection` | Nula — no hay SQL |

**Falsos positivos comunes y cómo suprimirlos:**

```python
# pickle.loads en DB local de solo lectura — suprimido
val = pickle.loads(v)  # nosec B301

# subprocess con lista de args (sin shell=True) — seguro pero bandit lo marca
subprocess.run(["python", wrapper, arg])  # nosec B603
```

**Integración CI — workflow:**

```yaml
# .github/workflows/security-scan.yml (ver 09-ci-cd-hardening.md)
- name: Run bandit
  run: |
    pip install bandit
    bandit -r backend/ -ll -f json -o bandit-report.json
```

**Severidad de fallo:** HIGH y MEDIUM severity findings **fallan el build** en CI. LOW es warning-only.

---

### 2. CodeQL — Python + JavaScript

GitHub CodeQL es gratuito para repositorios públicos. Escanea vulnerabilidades, errores de seguridad, y patrones OWASP.

**Workflow completo en `09-ci-cd-hardening.md` §Security-scan workflow.**

**Lenguajes habilitados:** `python` (backend), `javascript-typescript` (frontend).

**Triggers:** on push to main + on pull_request (opened, synchronize).

**Tiempo estimado de scan:** ~2-5 min (repo pequeño).

---

### 3. `react-doctor` — Estado actual

**Archivo:** `.github/workflows/react-doctor.yml`

**Estado:** Ejecutándose en CI, modo **advisory** (informa pero no falla).

**Para hacerlo blocking:**

```yaml
# En .github/workflows/react-doctor.yml, descomentar:
with:
  directory: frontend
  blocking: error       # Falla en nuevos findings de severidad "error"
  # O: blocking: warning  # Falla en cualquier nuevo finding
```

**Reglas suprimidas:** Documentadas en `frontend/doctor.config.ts:1-37` y `docs/react-doctor-veredictos.md`.

**Recomendación:** Graduar a `blocking: error` después de 2 sprints de uso advisory. Dar tiempo al equipo para acostumbrarse y limpiar findings preexistentes.

---

### 4. `npm audit` — Frontend Dependencies

**Estado actual:** NO se ejecuta en CI. `package.json` no tiene script de audit.

**Agregar a `package.json`:**

```json
"scripts": {
  "audit": "npm audit --audit-level=high",
  "audit:fix": "npm audit fix"
}
```

**Integración CI:**

```yaml
- run: npm ci
- run: npm audit --audit-level=high
  # Falla el build si hay vulnerabilidades high o critical
```

**Severidad de fallo:** HIGH y CRITICAL fallan. MODERATE es warning (continue-on-error). LOW ignorado.

---

### 5. `safety` — Python Dependencies

**Instalación:**

```bash
pip install safety
```

**Ejecución:**

```bash
# Escanear dependencias contra base de datos de CVEs
safety check -r backend/requirements.txt --output json

# Ignorar CVEs sin fix disponible
safety check -r backend/requirements.txt --ignore 70612
```

**Integración CI — workflow:**

```yaml
- name: Safety check
  run: |
    pip install safety
    safety check -r backend/requirements.txt --ignore 70612
  continue-on-error: false  # Falla en hallazgos
```

**Alternativa gratuita si safety requiere API key:**

```bash
pip install pip-audit
pip-audit -r backend/requirements.txt
```

---

## DAST (Dynamic Application Security Testing)

### OWASP ZAP

**Cuándo ejecutar:** Después de deploys mayores (cada sprint, no por commit).

**Setup básico — escaneo pasivo:**

```bash
# Docker — escanear la URL de Cloud Run
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app \
  -z "-config api.disablekey=true" \
  -r zap-report.html

# Escaneo activo (más agresivo — solo contra staging):
docker run -t owasp/zap2docker-stable zap-full-scan.py \
  -t https://cfdi-suite-api-hfg67q6kbq-uc.a.run.app \
  -z "-config api.disablekey=true" \
  -r zap-full-report.html
```

**Qué buscar:**
- Headers de seguridad faltantes (CSP, HSTS, X-Frame-Options)
- Cookies sin flags Secure/HttpOnly (N/A — no hay cookies)
- XSS reflejado en parámetros de query string
- Información de servidor en headers de respuesta
- Endpoints con métodos HTTP innecesarios

**Precaución:** ZAP activo genera tráfico real. Puede disparar Cloud Tasks, consumir créditos Diverza, y generar PDFs. Usar solo en entorno de staging con Diverza mockeado.

---

## Dependency Monitoring

### Dependabot

**Archivo:** `.github/dependabot.yml` (config en `09-ci-cd-hardening.md`)

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "security"
    versioning-strategy: "increase"

  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "security"
```

**Auto-merge criteria:** NO auto-merge. Todas las PR de Dependabot requieren:
1. CI verde (security-scan, react-doctor, build)
2. Review manual (revisar changelog de la dependencia)
3. Si es security fix: merge inmediato tras review
4. Si es minor/patch bump: puede esperar al día siguiente

---

## Secret Detection

### `detect-secrets` — Pre-commit

**Estado actual:** `.secrets.baseline` existe (2026-07-06) pero stale — incluye archivos posiblemente inexistentes (`_experimento_diseno_avanzado/gen_data.py`, `DocumentSettings.jsx`).

**Regenerar baseline:**

```bash
pip install detect-secrets
detect-secrets scan --all-files --exclude-files ".*\.(lock|json)$" > .secrets.baseline
detect-secrets audit .secrets.baseline  # Revisar manualmente
```

**Pre-commit hook (`ver 09-ci-cd-hardening.md` §Pre-commit):**

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

**Actualizar baseline después de cambios:**

```bash
# Después de mergear features que agregan nuevas strings
detect-secrets scan --all-files --baseline .secrets.baseline
# Si no hay cambios: baseline está al día
# Si hay nuevos hallazgos: auditarlos
```

### GitHub Secret Scanning Push Protection

**Activar en repo settings:** Settings → Code security → Secret scanning → Push protection (enable).

Esto bloquea commits que contengan patrones de secretos conocidos (GCP keys, Vercel tokens, AWS keys, etc.).

---

## Manual Testing Checklist

### Pentest Interno (cada 6 meses)

**Schedule:** Julio 2026, Enero 2027, Julio 2027

**Qué probar:**

| Item | Endpoint / Superficie | Método |
|------|----------------------|--------|
| XXE injection | `POST /api/cfdi/analyze`, `POST /api/cfdi/batch/analyze`, `POST /api/cfdi/pdf/start` | XML con `<!ENTITY>` en cada campo (Rfc, Nombre, UUID) |
| XML Bomb | Endpoints anteriores | Billion Laughs (10 niveles con 10 entidades por nivel) |
| Zip path traversal | `POST /api/cfdi/pdf/start-zip` | ZIP con entradas `../../../tmp/evil.xml` |
| Rate limit bypass | Todos los POST endpoints | Script con 1000 requests secuenciales |
| SSRF via Diverza URL | `POST /api/sat/enquiry` | UUID con caracteres especiales, path traversal en UUID |
| ReDoS | `PUT /api/templates/{id}/design` | Template config con miles de columnas |
| Excel formula injection | `POST /api/sat/enquiry/batch` | XLSX con celdas `=cmd|'/C calc.exe'!A0` en campos RFC/UUID |
| Job ID enumeration | `GET /api/sat/enquiry/batch/{id}/result` | 1000 UUID4 al azar → ver cuántos existen |
| Internal endpoint bypass | `/api/internal/generate-pdf`, `/api/internal/extract-zip` | Requests directos con y sin header `x-cloudtasks-queuename` |
| Pusher channel subscribe | Todos los canales batch | Suscribirse con key pública y batch IDs aleatorios |

### Pentest Externo (anual)

**Plataformas:** HackerOne, Bugcrowd, Cobalt.io, o freelance.

**Freelance perfil:** Pentester con experiencia en OWASP Top 10, APIs REST, y GCP. Presupuesto estimado: $2,000-$5,000 USD por engagement de 2 semanas.

---

## CI/CD Integration Map

```
Pre-commit (local, antes de commit):
  └── detect-secrets             ← Bloquea el commit si detecta secretos

PR open / push to any branch:
  └── react-doctor               ← Advisory (próximo: blocking=error)
  └── CodeQL                     ← Falla en error/warning
  └── bandit                     ← Falla en HIGH/MEDIUM
  └── safety / pip-audit         ← Falla en cualquier CVE
  └── npm audit                  ← Falla en HIGH/CRITICAL

Push to main:
  └── deploy-backend             ← Despliega a Cloud Run
  └── deploy-frontend            ← Despliega a Vercel
  └── Dependabot (semanal)       ← Abre PRs para actualizaciones

Sprint (manual):
  └── OWASP ZAP baseline         ← Después de deploy mayor
```

**Leyenda:**
- 🔴 **Bloqueante:** Falla el build / bloquea el merge
- 🟡 **Warning:** Reporta pero no bloquea (se convierte en blocking en <30 días)
- 🟢 **Informational:** Solo visible en logs

---

## Estimated Effort Summary

| Tool | Setup (h) | Maintenance (h/mes) | State |
|------|-----------|---------------------|-------|
| bandit | 1 | 0.5 | NOT DEPLOYED |
| CodeQL | 0.5 | 0 | NOT DEPLOYED |
| react-doctor | 0 | 0.25 | ADVISORY ONLY |
| npm audit | 0.5 | 0.25 | NOT DEPLOYED |
| safety/pip-audit | 0.5 | 0.25 | NOT DEPLOYED |
| Dependabot | 0.5 | 0.5 | NOT DEPLOYED |
| detect-secrets pre-commit | 0.5 | 0.25 | BASELINE STALE |
| OWASP ZAP | 1 | 0.5 (por sprint) | NOT DEPLOYED |
| **Total initial** | **4.5h** | **2.5h/mes** | |

---

> Referencia: https://owasp.org/www-project-web-security-testing-guide/
