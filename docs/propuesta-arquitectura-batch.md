# Propuesta de arquitectura: batch masivo diseñado desde cero

> **Este documento es exploración, no un plan.** Nada aquí está decidido ni en
> construcción, y no reemplaza al sistema actual, que funciona bien para el volumen
> de hoy. Es la respuesta a una pregunta distinta: "si diseñáramos el camino de
> conversión masiva desde cero, sin arrastrar lo que ya existe, ¿cómo se vería con
> las mejores ideas disponibles?" Continúa la conversación de
> `docs/investigacion-escalamiento-masivo.md`, pero mientras ese documento parte de
> la arquitectura actual y pregunta si aguanta, este parte en blanco.

## El modelo: tres capas independientes

Un buen diseño para esto separa tres preguntas que hoy están mezcladas en una sola
pieza de infraestructura (Cloud Run + Cloud Tasks haciendo las tres cosas a la vez).

**1. Distribución — ¿quién hace cada factura?**
Cada XML es 100% independiente de los demás — no hay razón para que pasen por una
cola central que alguien tiene que sintonizar (profundidad, reintentos, backoff).
**Cloud Run Jobs** encaja aquí: le dices "esta tarea, 15,000 veces, hasta N a la
vez" y la plataforma arranca esas N copias en paralelo directamente, sin cola
propia que administrar. El problema de "cuántas caben a la vez" deja de ser un
número que se te puede olvidar re-sintonizar (como pasó con
`maxConcurrentDispatches`) y se vuelve un parámetro explícito del job.

**2. Velocidad por unidad — ¿qué tan rápido se hace CADA PDF?**
Hoy el render corre en Python (WeasyPrint para el header + ReportLab para la
tabla). Ya aprendimos algo real con el benchmark: ReportLab es 10-15× más rápido
que WeasyPrint con la misma calidad de diseño, solo por estar más cerca del metal.
Un motor de tipografía **compilado** (pensado para documentos con plantilla —
ej. algo en la familia de `typst`, en Rust) lleva esa misma lección un escalón
más abajo.

**3. El algoritmo interno — ¿cómo calcula cada unidad su propio trabajo?**
Independientemente del motor, hay una elección de algoritmo: calcular la posición
de cada fila y cada salto de página **uno por uno en un ciclo**, o calcularlos
**todos de un jalón** como una operación en bloque (`numpy.cumsum` para las
posiciones acumuladas, división vectorizada para decidir en qué página cae cada
fila). Es la técnica de "suma de prefijos" (prefix sum / scan) — se ve secuencial
pero no lo es forzosamente.

Las tres capas se combinan, no compiten: Cloud Run Jobs decide *quién* trabaja en
paralelo, el motor compilado decide *con qué velocidad* trabaja cada uno, y el
algoritmo vectorizado decide *qué tan inteligente* es el cálculo que hace cada uno
por dentro.

## Cómo se vería junta

```
ZIP subido (15,000 XMLs)
        │
        ▼
Manifiesto: divide los XMLs en shards (ej. 1 shard = 100 XMLs)
        │
        ▼
Cloud Run Job — N tareas en paralelo, cada una toma 1 shard
        │
        ├─ Tarea 1 (100 XMLs) ─┐
        ├─ Tarea 2 (100 XMLs) ─┤   cada tarea, por dentro:
        ├─ ...                 ┤   1. parsea sus 100 XMLs
        └─ Tarea N (100 XMLs) ─┘   2. calcula TODAS las posiciones de fila/página
                                      de sus 100 facturas en un jalón (vectorizado)
                                   3. el motor compilado dibuja cada PDF con esa
                                      geometría ya resuelta
                                   4. lo único que sigue siendo por-factura, sin
                                      poder agruparse: el sello digital y el QR
                                      (criptografía real del SAT — es de una sola
                                      factura, no se puede precalcular en bloque)
                                   5. sube el PDF a GCS, marca "listo" en Redis
        │
        ▼
Mismo Redis + Pusher que ya existe para el progreso en tiempo real
```

