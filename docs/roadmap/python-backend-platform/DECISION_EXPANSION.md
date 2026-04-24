# Decision Expansion

## Propósito

Expandir la decisión `cfdi_inspector -> frontend de producto + backend Python` antes de seguir consolidando arquitectura, contrato y roadmap.

Este documento aplica el skill `decision-expander` para evitar que la dirección actual se cierre con variables omitidas, supuestos débiles o límites mal entendidos.

## 1. Qué existe realmente

### Hecho verificado

- existe una UI React/Vite operativa para inspección CFDI
- existe backend Python en `backend/app/`
- existe `GET /api/health`
- existe `POST /api/cfdi/analyze`
- existe integración del frontend hacia `/api/cfdi/analyze`
- existe fallback TypeScript cuando la API no responde
- `python-satcfdi` ya participa en la dirección activa del repo
- el contrato real emergente hoy sigue muy orientado a compatibilidad con la UI actual
- `python-satcfdi` hoy entrega estructura CFDI y filas, pero no findings equivalentes al motor TS
- el provider actual usa un bridge por subprocess hacia `src/cfdi/engine/python-satcfdi-wrapper.py`
- el roadmap y la arquitectura ya reconocen que el dominio no debe seguir creciendo dentro del browser

### Hecho verificado

El sistema todavía no tiene formalizados varios elementos críticos:

- contrato canónico interno
- semántica cerrada de degradación
- owner definitivo de findings
- interfaz rica de providers
- roadmap comprometido de capabilities más allá de `analyze_cfdi`

## 2. Qué parece que el usuario quiere decir

### Inferencia fuerte

No solo quieres "más detalle".

Quieres tensionar la decisión actual para descubrir:

- qué partes de la arquitectura todavía son frágiles
- qué variables de plataforma faltan
- qué límites son reales y cuáles solo son supuestos
- qué nuevas piezas conviene agregar al plan antes de seguir consolidando implementación

### Inferencia fuerte

También quieres evitar dos errores:

- institucionalizar una arquitectura incompleta porque ya existe código
- descartar opciones útiles solo porque todavía no están nombradas o medidas

## 3. Qué podría estar mal nombrado o mal asumido

### Inferencia fuerte

`backend Python` está bien como dirección, pero está mal si se entiende como una sola decisión cerrada.

En realidad son varias decisiones acopladas:

- arquitectura de capas
- frontera contractual
- ownership de findings
- estrategia de fallback
- política de providers
- roadmap de capabilities
- modelo operativo del producto

### Inferencia fuerte

`python-satcfdi como motor principal` puede estar mal nombrado si se interpreta como:

- que el provider define la capability
- que la librería define el contrato
- que toda expansión fiscal deberá vivir dentro de esa librería

La forma correcta es:

- `python-satcfdi` es provider principal inicial
- la plataforma sigue siendo dueña de capability, contrato y semántica de producto

### Inferencia fuerte

`fallback temporal` es demasiado ambiguo.

Sin política explícita, "temporal" puede durar indefinidamente.

### Riesgo

`una sola capability inicial` puede esconder una simplificación excesiva si no se define qué subcapacidades componen realmente `analyze_cfdi`.

## 4. Variables omitidas

### Hecho verificado

Las variables siguientes todavía no están suficientemente reflejadas en el plan:

- tamaño máximo de XML soportado
- tiempo máximo aceptable de análisis
- memoria y concurrencia esperadas
- comportamiento con lotes o uso repetitivo
- trazabilidad mínima por request
- estrategia de versionado de contrato
- política de compatibilidad hacia atrás
- modo de despliegue local y futuro
- observabilidad mínima
- clasificación de errores de negocio vs errores técnicos
- reglas de privacidad del XML cargado
- postura frente a retención o no retención de datos
- política de logging de XML o campos sensibles
- soporte objetivo por perfiles CFDI en cada fase
- estrategia de fixtures y corpus de regresión contractual
- criterio de "resultado degradado pero usable"
- criterio de cuándo una capability merece provider adicional
- criterio para promoción de capability candidata a capability comprometida
- expectativas de operación en desarrollo, CI y producción

### Hipótesis útil

También faltan variables de producto:

- si el producto será estrictamente interactivo o también batch
- si la salida está orientada a inspección humana, integración externa o ambas
- si el frontend será el único consumidor del backend
- si habrá futuro consumo por CLI, API pública o automaciones

