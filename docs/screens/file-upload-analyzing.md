# FileUpload — Analizando CFDI

> **Slug:** `file-upload-analyzing`
> **Componente principal:** `src/components/FileUpload.tsx`, `src/app/hooks/useCfdiAnalysis.ts`
> **Trigger / Ruta:** `phase === 'analyzing'` — activado cuando `reader.onload` completa y `onFileSelect(content)` (análisis backend) está en curso

> **Sin screenshot:** estado transient — dura mientras el backend procesa el XML (típicamente 200ms–2s).

---

## Propósito

Estado de análisis: el XML fue leído y se está enviando al backend para análisis completo (extracción de conceptos, cálculo de traslados, detección de discrepancias). Es el estado más informativo del flujo de carga — muestra el progreso del análisis con etiquetas y porcentajes del backend.

---

## Cómo se llega aquí

Inmediatamente después de `file-upload-reading`, cuando `reader.onload` dispara:
1. `setPhase('analyzing')` en `FileUpload.tsx`
2. `await Promise.resolve(onFileSelect(content))` — esto ejecuta `analyzeCFDI(xml, progressCallback)`
3. El callback de progreso llama `setAnalysisStageLabel`, `setAnalysisStageProgress`, `setAnalysisStageDetail` en `App.tsx`
4. Estos valores se pasan como props a `FileUpload`: `analysisLabel`, `analysisProgress`, `analysisDetail`

---

## Componentes y Layout

- **Ícono:** `LoaderCircle` rotando (spinner azul)
- **Barra de progreso:** avanza según `analysisProgress` (0-100%, vía callback del backend)
- **Grid de detalle:**
  - "Filas detectadas" → `analysisDetail` (count de filas)
  - "Progreso actual" → `analysisLabel` (ej. "Leyendo conceptos", "Calculando traslados")
- **Nota:** la barra de progreso del análisis viene del backend via callbacks — no del FileReader

---

## Funcionalidades

- No hay acciones disponibles durante el análisis. El botón de clic está bloqueado por `!isLoading`.

---

## Flujo de Navegación

- **→ `inspector-ingreso` / `inspector-pagos`:** al completar el análisis (`setIsLoading(false)`, `setPhase('idle')`, `setCfdi(result.cfdi)`)
- **→ `inspector-empty`:** si el análisis falla (error fatal del backend → `alert()` + sin setState de cfdi)

---

## Estados

| Estado | Trigger | Diferencia visual |
|--------|---------|-------------------|
| Inicio | `phase === 'analyzing'`, `analysisProgress === 0` | Spinner, barra al 0%, label inicial "Analizando estructura CFDI" |
| En progreso | Callbacks del backend | Barra avanzando, label cambiando (ej. "Leyendo conceptos"), detail con count de filas |
| Casi completo | `analysisProgress === 100` | Barra completa, antes de la transición al inspector cargado |

---

## Edge Cases

- Si el backend no responde, este estado dura indefinidamente — no hay timeout implementado en el frontend (`analyzeCFDI` no tiene AbortController ni timeout)
- El `if (elapsed < 450) await sleep(450 - elapsed)` en `FileUpload.tsx:49` garantiza que el estado `analyzing` dure al menos 450ms, incluso si el backend responde en 10ms — para que la UI no haga flash
- Si el CFDI es un `.xml` válido pero no es un CFDI (ej. un XML cualquiera), el backend puede retornar un error fatal — el estado `analyzing` termina con el `alert()` de error y regresa a `idle`

---

## Preguntas para el Reviewer

1. ¿El delay mínimo de 450ms es la cantidad correcta? ¿Debería ser más largo (para sensación de procesamiento) o más corto (para velocidad percibida)?
2. ¿Hay algún plan para agregar un timeout al análisis backend? Actualmente el usuario puede quedar atrapado esperando indefinidamente.
3. ¿El label de "Progreso actual" con etapas del backend es suficiente contexto para el usuario, o sería mejor un mensaje más amigable como "Verificando montos..."?
