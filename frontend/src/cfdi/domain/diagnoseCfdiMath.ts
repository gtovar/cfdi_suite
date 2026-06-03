import type { CanonicalCfdi, CanonicalTaxLine } from './canonicalCfdi';

export type MathFindingLevel = 'concept' | 'summary' | 'comprobante';
export type MathFindingSeverity = 'info' | 'warning' | 'error';

export interface MathFinding {
  code: 'SUBTOTAL_MISMATCH' | 'LINE_TAX_MISMATCH' | 'TOTAL_MISMATCH' | 'LINE_TAX_NOT_RECALCULATED';
  level: MathFindingLevel;
  severity: MathFindingSeverity;
  message: string;
  declared: number | null;
  calculated: number | null;
  difference: number | null;
  conceptIndex?: number;
  taxIndex?: number;
  context?: Record<string, unknown>;
}

export interface CfdiMathDiagnosis {
  findings: MathFinding[];
  hasErrors: boolean;
}

export function roundCurrency(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function roundRate(value: number): number {
  return Math.round((value + Number.EPSILON) * 1_000_000) / 1_000_000;
}

export function sumSafe(values: Array<number | null | undefined>): number {
  return values.reduce((acc, value) => acc + (value ?? 0), 0);
}

export function diffCurrency(declared: number | null, calculated: number | null): number | null {
  if (declared === null || calculated === null) {
    return null;
  }

  return roundCurrency(roundCurrency(declared) - roundCurrency(calculated));
}

function sumConceptImports(cfdi: CanonicalCfdi): number {
  return roundCurrency(sumSafe(cfdi.conceptos.map((concept) => concept.importe)));
}

function sumConceptTraslados(cfdi: CanonicalCfdi): number {
  return roundCurrency(
    sumSafe(
      cfdi.conceptos.flatMap((concept) => concept.traslados.map((tax) => tax.importe)),
    ),
  );
}

function sumConceptRetenciones(cfdi: CanonicalCfdi): number {
  return roundCurrency(
    sumSafe(
      cfdi.conceptos.flatMap((concept) => concept.retenciones.map((tax) => tax.importe)),
    ),
  );
}

function buildLineTaxMismatchFinding(
  tax: CanonicalTaxLine,
  conceptIndex: number,
  taxIndex: number,
  calculated: number,
): MathFinding {
  const declared = tax.importe;
  const difference = diffCurrency(declared, calculated);

  return {
    code: 'LINE_TAX_MISMATCH',
    level: 'concept',
    severity: 'error',
    message: `Concepto ${conceptIndex + 1}: traslado ${tax.impuesto ?? '-'} no coincide con Base × Tasa.`,
    declared,
    calculated,
    difference,
    conceptIndex,
    taxIndex,
    context: {
      impuesto: tax.impuesto,
      tipoFactor: tax.tipoFactor,
      base: tax.base,
      tasaOCuota: tax.tasaOCuota,
    },
  };
}

function buildLineTaxNotRecalculatedFinding(
  tax: CanonicalTaxLine,
  conceptIndex: number,
  taxIndex: number,
): MathFinding {
  return {
    code: 'LINE_TAX_NOT_RECALCULATED',
    level: 'concept',
    severity: 'info',
    message: `Concepto ${conceptIndex + 1}: traslado ${tax.impuesto ?? '-'} no se recalcula en v0 porque TipoFactor=${tax.tipoFactor ?? 'null'}.`,
    declared: tax.importe,
    calculated: null,
    difference: null,
    conceptIndex,
    taxIndex,
    context: {
      impuesto: tax.impuesto,
      tipoFactor: tax.tipoFactor,
      base: tax.base,
      tasaOCuota: tax.tasaOCuota,
    },
  };
}

export function diagnoseCfdiMath(cfdi: CanonicalCfdi): CfdiMathDiagnosis {
  const findings: MathFinding[] = [];

  const calculatedSubtotal = sumConceptImports(cfdi);
  const subtotalDifference = diffCurrency(cfdi.subTotal, calculatedSubtotal);

  if (subtotalDifference !== null && subtotalDifference !== 0) {
    findings.push({
      code: 'SUBTOTAL_MISMATCH',
      level: 'comprobante',
      severity: 'error',
      message: 'SubTotal declarado no coincide con la suma de importes de conceptos.',
      declared: cfdi.subTotal,
      calculated: calculatedSubtotal,
      difference: subtotalDifference,
      context: {
        conceptos: cfdi.conceptos.length,
      },
    });
  }

  cfdi.conceptos.forEach((concept, conceptIndex) => {
    concept.traslados.forEach((tax, taxIndex) => {
      if (tax.tipoFactor === 'Tasa' && tax.base !== null && tax.tasaOCuota !== null && tax.importe !== null) {
        const calculatedTax = roundCurrency(roundCurrency(tax.base) * roundRate(tax.tasaOCuota));
        const taxDifference = diffCurrency(tax.importe, calculatedTax);

        if (taxDifference !== null && taxDifference !== 0) {
          findings.push(buildLineTaxMismatchFinding(tax, conceptIndex, taxIndex, calculatedTax));
        }

        return;
      }

      if (tax.tipoFactor === 'Exento' || tax.tipoFactor === 'Cuota') {
        findings.push(buildLineTaxNotRecalculatedFinding(tax, conceptIndex, taxIndex));
      }
    });
  });

  const calculatedTotal = roundCurrency(
    calculatedSubtotal
      - roundCurrency(cfdi.descuento ?? 0)
      + sumConceptTraslados(cfdi)
      - sumConceptRetenciones(cfdi),
  );
  const totalDifference = diffCurrency(cfdi.total, calculatedTotal);

  if (totalDifference !== null && totalDifference !== 0) {
    findings.push({
      code: 'TOTAL_MISMATCH',
      level: 'comprobante',
      severity: 'error',
      message: 'Total declarado no coincide con la reconstruccion matematica v0 del comprobante.',
      declared: cfdi.total,
      calculated: calculatedTotal,
      difference: totalDifference,
      context: {
        subtotalCalculado: calculatedSubtotal,
        descuento: roundCurrency(cfdi.descuento ?? 0),
        traslados: sumConceptTraslados(cfdi),
        retenciones: sumConceptRetenciones(cfdi),
      },
    });
  }

  return {
    findings,
    hasErrors: findings.some((finding) => finding.severity === 'error'),
  };
}
