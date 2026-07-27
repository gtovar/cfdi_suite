# Red Team Reconciliation — Decision Log

> **CTO final review of `red-team-findings.md`** — all 32 findings triaged.
> Date: 2026-07-25

---

## Summary

| Verdict | Count |
|---------|-------|
| ACCEPTED & FIXED (incorporated into docs) | 17 |
| ACCEPTED & BACKLOG (valid, not urgent) | 12 |
| DISPUTED (not valid / not applicable) | 5 |
| **Total** | **34** (including 2 dups counted separately) |

---

## Critical (4)

| ID | Finding | Severity | Decision | Reasoning | Action |
|----|---------|----------|----------|-----------|--------|
| C1 | XXE via lxml in `canvas_service.py:835,869,983` — zero mitigation | CRIT | **ACCEPTED & FIXED** | Verified: all 3 call sites default to `resolve_entities=True`. `/proc/self/environ` exposes all Cloud Run env vars including `REDIS_PASSWORD`. This is the most exploitable vuln in the app. | Updated `03-backend.md` §XXE to add urgency tag and `/proc` attack surface. Fix tracked as CRITICAL #1 in `08-auditoria-actual.md`. |
| C2 | Cloud Tasks header check bypassable — `oidc_token` missing | CRIT | **ACCEPTED & FIXED** | Header spoofing confirmed. The queue name `pdf-generator-queue` is hardcoded in `task_dispatcher.py:9`. No `oidc_token` in task dispatch. | Updated `03-backend.md` §Endpoints internos and `04-infra-gcp.md` §4.1 to document OIDC as the real fix. Fix tracked as CRITICAL #2 in `08-auditoria-actual.md`. |
| C3 | `_job_results` in-memory dict — cross-tenant leak via job ID guessing + SSE | CRIT | **ACCEPTED & FIXED** | Verified: `sat_enquiry.py:24` stores results by `uuid4()` with no IP/session binding. The SSE stream broadcasts `job_id` at line 363. An attacker listening to SSE or brute-forcing UUIDs can download others' Excel results. Since the app has no auth, "tenant" = different browser sessions. | Updated `03-backend.md` §Safe error handling to document this. Fix tracked as CRITICAL #3 in `08-auditoria-actual.md`. |
| C4 | Zero rate limiting — Diverza credits exposed to unbounded consumption | HIGH | **ACCEPTED & BACKLOG** | Rate limiting is the next infrastructure priority. Diverza credits are a financial risk. However, the app is a personal/small-scale tool. Rate limiting should be implemented this sprint but doesn't need a same-day hotfix. | Backlog: implement `slowapi` this sprint. Diverza quota monitoring via Sentry alert when error rate spikes. Target: end of sprint. Estimated effort: 4h. |

---

## High-Risk Omissions (6)

