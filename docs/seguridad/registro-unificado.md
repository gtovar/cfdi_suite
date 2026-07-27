# Registro Unificado de Hallazgos — cfdi_suite

> Generado por `scripts/reconcile_registry.py` — código determinista, sin LLM, re-ejecutable.
> **Batches procesados:** 5
> **Candidates de batches:** 98
> **Filas de auditoría:** 62
> **Total en registro:** 160
> **Rechazados por panel:** 7

## Registro Unificado de Hallazgos de Seguridad

| id | título | severidad | verificación | fuentes | archivo:línea | spec |
|---|---|---|---|---|---|---|
| B7-BE-AUTH-01 | Missing authentication on /api/cfdi/batch/status/{batch_id} exposes full… | HIGH | panel unánime | batch-7 | backend/app/routers/batch.py:183 | — |
| B7-BE-AUTH-02 | Raw Python exception string leaked in DIOT generation HTTP 500 response | MEDIUM | sin panelear | batch-7 | backend/app/routers/batch.py:336 | — |
| B7-BE-AUTH-03 | Raw exception strings exposed to clients in batch worker analysis result… | MEDIUM | sin panelear | batch-7 | backend/app/routers/batch.py:272 | — |
| B7-BE-AUTH-04 | Subprocess error messages passed through as client-facing public_message… | MEDIUM | sin panelear | batch-7 | backend/app/providers/current_ts.py:114 | — |
| B7-BE-AUTH-05 | CFDI digital signature verification error exposed in analysis findings w… | LOW | sin panelear | batch-7 | backend/app/services/analyze_cfdi.py:646 | — |
| B7-BE-INJ-01 | Billion Laughs / Entity Expansion DoS via stdlib ET.fromstring in batch_… | MEDIUM | panel unánime | batch-7 | backend/app/services/batch_reports.py:31 | — |
| B7-CFDI-AUTH-01 | Subprocess binary path injection via unvalidated pythonBinary engine opt… | MEDIUM | sin panelear | batch-7 | frontend/src/cfdi/engine/pythonSatcfdiEngine.ts:68 | — |
| B7-CFDI-AUTH-02 | Arbitrary file execution via unvalidated wrapperPath engine option | MEDIUM | sin panelear | batch-7 | frontend/src/cfdi/engine/pythonSatcfdiEngine.ts:69 | — |
| B7-CFDI-AUTH-03 | Full stderr/stdout from Python subprocess leaked in error messages | MEDIUM | sin panelear | batch-7 | frontend/src/cfdi/engine/pythonSatcfdiEngine.ts:249 | — |
| B7-CFDI-AUTH-06 | Raw error messages propagated from TypeScript engines without sanitizati… | LOW | sin panelear | batch-7 | frontend/src/cfdi/engine/currentTsEngine.ts:27 | — |
| B7-CFDI-INJ-01 | XXE / Billion Laughs entity expansion via ET.fromstring in Python subpro… | MEDIUM | rechazado por panel | batch-7 | frontend/src/cfdi/engine/python-satcfdi-wrapper.py:406 | — |
| B7-CFDI-INJ-02 | NaN/Infinity propagation from attacker-crafted numeric XML attributes in… | LOW | sin panelear | batch-7 | frontend/src/cfdi/application/cfdiAnalysisService.ts:33 | — |
| B7-CFDI-INJ-03 | Untrusted XML attribute values interpolated into diagnostic display stri… | LOW | sin panelear | batch-7 | frontend/src/cfdi/application/cfdiAnalysisService.ts:127 | — |
| B7-CI-AUTH-01 | Third-party action millionco/react-doctor@v2 granted excessive permissio… | MEDIUM | sin panelear | batch-7 | .github/workflows/react-doctor.yml:17 | — |
| B7-CI-AUTH-02 | Production deploy workflows lack explicit permissions declaration — inhe… | LOW | sin panelear | batch-7 | .github/workflows/deploy-backend.yml:11 | — |
| B7-CI-AUTH-03 | No deployment approval gate — push to main immediately deploys to produc… | MEDIUM | sin panelear | batch-7 | .github/workflows/deploy-backend.yml:3 | — |
| B7-CI-AUTH-04 | Stale detect-secrets baseline with orphaned entries for deleted files | LOW | sin panelear | batch-7 | .secrets.baseline:140 | — |
| B7-CI-AUTH-05 | Two divergent deploy paths for same Cloud Run service — doubled attack s… | MEDIUM | sin panelear | batch-7 | .github/workflows/deploy-backend.yml:23 | — |
| B7-CI-AUTH-06 | Cloud Run service deployed with --allow-unauthenticated on default compu… | MEDIUM | sin panelear | batch-7 | .github/workflows/deploy-backend.yml:62 | — |
| B7-CI-CRYPTO-01 | Production secrets on disk in backend/.env — PUSHER_SECRET, REDIS_PASSWO… | HIGH | rechazado por panel | batch-7 | backend/.env:7 | — |
| B7-CI-CRYPTO-02 | No cryptographic hash pinning for pip dependencies — supply chain attack… | MEDIUM | panel mayoría | batch-7 | backend/requirements.txt:1 | — |
| B7-CI-CRYPTO-03 | Long-lived GCP Service Account Key used instead of Workload Identity Fed… | MEDIUM | rechazado por panel | batch-7 | .github/workflows/deploy-backend.yml:20 | — |
| B7-CI-CRYPTO-04 | detect-secrets 'pragma: allowlist secret' suppresses real hardcoded Push… | MEDIUM | sin panelear | batch-7 | frontend/src/lib/pdf-download.ts:308 | — |
| B7-CI-CRYPTO-05 | Container image deployed with :latest tag — no digest pinning or signatu… | MEDIUM | sin panelear | batch-7 | infra/deploy-batch-shard-job.sh:34 | — |
| B7-CI-CRYPTO-06 | VERCEL_TOKEN passed as CLI argument — visible in process listing and she… | LOW | sin panelear | batch-7 | .github/workflows/deploy-frontend.yml:22 | — |
| B7-CI-CRYPTO-07 | Infrastructure reconnaissance data exposed in version-controlled deploym… | LOW | sin panelear | batch-7 | infra/deploy-batch-shard-job.sh:66 | — |
| B7-CI-CRYPTO-08 | GitHub Actions use floating major-version tags without commit SHA pinnin… | LOW | sin panelear | batch-7 | .github/workflows/deploy-backend.yml:15 | — |
| B7-CI-CRYPTO-09 | Four opentelemetry dependencies completely unpinned — no version constra… | MEDIUM | sin panelear | batch-7 | backend/requirements.txt:16 | — |
| B7-CI-CRYPTO-10 | detect-secrets baseline references deleted files — stale exclusions coul… | LOW | sin panelear | batch-7 | .secrets.baseline:141 | — |
| B7-CI-INJ-01 | Four opentelemetry packages completely unpinned — dependency confusion a… | MEDIUM | rechazado por panel | batch-7 | backend/requirements.txt:16 | — |
| B7-CI-INJ-02 | Unbounded upper version on google-cloud-storage allows automatic major-v… | LOW | sin panelear | batch-7 | backend/requirements.txt:31 | — |
| B7-CI-INJ-03 | Environment variable injection via newline in GitHub secret interpolated… | LOW | sin panelear | batch-7 | .github/workflows/deploy-backend.yml:44 | — |
| B7-HOOKS-AUTH-01 | Raw FastAPI error detail exposed to end-user via useCfdiAnalysis error h… | MEDIUM | sin panelear | batch-7 | frontend/src/app/hooks/useCfdiAnalysis.ts:78 | — |
| B7-HOOKS-AUTH-02 | Raw backend error detail exposed to end-user via useRfcValidation error … | MEDIUM | sin panelear | batch-7 | frontend/src/app/hooks/useRfcValidation.ts:53 | — |
| B7-HOOKS-AUTH-03 | Raw backend error detail exposed to end-user via useSatEnquiry error han… | MEDIUM | sin panelear | batch-7 | frontend/src/app/hooks/useSatEnquiry.ts:30 | — |
| B7-HOOKS-AUTH-04 | Sensitive CFDI financial data fully exposed in React DevTools via useSta… | LOW | sin panelear | batch-7 | frontend/src/app/hooks/useCfdiAnalysis.ts:62 | — |
| B7-HOOKS-AUTH-05 | Full error object with stack trace logged to console in useCfdiExports | LOW | sin panelear | batch-7 | frontend/src/app/hooks/useCfdiExports.ts:174 | — |
| B7-HOOKS-INJ-01 | CSV formula injection via escapeCsv without formula character guard — fo… | MEDIUM | panel unánime | batch-7 | frontend/src/app/hooks/useCfdiExports.ts:15 | — |
| B7-UI-AUTH-01 | CFDI UUID and tax correction values persist on system clipboard without … | LOW | sin panelear | batch-7 | frontend/src/components/ResolutionPanel.tsx:18 | — |
| B8-BATCH-AUTH-01 | Full backend error responses leaked through batch API client to user-fac… | MEDIUM | panel unánime | batch-8 | frontend/src/lib/batch-api-client.ts:56 | — |
| B8-BATCH-CRYPTO-01 | Console.log leaks API base URL on every batch operation in production | LOW | panel unánime | batch-8 | frontend/src/lib/pdf-download.ts:8 | — |
| B8-BATCH-CRYPTO-02 | No integrity verification (hash/checksum) for downloaded PDF blobs and b… | LOW | rechazado por panel | batch-8 | frontend/src/lib/pdf-download.ts:508 | — |
| B8-BATCH-INJ-01 | localStorage batchId injected unsanitized into Pusher channel subscripti… | LOW | panel mayoría | batch-8 | frontend/src/lib/pdf-download.ts:412 | — |
| B8-EXTW-AUTH-01 | Mass fiscal data exported to downloads folder with no access control or … | MEDIUM | panel mayoría | batch-8 | frontend/src/app/hooks/useCfdiExports.ts:181 | — |
| B8-EXTW-AUTH-02 | Export button label and scope misleading — all rows exported regardless … | LOW | rechazado por panel | batch-8 | frontend/src/app/hooks/useCfdiExports.ts:184 | — |
| B8-EXTW-INJ-01 | CSV Formula Injection: escapeCsv escapes only double quotes, no formula … | MEDIUM | panel unánime | batch-8 | frontend/src/app/hooks/useCfdiExports.ts:15 | — |
| B8-FINDINGS-AUTH-01 | Backend SAT enquiry error details rendered raw in InspectorHeader DOM wi… | MEDIUM | panel unánime | batch-8 | frontend/src/components/InspectorHeader.tsx:210 | — |
| B8-FINDINGS-AUTH-02 | RFC emisor string exposed in SAT enquiry error title tooltip attribute | LOW | panel mayoría | batch-8 | frontend/src/components/InspectorHeader.tsx:209 | — |
| B8-FINDINGS-INJ-01 | Clipboard formula injection via unsanitized CFDI UUID from untrusted XML | MEDIUM | panel unánime | batch-8 | frontend/src/components/ResolutionPanel.tsx:18 | — |
| B8-FINDINGS-INJ-02 | NaN/Infinity propagation from untrusted XML renders garbage in monetary … | LOW | panel unánime | batch-8 | frontend/src/components/ConceptDetailModal.tsx:55 | — |
| B8-FINDINGS-INJ-03 | Unsanitized XML tax code values interpolated into copy-able correction s… | LOW | panel mayoría | batch-8 | frontend/src/app/hooks/useFindingContexts.ts:190 | — |
| B8-SHELL-AUTH-01 | VITE environment variables logged to browser console at application star… | MEDIUM | panel unánime | batch-8 | frontend/src/main.tsx:18 | — |
| B8-SHELL-AUTH-02 | Batch share URL (?batch=<id>) used as sole authorization token with no a… | HIGH | panel mayoría | batch-8 | frontend/src/App.tsx:69 | — |
| B8-SHELL-AUTH-03 | SSE EventSource URL constructed without authentication or session valida… | MEDIUM | panel mayoría | batch-8 | frontend/src/App.tsx:259 | — |
| B8-SHELL-AUTH-04 | React DevTools enabled in production exposes full App state with fiscal … | MEDIUM | panel mayoría | batch-8 | frontend/src/App.tsx:60 | — |
| B8-SHELL-CRYPTO-01 | Hardcoded Sentry DSN fallback in main.tsx sends telemetry to fixed produ… | LOW | panel unánime | batch-8 | frontend/src/main.tsx:14 | — |
| B8-SHELL-INJ-01 | URL query parameter `batch` flows unsanitized into API URL and Pusher ch… | MEDIUM | panel mayoría | batch-8 | frontend/src/App.tsx:106 | — |
| B8-SHELL-INJ-02 | Content-Disposition filename extracted without sanitization used as down… | LOW | panel mayoría | batch-8 | frontend/src/App.tsx:283 | — |
| B8-SHELL-INJ-03 | Server-provided jobId interpolated into fetch/EventSource URLs without v… | LOW | panel mayoría | batch-8 | frontend/src/App.tsx:259 | — |
| B8-XML-AUTH-01 | Full CFDI XML content rendered in DOM exposing all sensitive fiscal data… | MEDIUM | panel unánime | batch-8 | frontend/src/components/XmlNodeViewer.tsx:89 | — |
| B8-XML-AUTH-02 | Emisores API client performs all CRUD operations without authentication … | HIGH | panel mayoría | batch-8 | frontend/src/lib/emisores-api-client.ts:19 | — |
| B8-XML-AUTH-03 | Modified CFDI XML downloadable via onAcceptChange without access control… | LOW | panel mayoría | batch-8 | frontend/src/components/XmlNodeViewer.tsx:167 | — |
| B8-XML-INJ-01 | NaN/Infinity propagation through parseFloat in batch statistics, bypassi… | LOW | panel unánime | batch-8 | frontend/src/lib/useBatchStats.ts:59 | — |
| B8-XML-INJ-02 | Untrusted XML numeric values injected into diagnostic display strings vi… | LOW | panel unánime | batch-8 | frontend/src/cfdi/application/cfdiAnalysisService.ts:53 | — |
| B8-XML-INJ-03 | Unvalidated backend JSON deserialization into typed interfaces via unche… | LOW | panel mayoría | batch-8 | frontend/src/lib/cfdi-api-client.ts:130 | — |
| BATCH6-CANDIDATE-01 | Entire API surface (~30+ endpoints) has zero authentication — no middlew… | CRITICAL | panel unánime | batch-6 | backend/app/main.py:55 | — |
| BATCH6-CANDIDATE-02 | Batch worker-task endpoint has zero authentication — arbitrary GCS objec… | CRITICAL | panel unánime | batch-6 | backend/app/routers/batch.py:210 | — |
| BATCH6-CANDIDATE-03 | Emisor credential CRUD (create, overwrite, delete) completely unauthenti… | CRITICAL | panel unánime | batch-6 | backend/app/routers/emisores.py:54 | — |
| BATCH6-CANDIDATE-04 | Vercel rewrite makes internal Cloud Tasks endpoints same-origin — x-clou… | HIGH | panel unánime | batch-6 | frontend/vercel.json:5 | — |
| BATCH6-CANDIDATE-05 | Batch SAT enquiry accepts Excel uploads with no authentication — enables… | HIGH | panel unánime | batch-6 | backend/app/routers/sat_enquiry.py:312 | — |
| BATCH6-CANDIDATE-06 | Formula injection via user-supplied Excel fields reflected in output XLS… | MEDIUM | sin panelear | batch-6 | backend/app/routers/sat_enquiry.py:261 | — |
| BATCH6-CANDIDATE-07 | Batch SAT enquiry result endpoint retrievable without authentication — o… | MEDIUM | sin panelear | batch-6 | backend/app/routers/sat_enquiry.py:372 | — |
| BATCH6-CANDIDATE-08 | CFDI analysis endpoint /api/cfdi/analyze has no authentication — anyone … | MEDIUM | sin panelear | batch-6 | backend/app/main.py:164 | — |
| BATCH6-CANDIDATE-09 | Unsanitized UploadFile.filename interpolated into GCS blob paths allows … | MEDIUM | sin panelear | batch-6 | backend/app/routers/batch.py:137 | — |
| BATCH6-CANDIDATE-10 | Header injection via unsanitized rfc_presentante in Content-Disposition … | MEDIUM | sin panelear | batch-6 | backend/app/routers/batch.py:339 | — |
| BATCH6-CANDIDATE-11 | Race condition in credential file persistence — read-modify-write with n… | MEDIUM | sin panelear | batch-6 | backend/app/credentials.py:49 | — |
| BATCH6-CANDIDATE-12 | Shared Fernet encryption key between FIEL key material and PAC credentia… | MEDIUM | sin panelear | batch-6 | backend/app/fiel_config.py:10 | — |
| BATCH6-CANDIDATE-13 | GET /api/fiel/status exposes configured FIEL RFC without authentication … | MEDIUM | sin panelear | batch-6 | backend/app/routers/rfc_validation.py:125 | — |
| BATCH6-CANDIDATE-14 | POST /api/rfc/validate/sat without rate limiting — allows account lockou… | MEDIUM | sin panelear | batch-6 | backend/app/routers/rfc_validation.py:98 | — |
| BATCH6-CANDIDATE-15 | CSV formula injection via unsanitized cell values in BatchAnalysisPage e… | MEDIUM | sin panelear | batch-6 | frontend/src/components/BatchAnalysisPage.tsx:189 | — |
| BATCH6-CANDIDATE-16 | FIEL private key password stored in React state — visible in React DevTo… | MEDIUM | sin panelear | batch-6 | frontend/src/components/EmisoresPage.tsx:194 | — |
| BATCH6-CANDIDATE-17 | Diverza credential_token stored in React state — visible in React DevToo… | MEDIUM | sin panelear | batch-6 | frontend/src/components/EmisoresPage.tsx:31 | — |
| BATCH6-CANDIDATE-18 | Pusher public channel broadcasts sensitive fiscal data without authentic… | MEDIUM | sin panelear | batch-6 | frontend/src/lib/pdf-download.ts:412 | — |
| BATCH6-CANDIDATE-19 | Batch share URL grants unauthenticated access to batch progress and PDF … | MEDIUM | sin panelear | batch-6 | frontend/src/components/ConversionMasivaPage.tsx:62 | — |
| BATCH6-CANDIDATE-20 | Divergent env var strategies (merge vs overwrite) between two CI pipelin… | MEDIUM | sin panelear | batch-6 | backend/cloudbuild.yaml:41 | — |
| BATCH6-CANDIDATE-21 | Master encryption key stored alongside encrypted data in ~/.cfdi-suite/ … | LOW | sin panelear | batch-6 | backend/app/fiel_config.py:10 | — |
| BATCH6-CANDIDATE-22 | TOCTOU race condition in Fernet key generation on cold start — concurren… | LOW | sin panelear | batch-6 | backend/app/fiel_config.py:16 | — |
| BATCH6-CANDIDATE-23 | FIEL password stored in plaintext within Fernet blob alongside key mater… | LOW | sin panelear | batch-6 | backend/app/fiel_config.py:26 | — |
| BATCH6-CANDIDATE-24 | Race condition in save_fiel/load_fiel/delete_fiel — concurrent operation… | LOW | sin panelear | batch-6 | backend/app/fiel_config.py:28 | — |
| BATCH6-CANDIDATE-25 | Entity expansion DoS via stdlib ET.fromstring without defusedxml in XML … | LOW | sin panelear | batch-6 | backend/wrappers/python-satcfdi-wrapper.py:406 | — |
| BATCH6-CANDIDATE-26 | Pusher channel event data consumed as 'any' type without schema validati… | LOW | sin panelear | batch-6 | frontend/src/components/BatchAnalysisPage.tsx:813 | — |
| BATCH6-CANDIDATE-27 | SSE event data JSON.parsed without schema validation — malformed events … | LOW | sin panelear | batch-6 | frontend/src/lib/sat-enquiry-api-client.ts:87 | — |
| BATCH6-CANDIDATE-28 | File upload handlers rely solely on file extension without content-type … | LOW | sin panelear | batch-6 | frontend/src/components/ConversionMasivaPage.tsx:176 | — |
| BATCH6-CANDIDATE-29 | localStorage batchId used for API URL construction without sanitization … | LOW | sin panelear | batch-6 | frontend/src/components/BatchAnalysisPage.tsx:770 | — |
| BATCH6-CANDIDATE-30 | Vite proxy changeOrigin:true can bypass production CORS when misconfigur… | LOW | sin panelear | batch-6 | frontend/vite.config.ts:25 | — |
| BATCH6-CANDIDATE-31 | GCS signed URL access_token in query string combined with CORS wildcard … | LOW | sin panelear | batch-6 | backend/app/routers/pdf.py:668 | — |
| BATCH6-CANDIDATE-32 | Production Cloud Run URL hardcoded in multiple public versioned files — … | LOW | sin panelear | batch-6 | frontend/vercel.json:5 | — |
| TEMPLATE-PATH-TRAVERSAL-01 | Path traversal via template_id sin validar en 7 endpoints | MEDIUM | rechazado por panel | batch-4 | backend/app/routers/templates.py:160,304,317,335,341,357,421,428 | — |
| #1 | XXE via lxml en produccion | CRITICAL | OPEN | audit | canvas_service.py:835,869,983 | Sí |
| #10 | Excel formula injection | MEDIUM | OPEN | audit | - | Sí |
| #11 | SSTI via template upload | MEDIUM | OPEN | audit | - | Sí |
| #12 | Pusher public channels — no auth | MEDIUM |  | audit | - | Sí |
| #13 | Signed URL `access_token` en logs | MEDIUM | OPEN | audit | - | Sí |
| #14 | `pickle.loads` en codigo | MEDIUM | OPEN | audit | - | Sí |
| #15 | Race condition en batch TTL | MEDIUM | OPEN | audit | - | Sí |
| #16 | Dependency confusion risk | MEDIUM | OPEN | audit | - | Sí |
| #17 | SRI missing on third-party scripts | MEDIUM | OPEN | audit | - | Sí |
| #18 | `_job_results` loggea solo 5 entries | MEDIUM |  | audit | - | Sí |
| #19 | CORS `allow_methods=["*"]` | LOW | TRIVIAL | audit | - | Sí |
| #2 | Cloud Tasks sin OIDC — endpoints internos spoofables | CRITICAL | OPEN | audit | task_dispatcher.py:30-36, pdf.py:107-108, batch.py:213-231,301 | Sí |
| #20 | `console.log` de variables Vite en prod | LOW | TRIVIAL | audit | - | Sí |
| #21 | `SSL_CERT_REQS` inconsistente entre batch y API | LOW | TRIVIAL | audit | batch.py:49 tiene ssl_cert_reqs="required" pero pdf.py:74 y batch_shard_worker.py:59 tienen None. | Sí |
| #22 | `PUSHER_KEY` y `VERCEL_URL` en GitHub Secrets | LOW | TRIVIAL | audit | - | Sí |
| #23 | Timeout Cloud Run documentado a 1800s | LOW | TRIVIAL | audit | - | Sí |
| #24 | Vercel sin headers de seguridad | HIGH | OPEN | audit | - | Sí |
| #25 | GCS CORS wildcard (`"*"`) | HIGH | OPEN | audit | - | Sí |
| #26 | Cloud Run usa default compute SA con Editor | HIGH | OPEN | audit | deploy-backend.yml:61-67 | Sí |
| #27 | Pusher key hardcodeada en prod | MEDIUM | OPEN | audit | - | Sí |
| #28 | `VERCEL_TOKEN` via `--token=` flag | MEDIUM | OPEN | audit | - | Sí |
| #29 | Sin pre-commit hooks | MEDIUM | OPEN | audit | - | Sí |
| #3 | Cross-session data leak via `_job_results` | HIGH | OPEN | audit | sat_enquiry.py:24,359-374 | Sí |
| #30 | Secretos en `--set-env-vars` de Cloud Run | MEDIUM | OPEN | audit | - | Sí |
| #31 | Batch shard job sin SA dedicada ni secretos | MEDIUM | OPEN | audit | - | Sí |
| #32 | detect-secrets baseline stale (19 dias) | LOW | TRIVIAL | audit | - | Sí |
| #33 | `npm audit` no funcional | LOW | TRIVIAL | audit | - | Sí |
| #34 | Supply chain: sin hash pinning en requirements.txt | LOW | TRIVIAL | audit | - | Sí |
| #35 | SSRF via WeasyPrint — shell_preview | HIGH | OPEN | audit | shell_service.py:255-257, templates.py:357-371 | Sí |
| #36 | FIEL (e.firma) usado sin autenticacion contra el SAT | MEDIUM | OPEN | audit | - | Sí |
| #37 | FIEL (e.firma) se puede sobrescribir o borrar sin autenticacion | MEDIUM | OPEN | audit | - | Sí |
| #38 | SSRF via UUID path traversal a Diverza API | HIGH |  | audit | - | Sí |
| #39 | Zip bomb / Memory DoS via openpyxl sin `read_only` | HIGH |  | audit | - | Sí |
| #4 | Error details leaked in HTTP responses | HIGH | OPEN | audit | sat_enquiry.py:193-198,303, main.py:75, templates.py, pdf.py, batch.py:334, rfc_validation.py | Sí |
| #40 | Iframe srcDoc con HTML sin sanitizar + `allow-same-origin` indocumentado | MEDIUM |  | audit | - | Sí |
| #41 | Cero sanitizacion HTML en pipeline de templates | MEDIUM | OPEN | audit | InvoiceDesigner.jsx:1458, templates.py:341-349, shell_service.py:175-178 | Sí |
| #42 | Ausencia de `.dockerignore` — `.env` bakeado en imagen Docker | MEDIUM | OPEN | audit | - | Sí |
| #43 | Sin validacion MIME/content-type en uploads | MEDIUM | OPEN | audit | zip_manifest.py:21-24, pdf.py:240-243, batch.py:102-110 | Sí |
| #44 | Sin limite de tamano por archivo en batch_analyze → OOM | MEDIUM | OPEN | audit | batch.py:78,102-110, policy.py:3 | Sí |
| #45 | Batch status endpoint sin autenticacion | MEDIUM |  | audit | - | Sí |
| #46 | Diverza response → formula injection en Excel | MEDIUM | OPEN | audit | sat_enquiry.py:95-98,198,259-272 | Sí |
| #47 | Base image sin digest pinning | MEDIUM | OPEN | audit | - | Sí |
| #48 | Single-stage build retiene build tools en imagen final | MEDIUM |  | audit | - | Sí |
| #49 | `pip install` sin `--require-hashes` en Dockerfile | MEDIUM | OPEN | audit | - | Sí |
| #5 | Fernet key silent loss on cold start | MEDIUM | OPEN | audit | - | Sí |
| #50 | Contenedor corre como root — sin `USER` directive | LOW |  | audit | - | Sí |
| #51 | logoUrl interpolada en HTML sin escape | LOW |  | audit | - | Sí |
| #52 | Blob URLs abiertas via `window.open()` sin sandbox | LOW |  | audit | - | Sí |
| #53 | apt packages sin version pinning | LOW |  | audit | - | Sí |
| #54 | Sin `HEALTHCHECK` en Dockerfile | LOW |  | audit | - | Sí |
| #55 | `cloudbuild.yaml` sin `--service-account` | LOW |  | audit | - | Sí |
| #56 | Divergencia merge vs overwrite entre pipelines | LOW |  | audit | - | Sí |
| #57 | Filename del usuario interpolado en rutas GCS sin sanitizar | LOW |  | audit | - | Sí |
| #58 | Doc-code mismatch: `is_valid_xml_entry` | LOW |  | audit | - | Sí |
| #59 | `credential_id` expuesto en API publica de emisores | LOW |  | audit | - | Sí |
| #6 | Zero rate limiting — Diverza credits exposed | HIGH | OPEN | audit | main.py, sat_enquiry.py:286, batch.py:102 | Sí |
| #60 | `console.log` de URL de API en BatchAnalysisPage + pdf-download | LOW |  | audit | - | Sí |
| #61 | URL hardcodeada de Cloud Run como fallback | LOW |  | audit | - | Sí |
| #62 | Path traversal via `template_id` sin validar — REFUTADO por panel advers… | MEDIUM | OPEN (LOW) | audit | templates.py:304,317,335-338,341-349,357-371,421-439 | Sí |
| #7 | No CI security scanning | HIGH |  | audit | - | Sí |
| #8 | `ET.fromstring` sin `defusedxml` | HIGH | OPEN | audit | Archivos listados | Sí |
| #9 | Redis `ssl_cert_reqs=None` | HIGH | OPEN | audit | - | Sí |

