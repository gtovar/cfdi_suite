# Session Closeout — 2026-04-17

## Qué quedó cerrado

- benchmark estricto de `current-ts` operativo
- adaptador `python-satcfdi` operativo sobre el mismo corpus
- runtime local `.venv-satcfdi` preparado para benchmark
- `python-satcfdi` ya devuelve `profile`, `cfdi` mínimo y datasets básicos
- matriz de decisión poblada con evidencia real de ambos motores
- `useCfdiAnalysis` ya consume el resultado contractual directo sin pasar por `toLegacyAnalysisBundle(...)`

## Estado real al cerrar

- `current-ts` sigue siendo el motor principal del producto hoy
- `python-satcfdi` sigue siendo el mejor candidato de dominio amplio
- ambos motores pasan `10/10` fixtures estrictos del corpus actual
- solo `current-ts` emite findings útiles para la UX de inspección
- la decisión final del motor para el producto actual queda cerrada con la evidencia actual
- el flujo interno principal ya no depende del bundle legacy histórico
- la compatibilidad legacy restante quedó acotada principalmente al wrapper público `analyzeCFDI`

## Qué no debe rediscutirse al reabrir

- `cfdi_inspector` se conserva como producto
- no habrá híbrido permanente
- `python-satcfdi` se evalúa como motor, no como producto
- el benchmark actual ya es suficiente para comparar parseo estructural y datasets
- findings equivalentes en `python-satcfdi` no son requisito para cerrar la decisión actual
- `current-ts` se conserva como motor principal del producto actual
- `useCfdiAnalysis` ya no es remanente legacy activo

## Próxima unidad natural

Cerrar formalmente la fase 07 con este orden:

1. congelar `python-satcfdi` como benchmark o referencia de dominio
2. fijar capability map definitivo en la documentación de migración/retiro
3. decidir si el wrapper público `analyzeCFDI` sigue siendo necesario o puede retirarse

La decisión del motor solo se reabre si:

1. el producto cambia hacia dominio SAT más amplio, o
2. `python-satcfdi` demuestra valor contractual nuevo para la UI actual

## Reentrada mínima

Leer en este orden:

1. [STATUS.md](./STATUS.md)
2. [07-migration-and-retirement.md](./07-migration-and-retirement.md)
3. [08-session-management.md](./08-session-management.md)
4. si hace falta contexto adicional:
   - [06-engine-decision-matrix.md](./06-engine-decision-matrix.md)
   - [05-python-satcfdi-adapter.md](./05-python-satcfdi-adapter.md)

## Prompt exacto sugerido para la próxima sesión

```text
Lee STATUS.md y 07-migration-and-retirement.md. Quiero cerrar formalmente la fase 07: congela python-satcfdi como benchmark, valida el capability map actual y dime si analyzeCFDI todavía debe vivir o ya se puede retirar.
```