### Hipótesis útil

Faltan variables organizacionales:

- quién será owner técnico del contrato
- quién decidirá cuándo retirar el fallback
- quién aprobará expansión de capabilities

## 5. Capacidades no consideradas

### Inferencia fuerte

La plataforma ya podría soportar más que solo "API para la UI" si se diseña bien desde ahora.

Capacidades potenciales no suficientemente consideradas:

- backend como consumidor único de providers múltiples por capability
- modo comparación entre provider primario y motor TS sin exponerlo al usuario
- contract tests entre contrato canónico y proyección UI
- capability flags por entorno
- degradación controlada por capability, no solo por request global
- separación entre `structured extraction` y `product findings`
- provider scoring o matriz de cobertura por capability
- versionado por capability en lugar de versión global única
- respuestas parciales útiles cuando falla una subfase
- trazabilidad con `request_id` y `analysis_id`
- telemetría de fallback y degradación

### Hipótesis útil

Capacidades futuras que el plan todavía no explota conceptualmente:

- `analyze_cfdi` síncrono para UX
- `validate_cfdi` con salidas más normativas
- `render_cfdi` como capability separada y no mezclada con análisis
- `extract_rows` como proyección derivada para exportación
- `compare_engines` como capability interna de regresión

### Hipótesis útil

El sistema podría usar composición de providers sin "multi-provider real" productivo:

- provider principal para estructura
- provider secundario o reglas propias de plataforma para findings
- provider auxiliar solo para validaciones puntuales

## 6. Límites reales

### Hecho verificado

Límites reales observables hoy:

- `python-satcfdi` no entrega findings equivalentes listos para el lenguaje actual del producto
- el provider actual está acoplado a un wrapper subprocess
- el contrato real actual todavía favorece shape compatibility con la UI
- el fallback TS sigue siendo parte del flujo de uso

### Inferencia fuerte

Límites reales probables, aunque no totalmente medidos:

- la UI actual no debería cargar indefinidamente con más semántica de transición
- el contrato no puede seguir ambiguo si habrá nuevas capabilities
- mantener dos dueños para findings vuelve frágil el producto

### Hipótesis útil

No está probado todavía que estos sean límites estructurales:

- que `python-satcfdi` no pueda servir también como fuente parcial para findings
- que el subprocess sea inviable como bridge transicional suficiente
- que `validate_cfdi` deba ser necesariamente la siguiente capability

### Riesgo

Sería un error tratar como límite real algo que todavía no está medido, por ejemplo:

- asumir que el backend no puede manejar más perfiles
- asumir que el frontend no puede consumir un contrato más rico
- asumir que el fallback debe vivir en browser durante toda la transición

## 7. Alternativas no obvias

### Hipótesis útil

Alternativa 1:

No pensar solo en `API v1 compatible con UI actual`, sino en:

- contrato canónico interno
- contrato HTTP estable
- proyección UI v1

Esto reduce el costo de futuras capabilities sin romper la iteración actual.

### Hipótesis útil

Alternativa 2:

No obligar a que los findings salgan enteros de un solo lugar.

Se puede diseñar:

- provider para estructura
- plataforma para findings
- fallback TS solo como comparación/regresión, no como productor visible final

### Hipótesis útil

Alternativa 3:

Mover el fallback del browser al backend en una fase futura.

Eso permitiría:

- un punto único de política de degradación
- telemetría uniforme
- menor complejidad visible en frontend

No es recomendación inmediata, pero sí una alternativa que no debe descartarse por costumbre actual.

### Hipótesis útil

Alternativa 4:

No promover automáticamente `validate_cfdi` como siguiente capability.

Podría ser más rentable primero cerrar:

- findings de plataforma
- metadatos y degradación
- observabilidad contractual

Antes de abrir más superficie funcional.

### Hipótesis útil

Alternativa 5:

Agregar una capability interna no productiva:

- `compare_analyze_cfdi_outputs`

Esto serviría para medir brechas entre backend Python y motor TS sin contaminar el producto.

## 8. Riesgos

### Riesgo

Riesgo de no explorar suficiente:

- cristalizar un contrato demasiado pegado a la UI actual
- asumir que el provider actual ya equivale al diseño final
- abrir nuevas capabilities sobre una base semántica ambigua

### Riesgo

Riesgo de sobreestimar el sistema:

