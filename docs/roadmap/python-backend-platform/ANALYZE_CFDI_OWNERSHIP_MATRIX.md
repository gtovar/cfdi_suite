# Analyze CFDI Ownership Matrix

## Propósito

Cerrar el ownership operativo de `analyze_cfdi` para evitar mezcla de responsabilidades entre:

- frontend
- API de plataforma
- capability layer
- provider
- proyección UI
- fallback TS

## Regla base

`analyze_cfdi` es una capability de plataforma.

No es:

- un endpoint HTTP solamente
- un wrapper de `python-satcfdi`
- una proyección UI
- una variante del motor TS

## Matriz de ownership

| Subresponsabilidad | Owner primario | Owner secundario | Salida afectada | Fallback permitido | Degradación permitida | Nota |
|---|---|---|---|---|---|---|
| `ingest_xml` | plataforma | ninguno | request validation | no | no | input inválido debe fallar antes de tocar provider |
| `transport_validation` | API de plataforma | ninguno | HTTP contract | no | no | shape del request y límites básicos |
| `request_metadata` | API de plataforma | capability | `meta.requestId`, trazabilidad | no | sí | puede degradarse si falta metadata opcional, no si rompe trazabilidad mínima |
| `detect_profile` | capability | provider | `profile`, routing lógico | sí | sí | la plataforma conserva la semántica final aunque use señal del provider |
| `extract_structured_cfdi` | provider | capability | datos canónicos base | sí | sí | si falla provider principal puede entrar fallback o modo degradado según política |
| `normalize_cfdi` | capability | ninguno | contrato canónico interno | no | sí | normaliza lenguaje del producto, no del provider |
| `derive_tabular_views` | capability | projection layer | `ingresoRows`, `pagoRows` | sí | sí | las filas son proyección, no núcleo del dominio |
| `compute_findings` | capability | ninguno | `findings`, `verdict`, `supportText` | sí | sí | findings son propiedad de plataforma |
| `classify_issues` | capability | API de plataforma | `issues`, `meta.degraded` | no | no | semántica de error/degradación es de plataforma |
| `assemble_response` | API de plataforma | capability | response HTTP v1 | no | no | consolida contrato v1 y garantiza consistencia |
| `ui_projection` | projection layer | capability | shape consumible por frontend | no | sí | no recalcula dominio fuerte |
| `render_progress_state` | frontend | ninguno | UX de progreso | sí | sí | el frontend solo comunica etapa y origen |
| `fallback_policy_decision` | plataforma | ninguno | `meta.providerMode`, comportamiento | no | no | la decisión de fallback no pertenece al frontend |
| `fallback_execution` | transición actual: frontend | futuro posible: backend | resultado alterno | sí | sí | declarado explícitamente como transición |
| `contract_backward_compatibility` | plataforma | ninguno | estabilidad v1 | no | no | owner documental y técnico debe estar fuera del provider |

## Decisiones cerradas por subresponsabilidad

### 1. Lo que nunca debe ser del provider

- semántica de `findings`
- semántica de `issues`
- shape del contrato HTTP v1
- política de degradación
- política de compatibilidad hacia atrás
- política de fallback

### 2. Lo que nunca debe ser del frontend

- clasificación fiscal fuerte
- política de fallback
- cálculo de findings canónicos
- semántica de degradación
- decisiones de provider

### 3. Lo que sí puede ser transicional

- lugar de ejecución del fallback TS
- bridge específico de `python-satcfdi`
- nivel de riqueza de metadata observacional

## Política de fallback por subresponsabilidad

### Se permite fallback

- `detect_profile`
- `extract_structured_cfdi`
- `derive_tabular_views`
- `compute_findings`

### No se permite fallback

- validación del request
- taxonomía de issues
- ensamblado del contrato HTTP
- política de compatibilidad

Razón:

Si esas piezas caen en fallback, la plataforma deja de ser dueña del contrato.

## Política de degradación por subresponsabilidad

### Degradación no permitida

- input inválido
- request sin XML usable
- response sin semántica contractual mínima

### Degradación permitida

- findings incompletos pero resultado estructural usable
- tablas omitidas por limitación explícita
- metadata secundaria faltante
- provider primario indisponible con fallback exitoso

## Evidencia requerida para retirar el fallback TS

Para retirar TS del flujo productivo normal, `analyze_cfdi` debe cumplir:

- estructura CFDI estable para `ingreso` y `pagos`
- findings de plataforma suficientemente útiles sin depender de TS como owner
- issues y degradación con semántica cerrada
- contract regression estable contra la UI actual
- observabilidad suficiente para detectar regresiones sin depender del fallback visible

## Riesgos si esta matriz no se respeta

- provider definiendo el producto por accidente
- frontend reteniendo dominio por costumbre
- fallback permanente escondido como "compatibilidad temporal"
- contratos ambiguos aunque el endpoint ya funcione

## Conclusión operativa

La pregunta correcta ya no es "quién ejecuta el análisis".

La pregunta correcta es:

- quién es dueño de cada subresponsabilidad
- qué puede degradarse
- qué puede entrar en fallback
- qué nunca debe salir de la plataforma
