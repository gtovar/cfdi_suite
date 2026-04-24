export interface CFDIConcept {
  descripcion: string;
  cantidad: number;
  valorUnitario: number;
  importe: number;
  importeCalculado: number;
  diferencia: number;
  claveProdServ: string;
  impuestos: CFDIImpuesto[];
}

export interface CFDIImpuesto {
  tipo: 'Traslado' | 'Retencion';
  impuesto: string;
  base: number;
  tipoFactor: string;
  tasaOCuota: number;
  importe: number;
  importeCalculado: number;
  diferencia: number;
}

export interface AuditFinding {
  id: string;
  severity: 'critical' | 'warning';
  title: string;
  summary: string;
}

export interface CFDIIngresoRow {
  uuid: string;
  fecha: string;
  serie: string;
  folio: string;
  rfcEmisor: string;
  nombreEmisor: string;
  rfcReceptor: string;
  nombreReceptor: string;
  usoCfdi: string;
  metodoPago: string;
  formaPago: string;
  moneda: string;
  tipoCambio: string;
  subtotal: string;
  descuento: string;
  total: string;
  claveProdServ: string;
  cantidad: string;
  descripcion: string;
  valorUnitario: string;
  importe: string;
  objetoImp: string;
  tipoImp: string;
  baseImp: string;
  impuesto: string;
  tipoFactor: string;
  tasaCuota: string;
  importeImp: string;
}

export interface CFDIPagoRow {
  uuidCFDI: string;
  fechaCFDI: string;
  rfcEmisor: string;
  rfcReceptor: string;
  fechaPago: string;
  formaPago: string;
  monedaP: string;
  monto: string;
  uuidDR: string;
  serieFolio: string;
  parcialidad: string;
  impPagado: string;
  saldoInsoluto: string;
  baseDR: string;
  impuestoDR: string;
  tipoFactorDR: string;
  tasaCuotaDR: string;
  importeDR: string;
}

export type CFDIProfile = 'ingreso' | 'pagos' | 'unknown';

export interface TaxAuditGroup {
  key: string;
  impuesto: string;
  tipoFactor: string;
  tasaOCuota: number;
  importeDetalle: number;
  importeAgrupado: number;
  diferencia: number;
  conceptos: number[];
}

export interface CFDIData {
  version: string;
  fecha: string;
  uuid: string;
  emisor: string;
  receptor: string;
  subtotal: number;
  descuento: number;
  total: number;
  conceptos: CFDIConcept[];
  impuestosGlobales: CFDIImpuesto[];
  subtotalCalculado: number;
  totalCalculado: number;
  hallazgos: string[];
  findings: AuditFinding[];
  impactedConceptIndexes: number[];
  taxAuditGroups: TaxAuditGroup[];
  verdict: {
    status: 'clean' | 'review' | 'critical';
    title: string;
    summary: string;
  };
  supportText: string;
}
