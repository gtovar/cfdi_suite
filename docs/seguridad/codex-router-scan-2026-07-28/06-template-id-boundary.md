# 06 — Borde de `template_id`

## Evidencia original

**Hecho verificado:** `routers/templates.py` ya valida IDs con regex, pero los
flujos PDF toman `_id` de JSON/form-data y tareas internas antes de componer
rutas de templates en servicios.

## Análisis decision-expander

1. **Qué existe realmente / contexto omitido:** existen dos límites: API de
   templates y consumidores PDF/Cloud Tasks; validar sólo el primero deja
   entradas indirectas.
2. **Qué parece que se quiere decir / restricciones reales:** reutilizar la
   regla existente, bloqueando traversal sin cambiar el fallback de template
   válido inexistente.
3. **Qué podría estar mal nombrado / supuestos no verificados:** “interno” no
   significa confiable si el payload fue construido desde request; URL-decoding
   puede introducir separadores.
4. **Capacidades nativas ya existentes:** regex actual y validación Pydantic/
   funciones compartidas.
5. **Capacidades con configuración o composición:** módulo neutral de validador,
   chequeado antes de encolar y antes de cargar.
6. **Límites reales:** regex no confirma existencia ni autorización de template,
   intencionalmente preserva fallback.
7. **Alternativas no obvias:** usar UUID de template o registro en DB; sobrediseño
   para el objetivo de traversal actual.
8. **Riesgos / costo de no explorar:** lectura/escritura de rutas arbitrarias;
   validar existencia rompe personalización/fallback.
9. **Costo de sobreestimar / prueba mínima:** no asumir que la regex acepta todos
   IDs actuales; probar IDs personalizados y ataques codificados.
10. **Recomendación:** proceder como hardening con validador compartido; pendiente.

## Implementación

Extraer/reusar regex en capa común y validarla en JSON, form-data, encolado y
worker antes de cargar archivos.

## Pruebas

`../default`, barras, absoluto, URL encoding y IDs válidos personalizados;
template válido inexistente mantiene fallback.

## Rollback

Revertir el commit dedicado; no hay migración de IDs.
