# Decision Validation Pass 2

## Propósito

Validar con `decision-expander` los refuerzos agregados después de la primera expansión:

- buenas prácticas de estructura
- testing por frontera
- seguridad y operación
- workflow de cambios
- observabilidad mínima

Este documento no reabre la decisión desde cero.

Valida si esos refuerzos:

- realmente robustecen el plan
- introducen sobrepromesas
- siguen siendo demasiado abstractos
- requieren nuevas decisiones explícitas para volverse operables

## Qué cambió desde la expansión anterior

### Hecho verificado

Desde `DECISION_EXPANSION.md` se agregaron al plan y a la arquitectura:

- reglas de separación de concerns
- dependency inversion como criterio explícito
- estrategia de pruebas por frontera y riesgo
- reglas de error seguro y datos sensibles
- trazabilidad mínima vía `requestId`
- workflow de cambios y calidad
- criterios más fuertes para compatibilidad hacia atrás

### Inferencia fuerte

La arquitectura dejó de ser solo "funcional" y pasó a incluir dimensión de operación y mantenibilidad.

### Riesgo

Todavía no todas esas prácticas están cerradas como decisiones ejecutables. Varias siguen descritas como intención de calidad más que como contrato operativo del sistema.

## 1. Qué existe realmente

### Hecho verificado

Los documentos actuales ya contienen:

- principios de alta cohesión y bajo acoplamiento
- separación explícita entre capability, provider, contract y projection
- criterios de pruebas unitarias, integración, funcionales y contractuales
- reglas de manejo seguro de errores
- reglas mínimas de observabilidad y trazabilidad
- reglas de workflow y calidad

### Hecho verificado

Los documentos todavía no contienen, como decisión cerrada:

- shape definitivo de `meta`
- taxonomía final de `issues`, `warnings` y `degraded`
- política precisa de logging de XML y campos sensibles
- owner operativo de fallback, compatibilidad y contrato
- presupuesto operativo de performance, concurrencia y límites de payload

## 2. Qué parece que el usuario quiere decir

### Inferencia fuerte

Quieres confirmar que los refuerzos recientes no son solo "buenas prácticas bonitas", sino piezas que realmente endurecen la plataforma.

### Inferencia fuerte

También quieres detectar si alguna práctica que agregué:

- está mal aterrizada
- está sobreespecificada para esta etapa
- o todavía deja huecos importantes sin nombrar

## 3. Qué podría estar mal nombrado o mal asumido

### Inferencia fuerte

`buenas prácticas incorporadas` puede estar mal entendido si se lee como "ya decidimos esto".

En varios casos lo correcto es:

- práctica aceptada como criterio
- pero todavía no convertida en decisión operativa cerrada

### Inferencia fuerte

`observabilidad mínima desde v1` sigue mal definida mientras no se cierre:

- qué identificadores existen
- qué eventos se registran
- qué datos no pueden registrarse
- qué señales activan alertas o revisiones

### Inferencia fuerte

`dependency inversion` puede quedar decorativa si no se define cuál es la interfaz concreta mínima del provider.

### Riesgo

`testing por frontera` puede parecer suficiente, pero sin matriz de casos y ownership sigue siendo una intención correcta todavía no operacionalizada.

## 4. Variables omitidas

### Hecho verificado

A pesar del refuerzo, siguen faltando estas variables:

- SLA o expectativa de latencia para `analyze_cfdi`
- tamaño máximo aceptable del XML
- política de timeouts y cancelación
- estrategia de concurrencia
- qué se considera dato sensible dentro del XML
- duración y destino de logs
- si habrá redacción o hashing de campos sensibles
- qué nivel de trazabilidad se necesita en desarrollo vs producción
- qué entorno o actor consume métricas y logs
- criterio para declarar "degraded usable"
- criterio de aceptación para contract tests
- owner documental del contrato y del roadmap

### Hipótesis útil

También faltan variables de evolución:

- si `requestId` debe venir del cliente o generarse solo en backend
- si el contrato v1 será estable solo para frontend o también para otros clientes futuros
- si la telemetría debe vivir solo en backend o reflejarse parcialmente en frontend

## 5. Capacidades no consideradas

### Inferencia fuerte

Los refuerzos recientes abren capacidades nuevas que aún no están incorporadas al roadmap como tales:

- contract linting o revisión semántica de cambios de contrato
- matriz de compatibilidad por capability
- policy pack de errores y degradación reutilizable entre capabilities
- capability readiness checklist antes de promover nuevas capacidades
- clasificación de datos sensibles por campo contractual

### Hipótesis útil

Una capacidad interna muy valiosa que todavía no se nombra formalmente es:

- `contract_change_review`

No como endpoint productivo, sino como práctica/artefacto de gobernanza para cada cambio de `meta`, `issues`, `findings` o shape de respuesta.

### Hipótesis útil

Otra capacidad interna plausible:

- `fallback_observability_review`

Para separar "hay fallback" de "el fallback está gobernado".

