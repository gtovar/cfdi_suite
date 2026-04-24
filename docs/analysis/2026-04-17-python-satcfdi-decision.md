# Decision Review: `cfdi_inspector` vs `python-satcfdi`

Date: 2026-04-17

## 1. Qué existe realmente

### `cfdi_inspector`
- Frontend React/Vite orientado a inspección manual de XML CFDI.
- Motor local TypeScript para:
  - detectar perfil (`ingreso` o `pagos`),
  - parsear XML,
  - normalizar conceptos e impuestos,
  - calcular discrepancias matemáticas,
  - extraer filas para tablas de ingresos y pagos.
- UX ya pensada para lectura operativa: progreso, findings, conceptos impactados, tablas, detalle contextual.
- El alcance real del dominio es estrecho:
  - soporte visible para `ingreso` y `pagos`,
  - sin evidencia local de nómina, retenciones, PACs, render PDF/HTML, validación XSD SAT o integraciones SAT.

### `python-satcfdi`
- Librería/plataforma Python amplia para CFDI y dominios adyacentes SAT.
- Cobertura declarada y respaldada por estructura de código/tests para:
  - CFDI 3.2, 3.3, 4.0,
  - `ingreso`, `nomina`, `pagos`, `traslados`, complementos,
  - retenciones 1.0/2.0,
  - render HTML/PDF/JSON,
  - CLI,
  - PACs,
  - descarga/validación SAT,
  - DIOT, contabilidad, CSF y otras utilidades.
- Su centro de gravedad es motor de dominio + utilidades operativas, no producto de inspección UX-first.

## 2. Qué intentaba hacer cada uno

### `cfdi_inspector`
- Resolver inspección rápida y comprensible de CFDIs desde una interfaz moderna.
- Convertir XML en diagnóstico legible, no en plataforma fiscal general.

### `python-satcfdi`
- Resolver procesamiento amplio de CFDI/SAT como toolkit reutilizable.
- Cubrir generación, carga, render, validación y flujos operativos más allá de inspección.

## 3. Hechos verificados

- `cfdi_inspector` analiza correctamente fixtures reales del repo externo.
- Sobre el fixture `h&e951128469_ingreso_iva16_stamped.xml`, el motor local detectó:
  - perfil `ingreso`,
  - UUID correcto,
  - versión `4.0`,
  - 1 concepto,
  - 0 findings,
  - veredicto `clean`.
- Sobre el fixture `pago_h&e951128469_ingreso_iva16.xml`, el motor local detectó:
  - perfil `pagos`,
  - UUID correcto,
  - versión `4.0`,
  - 1 concepto,
  - 0 findings,
  - 1 fila de pagos.
- `cfdi_inspector` también genera `ingresoRows` incluso para perfil `pagos`, porque el bundle actual siempre ejecuta `extractIngresoRowsData(xml)` y solo hace opcional `pagoRows`.
- `python-satcfdi` no se pudo ejecutar directamente en esta sesión sin instalar dependencias Python (`lxml` faltante), por lo que la evidencia dinámica del repo externo quedó limitada.
- Aun así, su amplitud funcional sí está sustentada por:
  - `readme.rst`,
  - `setup.py`,
  - estructura de paquetes,
  - batería de tests y fixtures.

## 4. Inferencias fuertes

- `cfdi_inspector` hoy es mejor producto de inspección que plataforma de dominio.
- `python-satcfdi` hoy es mejor plataforma de dominio que producto de inspección.
- Compararlos como si fueran dos productos equivalentes sería un error de categoría.
- La ventaja real de `cfdi_inspector` no está en amplitud funcional sino en:
  - UX,
  - claridad del flujo,
  - framing de hallazgos,
  - lectura operativa.
- La ventaja real de `python-satcfdi` no está en UX sino en:
  - cobertura del dominio,
  - madurez del ecosistema,
  - variedad de casos soportados,
  - potencial como backend o motor canónico.

## 5. Hipótesis útiles

- Que `python-satcfdi` pueda reemplazar por completo el núcleo TypeScript local sin introducir un costo operativo excesivo.
- Que la UX actual de `cfdi_inspector` sea suficientemente portable encima de un backend Python.
- Que la mayor parte de las funciones amplias del repo externo realmente sean necesarias para este producto y no solo superficie adicional.
- Que el motor local actual pueda sostenerse a largo plazo si se intentara crecer hacia nómina, retenciones, PACs y validaciones formales.

## 6. Qué está mal nombrado o mezclado

- "Integrar el otro proyecto" mezcla cuatro posibles acciones:
  - usarlo como motor,
  - migrar el producto a él,
  - copiar capacidades seleccionadas,
  - reemplazar por completo el proyecto actual.
- "Mejor tecnología" no es el criterio correcto.
  - El criterio correcto es: mejor base para evolucionar a producto real sin duplicar dominio.
- "Híbrido" es riesgoso porque puede encubrir una no-decisión.
  - Solo sirve como transición táctica con retiro definido.

## 7. Comparación estructural