- prometer reemplazo rápido del motor TS sin cerrar findings
- asumir que la semántica actual de errores ya alcanza
- asumir que el provider actual puede escalar como patrón general

### Riesgo

Riesgo de subestimar el sistema:

- pensar que la única ruta es mantener fallback visible en frontend
- asumir que `python-satcfdi` solo sirve como parser estructural
- limitar el roadmap a endpoints mínimos sin diseñar capability ownership

### Riesgo

Riesgo operativo omitido:

- falta de política de observabilidad
- falta de política de datos sensibles
- falta de lineamientos de despliegue y runtime

### Riesgo

Riesgo contractual:

- mezclar en el mismo nivel `issues`, `warnings`, `degraded`, `findings` y `verdict` sin semántica clara

## 9. Prueba mínima para salir de la duda

### Recomendación

La siguiente prueba mínima ya no es de implementación pura; es de diseño verificable.

Debe cerrarse una matriz mínima de decisión para `analyze_cfdi` con estas columnas:

- subresponsabilidad
- owner de plataforma
- owner de provider
- contrato canónico afectado
- proyección UI afectada
- fallback permitido o no
- degradación permitida o no
- evidencia requerida para retirar TS

### Recomendación

La segunda prueba mínima es contractual:

- definir un response `v1` con semántica explícita para `meta`, `issues`, `findings`, `degraded` y `providerMode`
- y evaluar si cubre sin ambigüedad los cuatro escenarios reales:
- éxito normal
- parse failure
- resultado degradado usable
- fallback

### Recomendación

La tercera prueba mínima es de roadmap:

- decidir si el siguiente frente es `findings ownership`
- o `validate_cfdi`

No deben correr como prioridades equivalentes.

## 10. Recomendación

### Recomendación

La dirección `frontend + backend Python` sigue siendo correcta.

Pero todavía está subdefinida en los puntos que más costo de reversión tienen.

La recomendación no es abrir más implementación.

La recomendación es endurecer primero estas cinco decisiones:

1. contrato HTTP v1 con semántica explícita
2. contrato canónico interno de `analyze_cfdi`
3. ownership definitivo de findings
4. política de fallback y degradación
5. criterio de promoción de nuevas capabilities

### Recomendación

No recomiendo abrir `validate_cfdi` todavía como siguiente paso comprometido.

Antes conviene cerrar la semántica de la capability principal.

### Recomendación

Tampoco recomiendo tratar el subprocess bridge actual como arquitectura base.

Debe seguir declarado como bridge transicional hasta que exista decisión explícita en sentido contrario.

## Lentes aplicados

### contexto omitido

### Hecho verificado

La discusión original estaba demasiado centrada en backend y contrato mínimo, y no incorporaba suficiente contexto operativo, contractual y de producto.

### restricciones reales

### Hecho verificado

La brecha de findings y la presencia del fallback son restricciones reales hoy.

### Hipótesis útil

No está probado todavía que esas restricciones obliguen a mantener la misma forma de transición.

### supuestos no verificados

### Inferencia fuerte

Se estaba asumiendo demasiado rápido que:

- `validate_cfdi` debía ser la siguiente capability
- el fallback browser era la transición natural
- el contrato shape-compatible era suficiente como base

### capacidades nativas ya existentes

### Hecho verificado

Ya existe base suficiente en repo para diseñar sobre estado real y no sobre hipótesis pre-implementación.

### capacidades posibles con configuración o composición

### Hipótesis útil

La composición `provider estructural + findings de plataforma + fallback interno de comparación` abre más espacio que el binario actual `API o fallback`.

### límites reales del sistema

### Hecho verificado

El límite real hoy no es "no hay backend".

El límite real es "todavía no existe una semántica suficientemente cerrada para consolidarlo".

### alternativas no obvias

### Hecho verificado

Se documentaron alternativas intermedias entre:

- adoptar por completo el provider como motor dueño
- o mantener la transición actual casi igual

### costo de no explorar

### Riesgo

No explorar más consolidaría deuda contractual y de ownership.

### costo de sobreestimar

### Riesgo

Sobreestimar la madurez de la base actual podría acelerar una arquitectura ambigua.

### prueba mínima para salir de la duda

### Recomendación

La prueba mínima correcta ya no es "hacer más código", sino cerrar matriz de ownership, response semantics y prioridad real del roadmap.
