import { describe, expect, it } from 'vitest';
import type { CFDIData } from './cfdiTypes';
import { enrichCfdiWithMathDiagnosis, toCanonicalCfdi } from './cfdiAnalysisAdapter';

function createBaseCfdiData(overrides: Partial<CFDIData> = {}): CFDIData {
  return {
    version: '4.0',
    fecha: '2026-03-26T10:00:00',
    uuid: 'TEST-UUID-123',
    emisor: 'EMISOR SA DE CV',
    receptor: 'RECEPTOR SA DE CV',
    subtotal: 100,
    descuento: 0,
    total: 116,
    conceptos: [
      {
        descripcion: 'Servicio base',
        cantidad: 1,
        valorUnitario: 100,
        importe: 100,
        importeCalculado: 100,
        diferencia: 0,
        claveProdServ: '10101504',
        impuestos: [
          {
            tipo: 'Traslado',
            impuesto: '002',
            base: 100,
            tipoFactor: 'Tasa',
            tasaOCuota: 0.16,
            importe: 16,
            importeCalculado: 16,
            diferencia: 0,
          },
        ],
      },
    ],
    impuestosGlobales: [
      {
        tipo: 'Traslado',
        impuesto: '002',
        base: 100,
        tipoFactor: 'Tasa',
        tasaOCuota: 0.16,
        importe: 16,
        importeCalculado: 0,
        diferencia: 0,
      },
    ],
    subtotalCalculado: 0,
    totalCalculado: 0,
    hallazgos: [],
    findings: [],
    impactedConceptIndexes: [],
    taxAuditGroups: [],
    verdict: {
      status: 'clean',
      title: 'Sin discrepancias detectadas',
      summary: 'Los importes principales cuadran con el cálculo actual.',
    },
    supportText: '',
    ...overrides,
  };
}

describe('cfdiAnalysisAdapter', () => {
  it('maps CFDIData into CanonicalCfdi shape', () => {
    const data = createBaseCfdiData();

    const canonical = toCanonicalCfdi(data);

    expect(canonical).toMatchObject({
      version: '4.0',
      tipoDeComprobante: 'I',
      subTotal: 100,
      total: 116,
      descuento: 0,
      conceptos: [
        {
          descripcion: 'Servicio base',
          cantidad: 1,
          valorUnitario: 100,
          importe: 100,
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
    });
  });

  it('enriches CFDIData with math findings and impacted concepts', () => {
    const data = createBaseCfdiData({
      subtotal: 90,
      total: 120,
      conceptos: [
        {
          descripcion: 'Servicio con diferencia',
          cantidad: 1,
          valorUnitario: 100,
          importe: 100,
          importeCalculado: 100,
          diferencia: 0,
          claveProdServ: '10101504',
          impuestos: [
            {
              tipo: 'Traslado',
              impuesto: '002',
              base: 100,
              tipoFactor: 'Tasa',
              tasaOCuota: 0.16,
              importe: 15,
              importeCalculado: 16,
              diferencia: 1,
            },
          ],
        },
      ],
    });

    const enriched = enrichCfdiWithMathDiagnosis(data);

    expect(enriched.subtotalCalculado).toBe(100);
    expect(enriched.totalCalculado).toBe(115);
    expect(enriched.findings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ title: 'Discrepancia en subtotal', severity: 'critical' }),
        expect.objectContaining({ title: 'Traslado inconsistente en concepto 1', severity: 'critical' }),
        expect.objectContaining({ title: 'Discrepancia en total', severity: 'critical' }),
      ]),
    );
    expect(enriched.hallazgos).toEqual(
      expect.arrayContaining([
        expect.stringContaining('Discrepancia en subtotal'),
        expect.stringContaining('Traslado inconsistente en concepto 1'),
        expect.stringContaining('Discrepancia en total'),
      ]),
    );
    expect(enriched.impactedConceptIndexes).toContain(0);
  });

  it('adds informational finding for Exento without converting it into hallazgo', () => {
    const data = createBaseCfdiData({
      total: 100,
      impuestosGlobales: [],
      conceptos: [
        {
          descripcion: 'Exento',
          cantidad: 1,
          valorUnitario: 100,
          importe: 100,
          importeCalculado: 100,
          diferencia: 0,
          claveProdServ: '10101504',
          impuestos: [
            {
              tipo: 'Traslado',
              impuesto: '002',
              base: 100,
              tipoFactor: 'Exento',
              tasaOCuota: 0,
              importe: 0,
              importeCalculado: 0,
              diferencia: 0,
            },
          ],
        },
      ],
    });

    const enriched = enrichCfdiWithMathDiagnosis(data);

    expect(enriched.findings).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          title: 'Traslado no recalculado en concepto 1',
          severity: 'warning',
        }),
      ]),
    );
    expect(enriched.hallazgos).toEqual([]);
  });
});
