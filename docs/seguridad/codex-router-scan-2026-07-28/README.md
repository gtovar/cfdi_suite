# Scan Codex de routers — 2026-07-28

Registro persistente del análisis y sus decisiones antes de cambiar código. Los
planes se evaluaron individualmente con `decision-expander`; cada documento
contiene sus diez lentes, evidencia, implementación, pruebas y rollback.

| Plan | Decisión | Alcance de esta sesión |
|---|---|---|
| [01 — Propiedad de rutas GCS](01-gcs-path-ownership.md) | Proceder — **cerrado y validado en producción** | Sí |
| [02 — Presupuestos ZIP](02-zip-resource-budgets.md) | Proceder — **implementado y desplegado** | Sí |
| [03 — Presupuestos multipart](03-multipart-memory-budgets.md) | Proceder — **implementado; pendiente de revisión de cierre** | Sí |
| [04 — Cola XLSX/SAT](04-sat-xlsx-work-queue.md) | Proceder | No |
| [05 — Query auth y rate limit](05-query-auth-rate-limit.md) | Proceder | No |
| [06 — Borde de `template_id`](06-template-id-boundary.md) | Proceder como hardening | No |
| [07 — Auth fail-closed en producción](07-production-auth-fail-closed.md) | Proceder como garantía de despliegue | No |

No se edita `registro-unificado.md`: es un artefacto generado. El Plan 01 se
cerró con pruebas locales, deploy Cloud Run exitoso y smoke autenticado; ver
[09 — Reporte de validación](09-plan-01-validation-report.md). Los planes 04–07
siguen siendo decisiones de trabajo pendientes, no declaración de implementación.
El Plan 02 se implementó en `9a524d6` y forma parte de la revisión de
producción actual; sus pruebas cubren los presupuestos y el fixture compatible
de 367 MB.
El Plan 03 está implementado localmente: límite ASGI previo al parseo,
presupuestos por ruta y lecturas secuenciales. Falta la revisión explícita de
cierre antes de declararlo cerrado.
