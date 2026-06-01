# Features de CFDI Suite — Inspector

> Índice de capacidades activas de la app. Actualizar cuando se agrega o cambia un feature.
> Para decisiones de arquitectura ver `docs/ROADMAP_MAESTRO.md`.
> Para contratos internos ver `docs/contracts/`.

---

## Inspector de CFDI

### Parsing y detección de perfil
- **Qué hace:** Parsea un XML CFDI (versión 4.0) y detecta si es de tipo Ingreso o Pagos.
- **Dónde vive:** `src/cfdi/engine/python-satcfdi-wrapper.py` (motor principal), con fallback a `src/cfdi/engine/current-ts-wrapper.ts`
- **Estado:** Activo

### Validación matemática (subtotal, total, impuestos por línea)
- **Qué hace:** Verifica que `Importe = Cantidad × ValorUnitario` por concepto, que `SubTotal` y `Total` cuadren, y que los traslados por línea sean correctos.
- **Dónde vive:** `backend/app/services/analyze_cfdi.py` (`_collect_math_findings`, `_collect_concept_diffs`)
- **Estado:** Activo

### Auditoría de impuestos agrupados (regla SAT de redondeo)
- **Qué hace:** Compara la suma de impuestos por concepto contra el nodo Impuestos global del comprobante, aplicando la regla de acumulación y redondeo del SAT.
- **Dónde vive:** `backend/app/services/analyze_cfdi.py` (`_collect_sat_rounding_findings`, `_collect_tax_audit_group_findings`)
- **Estado:** Activo

### Validación de catálogos — claveProdServ
- **Qué hace:** Verifica que la `ClaveProdServ` de cada concepto exista en el catálogo SAT `c_ClaveProdServ`. Genera un finding por clave inválida con los conceptos afectados.
- **Dónde vive:** `src/cfdi/engine/python-satcfdi-wrapper.py` (`normalize_concept`), `backend/app/services/analyze_cfdi.py` (`_collect_catalog_findings`)
- **Estado:** Activo
- **Contrato:** ver `docs/contracts/sentinel-catalogo.md`

### Validación de catálogos — cabecera del CFDI
- **Qué hace:** Verifica que `UsoCFDI`, `MetodoPago`, `FormaPago` y `Moneda` del comprobante existan en sus catálogos SAT respectivos. Genera un finding por campo inválido.
- **Dónde vive:** `src/cfdi/engine/python-satcfdi-wrapper.py` (`build_cfdi_payload`), `backend/app/services/analyze_cfdi.py` (`_collect_catalog_findings`, `_HEADER_CATALOG_FIELDS`)
- **Estado:** Activo — valida pertenencia al catálogo, no validez contextual por régimen
- **Contrato:** ver `docs/contracts/sentinel-catalogo.md`
- **Finding IDs:** `catalog-uso-cfdi-*`, `catalog-metodo-pago-*`, `catalog-forma-pago-*`, `catalog-moneda-*`

### Findings sidebar con correctionSteps
- **Qué hace:** Muestra hallazgos clasificados por severidad (critical / warning) con explicación, conceptos relacionados y pasos de corrección accionables.
- **Dónde vive:** `src/components/FindingsSidebar.tsx`, `src/app/hooks/useFindingContexts.ts`
- **Estado:** Activo

### Extracción a tabla (Ingreso)
- **Qué hace:** Exporta los conceptos e impuestos del CFDI a una tabla flat con columnas por tipo de impuesto, useful para exportar a Excel/CSV.
- **Dónde vive:** `src/cfdi/engine/python-satcfdi-wrapper.py` (`build_ingreso_rows`, `build_ingreso_row_header`)
- **Estado:** Activo

### Extracción a tabla (Pagos)
- **Qué hace:** Extrae los pagos y documentos relacionados del complemento cfdi:Pagos a una tabla flat.
- **Dónde vive:** `src/cfdi/engine/python-satcfdi-wrapper.py` (`build_pago_rows`)
- **Estado:** Activo

### Visor de árbol XML (XmlNodeViewer)
- **Qué hace:** Muestra el XML como árbol de nodos navegable con virtual scroll para XMLs pesados. Permite ver atributos y valores de cada nodo.
- **Dónde vive:** `src/components/XmlNodeViewer.tsx`
- **Estado:** Activo

### Validación de RFC (formato)
- **Qué hace:** Verifica que el RFC del emisor o receptor tenga el formato correcto (estructura SAT).
- **Dónde vive:** Frontend + llamada a API SAT
- **Estado:** Activo

### Consulta estado SAT (vigente / cancelado)
- **Qué hace:** Consulta si un CFDI está vigente o cancelado en el portal del SAT, dado su UUID, RFC emisor y RFC receptor.
- **Dónde vive:** `backend/app/routers/sat_enquiry.py`, frontend `ConsultasSat`
- **Estado:** Activo

---

## Pendiente / Backlog

| Feature | Estado | Frente |
|---|---|---|
| Validación catálogo `claveUnidad` | Pendiente | Frente B-ext |
| Validación `FormaDePagoP` en complemento Pagos | Pendiente | Frente B-ext |
| Verificación firma digital (sello SAT/PAC) | Exploración | Frente B |
| XML → PDF / render del comprobante | Exploración | Frente C |
| Validación XSD / estructura XML | Pendiente | Frente D |
| DIOT / Contabilidad electrónica | No iniciado | Frente E |