## Hallazgos Rechazados por Panel Adversarial

Estos hallazgos fueron evaluados por el panel de 3 votantes y recibieron <2 votos TRUE_POSITIVE. No se eliminan del registro — si desaparecen del código, el próximo scan los vuelve a encontrar y se re-triagean.

| id | título | severidad propuesta | reclasificado | motivo del panel |
|---|---|---|---|---|
| B7-CFDI-INJ-01 | XXE / Billion Laughs entity expansion via ET.fromstring in Pytho… | MEDIUM | FALSE_POSITIVE | 0/3 TRUE_POSITIVE — reclasificado FALSE_POSITIVE |
| B7-CI-CRYPTO-01 | Production secrets on disk in backend/.env — PUSHER_SECRET, REDI… | HIGH | FALSE_POSITIVE | 0/3 TRUE_POSITIVE — reclasificado FALSE_POSITIVE |
| B7-CI-CRYPTO-03 | Long-lived GCP Service Account Key used instead of Workload Iden… | MEDIUM | FALSE_POSITIVE | 1/3 TRUE_POSITIVE — reclasificado FALSE_POSITIVE |
| B7-CI-INJ-01 | Four opentelemetry packages completely unpinned — dependency con… | MEDIUM | FALSE_POSITIVE | 1/3 TRUE_POSITIVE — reclasificado FALSE_POSITIVE |
| B8-BATCH-CRYPTO-02 | No integrity verification (hash/checksum) for downloaded PDF blo… | LOW | FALSE_POSITIVE | 1/3 TRUE_POSITIVE — reclasificado FALSE_POSITIVE |
| B8-EXTW-AUTH-02 | Export button label and scope misleading — all rows exported reg… | LOW | FALSE_POSITIVE | 1/3 TRUE_POSITIVE — reclasificado FALSE_POSITIVE |
| TEMPLATE-PATH-TRAVERSAL-01 | Path traversal via template_id sin validar en 7 endpoints | MEDIUM | LOW | Defense-in-depth gap, no explotable en producción actual. Fix de hardening (30 min). |
