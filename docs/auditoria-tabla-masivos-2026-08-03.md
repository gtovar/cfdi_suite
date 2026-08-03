# Auditoría — Tabla de progreso y resultados (Análisis masivo / Conversión masiva)

## Estado de implementación (actualizado 2026-08-03, tarde)

Plan ejecutado en 4 PRs secuenciales, sobre `/Users/gil/.claude/plans/jolly-launching-gizmo.md`,
validado dos veces por `decision-expander` (tabla de ponderación y secuenciación de PRs).
Verificación en cada PR: `tsc --noEmit` + `vitest` contra línea base (10 errores/13 tests
preexistentes, ajenos al alcance, sin cambio en ningún PR) + captura visual con Playwright.

| # | Hallazgo | Estado |
|---|---|---|
| 1 | Altura fija (`h-72`/`max-h-[560px]`) | ✅ Resuelto — PR2, `md:`-gated, verificado en 3 viewports |
| 2 | Montos alineados a la izquierda | ✅ Resuelto — PR1 |
| 3 | Topes `max-w` inconsistentes / falta `table-fixed` | ✅ Resuelto — PR3, `<colgroup>` en las 3 tablas |
| 4 | Widget: caso de dos lotes simultáneos | ✅ Resuelto — `FloatingBatchWidgetStack` apila los widgets en vez de ocultar uno; cada uno con etiqueta propia (Análisis masivo / Conversión masiva). Verificado con 5 tests unitarios (`FloatingBatchWidget.test.tsx`, patrón `renderReact` ya usado en el proyecto — no se instaló ninguna librería nueva) |
| 5 | Convergencia de retícula entre tablas | ✅ Resuelto — PR3, verificado con 0px de diferencia en x de RFC EMISOR entre ambas tablas |
| 6 | Doble spinner en Conversión masiva | ✅ Resuelto — PR4 |
| 7 | Sticky header faltante | ✅ Resuelto — PR3, las 3 tablas |
| 8 | Sin `prefers-reduced-motion` | ✅ Resuelto — PR4 |
| 9 | HALLAZGOS repite ESTADO | ✅ Resuelto — PR3, fusionado en el badge |
| 10 | Widget contradictorio | ✅ Corregido el texto del hallazgo (ver abajo); el gap menor queda en el ítem #4 |
| 11 | Sin barra de estado persistente | ✅ Resuelto — PR4 |
| 12 | Texto de implementación expuesto | ✅ Resuelto — PR4 |
| 13 | Cero ARIA / sin teclado | ✅ Resuelto — PR1, verificado con navegación por teclado real (Playwright) |
| — | RFC/EMISOR repetidos sin atenuar | ✅ Resuelto — PR4, verificado visualmente con dataset de prueba |
| — | Zebra inconsistente | ✅ Resuelto — PR4, quitada de las 3 tablas (no añadida) |
| — | Pie de conteo en tabla en vivo | ✅ Resuelto — PR4 |
| — | Tarjeta de métrica sola a ancho completo | ✅ Resuelto — PR4, `grid grid-cols-3` |

**Fuera de esta ronda:** dirección estética (Libro Mayor/Consola/Cuadro) — decisión previa, no
implementada. Contraste WCAG numérico — nunca se completó esa lente del panel.

---

**Fecha:** 2026-08-03
**Alcance:** las dos pantallas de trabajo masivo y sus tablas.
**Método:** capturas nuevas con Playwright sobre la app corriendo en local, lectura del código,
y un panel de 5 subagentes con lentes separadas (tablas densas, UX de progreso, producto fiscal,
accesibilidad, dirección de arte).

## Estado del panel

De 5 lentes, **2 entregaron reporte completo** (tablas densas, dirección de arte) y **1 quedó
cubierta por verificación directa del agente principal** (accesibilidad — hallazgos básicos).
**2 no entregaron**: `producto-fiscal` y `a11y-calidad` (para su parte más fina, ratios de
contraste) chocaron con el límite real de la cuenta — restablece **2:10pm America/Monterrey**.
`ux-progreso` murió antes por el mismo motivo.

