import { useState } from 'react';
import type { CFDIData, CFDIIngresoRow, CFDIPagoRow } from '../../cfdi/public';
import type { ExtractGridController } from '../../components/extract-workspace/types';

function downloadBlob(content: BlobPart, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function escapeCsv(value: string | number) {
  return `"${String(value).replaceAll('"', '""')}"`;
}

export function useCfdiExports(params: {
  cfdi: CFDIData | null;
  ingresoRows: CFDIIngresoRow[];
  pagoRows: CFDIPagoRow[];
  activeDatasetType: 'ingresos' | 'pagos';
  extractGrid: ExtractGridController;
}) {
  const { cfdi, ingresoRows, pagoRows, activeDatasetType, extractGrid } = params;
  const [reportExported, setReportExported] = useState(false);
  const [taxesExported, setTaxesExported] = useState(false);
  const [ingresosExported, setIngresosExported] = useState(false);
  const [pagosExported, setPagosExported] = useState(false);
  const [pagosExportError, setPagosExportError] = useState(false);
  const [tableExported, setTableExported] = useState(false);
  const [tableExportError, setTableExportError] = useState(false);

  function exportReport() {
    if (!cfdi) return;

    const report = `
REPORTE DE AUDITORÍA CFDI
-------------------------
UUID: ${cfdi.uuid}
Fecha: ${cfdi.fecha}
Emisor: ${cfdi.emisor}
Receptor: ${cfdi.receptor}

DICTAMEN:
${cfdi.verdict.title}
${cfdi.verdict.summary}

RESUMEN FINANCIERO:
Subtotal XML: $${cfdi.subtotal}
Subtotal Calc: $${cfdi.subtotalCalculado}
Total XML: $${cfdi.total}
Total Calc: $${cfdi.totalCalculado}

HALLAZGOS:
${cfdi.findings.length > 0 ? cfdi.findings.map((f) => `- ${f.title}: ${f.summary}`).join('\n') : 'Sin discrepancias detectadas.'}

TRASLADOS AGRUPADOS:
${cfdi.taxAuditGroups.length > 0 ? cfdi.taxAuditGroups.map((group) => `- ${group.impuesto} ${group.tipoFactor} ${(group.tasaOCuota * 100).toFixed(2)}% | Detalle: ${group.importeDetalle.toFixed(2)} | Agrupado: ${group.importeAgrupado.toFixed(2)} | Dif: ${group.diferencia.toFixed(2)}`).join('\n') : 'Sin traslados agrupados detectados.'}

CONCEPTOS AFECTADOS:
${cfdi.impactedConceptIndexes.length > 0 ? cfdi.impactedConceptIndexes.map((index) => {
  const c = cfdi.conceptos[index];
  return `- ${index + 1}. ${c.descripcion}: XML $${c.importe} vs Calc $${c.importeCalculado} | Dif $${c.diferencia.toFixed(6)}`;
}).join('\n') : 'No hay conceptos afectados.'}

CONCEPTOS REVISADOS:
${cfdi.conceptos.map((c) => `- ${c.descripcion}: XML $${c.importe} vs Calc $${c.importeCalculado} (${c.diferencia === 0 ? 'OK' : 'ERROR'})`).join('\n')}
    `;

    downloadBlob(report, `Reporte_CFDI_${cfdi.uuid.substring(0, 8)}.txt`, 'text/plain');
    setReportExported(true);
    window.setTimeout(() => setReportExported(false), 1600);
  }

  function exportTaxBreakdown() {
    if (!cfdi) return;

    const headers = [
      'concepto_index',
      'descripcion',
      'clave_prod_serv',
      'impuesto',
      'tipo_factor',
      'tasa_porcentaje',
      'base',
      'importe_xml',
      'importe_calculado',
      'diferencia',
    ];

    const rows = cfdi.conceptos.flatMap((concepto, conceptIndex) =>
      concepto.impuestos.map((impuesto) => [
        conceptIndex + 1,
        concepto.descripcion,
        concepto.claveProdServ,
        impuesto.impuesto,
        impuesto.tipoFactor,
        (impuesto.tasaOCuota * 100).toFixed(6),
        impuesto.base.toFixed(6),
        impuesto.importe.toFixed(6),
        impuesto.importeCalculado.toFixed(6),
        impuesto.diferencia.toFixed(6),
      ]),
    );

    const csv = [
      headers.join(','),
      ...rows.map((row) => row.map(escapeCsv).join(',')),
    ].join('\n');

    downloadBlob(csv, `Desglose_Impuestos_${cfdi.uuid.substring(0, 8)}.csv`, 'text/csv;charset=utf-8;');
    setTaxesExported(true);
    window.setTimeout(() => setTaxesExported(false), 1600);
  }

  function exportIngresosCsv() {
    if (!cfdi) return;

    const headers = [
      'UUID', 'Fecha', 'Serie', 'Folio', 'RFC_Emisor', 'Nombre_Emisor', 'RFC_Receptor',
      'Nombre_Receptor', 'UsoCFDI', 'MetodoPago', 'FormaPago', 'Moneda', 'TipoCambio',
      'Subtotal', 'Descuento', 'Total', 'ClaveProdServ', 'Cantidad', 'Descripcion',
      'ValorUnitario', 'Importe', 'ObjetoImp', 'TipoImp', 'Base', 'Impuesto',
      'TipoFactor', 'TasaOCuota', 'ImporteImp',
    ];

    const csv = [
      headers.join(','),
      ...ingresoRows.map((row) => [
        row.uuid, row.fecha, row.serie, row.folio, row.rfcEmisor, row.nombreEmisor,
        row.rfcReceptor, row.nombreReceptor, row.usoCfdi, row.metodoPago, row.formaPago,
        row.moneda, row.tipoCambio, row.subtotal, row.descuento, row.total, row.claveProdServ,
        row.cantidad, row.descripcion, row.valorUnitario, row.importe, row.objetoImp,
        row.tipoImp, row.baseImp, row.impuesto, row.tipoFactor, row.tasaCuota, row.importeImp,
      ].map(escapeCsv).join(',')),
    ].join('\n');

    downloadBlob(`\ufeff${csv}`, `CFDI_Ingresos_${cfdi.uuid.substring(0, 8)}.csv`, 'text/csv;charset=utf-8;');
    setIngresosExported(true);
    window.setTimeout(() => setIngresosExported(false), 1600);
  }

  function exportPagosCsv() {
    if (!cfdi) return;

    try {
      if (pagoRows.length === 0) {
        throw new Error('No es complemento de pagos');
      }

      const headers = [
        'UUID_CFDI', 'Fecha_CFDI', 'RFC_Emisor', 'RFC_Receptor', 'FechaPago', 'FormaPago',
        'MonedaP', 'Monto', 'UUID_DR', 'SerieFolio', 'Parcialidad', 'ImpPagado',
        'SaldoInsoluto', 'BaseDR', 'ImpuestoDR', 'TipoFactorDR', 'TasaOCuotaDR', 'ImporteDR',
      ];

      const csv = [
        headers.join(','),
        ...pagoRows.map((row) => [
          row.uuidCFDI, row.fechaCFDI, row.rfcEmisor, row.rfcReceptor, row.fechaPago,
          row.formaPago, row.monedaP, row.monto, row.uuidDR, row.serieFolio, row.parcialidad,
          row.impPagado, row.saldoInsoluto, row.baseDR, row.impuestoDR, row.tipoFactorDR,
          row.tasaCuotaDR, row.importeDR,
        ].map(escapeCsv).join(',')),
      ].join('\n');

      downloadBlob(`\ufeff${csv}`, `CFDI_Pagos_${cfdi.uuid.substring(0, 8)}.csv`, 'text/csv;charset=utf-8;');
      setPagosExportError(false);
      setPagosExported(true);
      window.setTimeout(() => setPagosExported(false), 1600);
    } catch (error) {
      console.error('Error exporting pagos CSV:', error);
      setPagosExported(false);
      setPagosExportError(true);
      window.setTimeout(() => setPagosExportError(false), 2200);
    }
  }

  function exportCurrentTable() {
    try {
      const visibleColumns = extractGrid.table.getVisibleLeafColumns();
      const rowModel = extractGrid.selectedRowCount > 0
        ? extractGrid.table.getSelectedRowModel()
        : extractGrid.table.getSortedRowModel();

      if (rowModel.rows.length === 0 || visibleColumns.length === 0) {
        throw new Error('Sin datos');
      }

      const headers = visibleColumns.map((column) => String(column.columnDef.header ?? column.id));
      const csvRows = rowModel.rows.map((row) =>
        visibleColumns
          .map((column) => escapeCsv(String(row.getValue(column.id) ?? '')))
          .join(','),
      );

      const csv = [headers.join(','), ...csvRows].join('\n');
      const uuidSuffix = cfdi?.uuid?.substring(0, 8) || 'cfdi';

      downloadBlob(`\ufeff${csv}`, `Tabla_${activeDatasetType}_${uuidSuffix}.csv`, 'text/csv;charset=utf-8;');
      setTableExportError(false);
      setTableExported(true);
      window.setTimeout(() => setTableExported(false), 1600);
    } catch {
      setTableExported(false);
      setTableExportError(true);
      window.setTimeout(() => setTableExportError(false), 1600);
    }
  }

  return {
    reportExported,
    taxesExported,
    ingresosExported,
    pagosExported,
    pagosExportError,
    tableExported,
    tableExportError,
    exportReport,
    exportTaxBreakdown,
    exportIngresosCsv,
    exportPagosCsv,
    exportCurrentTable,
  };
}
