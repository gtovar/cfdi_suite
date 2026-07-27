# B-lite: identidad real en el backend

> **Arranca desde aquí.** No necesitas `prompt-fase2.md` ni
> `prompt-fase2-bloques-6-9.md` — eso ya pasó. Todo lo que hay que saber está
> en este archivo. Escrito el 2026-07-27 al cerrar la Fase 2 completa.

---

## Dónde estamos

Rama **`seguridad/fase-2`** con **49 commits** sobre `main`. **Nada desplegado**
en Cloud Run (sigue corriendo con la compute SA default). La deuda de
despliegue del paso 12 (OIDC en dos fases, drenar la cola) sigue vigente —
léela en `docs/seguridad/prompt-fase2-bloques-6-9.md` §"Deuda de despliegue".

### Lo que se cerró en los bloques 6–9 (esta sesión)

| Bloque | Hallazgos cerrados |
|---|---|
| 6 — Vercel headers | #24 |
| 7 — CI/CD + supply chain | #7, #29, #32 (sin cambios), #28, #20, #27/#34, #16/#34, #49, #53 (documentado) |
| 8 — MEDIUM/LOW mecánicos | #10, #43, #44, #46 (subsumido), #48, #51, #52, #55, #56, #57, #58, #59, #60, #61, #62, NUEVO-BATCHID |
| 9 — MEDIUM restantes | #5, #15, #13, #14, #11 (auditoría — sin SSTI), #40, #41, #33 |

### Lo que ya no está roto

Las variables de Vercel `VITE_PUSHER_KEY` y `VITE_PUSHER_CLUSTER` ya tienen
valor real. El fix de #27/#34 (quitar la key hardcodeada de `pdf-download.ts`)
ya no va a reventar en producción.

### Pendientes que requieren clicks en consola (no código)

- **#22**: mover `PUSHER_KEY` y `VERCEL_URL` de Secrets a Variables en GitHub
- **#30**: crear `fernet-key` en GCP Secret Manager y referenciarlo con `--set-secrets`
- **#31**: SA dedicada para el batch shard job

---

## Baselines (sin cambios)

```bash
cd /Users/gil/Documents/cfdi_suite
git checkout seguridad/fase-2
python3 -m pytest backend/tests/ -q          # 329 passed
python3 -m ruff check backend/app/           # 43 errors (preexistentes)
cd frontend && npm run lint && npm test && cd ..  # 6 TS errors preexistentes, 120 tests
```

---

## El corte: B-lite

La Fase 2 termina aquí. **La API sigue abierta a internet sin autenticación de
usuario** — cero `Depends()` en `backend/app/`. Eso cierra B-lite.

### Qué es B-lite

Un `Depends()` global de identidad verificada, más aislamiento por tenant del
material de FIEL y de los emisores. Cierra **14 hallazgos abiertos**, incluidos
dos CRITICAL con panel unánime (#36 y #37, la e.firma) y la validación RFC
contra el SAT.

### Lo que ya se sabe

1. **Plan de Vercel: Hobby** (confirmado en vivo 2026-07-27). No hay Deployment
   Protection — Vercel no filtra requests por OIDC. **Toca identidad en la
   aplicación.**

2. **Tres llamadores que no son un navegador:**
   - Cloud Tasks → ya resuelto con OIDC (paso 12, `verify_cloud_tasks`)
   - Cloud Run Job `cfdi-batch-shard` → necesita token o endpoint interno
   - El backend que se auto-invoca vía `API_URL` → mismo problema

3. **El token OIDC local dice `"plan":"hobby"`.** El dato viene de un token de
   entorno de desarrollo; no es concluyente pero es el único indicio que hay.
   Ya se confirmó en consola.

### Lo que NO está decidido

- **Cuántos usuarios va a haber.** "Una identidad" y "múltiples tenants
  aislados" son sistemas distintos. Esto define si alcanza con un secreto
  compartido (Bearer token fijo) o se necesita OAuth/OIDC con proveedor.

- **Qué proveedor de identidad.** Google IAP (requiere Load Balancer, costo
  extra), Google Identity Platform/Firebase Auth (gratis hasta cierto límite),
  Cloud Run IAP (solo para tráfico interno), o un simple Bearer token
  compartido (mínimo viable para un solo usuario).

- **Dónde vive el material de FIEL.** Hoy está en el filesystem de Cloud Run
  (efímero, se pierde en cold start). Con identidad y tenant isolation, se
  mueve a GCS con clave de encriptación por tenant.

### Qué NO se toca

**#36 y #37** (FIEL usada, sobrescrita y borrada sin auth — HIGH, panel
unánime). No los arregles con guards ad-hoc. El fix es B-lite completo.

