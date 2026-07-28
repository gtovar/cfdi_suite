# 01 — Propiedad de rutas GCS

## Evidencia original

**Hecho verificado:** `ProcessGcsZipPayload.gcsPath` llega sin restricción a
`/api/cfdi/pdf/start-zip-gcs` y se envía a Cloud Tasks. `internal_extract_zip`
lo pasa a `process_zip_in_background`; éste construye `bucket.blob(gcs_path)` y
su `finally` llama `blob.delete()` (`backend/app/routers/pdf.py`). Por tanto un
cliente podía pedir procesar y borrar objetos ajenos del mismo bucket, como
`credenciales/default-tenant/emisores.enc`.

## Análisis decision-expander

1. **Qué existe realmente / contexto omitido:** existe un productor legítimo,
   `request-upload`, que genera exclusivamente `uploads/{uuid4}.zip`; el
   consumidor público e interno no vinculaban esa forma a su contrato.
2. **Qué parece que se quiere decir / restricciones reales:** se busca ligar la
   capacidad de procesar y limpiar al objeto de subida temporal; B-lite es
   single-tenant y no requiere aún un capability token adicional.
3. **Qué podría estar mal nombrado / supuestos no verificados:** `gcsPath` no
   es una referencia segura por ser “interna”; Cloud Tasks autentica el salto,
   pero conserva datos de origen público. No se asume que todos los objetos
   `uploads/` sean seguros: se exige UUID canónico y `.zip`.
4. **Capacidades nativas ya existentes:** `uuid.uuid4()` ya crea la forma que
   se permitirá; FastAPI permite rechazar antes de Redis y GCS.
5. **Capacidades con configuración o composición:** una validación pura común,
   aplicada en endpoint público, endpoint interno, procesador y cleanup, crea
   defensa en profundidad sin cambiar Cloud Tasks.
6. **Límites reales:** el patrón no prueba propiedad por usuario; en B-lite no
   hay identidad por tenant. Tampoco limita tamaño o contenido del ZIP (Plan 02).
7. **Alternativas no obvias:** token de capacidad por objeto, metadata firmada o
   bucket dedicado. Son mejores para multitenancy, pero añaden estado y no
   resuelven el defecto inmediato mejor que el prefijo contractual.
8. **Riesgos / costo de no explorar:** permitir rutas arbitrarias habilita
   borrado de credenciales y datos; introducir capability token ahora duplica la
   futura capa de identidad y puede romper subidas existentes.
9. **Costo de sobreestimar / prueba mínima:** no prometer aislamiento de tenant.
   Probar UUID legítimo, prefijos y traversal rechazados, y demostrar que una
   ruta de credenciales no llega a `bucket.blob(...).delete()`.
10. **Recomendación:** proceder con allowlist `uploads/{UUID}.zip`, revalidada
    en cada frontera y justo antes de borrar; no añadir capability token aún.

## Implementación

- Centralizar el predicado/validador en `routers/pdf.py`.
- Validar antes de crear estado o encolar en `start-zip-gcs`, y al recibir la
  tarea en `internal/extract-zip`.
- Validar defensivamente al inicio de `process_zip_in_background` y antes de
  `blob.delete()`; ninguna ruta fuera de `uploads/` se limpia.

## Pruebas

- Aceptar `uploads/<uuid-canónico>.zip`.
- Rechazar prefijos ajenos, traversal, extensión distinta y UUID no canónico.
- Verificar endpoint público e interno; ante ZIP inválido, la ruta legítima
  sigue la semántica actual.
- Simular `credenciales/default-tenant/emisores.enc` y afirmar que no se invoca
  `blob()` ni `delete()`.

## Rollback

Revertir solamente el commit del Plan 01 restablece el contrato anterior. No
hay migración ni datos persistentes; antes de hacerlo se debe confirmar que no
existan clientes legítimos que dependan de rutas no generadas por
`request-upload`.
