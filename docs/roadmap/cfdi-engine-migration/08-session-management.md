# 08. Session Management

## Propósito

Evitar degradación de conversación y pérdida de contexto durante esta migración.  
La regla ya no es solo "cuándo cerrar sesión", sino **verificar explícitamente si conviene iniciar una nueva sesión** antes de seguir una unidad de trabajo relevante.

## Estado actual

La fase 07 ya quedó cerrada:
- `current-ts` quedó ratificado como dueño operativo del producto
- `python-satcfdi` quedó congelado como benchmark y referencia de dominio
- el cleanup legacy de `analyzeCFDI` ya fue ejecutado

La fase 08 queda activa para institucionalizar una disciplina simple:
- antes de continuar trabajo importante, verificar si corresponde nueva sesión
- después de cada hito verificable, volver a verificar
- no depender de memoria conversacional para retomar

## Regla operativa

Antes de continuar una unidad de trabajo relevante, hacer esta pregunta:

**¿Conviene iniciar nueva sesión?**

Si se cumple una o más condiciones de las siguientes, la respuesta por default es **sí**.

Si no se cumple ninguna, se puede continuar en la sesión actual.

## Checklist de nueva sesión

### 1. Cambio de fase
Si la siguiente acción ya pertenece a otra fase del roadmap, abrir nueva sesión.

Ejemplos:
- de contrato a benchmark
- de benchmark a adaptador Python
- de benchmark comparativo a decisión de motor
- de migración/retiro a disciplina operativa

### 2. Cambio de preocupación principal
Si la conversación pasa de una preocupación a otra distinta, abrir nueva sesión.

Ejemplos:
- de tipos/interfaces a corpus/fixtures
- de corpus a integración Python
- de integración a migración/retiro
- de cleanup técnico a reglas operativas del repo

### 3. Demasiadas superficies activas
Si para continuar correctamente ya hay que tener abiertas al mismo tiempo:
- más de 3 documentos del roadmap
- o más de 6 archivos de implementación relevantes
- o decisiones pendientes mezcladas entre producto, contrato, benchmark y operación

entonces conviene abrir nueva sesión.

### 4. Hito verificable ya cerrado
Si ya se cerró un hito con código o documentación verificable, conviene cortar y reevaluar.

Ejemplos:
- contrato formal cerrado y tests pasando
- corpus inicial creado
- benchmark `current-ts` corriendo
- adaptador Python inicial corriendo
- cierre formal de fase 07 y cleanup legacy aplicado

### 5. Dependencias externas o runtime distinto
Si la siguiente unidad depende de Python, procesos externos, fixtures nuevos o entorno adicional, conviene arrancarla en sesión limpia.

### 6. Cambio de tipo de tarea
Si el trabajo pasa de exploración a implementación, o de implementación a una nueva decisión, abrir nueva sesión.

Esto aplica incluso si el tema parece relacionado: el cambio de tipo de tarea ya es suficiente para separar el flujo.

## Tamaño recomendado de sesión

Para este roadmap, la unidad correcta de sesión no es "número de mensajes" sino:
- **1 fase pequeña completa**, o
- **1 subfase técnica cerrada con validación**, o
- **1 decisión cerrada con documentación actualizada**

No conviene mezclar más de una de esas unidades en una sola sesión salvo que la segunda sea muy corta y puramente mecánica.

## Cuándo seguir en la misma sesión

Se puede continuar en la misma sesión si:
- la preocupación principal no cambió
- la siguiente acción sigue dentro de la misma unidad técnica
- `STATUS.md` sigue siendo suficiente para rehidratar el estado
- no hace falta abrir muchas superficies nuevas
- no acabamos de cerrar un hito que ya merezca corte natural

Ejemplo típico:
- una corrección pequeña de documentación o pruebas dentro de la misma unidad ya abierta

## Cuándo conviene abrir nueva sesión ahora

Se debe preferir nueva sesión cuando:
- la próxima acción ya está identificada
- `STATUS.md` está al día
- la documentación del roadmap refleja el estado real
- los cambios importantes tienen tests o validación mínima
- y la continuación ya pertenece a otra unidad natural

## Estado operativo de esta fase

### Ya quedó cubierto
- fase 07 cerrada
- capability map validado
- `python-satcfdi` congelado como benchmark
- cleanup legacy ejecutado
- `STATUS.md` actualizado para apuntar a fase 08

### Próxima unidad natural
- usar esta regla de sesión como gate activo del repo
- mantener `STATUS.md` y el roadmap sincronizados al cerrar cada hito posterior
- rehidratar desde `STATUS.md` antes de retomar cualquier trabajo nuevo relevante

Conclusión actual:
- **sí conviene verificar nueva sesión antes de cada unidad relevante**
- para el estado actual del roadmap, una nueva sesión suele ser preferible cuando el siguiente trabajo ya no sea solo ajuste documental de fase 08

## Rehidratación de contexto

Para retomar sin depender de la conversación anterior, abrir en este orden:

1. `docs/roadmap/cfdi-engine-migration/STATUS.md`
2. `docs/roadmap/cfdi-engine-migration/index.md`
3. `docs/roadmap/cfdi-engine-migration/08-session-management.md`
4. si hace falta contexto adicional:
   - `docs/roadmap/cfdi-engine-migration/07-migration-and-retirement.md`
   - `docs/analysis/2026-04-17-python-satcfdi-decision.md`

## Nota sobre runtime Python

El benchmark actual ya usa `.venv-satcfdi/` local cuando existe.  
No hace falta volver a clonar nada en `/tmp` para rehidratar el trabajo actual.

Si el entorno local se pierde, basta con reconstruir el virtualenv y reinstalar `satcfdi` antes de retomar el benchmark Python.

## Regla de continuidad

Nada importante de esta migración debe vivir solo en la conversación.  
Si una sesión produce una decisión, un criterio o un siguiente paso, debe quedar reflejado en:
- el roadmap,
- `STATUS.md`,
- o documentación de análisis.

## Criterio de salida

La gestión de sesión se considera suficiente si cualquier sesión nueva puede retomar el trabajo leyendo primero `STATUS.md`, luego `index.md`, y después solo el documento temático de la unidad en curso.
