# HOTFIX

INCIDENT:
The extract grid `resetAll()` function always restores sorting to `descripcion`, even when the active dataset is `pagos`, whose default sort should be `fechaPago`.

IMPACT:
Resetting the grid state can leave the internal default sort inconsistent with the active dataset semantics, which weakens the guarantee that reset returns the grid to its expected baseline.

HYPOTHESIS:
`resetAll()` uses a hard-coded sort key instead of the dataset-aware default already used elsewhere in the hook.

MINIMAL FIX:
Make `resetAll()` choose `fechaPago` for `pagos` and `descripcion` for `ingresos`, matching the existing reset behavior in `resetGrid()` and `resetForNewAnalysis()`.

RISK:
Low. The change is localized to reset behavior, but it must not alter sorting for other paths.

VALIDATION:
- npm test
- npm run build
- review the diff to confirm only the reset default sort key changed
