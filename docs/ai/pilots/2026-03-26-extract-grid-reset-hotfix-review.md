# HOTFIX REVIEW

DECISION REFERENCE:
- docs/ai/pilots/2026-03-26-extract-grid-reset-hotfix.md

RESULT:
`resetAll()` now restores the dataset-aware default sort key: `descripcion` for `ingresos` and `fechaPago` for `pagos`.

DEVIATION REVIEW:
- Incident addressed: yes
- Scope expansion: no
- Additional behavior introduced: no
- Return to exploration required: no

VERIFICATION:
- npm test
- npm run build
- diff review of `src/app/hooks/useExtractGridState.ts`

FRICTION FOUND:
- This hotfix was straightforward because the hook already had the correct default sort logic in other reset paths. The main value here was confirming that the compressed hotfix template was enough to guard scope on a narrow bug.
