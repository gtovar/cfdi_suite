# Decision Review: `cfdi_inspector` as Frontend + `python-satcfdi` as Backend

Date: 2026-04-18

## 1. Decisión nueva

Se reabre la dirección del producto.

La ruta elegida deja de ser:

- inspector local acotado con motor TypeScript como runtime principal

Y pasa a ser:

- `cfdi_inspector` como frontend de inspección
- `python-satcfdi` como backend y motor principal de dominio

## 2. Qué significa

- la UI actual se conserva como shell de producto
- el conocimiento fiscal amplio deja de crecer dentro del browser
- el motor TypeScript local pasa a ser compatibilidad temporal y fallback, no dirección estratégica
- la frontera importante ya no es solo `producto vs motor`, sino `frontend vs backend`

## 3. Por qué cambia la dirección

- el objetivo del producto ya no es solo inspección acotada de `ingreso` y `pagos`
- el valor esperado ahora sí incluye una base fiscal/técnica más amplia
- `python-satcfdi` tiene más amplitud de dominio que el motor TS local
- seguir ampliando TypeScript duplicaría dominio con peor punto de partida

## 4. Qué se conserva

- experiencia de inspección en React/Vite
- flujo de carga y lectura operativa
- findings, tablas y navegación como lenguaje de producto
- contrato de salida que la UI necesita para renderizar

## 5. Qué cambia

- el análisis deja de vivir principalmente en worker/browser
- la UI debe consumir un backend HTTP o adaptador de proceso claramente delimitado
- `python-satcfdi` deja de ser benchmark congelado y pasa a ser candidato de implementación activa
- el contrato actual del engine deja de ser solo abstracción interna y pasa a ser base del contrato de API

## 6. Arquitectura objetivo

Flujo actual:

`XML -> motor TS local -> contrato -> UI`

Flujo objetivo:

`XML -> backend Python -> adaptador -> contrato JSON estable -> UI`

## 7. Riesgos que ahora sí aceptamos

- agregar runtime Python al producto
- definir despliegue y operación de backend
- invertir en un contrato estable entre frontend y backend

## 8. Riesgos que queremos evitar

- duplicar reglas fiscales en TypeScript y Python a largo plazo
- meter imports o lógica Node/Python dentro del bundle del navegador
- crecer el frontend como si fuera dueño del dominio

## 9. Regla nueva

Toda expansión relevante de cobertura CFDI/SAT debe considerarse primero en la capa Python.

Si una capacidad nueva no puede vivir razonablemente en el backend Python, hay que justificar explícitamente por qué debe quedar en TypeScript.

## 10. Primer frente real

El siguiente trabajo ya no es benchmark.

El siguiente trabajo real es:

1. definir el contrato HTTP/JSON entre frontend y backend
2. montar un backend mínimo de análisis sobre `python-satcfdi`
3. conectar el frontend a ese backend sin romper el flujo actual
4. retirar gradualmente el motor TS como camino principal

## 11. Conclusión corta

`cfdi_inspector` ya no debe pensarse como inspector local con engine intercambiable solamente.

Debe pensarse como:

- frontend de producto
- respaldado por un backend Python que concentre el dominio fiscal