Dato operativo importante para la pregunta del loop: **5 agentes en paralelo, cada uno leyendo
capturas e imágenes, agotan el límite de la cuenta antes de completar una ronda.** No es apto
para iterar sin ajustar el tamaño del panel.

Todo hallazgo de este documento está clasificado por su propio autor en una de tres categorías
de evidencia (ver "Procedencia" en cada sección). **Nada depende de la captura de junio** —
se descartó por completo tras confirmar que estaba 2 meses obsoleta.

## Cómo se generaron las capturas

Script: `docs/screens/2026-08-03/capture_v2.mjs` (estados reales, XMLs de `cfdi-suite-extras/amigo/archivos/`)
y `capture_resolved.mjs` (estado resuelto, API interceptada con `page.route()` y datos sintéticos
variados — no se usaron credenciales de GCP para no subir archivos de prueba al bucket de producción).

El script antiguo `scripts/capture-masivo-screens.py` **está roto**: apunta a `amigo/archivos/`,
ruta que se movió a `cfdi-suite-extras/amigo/archivos/`. Los PNG de `docs/screens/` anteriores a
esta fecha están obsoletos y no deben usarse como referencia.

---

## Parte 1 — Por qué se ve "genérico"

*(Lente: dirección de arte. Evidencia: capturas frescas + `index.css` + componentes. Cero
dependencia de la captura de junio.)*

**Veredicto de una línea:** no es que esté mal hecha — es que nadie la decidió. Cada superficie,
color y tamaño de letra es el default de Tailwind o de una plantilla comprada. Prueba textual,
no interpretación: `index.css:8` dice literalmente `/* Custom text sizes (Tailux design tokens) */`.
Tailux es una plantilla de dashboard comercial. El origen genérico está nombrado en el propio código.

### 1. No existe escala tipográfica — causa raíz, por encima del color
De 341 usos de tamaño de texto en el frontend: 287 están entre 10px y 12px (`text-tiny` 93,
`text-xs` 194). Trece en total pasan de 14px. En la captura del estado en proceso, las tres
cifras que el contable más necesita ("1000.0 /seg", "$286K MXN", "~1s") están a 18px dentro de
tarjetas de ~550px de ancho, con un rótulo de 10px encima — ocho píxeles de diferencia para
separar metadato de cifra. Sin contraste tipográfico el ojo no encuentra puerta de entrada.

### 2. La misma tarjeta blanca, 51 veces, como única herramienta de agrupación
`rounded-xl border border-gray-200 bg-white shadow-sm` se repite 13 veces exacto, 51 en
variantes. Métrica, tabla, banner y widget flotante son la misma caja. Cuando todo contenedor
pesa igual, la jerarquía dependería solo de la tipografía — y el punto 1 dice que ahí no la hay.

