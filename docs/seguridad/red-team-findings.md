# Red Team Findings — cfdi_suite Security Review

> **Adversarial review of docs/seguridad/01-05.** This is NOT a "nice feedback"
> document. Every finding is backed by actual source code evidence or verifiable
> missing coverage.

---

## Critical Gaps (must fix before production hardening)

### C1 — XXE via lxml in production code, zero mitigation
All 3 call sites of `lxml.etree.iterparse` in `canvas_service.py:835,869,983` use
the default parser with `resolve_entities=True` and no `no_network` restriction.
An attacker can:

1. Upload an XML CFDI containing `<!ENTITY xxe SYSTEM "file:///proc/self/environ">`
2. Extract all Cloud Run env vars (`REDIS_PASSWORD`, `PUSHER_SECRET`,
   `SENTRY_DSN`) via the `Rfc` or `Nombre` field of the parsed `Emisor` node
3. Those values end up in canvas output, logs, PDFs, or API responses

The docs acknowledge this (01:§A03, 03:§XXE) but mark the fix as "Quick win"
with no committed implementation. Meanwhile, the attack works **today** against
production.

### C2 — Cloud Tasks header check is trivially bypassable
`pdf.py:107` verifies `x-cloudtasks-queuename` in request headers. The queue name
is hardcoded and predictable: `pdf-generator-queue` (`task_dispatcher.py:9`).
Doc 03:§Endpoints internos admits this weakness ("poco robusto") and doc
04:§1.1 documents the attack explicitly.

Yet **neither doc identifies the real solution**: the Cloud Tasks SDK's
`oidc_token` field authenticates the caller cryptographically
(`task_dispatcher.py:30-36` sends NO oidc_token). The recommendation to "check
the header" is a placebo for a service deployed with `--allow-unauthenticated`.

**Exploit**: `curl -H "x-cloudtasks-queuename: pdf-generator-queue"
-X POST https://CFDI_API/api/internal/generate-pdf -d '{"job_id":"attacker",
"xml_b64":"...", ...}'`

### C3 — `_job_results` in-memory store: no auth, no eviction, cross-tenant leak
`sand_enquiry.py:24` — `_job_results: dict[str, bytes] = {}`. This module-level
dict stores batch SAT enquiry Excel results. Any request to
`GET /api/sat/enquiry/batch/{job_id}/result` (`line 372`) pops and returns the
result — **one-time download, no ownership check**. An attacker can:

1. Brute-force UUIDs (semi-predictable given `uuid4()` is not cryptographically
   weak but the namespace is tiny with the SSE response leaking IDs)
2. Or replay the SSE stream to extract `job_id` from the `done` event
   (`line 363: yield f"data: ...'job_id': job_id...\n\n"`)
3. Download another user's SAT enquiry results with Excel full of RFCs and UUIDs

This is the only endpoint in the app with actual data-leak potential because it
creates a *temporary session* concept (the job ID) without any binding to the
initial requestor.

### C4 — No rate limiting anywhere, Diverza credits unprotected
Zero rate limiting confirmed across all endpoints. `POST /api/sat/enquiry` at
`sand_enquiry.py:286` calls Diverza API with credentials from the server. A
single attacker can:

- Burn through Diverza API credits (financial cost)
- Get the Diverza account rate-limited or banned
- Exhaust Cloud Tasks capacity (the queue has no `max-dispatches-per-second`
  documented in code; doc 04:§4.2 only *recommends* settings)

Doc 03:§Rate limiting proposes slowapi but nothing is implemented.

---

## High-Risk Omissions

### H1 — Zip path traversal / symlink attacks not addressed
`py.py:260-266` uses `zipfile.ZipFile` to iterate entries. Python's `zipfile`
does NOT prevent path traversal by default — an entry named
`../../../etc/cron.d/evil` would be extracted outside the target directory
*if extracted to disk*. The code currently reads to memory (`z.read()` at line
264) and never extracts to disk — **safe for now**. But `is_valid_xml_entry`
(`zip_manifest.py:21-24`) only checks `filename.endswith(".xml")` — a zip entry
named `../../../tmp/evil.xml` passes this check. If any future code extracts to
disk, this becomes exploitable.

The docs claim "Path traversal implícito: `zipfile.ZipFile` no permite escritura
fuera del directorio destino" (03:§File upload security) — this is **false** for
manual extraction; `zipfile`'s `extract()`/`extractall()` are vulnerable without
`members` filtering. The `.read()` in current code is safe, but the claim is
misleading.