## 6. Límites reales

### Hecho verificado

Límites reales de los nuevos refuerzos:

- siguen siendo documentación, no enforcement automático
- no sustituyen decisiones concretas de contrato
- no resuelven por sí solos la brecha de findings
- no convierten automáticamente el bridge actual en un provider bien abstraído

### Inferencia fuerte

El límite real aquí no es falta de buenas prácticas.

El límite real es que varias buenas prácticas aún no están convertidas en definiciones verificables.

### Hipótesis útil

No está probado todavía que haga falta más volumen de documentación.

Podría ser suficiente con cerrar tres artefactos operativos bien definidos.

## 7. Alternativas no obvias

### Hipótesis útil

Alternativa 1:

En vez de seguir agregando principios generales, cerrar una `capability decision matrix` para `analyze_cfdi`.

Eso obligaría a convertir principios en ownership y criterios verificables.

### Hipótesis útil

Alternativa 2:

Crear una `contract semantics appendix` corta, separada del plan general, solo para:

- `meta`
- `issues`
- `warnings`
- `degraded`
- `fallback`

Eso daría más precisión que seguir expandiendo arquitectura general.

### Hipótesis útil

Alternativa 3:

Crear un `operational minimum` específico para v1:

- observabilidad mínima
- política de datos sensibles
- errores seguros
- límites de payload y timeout

Eso evitaría que seguridad y operación queden dispersas entre varios documentos.

## 8. Riesgos

### Riesgo

Riesgo de sobreestimar el refuerzo reciente:

- creer que ya existe gobernanza suficiente solo porque ahora se nombran buenas prácticas

### Riesgo

Riesgo de subestimar el refuerzo reciente:

- ignorar que ya se corrigió una carencia real: antes el plan no incluía casi nada de seguridad, operabilidad ni testing estructurado

### Riesgo

Riesgo de seguir documentando sin cerrar artefactos:

- el plan puede crecer en principios sin mejorar realmente la capacidad de decidir implementación

### Riesgo

Riesgo de dispersión documental:

- si contrato, operación, fallback y calidad quedan repartidos entre demasiados documentos, la claridad baja aunque el contenido aumente

## 9. Prueba mínima para salir de la duda

### Recomendación

La prueba mínima correcta después de este refuerzo no es agregar más principios.

Es convertir tres zonas ambiguas en artefactos de decisión cerrados:

1. matriz de ownership de `analyze_cfdi`
2. apéndice semántico de contrato v1
3. mínimo operativo v1 para observabilidad, errores seguros y datos sensibles

### Recomendación

Si esos tres artefactos se pueden definir sin contradicciones con el plan actual, entonces los refuerzos recientes sí fueron robustecimiento real y no solo expansión teórica.

## 10. Recomendación

### Recomendación

Los cambios recientes sí fortalecen el plan.

Especialmente porque corrigieron una omisión real:

- antes la arquitectura casi no hablaba de seguridad, operación, pruebas ni workflow

### Recomendación

Pero todavía no recomiendo tratar esos refuerzos como "decisiones cerradas".

Recomiendo tratarlos como:

- criterios aceptados
- pendientes de traducción a artefactos operativos concretos

### Recomendación

El siguiente movimiento de planeación no debería ser más expansión general.

Debería ser cerrar, al menos, uno de estos tres:

- matriz de ownership de `analyze_cfdi`
- semántica contractual exacta de v1
- mínimo operativo v1

## Lentes aplicados

### contexto omitido

### Hecho verificado

El contexto nuevo es que ya no estábamos discutiendo solo arquitectura base, sino endurecimiento con buenas prácticas.

### restricciones reales

### Hecho verificado

La restricción real es que la mayoría de esos refuerzos siguen en nivel de criterio y no de enforcement.

### supuestos no verificados

### Inferencia fuerte

Se estaba asumiendo que agregar buenas prácticas al plan equivale a cerrar el problema. No equivale.

### capacidades nativas ya existentes

### Hecho verificado

La documentación actual ya tiene suficiente estructura para derivar artefactos más concretos sin volver a reabrir todo el mapa.

### capacidades posibles con configuración o composición

### Hipótesis útil

Una combinación de `decision matrix + contract appendix + operational minimum` puede cerrar mucho más valor que seguir expandiendo principios generales.

### límites reales del sistema

### Hecho verificado

La documentación no reemplaza decisiones operativas específicas.

### alternativas no obvias

### Hecho verificado

Se identificaron rutas más cortas y precisas que seguir expandiendo teoría.

### costo de no explorar

### Riesgo

Si no se hacía esta segunda validación, era fácil confundir robustez documental con cierre decisional.

### costo de sobreestimar

### Riesgo

Sobreestimar estos refuerzos llevaría a implementar sobre criterios todavía ambiguos.

### prueba mínima para salir de la duda

### Recomendación

La duda principal ya no se cierra con más lectura, sino con tres artefactos de planeación más precisos.
