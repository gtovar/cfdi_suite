# PROJECT_STATE — cfdi_inspector
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
experiment/sidebar-context-and-ui-baseline

## Último cambio
Governance completado: detect-secrets instalado y configurado en pre-commit hook,
governance.json corregido a strategy "git-hooks" (alineado con .git/hooks/pre-commit existente),
.gitignore actualizado con patrones Python cache.

## Próximo paso
Retomar trabajo en sidebar: contexto de findings (`useFindingContexts`) y UI baseline.

## Riesgos abiertos
- `src/app/utils/` untracked: verificar si es código nuevo que debe commitearse
- `.secrets.baseline` debe actualizarse si se añaden nuevos archivos con valores de alta entropía legítimos