### Dominio
- Gana `python-satcfdi`.
- Su cobertura y superficie de dominio son claramente superiores.

### Producto
- Gana `cfdi_inspector`.
- La experiencia actual está pensada para inspección y explicación, no solo para transformar XML.

### Mantenibilidad del dominio
- Hoy gana `python-satcfdi`.
- Su breadth, tests y estructura indican un motor más maduro para reglas fiscales amplias.

### Mantenibilidad del producto
- `cfdi_inspector` parece más simple de operar como interfaz.
- `python-satcfdi` introduce más dependencias y costo operativo.

### Complejidad
- `cfdi_inspector` tiene menos complejidad total.
- `python-satcfdi` tiene más complejidad, pero parte de esa complejidad responde a cobertura real del dominio.

### Reversibilidad
- Mantener `cfdi_inspector` como base y absorber más dominio desde cero tendría costo de reversión alto si luego se descubre que el motor local era insuficiente.
- Adoptar `python-satcfdi` como motor deja una reversión más controlada si la UX se mantiene desacoplada.

### Potencial de evolucionar a producción
- Como motor de dominio, gana `python-satcfdi`.
- Como experiencia final de usuario, `cfdi_inspector` tiene mejor punto de partida.

## 8. Riesgos reales

### Alto
- Mantener dos fuentes de verdad del dominio CFDI a largo plazo.
- Seguir creciendo el motor TypeScript local hacia cobertura SAT amplia sin una razón fuerte.
- Migrar al repo Python completo sin separar qué parte del valor es motor y qué parte es ruido para este producto.

### Medio
- Sobreestimar la portabilidad de la UX actual.
- Sobreestimar la facilidad operativa de meter Python como backend estable.
- Subestimar la diferencia entre "parser que funciona" y "motor canónico de dominio".

### Bajo
- Usar `python-satcfdi` solo como benchmark temporal durante la decisión.
- Conservar la UI actual aunque cambie el motor por debajo.

## 9. Veredicto

### Recomendación
- Seguir, pero corrigiendo la dirección.

### Qué significa eso aquí
- No conviene descartar `cfdi_inspector` como producto.
- No conviene mantener `cfdi_inspector` como dueño principal del dominio CFDI si el objetivo es potenciarlo con cobertura amplia.
- La ruta más sólida es:
  - preservar `cfdi_inspector` como shell de producto y experiencia,
  - mover la ambición de dominio hacia `python-satcfdi` como motor candidato,
  - validar esa sustitución antes de integrar código o reescribir reglas.

### Por qué pierden las otras opciones

#### Mantener `cfdi_inspector` como base completa
- Pierde porque obliga a seguir ampliando un motor local hoy estrecho mientras ya existe un motor mucho más amplio y maduro.

#### Migrar completamente a `python-satcfdi`
- Pierde porque confunde motor con producto.
- Hoy no hay evidencia de que el repo externo traiga una experiencia de inspección superior.

#### Hacer un híbrido permanente
- Pierde porque institucionaliza doble lógica de dominio y falta de dueño único.

## 10. Siguiente paso concreto

### Big picture
- Convertir esta comparación en una arquitectura objetivo: UI/producto por un lado, motor canónico de dominio por otro.

### Fases recomendadas
1. Definir el contrato de salida que `cfdi_inspector` necesita del motor.
2. Construir un adaptador comparativo entre salida actual TS y salida esperada desde Python.
3. Ejecutar un benchmark funcional con corpus mayor.
4. Decidir si el motor TS se reemplaza parcial o totalmente.
5. Retirar progresivamente la lógica duplicada.

### Qué preservar
- UX de inspección.
- framing de findings,
- navegación de conceptos impactados,
- flujo de carga y lectura operativa.

### Qué corregir
- Separar producto de dominio.
- Evitar que el bundle actual siga mezclando extracción de ingresos incluso en `pagos`.
- Frenar el crecimiento del motor TS como si fuera el kernel definitivo del dominio.

### Qué detener
- Nuevas expansiones grandes del dominio CFDI dentro de TypeScript hasta decidir el dueño del motor.

### Qué validar antes de seguir
- Si `python-satcfdi` puede exponer, con costo razonable, una salida alineada a la UX actual.
- Si la dependencia operativa de Python cabe en el futuro despliegue del producto.

## 11. Qué no debes confundir

- Que `cfdi_inspector` procese bien algunos XMLs no prueba que deba seguir siendo el kernel del dominio.
- Que `python-satcfdi` tenga mucha cobertura no prueba que deba reemplazar la UX/producto.
- Un frontend convincente puede validar experiencia de uso sin validar la base técnica del dominio.
- Un motor amplio puede validar dominio sin validar producto.

## 12. Conclusión corta

- El producto actual no debe tirarse.
- El motor local actual no debería asumirse como base definitiva del dominio.
- La decisión correcta hoy es preservar `cfdi_inspector` como capa de producto y evaluar seriamente `python-satcfdi` como futuro motor canónico, evitando una convivencia permanente.
