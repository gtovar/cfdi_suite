# 06. Engine Decision Matrix

## Propósito

Cerrar la decisión del motor para el producto actual con criterios explícitos y repetibles.

## Qué se decide aquí

Una sola de estas salidas:
- `current-ts` sigue como motor principal
- `python-satcfdi` pasa a ser motor principal

La salida híbrida permanente queda descartada y no se activa transición temporal.

## Evidencia base usada en esta iteración

Benchmark actual sobre el mismo corpus versionado:

- `current-ts`: 10/10 fixtures estrictos OK
- `python-satcfdi`: 10/10 fixtures estrictos OK

Señales relevantes del benchmark:

- ambos motores cubren `profile`, `cfdi` mínimo y datasets básicos de `ingreso` / `pagos`
- ambos fallan correctamente los dos casos fatales de parseo
- `current-ts` sí emite findings matemáticos útiles en los 5 casos diagnósticos
- `python-satcfdi` todavía no emite findings equivalentes y lo declara como `UNSUPPORTED_CAPABILITY`
- `python-satcfdi` ya procesa el fixture `nomina-like`, pero dentro del benchmark actual eso solo prueba parseo estructural mínimo, no valor completo para el producto

## Matriz por criterio

| Criterio | `current-ts` | `python-satcfdi` | Lectura |
|---|---|---|---|
| Cobertura del corpus actual | 10/10 | 10/10 | Empate en benchmark actual |
| Calidad del `cfdi` para el producto | Buena y ya integrada a findings | Buena a nivel estructural mínimo | Ventaja ligera `current-ts` |
| Datasets de ingresos y pagos | Sí | Sí | Empate |
| Findings útiles para inspección | Sí | No todavía | Gana `current-ts` |
| Cobertura potencial de dominio SAT | Limitada al alcance actual local | Muy superior por librería y ecosistema | Gana `python-satcfdi` |
| Complejidad operativa | Baja, runtime único Node | Mayor, requiere Python + venv + bridge | Gana `current-ts` |
| Mantenibilidad del dominio amplio | Débil si crece localmente | Fuerte por superficie y madurez externa | Gana `python-satcfdi` |
| Costo de integración al producto actual | Ya absorbido | Aún incompleto por findings y operación | Gana `current-ts` |

## Lectura recomendada de resultados

### Dominio

`python-satcfdi` sigue ganando como candidato a motor de dominio amplio.

Razones:
- ya demuestra parseo estructural útil sobre el corpus local
- soporta `nomina-like` sin romper contrato
- su superficie SAT sigue siendo mucho más grande que la del motor TS local

### Calidad de salida para el producto

`current-ts` sigue ganando hoy.

Razones:
- el producto actual no solo necesita parsear
- también necesita findings legibles y accionables
- esa parte hoy solo existe de forma útil en `current-ts`

### Operabilidad

`current-ts` gana claramente hoy.

Razones:
- no agrega runtime extra
- no depende de `.venv-satcfdi`
- no necesita puente Node -> Python

### Mantenibilidad

La lectura está partida:

- si el objetivo es seguir como producto de inspección estrecho, `current-ts` sigue siendo más simple
- si el objetivo es crecer hacia dominio SAT más amplio, `python-satcfdi` sigue siendo mejor base

## Decisión de esta iteración

### Recomendación accionable

Cerrar la decisión ahora con el criterio de producto actual.

La salida correcta en esta iteración es:
- **`current-ts` sigue como motor principal del producto**
- `python-satcfdi` no pasa a motor principal en esta iteración
- `python-satcfdi` queda como benchmark o referencia de dominio, no como línea paralela de implementación
- no seguir ampliando superficie equivalente de negocio en ambos motores en paralelo

## Por qué no gana `python-satcfdi` todavía

- aún no aporta findings equivalentes al flujo real de inspección
- todavía introduce complejidad operativa extra
- la ventaja de dominio todavía no se traduce en una mejora decisiva del contrato útil para la UI actual

## Qué significa la ausencia de findings equivalentes

- no bloquea la decisión final del motor
- sí bloquea que `python-satcfdi` pueda ganar como reemplazo inmediato del motor actual
- pasa a ser condición de reapertura, no trabajo obligatorio de esta fase

## Por qué no se descarta `python-satcfdi` todavía

- ya demostró integración real al contrato mínimo
- ya corre el benchmark estricto sin divergencias
- su ventaja potencial de dominio sigue siendo relevante para el roadmap del producto

## Regla de reapertura

Reabrir esta decisión solo si ocurre una de estas dos cosas:

1. el producto cambia de alcance hacia dominio SAT más amplio
2. `python-satcfdi` demuestra valor contractual adicional real para la UI, no solo paridad de parseo estructural

Mientras eso no ocurra, `python-satcfdi` no debe seguir creciendo como motor paralelo dentro del repo.

## Validación

La matriz actual evita juicio narrativo porque:
- separa dominio, producto y operación
- usa benchmark real del repo
- y produce una decisión final concreta para el producto actual

## Criterio de salida

Esta fase queda cerrada con esta salida escrita:

- `current-ts` se queda como motor principal para este producto
