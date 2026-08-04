# Auditoría — Tabla de progreso y resultados (Análisis masivo / Conversión masiva)

- Status: history (hallazgos técnicos, ya resueltos) + decisión pendiente (dirección estética)
- Fecha: 2026-08-03
- Alcance: las tablas de Análisis masivo y Conversión masiva
- Complementa: [masivo-ux-analysis.md](./masivo-ux-analysis.md) — ese documento cubre flujo/
  descubrimiento para diseño (2026-06-03, aún sin implementar); este cubre estructura técnica de
  tabla y accesibilidad, ya implementado y verificado. Sus capturas base (`docs/screens/*.png`
  previas a esta fecha) quedaron obsoletas: el script que las generaba apuntaba a una ruta movida.
- Evidencia: `docs/screens/2026-08-03/` (capturas Playwright antes/después + scripts de captura)

## Estado de implementación

Plan ejecutado en 4 PRs secuenciales, validado por `decision-expander` (tabla de ponderación y
secuenciación). Verificación en cada PR: `tsc --noEmit` + `vitest` contra línea base (10 errores/
13 tests preexistentes, ajenos al alcance, sin cambio en ningún PR) + captura visual con Playwright.

| Hallazgo | Estado |
|---|---|
| Altura fija (`h-72`/`max-h-[560px]`) ocultaba la mayoría de las filas | ✅ Altura flexible, `md:`-gated, verificado en 3 viewports |
| Montos alineados a la izquierda | ✅ Alineación derecha + `tabular-nums` |
| `max-w` inconsistentes (5 valores distintos) sin `table-fixed` | ✅ `<colgroup>` en las 3 tablas |
| Retícula distinta entre tabla en vivo y tabla de resultados | ✅ Verificado con 0px de diferencia en x de RFC EMISOR entre ambas |
| Doble spinner en Conversión masiva | ✅ Un solo indicador (el badge de estado ya lo traía) |
| Sticky header faltante en 2 de 3 tablas | ✅ Las 3 tablas |
| Sin `prefers-reduced-motion` | ✅ Animaciones envueltas en `@media` |
| Columna HALLAZGOS repetía la columna ESTADO | ✅ Fusionado en el badge |
| Widget flotante: dos lotes simultáneos, uno se ocultaba sin avisar | ✅ `FloatingBatchWidgetStack` los apila, cada uno con etiqueta propia. Verificado con 5 tests unitarios (`renderReact`, patrón ya usado en el proyecto) |
| Sin barra de estado persistente en la tabla en vivo | ✅ Borde izquierdo por color |
| Texto de implementación expuesto ("Máximo 4 subidas simultáneas") | ✅ Retirado |
| Cero ARIA / tabla no operable por teclado | ✅ `aria-sort`, `scope`, `aria-rowcount`, navegación por teclado verificada con Playwright |
| RFC/Emisor repetidos sin atenuar | ✅ Atenuado en filas consecutivas |
| Zebra inconsistente entre tablas | ✅ Quitada de las 3 (no añadida) |
| Sin pie de conteo en la tabla en vivo | ✅ Agregado |
| Tarjeta de métrica sola a ancho completo al inicio | ✅ `grid grid-cols-3` reservado desde el inicio |

**Fuera de esta ronda:** dirección estética (Parte 1, abajo) — decisión previa, no implementada.
Contraste WCAG numérico de los tokens de color — no se llegó a medir.

## Deuda de tooling encontrada de paso

`scripts/capture-masivo-screens.py` apunta a una ruta que ya no existe (`amigo/archivos/` se
movió a `cfdi-suite-extras/amigo/archivos/`) y lleva meses sin producir capturas válidas. Usar en
su lugar los scripts en `docs/screens/2026-08-03/` (`capture_v2.mjs`, `capture_resolved.mjs`).

---

## Parte 1 — Por qué la UI se percibe genérica (decisión pendiente, no implementada)

**Veredicto de una línea:** no es que esté mal hecha — es que nadie la decidió. Cada superficie,
color y tamaño de letra es el default de Tailwind o de una plantilla comprada. Prueba textual:
`index.css:8` dice literalmente `/* Custom text sizes (Tailux design tokens) */` — Tailux es una
plantilla de dashboard comercial.

**Causa raíz — no existe escala tipográfica.** De 341 usos de tamaño de texto en el frontend,
287 están entre 10px y 12px. Trece en total pasan de 14px. Sin contraste tipográfico el ojo no
encuentra puerta de entrada. Esto también explica el problema de altura fija resuelto arriba:
mientras la tabla se trate como una tarjeta de tamaño propio, no como un lienzo que ocupa el
viewport, cualquier altura fija va a estar mal para contenido de 7 o de 5,000 filas.

**Otros síntomas del mismo origen:** la misma tarjeta blanca repetida 51 veces como única
herramienta de agrupación; cinco radios de esquina distintos y simultáneos en una sola pantalla;
la misma taxonomía (ok/hallazgo/error) dibujada cuatro veces (stepper, tarjetas, píldoras, badge
por fila); emoji junto a iconos monolineales sin acompañamiento tipográfico.

**Sobre la paleta — el usuario reportó que le gustan los colores.** El índigo es literal,
verificado escalón por escalón contra el `indigo` de Tailwind (`#eef2ff`…`#1e1b4b`, los once
coinciden exacto) — no es una paleta ajustada, es la constante de Tailwind renombrada a
`primary`. El mismo índigo se usa con cuatro significados distintos en una sola pantalla (marca,
ubicación, filtro activo, progreso), por eso no se lee como marca sino como resaltador.

### Tres direcciones estéticas nombradas y opuestas

Todas parten de un referente que el índigo de Tailwind no tiene: el mundo visual de la
contabilidad mexicana — papel de trabajo, libro mayor, tinta sobre bond. *(El guinda
institucional #611232 es la familia correcta pero es el color del gobierno federal; desplazarlo
hacia el tinto, no copiarlo literal.)*

- **A — "Libro Mayor".** La tabla ES la página: sin sombras, sin radio, sin contenedor. Sustrato
  cálido de papel, estado como glifo de un carácter (✓ ! ✗) en vez de píldora. La más alejada del
  estado actual.
- **B — "Consola".** La app ya tiene esta veta latente: archivo y RFC ya van en monoespaciada.
  Fondo oscuro, un único color de señal reservado exclusivamente para estado. La más arriesgada
  para un contable formado en Excel, la que más rápido se lee como intencional.
- **C — "Cuadro".** Tres tamaños de tipo con salto real (48px display vs 14px cuerpo), blanco
  puro, un solo acento. Requiere reescribir los 93 usos de `text-tiny`, pero mejor resultado por
  esfuerzo invertido.

**Si solo se hace una cosa:** borrar `--text-tiny`/`--text-tiny-plus`, subir el piso a 13-14px, y
crear un tamaño display (>40px) para la cifra dominante de cada pantalla. En paralelo: unificar a
un solo verde (`green`/`emerald` compiten hoy), un solo ámbar (`amber`/`yellow`), un solo azul
(`blue`/`primary` en la misma función, `ConversionMasivaPage.tsx:1177-1179`).