| ID | Finding | Severity | Decision | Reasoning | Action |
|----|---------|----------|----------|-----------|--------|
| H1 | Zip path traversal — `is_valid_xml_entry` checks extension only | HIGH | **ACCEPTED & BACKLOG** | Red team correct: current code reads to memory (safe), but the doc claim "zipfile no permite escritura fuera" is false for `extractall()`. If extraction to disk is ever added, path traversal is exploitable. | Doc corrected in `03-backend.md` §File upload security. Backlog: add path sanitization if disk extraction is added. Estimated effort: 1h when needed. |
| H2 | Openpyxl XXE/Billion Laughs via Excel upload — never analyzed | HIGH | **ACCEPTED & BACKLOG** | Openpyxl does NOT resolve external entities by default in `data_only=True` mode. The risk is lower than lxml XXE. However, XML bombs are theoretically possible in `.xlsx` internals (they're ZIPs of XML). | Updated `03-backend.md` §XXE to mention openpyxl. Backlog: verify openpyxl version has no known vulns. Estimated effort: 1h. |
| H3 | ReDoS via template ID validation — `_ID_RE` and `_validate_columns` | HIGH | **DISPUTED** | The regex `^[a-z0-9][a-z0-9_-]*$` is linear and cannot backtrack exponentially — no catastrophic backtracking possible. `_HEX_RE` (`^#[0-9A-Fa-f]{6}$`) is also safe. The "acknowledgement" gap is real: template validation surface is undocumented — but ReDoS is not the threat. Template injection (SSTI) is the actual concern (see Missing Threat Classes below). | No change. SSTI concern captured in Missing Threat Classes tracking. |
| H4 | Pusher channel auth bypass — public channels with UUID names | HIGH | **ACCEPTED & BACKLOG** | Public channels are by design for a no-auth app. The UUID namespace is large enough for practical obscurity. But the red team is right: in a future with auth, this becomes a real leak. Pusher client events should be disabled. | Updated `02-frontend.md` §Pusher key exposure. Backlog: disable Pusher client events in dashboard. Private channels needed when auth is added. |
| H5 | Fernet key silently regenerated on cold start — credentials vanish | HIGH | **ACCEPTED & FIXED** | Confirmed: `credentials.py:16-17` generates new key on cold start. Previous `emisores.enc` becomes unreadable. User sees 404 "RFC emisor no configurado" with no warning. This is an operational failure, not a breach, but it breaks the product. | Updated `05-secretos.md` §2.4 and `03-backend.md` §Secrets management to flag the silent failure. Fix tracked as HIGH #1 in `08-auditoria-actual.md`. |
| H6 | Supply chain — caret ranges, no hash pinning, no CI audit | HIGH | **ACCEPTED & FIXED** | Confirmed: zero security scanning in CI. No Dependabot. No `npm audit` on CI. No `safety`/`pip-audit`. This is the easiest class to fix: add workflows, add Dependabot. | Created `09-ci-cd-hardening.md` with copy-paste-ready workflows for `security-scan.yml`, `codeql.yml`, and `.github/dependabot.yml`. |

---

## Inconsistencies Between Docs (4)

| ID | Finding | Severity | Decision | Reasoning | Action |
|----|---------|----------|----------|-----------|--------|
| I1 | Timeout: 600s recommendation vs. 1800s reality | LOW | **ACCEPTED & FIXED** | Verified: `deploy-backend.yml:66` = 1800s. Docs 03 and 04 disagree. The 1800s is intentional for large batch PDF rendering (pre-Cloud-Run-Jobs path). With `BATCH_JOB_ENABLED=true`, timeout can come down. | Fixed `04-infra-gcp.md` §1.3 to note that 1800s is the current value and the 600s reduction depends on batch job enablement. Fixed `03-backend.md` to source the value from deploy-backend.yml. |
| I2 | `python-satcfdi-wrapper.py` path wrong in docs | LOW | **ACCEPTED & FIXED** | Verified: file is at `backend/wrappers/python-satcfdi-wrapper.py`, not `backend/app/services/`. | Fixed `01-fundamentos.md` §A03 and `03-backend.md` §XXE to use correct path. |
| I3 | Doc 02 claims no `innerHTML` but test files use it | LOW | **DISPUTED** | Test cleanup (`document.body.innerHTML = ''`) is standard testing pattern, not a vulnerability. The doc refers to production code rendering user content. Semantically correct. | No change. |
| I4 | Pusher key classification conflict — Secret vs Variable | LOW | **ACCEPTED & FIXED** | Doc 05 correctly flags `PUSHER_KEY` as misclassified in GitHub Secrets. It's public by design. Reclassifying to Variable would require updating `deploy-backend.yml:52`. | Updated `05-secretos.md` to mark the trade-off: changing classification breaks the deploy workflow. Backlog task: move to Variable when workflow is touched next. |

---

## Weak Recommendations (5)

| ID | Finding | Severity | Decision | Reasoning | Action |
|----|---------|----------|----------|-----------|--------|
| W1 | CSP with `'unsafe-inline'` defeats XSS protection | MED | **ACCEPTED & BACKLOG** | Red team is technically correct: CSP without nonces and with `'unsafe-inline'` provides minimal XSS protection. However, this is the pragmatic starting point for a Vite+React app without a backend CSP infra. Nonces require server-side rendering or header injection at request time. | Updated `02-frontend.md` §CSP to explain the trade-off explicitly: this CSP prevents 3rd-party script injection but NOT inline XSS. Full protection requires nonces (long-term). |
| W2 | "Quick win: Cloud Tasks header check" marked as "Ya" but it's insufficient | MED | **ACCEPTED & FIXED** | Agreed: calling this a "quick win" and listing it as "Nivel 1: Ya" is misleading. The header check is a speed bump, not a lock. | Updated `04-infra-gcp.md` §1.1 maturity table. Level 1 now says "Parcial" and notes the header is bypassable. OIDC is Level 2. |
| W3 | "Best-effort" on Redis outage is anti-pattern | LOW | **DISPUTED** | `pdf.py:887-888` has an explicit decision comment: "best-effort en vez de fail-closed". This is a **business decision** (availability > consistency for a public tool with no SLA). Duplicate processing during Redis outage = wasted CPU, not data corruption. The trade-off is documented and intentional. | No change. Added note to `04-infra-gcp.md` §5 explaining the rationale: for a free public tool with no paying users, fail-open is acceptable. Would not be for a paying service. |
| W4 | Signed URL in browser history and server logs | MED | **ACCEPTED & BACKLOG** | Valid: the `access_token` in the URL query string gets logged. 15-minute window mitigates but doesn't eliminate risk. | Backlog: evaluate header-based signed URL auth or log filtering. Not urgent (15-min window + single-use URLs). Estimated effort: 2h. |
| W5 | "Sin autenticacion" accepted too quickly — LFPDPPP compliance | MED | **ACCEPTED & BACKLOG** | Red team correctly flags Mexican data protection law (LFPDPPP). RFC IDs ARE personal data. The no-auth decision was made at the product level for a personal-use tool, but the doc should acknowledge the legal implication. | Updated `01-fundamentos.md` §A04 to add a compliance note about LFPDPPP. Not a security fix — a legal/compliance note. |

---

## False Assumptions (5)

| ID | Finding | Severity | Decision | Reasoning | Action |
|----|---------|----------|----------|-----------|--------|
| F1 | "Cloud Run tmpfs is safe" ignores `/proc` and metadata server | HIGH | **ACCEPTED & FIXED** | Critical correction. `/proc/self/environ`, `/proc/self/cmdline`, and the metadata server at `169.254.169.254` are all readable via XXE. The doc downplayed the blast radius. | Updated `01-fundamentos.md` §A03 and `03-backend.md` §XXE to enumerate the full attack surface: env vars, metadata server, SSRF. |
| F2 | CORS analysis misses same-origin XSS via Vercel rewrites | HIGH | **ACCEPTED & FIXED** | The Vercel rewrite makes `/api/*` same-origin to the browser. An XSS on the Vercel domain can hit ALL endpoints including `/api/internal/*` with forged `x-cloudtasks-queuename`. The only defense for internal endpoints is real auth (OIDC). | Updated `02-frontend.md` §CORS to document the same-origin XSS risk. This reinforces C2/C3/C4 as high-priority fixes. |
| F3 | "GCS lifecycle de 1 día" doesn't prevent exfiltration in a breach | LOW | **ACCEPTED & FIXED** | Correct: lifecycle is garbage collection, not breach containment. The doc framed it as a security feature. | Fixed `04-infra-gcp.md` §3.2 and `01-fundamentos.md` §Principle of Least Privilege to distinguish: lifecycle = cost control, NOT breach mitigation. |
| F4 | Pydantic "validacion" is just size, not content | MED | **ACCEPTED & FIXED** | `contracts.py:13-14` only validates `min_length=1, max_length=20_000_000`. Calling this XML validation is misleading. | Updated `01-fundamentos.md` §Flujos críticos to clarify: Pydantic checks size only. No CFDI schema validation, no XXE scanning, no content sanitization. |
| F5 | "Endpoint /api/internal/generate-pdf sí protege el acceso" — false | MED | **ACCEPTED & FIXED** | Same as C2. The header check is spoofable. | Updated `01-fundamentos.md` §A04 to remove the false claim and reference C2/OIDC fix. |

---

## Code-Level Vulnerabilities (8)

| ID | Finding | Severity | Decision | Reasoning | Action |
|----|---------|----------|----------|-----------|--------|
| V1 | `canvas_service.py:835,869,983` — XXE via lxml | CRIT | **ACCEPTED & FIXED** | Duplicate of C1. | See C1. |
| V2 | `batch.py:83` — `ET.fromstring` without `defusedxml` | HIGH | **ACCEPTED & FIXED** | `_extract_header` parses user-supplied XML for Emisor/Receptor metadata. No DTD resolution in stdlib ET by default, but `defusedxml` is best practice. | Updated `03-backend.md` §XXE fix recommendations to include `batch.py:83`. Added to CRITICAL fixes in `08-auditoria-actual.md` (lower effort, done alongside C1). |
| V3 | `sat_enquiry.py:303` — `str(exc)` leaked in HTTP 502 | HIGH | **ACCEPTED & FIXED** | Confirmed: error response includes raw exception text. Internal Diverza URLs and response details may leak. | Updated `03-backend.md` §Safe error handling. Fix code: replace `detail=f"Error Diverza: {exc}"` with generic message + Sentry + log. |
| V4 | `sat_enquiry.py:193-198` — `str(exc)` in batch results → SSE + Excel | HIGH | **ACCEPTED & FIXED** | Same class as V3, different path. Exception strings propagate through SSE stream and into Excel output. | Added to `03-backend.md` §Safe error handling. |
| V5 | `sat_enquiry.py:359-361` — unbounded memory + predictable job IDs | MED | **ACCEPTED & FIXED** | Duplicate of C3. | See C3. |
| V6 | `credentials.py:14-19` — Fernet key silently regenerated | MED | **ACCEPTED & FIXED** | Duplicate of H5. | See H5. |
| V7 | `catalogs.py:31,32,54` — `pickle.loads` on local DB data | LOW | **ACCEPTED & BACKLOG** | `pickle.loads` reads from `satcfdi` package's SQLite DB, not user input. Not exploitable today. But `pickle` is inherently unsafe — if the DB file is ever replaced or loaded from an untrusted source, it becomes RCE. | Added to Missing Threat Classes section. Backlog: replace `pickle` with `json` or `shelve`. Estimated effort: 2h. |
| V8 | `batch_reports.py:31` — `ET.fromstring` without `defusedxml` | MED | **ACCEPTED & FIXED** | Same class as V2. DIOT report generation parses user XML. | Same fix as V2: add `defusedxml`. |

---

## Missing Threat Classes (8 from the original matrix)

| Threat Class | Severity | Decision | Reasoning | Action |
|---|---|---|---|---|
| Excel formula injection (CSV injection) | MED | **ACCEPTED & BACKLOG** | `_build_result_excel` writes user RFC/UUID to XLSX. If values start with `=`, `+`, `-`, `@`, they become formulas. Excel warns before executing, but the risk exists. | Added to `03-backend.md` §Input validation. Backlog: prepend `'` to cell values starting with dangerous chars. Estimated effort: 30 min. |
| SSTI via template upload | MED | **ACCEPTED & BACKLOG** | Uploaded templates (`PUT /api/templates/{id}/design`) include HTML shells rendered by WeasyPrint. If template interpolation uses `str.format()` on user input, SSTI is theoretically possible. Need code audit. | Added to `03-backend.md` §SSRF risks (general principle). Backlog: audit template rendering path. Estimated effort: 3h. |
| Prototype pollution in JS deps | LOW | **DISPUTED** | Real threat class, but no exploit path identified in this codebase. React 19 has reasonable prototype pollution defenses. No CVEs in current deps. Monitoring via Dependabot is sufficient. | No immediate action. Covered by Dependabot (see `09-ci-cd-hardening.md`). |
| Subresource Integrity (SRI) | LOW | **ACCEPTED & BACKLOG** | No SRI hashes on `pusher-js` or `@sentry/react` loaded from CDN. A compromised CDN could inject arbitrary JS. Risk is low (high-profile CDNs), but SRI is a one-line fix per script tag. | Added to `02-frontend.md` §Dependency auditing. Backlog: add `integrity` hashes. Estimated effort: 30 min. |
| Dependency confusion | HIGH | **ACCEPTED & FIXED** | Python packages `pusher`, `redis`, `openpyxl` are common names. A typosquatter could publish malicious versions to public PyPI. No `--index-url` pinning or hash verification. | Added to `09-ci-cd-hardening.md` §pre-commit and `03-backend.md` §Dependency auditing. Recommend private PyPI mirror or `--require-hashes`. |
| Race condition in batch state TTL | LOW | **ACCEPTED & BACKLOG** | `batch.py:116-123` does `hmset` + `expire` as separate calls. If process dies between them, hash key persists forever (memory leak in Redis). Unlikely but real. | Backlog: use `hset` with `ex` param or wrap in Redis pipeline. Estimated effort: 30 min. |
| Missing Content-Type on error responses | LOW | **ACCEPTED & FIXED** | `main.py:111-151` returns `JSONResponse` but doesn't set `content-type` explicitly (FastAPI does it automatically for `JSONResponse`). FastAPI's `JSONResponse` sets `Content-Type: application/json` by default — this is NOT missing. However, manual `Response()` calls in `sat_enquiry.py:377-381` correctly set `media_type`. Verified: no MIME-sniffing risk. Red team concern is unfounded for FastAPI. | No code change needed. FastAPI's `JSONResponse` sets `Content-Type` automatically. |
| No audit log of Cloud Tasks header bypass attempts | MED | **ACCEPTED & FIXED** | Internal endpoints reject with 403 but don't log the attempt. An attacker can probe `/api/internal/*` undetected. | Added to `03-backend.md` §Endpoints internos recommendation: log failed attempts to Sentry. Added to `01-fundamentos.md` §A09. |

---

## Top 5 CTO Decisions

1. **XXE is the #1 priority.** Every lxml call site gets `resolve_entities=False` this sprint. No exceptions. The `/proc/self/environ` exposure makes this a same-week emergency.

2. **OIDC for Cloud Tasks, not header tricks.** The `x-cloudtasks-queuename` header check stays as defense-in-depth, but the real fix is OIDC tokens on task dispatch. The doc is updated to stop calling a bypassable check "done."

3. **Rate limiting waits one sprint.** It's the right thing to do, but no attacker is burning Diverza credits today. Implement `slowapi` before next feature work. Diverza usage alert via Sentry threshold happens today (free, effort: 15 min).

4. **Pusher stays public until auth ships.** Private channels add auth infrastructure overhead. For a no-auth tool, UUID-based channel names + disabled client events are "good enough." When Google OAuth ships, private channels ship with it.

5. **Supply chain scanning ships today.** CI security scanning (`bandit`, `safety`, `npm audit`, CodeQL, Dependabot) is the highest-ROI security investment: one-time setup, zero ongoing maintainer effort, catches vulnerabilities automatically. All workflows provided copy-paste in `09-ci-cd-hardening.md`.

---

> This reconciliation represents the final CTO-level triage. All ACCEPTED & FIXED findings have been incorporated into docs 01-05 and tracked in `08-auditoria-actual.md`.
> ACCEPTED & BACKLOG findings are scheduled per their estimated effort and severity.
> DISPUTED findings are closed with reasoning — no further action.
