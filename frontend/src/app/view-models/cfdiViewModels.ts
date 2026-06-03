import { Calendar, Database, FileText, User } from 'lucide-react';
import type { CFDIData, CFDIIngresoRow, CFDIPagoRow, CFDIProfile } from '../../cfdi/public';
import type { SummaryFieldCard } from '../../components/CfdiSummaryHeader';
import type { ExtractMode } from '../../components/extract-workspace/types';

export interface SummaryMetricCard {
  key: string;
  label: string;
  value: string;
}

function formatDetectedDate(value: string | undefined) {
  return value ? new Date(value).toLocaleString() : '-';
}

export function getProfileLabel(profile: CFDIProfile) {
  switch (profile) {
    case 'ingreso':
      return 'Ingreso';
    case 'pagos':
      return 'Pagos';
    default:
      return 'Desconocido';
  }
}

export function buildSummaryFields(params: {
  profile: CFDIProfile;
  cfdi: CFDIData | null;
  pagoRows: CFDIPagoRow[];
}): SummaryFieldCard[] {
  const { profile, cfdi, pagoRows } = params;

  switch (profile) {
    case 'pagos': {
      const firstPago = pagoRows[0];
      return [
        { key: 'emisor', label: 'Emisor', value: cfdi?.emisor || firstPago?.rfcEmisor || '-', icon: User, meaning: 'Nombre o RFC del emisor detectado en el CFDI.' },
        { key: 'uuid', label: 'UUID', value: cfdi?.uuid || firstPago?.uuidCFDI || '-', icon: FileText, meaning: 'Identificador fiscal único del comprobante timbrado.' },
        { key: 'receptor', label: 'Receptor', value: cfdi?.receptor || firstPago?.rfcReceptor || '-', icon: Database, meaning: 'Nombre o RFC del receptor detectado en el CFDI.' },
        {
          key: 'fecha',
          label: 'Fecha CFDI',
          value: formatDetectedDate(firstPago?.fechaCFDI || cfdi?.fecha),
          icon: Calendar,
          meaning: 'Fecha detectada del comprobante para esta lectura operativa.',
        },
      ];
    }
    case 'ingreso':
      return cfdi
        ? [
            { key: 'emisor', label: 'Emisor', value: cfdi.emisor || '-', icon: User, meaning: 'Nombre o RFC del emisor detectado en el CFDI.' },
            { key: 'uuid', label: 'UUID', value: cfdi.uuid || '-', icon: FileText, meaning: 'Identificador fiscal único del comprobante timbrado.' },
            { key: 'receptor', label: 'Receptor', value: cfdi.receptor || '-', icon: Database, meaning: 'Nombre o RFC del receptor detectado en el CFDI.' },
            {
              key: 'fecha',
              label: 'Fecha timbrado',
              value: formatDetectedDate(cfdi.fecha),
              icon: Calendar,
              meaning: 'Fecha detectada del comprobante para esta lectura operativa.',
            },
          ]
        : [];
    case 'unknown':
    default:
      return cfdi
        ? [
            { key: 'emisor', label: 'Emisor', value: cfdi.emisor || '-', icon: User, meaning: 'Nombre o RFC del emisor detectado en el CFDI.' },
            { key: 'uuid', label: 'UUID', value: cfdi.uuid || '-', icon: FileText, meaning: 'Identificador fiscal único del comprobante timbrado.' },
            { key: 'receptor', label: 'Receptor', value: cfdi.receptor || '-', icon: Database, meaning: 'Nombre o RFC del receptor detectado en el CFDI.' },
            {
              key: 'fecha',
              label: 'Fecha detectada',
              value: formatDetectedDate(cfdi.fecha),
              icon: Calendar,
              meaning: 'Fecha detectada del comprobante para esta lectura operativa.',
            },
          ]
        : [];
  }
}

export function buildExtractMetrics(params: {
  activeDatasetType: ExtractMode;
  extractSearchTerm: string;
  filteredIngresoRows: CFDIIngresoRow[];
  filteredPagoRows: CFDIPagoRow[];
  ingresoRows: CFDIIngresoRow[];
  pagoRows: CFDIPagoRow[];
}): SummaryMetricCard[] {
  const { activeDatasetType, extractSearchTerm, filteredIngresoRows, filteredPagoRows, ingresoRows, pagoRows } = params;

  const conceptosDetectados = new Set(
    ingresoRows.map((row) => `${row.uuid}|${row.claveProdServ}|${row.descripcion}|${row.importe}`),
  ).size;
  const conceptosConImpuesto = new Set(
    ingresoRows
      .filter((row) => row.tipoImp)
      .map((row) => `${row.uuid}|${row.claveProdServ}|${row.descripcion}`),
  ).size;
  const pagosDetectados = new Set(
    pagoRows.map((row) => `${row.uuidCFDI}|${row.fechaPago}|${row.monto}|${row.formaPago}`),
  ).size;
  const doctosRelacionadosDetectados = new Set(
    pagoRows.map((row) => `${row.uuidCFDI}|${row.uuidDR}|${row.serieFolio}|${row.parcialidad}`),
  ).size;
  const registrosConImpuestoDr = pagoRows.filter((row) => row.impuestoDR || row.importeDR).length;

  if (activeDatasetType === 'pagos') {
    return [
      { key: 'rows', label: 'Registros', value: filteredPagoRows.length.toLocaleString('es-MX') },
      { key: 'payments', label: 'Pagos', value: pagosDetectados.toLocaleString('es-MX') },
      { key: 'documents', label: 'Doctos Rel.', value: doctosRelacionadosDetectados.toLocaleString('es-MX') },
      { key: 'drTax', label: 'Con impuesto DR', value: registrosConImpuestoDr.toLocaleString('es-MX') },
    ];
  }

  return [
    { key: 'rows', label: 'Registros', value: filteredIngresoRows.length.toLocaleString('es-MX') },
    { key: 'concepts', label: 'Conceptos', value: conceptosDetectados.toLocaleString('es-MX') },
    { key: 'taxed', label: 'Con impuesto', value: conceptosConImpuesto.toLocaleString('es-MX') },
    { key: 'results', label: 'Resultados', value: extractSearchTerm ? 'Filtrados' : 'Todos' },
  ];
}
