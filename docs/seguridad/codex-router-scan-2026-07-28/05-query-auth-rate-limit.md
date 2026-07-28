# 05 — Token por query y rate limit

## Evidencia original

**Hecho verificado:** `verify_user_identity` acepta `?token=` para cualquier
método; la identidad se vuelve `default-tenant`, mientras limitadores pueden
derivar clave de `Authorization`, ausente en EventSource/query.

## Análisis decision-expander

1. **Qué existe realmente / contexto omitido:** EventSource necesita query por
   no poder fijar Authorization; POST no comparte esa limitación.
2. **Qué parece que se quiere decir / restricciones reales:** mantener GET SSE/
   descargas explícitamente permitidos, y contar por identidad ya validada.
3. **Qué podría estar mal nombrado / supuestos no verificados:** presencia de
   header no es identidad; query token se filtra por logs/referrer si no se
   controla cache/referrer.
4. **Capacidades nativas ya existentes:** `request.state`, método/path y headers
   de respuesta permiten extraer una vez, limitar y mitigar exposición.
5. **Capacidades con configuración o composición:** fingerprint hash del secreto
   en estado, allowlist de rutas y headers anti-cache/referrer.
6. **Límites reales:** token fijo no distingue usuarios; sólo limita el grupo
   B-lite, no reemplaza auth multitenant.
7. **Alternativas no obvias:** cookie HttpOnly o SSE proxy autenticado; cambian
   cliente y no son necesarios para el contrato actual.
8. **Riesgos / costo de no explorar:** bypass de limitador y token en URLs;
   bloquear todo query rompe EventSource.
9. **Costo de sobreestimar / prueba mínima:** hashing no evita filtración de URL;
   probar 4 requests con límite 2, SSE permitido y POST query 401.
10. **Recomendación:** proceder con estado/fingerprint y allowlist GET; pendiente.

## Implementación

Extraer token una vez, guardar identidad y huella; limiter sólo usa estado;
restringir query a GET permitido y agregar headers adecuados.

## Pruebas

Límite dos → 429 en cuatro query requests; SSE conserva autenticación; POST
query devuelve 401.

## Rollback

Revertir el commit, conservando telemetría de rutas query para resolver clientes
no inventariados antes de relajar la allowlist.
