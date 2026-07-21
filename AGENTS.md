## Wiki Knowledge Base
Path: ~/Users/gil/Documents/claude-obsidian

When you need context not already in this project:
1. Read wiki/hot.md first (recent context cache)
2. If not enough, read wiki/index.md
3. If you need domain details, read the relevant domain sub-index
4. Only then drill into specific wiki pages

Do NOT read the wiki for general coding questions or tasks unrelated to [domain].

## Política de hallazgos preexistentes

Si durante una tarea encuentras algo roto que NO es de tu cambio (test que ya
fallaba, error de lint previo, warning de react-doctor viejo):

1. **Prohibido descartarlo en silencio.** Decir "es preexistente" sin dejar
   rastro escrito no es aceptable.
2. Anótalo en `PROJECT_STATE.md §Hallazgos preexistentes` con evidencia
   verificable de que es preexistente (p. ej. `git stash` y reproducir el
   fallo sin tus cambios).
3. Si el hallazgo es de react-doctor, regístralo/referéncialo además en
   `docs/react-doctor-veredictos.md` (la fuente de verdad de esos veredictos).
4. No lo arregles dentro de tu tarea salvo que el usuario lo pida — anotarlo
   es obligatorio, arreglarlo es decisión aparte.

Para verificar si un hallazgo de react-doctor es tuyo o preexistente:
`npx react-doctor --scope changed` (desde `frontend/`) reporta solo lo
introducido contra la rama base.

## Política de código aparentemente sin uso

**Nunca borres código "muerto" (archivos, exports, dependencias, métodos sin
referencias) sin investigación de propósito Y confirmación explícita del
usuario.** Ya ocurrió que código "sin uso" a punto de borrarse resultó ser
exactamente lo que una feature posterior necesitaba. Flujo obligatorio:
investigar (`git log`, imports históricos, features en desarrollo, imports
dinámicos/workers) → clasificar con evidencia → proponer al usuario → borrar
solo con su confirmación. Detalle en `docs/react-doctor-veredictos.md`
§Política de código no usado.

