import { describe, expect, it } from 'vitest';
import type { CanonicalCfdi } from './canonicalCfdi';
import { diagnoseCfdiMath } from './diagnoseCfdiMath';

function createBaseCfdi(overrides: Partial<CanonicalCfdi> = {}): CanonicalCfdi {
  return {
    version: '4.0',
    tipoDeComprobante: 'I',
    subTotal: 100,
    total: 116,
    moneda: 'MXN',
    descuento: 0,
    conceptos: [
      {
        descripcion: 'Servicio base',
        cantidad: 1,
        valorUnitario: 100,
        importe: 100,
        objetoImp: '02',
        traslados: [
          {
            base: 100,
            impuesto: '002',
            tipoFactor: 'Tasa',
            tasaOCuota: 0.16,
            importe: 16,
          },
        ],
        retenciones: [],
      },
    ],
    resumenImpuestos: {
      traslados: [],
      retenciones: [],
    },
    ...overrides,
  };
}

describe('diagnoseCfdiMath', () => {
  it('returns no findings for a consistent CFDI', () => {
    const diagnosis = diagnoseCfdiMath(createBaseCfdi());

    expect(diagnosis.findings).toEqual([]);
    expect(diagnosis.hasErrors).toBe(false);
  });

  it('reports subtotal mismatch', () => {
    const diagnosis = diagnoseCfdiMath(createBaseCfdi({ subTotal: 90 }));

    expect(diagnosis.findings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'SUBTOTAL_MISMATCH',
          level: 'comprobante',
          severity: 'error',
          declared: 90,
          calculated: 100,
          difference: -10,
        }),
      ]),
    );
    expect(diagnosis.hasErrors).toBe(true);
  });

  it('reports line tax mismatch for traslado tipo Tasa', () => {
    const cfdi = createBaseCfdi();
    cfdi.conceptos[0].traslados[0].importe = 15;

    const diagnosis = diagnoseCfdiMath(cfdi);

    expect(diagnosis.findings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'LINE_TAX_MISMATCH',
          level: 'concept',
          severity: 'error',
          declared: 15,
          calculated: 16,
          difference: -1,
          conceptIndex: 0,
          taxIndex: 0,
        }),
      ]),
    );
  });

  it('reports total mismatch', () => {
    const diagnosis = diagnoseCfdiMath(createBaseCfdi({ total: 120 }));

    expect(diagnosis.findings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'TOTAL_MISMATCH',
          level: 'comprobante',
          severity: 'error',
          declared: 120,
          calculated: 116,
          difference: 4,
        }),
      ]),
    );
  });

  it('handles CFDI without taxes', () => {
    const diagnosis = diagnoseCfdiMath(
      createBaseCfdi({
        subTotal: 50,
        total: 50,
        conceptos: [
          {
            descripcion: 'Exento',
            cantidad: 1,
            valorUnitario: 50,
            importe: 50,
            objetoImp: '01',
            traslados: [],
            retenciones: [],
          },
        ],
      }),
    );

    expect(diagnosis.findings).toEqual([]);
    expect(diagnosis.hasErrors).toBe(false);
  });

  it('marks Exento as not recalculated in v0', () => {
    const diagnosis = diagnoseCfdiMath(
      createBaseCfdi({
        total: 100,
        conceptos: [
          {
            descripcion: 'Exento',
            cantidad: 1,
            valorUnitario: 100,
            importe: 100,
            objetoImp: '02',
            traslados: [
              {
                base: 100,
                impuesto: '002',
                tipoFactor: 'Exento',
                tasaOCuota: null,
                importe: null,
              },
            ],
            retenciones: [],
          },
        ],
      }),
    );

    expect(diagnosis.findings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'LINE_TAX_NOT_RECALCULATED',
          level: 'concept',
          severity: 'info',
          conceptIndex: 0,
          taxIndex: 0,
          calculated: null,
          difference: null,
        }),
      ]),
    );
    expect(diagnosis.hasErrors).toBe(false);
  });

  it('marks Cuota as not recalculated in v0', () => {
    const diagnosis = diagnoseCfdiMath(
      createBaseCfdi({
        total: 103,
        conceptos: [
          {
            descripcion: 'Cuota',
            cantidad: 1,
            valorUnitario: 100,
            importe: 100,
            objetoImp: '02',
            traslados: [
              {
                base: 100,
                impuesto: '003',
                tipoFactor: 'Cuota',
                tasaOCuota: 3,
                importe: 3,
              },
            ],
            retenciones: [],
          },
        ],
      }),
    );

    expect(diagnosis.findings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'LINE_TAX_NOT_RECALCULATED',
          level: 'concept',
          severity: 'info',
          conceptIndex: 0,
          taxIndex: 0,
        }),
      ]),
    );
    expect(diagnosis.hasErrors).toBe(false);
  });

  it('reports total mismatch when retenciones affect reconstructed total', () => {
    const diagnosis = diagnoseCfdiMath(
      createBaseCfdi({
        total: 116,
        conceptos: [
          {
            descripcion: 'Servicio con retencion',
            cantidad: 1,
            valorUnitario: 100,
            importe: 100,
            objetoImp: '02',
            traslados: [
              {
                base: 100,
                impuesto: '002',
                tipoFactor: 'Tasa',
                tasaOCuota: 0.16,
                importe: 16,
              },
            ],
            retenciones: [
              {
                base: 100,
                impuesto: '001',
                tipoFactor: 'Tasa',
                tasaOCuota: 0.04,
                importe: 4,
              },
            ],
          },
        ],
      }),
    );

    expect(diagnosis.findings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'TOTAL_MISMATCH',
          level: 'comprobante',
          severity: 'error',
          declared: 116,
          calculated: 112,
          difference: 4,
        }),
      ]),
    );
  });

  it('reports total mismatch when descuento affects reconstructed total', () => {
    const diagnosis = diagnoseCfdiMath(
      createBaseCfdi({
        descuento: 10,
        total: 116,
      }),
    );

    expect(diagnosis.findings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'TOTAL_MISMATCH',
          level: 'comprobante',
          severity: 'error',
          declared: 116,
          calculated: 106,
          difference: 10,
        }),
      ]),
    );
  });
});
