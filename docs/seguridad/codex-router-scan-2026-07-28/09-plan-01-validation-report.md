# 09 — Reporte de validación del Plan 01

Fecha: 2026-07-28. Alcance: propiedad de rutas GCS para ZIPs; no incluye los
planes 02–07.

## Cambio validado

- Se permite exclusivamente `uploads/{uuid-canónico}.zip`.
- La misma validación corre en el endpoint público, Cloud Tasks interno,
  procesador y antes del cleanup destructivo.
- Un valor como `credenciales/default-tenant/emisores.enc` falla con HTTP 400
  antes de crear estado Redis o acceder a `bucket.blob`.

## Evidencia de pruebas

| Capa | Resultado |
|---|---|
| Focal: `backend/tests/test_pdf_batch_ttl.py` | 18 passed, incluidos prefijos prohibidos, ruta válida, payload interno, ZIP corrupto y no acceso/borrado de credenciales. |
| Suite backend: `python3 -m pytest backend/tests -q` | 338 passed, 27 subtests passed. |
| Integridad de diff: `git diff --check` | Sin errores. |

La suite completa inicialmente hizo fallar el guardrail Redis porque su
allowlist está anclada a número de línea. La validación del Plan 01 desplazó
la llamada cosmética existente de 1049 a 1081; se actualizó únicamente la
referencia documentada. La segunda corrida completa pasó.

## Publicación y producción

Los commits locales previstos para publicar son `5e42208`, `bbea26d` y
`15c3be4`, más la actualización de guardrail posterior a este reporte. El
push directo fue bloqueado por la política del entorno antes de salir de la
máquina. Como alternativa, el conector GitHub intentó avanzar `main` con
fast-forward y GitHub respondió 403 `Resource not accessible by integration`.

Por ello **no hubo deploy ni smoke test de producción**. No se simuló el
resultado con tráfico anónimo ni se creó un batch inexistente: ambos habrían
dado evidencia falsa o generado reintentos en Cloud Tasks. Para terminar la
validación en producción queda por ejecutar con un token B-lite disponible de
forma segura: rechazo autenticado de ruta de credenciales y flujo completo de
ZIP sintético propio.

## Revisión final de decision-expander

1. **Qué existe realmente / contexto omitido:** código, pruebas focales y
   suite backend son verdes; `main` remoto sigue sin los commits porque ninguna
   credencial disponible puede escribirlo.
2. **Qué parece que se quiere decir / restricciones reales:** cerrar Plan 01
   exige evidencia del servicio desplegado, no sólo de la lógica local. La
   restricción es de autorización de GitHub y de token B-lite de producción.
3. **Qué podría estar mal nombrado / supuestos no verificados:** “pruebas
   completas” no equivale a “producción validada”; tampoco puede inferirse un
   400 remoto desde el test local.
4. **Capacidades nativas ya existentes:** workflow de GitHub despliega al push
   a `main`; `request-upload` permite generar un objeto sintético aislado.
5. **Capacidades con configuración o composición:** un operador con permisos
   `contents:write` y token B-lite puede publicar y ejecutar el smoke sin
   exponer secretos ni tocar datos reales.
6. **Límites reales:** este entorno no puede empujar ni autenticar los endpoints
   de aplicación; no hay una alternativa segura que convierta eso en una
   prueba de producción.
7. **Alternativas no obvias:** un workflow manual con secreto de test o Cloud
   Shell con acceso a Secret Manager; ambos requieren autoridad externa.
8. **Riesgos / costo de no explorar:** declarar cierre ahora ocultaría que el
   deploy no ocurrió; crear rutas inexistentes para “probar” ensuciaría la cola.
9. **Costo de sobreestimar / prueba mínima:** no afirmar que Cloud Run recibió
   el cambio. La prueba mínima pendiente es push/deploy exitoso y dos requests
   autenticadas: rechazo de credenciales y ZIP sintético válido.
10. **Recomendación:** **no aprobar todavía el cierre del Plan 01**. Aprobar la
    implementación local y sus pruebas; bloquear sólo el hito de producción
    hasta contar con un push autorizado y token de prueba seguro. No avanzar al
    siguiente plan hasta completar esas dos verificaciones o recibir una
    excepción explícita del dueño.

## Actualización: validación en producción completada

El 2026-07-28 se publicó el contenido correcto en `main` y el workflow
`Deploy Backend → Cloud Run` concluyó exitosamente. El intento inicial de
publicación mediante el conector creó blobs inválidos con bytes nulos; la
revisión no pasó el health check ni recibió tráfico. Se corrigió el contenido
UTF-8 mediante la API oficial de GitHub y el deploy correctivo sí completó.

Smoke autenticado, con secreto leído sólo por el proceso y nunca impreso:

| Comprobación | Resultado |
|---|---|
| `GET /api/health` | 200 |
| `POST /start-zip-gcs` con `credenciales/default-tenant/emisores.enc` | 400 |
| `POST /request-upload` | emitió `uploads/{uuid}.zip` canónico |
| PUT de ZIP sintético sin CFDI | 200 |
| `POST /start-zip-gcs` con la ruta sintética | 200 y `batchId` presente |
| Listado posterior de `uploads/` | ningún objeto nuevo de la prueba permaneció |

## Decision-expander — revisión final posterior a producción

1. **Qué existe realmente / contexto omitido:** hay evidencia local completa,
   deploy Cloud Run exitoso y smoke autenticado con datos sintéticos; los ZIPs
   antiguos listados son anteriores a la prueba y no se usaron.
2. **Qué parece que se quiere decir / restricciones reales:** la meta era que
   sólo los ZIPs temporales propios llegaran a procesamiento y cleanup, sin
   bloquear el flujo legítimo.
3. **Qué podría estar mal nombrado / supuestos no verificados:** un 400 no
   demuestra aislamiento multitenant; sólo prueba el contrato de path de
   B-lite, como estaba delimitado desde el Plan 01.
4. **Capacidades nativas ya existentes:** UUID emitido por `request-upload`,
   Cloud Tasks y lifecycle GCS permitieron un smoke sin datos de cliente.
5. **Capacidades con configuración o composición:** endpoint público,
   endpoint interno, procesador y cleanup formaron defensas redundantes y se
   observaron los extremos público válido/prohibido en el servicio real.
6. **Límites reales:** no se probó ni se promete ownership por usuario;
   capability tokens y presupuestos ZIP permanecen en planes posteriores.
7. **Alternativas no obvias:** el smoke con ruta inexistente fue descartado
   correctamente porque habría generado reintentos; el ZIP sintético dio
   evidencia superior y limpia.
8. **Riesgos / costo de no explorar:** la publicación por API mostró un riesgo
   operativo real (codificación); se detectó mediante health check y se corrigió
   antes de dirigir tráfico a una revisión no saludable.
9. **Costo de sobreestimar / prueba mínima:** no se infiere éxito sólo de CI;
   se requieren exactamente deploy verde, rechazo autenticado y flujo válido,
   los tres ahora observados.
10. **Recomendación:** **aprobar el Plan 01**. La implementación y el borde de
    producción están validados. Puede iniciarse el Plan 05, según el orden
    fijado originalmente después de Plan 01.