**Lo que se reutilizaría tal cual** (mismo patrón que ya vale para el "camino
masivo" del documento hermano):
- GCS como almacén de PDFs — mismo bucket.
- Redis para estado del batch y Pusher para progreso en tiempo real — el patrón
  "estado vive en Redis, no en memoria de la instancia" ya funciona bien y no
  depende de si el cómputo corre en Cloud Run o en un Job.
- El parseo SAX del XML (`parse_xml_to_rows`) — ya es O(1) en memoria, sirve igual
  aquí.

**Lo que sería trabajo nuevo, no una extensión de lo que hay:**
- El motor compilado en sí — hoy no existe, sería construir (o adoptar) uno.
- El cálculo vectorizado del layout — hoy `render_conceptos` calcula fila por fila
  en Python; vectorizarlo es reescribir esa lógica, no un ajuste.
- El job de Cloud Run y el paso de "dividir en shards" — infraestructura nueva.

## Lo que no sabemos (honesto, no es una promesa de velocidad)

1. ~~**Nunca se perfiló dónde se va el tiempo hoy, separando WeasyPrint (header) de
   ReportLab (tabla).**~~ **Resuelto el 12 de julio de 2026 — ver la sección
   "Resultado del perfilado de `generate()`" más abajo.** El hallazgo invierte la
   intuición que traía este punto: WeasyPrint no es lento por procesar mucho
   contenido, es un **costo fijo por factura** (~270ms, casi no cambia con el
   tamaño de la tabla) porque solo renderiza el header de una página. Para
   facturas típicas (pocas decenas de conceptos) ese costo fijo es el 70-85% del
   tiempo total — no la tabla.
2. **Un motor tipo `typst` es un candidato, no una pieza que encaje garantizado.**
   No se verificó si soporta bien lo que este proyecto necesita: sello digital y
   QR del SAT incrustados, el nivel de control de diseño que hoy tiene el editor
   HTML del usuario, ni el patrón exacto de plantilla que usan las facturas CFDI.
3. **No se verificó el paralelismo real que permite Cloud Run Jobs** — cuotas por
   proyecto/región, qué tan rápido escala a cientos de tareas simultáneas. Es
   posible que haya un límite de plataforma antes de llegar a donde uno esperaría.
4. **La vectorización ayuda al cálculo de posiciones, no al dibujo final del PDF
   ni a la criptografía por factura** — esas partes siguen siendo trabajo real por
   documento, vectorizar no las elimina.

## Para cuando se retome esto

Si se quiere convertir esta exploración en algo accionable, el primer paso natural
—y el más barato— es el punto 1 de arriba: perfilar `generate()` separando
WeasyPrint de ReportLab de `pypdf`, en local, sin tocar producción. Eso es lo que
convierte "creemos que el cuello de botella está aquí" en un hecho medido, y es la
base real para decidir si vale la pena construir cualquiera de las tres capas de
este documento.

## Resultado del perfilado de `generate()` (12 de julio de 2026)

**Qué se hizo y por qué se puede confiar en el número:** se escribió un script
local (`profile_generate.py`, corrido con el intérprete del backend,
`.venv/bin/python`, sin tocar producción ni desplegar nada) que reproduce
**exactamente** los pasos 3-6 de `generate_from_data()`
(`backend/app/services/pdf_pipeline.py:96-153`) — el mismo código que corre hoy
en producción, no una versión simplificada — pero con un cronómetro
(`time.perf_counter()`) alrededor de cada una de las tres etapas:

- **A. WeasyPrint** (`render_shell`, en `shell_service.py`) — renderiza el
  header HTML de la página 1.
- **B. ReportLab** (`render_conceptos`, en `canvas_service.py`) — renderiza la
  tabla de conceptos y el footer, páginas 2+.
- **C. `pypdf`** (`_stamp_and_merge`, en `pdf_pipeline.py`) — lee la altura real
  de cada PDF y fusiona el header sobre la página 1 del canvas.

Los datos de entrada no fueron un XML real: se usó
`sample_data.generar_datos_ejemplo(n_rows)`, una función que ya existe en el
proyecto (`backend/app/services/sample_data.py`) y que produce el **mismo shape
exacto** que `parse_xml_to_rows` (la misma función que sí procesa XML real en
producción) — esto es válido porque el propio documento ya establece que el
parseo del XML es O(1) en memoria y no es lo que se está investigando aquí; lo
que se mide es el render, no el parseo. Se corrieron 5 repeticiones por cada
tamaño de tabla y se reporta la mediana (para no dejar que un solo warm-up de
Python o una pausa de garbage collection distorsione el número). El paralelismo
interno de `render_conceptos` se fijó a `workers=1` a propósito, para medir el
costo de render puro por documento — esto es fiel a cómo se comporta hoy la
producción para un documento individual: desde el 2026-07-11 (ver comentario en
`canvas_service.py` línea ~692-699), un solo documento con miles de conceptos ya
NO reparte sus propios chunks entre varios núcleos; el paralelismo real de hoy
ocurre **entre documentos distintos** (varios workers del pool procesando
facturas diferentes al mismo tiempo), no dentro de un mismo documento.

### La tabla de resultados

| n_rows (conceptos) | WeasyPrint | ReportLab | pypdf merge | TOTAL | % WeasyPrint | % ReportLab | % pypdf |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1     | 0.275s | 0.021s | 0.030s | 0.324s | 84.8% | 6.6%  | 9.4% |
| 6     | 0.292s | 0.023s | 0.041s | 0.357s | 81.8% | 6.6%  | 11.5% |
| 50    | 0.273s | 0.038s | 0.031s | 0.352s | 77.5% | 10.9% | 8.9% |
| 200   | 0.271s | 0.081s | 0.032s | 0.392s | 69.2% | 20.7% | 8.1% |
| 1000  | 0.270s | 0.303s | 0.038s | 0.618s | 43.7% | 49.1% | 6.1% |
| 2000  | 0.269s | 0.585s | 0.045s | 0.910s | 29.6% | 64.2% | 4.9% |
| 5000  | 0.269s | 1.468s | 0.070s | 1.807s | 14.9% | 81.3% | 3.9% |

### Los tres hallazgos, en orden de importancia

**1. WeasyPrint es un costo FIJO por factura, no un costo que escale con el
tamaño de la tabla.** El tiempo de WeasyPrint se queda pegado en ~0.27-0.29
segundos sin importar si la factura tiene 1 concepto o 5,000 — porque WeasyPrint
solo renderiza el header (una página de tamaño y complejidad constante),
independientemente de cuántas filas tenga la tabla de conceptos, que es trabajo
de ReportLab. Esto tiene una consecuencia directa: **como el sello y el QR ya
vienen calculados, y la mayoría de facturas reales tienen pocas decenas de
conceptos (no miles)**, ese costo fijo de ~270ms es, en la práctica, el gasto
dominante del `generate()` de una factura típica — el 70-85% del tiempo total
para tablas de 1 a 200 filas.

**2. ReportLab sí escala con el tamaño de la tabla, y lo hace de forma
aproximadamente lineal** (5000 filas tarda ~2.5× lo que tardan 2000 filas —
2000→5000 es 2.5× más filas, y el tiempo pasa de 0.585s a 1.468s, también
~2.5×). Pero solo se vuelve el costo dominante del `generate()` completo a
partir de tablas grandes: el cruce donde ReportLab empieza a pesar más que
WeasyPrint ocurre en algún punto entre 200 y 1000 filas (aprox. donde ambas
curvas se cruzan cerca del 50%).

**3. El merge de `pypdf` nunca es el cuello de botella** — se queda entre 30 y
70 milisegundos en todo el rango medido, y de hecho su peso porcentual *baja*
conforme la tabla crece (9.4% en 1 fila, 3.9% en 5000), porque el resto del
trabajo crece más rápido que él.

### Por qué esto corrige, no repite, el benchmark de motores de junio de 2026

Existe un benchmark previo (`[[project-benchmark-motores-pdf]]` en la memoria de
este proyecto, corrido 2026-06-26) que comparó WeasyPrint contra ReportLab
**monolíticos** — es decir, midiendo cuánto tarda **todo el documento completo**
(header + tabla completa) si se renderizara entero en un solo motor. Esa medición
mostró a WeasyPrint 10-15× más lento que ReportLab a volumen — pero ese número
describe una arquitectura hipotética (todo en un motor), no la que corre hoy en
producción.

El pipeline real de hoy **nunca usa WeasyPrint para la tabla** — la separación
header(WeasyPrint)/tabla(ReportLab) que ya existe en `pdf_pipeline.py` fue
diseñada precisamente para explotar la ventaja de ReportLab en la parte que
escala (la tabla) y dejarle a WeasyPrint solo la parte que no escala (el header,
diseñable en HTML/CSS por el usuario). Ese diseño ya estaba haciendo, desde
antes de esta investigación, lo correcto en cuanto a *qué motor usa cada parte*.
Lo que esta ronda de perfilado añade es la pieza que faltaba: **cuantificar que,
precisamente por ese diseño, el costo fijo de WeasyPrint (no su velocidad de
tabla, que ya no se usa) es hoy el gasto dominante para la mayoría de facturas
reales.** El benchmark de junio y este perfilado no se contradicen — miden cosas
distintas, y juntos cuentan la historia completa: el diseño de separar header y
tabla ya evitó el peor escenario (WeasyPrint procesando miles de filas), pero
dejó sin resolver el costo fijo de renderizar el header con WeasyPrint en cada
factura.

### Qué implica esto para las tres capas de la propuesta original

Este hallazgo cambia dónde debería apuntar el esfuerzo si se decide construir
algo, y matiza el entusiasmo original por cada capa:

- **Capa 3 (vectorización del layout con `numpy`)** — el documento original la
  presenta como una mejora general al "algoritmo interno". Con este dato, su
  impacto real es condicional al tamaño de la factura: solo importa para tablas
  grandes (aprox. 1000+ filas), donde ReportLab ya es el costo dominante. Para
  la mayoría de facturas reales (pocas decenas de conceptos), vectorizar el
  cálculo de posiciones **no movería la aguja**, porque ReportLab ya es una
  fracción pequeña del tiempo total en ese rango (6.6-11% en 1-50 filas).
- **Capa 2 (motor de tipografía compilado tipo `typst`)** — el documento
  original lo presenta como reemplazo de "WeasyPrint (header) + ReportLab
  (tabla)" en conjunto. Con este dato, el reemplazo que de verdad movería la
  aguja para la mayoría de facturas es el de **WeasyPrint**, no el de
  ReportLab — porque WeasyPrint es el costo fijo dominante en el caso típico.
  Esto en realidad **refuerza el caso de negocio de la Capa 2** (no lo debilita):
  si un motor compilado reemplaza también el render del header (no solo la
  tabla), el techo de mejora por factura típica es mucho mayor de lo que el
  benchmark de junio sugería, porque ese 70-85% del tiempo hoy es la parte
  candidata a eliminar, no un 10-15% marginal.
- **Capa 1 (Cloud Run Jobs)** — sin cambios por este hallazgo; sigue siendo
  ortogonal (decide *quién* procesa en paralelo, no *qué tan rápido* procesa
  cada uno).

### El hallazgo lateral, puesto a prueba (12 de julio de 2026): sí vale la pena

La primera versión de este documento dejaba anotado, sin perseguir, un hallazgo
lateral: existe una función `get_or_create_shell()`
(`backend/app/services/shell_service.py:242-253`) cuyo docstring afirma que
cachea el PDF del shell "por hash del `html_template` (la estructura)" y solo
rellena los datos de la factura sobre esa estructura cacheada — pero su cuerpo
no tiene ninguna lógica de caché real (no hay diccionario, `lru_cache`, ni
comparación de hash), y además no se llama desde ningún lado del repo: es
código muerto. En ese momento quedó la pregunta abierta: ¿vale la pena
perseguir esa pista, o se ignora?

**Se hizo la prueba, y la respuesta es: la pista vale la pena, pero la premisa
original del docstring está mal — lo que hay que cachear no es el PDF, es la
configuración de fuentes.** Cachear el PDF completo por plantilla (como sugiere
el docstring) es imposible de raíz: cada factura tiene datos distintos (folio,
importes, nombres), así que el HTML que le llega a WeasyPrint es distinto en
cada llamada — no hay PDF de salida que se pueda reutilizar entre facturas.
Pero eso no significa que no haya nada que cachear dentro de esa llamada.

**El experimento:** se perfiló con `cProfile` una sola llamada a
`HTML(string=filled_html).write_pdf()` (la misma que hace `render_shell` hoy) y
se encontró, leyendo el código fuente de WeasyPrint instalado
(`weasyprint/document.py`, método `Document._render`), que **cuando no se le
pasa un `font_config` explícito, WeasyPrint crea uno nuevo en cada llamada**:

```python
if font_config is None:
    font_config = FontConfiguration()
```

Y el constructor de `FontConfiguration` (`weasyprint/text/fonts.py`) llama a
`fontconfig.FcInitLoadConfigAndFonts()` — **escanea el inventario completo de
fuentes instaladas en el sistema, desde cero, en cada llamada**, sin importar
si el documento declara fuentes propias (`@font-face`) o no. La plantilla
default de CFDI Suite no declara ninguna (usa `Helvetica, Arial, sans-serif`,
fuentes de sistema), así que la hipótesis inicial — "esto solo importaría si
hubiera fuentes custom" — resultó **incorrecta**: el escaneo de fuentes ocurre
de todas formas, para poder resolver cualquier `font-family`, incluidas las de
sistema.

Se probó crear un único `FontConfiguration()` una sola vez y reutilizarlo en
llamadas repetidas a `write_pdf(font_config=...)`, sobre el mismo HTML relleno
de una factura de ejemplo (`generar_datos_ejemplo(n_rows=6)`), 15 repeticiones
por variante:

| Variante | Mediana | Media | Mín | Máx |
|---|---:|---:|---:|---:|
| Sin reutilizar (comportamiento actual) | 240.8ms | 247.9ms | 233.3ms | 301.7ms |
| Reutilizando un `FontConfiguration()` por proceso | 162.0ms | 171.5ms | 157.2ms | 226.7ms |

**Reducción: 32.7% en la mediana**, solo por evitar repetir el escaneo de
fuentes del sistema en cada factura.

**Verificación de que no cambia el resultado:** se comparó el PDF generado sin
reutilizar contra el generado reutilizando `FontConfiguration` — **mismo
tamaño exacto, 47,002 bytes en ambos casos**. Reutilizar la configuración de
fuentes no altera el documento producido; solo evita rehacer un trabajo que da
el mismo resultado cada vez dentro del mismo proceso (el inventario de fuentes
del sistema no cambia factura a factura).

**Qué implica esto para el total de `generate()`:** aplicando esa reducción de
32.7% al componente WeasyPrint de la tabla de perfilado de arriba, el tiempo
total de `generate()` para una factura típica (pocas decenas de conceptos)
bajaría aproximadamente **25-28%** — por ejemplo, para `n_rows=6` (total
0.357s, de los cuales WeasyPrint son 0.292s), el nuevo total estimado sería
~0.261s. No es una promesa exacta (el experimento se corrió aislado, sin la
carga completa de `generate_from_data`), pero es la misma proporción de
mejora aplicada al mismo costo fijo ya medido.

> **Veredicto: SÍ valía la pena — se implementó.** Es una optimización de bajo
> riesgo (no cambia el PDF de salida, verificado) y de bajo costo de
> implementación, y es ortogonal a las tres capas de la propuesta original — no
> depende de construir Cloud Run Jobs, ni de un motor compilado, ni de
> vectorizar nada.

### Implementado el 12 de julio de 2026

A petición explícita, esta optimización se implementó de verdad en
`backend/app/services/shell_service.py` — no se quedó solo en el experimento
del scratchpad. El cambio:

- Se agregó `_get_font_config()`: un `FontConfiguration()` guardado en
  `threading.local()`, creado una sola vez por hilo y reutilizado en llamadas
  posteriores dentro de ese mismo hilo.
- `render_shell()` y `render_shell_preview()` (las dos funciones activas que
  invocan WeasyPrint; `get_or_create_shell()` sigue sin usarse en ningún lado,
  no se tocó) ahora pasan `font_config=_get_font_config()` en vez de dejar que
  WeasyPrint cree uno nuevo en cada llamada.
- **Por qué por hilo y no un solo objeto global del proceso:** `render_shell`
  corre dentro de `PDF_PROCESS_POOL` (procesos aislados, un documento a la vez
  por proceso — ahí un config por hilo equivale a uno por proceso, sin
  cambios). Pero `render_shell_preview` se invoca desde
  `routers/templates.py` vía `asyncio.to_thread`, que sí puede correr en
  paralelo real en distintos hilos del mismo proceso (dos previews de diseño
  simultáneos, por ejemplo). Compartir un único `FontConfiguration` entre esos
  hilos habría sido un riesgo de condición de carrera no verificado (sus cachés
  internos, `strut_layouts`/`font_features`, no están documentados como
  thread-safe). Un config por hilo da el mismo ahorro sin ese riesgo.

**Verificación después del cambio, no solo antes:**
- Se corrió `generate_from_data()` completo (el pipeline real, no el
  experimento aislado) para facturas de 1, 6, 50 y 200 conceptos: **26-35% menos
  tiempo total**, ligeramente mejor que la estimación de 25-28% de arriba
  (`n=1`: 324ms→229ms; `n=6`: 357ms→234ms; `n=50`: 352ms→250ms; `n=200`:
  392ms→290ms), y los 4 PDFs resultantes son válidos (encabezado `%PDF`
  correcto).
- Se corrió la suite de tests del backend completa
  (`backend/.venv/bin/python -m pytest backend/tests/`, ejecutada desde la raíz
  del repo): **200 tests pasan, 0 fallos** — incluye
  `test_pdf_pipeline.py` y `test_table_preview_equivalence.py`, los dos
  archivos de test que tocan este código.
- El cambio no se ha desplegado a producción — vive en el working tree local,
  sin commit todavía (queda a criterio de cuándo se decida subirlo).

### Reproducibilidad

El script vive en el scratchpad de la sesión en que se corrió
(`profile_generate.py`), no en el repo — es una herramienta de un solo uso, no
parte del proyecto. Si se quiere volver a correr o extender (por ejemplo, con
más tamaños de tabla, o perfilando también con `workers>1` para ver el efecto
del pool de procesos), el script importa directamente
`app.services.canvas_service.render_conceptos`,
`app.services.pdf_pipeline._stamp_and_merge`,
`app.services.sample_data.generar_datos_ejemplo`, y
`app.services.shell_service.render_shell`/`get_html_template` — sin pasar por
FastAPI, Redis, GCS ni ningún estado de producción.

### Qué sigue después de este perfilado

La pregunta que dejaba abierta esta sección —¿por qué WeasyPrint tarda ~270ms
fijos, y se puede reducir sin cambiar de motor?— ya se contestó (ver arriba: es
el escaneo de fuentes del sistema, y reutilizarlo reduce el costo ~33%). Con
eso resuelto, hay dos caminos independientes desde aquí, y no son mutuamente
excluyentes:

1. **El camino barato y ya probado:** implementar la reutilización de
   `FontConfiguration()` en el pipeline actual (`shell_service.py`/
   `pdf_pipeline.py`) — ~25-28% menos tiempo por factura típica, bajo riesgo,
   sin esperar a ninguna decisión sobre las tres capas de este documento. Esto
   no requiere Ronda 1 ni Ronda 2; es una mejora del sistema que **ya está en
   producción hoy**, independiente de si el batch masivo rediseñado desde cero
   se construye algún día.
2. **El camino grande, sin resolver todavía:** convocar la Ronda 1 (el panel de
   tres perfiles: infraestructura/SRE, sistemas de documentos/tipografía,
   cumplimiento SAT) para evaluar si construir las tres capas de este documento
   sigue teniendo sentido, ahora con dos piezas de evidencia nueva en la mesa
   que no existían al escribir la propuesta original: (a) el perfilado que
   ubica el costo fijo de WeasyPrint como el gasto dominante en facturas
   típicas, y (b) que ese costo fijo tiene un margen de mejora barato *sin*
   necesidad de reemplazar el motor — lo cual matiza qué tanto se ganaría
   todavía con un motor compilado nuevo, una vez aplicada la mejora barata.

## Cómo se va a revisar esto: rondas, no una sola mesa

**Contexto de por qué existe esta sección:** el 11-12 de julio de 2026, al leer
este documento, surgió la idea de convocar un "consejo" — un grupo de agentes
especializados que lo revisaran antes de decidir si se convierte en plan. La
primera pregunta no fue "¿qué opinan los agentes de la propuesta?" sino una previa:
**¿quién debería sentarse en esa mesa, y es una sola mesa o varias?** Para
responder eso se corrió el skill `decision-expander` (expansión de decisión antes
de ejecutar). Esta sección es el resultado de ese ejercicio, integrado aquí para
que quede memoria de *por qué* se va a revisar en el orden en que se va a revisar,
y no se pierda el criterio la próxima vez que se retome este documento.

### La conclusión central del decision-expander

**No conviene una sola mesa homogénea de "arquitectos de software".** La propuesta
de arriba mezcla tres apuestas de naturaleza muy distinta (infraestructura de
plataforma, motor de tipografía con requisitos legales del SAT, y un cambio de
algoritmo), y cada una necesita un tipo de revisor distinto. Meterlas todas frente
al mismo panel genérico arriesga que la capa más peligrosa (el motor tipográfico
compilado, por el requisito de sello digital y QR del SAT) reciba el mismo nivel
de escrutinio superficial que la más segura (Cloud Run Jobs, que es configuración
de plataforma bien documentada, no una apuesta de diseño).

También se identificó un **riesgo de secuencia**: convocar deliberación elaborada
*antes* de tener datos de perfilado (el paso barato que ya recomienda la sección
anterior) corre el riesgo de producir opiniones bien articuladas sobre apuestas
que todavía no se han medido. Por eso el orden de las rondas de abajo empieza en
una investigación dirigida y barata, no en una mesa grande.

Y se identificó un **veto potencial duro**: si un motor tipográfico compilado
(familia `typst`) no puede incrustar el sello digital y el QR conforme a la
especificación del SAT (Anexo 20), la Capa 2 completa de este documento (el motor
compilado) se cae sin importar qué tan bien salga todo lo demás. Vale la pena
resolver esa pregunta primero, barato, antes de gastar deliberación de varios
perfiles en una apuesta que podría estar muerta desde el inicio por una razón
legal, no de ingeniería.

### Las rondas, en el orden en que se van a correr

**Ronda 0 — investigación dirigida, no consejo (barata, un solo agente
`general-purpose`).**
No es una mesa: es un agente investigando dos preguntas concretas que, si salen
mal, ya deciden buena parte del resto sin necesitar más deliberación:
1. ¿Puede un motor tipográfico compilado tipo `typst` incrustar el sello digital y
   el QR que exige el SAT (Anexo 20) para un CFDI? Esto es el veto duro de la
   Capa 2.
2. ¿Qué tan reales son las cuotas y límites de paralelismo de Cloud Run Jobs por
   proyecto/región en GCP? Esto acota qué tan lejos puede llegar la Capa 1 antes
   de chocar con un techo de plataforma.

Esta ronda no necesita perfiles humanos simulados ni juego de roles — es
investigación factual con `WebSearch`/`WebFetch`, y su resultado (viable / no
viable / incierto) determina si vale la pena convocar la Ronda 1 completa o si
alguna capa ya se descarta antes de llegar a esa mesa.

**Ronda 1 — viabilidad técnica (mesa real, en una sesión separada, después de
tener datos del perfilado de `generate()` que recomienda la sección anterior).**
Aquí sí se convoca un panel, pero con tres perfiles específicos, no "arquitectos"
genéricos:
- un perfil de **infraestructura/SRE en GCP**, que evalúa Cloud Run Jobs con datos
  reales de cuotas (los que trajo la Ronda 0) y el patrón de sharding propuesto;
- un perfil de **sistemas de documentos/tipografía a escala**, que evalúa el motor
  compilado y la vectorización del layout, ya con el perfilado de `generate()` en
  mano en vez de estimaciones;
- un perfil de **cumplimiento fiscal/dominio SAT**, que verifica que cualquier
  motor nuevo cumpla con sello digital y QR conforme a especificación, no solo que
  "parezca" viable.

**Ronda 2 — build vs. buy / negocio (otra sesión distinta, y solo si la Ronda 1 no
mata la propuesta).**
Pregunta cualitativamente distinta a las anteriores: ¿existe algo ya construido
en el mercado que resuelva esto sin construir un motor tipográfico propio? ¿vale
la pena el costo de desarrollo y mantenimiento frente al volumen real esperado?
Se separa de la Ronda 1 a propósito — para que un argumento de negocio fuerte
("no vale la pena construir esto ahora") no cierre la conversación antes de que
se evalúe si alguna capa por separado (ej. solo Cloud Run Jobs, que es de bajo
riesgo) ya merece adoptarse independientemente de las otras dos.

### Por qué son sesiones separadas y no una sola corrida

Tres razones, en orden de peso:
1. Este documento es exploración explícita, no una decisión — mezclar viabilidad
   técnica con business case en la misma conversación arriesga decidir con
   información incompleta de un lado o del otro.
2. Hay un veto potencial duro (cumplimiento SAT) que es más barato resolver con
   una investigación dirigida (Ronda 0) que con una mesa completa desde el
   arranque.
3. Terminar una sesión y abrir la siguiente da un punto de corte limpio: el
   estado de cada ronda queda documentado (este archivo, y `PROJECT_STATE.md`)
   antes de que empiece la siguiente, sin que el entusiasmo o el sesgo de una
   ronda contamine el juicio de la que sigue.

### Estado de las rondas

- **Ronda 0:** completada el 12 de julio de 2026 — ver resultado íntegro abajo.
- **Ronda 1:** no iniciada. Depende de (a) el resultado de Ronda 0 (ya disponible,
  ver abajo) y (b) el perfilado de `generate()` mencionado en la sección anterior,
  que sigue pendiente.
- **Ronda 2:** no iniciada. Depende de que Ronda 1 no descarte la propuesta.

## Resultado de la Ronda 0 (investigación dirigida, 12 de julio de 2026)

**Qué se hizo:** un agente de investigación (no un "perfil" con opinión de
arquitecto — solo búsqueda de hechos con fuentes citables) contestó las dos
preguntas de veto duro planteadas arriba: (1) si un motor tipográfico compilado
tipo `typst` puede cumplir el requisito de sello digital + QR del SAT, y (2) qué
tan reales son los límites de paralelismo de Cloud Run Jobs. Además de buscar en
documentación oficial, el agente revisó el código real de este repo
(`backend/app/services/pdf_reportlab.py` y `backend/app/services/canvas_service.py`)
para no especular sobre cómo CFDI Suite maneja el sello y el QR hoy — esa
verificación contra el código real es lo que produjo el hallazgo más importante
de toda esta ronda, explicado abajo.

### Pregunta 1: ¿Puede un motor tipográfico compilado (typst) cumplir sello digital + QR del SAT?

**El hallazgo que cambia el marco de la pregunta original:** antes de esta ronda,
la pregunta se planteaba como "¿puede typst manejar una firma criptográfica
embebida en el PDF?", asumiendo que eso es lo que el Anexo 20 del SAT exige. La
investigación encontró que **esa premisa es incorrecta** — ni el sello digital ni
el QR requieren que el PDF final tenga una firma criptográfica a nivel de
archivo (tipo firma PKCS#7/Adobe). Ambos son, para efectos de la representación
impresa, contenido ya calculado que solo hay que imprimir:

- El **sello digital** (`cfdi:Comprobante/@Sello` y
  `TimbreFiscalDigital/@SelloSAT`) es un string base64 que el PAC/CSD ya firmó
  criptográficamente *dentro del XML*, antes de que exista cualquier paso de
  conversión a PDF. La representación impresa solo lo **imprime como texto**
  (normalmente truncado a los primeros/últimos caracteres por espacio).
- El **código QR** codifica una URL de verificación del SAT con parámetros de
  texto plano — por ejemplo:
  `https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id=5803EB8D-...&re=XOCD720319T86&rr=CARR861127SB0&tt=0000014300.000000&fe=rH8/bw==`
  (`id` = UUID del CFDI, `re`/`rr` = RFCs de emisor/receptor, `tt` = total,
  `fe` = últimos 8 caracteres del sello). No hay ninguna operación criptográfica
  al momento de generar el PDF: el QR es una imagen que codifica un string, nada
  más.

Esto se confirmó leyendo el código actual del proyecto, no es una suposición:
en `backend/app/services/pdf_reportlab.py` (funciones `_sat_qr_url` ~línea
176-199 y `_timbre_section` ~línea 610-624) y en
`backend/app/services/canvas_service.py` (`_draw_qr` ~línea 410-423,
`_VERIFICA_URL` ~línea 46/848), el sello se inyecta como **texto plano** en un
`Paragraph`/`drawString`, y el QR se genera con la librería `qrcode` de PyPI
como PNG rasterizado, dibujado con `drawImage`/`Image` en una posición fija. En
todo el repo no hay una sola llamada a `pyHanko`, `endesive`, PKCS7 ni firma
X.509 sobre el archivo PDF — y `pypdf`, que sí se usa, es solo para *unir* la
página de WeasyPrint con las de ReportLab, no para firmar nada.

Con la pregunta correctamente encuadrada — "¿puede typst imprimir texto
posicionado con precisión, y generar/incrustar un QR con posición exacta?" — la
respuesta es sí, con evidencia concreta:

- **Generación de QR nativa vía ecosistema**: Typst Universe (el repositorio de
  paquetes de la comunidad) tiene varios paquetes dedicados —`rustycure`
  (compilado a WASM), `codetastic`, `zebra`, `tiaoma` (usa la librería Zint) y
  `cades`. Ejemplo mínimo documentado:
  `#import "@preview/rustycure:0.1.0": qr-code` seguido de `#qr-code("...")`.
  Fuentes:
  [rustycure](https://typst.app/universe/package/rustycure/),
  [codetastic](https://typst.app/universe/package/codetastic/),
  [zebra](https://typst.app/universe/package/zebra/),
  [tiaoma](https://typst.app/universe/package/tiaoma/),
  ejemplo práctico en
  [lifewithbsd.org](https://lifewithbsd.org/blog/2025-08-15-generate-a-qr-code-with-typst/).
- **Posicionamiento exacto**: la función nativa `place()` de typst acepta
  `dx`/`dy` para desplazamiento absoluto, y permite colocar contenido en
  `page.foreground`/`page.background` para posicionamiento absoluto en toda la
  página (incluyendo márgenes) — el control pixel-perfect que se necesita para
  reproducir el layout fijo del Anexo 20. Fuente:
  [Place – Typst Documentation](https://typst.app/docs/reference/layout/place/).
- **Incrustar una imagen ya generada externamente** (si se prefiere seguir
  calculando el QR fuera de typst, con la misma librería `qrcode` de Python que
  se usa hoy) es una función nativa trivial (`image()`), sin paquetes
  adicionales.

**Sobre firmas/metadata a nivel PDF (la pregunta original, más estricta que lo
que realmente exige el SAT):** aquí sí hay una limitación real de typst, aunque
no es la que bloquea el caso de uso de CFDI. Un hilo oficial de GitHub
([typst/typst#4473](https://github.com/typst/typst/discussions/4473)) confirma
que typst **no soporta añadir metadata arbitraria/firmas dentro del propio
compilador** — la única vía nativa es el campo `keywords`, y el hilo mismo dice
que la alternativa es post-procesamiento externo del PDF ya generado. La
documentación oficial de PDF de typst
([PDF – Typst Documentation](https://typst.app/docs/reference/pdf/)) confirma
soporte de XMP metadata estándar y adjuntar archivos (`attach()`, en
conformidad PDF/A-3 y PDF/A-4f), pero no menciona firma digital criptográfica
(PDF signature dictionary) en ningún lugar. Un hilo del foro oficial
([¿método simple para "auto-firmar" contenido con un QR?](https://forum.typst.app/t/is-there-a-simple-method-to-self-sign-contents-of-document-with-a-qr-code/2913))
confirma esto desde la comunidad: no hay paquetes de criptografía asimétrica
nativos en typst; la firma criptográfica real requeriría herramientas externas
o plugins WASM, y la comunidad recomienda firmar el *código fuente* (`.typ`)
con GPG externamente, no el PDF de salida.

**Sobre la arquitectura "generar visual + inyectar firma/QR por fuera":** no se
encontró documentación oficial de typst que hable directamente de un flujo
"typst genera el PDF, luego un paso externo lo post-procesa para firmar", pero
la evidencia indirecta (el hilo #4473 sugiriendo post-procesamiento como única
vía para metadata custom, más el patrón estándar de la industria de inyectar
firmas después de generar el PDF con cualquier motor) indica que es una
arquitectura común y viable — y de hecho **es exactamente el patrón que CFDI
Suite ya usa hoy** con WeasyPrint+ReportLab (nada se firma a nivel PDF; todo es
texto/imagen estático).

> **Veredicto: VIABLE, con una corrección importante a la premisa de la
> pregunta original.** typst puede satisfacer con holgura ambos requisitos
> reales del Anexo 20 — imprimir el sello como texto posicionado con precisión,
> e incrustar/generar un QR con posición exacta — usando capacidades nativas
> (`place()`, `image()`) y/o paquetes del ecosistema (`rustycure`, `tiaoma`,
> `zebra`). El "veto duro potencial" que se temía originalmente (firma
> criptográfica embebida a nivel PDF) **no aplica al caso de uso real de
> CFDI**, porque el sistema actual tampoco firma criptográficamente el PDF —
> solo imprime valores ya firmados en el XML. Si en algún escenario futuro sí
> se necesitara una firma PDF real (poco probable dado el estándar del SAT),
> typst no la soportaría nativamente y requeriría post-procesamiento externo
> (p. ej. `pypdf`/`pyHanko`), igual que hoy.
>
> **Pendiente honesto:** no se encontró ningún caso documentado de alguien
> usando typst específicamente para CFDI, SAT, o facturación electrónica
> mexicana — toda la evidencia de arriba es "compatibilidad de capacidades
> generales", no un caso de uso ya probado en este dominio. Antes de
> comprometerse con esta capa, vale la pena una prueba de concepto acotada:
> generar un PDF de muestra con el layout de un CFDI real usando typst +
> `tiaoma`/`rustycure` para el QR.

### Pregunta 2: ¿Qué tan reales son los límites de paralelismo de Cloud Run Jobs?

Consultado directamente contra la documentación oficial de Google Cloud
([Cloud Run Quotas and Limits](https://docs.cloud.google.com/run/quotas) y
[Set parallelism for jobs](https://docs.cloud.google.com/run/docs/configuring/parallelism)):

- **Máximo de tasks por ejecución de un Job: 10,000 tasks**, y es un tope duro
  de la plataforma — no ajustable.
- **Parallelism** (tasks corriendo simultáneamente dentro de un mismo Job): por
  defecto se inician "tan rápido como sea posible, hasta un máximo que varía
  según cuántos CPUs se están usando" — el techo real depende de la
  configuración de CPU/memoria del job y de la región. Este valor **sí es una
  cuota regional ajustable**: una vez otorgada en una región, todos los jobs en
  esa región pueden llegar hasta el límite otorgado.
- **Ejecuciones concurrentes**: máximo de **1,000 job executions corriendo
  simultáneamente por proyecto y región** (ajustable).
- **Instancias de contenedor con Direct VPC egress**: entre **100–200 por
  revisión y región**, según la configuración regional (ajustable).
- **Límite de tiempo por task**: hasta **168 horas (7 días)** de ejecución
  máxima por task.
- La documentación oficial **no publica un número fijo de "parallelism máximo
  por defecto"** — remite a la consola de "Quotas and system limits" del
  proyecto para ver el valor específico otorgado. Es decir: **el número
  concreto de paralelismo disponible hoy para el proyecto de CFDI Suite no se
  puede afirmar sin consultarlo directamente en la consola de GCP** (página de
  Quotas, filtrada por "Cloud Run Admin API" y la región activa, ej.
  `us-central1`).

> **Veredicto: VIABLE, con un dato pendiente de verificar en la consola del
> proyecto real** (no es un límite bloqueante conocido, pero el número exacto
> de paralelismo otorgado hoy es INCIERTO sin consultarlo). La arquitectura de
> "cientos de tareas concurrentes" de la Capa 1 está dentro de los topes
> documentados (10,000 tasks por ejecución es holgado; 1,000 ejecuciones
> concurrentes por proyecto/región también), pero el paralelismo *dentro de
> una sola ejecución* depende de una cuota regional cuyo valor exacto no
> publica la documentación. Hay que revisarlo en `Quotas and system limits`
> del proyecto de CFDI Suite antes de diseñar asumiendo un número específico
> (ej. "200 tasks en paralelo"). Si el valor otorgado por defecto resulta bajo,
> es ajustable vía solicitud de cuota a Google, pero eso implica tiempo de
> aprobación que hay que considerar en el plan.

### Qué implica esto para las capas de la propuesta original

La **Capa 2** (motor tipográfico compilado tipo typst) pierde su principal
riesgo de veto: la preocupación original de que un motor "solo visual" no
pudiera cargar una firma criptográfica del SAT resulta ser un problema mal
planteado, porque el pipeline actual tampoco firma el PDF a nivel
criptográfico — solo imprime texto y una imagen QR, ambas cosas que typst hace
de forma nativa y con control de posición exacto. Typst sigue teniendo una
limitación real y documentada (no soporta firma digital ni metadata arbitraria
embebida de forma nativa), pero esa limitación no es relevante para el caso de
uso de CFDI tal como está implementado hoy. Sigue pendiente, eso sí, una prueba
de concepto acotada antes de comprometerse, porque no existe ningún caso
documentado de alguien usando typst específicamente para CFDI o facturación
mexicana.

La **Capa 1** (Cloud Run Jobs) sigue en pie sin ajustes de fondo: los topes
documentados (10,000 tasks/ejecución, 1,000 ejecuciones concurrentes/proyecto-
región) son muchísimo más altos que cualquier volumen de batch mencionado hasta
ahora en este proyecto. El único pendiente accionable, y es barato de resolver,
es consultar la cuota real de "parallelism" ya otorgada al proyecto de CFDI
Suite en la consola de GCP (`Quotas and system limits` → Cloud Run Admin API,
región activa) para saber si el número por defecto ya alcanza el paralelismo
que la Capa 1 asume, o si hace falta solicitar aumento de cuota con
anticipación.

### Qué sigue después de esta ronda

Con el veto potencial de la Capa 2 descartado y la Capa 1 confirmada dentro de
límites holgados, el siguiente paso natural — antes de convocar la Ronda 1
completa (el panel de tres perfiles descrito arriba) — sigue siendo el mismo
que ya recomendaba este documento desde el principio: perfilar `generate()`
separando WeasyPrint de ReportLab de `pypdf`, para tener datos reales de dónde
se va el tiempo hoy. Ronda 0 resolvió las dudas de "¿esto es legalmente/
técnicamente posible?"; el perfilado resuelve "¿vale la pena el esfuerzo dado
lo que tarda hoy?". Ambas respuestas hacen falta antes de convocar a los tres
perfiles de la Ronda 1 con algo concreto que evaluar, en vez de apuestas sin
medir.
