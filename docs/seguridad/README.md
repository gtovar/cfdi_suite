# Seguridad — cfdi_suite

> Tax invoice inspector tool. React + FastAPI + GCP Cloud Run.
> Public web app, no auth. Handles Mexican CFDI XMLs with RFC tax IDs.

---

## Quicklinks

| Necesitas... | Lee... |
|---|---|
| Entender conceptos base y OWASP aplicados | [01-fundamentos.md](01-fundamentos.md) |
| Asegurar el frontend (XSS, CSP, CORS, Pusher) | [02-frontend.md](02-frontend.md) |
| Asegurar el backend (XXE, rate limiting, errores) | [03-backend.md](03-backend.md) |
| Hardening de infraestructura GCP | [04-infra-gcp.md](04-infra-gcp.md) |
| Manejar secretos (rotacion, clasificacion) | [05-secretos.md](05-secretos.md) |
| Herramientas de testing de seguridad | [06-testing-seguridad.md](06-testing-seguridad.md) |
| Responder a incidentes (2am playbook) | [07-incident-response.md](07-incident-response.md) |
| Ver hallazgos actuales (living document) | [08-auditoria-actual.md](08-auditoria-actual.md) |
| Configurar CI/CD seguro | [09-ci-cd-hardening.md](09-ci-cd-hardening.md) |
| Ver hallazgos del red team (adversarial) | [red-team-findings.md](red-team-findings.md) |
| Ver decisiones del CTO (triage) | [red-team-reconciliation.md](red-team-reconciliation.md) |

---

## Ultima Auditoria

**2026-07-25** — Auditoria de 4 agentes (security senior, architect, red team, CTO).

**Segunda ronda — 2026-07-25 (4 agentes automatizados):** Security-Frontend, Security-Backend, Security-Infra, Security-Secrets verificaron todos los quick wins y encontraron 11 hallazgos nuevos.

**Hallazgos:**
- 3 CRITICAL (arreglar esta semana)
- 9 HIGH (este sprint) — 3 nuevos de agentes
- 14 MEDIUM (backlog) — 5 nuevos de agentes
- 8 LOW (nice to have) — 3 nuevos de agentes

**Total: 34 hallazgos.** 39 quick wins sin implementar.

Ver [08-auditoria-actual.md](08-auditoria-actual.md) para inventario completo y estados.

---

## Estado General

- Redis password rotado (incidente Jun-Jul 2026) y migrado a GitHub Secrets
- 34 hallazgos del red team bajo triage → ver [red-team-reconciliation.md](red-team-reconciliation.md)
- Documentacion de seguridad creada por primera vez (Jul 2026)
- CI/CD security scanning: NOT DEPLOYED (workflows en [09-ci-cd-hardening.md](09-ci-cd-hardening.md))
- Rate limiting: NOT DEPLOYED (slowapi pendiente)
- **Verificacion automatizada 2026-07-25:** 39/39 quick wins sin implementar. 11 nuevos hallazgos encontrados. Cero fixes aplicados desde auditoria original.

---

## Top 5 CTO Decisions (Jul 2026)

1. **XXE is #1 priority** — Fix lxml parser today. `/proc/self/environ` exposure is a same-week emergency.
2. **OIDC for Cloud Tasks** — The header check stays as defense-in-depth, but real fix is OIDC tokens.
3. **Rate limiting waits one sprint** — Implement `slowapi` before next feature work.
4. **Pusher stays public until auth ships** — UUID channel names + disabled client events = good enough.
5. **Supply chain scanning ships today** — `bandit`, `safety`, `npm audit`, CodeQL, Dependabot. One-time setup, zero maintenance.

---

## CRITICAL — Arreglar Esta Semana

1. **XXE via lxml** — `canvas_service.py:835,869,983` → `resolve_entities=False, no_network=True`
2. **Cloud Tasks sin OIDC** — `task_dispatcher.py:30-36` → agregar `oidc_token`
3. **Cross-session `_job_results` leak** — `sat_enquiry.py:24` → binding por IP o eliminacion de dict
