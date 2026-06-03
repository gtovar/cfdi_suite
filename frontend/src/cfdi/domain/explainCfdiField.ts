import {
  objetoImpCatalog,
  taxCodeCatalog,
  tipoFactorCatalog,
} from './cfdiCatalogs';

export interface ExplainedCfdiField {
  key: string;
  rawValue: string | number | null;
  label: string;
  meaning: string;
}

const fieldLabelMap: Record<string, string> = {
  version: 'Version',
  tipoDeComprobante: 'Tipo de comprobante',
  subTotal: 'SubTotal',
  total: 'Total',
  moneda: 'Moneda',
  descuento: 'Descuento',
  descripcion: 'Descripcion',
  cantidad: 'Cantidad',
  valorUnitario: 'ValorUnitario',
  importe: 'Importe',
  objetoImp: 'ObjetoImp',
  base: 'Base',
  impuesto: 'Impuesto',
  tipoFactor: 'TipoFactor',
  tasaOCuota: 'TasaOCuota',
};

const fieldMeaningMap: Record<string, string> = {
  version: 'Version declarada del CFDI.',
  tipoDeComprobante: 'Tipo fiscal del comprobante.',
  subTotal: 'Suma declarada antes de impuestos y descuentos.',
  total: 'Monto final declarado del comprobante.',
  moneda: 'Clave de moneda declarada en el CFDI.',
  descuento: 'Descuento declarado a nivel comprobante.',
  descripcion: 'Descripcion comercial del concepto.',
  cantidad: 'Cantidad declarada del concepto.',
  valorUnitario: 'Valor unitario declarado del concepto.',
  importe: 'Monto monetario declarado para el concepto o linea fiscal.',
  objetoImp: 'Indica si el concepto debe o no manejar desglose fiscal.',
  base: 'Monto sobre el que se calcula el impuesto.',
  impuesto: 'Codigo SAT del impuesto que debe traducirse a una etiqueta humana.',
  tipoFactor: 'Regla SAT que indica como se aplica el impuesto.',
  tasaOCuota: 'Valor tecnico de porcentaje o cuota aplicable.',
};

function getFieldLabel(key: string): string {
  return fieldLabelMap[key] ?? key;
}

function formatPercent(value: number): string {
  return `${(value * 100).toLocaleString('es-MX', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 6,
  })}%`;
}

function explainTaxCode(rawValue: string | null): string {
  if (!rawValue) {
    return 'Sin codigo de impuesto declarado.';
  }

  const catalogEntry = taxCodeCatalog[rawValue as keyof typeof taxCodeCatalog];
  return catalogEntry
    ? `${catalogEntry.label}. Codigo SAT ${rawValue}.`
    : `Codigo SAT ${rawValue} sin catalogo UI v0.`;
}

function explainTipoFactor(rawValue: string | null): string {
  if (!rawValue) {
    return 'Sin tipo de factor declarado.';
  }

  const catalogEntry = tipoFactorCatalog[rawValue as keyof typeof tipoFactorCatalog];
  return catalogEntry
    ? `${catalogEntry.label}. ${catalogEntry.description}.`
    : `TipoFactor ${rawValue} sin catalogo UI v0.`;
}

function explainObjetoImp(rawValue: string | null): string {
  if (!rawValue) {
    return 'Sin ObjetoImp declarado.';
  }

  const catalogEntry = objetoImpCatalog[rawValue as keyof typeof objetoImpCatalog];
  return catalogEntry
    ? `${catalogEntry.label}. Codigo SAT ${rawValue}.`
    : `ObjetoImp ${rawValue} sin catalogo UI v0.`;
}

function explainTasaOCuota(rawValue: string | number | null): string {
  if (rawValue === null || rawValue === '') {
    return 'Sin tasa o cuota declarada.';
  }

  const numericValue = typeof rawValue === 'number' ? rawValue : Number(rawValue);
  if (Number.isNaN(numericValue)) {
    return `Valor tecnico ${String(rawValue)}.`;
  }

  return `${String(rawValue)}. Traduccion humana aproximada: ${formatPercent(numericValue)}.`;
}

export function explainCfdiField(
  key: string,
  rawValue: string | number | null,
): ExplainedCfdiField {
  switch (key) {
    case 'impuesto':
      return {
        key,
        rawValue,
        label: getFieldLabel(key),
        meaning: explainTaxCode(rawValue === null ? null : String(rawValue)),
      };
    case 'tipoFactor':
      return {
        key,
        rawValue,
        label: getFieldLabel(key),
        meaning: explainTipoFactor(rawValue === null ? null : String(rawValue)),
      };
    case 'objetoImp':
      return {
        key,
        rawValue,
        label: getFieldLabel(key),
        meaning: explainObjetoImp(rawValue === null ? null : String(rawValue)),
      };
    case 'tasaOCuota':
      return {
        key,
        rawValue,
        label: getFieldLabel(key),
        meaning: explainTasaOCuota(rawValue),
      };
    default:
      return {
        key,
        rawValue,
        label: getFieldLabel(key),
        meaning: fieldMeaningMap[key] ?? 'Campo canonico del CFDI v0 sin explicacion especifica adicional.',
      };
  }
}
