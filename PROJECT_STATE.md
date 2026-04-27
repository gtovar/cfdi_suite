# PROJECT_STATE — cfdi_inspector
> Actualizar antes de cada commit con cambios de código

## Checkpoint activo
experiment/sidebar-context-and-ui-baseline

## Último cambio
Sesión C completada: retiro del fallback local del frontend. El api-client ya no ejecuta
el motor TypeScript local cuando el backend no responde — los errores de red propagaran
al usuario con mensaje claro. Removidos: `analysisEngine`, `analysisReason`, badge UI de
fallback, `isApiUnavailableError`. Tests actualizados (6/6 pasan).

## Próximo paso
Sesión B: implementar `cfdi.findings` ricos desde python-satcfdi y reemplazar placeholders
de `verdict` y `supportText` (5 archivos backend + 1 frontend).

## Riesgos abiertos
- `.secrets.baseline` debe actualizarse si se añaden nuevos archivos con valores de alta entropía legítimos
- Obligación "Implement a secrets detection strategy" en governance server requiere cierre manual en http://localhost:3000
