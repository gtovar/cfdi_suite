import { describe, expect, it } from 'vitest';
import { explainCfdiField } from './explainCfdiField';

describe('explainCfdiField', () => {
  it('explains known tax codes through catalog labels', () => {
    const explained = explainCfdiField('impuesto', '002');

    expect(explained).toEqual({
      key: 'impuesto',
      rawValue: '002',
      label: 'Impuesto',
      meaning: 'IVA. Codigo SAT 002.',
    });
  });

  it('falls back when tax code is unknown', () => {
    const explained = explainCfdiField('impuesto', '999');

    expect(explained.meaning).toBe('Codigo SAT 999 sin catalogo UI v0.');
  });

  it('explains known tipoFactor values', () => {
    const explained = explainCfdiField('tipoFactor', 'Cuota');

    expect(explained).toEqual({
      key: 'tipoFactor',
      rawValue: 'Cuota',
      label: 'TipoFactor',
      meaning: 'Cuota. Cuota fija.',
    });
  });

  it('explains known objetoImp values', () => {
    const explained = explainCfdiField('objetoImp', '02');

    expect(explained).toEqual({
      key: 'objetoImp',
      rawValue: '02',
      label: 'ObjetoImp',
      meaning: 'Sí objeto de impuesto. Codigo SAT 02.',
    });
  });

  it('explains tasaOCuota with human-readable percent text', () => {
    const explained = explainCfdiField('tasaOCuota', 0.16);

    expect(explained).toEqual({
      key: 'tasaOCuota',
      rawValue: 0.16,
      label: 'TasaOCuota',
      meaning: '0.16. Traduccion humana aproximada: 16%.',
    });
  });

  it('returns generic label and meaning for canonical fields without special handler', () => {
    const explained = explainCfdiField('subTotal', 100);

    expect(explained).toEqual({
      key: 'subTotal',
      rawValue: 100,
      label: 'SubTotal',
      meaning: 'Suma declarada antes de impuestos y descuentos.',
    });
  });

  it('handles null values in special fields', () => {
    expect(explainCfdiField('tipoFactor', null).meaning).toBe('Sin tipo de factor declarado.');
    expect(explainCfdiField('objetoImp', null).meaning).toBe('Sin ObjetoImp declarado.');
    expect(explainCfdiField('tasaOCuota', null).meaning).toBe('Sin tasa o cuota declarada.');
  });

  it('falls back for unknown canonical keys', () => {
    const explained = explainCfdiField('campoInventado', 'x');

    expect(explained).toEqual({
      key: 'campoInventado',
      rawValue: 'x',
      label: 'campoInventado',
      meaning: 'Campo canonico del CFDI v0 sin explicacion especifica adicional.',
    });
  });
});
