import type { CanonicalCfdi, CanonicalConcept, CanonicalTaxLine } from '../domain/canonicalCfdi';
import { diagnoseCfdiMath, roundCurrency, sumSafe, type MathFinding } from '../domain/diagnoseCfdiMath';
import type { AuditFinding, CFDIConcept, CFDIData, CFDIImpuesto } from './cfdiTypes';

function toCanonicalTaxLine(impuesto: CFDIImpuesto): CanonicalTaxLine {
  return {
    base: impuesto.base,
    impuesto: impuesto.impuesto || null,
    tipoFactor: impuesto.tipoFactor || null,
    tasaOCuota: impuesto.tasaOCuota,
    importe: impuesto.importe,
  };
}

function toCanonicalConcept(concepto: CFDIData['conceptos'][number]): CanonicalConcept {
  return {
    descripcion: concepto.descripcion || null,
    cantidad: concepto.cantidad,
    valorUnitario: concepto.valorUnitario,
    importe: concepto.importe,
    objetoImp: null,
    traslados: concepto.impuestos.filter((impuesto) => impuesto.tipo === 'Traslado').map(toCanonicalTaxLine),
    retenciones: concepto.impuestos.filter((impuesto) => impuesto.tipo === 'Retencion').map(toCanonicalTaxLine),
  };
}

function fromCanonicalTaxLine(impuesto: CanonicalTaxLine, tipo: CFDIImpuesto['tipo']): CFDIImpuesto {
  return {
    tipo,
    impuesto: impuesto.impuesto ?? '',
    base: impuesto.base ?? 0,
    tipoFactor: impuesto.tipoFactor ?? '',
    tasaOCuota: impuesto.tasaOCuota ?? 0,
    importe: impuesto.importe ?? 0,
    importeCalculado: 0,
    diferencia: 0,
  };
}

export function toCanonicalCfdi(data: CFDIData): CanonicalCfdi {
  return {
    version: data.version || null,
    tipoDeComprobante: 'I',
    subTotal: data.subtotal,
    total: data.total,
    moneda: null,
    descuento: data.descuento,
    conceptos: data.conceptos.map(toCanonicalConcept),
    resumenImpuestos: {
      traslados: data.impuestosGlobales.filter((impuesto) => impuesto.tipo === 'Traslado').map(toCanonicalTaxLine),
      retenciones: data.impuestosGlobales.filter((impuesto) => impuesto.tipo === 'Retencion').map(toCanonicalTaxLine),
    },
  };
}

export function canonicalConceptToCfdiConcept(concepto: CanonicalConcept): CFDIConcept {
  const impuestos = [
    ...concepto.traslados.map((impuesto) => fromCanonicalTaxLine(impuesto, 'Traslado')),
    ...concepto.retenciones.map((impuesto) => fromCanonicalTaxLine(impuesto, 'Retencion')),
  ];

  const cantidad = concepto.cantidad ?? 0;
  const valorUnitario = concepto.valorUnitario ?? 0;
  const importe = concepto.importe ?? 0;

  return {
    descripcion: concepto.descripcion ?? '',
    cantidad,
    valorUnitario,
    importe,
    importeCalculado: Number((cantidad * valorUnitario).toFixed(6)),
    diferencia: Math.abs(importe - cantidad * valorUnitario),
    claveProdServ: '',
    impuestos: impuestos.map((impuesto) => ({
      ...impuesto,
      importeCalculado:
        impuesto.tipoFactor === 'Tasa'
          ? Number(((impuesto.base ?? 0) * (impuesto.tasaOCuota ?? 0)).toFixed(6))
          : 0,
      diferencia:
        impuesto.tipoFactor === 'Tasa'
          ? Math.abs((impuesto.importe ?? 0) - (impuesto.base ?? 0) * (impuesto.tasaOCuota ?? 0))
          : 0,
    })),
  };
}

export function canonicalSummaryTaxesToCfdi(summary: CanonicalCfdi['resumenImpuestos']): CFDIImpuesto[] {
  return [
    ...summary.traslados.map((impuesto) => fromCanonicalTaxLine(impuesto, 'Traslado')),
    ...summary.retenciones.map((impuesto) => fromCanonicalTaxLine(impuesto, 'Retencion')),
  ];
}

function mapMathSeverity(severity: MathFinding['severity']): AuditFinding['severity'] {
  return severity === 'error' ? 'critical' : 'warning';
}

function buildMathFindingTitle(finding: MathFinding): string {
  switch (finding.code) {
    case 'SUBTOTAL_MISMATCH':
      return 'Discrepancia en subtotal';
    case 'LINE_TAX_MISMATCH':
      return `Traslado inconsistente en concepto ${(finding.conceptIndex ?? 0) + 1}`;
    case 'TOTAL_MISMATCH':
      return 'Discrepancia en total';
    case 'LINE_TAX_NOT_RECALCULATED':
      return `Traslado no recalculado en concepto ${(finding.conceptIndex ?? 0) + 1}`;
    default:
      return finding.code;
  }
}

function formatMoney(value: number | null): string {
  if (value === null) return '-';
  return value.toFixed(2);
}

function buildMathFindingSummary(finding: MathFinding): string {
  if (finding.code === 'LINE_TAX_NOT_RECALCULATED') {
    const tipoFactor = String(finding.context?.tipoFactor ?? '-');
    return `TipoFactor ${tipoFactor} no se recalcula como tasa en v0.`;
  }

  return `XML declara ${formatMoney(finding.declared)} y el cálculo da ${formatMoney(finding.calculated)}.`;
}

function buildMathFindingMessage(finding: MathFinding): string {
  return `${buildMathFindingTitle(finding)}: ${buildMathFindingSummary(finding)}`;
}

export function enrichCfdiWithMathDiagnosis(data: CFDIData, canonical: CanonicalCfdi = toCanonicalCfdi(data)): CFDIData {
  data.subtotalCalculado = roundCurrency(sumSafe(data.conceptos.map((concepto) => concepto.importe)));
  data.totalCalculado = roundCurrency(
    data.subtotalCalculado
      - roundCurrency(data.descuento ?? 0)
      + roundCurrency(sumSafe(data.conceptos.flatMap((concepto) => concepto.impuestos.filter((impuesto) => impuesto.tipo === 'Traslado').map((impuesto) => impuesto.importe))))
      - roundCurrency(sumSafe(data.conceptos.flatMap((concepto) => concepto.impuestos.filter((impuesto) => impuesto.tipo === 'Retencion').map((impuesto) => impuesto.importe)))),
  );

  const diagnosis = diagnoseCfdiMath(canonical);

  diagnosis.findings.forEach((finding) => {
    data.findings.push({
      id: `math-${finding.code}-${finding.level}-${finding.conceptIndex ?? 'na'}-${finding.taxIndex ?? 'na'}`,
      severity: mapMathSeverity(finding.severity),
      title: buildMathFindingTitle(finding),
      summary: buildMathFindingSummary(finding),
      declared: finding.declared != null ? String(finding.declared) : undefined,
      expected: finding.calculated != null ? String(finding.calculated) : undefined,
    });

    if (finding.severity === 'error') {
      data.hallazgos.push(buildMathFindingMessage(finding));
    }

    if (typeof finding.conceptIndex === 'number' && !data.impactedConceptIndexes.includes(finding.conceptIndex)) {
      data.impactedConceptIndexes.push(finding.conceptIndex);
    }
  });

  return data;
}
