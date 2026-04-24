# 04. Benchmark and Corpus

## Propósito

Convertir la comparación entre motores en un mecanismo repetible, no en una discusión narrativa.

## Objetivo final

Poder correr `current-ts` y `python-satcfdi` sobre el mismo corpus y obtener:
- cobertura real
- gaps reales
- divergencias de salida
- y criterio objetivo para decidir ownership del dominio

## Estructura recomendada

### Ubicación
- `src/cfdi/benchmark/fixtures/`
- `src/cfdi/benchmark/expectations.ts`
- `src/cfdi/benchmark/runBenchmark.ts`

### Modelo por fixture
Cada fixture debe definir:
- `id`
- descripción corta
- origen del XML
- tipo esperado
- si debería parsear
- perfil esperado
- datasets esperados
- findings mínimos o categoría esperada
- motores esperados o no esperados

## Corpus mínimo obligatorio

### Casos de base
- `ingreso` válido y limpio
- `pagos` válido y limpio
- XML malformado
- XML sin nodo `Comprobante`

### Casos de diagnóstico
- discrepancia de subtotal
- discrepancia de total
- discrepancia de traslado por línea
- caso `Exento`
- caso `Cuota`

### Casos de cobertura ampliada
- al menos un caso `nomina` o `retenciones`

## Salida esperada del benchmark

Por caso y por motor:
- success/failure
- profile detectado
- `cfdi` presente o no
- cantidad de `ingresoRows`
- cantidad de `pagoRows`
- findings generados
- issues
- divergencias contra expectativas

Salida agregada:
- cobertura total
- cobertura por tipo
- errores fatales
- gaps no fatales
- métricas comparativas por motor

## Implementación o ejecución esperada

1. Crear fixtures y expectativas versionadas.
2. Construir runner neutral al motor.
3. Ejecutar primero `current-ts`.
4. Ejecutar después `python-satcfdi`.
5. Generar resumen legible y JSON de soporte.

## Implementación actual en este repo

- `src/cfdi/benchmark/fixtures/`
- `src/cfdi/benchmark/expectations.ts`
- `src/cfdi/benchmark/runBenchmark.ts`
- `src/cfdi/benchmark/runBenchmark.test.ts`

Comando repetible actual:

```bash
npm run benchmark:current-ts
```

Salida JSON:

```bash
npm run benchmark:current-ts:json
```

## Regla clave

El benchmark no debe medir UX.  
Debe medir solo la capacidad del motor para alimentar correctamente el contrato del producto.

## Validación

El benchmark se considera útil si:
- cualquier persona puede repetirlo
- no depende de editar fixtures manualmente por corrida
- los failures se explican como gap, bug o no soporte
- y la comparación cambia realmente la decisión si el resultado cambia

## Criterio de salida

Esta fase termina cuando el benchmark del `current-ts` es repetible y deja preparado el camino para correr exactamente lo mismo contra `python-satcfdi`.
