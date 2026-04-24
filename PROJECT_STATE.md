# PROJECT_STATE — cfdi_inspector
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
experiment/sidebar-context-and-ui-baseline

## Último cambio
Governance completado + utils recuperados: detect-secrets configurado en pre-commit, governance.json
corregido a "git-hooks", .gitignore con patrones Python. Añadidos cfdiFormatters.ts y
findingUtils.ts (extraídos en refactor d2a6f98 pero sin commitear).

## Próximo paso
Retomar trabajo en sidebar: contexto de findings (`useFindingContexts`) y UI baseline.

## Riesgos abiertos
- `src/app/utils/` untracked: verificar si es código nuevo que debe commitearse
- `.secrets.baseline` debe actualizarse si se añaden nuevos archivos con valores de alta entropía legítimos
