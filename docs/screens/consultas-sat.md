# Consultas SAT — Inicial

> **Slug:** `consultas-sat`
> **Componente principal:** `src/components/ConsultasSATPage.tsx`
> **Trigger / Ruta:** Clic en "Consultas SAT" en `AppSidebar` → `setActiveView('consultas-sat')`

![Consultas SAT — Inicial](./consultas-sat.png)

---

## Propósito

Módulo de consulta batch del estado de CFDIs en el SAT vía Diverza. El usuario carga un archivo `.xlsx` con una lista de UUIDs y RFC emisor/receptor, y el sistema consulta la vigencia y cancelabilidad de cada CFDI. Esta pantalla muestra el estado vacío (idle) con la zona de carga y la referencia del formato de columnas esperado.

---

## Cómo se llega aquí

- Clic en "Consultas SAT" en el sidebar lateral (disponible desde cualquier vista).

---

## Componentes y Layout

- **Layout principal:** columna centrada `max-w-2xl`, scroll vertical, fondo `bg-gray-50`
- **Encabezado de página:** "Consultas SAT" + subtítulo "Vigencia y cancelabilidad de CFDIs vía Diverza"
- **Card "Batch — Excel":** drop-zone para `.xlsx` con borde punteado
- **Acciones:** botón "Iniciar consulta" (disabled mientras no haya archivo)
- **Card "Formato de entrada":** tabla de referencia con las 5 columnas requeridas del Excel

---

## Funcionalidades

1. **Seleccionar archivo:** arrastrar o clic en la drop-zone → `setFile(selected)` (no inicia la consulta automáticamente)
2. **Iniciar consulta:** botón "Iniciar consulta" (habilitado solo si `file !== null`) → `handleStart()`
3. Navegar a otras vistas desde el sidebar sin perder el archivo seleccionado (pero si el componente se desmonta, el estado se pierde)

---

## Flujo de Navegación

- **← Origen:** cualquier vista, clic en sidebar
- **→ `consultas-sat-file-ready`:** al seleccionar un archivo `.xlsx`
- **→ `consultas-sat-processing`:** clic en "Iniciar consulta" con archivo válido

---

## Estados

| Estado | Trigger | Diferencia visual |
|--------|---------|-------------------|
| `idle` sin archivo | Por defecto al entrar | Drop-zone con borde gris, botón "Iniciar consulta" disabled |
| `idle` con archivo | Tras `handleFileDrop` o `handleFileSelect` | Drop-zone resalta archivo (borde primary, ver `consultas-sat-file-ready`) |

---

## Edge Cases

- El drop-zone solo acepta `.xlsx` (`dropped?.name.endsWith('.xlsx')`), pero el `input[accept=".xlsx"]` no valida el contenido real del archivo.
- Si el usuario navega a otra vista con `activeView`, `ConsultasSATPage` se desmonta y `file` se pierde (React state no persiste entre desmontajes).
- La tabla de formato de entrada es informativa/estática — no hay validación de columnas antes de iniciar la consulta.

---

## Preguntas para el Reviewer

1. ¿Debería la app recordar el archivo entre navegaciones (ej. usando `useRef` o contexto global)?
2. La tabla de formato es estática en el componente — ¿debería cargarse desde el backend o de una fuente de configuración para mantenerse sincronizada con los cambios del PAC?
3. ¿Por qué el input acepta `.xlsx` pero el drop-zone solo valida la extensión del nombre, sin verificar el MIME type?
