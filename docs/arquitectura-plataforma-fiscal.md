# Arquitectura Plataforma Fiscal

## Propósito

Definir una arquitectura sostenible para evolucionar `cfdi_inspector` desde inspector local hacia una plataforma fiscal con:

- frontend estable de producto
- API propia como frontera de dominio
- capabilities explícitas
- providers aislados
- contratos versionados y controlados por la plataforma

Este documento quedó reforzado con prácticas de estructura, testing, seguridad y workflow tomadas de la base de Obsidian en:

- `wiki/domains/dev-practices/code-structure.md`
- `wiki/domains/dev-practices/testing-strategy.md`
- `wiki/domains/dev-practices/security-and-maintenance.md`
- `wiki/domains/dev-practices/version-control-workflow.md`

## Principio central

La plataforma no debe crecer metiendo más lógica fiscal dentro del frontend.

Pero tampoco debe limitarse a envolver una librería externa con HTTP.

La separación correcta es:

- producto
- plataforma
- capabilities
- providers
- proyecciones de compatibilidad

## Principios rectores

### 1. El frontend no es dueño del dominio fiscal

El frontend:

- carga XML
- orquesta experiencia de inspección
- muestra findings, tablas y contexto
- no define reglas fiscales fuertes nuevas

### 2. El contrato pertenece a la plataforma

El contrato:

- no pertenece a `python-satcfdi`
- no pertenece a la UI actual
- debe poder sobrevivir a cambios de provider y de pantallas

### 3. Una capability no es lo mismo que un provider

Una capability expresa un caso de uso del producto.

Un provider solo aporta datos o funciones externas.

### 4. La compatibilidad es una capa, no el dominio

`ingresoRows`, `pagoRows` y otras formas pensadas para la UI actual deben considerarse proyecciones derivadas.

No deben convertirse en el centro de la arquitectura.

### 5. El fallback es transicional y gobernado

Toda degradación o fallback debe ser:

- visible
- medible
- reversible
- retirable

### 6. Alta cohesión, bajo acoplamiento

Cada capa debe tener responsabilidad clara y frontera pequeña.

La arquitectura debe seguir estas reglas:

- alto desacoplamiento entre frontend, capability, provider y proyección
- alta cohesión dentro de cada módulo
- dependencias hacia abstracciones, no hacia implementaciones concretas
- ninguna capa debe depender de métodos o datos que no usa

### 7. La seguridad y la operabilidad también son arquitectura

La arquitectura no queda cerrada solo con endpoints y contratos.

También debe definir:

- validación estricta de entrada
- manejo seguro de errores
- trazabilidad mínima
- observabilidad
- política de datos sensibles

## Capas principales

### 1. Frontend de producto

Responsabilidad:

- carga de XML
- estado de sesión de análisis
- progreso, findings, auditoría y tablas
- navegación y lectura operativa

Tecnología actual:

- React
- Vite

Regla:

El frontend no debe conocer detalles internos de `python-satcfdi` ni de ningún otro provider.

### 2. API de plataforma

Responsabilidad:

- exponer endpoints HTTP/JSON estables
- validar requests de transporte
- resolver capabilities
- ensamblar respuestas para el producto
- aplicar políticas de error, warning y degradación

Rol arquitectónico:

- frontera estable entre producto y dominio
- punto único de entrada para nuevas capabilities

### 3. Capability layer

Responsabilidad:

- representar casos de uso del negocio
- definir ownership de la salida
- orquestar providers, normalización y proyecciones

Capabilities candidatas:

- `analyze_cfdi`
- `validate_cfdi`
- `catalog_checks`
- `sat_status`
- `render_cfdi`

Regla:

Cada capability debe tener owner claro y semántica cerrada. No deben existir dos motores equivalentes resolviendo la misma capability de manera indefinida.

Buena práctica adicional:

- una capability no debe mezclar transporte, reglas de dominio, integración externa y proyección UI en el mismo módulo
- cada subresponsabilidad debe poder probarse de forma independiente

### 4. Provider layer

Responsabilidad:

- adaptar librerías o proyectos externos
- encapsular dependencias
- declarar capacidades soportadas

Ejemplos probables:

- `provider_python_satcfdi`
- futuro `provider_catalogmx`
- futuro `provider_phpcfdi` si alguna capability realmente lo justifica

Regla:

Los providers no exponen modelos crudos al contrato HTTP.

Buena práctica adicional:

- los providers deben depender de una interfaz mínima
- la plataforma no debe depender del bridge específico de un provider
- cualquier proveedor nuevo debe poder agregarse por extensión, no por modificación transversal del sistema

### 5. Contract layer

Responsabilidad:

- definir request/response estables
- versionar integración frontend/backend
- fijar semántica para findings, issues, warnings, perfiles y metadatos

Regla:

Debe existir al menos una distinción conceptual entre:

- contrato canónico de plataforma
- contrato HTTP expuesto
- proyección de compatibilidad para la UI

### 6. Projection layer

Responsabilidad:

- traducir el contrato canónico a la forma requerida por la UI actual
- concentrar compatibilidad transicional
- evitar que esa compatibilidad se disperse en componentes

Regla:

La proyección no debe recalcular dominio fuerte. Solo debe transformar presentación y compatibilidad.

## Flujo principal

1. El usuario carga un XML en el frontend.
2. El frontend llama a la API.
3. La API resuelve la capability.
4. La capability consulta uno o más providers.
5. Los providers retornan datos o señales normalizables.
6. La plataforma construye el resultado canónico.
7. La plataforma genera la proyección compatible para la UI.
8. El frontend renderiza sin conocer el provider.

## Diagrama mental

`frontend -> API -> capability -> provider -> normalización -> proyección -> UI`

## Capability principal inicial

### `analyze_cfdi`

Debe entenderse como capability compuesta, no como simple wrapper de librería.

Subresponsabilidades:

- `ingest_xml`
- `detect_profile`
- `extract_structured_cfdi`
- `derive_tabular_views`
- `compute_findings`
- `assemble_response`

Ownership recomendado:

- platform: `ingest_xml`, `derive_tabular_views`, `compute_findings`, `assemble_response`
- provider: `extract_structured_cfdi`
- compartido pero normalizado por plataforma: `detect_profile`

## Contratos recomendados

### 1. Contrato canónico interno

Debe contener:

- identidad y perfil del CFDI
- estructura fiscal normalizada
- findings de plataforma
- issues y degradaciones
- metadatos de trazabilidad

No debe optimizarse para una sola pantalla.

### 2. Contrato HTTP v1

Debe ser estable y simple para la UI actual.

Shape base esperado:

```json
{
  "profile": "ingreso",
  "cfdi": {},
  "ingresoRows": [],
  "pagoRows": [],
  "issues": [],
  "meta": {
    "contractVersion": "v1",
    "capability": "analyze_cfdi",
    "provider": "python-satcfdi",
    "providerMode": "primary",
    "degraded": false
  }
}
```

Buena práctica adicional:

- el contrato debe ser explícitamente versionado
- los cambios incompatibles deben obligar nueva versión
- la compatibilidad hacia atrás no debe quedar implícita
- el contrato debe tener tests de frontera dedicados

### 3. Proyección UI

Debe incluir:

- `cfdi`
- `ingresoRows`
- `pagoRows`
- `verdict`
- `supportText`

Pero esos campos no deben definir el dominio completo.

## Findings, issues y degradación

### Findings

Deben ser propiedad de la plataforma.

Un provider puede aportar datos fuente, pero no debe dictar por sí solo el lenguaje final de findings del producto.

### Issues

Deben representar problemas técnicos o contractuales:

- request inválido
- parseo inválido
- runtime/provider failure
- capability no soportada
- degradación no fatal

### Degradación

Debe modelarse explícitamente en `meta`.

No basta con confiar en `fatal: false`.

Buena práctica adicional:

- el usuario no debe recibir detalles internos del provider o stack trace
- los logs internos sí deben retener suficiente detalle para diagnóstico
- error de usuario, error de contrato y error de infraestructura deben quedar diferenciados

## Estrategia de providers

### Provider inicial

- `python-satcfdi`

### Requisitos mínimos para cualquier provider