Tampoco: **#45** (batch status sin auth), **#12** (canales de Pusher
públicos), **#6** (rate limiting), `BATCH6-CANDIDATE-12`, los datos visibles
en React DevTools, la inyección en headers de respuesta, `NaN`/`Infinity`
desde XML, las opciones de subprocess del engine, el render del XML en el DOM,
**#23** (timeout de Cloud Run).

### Cómo arrancar B-lite

No hay specs escritas. Esto no es aplicar un diff — es una decisión de
arquitectura. El flujo es:

1. **Definir el mecanismo de identidad** según cuántos usuarios y qué
   proveedor. La opción más barata para Hobby + un solo usuario es un Bearer
   token fijo en Secret Manager, rotado a mano, y verificado en un
   `Depends()` global.

2. **Definir el modelo de tenant.** Si es un solo tenant, el `sub` del token
   es constante y el aislamiento es trivial. Si son múltiples, cada tenant
   tiene su propio material de FIEL y emisores, aislados por `sub`.

3. **Resolver los tres llamadores no-navegador** para que no rompan con el
   `Depends()` global.

4. **Escribir las specs una por una**, con antes/después y comando de
   verificación, como en `plan-fixes.md`.

5. **Aplicar en orden**, un commit por fix.

---

## Qué esperar del hook de pre-commit

`.pre-commit-config.yaml` está versionado. Si no has corrido `pre-commit
install`, el hook manual en `.git/hooks/pre-commit` sigue activo. En cualquier
caso, tres cosas van a pasar al commitear:

- **react-doctor** imprime 13 hallazgos preexistentes. No bloquean.
- **`detect-secrets` reescribe `.secrets.baseline`** cuando cambian números de
  línea y aborta el commit pidiendo `git add .secrets.baseline`. Antes de
  añadirlo, verifica que sólo cambiaron números de línea:
  ```bash
  python3 -c "
  import json,subprocess
  a=json.loads(subprocess.run(['git','show','HEAD:.secrets.baseline'],capture_output=True,text=True).stdout)
  b=json.load(open('.secrets.baseline'))
  f=lambda d:{(k,r['type'],r['hashed_secret']) for k,rs in d.get('results',{}).items() for r in rs}
  print('nuevos:', f(b)-f(a) or 'ninguno', '| desaparecidos:', f(a)-f(b) or 'ninguno')"
  ```
- **`detect-secrets` da falsos positivos** con cadenas de 32 hex (UUID de
  prueba). Se resuelven con `# pragma: allowlist secret` en la línea.

---

## Archivos de referencia

- `docs/seguridad/plan-fixes.md` — specs de todos los fixes (lo cerrado y lo
  pendiente)
- `docs/seguridad/prompt-fase2.md` — decisión de auth original y tabla "Qué NO
  se toca"
- `docs/seguridad/prompt-fase2-bloques-6-9.md` — deuda de despliegue,
  baselines anteriores, errores de la spec
- `docs/seguridad/registro-unificado.md` — registro completo de hallazgos
- `PROJECT_STATE.md` — checkpoint y baselines de la sesión anterior