### H2 — Openpyxl XXE / Billion Laughs for Excel uploads never discussed
`sand_enquiry.py:211` calls `openpyxl.load_workbook(io.BytesIO(content),
data_only=True)`. The docs mention openpyxl in the dependency table
(03:§Dependency auditing: "XXE vía Excel es teóricamente posible") but **never
analyze** whether `data_only=True` mitigates it or whether openpyxl has known
vulnerabilities in the version used. The batch SAT enquiry endpoint
(`/api/sat/enquiry/batch` at line 312) uploads up to 10 MB of Excel — an
attacker can craft a malicious XLSX with entity expansion.

### H3 — Regex DoS (ReDoS) via template ID validation
`templates.py:21` — `_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)`.
While this regex is safe, `_HEX_RE` (line 25: `r"^#[0-9A-Fa-f]{6}$"`) and the
`_validate_columns` function (line 51) perform extensive string validation on
user-supplied template configs. A template with thousands of columns or deeply
nested config could cause exponential backtracking if any future regex is added
without testing. The current code is safe but the **attack surface is
unacknowledged** — the template upload/validation endpoint is
`PUT /api/templates/{id}/design` (uncharted in any security doc).

### H4 — Pusher channel authorization bypass via public channels
`realtime.py:80` triggers events on `pdf-batch-{batch_id}` — a public channel.
**Anyone** who knows the batch ID can subscribe and receive progress events.
While the signal is minimal (`{"kind": "job_done"}`), an attacker can:

1. Subscribe to ALL public channels (Pusher allows wildcard subscriptions on the
   client using their debug console)
2. Monitor batch creation events to extract batch IDs
3. In a future with authenticated users, know exactly when competing batches
   finish

Doc 02:§Pusher key exposure correctly recommends disabling "Enable client
events" but misses the channel authorization gap. Doc 04:§6.2 dismisses this
as "aceptable" (security by obscurity).

### H5 — In-memory Fernet key on ephemeral filesystem — silent data loss
`credentials.py:14-19` — `_ensure_key()` generates a new Fernet key on every
Cloud Run cold start. Doc 05:§2.4 correctly documents this. Doc 01:§A02
mentions it. **But no doc connects this to the operational risk**: if emisor
credentials are configured during a session, they're lost on the next
scale-to-zero. The user sees a successful `POST /api/emisores` (HTTP 201), then
later `GET /api/sat/enquiry` returns "RFC emisor no configurado: XXXX" (HTTP 404
from `sand_enquiry.py:290-293`). The failure is **silent** — no error, no
warning, just missing credentials.

### H6 — Supply chain: npm caret ranges, no hash pinning, no CI audit
`frontend/package.json` uses `^` (caret) ranges. `backend/requirements.txt` uses
`>=`/`<` ranges. Neither has `--hash` pinning. No `npm audit` or `safety` in CI
(confirmed: `.github/workflows/` has zero security scanning jobs). Doc
02:§Dependency auditing *recommends* adding these, but the gap is already
exploitable.

---

## Inconsistencies Between Docs

### I1 — Timeout: 600s recommendation vs. 1800s reality
Doc 03:§Redis connection states Cloud Run timeout is 1800s. Doc 04:§1.3
*recommends* reducing to 600s, but `deploy-backend.yml:66` confirms it's still
**1800s**. All docs agree the recommendation, but 04 concedes the current value
while 01 and 03 don't mention the discrepancy.

### I2 — `python-satcfdi-wrapper.py` path is wrong in 01, 03
Docs 01:§A03 and 03:§XXE reference
`backend/app/services/python-satcfdi-wrapper.py:406`. The actual file is at
`backend/wrappers/python-satcfdi-wrapper.py:406`. The import of
`xml.etree.ElementTree` is at line 6, not detected by the path in the docs.
This invalidates the claim that all three stdlib ET files are accounted for.

### I3 — Doc 02 claims no `innerHTML` usage, but test files have it
Doc 02:§XSS vectors says "No se usa `eval` en el código actual" and "En este
codebase no se usa `dangerouslySetInnerHTML`". True for production code, but
three test files use `document.body.innerHTML = ''` (`FindingsSidebar.test.tsx:50`,
`ExtractWorkspacePagination.test.tsx:44`, `ExtractWorkspaceToolbar.test.tsx:44`).
Minor, but the doc's absolute claim is technically incorrect.

