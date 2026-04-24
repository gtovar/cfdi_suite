# API V1 Semantics Appendix

## Propósito

Cerrar la semántica de `POST /api/cfdi/analyze` para que:

- el contrato v1 no quede solo en shape
- `meta`, `issues`, `warnings`, `degraded` y `fallback` tengan significado preciso
- el equipo pueda decidir cambios sin ambigüedad

## Regla general

El contrato v1 es estable para la UI actual.

Eso implica:

- cambios incompatibles requieren nueva versión
- cambios compatibles pueden enriquecer campos opcionales
- la semántica de campos existentes no debe cambiar silenciosamente

## Request v1

### Campo obligatorio

- `xml`: string con contenido XML del CFDI
- límite operativo v1: `1_000_000` caracteres

### Campos opcionales recomendados

- `options.profileHint`
- `options.includeRows`
- `options.includeFindings`
- `options.debug`

## Response v1

### Campos obligatorios

- `profile`
- `cfdi`
- `ingresoRows`
- `pagoRows`
- `issues`
- `meta`

### Fuente oficial de findings

Decisión:

- la fuente oficial de findings en v1 debe ser `cfdi.findings`

Consecuencia:

- si existe `findings` top-level, debe tratarse como legacy candidate y no debe consolidarse como segunda fuente semántica

## Semántica de `profile`

Valores válidos:

- `ingreso`
- `pagos`
- `unknown`

Reglas:

- `unknown` no implica automáticamente error fatal
- `unknown` sí obliga a revisar `issues` y `meta.degraded`
- la plataforma, no el provider, decide el valor final publicado

## Semántica de `cfdi`

- `cfdi` contiene la proyección estructural principal para la UI
- `cfdi = null` solo es aceptable cuando el resultado no es usable
- si `cfdi = null`, debe existir al menos un `issue.fatal = true`

## Semántica de `ingresoRows` y `pagoRows`

- son proyecciones derivadas para la UI
- no son el contrato canónico del dominio
- pueden llegar vacías sin error fatal si la capability sigue siendo usable y la degradación queda declarada

## Semántica de `issues`

`issues` representa problemas técnicos o contractuales del request/proceso.

No debe mezclarse con findings fiscales del producto.

### Clases mínimas de `issues`

- request inválido
- parseo CFDI inválido
- fallo de provider/runtime
- capability no soportada
- resultado degradado pero usable

### Reglas

- `issue.fatal = true` significa que la respuesta no es usable como análisis principal
- `issue.fatal = false` significa que hay limitación declarada pero aún existe utilidad parcial o total
- `issues` debe ser suficiente para explicar por qué hay `degraded = true`

## Semántica de `meta`

`meta` describe cómo se obtuvo la respuesta, no el contenido fiscal del CFDI.

### Campos mínimos semánticos

- `contractVersion`
- `capability`
- `provider`
- `providerMode`
- `degraded`
- `requestId`

### Campos opcionales recomendados

- `providerVersion`
- `warnings`
- `timingMs`
- `fallbackReason`

## Semántica de `providerMode`

Valores recomendados:

- `primary`
- `fallback`
- `comparison`
- `bridge`

### Significado

- `primary`: resultado emitido por el camino principal esperado
- `fallback`: resultado emitido por ruta alternativa aprobada
- `comparison`: ejecución interna no pensada como camino principal de usuario
- `bridge`: indica modo técnico transicional de integración, no prioridad funcional

## Semántica de `degraded`

`degraded = true` significa:

- la respuesta sigue siendo usable al menos en parte
- pero existe una limitación declarada que reduce completitud, fidelidad o camino normal

`degraded = false` significa:

- no se detectó degradación relevante para el contrato v1

### Casos típicos de `degraded = true`

- findings incompletos
- filas no disponibles por limitación conocida
- provider primario no disponible con fallback exitoso
- metadata secundaria faltante pero análisis usable

### Casos donde `degraded` no basta

- request inválido
- parseo inválido sin resultado usable
- respuesta sin `cfdi` y sin estructura mínima

Ahí debe existir error fatal.

## Semántica de `warnings`

- `warnings` vive dentro de `meta`
- expresa notas de ejecución o limitaciones no suficientemente fuertes para convertirse en `issues`
- no sustituye a `issues`

## Semántica de `requestId`

- debe existir en toda respuesta v1
- sirve para trazabilidad técnica
- no debe contener datos sensibles

### Decisión abierta controlada

Todavía puede decidirse si:

- se genera exclusivamente en backend
- o si el cliente puede propagar uno propio

Pero v1 requiere un identificador final publicado por la plataforma.

## Semántica de fallback

La respuesta que vino de fallback debe declararlo explícitamente mediante:

- `meta.providerMode = fallback`
- `meta.degraded = true` cuando aplique
- `meta.fallbackReason` cuando sea útil y seguro

### Catálogo mínimo cerrado de `fallbackReason`

- `provider_runtime_failure`: el provider primario no pudo completar la ejecución y la plataforma emitió resultado desde la ruta alterna

## Compatibilidad hacia atrás

### Cambios compatibles

- agregar campos opcionales nuevos
- enriquecer `warnings`
- enriquecer metadata adicional

### Cambios incompatibles

- cambiar significado de `degraded`
- mover la fuente oficial de findings sin migración explícita
- eliminar campos obligatorios
- cambiar el significado contractual de `providerMode`

## Escenarios de referencia

### 1. Éxito normal

- `cfdi` presente
- `issues` vacío o solo warnings no críticas
- `meta.providerMode = primary`
- `meta.degraded = false`

### 2. Parse failure

- `cfdi = null`
- `issues` contiene error fatal
- `meta.degraded` puede ser `false` o `true`, pero no sustituye el fatal

### 3. Request inválido

- la plataforma puede responder `422`
- la respuesta sigue publicando la forma contractual v1
- `cfdi = null`
- `issues` contiene error fatal seguro
- no se expone detalle interno del validador

### 3. Resultado degradado usable

- `cfdi` presente
- `issues` contiene limitación no fatal o `warnings`
- `meta.degraded = true`

### 4. Fallback exitoso

- `cfdi` presente
- `meta.providerMode = fallback`
- `meta.degraded = true` si hubo degradación relevante frente al camino principal

## Tests contractuales mínimos

- shape estable de `meta`
- presencia obligatoria de `requestId`
- coherencia entre `cfdi = null` y `issue.fatal = true`
- coherencia entre fallback y `providerMode`
- existencia de una sola fuente oficial de findings
