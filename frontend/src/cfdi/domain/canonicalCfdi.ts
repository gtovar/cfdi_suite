// v0 uses a tolerant contract because values come from real XML input.
// SAT catalogs constrain the known values, but the canonical shape does not
// reject unexpected codes during normalization.
export type CanonicalTaxCode = string;
export type CanonicalTipoFactor = string;

export interface CanonicalTaxLine {
  base: number | null;
  impuesto: CanonicalTaxCode | null;
  tipoFactor: CanonicalTipoFactor | null;
  tasaOCuota: number | null;
  importe: number | null;
}

export interface CanonicalTaxSummary {
  traslados: CanonicalTaxLine[];
  retenciones: CanonicalTaxLine[];
}

export interface CanonicalConcept {
  descripcion: string | null;
  cantidad: number | null;
  valorUnitario: number | null;
  importe: number | null;
  objetoImp: string | null;
  traslados: CanonicalTaxLine[];
  retenciones: CanonicalTaxLine[];
}

export interface CanonicalCfdi {
  version: string | null;
  tipoDeComprobante: string | null;
  subTotal: number | null;
  total: number | null;
  moneda: string | null;
  descuento: number | null;
  conceptos: CanonicalConcept[];
  resumenImpuestos: CanonicalTaxSummary;
}
