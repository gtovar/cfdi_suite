# Modal — Agregar Emisor

> **Slug:** `emisores-modal-add`
> **Componente principal:** `src/components/EmisoresPage.tsx` — función `EmisorModal`
> **Trigger / Ruta:** `modal === 'create'`, activado por `setModal('create')` al hacer clic en "+ Agregar emisor"

![Modal — Agregar Emisor](./emisores-modal-add.png)

---

## Propósito

Formulario para registrar las credenciales Diverza de un nuevo RFC emisor en el sistema. Sin estas credenciales, la funcionalidad de Consultas SAT no puede autenticarse con el PAC para ese RFC. Es el paso de configuración previo obligatorio para el flujo de consulta.

---

## Cómo se llega aquí

1. Navegar a `emisores-view`
2. Hacer clic en el botón "+ Agregar emisor"
3. `setModal('create')` → `EmisoresPage.tsx:322` renderiza `EmisorModal` con `initial={undefined}`

---

## Componentes y Layout

- **Layout principal:** Overlay de pantalla completa (`fixed inset-0 bg-black/50 z-50`) con el modal centrado
- **Modal:** `max-w-md`, fondo blanco, sombra, borde redondeado
- **Campos del formulario:**
  - RFC (requerido) — input de texto, habilitado solo en creación
  - PAC (requerido) — select con opción "Diverza" u otras PACs
  - Credential ID (requerido) — input de texto
  - Token (requerido en creación, opcional en edición) — input tipo password con toggle `showToken`
  - Certificate Number (opcional) — input de texto
- **Botones:** "Guardar" (submit, deshabilitado durante `saving`) y "Cancelar" (`onClose`)

---

## Funcionalidades

1. **Ingresar RFC:** campo requerido, no editable en modo edición (disabled cuando `initial !== undefined`)
2. **Toggle de visibilidad del token:** ícono de ojo en el campo de token — `setShowToken(!showToken)`
3. **Guardar:** `POST /emisores` con los datos del formulario → `setModal(null)` + `refreshEmisores()` si exitoso
4. **Cancelar:** `setModal(null)` sin guardar

---

## Flujo de Navegación

- **← `emisores-view`:** al guardar exitosamente o al cancelar (`setModal(null)`)

---

## Estados

| Estado | Trigger | Diferencia visual |
|--------|---------|-------------------|
| Formulario vacío | Apertura del modal | Todos los campos vacíos, botón "Guardar" habilitado |
| Con validación | Clic en "Guardar" con campos vacíos | Mensajes de error en rojo bajo los campos requeridos vacíos |
| `saving` | POST en curso | Botón "Guardar" deshabilitado y muestra "Guardando…" |
| Error de API | POST falla | Mensaje de error en alerta roja dentro del modal |
| Éxito | POST retorna 200 | Modal se cierra, lista de emisores se actualiza |

---

## Edge Cases

- El RFC ingresado no se valida con formato SAT (no verifica que sea un RFC válido de 12 o 13 caracteres) — se permite guardar cualquier cadena
- Si el token se ingresa como texto plano y el backend no lo encripta, queda expuesto en la base de datos
- Hacer clic fuera del modal no lo cierra (no hay `onClick` en el overlay para `onClose`) — el usuario debe hacer clic explícitamente en "Cancelar"

---

## Preguntas para el Reviewer

1. ¿Debería validar el formato del RFC (regex `^[A-Z&Ñ]{3,4}[0-9]{6}[A-Z0-9]{3}$`) antes de intentar guardar? Actualmente acepta cualquier cadena.
2. ¿Cerrar el modal con clic fuera es el comportamiento esperado, o fue una decisión deliberada mantenerlo solo con el botón "Cancelar"?
3. El campo "Certificate Number" es opcional — ¿cuándo es requerido y cuándo no? La UI no da contexto sobre esto.
4. Si el PAC es "Diverza" siempre, ¿por qué hay un select? ¿Se planea soportar otros PACs próximamente?
