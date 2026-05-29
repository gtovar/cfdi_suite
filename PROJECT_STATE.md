# PROJECT_STATE — CFDI Suite (antes cfdi_inspector)
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
main

## Último cambio
CFDI Suite Fase 2 completada: Consultas SAT vía Diverza.
- Backend: `routers/sat_enquiry.py` — POST /api/sat/enquiry (individual), POST /api/sat/enquiry/batch
  (xlsx upload → SSE progreso → job_id), GET /api/sat/enquiry/batch/{job_id}/result (descarga xlsx).
  Lógica: parsing robusto de respuesta JSON de Diverza, regla "No cancelable estatus", 20 conexiones
  concurrentes con httpx.Limits. Deps añadidas: httpx, openpyxl, python-multipart.
- Frontend: `ConsultasSATPage.tsx` (batch: drop xlsx, barra de progreso SSE, descarga),
  `OperacionesPage.tsx` (card Consultas SAT ahora clickable), `InspectorHeader.tsx` (botón
  "Consultar SAT" + chip de resultado inline), `useSatEnquiry.ts` (hook), `sat-enquiry-api-client.ts`.
- Tests: 13 nuevos backend (24 total) + 51 frontend pasan.

## Próximo paso
1. Sesión B (pendiente): implementar `cfdi.findings` ricos desde python-satcfdi
2. CFDI Suite Fase 3: Reprint PDF/XML vía Diverza

## Riesgos abiertos
- `.secrets.baseline` debe actualizarse si se añaden nuevos archivos con valores de alta entropía legítimos
- Obligación "Implement a secrets detection strategy" en governance server requiere cierre manual
- `~/.cfdi-suite/secret.key` es la llave maestra; si se pierde, las credenciales guardadas no son recuperables