### I4 — Pusher key classification conflict
Doc 05:§1.2 classifies `PUSHER_KEY` as "mal clasificado" (should be GitHub
Variable, not GitHub Secret). But doc 05:§1.1 lists `PUSHER_APP_ID` as SECRET
and 05:§2.1 shows it in GitHub Secrets. These three items (KEY, SECRET, APP_ID)
have different confidentiality levels but all sit in GitHub Secrets. Doc 05
correctly identifies the misclassification but doesn't reconcile with
`deploy-backend.yml:51-53` which uses `${{ secrets.PUSHER_KEY }}` — if KEY is
reclassified to Variable, the deployment workflow must be updated.

---

## Weak Recommendations

### W1 — CSP with `'unsafe-inline'` defeats XSS protection
Both doc 02:§CSP and doc 03:§Security headers propose CSP policies with
`script-src 'self' 'unsafe-inline'`. This **negates the primary benefit of CSP**
— an attacker who finds any XSS injection point can execute arbitrary inline
scripts. The docs acknowledge this is "for Vite HMR" but recommend it for
production. A CSP without nonces/hashes and with `'unsafe-inline'` provides
**almost zero XSS protection**.

### W2 — "Quick win: Cloud Tasks header check" is insufficient
Both doc 03 and doc 04 mark the header check as a "Quick win". As documented in
Finding C2, this header is spoofable. Calling it a "win" gives false confidence.
The docs *know* it's weak (03:§Endpoints internos, 04:§1.1) but still
categorize it as "Nivel 1: Ya" in the maturity table. "Ya" means "already done"
— it is NOT done correctly.

### W3 — "Best-effort in favour of continuing" is anti-pattern for security
`py.py:887-888` — when Redis is down, the extraction lock is SKIPPED and
processing continues. The comment says "Decisión explícita del usuario:
best-effort en vez de fail-closed." This means a duplicate Cloud Tasks retry
during a Redis outage will process the same ZIP twice — resource waste but
also potential data corruption (duplicate job IDs, race on GCS writes).
Doc 04:§5 never addresses what happens when Redis is fully down.

### W4 — GCS Signed URL expiration: 15 minutes is good, but the URL is in
browser history and server logs
The signed URLs (doc 04:§3.3, `py.py:662-669`) have 15-minute expiration. While
this limits long-term exposure, the URL includes the `access_token` in the query
string. If Vercel or Cloud Run logs capture full URLs (they do by default), the
signed URL — valid for 15 minutes — is logged in plaintext.

### W5 — "Sin autenticación es una decisión consciente" — accepted as OK too quickly
Doc 01:§A01 and §A04:2021 frame the lack of authentication as an accepted design
decision. This ignores the **data privacy implications** of CFDI data:
- RFC IDs are personal identifiers under Mexican data protection law (LFPDPPP)
- Anyone can upload a CFDI with a third party's RFC and view their fiscal data
- The `/api/emisores` endpoint (`emisores.py:49`) exposes `credential_id` values
  (even without the token, the credential_id is sensitive metadata)
- No doc mentions LFPDPPP, ARCO rights, or data subject access requests

---

## False Assumptions

### F1 — "Cloud Run tmpfs is safe because the filesystem is limited"
Doc 03:§XXE and 01:§A03 note that Cloud Run's filesystem is limited, implying
XXE impact is reduced. This is **dangerously wrong**. An XXE payload can read:
- `/proc/self/environ` — ALL environment variables, including `REDIS_PASSWORD`,
  `PUSHER_SECRET`, `SENTRY_DSN`
- `/proc/self/cmdline` — full startup command
- Metadata server at `http://169.254.169.254` — GCP service account tokens
- Plus SSRF to internal services via `<!ENTITY xxe SYSTEM "http://...">`

The "limited filesystem" comment only applies to `/etc/passwd` and static files;
it **completely misses** `/proc` and the metadata server as exfiltration
targets.

### F2 — "CORS is not a server security mechanism" — correct but incomplete analysis
Doc 02:§CORS correctly states CORS is browser-enforced. But it misses that
`vercel.json:5` (rewrites) makes ALL `/api/*` requests **same-origin** to the
browser. This means any XSS on the Vercel domain can hit ALL endpoints with the
user's browser — including `/api/internal/*` if the attacker crafts a request
with the right header. Since the browser can set arbitrary headers, and the
rewrite removes the CORS barrier, the Cloud Tasks header check is the **only**
defense for internal endpoints from a browser-based attack.

