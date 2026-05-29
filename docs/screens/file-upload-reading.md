# FileUpload — Leyendo Archivo

> **Slug:** `file-upload-reading`
> **Componente principal:** `src/components/FileUpload.tsx`
> **Trigger / Ruta:** `phase === 'reading'` — activado por `handleFile(file)` cuando `reader.readAsText(file)` está en curso

> **Sin screenshot:** estado transient de muy corta duración (depende del tamaño del XML y la velocidad de lectura del FileReader — típicamente <500ms para archivos <1MB).

---

## Propósito

Estado intermedio que muestra al usuario que el archivo fue aceptado y está siendo leído localmente (antes de enviarlo al backend). Proporciona feedback de progreso real via `FileReader.onprogress`.

---

## Cómo se llega aquí

1. `inspector-empty` — usuario selecciona o arrastra un `.xml`
2. `handleFile(file)` ejecuta: `setIsLoading(true)`, `setPhase('reading')`, `reader.readAsText(file)`
3. `reader.onprogress` actualiza `progress` (0-100%)
4. Al completarse: `reader.onload` → `setPhase('analyzing')`

---

## Componentes y Layout

- **Zona de upload:** misma área del drop zone, pero contenido reemplazado por el estado de loading
- **Layout del estado loading:**
  - Ícono `FileText` en círculo azul (no el ícono de upload del estado idle)
  - Nombre del archivo seleccionado
  - Barra de progreso azul con `%` calculado de `FileReader.onprogress`
  - Texto: `Modo de carga: Lectura local`

---

## Funcionalidades

- No hay acciones disponibles — el drop zone tiene `onClick` que chequea `!isLoading` antes de abrir el selector. Durante `reading`, no se puede seleccionar otro archivo.

---

## Flujo de Navegación

- **→ `file-upload-analyzing`:** automáticamente cuando `reader.onload` se dispara

---

## Estados

| Estado | Trigger | Diferencia visual |
|--------|---------|-------------------|
| Inicio de lectura | `phase === 'reading'`, `progress === 0` | Barra de progreso al 0% |
| En progreso | `reader.onprogress` events | Barra de progreso avanzando (solo visible para archivos grandes con `e.lengthComputable`) |
| Fin de lectura | `progress === 100` | Antes de transicionar a `analyzing` |

---

## Edge Cases

- Para archivos pequeños (<100KB), `onprogress` puede no dispararse en absoluto — el progreso salta directamente a 100% o el estado `reading` dura <50ms y es imperceptible
- Si `e.lengthComputable === false` (posible en algunos browsers o circunstancias), la barra no avanza aunque el archivo se esté leyendo
- Si el usuario cierra el browser durante la lectura, no hay recuperación posible

---

## Preguntas para el Reviewer

1. ¿Este estado es suficientemente visible para el usuario, dado que dura tan poco tiempo? ¿O hay riesgo de que el usuario haga clic varias veces pensando que no pasó nada?
2. ¿El texto "Modo de carga: Lectura local" agrega valor al usuario final, o es demasiado técnico?
