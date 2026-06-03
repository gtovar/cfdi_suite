import { describe, expect, it } from 'vitest';
import { normalizeCfdi } from './normalizeCfdi';

const CFDI_NS = 'http://www.sat.gob.mx/cfd/4';

function wrapCfdi(inner: string, attrs: Record<string, string> = {}) {
  const attrString = Object.entries({
    Version: '4.0',
    TipoDeComprobante: 'I',
    Moneda: 'MXN',
    ...attrs,
  })
    .map(([key, value]) => `${key}="${value}"`)
    .join(' ');

  return `<?xml version="1.0" encoding="UTF-8"?>
    <cfdi:Comprobante xmlns:cfdi="${CFDI_NS}" ${attrString}>
      ${inner}
    </cfdi:Comprobante>`;
}

describe('normalizeCfdi', () => {
  it('throws on invalid xml', () => {
    expect(() => normalizeCfdi('<cfdi:Comprobante')).toThrow('XML inválido');
  });

  it('throws when Comprobante node is missing', () => {
    const xml = `<?xml version="1.0" encoding="UTF-8"?><root></root>`;
    expect(() => normalizeCfdi(xml)).toThrow('No se encontró el nodo Comprobante');
  });

  it('normalizes a basic ingreso with concept traslados', () => {
    const xml = wrapCfdi(
      `
      <cfdi:Conceptos>
        <cfdi:Concepto Descripcion="Servicio" Cantidad="2" ValorUnitario="50.00" Importe="100.00" ObjetoImp="02">
          <cfdi:Impuestos>
            <cfdi:Traslados>
              <cfdi:Traslado Base="100.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="16.00"/>
            </cfdi:Traslados>
          </cfdi:Impuestos>
        </cfdi:Concepto>
      </cfdi:Conceptos>
      `,
      { SubTotal: '100.00', Total: '116.00' },
    );

    const normalized = normalizeCfdi(xml);

    expect(normalized.tipoDeComprobante).toBe('I');
    expect(normalized.subTotal).toBe(100);
    expect(normalized.total).toBe(116);
    expect(normalized.conceptos).toHaveLength(1);
    expect(normalized.conceptos[0]).toMatchObject({
      descripcion: 'Servicio',
      cantidad: 2,
      valorUnitario: 50,
      importe: 100,
      objetoImp: '02',
    });
    expect(normalized.conceptos[0].traslados).toEqual([
      {
        base: 100,
        impuesto: '002',
        tipoFactor: 'Tasa',
        tasaOCuota: 0.16,
        importe: 16,
      },
    ]);
    expect(normalized.conceptos[0].retenciones).toEqual([]);
  });

  it('normalizes concept retenciones', () => {
    const xml = wrapCfdi(
      `
      <cfdi:Conceptos>
        <cfdi:Concepto Descripcion="Honorarios" Cantidad="1" ValorUnitario="1000.00" Importe="1000.00" ObjetoImp="02">
          <cfdi:Impuestos>
            <cfdi:Retenciones>
              <cfdi:Retencion Base="1000.00" Impuesto="001" TipoFactor="Tasa" TasaOCuota="0.100000" Importe="100.00"/>
            </cfdi:Retenciones>
          </cfdi:Impuestos>
        </cfdi:Concepto>
      </cfdi:Conceptos>
      `,
      { SubTotal: '1000.00', Total: '900.00' },
    );

    const normalized = normalizeCfdi(xml);

    expect(normalized.conceptos[0].retenciones).toEqual([
      {
        base: 1000,
        impuesto: '001',
        tipoFactor: 'Tasa',
        tasaOCuota: 0.1,
        importe: 100,
      },
    ]);
    expect(normalized.conceptos[0].traslados).toEqual([]);
  });

  it('reads global impuestos from Comprobante direct children', () => {
    const xml = wrapCfdi(
      `
      <cfdi:Conceptos>
        <cfdi:Concepto Descripcion="Producto" Cantidad="1" ValorUnitario="100.00" Importe="100.00" ObjetoImp="02" />
      </cfdi:Conceptos>
      <cfdi:Impuestos>
        <cfdi:Traslados>
          <cfdi:Traslado Base="100.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="16.00"/>
        </cfdi:Traslados>
        <cfdi:Retenciones>
          <cfdi:Retencion Base="100.00" Impuesto="001" TipoFactor="Tasa" TasaOCuota="0.040000" Importe="4.00"/>
        </cfdi:Retenciones>
      </cfdi:Impuestos>
      `,
      { SubTotal: '100.00', Total: '112.00' },
    );

    const normalized = normalizeCfdi(xml);

    expect(normalized.resumenImpuestos.traslados).toEqual([
      {
        base: 100,
        impuesto: '002',
        tipoFactor: 'Tasa',
        tasaOCuota: 0.16,
        importe: 16,
      },
    ]);
    expect(normalized.resumenImpuestos.retenciones).toEqual([
      {
        base: 100,
        impuesto: '001',
        tipoFactor: 'Tasa',
        tasaOCuota: 0.04,
        importe: 4,
      },
    ]);
  });

  it('returns empty impuestos arrays when taxes are absent', () => {
    const xml = wrapCfdi(
      `
      <cfdi:Conceptos>
        <cfdi:Concepto Descripcion="Exento" Cantidad="1" ValorUnitario="50.00" Importe="50.00" ObjetoImp="01" />
      </cfdi:Conceptos>
      `,
      { SubTotal: '50.00', Total: '50.00' },
    );

    const normalized = normalizeCfdi(xml);

    expect(normalized.conceptos).toHaveLength(1);
    expect(normalized.conceptos[0].traslados).toEqual([]);
    expect(normalized.conceptos[0].retenciones).toEqual([]);
    expect(normalized.resumenImpuestos.traslados).toEqual([]);
    expect(normalized.resumenImpuestos.retenciones).toEqual([]);
  });
});