Esto también explica el hallazgo del `h-72` (Parte 2, #1): mientras la tabla se trate como una
tarjeta —un objeto de tamaño propio, no un lienzo que ocupa el viewport— cualquier altura fija
que se le asigne va a estar mal para contenido de 7 o de 5,000 filas.

### 3. Cinco radios de esquina distintos, simultáneos, en una sola pantalla
`rounded` (checkbox), `rounded-md` (tab), `rounded-lg` (botones, contenedor de tabs),
`rounded-xl` (tarjetas), `rounded-full` (píldoras, badges) — los cinco visibles a la vez en la
pantalla de resultados. Un lenguaje con autor usa dos radios: superficie y control. Cinco no es
flexibilidad, es ausencia de sistema.

### 4. El encabezado `text-tiny uppercase tracking-wider text-gray-500`, 28 veces
El tic más reconocible de plantilla de dashboard. Con once columnas en la tabla de resultados
debería sostener la lectura horizontal; en la práctica es el elemento más débil de la fila,
hundido bajo su propio contenido.

### 5. La misma taxonomía (ok / hallazgo / error) dibujada cuatro veces
Stepper, tres tarjetas pastel, píldoras de filtro y badge por fila comunican lo mismo en
~400px verticales — y las tarjetas y las píldoras hacen literalmente el mismo trabajo (ambas
filtran la tabla), con formas distintas, una encima de otra. La columna HALLAZGOS repite otra
vez el estado de ESTADO en la misma fila, a ~900px de distancia. La pregunta "¿qué manda en
esta pantalla?" tiene una respuesta honesta: manda la redundancia.

### 6. Emoji junto a iconos monolineales, e Inter sin acompañamiento
`InsightCard` usa `icon="🏆"` e `icon="📅"` junto a los iconos grises de `lucide-react`. Dos
sistemas de ilustración a la vez, y son los únicos elementos con color saturado de esa mitad
de pantalla — para celebrar trivia ("Mes más activo"). Inter + gris sobre blanco + acento
índigo es, por sí solo, el aspecto de otros diez mil productos.

### Veredicto sobre la paleta — el usuario dice que le gustan los colores

**El índigo es literal, verificado escalón por escalón contra el `indigo` de Tailwind:**
`#eef2ff`, `#e0e7ff`, `#6366f1`, `#4f46e5`, `#312e81`, `#1e1b4b` — coinciden los once escalones.
No es una paleta índigo ajustada: es la constante `indigo` de Tailwind renombrada a `primary`.
**Esto lo verificó también el agente principal, comparando `index.css:18-28` directo contra la
escala pública de Tailwind — no depende del criterio del experto.**

Sin diplomacia: no tiene razón en que el índigo sea una elección, y la razón importa. Le gusta
el índigo como le gusta una pared recién pintada de gris: no le molesta. Pero "no me molesta"
no es identidad. La pregunta que hoy no tiene respuesta en el repositorio es *por qué índigo y
no, por ejemplo, la tinta de un libro mayor* para un producto fiscal mexicano.

El mismo índigo, además, se usa con cuatro significados distintos en una sola pantalla: logo
(marca), nav activo (ubicación), píldora "Todas" (filtro activo), nodos del stepper (progreso).
Un sistema diría que el acento sólido significa una sola cosa. Por eso no se lee como marca:
se lee como resaltador.

Y el semáforo de las tres tarjetas (verde/amarillo/rojo al 50%) es la misma enfermedad que el
índigo, no una excepción: son escalones crudos de Tailwind, la primera respuesta disponible
ante una taxonomía de tres estados, no una decisión sobre CFDI.

### Tres direcciones estéticas nombradas y opuestas

Las tres parten de un referente que el índigo de Tailwind no tiene: el mundo visual de la
contabilidad mexicana — papel de trabajo, libro mayor, tinta sobre bond. *(Nota: el guinda
institucional #611232 es la familia de color correcta pero es el color del gobierno federal;
hay que desplazarlo hacia el tinto, no copiarlo literal — un SaaS privado no debe leerse como
portal oficial.)*

**A — "Libro Mayor".** La tabla ES la página: sin sombras, sin radio, sin contenedor. Sustrato
cálido de papel (`--color-paper: #faf8f4`) en vez de gris azulado. Estado como glifo de un
carácter (✓ ! ✗) en vez de píldora. Las tres tarjetas de resumen se vuelven una línea de
sumario tipo balance contable. Acento en tinto (`#7a1f2e`), no guinda literal. La dirección
más alejada del estado actual — y la única que ningún competidor tendrá por accidente.

**B — "Consola".** La app ya tiene esta veta latente sin explotar: los nombres de archivo y
RFC ya se renderizan en monoespaciada. Fondo oscuro continuo, la monoespaciada como rol
tipográfico de primer nivel, un único color de señal reservado exclusivamente para estado
(nunca para botones ni marca — resuelve el problema de los cuatro significados del índigo por
definición). El estado de fila pasa a ser una barra vertical de 3px al margen izquierdo, lo
que libera el ancho que hoy pierde EMISOR por truncamiento. La más arriesgada para un contable
formado en Excel; la que más rápido se lee como "hecha con intención".

**C — "Cuadro".** Antídoto directo al problema #1: tres tamaños de tipo en todo el producto,
con un salto real entre display (48px) y cuerpo (14px) — no de ocho píxeles. Blanco puro, sin
campo gris, sin tarjetas; la alineación sustituye a los bordes. Un solo acento (naranja
quemado, un uso por pantalla). Los montos suben a 20px tabular en la tabla. Requiere reescribir
los 93 usos de `text-tiny`, pero es la de mejor resultado por esfuerzo invertido.

**Si solo se hace una cosa:** borrar `--text-tiny`/`--text-tiny-plus`, subir el piso a 13-14px,
y crear un tamaño display (>40px) para la cifra dominante de cada pantalla. Sin tocar un solo
color, eso ataca la causa real: 287 de 341 decisiones tipográficas dicen hoy lo mismo. En
paralelo: unificar a un solo verde (hoy `green`/`emerald` compiten), un solo ámbar (`amber`/`yellow`
conviven en la misma pantalla) y un solo azul (`blue`/`primary` en la misma función, líneas
contiguas en `ConversionMasivaPage.tsx:1177-1179`).

---

## Parte 2 — Defectos concretos de la tabla

*(Lente: tablas densas + verificación directa del agente principal. BAP = `BatchAnalysisPage.tsx`,
CMP = `ConversionMasivaPage.tsx`.)*

### 1. Altura fija deja la mayoría de las filas fuera de vista — `bloqueante`
`BAP:501` — `h-72` (288px fijos) en la tabla en vivo. Con filas de 36px caben 7-8 de 45.
`BAP:1620` — `max-h-[560px]` en la tabla de resultados; corta la última fila visible a la mitad.
Es la causa exacta de *"los últimos registros se quedan escondidos"*.
**Cambio:** altura flexible atada al viewport (`flex-1 min-h-0` en el contenedor padre), no un
número fijo.

### 2. Los montos y tamaños van alineados a la izquierda — `bloqueante`
Con datos variados (`$117.99` a `$235,000.00`) los puntos decimales caen en ocho posiciones
distintas; comparar magnitudes exige leer dígito por dígito. **El usuario pidió "centrar" — el
síntoma que detectó es real, pero centrar es peor que la izquierda actual**: hace bailar el
decimal en las dos direcciones a la vez, y ni siquiera alinea el símbolo `$` como hoy. Lo
correcto es **alineación derecha con `tabular-nums`** (que la columna ya usa, pero sin
alineación no sirve). Encabezado también a la derecha.
**Cambio:** `text-right` en `<th>` y `<td>` de TOTAL, TAMAÑO y HALLAZGOS.

### 3. Los topes de ancho truncan texto que tenía espacio libre — `bloqueante`
Ninguna de las tres tablas usa `table-fixed`; el navegador reparte el ancho por contenido,
pero cada celda además impone su propio tope desconectado (`max-w-[160px]`, `max-w-[180px]`,
`max-w-[200px]`, `max-w-[220px]`, `max-w-[280px]` — cinco topes distintos para el mismo tipo de
dato en tres lugares). Resultado visible: 5 de 6 nombres de emisor truncados con ~92px libres
al lado. El mismo emisor se corta en dos puntos distintos según la vista (`AUCHAN COMERCIALIZA…`
en una tabla, `AUCHAN COMERCIALIZADO…` en otra), y dos razones sociales con prefijo compartido
colapsan a la misma cadena truncada mientras el espacio para distinguirlas existe, vacío.
**Cambio:** `table-fixed` con un `<colgroup>` de anchos porcentuales compartido entre las dos
tablas, y eliminar los `max-w-[…]` sueltos — con ancho fijo el `truncate` corta justo en el borde.

### 4. Dos tablas con densidad de información distinta que no comparten retícula — `importante`
Verificado con precisión: la altura de fila **no** difiere (ambas usan `style={{height:36}}`).
Lo que difiere es cuántos campos caben en esos 36px: 6 en la tabla en vivo, 9-11 en la de
resultados, y la columna TIPO se inserta en medio y desplaza todo lo que sigue.
**Veredicto:** las dos tablas *deben* diferir en affordances — la tabla en vivo es un monitor
(no se puede seleccionar ni ordenar lo que aún no termina), la de resultados es un libro mayor
(se filtra, ordena, selecciona). Pero **no deberían divergir en la retícula**: son las mismas
45 filas de la misma sesión, y el usuario construye un mapa espacial en la fase en vivo que la
fase de resultados invalida al reordenar las columnas.
**Cambio:** un `<colgroup>` compartido con las columnas exclusivas de la fase de resultados
(checkbox, acción) reservadas y vacías en la tabla en vivo, para que cada dato caiga en la
misma posición horizontal en ambas fases.

### 5. Encabezado uppercase de 10px: correcto aquí, no es ruido — veredicto matizado
A diferencia de otros usos de plantilla (Parte 1, #4), en el contexto específico de una tabla
densa este patrón cumple su función: cede jerarquía al dato. Único ajuste necesario: alinear a
la derecha los encabezados numéricos (hoy TOTAL cuelga sobre el aire de una columna alineada
a la izquierda).

### 6. Dos indicadores del mismo estado en la misma fila — `importante`
`CMP:1174-1191` — cada fila en conversión muestra el badge "Enviando XML…" y además un
segundo spinner suelto en una columna sin encabezado, a la derecha. Con 20 filas son 40
animaciones diciendo lo mismo. Causa exacta de *"cuando cambia de spinner a otra etiqueta se ve mal"*.
**Cambio:** un solo indicador; la columna de acción queda vacía o estable mientras el estado
se comunica en su propia columna.

### 7. La columna HALLAZGOS repite lo que ya dice ESTADO — `importante`
Toda fila con número en HALLAZGOS dice "Con hallazgos" en ESTADO; toda fila con "—" dice "Sin
errores" o "Error de lectura" — correlación perfecta, verificada en 26 filas de dos capturas
distintas. Dos columnas separadas por el ancho completo de la tabla para un solo hecho.
**Cambio:** fundir el contador dentro del badge de estado y eliminar la columna HALLAZGOS.

### 8. RFC, EMISOR y TIPO repiten valores con alta frecuencia — `importante`
Incluso con un set sintético deliberadamente variado (8 emisores), 5 RFC se repiten en 14
filas y TIPO solo toma dos valores en toda la tabla. La propia app ya asume esta concentración
(tarjeta "Emisor más frecuente"). Es razonable inferir —marcado como inferencia, no hecho— que
un lote real (facturas de un mismo cliente) repetirá más, no menos. La repetición entrena al
ojo a saltarse esas columnas, así que la fila con el emisor distinto —la interesante— se vuelve
invisible.
**Cambio:** atenuar (no ocultar) el valor repetido consecutivo en la tabla de resultados; en la
tabla en vivo (orden fijo, no reordenable) se puede usar celda vacía cuando coincide con la
fila anterior. TIPO debería ser una píldora de filtro más, no una columna.

### 9. El encabezado no es pegajoso (`sticky`) en 2 de las 3 tablas — `importante`
`BAP:503` sí tiene `sticky top-0 z-10`. `BAP:1628` (resultados) y `CMP:1154` (conversión) no
lo tienen, pese a estar dentro de contenedores `overflow-auto` de altura acotada. Con 15 filas
visibles de 45 en la tabla de resultados, al tercer scroll un número queda sin columna que lo
identifique. *(Verificado por lectura de código; no confirmado en una captura porque las
disponibles no capturan el momento exacto del scroll intermedio en esa tabla específica.)*
**Cambio:** replicar el mismo `className` de `BAP:503` en las otras dos.

### 10. Widget flotante: caso de dos lotes simultáneos sin resolver, y tapa la tabla — `importante`
**Corregido 2026-08-03:** el texto original de este hallazgo ("contadores contradictorios, 0/45
vs 0/20, sin explicación de a qué lote pertenece") era incorrecto y se reclasifica de
`bloqueante` a `importante`. Verificado directamente en `App.tsx:103,107,528-542`: la app ya
separa `batchMasivoStatus` y `batchPdfStatus` en dos estados independientes, cada widget lee el
suyo. Lo capturado en `13-conversion-processing-viewport.png` fue el script de prueba
(`capture_v2.mjs`) encadenando el flujo de Análisis masivo —que nunca llegó a `done` por el
backend local roto— directo con Conversión masiva, en la misma sesión de página, sin limpiar el
primer lote. No es un bug de contadores cruzados.

El gap real y menor, documentado por el propio autor del código en `App.tsx:523-527`: cuando dos
lotes corren a la vez, solo se muestra un widget (se prioriza Análisis masivo), sin indicar que
hay un segundo lote en curso. También se superpone a las últimas filas visibles de la tabla,
tapando texto de sus badges.
**Cambio (opcional):** cuando ambos lotes corren a la vez, mostrar los dos widgets apilados o un
indicador de "+1 lote" en vez de ocultar el segundo; reservar espacio para que no tape contenido.

### 11. Ninguna animación respeta `prefers-reduced-motion` — `importante`
Verificado: la media query no existe en ningún punto de `index.css`. Las críticas son
`row-flash-ok/yellow/red` (1.1s), que se disparan una vez por cada fila que se resuelve — 45
destellos encadenados en un lote grande, sin forma de desactivarlos.
**Cambio:** envolver las animaciones en `@media (prefers-reduced-motion: no-preference)`, y
reconsiderar si el flash por fila tiene sentido en lotes grandes.

### 12. Cero ARIA en ambas tablas; ordenar y abrir detalle son solo de mouse — `bloqueante`
Verificado: sin `aria-live`, `aria-rowcount`, `scope` en los `<th>`, ni `<caption>`. Y en
`BAP:1632-1638` el `onClick` de ordenar está en el `<th>` directo (sin `<button>`, sin
`tabIndex`, sin `aria-sort`); en `BAP:1654-1656` las filas clicables son `<tr onClick>` sin rol
ni foco. En una herramienta donde alguien procesa cientos de facturas al día, perder el
teclado es costo operativo, no solo accesibilidad.
**Cambio:** `<button>` dentro del `<th>` con `aria-sort`; `tabIndex={0}` + `role="button"` +
handler de teclado en la fila; `aria-live="polite"` acotado para el progreso del lote.

### 13. Sin señal de estado a nivel de fila en la cola en vivo — `importante`
El único indicador es un badge de columna de tamaño y posición fijos, con fondos al 50% de
saturación que en la práctica dan luminancia casi idéntica entre "Sin errores" (verde) y "Con
hallazgos" (amarillo). El tinte de fila (`row-flash-*`) es transitorio por construcción — exige
`isNew`, así que no ayuda a *encontrar* después la fila problemática, solo a notarla en el
instante en que llega.
**Cambio:** una barra de 2px al borde izquierdo de la fila, coloreada por estado, persistente
(no solo el flash transitorio) — permite ver el patrón de las 45 filas sin leer cada badge.

### Detalles menores (`pulido`)
- Tarjeta VELOCIDAD sola ocupando todo el ancho al inicio del proceso, antes de que aparezcan
  las otras dos — se lee como layout roto, no como estado de carga.
- Se expone detalle de implementación al usuario: "Máximo 4 subidas simultáneas", "Procesando
  de 4 en 4…" (truncado con elipsis).
- Zebra (`bg-gray-50/50`) y borde inferior a la vez en la tabla de resultados, pero solo borde
  en la tabla en vivo — inconsistente entre las dos, y a 36px de alto el borde solo ya basta.
- Columnas de acción (PDF, chevron, confirmar/reintentar) sin `<th>` propio y con anchos que
  varían según el estado de la fila, produciendo un borde derecho dentado.
- `overscan: 5` sobre un contenedor de solo 288px de alto: el virtualizador no compra nada de
  rendimiento ahí — la altura del contenedor es el problema, no la virtualización.
- Falta un pie de conteo ("45 archivos") en la tabla en vivo; sí existe en la de resultados.

---

## Pendiente — se completa después de las 2:10pm si se retoma

- **Lente de producto fiscal:** qué columnas sobran o faltan para el trabajo real de un
  contable (UUID, folio, método de pago, moneda, agregados de IVA/ISR del lote).
- **Ratios de contraste numéricos** (WCAG AA) de los tokens de gris y de los tres badges de
  color — la a11y básica (motion, ARIA, teclado) ya quedó cubierta en la Parte 2, #11 y #12.
- **Verificación con datos reales** de las métricas VELOCIDAD / TIEMPO RESTANTE — las cifras
  observadas ("1000.0 /seg", "~1s restante") vienen de la captura con API interceptada y
  podrían estar distorsionadas por el método, no por la app.

## Deuda encontrada de paso

`scripts/capture-masivo-screens.py` apunta a una ruta que ya no existe y lleva ~2 meses sin
producir capturas válidas. Los PNG de `docs/screens/` anteriores a esta fecha están obsoletos.