### F3 — "GCS con lifecycle de 1 día evita acumulación perpetua"
Doc 04:§3.2 and 01:§Principle of Least Privilege cite the 1-day lifecycle as a
security benefit. This is true for storage cost, but **does not prevent data
exfiltration** — an attacker who gains access to the bucket has 24 hours to
download everything. The lifecycle rule helps with garbage collection, not
with breach containment.

### F4 — "El XML viaja en el body. Validado por Pydantic"
Doc 01:§Flujos críticos says the XML is "validado por Pydantic
(`contracts.py:13-14`)". The "validation" is **only** `min_length=1,
max_length=20_000_000`. This is size validation, NOT content or structure
validation. The XML is NOT validated against the CFDI schema, NOT checked for
XXE payloads, NOT sanitized. Calling this "validado" is misleading.

### F5 — "El endpoint /api/internal/generate-pdf sí protege el acceso"
Doc 01:§A04 states this endpoint "protege el acceso verificando
`x-cloudtasks-queuename`". As proven in C2, this is NOT real protection. The
doc presents a secure design claim that doesn't match reality.

---

## Code-Level Vulnerabilities Missed by Docs

### V1 — `canvas_service.py:835,869,983` — Unmitigated XXE via lxml
```python
for _, el in etree.iterparse(io.BytesIO(xml_bytes), events=("start",),
                              recover=True):
```
**Attack**: Upload XML with `<!ENTITY xxe SYSTEM "file:///proc/self/environ">`
→ env vars read and embedded in parsed data → appears in PDF/response.
**Docs mention**: Yes (03:§XXE). **Docs miss**: That it's still unfixed in
production, and the `/proc` attack surface.

### V2 — `batch.py:83` — stdlib `ET.fromstring` without defusedxml
```python
root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))
```
**Attack**: Billion laughs / XML bomb via the batch analysis endpoint. The
`MAX_FILES = 500` limit at line 78 doesn't prevent a single malicious XML
from exhausting memory.
**Docs mention**: Yes, recommends `defusedxml`. **Docs miss**: That
`_extract_header` runs on USER-SUPPLIED XML in the batch analysis hot path
and is equally vulnerable to XML bombs as the canvas parse paths.

### V3 — `sand_enquiry.py:303` — Error details leaked in HTTP response
```python
except httpx.HTTPError as exc:
    raise HTTPException(status_code=502, detail=f"Error Diverza: {exc}")
```
**Attack**: Trigger Diverza API errors with crafted UUIDs → the response
includes `str(exc)` which can contain internal URLs, Diverza API response
details, and network topology information.
**Docs mention**: Yes (03:§Safe error handling). **Docs miss**: That
`_enquiry_indexed` at line 198 also leaks `str(exc)` in the in-memory
results dict, which then appears in the SSE stream and Excel output.

### V4 — `sand_enquiry.py:193-198` — Unfiltered exception strings in batch results
```python
except Exception as exc:
    return idx, {"uuid": uuid, ..., "error": str(exc)}
```
**Attack**: Same as V3 but via batch SSE stream — the error message propagates
through `event_stream()` line 352 and into the Excel result at line 270.
**Docs mention**: No — the docs only flag line 303.

### V5 — `sand_enquiry.py:359-361` — Unbounded memory growth + predictable job IDs
```python
if len(_job_results) >= 5:
    oldest = next(iter(_job_results))
    del _job_results[oldest]
_job_results[job_id] = excel_bytes
```
**Attack**: Submit 5 quick batch enquiries → fill the store → SSRF the SSE
streams to extract job IDs → download Excel results containing others' UUIDs
and RFCs.
**Docs mention**: No — this module-level mutable state is never discussed in
any security doc.

### V6 — `credentials.py:14-19` — FERNET_KEY silently regenerated on cold start
```python
if not _KEY_FILE.exists():
    _KEY_FILE.write_bytes(Fernet.generate_key())
