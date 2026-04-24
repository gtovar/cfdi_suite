# CFDI Engine Migration

## Objetivo

Convertir `cfdi_inspector` en un producto desacoplado del motor CFDI y evaluar `python-satcfdi` como candidato a motor canónico del dominio, sin perder la UX actual y sin institucionalizar una arquitectura híbrida permanente.

## Decisión base ya tomada

- `cfdi_inspector` se conserva como producto.
- El motor CFDI deja de tratarse como parte inseparable del frontend.
- `current-ts` sigue siendo el motor operativo inicial.
- `python-satcfdi` entra como candidato a motor canónico, no como reemplazo automático del producto.
- La convivencia permanente de dos motores con reglas equivalentes queda descartada.

## Estado actual

- Existe un documento de decisión base: [2026-04-17-python-satcfdi-decision.md](../../analysis/2026-04-17-python-satcfdi-decision.md).
- Ya existe una primera frontera técnica del motor en:
  - `src/cfdi/engine/analysisContract.ts`
  - `src/cfdi/engine/currentTsEngine.ts`
- La API pública ya expone una variante basada en contrato.
- La decisión del motor para el producto actual ya quedó cerrada en favor de `current-ts`.
- La migración técnica del engine ya quedó resuelta en favor de `current-ts`.
- Lo que sigue ya no es otra fase técnica del motor, sino seguimiento operativo y posible reapertura solo por trigger explícito.

## Cómo usar este paquete

Lee los documentos en este orden. El orden también representa la secuencia recomendada de ejecución.

1. [01-decision-context.md](./01-decision-context.md)
   Motivo de la dirección elegida y reglas que no deben romperse.
2. [02-analysis-contract.md](./02-analysis-contract.md)
   Frontera oficial entre producto y motor.
3. [03-current-ts-engine.md](./03-current-ts-engine.md)
   Papel y límites del motor TypeScript actual.
4. [04-benchmark-and-corpus.md](./04-benchmark-and-corpus.md)
   Cómo comparar motores con el mismo corpus.
5. [05-python-satcfdi-adapter.md](./05-python-satcfdi-adapter.md)
   Cómo integrar `python-satcfdi` sin contaminar el producto.
6. [06-engine-decision-matrix.md](./06-engine-decision-matrix.md)
   Cómo se forzará la decisión final del motor.
7. [07-migration-and-retirement.md](./07-migration-and-retirement.md)
   Cómo sustituir o retirar motores sin duplicación permanente.
8. [08-session-management.md](./08-session-management.md)
   Cómo verificar si conviene iniciar nueva sesión y cómo rehidratar el contexto.
9. [STATUS.md](./STATUS.md)
   Estado operativo corto, hitos y próxima acción.

## Regla central

El producto visible es `cfdi_inspector`.  
El motor CFDI es intercambiable.  
No se agregará nueva lógica de dominio relevante al motor perdedor una vez que el ownership del dominio quede cerrado.

Aplicación actual de la regla:
- `current-ts` es el dueño operativo del dominio para este producto
- `python-satcfdi` queda relegado a benchmark o referencia de dominio

## Cierre ejecutivo

Lectura recomendada del estado actual:
- el roadmap cumplió su objetivo técnico principal
- no existe otra fase de implementación obligatoria dentro de esta secuencia
- cualquier trabajo futuro sobre el motor debe tratarse como reapertura, no como continuación automática
