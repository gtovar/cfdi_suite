# Operational Minimum V1

## Propósito

Definir el mínimo operativo que debe quedar decidido e instrumentado para `analyze_cfdi` v1 antes de tratar la capability como plataforma usable.

Este documento no promete observabilidad de producción ni integración con un vendor externo.

Sí fija el mínimo de decisiones y señales que deben existir realmente en el backend local.

## 1. Observabilidad mínima

### Decisiones cerradas

- toda respuesta v1 debe incluir `requestId`
- toda ejecución debe identificar `capability`
- toda ejecución debe identificar `provider`
- toda ejecución debe identificar `providerMode`
- toda degradación relevante debe reflejarse en `meta.degraded`

### Señales mínimas que deben existir

- volumen de requests
- tasa de errores fatales
- tasa de respuestas degradadas
- frecuencia de fallback
- distribución por `providerMode`

### Instrumentación elegida para esta etapa

- logs estructurados backend por request final
- registry de métricas en memoria para pruebas y validación local
- emisión única por respuesta final para evitar duplicación entre provider primario y fallback

### Campos loggeados por request

- `requestId`
- `capability`
- `provider`
- `providerMode`
- `degraded`
- `fallbackReason`
- `profile`
- `timingMs`
- `httpStatus`
- `fatalIssueCount`

### Señales recomendadas

- latencia por request
- latencia por provider
- frecuencia de `profile = unknown`
- frecuencia de rows vacías por perfil

## 2. Errores seguros

### Decisiones cerradas

- la respuesta al usuario no debe incluir stack traces
- la respuesta al usuario no debe exponer detalles internos del subprocess o librería externa
- los errores deben clasificarse en contractuales/técnicos en `issues`
- el backend sí debe conservar detalle interno suficiente para diagnóstico seguro

### Lo que sí puede exponerse

- mensaje claro y útil para el usuario o frontend
- clasificación general del error
- indicador de fatalidad
- estado de degradación si aplica

### Lo que no debe exponerse

- tracebacks completos
- rutas internas del filesystem
- variables de entorno
- contenido sensible del XML

## 3. Datos sensibles

### Decisión base

El XML CFDI debe tratarse como dato sensible operativo.

### Campos que deben considerarse sensibles por defecto

- RFCs
- nombres de emisor y receptor
- UUID completo
- montos cuando se registren fuera del contrato de negocio
- contenido bruto del XML

### Reglas mínimas

- no loggear XML completo por defecto
- no devolver XML completo en respuestas
- evitar copiar datos sensibles a mensajes de error
- si se requiere correlación, preferir `requestId` sobre contenido del XML
- no loggear `cfdi.uuid`, RFCs, nombres fiscales ni montos crudos en la capa de observabilidad mínima

### Decisión abierta controlada

Queda por cerrar si algunos campos:

- se redactan
- se hashean
- o solo se excluyen de logs

Pero v1 no debe asumir logging abierto del XML.

## 4. Límites operativos mínimos a cerrar

Valores cerrados para esta etapa:

- tamaño máximo de `xml`: `1_000_000` caracteres
- timeout máximo por provider: `15s`
- comportamiento ante timeout: error contractual seguro con clasificación fatal si no hubo fallback exitoso
- política de cancelación: no expuesta como capability v1
- expectativa básica de concurrencia: proceso local de desarrollo, sin promesa formal de throughput

## 5. Fallback y operación

### Decisiones cerradas

- el fallback debe ser visible en metadata
- el fallback debe ser medible
- el fallback debe tener owner
- el fallback no debe interpretarse como normalidad silenciosa

### Métricas mínimas del fallback

- cuántas veces ocurre
- por qué ocurre
- qué porcentaje del tráfico representa
- si produce degradación material del resultado

### Catálogo mínimo cerrado

- `provider_runtime_failure`

## 6. Contract tests operativos mínimos

No basta con tests de shape. Deben existir criterios operativos mínimos:

- toda respuesta tiene `requestId`
- toda degradación relevante se refleja en `meta.degraded`
- todo fallback refleja `providerMode` correcto
- todo fallback refleja `fallbackReason` conocido
- toda respuesta fatal evita `cfdi` usable inconsistente
- ningún mensaje público expone detalle interno sensible
- ningún log estructurado de esta etapa incluye XML crudo ni campos fiscales sensibles
- request inválido y runtime fatal actualizan métricas operativas mínimas

## 7. Owners mínimos a definir

Aunque todavía no se nombren personas, el plan debe asumir estos owners:

- owner del contrato v1
- owner de semántica de degradación
- owner del fallback
- owner de política de datos sensibles
- owner de corpus de regresión contractual

## 8. Definition of minimally operable

`analyze_cfdi` v1 es mínimamente operable cuando:

- su respuesta es trazable vía `requestId`
- sus errores públicos son seguros
- sus limitaciones se expresan semánticamente
- el fallback no es opaco
- existe una política mínima para datos sensibles
- existe un límite operativo mínimo explícito para payload y timeout

## 9. Lo que este documento no promete

- observabilidad completa de producción
- SRE formal
- dashboards definitivos
- política corporativa completa de seguridad
- exportación a Prometheus, OpenTelemetry o vendor externo

Solo fija el mínimo que la capability ya no debe omitir ni dejar sin instrumentar.