- declarar perfiles soportados
- declarar capabilities soportadas
- declarar limitaciones conocidas
- no filtrar modelos crudos al contrato HTTP
- poder ser reemplazable sin reescribir frontend
- exponer metadatos mínimos de versión y modo de ejecución
- permitir pruebas unitarias e integración sin acoplar toda la capability a un proceso real

### Regla importante

El bridge actual por subprocess puede ser correcto como transición.

No debe asumirse como definición permanente del patrón de provider.

## Cómo entra cada pieza

### `python-satcfdi`

- librería externa
- provider principal inicial
- fuente fuerte de estructura fiscal
- no dueño del contrato del producto

### `catalogmx`

- candidato para validaciones y catálogos
- no debe entrar al core sin capability concreta que lo justifique

### `phpCfdi / CfdiUtils`

- referencia útil de ecosistema
- solo debe entrar si resuelve una capability específica mejor que las alternativas
- siempre aislado como provider

## Regla de integración de open source

Sí conviene:

- usar librerías como dependencias
- aislarlas en providers
- mapear su salida a contratos de plataforma

No conviene:

- mezclar modelos externos con contrato del producto
- absorber repos completos sin fronteras
- sostener doble lógica equivalente de dominio de manera permanente

## Riesgos arquitectónicos a evitar

- API Frankenstein con múltiples motores haciendo lo mismo
- contrato rehén de la UI actual
- contrato rehén del provider actual
- findings sin owner
- fallback TS opaco o permanente
- bridge transicional convertido en arquitectura base

## Reglas de estructura

Estas reglas provienen de buenas prácticas de estructura y mantenimiento y deben aplicarse a la evolución del backend:

- separación de concerns: transporte, capability, provider, contrato y proyección no deben mezclarse
- funciones pequeñas y módulos enfocados: cada módulo debe resolver una sola responsabilidad dominante
- dependency inversion: la capability depende de interfaces de provider, no de implementaciones concretas
- open/closed: agregar providers o capabilities no debe requerir reescribir el flujo central
- DRY con criterio: centralizar semántica contractual y taxonomía de errores; no duplicarla entre frontend, backend y wrapper
- KISS y YAGNI: no abrir multi-provider productivo ni capacidades no comprometidas antes de cerrar `analyze_cfdi`

## Reglas de calidad y operación

La arquitectura también debe asumir estas prácticas mínimas:

- validación de input: XML y opciones del request deben validarse antes de tocar provider
- documentación viva: contrato, límites y decisiones deben actualizarse junto con el diseño
- observabilidad mínima: `request_id`, origen del provider, modo de ejecución y estado de degradación
- monitoreo futuro: el plan debe dejar espacio para métricas y alertas sobre errores, degradación y fallback
- revisión de seguridad: no exponer detalles internos del runtime en respuestas al usuario
- gestión de dependencias: el backend debe contemplar monitoreo de vulnerabilidades y actualización de dependencias como parte del lifecycle

## Estrategia de pruebas arquitectónicas

La documentación ya no debe hablar solo de "tests" en abstracto. Debe distinguir:

- pruebas unitarias para normalización, taxonomía de issues, proyecciones y reglas de findings
- pruebas de integración para frontera API -> capability -> provider
- pruebas funcionales para flujos críticos de `ingreso`, `pagos`, XML inválido y degradación usable
- pruebas de regresión contractual para garantizar que el frontend no rompe ante cambios internos

Regla:

Las fronteras importantes del sistema deben probarse por tipo de riesgo, no solo por cobertura total.

## Criterio de éxito

La arquitectura es correcta si:

- el frontend no necesita reescribirse cuando cambie un provider
- la plataforma puede sumar capabilities sin contaminar la UI
- el contrato sigue estable aunque cambie la implementación interna
- el dominio fiscal fuerte deja de vivir en el browser
- el fallback TS puede retirarse sin colapsar la experiencia principal

## Resumen corto

- frontend = experiencia
- API = frontera de plataforma
- capability = caso de uso con owner
- provider = adaptador a dependencia externa
- contract = lenguaje estable de integración
- projection = compatibilidad explícita con la UI

La evolución sana de `cfdi_inspector` hacia plataforma fiscal depende de mantener esas fronteras claras.
