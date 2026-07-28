# 08 — Puerta de validación en producción del Plan 01

## Propuesta evaluada

Después de desplegar el Plan 01, comprobar en producción que un `gcsPath` de
credenciales sea rechazado con 400 y que una ruta legítima `uploads/{uuid}.zip`
mantenga el flujo de subida/encolado, sin tocar datos de clientes.

## Decision-expander (preautorización)

1. **Qué existe realmente / contexto omitido:** el push a `main` despliega
   `backend/**` a Cloud Run. La API tiene Bearer B-lite; el cliente de pruebas
   necesita una vía autorizada sin exponer el secreto en logs.
2. **Qué parece que se quiere decir / restricciones reales:** validar el efecto
   en el servicio real, incluida la configuración de deploy, con datos propios.
   No está autorizado usar credenciales, ZIPs o batches de clientes.
3. **Qué podría estar mal nombrado / supuestos no verificados:** un 400 al
   endpoint no prueba que Cloud Tasks/GCS funcionen; encolar un UUID inexistente
   podría producir reintentos y ruido operativo.
4. **Capacidades nativas ya existentes:** `request-upload` emite un UUID y URL
   firmada; un ZIP sintético mínimo puede subirse directo a GCS y el backend lo
   elimina al terminar. GitHub Actions expone estado del deploy.
5. **Capacidades con configuración o composición:** se puede encadenar URL
   firmada -> ZIP sintético -> `start-zip-gcs` -> consulta de estado, usando una
   credencial de prueba autorizada sin imprimirla.
6. **Límites reales:** sin token B-lite disponible para el operador no es posible
   invocar las rutas protegidas; tampoco se debe inferir que 401 sea éxito del
   fix de path.
7. **Alternativas no obvias:** smoke autenticado desde Cloud Shell/secret manager
   o una prueba manual del dueño; son equivalentes si el entorno local no tiene
   el secreto. No se debe crear una ruta anónima de diagnóstico.
8. **Riesgos / costo de no explorar:** desplegar sin smoke deja incierta la
   propagación; iniciar un batch inexistente ensucia Cloud Tasks y logs.
9. **Costo de sobreestimar / prueba mínima:** no afirmar encolado sólo por 200.
   El mínimo es una petición autenticada que rechace la ruta prohibida, y una
   subida de ZIP sintético que llegue a estado de extracción sin error.
10. **Recomendación:** **aprobar condicionalmente** el deploy y smoke. Primero
    verificar el workflow; después usar sólo un token de prueba disponible de
    forma segura. Si no existe, detenerse tras validar el deploy y pedir al
    dueño ejecutar los dos `curl` autenticados, sin sustituirlo por tráfico
    anónimo ni un batch inexistente.

## Límites operativos fijados

- Rechazo: `credenciales/default-tenant/emisores.enc`, sin crear tarea.
- Camino válido: ZIP nuevo, mínimo y sintético obtenido mediante
  `request-upload`; nunca una ruta o archivo preexistente.
- No registrar Authorization, URL firmada completa ni datos de CFDI.
- Reportar por separado deploy, rechazo, aceptación y estado final.
