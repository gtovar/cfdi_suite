# 03 — Presupuestos multipart y memoria

## Evidencia original

**Hecho verificado:** rutas multipart permiten que Starlette reciba/parsee el
cuerpo y algunos flujos leen archivos completos o concurrentemente. Eso permite
que un request sin `Content-Length` eluda una comprobación sólo de header.

## Análisis decision-expander

1. **Qué existe realmente / contexto omitido:** el límite debe ocurrir antes de
   parsear multipart y contemplar body agregado, no sólo cada `UploadFile`.
2. **Qué parece que se quiere decir / restricciones reales:** limitar a 100 MB
   lotes, 50 MB XML-PDF, 10 MB XLSX y 5 MB FIEL sin romper flujos válidos.
3. **Qué podría estar mal nombrado / supuestos no verificados:** archivos
   temporales no eliminan consumo: el filesystem de Cloud Run es tmpfs.
4. **Capacidades nativas ya existentes:** ASGI expone eventos `receive`; lecturas
   por chunks permiten contador individual y agregado.
5. **Capacidades con configuración o composición:** middleware por ruta más
   lector streaming protege header y streams sin header.
6. **Límites reales:** Starlette ya puede haber reservado overhead multipart;
   un middleware minimiza pero no cambia límites del proxy previo.
7. **Alternativas no obvias:** subida directa a GCS para todos los tipos; no
   cubre validación ni los flujos de archivos pequeños existentes.
8. **Riesgos / costo de no explorar:** OOM y concurrencia materializando lotes;
   límite demasiado uniforme rompe XML PDF de 50 MB.
9. **Costo de sobreestimar / prueba mínima:** no confiar sólo en Content-Length;
   probar stream sin header y suma de lote.
10. **Recomendación:** proceder con middleware ASGI y chunks; pendiente.

## Implementación

Middleware de bytes por ruta antes del parseo, contadores en chunk y eliminación
de `asyncio.gather()` que materialice lotes completos.

## Pruebas

Headers y streams sin header, agregado 100 MB, límites por endpoint, rechazo
temprano y equivalencia funcional para archivos válidos.

## Rollback

Revertir middleware y lectores en el commit dedicado; conservar códigos 413 y
métricas para diagnosticar falsos positivos.
