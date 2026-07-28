# 02 — Presupuestos de recursos ZIP

## Evidencia original

**Hecho verificado:** el procesamiento ZIP descarga y abre el archivo, filtra
`infolist()` y lee XMLs sin presupuesto común para rutas directa, GCS, remota y
worker. La URL firmada actual es PUT y no impone rango de tamaño. El lote real
de referencia es 367 MB.

## Análisis decision-expander

1. **Qué existe realmente / contexto omitido:** hay cuatro caminos ZIP y GCS
   lifecycle; un límite aislado deja otro camino explotable.
2. **Qué parece que se quiere decir / restricciones reales:** preservar el lote
   de 367 MB y proteger memoria, CPU, disco tmpfs y costo. Se fijan 512 MiB
   comprimidos, 2,000 entradas, 20 MB/XML y 2 GiB descomprimidos.
3. **Qué podría estar mal nombrado / supuestos no verificados:** “ZIP válido”
   no implica seguro; el ratio debe medirse con tamaños declarados y datos
   reales, pues metadata ZIP puede ser engañosa.
4. **Capacidades nativas ya existentes:** `ZipInfo` expone tamaños/entradas;
   GCS expone tamaño de blob; POST V4 admite `content-length-range`.
5. **Capacidades con configuración o composición:** un validador de manifiesto
   compartido y política POST V4 detienen el problema antes de descarga.
6. **Límites reales:** no puede asegurarse el costo de descompresión sin leer;
   checks de manifiesto reducen, no eliminan, ZIPs malformados.
7. **Alternativas no obvias:** antivirus/Cloud Run Job aislado; sirven como
   capas futuras, no sustituyen presupuestos deterministas del router.
8. **Riesgos / costo de no explorar:** ZIP bomb y agotamiento de instancia;
   límite menor a 367 MB rompe producción.
9. **Costo de sobreestimar / prueba mínima:** POST policy depende de soporte de
   cliente y firma; probar fixture de 367 MB y límites exactos/ratio 1,027×.
10. **Recomendación:** proceder con presupuesto central y POST V4; no ejecutar
    en esta sesión.

## Implementación

Centralizar manifiesto, cambiar PUT por POST V4 con rango 512 MiB, rechazar blob
GCS sobredimensionado y aplicar los cuatro presupuestos antes de procesar.

## Pruebas

ZIP benigno; ratio 1,027×; >2,000 entradas; XML >20 MB; total >2 GiB; integración
controlada del fixture 367 MB y contrato de campos POST del frontend.

## Rollback

Revertir el commit y restaurar temporalmente PUT; conservar métricas de rechazo
para ajustar límites sin perder compatibilidad.