```
**Attack**: Not directly exploitable, but the silent credential loss (H5) means
previous `emisores.enc` is unreadable → credentials silently vanish → `get_cred`
at `sat_enquiry.py:178` returns `None` → 404 to user. An attacker who learns of
this pattern could time attacks against cold starts.
**Docs mention**: Yes (05:§2.4). **Docs miss**: The user-visible failure mode
and operational risk.

### V7 — `catalogs.py:31,32,54` — `pickle.loads` on local DB data
```python
val = pickle.loads(v)
result[str(pickle.loads(k))] = str(val[0] if isinstance(val, list) else val)
```
**Risk**: Low (reads from `satcfdi` package's SQLite DB, not user input).
**Docs mention**: No — no doc mentions pickle usage in the codebase.

### V8 — `batch_reports.py:31` — `ET.fromstring` without defusedxml
Same as V2. This file is the DIOT report generator, triggered from
`POST /api/cfdi/batch/diot` (`batch.py:313`). The docs list it as a parse point
at 03:§XXE but don't highlight it as a distinct endpoint with its own risk.

---

## Missing Threat Classes (Not Addressed by Any Doc)

| Threat Class | Why It Matters | Relevant Endpoint/File |
|---|---|---|
| **Excel formula injection (CSV injection)** | `_build_result_excel` at `sand_enquiry.py:241` writes user-supplied RFC/UUID values to XLSX; if opened in Excel and values start with `=`, `+`, `-`, `@`, they execute as formulas | `sand_enquiry.py:259-273` |
| **Server-Side Template Injection (SSTI)** | Templates uploaded via `PUT /api/templates/{id}/design` (`templates.py`) include HTML shells that get rendered by WeasyPrint — if template fields are `str.format()`-based or use Jinja2, user input could escape the template | `canvas_service.py`, `templates.py` |
| **Prototype pollution in JS dependencies** | `pusher-js`, `@sentry/react`, React 19 — if any dependency allows `__proto__` manipulation, DOM clobbering or property injection is possible | All frontend dependencies |
| **Subresource Integrity (SRI)** | The frontend has NO SRI hashes on any third-party script — a compromised CDN for pusher-js or sentry would execute arbitrary code | `index.html` |
| **Dependency confusion / namespace confusion** | The package names `pusher` (PyPI), `redis` (PyPI), `openpyxl` could be typosquatted; no `--index-url` pinning in `requirements.txt` | `requirements.txt` |
| **Race condition in batch state transitions** | `batch.py:116-120` does `hmset` then separate `expire` calls — if the process dies between them, the hash key lives forever without TTL (memory leak in Redis) | `batch.py:116-123` |
| **Missing Content-Type on error responses** | Some error handlers return `JSONResponse` without explicit `content-type`; browser MIME sniffing could interpret error JSON as HTML | `main.py:111-151` |
| **No audit log of Cloud Tasks header bypass attempts** | Internal endpoints reject with 403 but don't log the attempt. An attacker can probe undetected. | `py.py:107-108` |

---

## Scorecard

| Doc | File | Realism | Completeness | Actionability | Overall |
|------|------|---------|-------------|---------------|---------|
| 01 | 01-fundamentos.md | 7/10 | 6/10 | 7/10 | 7/10 |
| 02 | 02-frontend.md | 6/10 | 5/10 | 6/10 | 6/10 |
| 03 | 03-backend.md | 7/10 | 5/10 | 8/10 | 7/10 |
| 04 | 04-infra-gcp.md | 8/10 | 6/10 | 7/10 | 7/10 |
| 05 | 05-secretos.md | 8/10 | 7/10 | 8/10 | 8/10 |

**Best doc**: `05-secretos.md` — honest about classification, realistic about
the Fernet key problem, provides concrete migration paths with code, and
acknowledges the historical Redis password exposure incident transparently.

**Weakest doc**: `02-frontend.md` — spends significant space on hypothetical
future CSRF and CSP configs while missing Pusher channel auth bypass, ReDoS
surface in template validation, and the actual 3 `innerHTML` usages in test
files. The CSP recommendation with `'unsafe-inline'` is counterproductive.

**Overall**: The docs are a solid foundation but share a common weakness:
recommendations not yet implemented are marked as "covered" in threat
assessments. The gap between "we know this is a problem" and "we fixed it" is
where the actual risk lives.

---

## Summary Counts

- **#critical**: 4
- **#high**: 6
- **#inconsistencies**: 4
- **#weak-recs**: 5
- **#false-assumptions**: 5
- **#code-vulns**: 8
