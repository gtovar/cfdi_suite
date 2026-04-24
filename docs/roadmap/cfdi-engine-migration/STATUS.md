# STATUS

## Fase actual

Roadmap técnicamente completado; fase 08 queda activa solo como disciplina operativa.

Estado estratégico actual:
- este roadmap ya no es la ruta principal del producto
- desde `2026-04-18` la dirección estratégica se reabre hacia `frontend + backend Python`
- ver `docs/analysis/2026-04-18-python-backend-platform-decision.md`
- ver `docs/roadmap/python-backend-platform/`

Estado base heredado:
- fase 07 quedó cerrada con `python-satcfdi` congelado como benchmark y referencia de dominio
- la compatibilidad legacy interna basada en `analyzeCFDI` ya fue retirada
- la migración del engine ya no tiene backlog técnico fuerte dentro de este roadmap

## Hitos completados

- Documento de decisión base creado en `docs/analysis/2026-04-17-python-satcfdi-decision.md`
- Decisión final del motor emitida para el producto actual
- Contrato inicial de análisis creado
- Interfaz formal `CfdiAnalysisEngine` agregada
- Adaptador `current-ts` creado
- API pública con variante de contrato expuesta
- Worker alineado al adaptador nuevo
- `cfdi-worker-client` y `useCfdiAnalysis` alineados a la variante de contrato
- Extracción fallida degradada a issue no fatal cuando `cfdi` ya existe
- Tests iniciales del contrato y del motor actual agregados
- Corpus mínimo del benchmark versionado en `src/cfdi/benchmark/fixtures/`
- Runner repetible de benchmark para `current-ts` agregado
- Benchmark cubierto por test automatizado y script CLI
- Adaptador inicial `python-satcfdi` agregado al mismo runner compartido
- Wrapper Python local agregado con clasificación explícita de gaps y errores de runtime
- Runtime local `.venv-satcfdi` preparado para benchmark
- `python-satcfdi` ya entrega `cfdi` mínimo y datasets básicos dentro del mismo benchmark estricto
- Matriz de decisión actualizada con evidencia real de benchmark para ambos motores
- `useCfdiAnalysis` ya consume el resultado contractual directo sin pasar por `toLegacyAnalysisBundle(...)`
- `python-satcfdi` queda formalmente congelado para benchmark comparativo y referencia de dominio SAT
- capability map validado contra el código actual del producto
- `analyzeCFDI` quedó clasificado como wrapper legacy sin rol en el flujo principal y luego fue retirado
- `analyzeCFDI`, `CFDIAnalysisBundle`, `buildCfdiAnalysisBundle(...)` y `toLegacyAnalysisBundle(...)` fueron retirados del código activo
- la API pública de análisis queda reducida al contrato `analyzeCFDIContract`

## Seguimiento operativo

- mantener `08-session-management.md` y este `STATUS.md` al día al cerrar cada hito
- mantener `python-satcfdi` acotado a benchmark o referencia de dominio mientras no exista evidencia contractual nueva
- usar fase 08 como gate para decidir cuándo conviene iniciar nueva sesión

## Decisiones cerradas

- `cfdi_inspector` sigue como producto
- el motor CFDI debe ser intercambiable
- no habrá híbrido permanente
- `python-satcfdi` se evalúa como motor, no como producto
- `current-ts` se conserva como motor principal del producto actual
- findings equivalentes en `python-satcfdi` no son requisito para cerrar la decisión actual del motor
- el capability map vigente queda validado así:
  - parseo y perfilado del producto: `current-ts`
  - normalización de `cfdi` consumida por UI: `current-ts`
  - findings y framing operativo: `current-ts`
  - extracción de ingresos y pagos: `current-ts`
  - benchmark comparativo entre motores: `current-ts` y `python-satcfdi`
  - referencia de dominio SAT amplio fuera del flujo del producto: `python-satcfdi`
- `analyzeCFDI` ya no tiene consumidores internos de producción y fue retirado
- la superficie pública legacy basada en `CFDIAnalysisBundle` ya no forma parte del producto

## Condiciones de reapertura

- reabrir la decisión del motor solo si el producto cambia de alcance hacia dominio SAT más amplio
- reabrir la decisión del motor solo si `python-satcfdi` demuestra valor contractual adicional real para la UI, no solo paridad de parseo estructural
- evaluar una nueva capa pública de compatibilidad solo si aparece una necesidad real fuera del contrato actual

## Bloqueos actuales

- ninguno estructural
- el clone de `python-satcfdi` usado antes estuvo en `/tmp`, así que no debe asumirse persistente entre sesiones

## Próxima acción concreta

Usar `STATUS.md` y fase 08 como gate operativo para cualquier trabajo nuevo; no abrir otro frente del roadmap salvo que se active una condición de reapertura.

Nota posterior:
- la condición de reapertura estratégica sí se activó por cambio explícito de objetivo del producto
- la nueva unidad de trabajo ya no vive aquí sino en `docs/roadmap/python-backend-platform/`

## Reentrada mínima

Para retomar en sesión nueva:
1. leer este `STATUS.md`
2. leer `index.md`
3. ir a `08-session-management.md`

Si se necesita contexto adicional:
- `06-engine-decision-matrix.md`
- `05-python-satcfdi-adapter.md`
- `04-benchmark-and-corpus.md`
- `docs/analysis/2026-04-17-python-satcfdi-decision.md`
