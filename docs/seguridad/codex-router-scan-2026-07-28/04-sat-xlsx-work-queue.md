# 04 — XLSX/SAT: filas y cola de trabajo

## Evidencia original

**Hecho verificado:** el flujo SAT lee XLSX en modo lectura pero puede formar
una tarea por fila y disparar consultas externas sin techo de filas ni de
concurrencia.

## Análisis decision-expander

1. **Qué existe realmente / contexto omitido:** `read_only=True` reduce RAM,
   no limita trabajo, objetos ni peticiones a Diverza.
2. **Qué parece que se quiere decir / restricciones reales:** admitir hasta 500
   UUIDs y como máximo 20 workers preservando resultados y SSE.
3. **Qué podría estar mal nombrado / supuestos no verificados:** limitar tareas
   no basta si el parser sigue recorriendo millones de filas; debe detenerse al
   501.º UUID válido.
4. **Capacidades nativas ya existentes:** iteración streaming de openpyxl y
   `asyncio.Queue`/workers ofrecen backpressure.
5. **Capacidades con configuración o composición:** cola acotada conserva orden
   indexando resultados sin crear una lista enorme.
6. **Límites reales:** no se puede garantizar disponibilidad de Diverza; se
   conservan tres reintentos actuales.
7. **Alternativas no obvias:** Cloud Tasks por UUID o procesamiento offline;
   añaden latencia y no sustituyen el límite de entrada.
8. **Riesgos / costo de no explorar:** XLSX hostil causa miles de tareas y costo
   externo; límite estricto puede requerir UX de división de archivo.
9. **Costo de sobreestimar / prueba mínima:** 20 workers no implica 20 conexiones
   si reintentos internos multiplican llamadas; instrumentar concurrencia.
10. **Recomendación:** proceder; devolver 413 antes de Diverza si hay 501 UUIDs.

## Cierre (2026-07-28)

**CERRADO por Decision Expander, tras segunda ronda.** El parser conserva
`read_only=True`, rechaza el UUID válido 501 con 413 y el lote usa un pool de
20 workers con colas acotadas. Los resultados siguen indexados y los eventos
SSE mantienen su contrato.

Evidencia: 36 pruebas focalizadas y 93 pruebas conjuntas pasan. La prueba
end-to-end de POST multipart con 501 UUIDs verifica 413 y
`httpx.AsyncClient.put.assert_not_called()`: no empieza ninguna consulta a
Diverza después del rechazo.

## Implementación

Detener al exceder 500 UUIDs válidos y usar cola con 20 workers, resultados
ordenados y eventos SSE intactos.

## Pruebas

500/501 filas, inválidas, techo de concurrencia y cero llamada externa tras 413.

## Rollback

Revertir el commit dedicado; documentar el límite para soporte antes de ampliar.
