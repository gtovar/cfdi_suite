import path from 'node:path';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { analyzeCfdiWithPythonSatcfdiEngine } from './pythonSatcfdiEngine';

function fixture(name: string) {
  return readFileSync(path.join(process.cwd(), 'src/cfdi/benchmark/fixtures', name), 'utf8');
}

describe('pythonSatcfdiEngine', () => {
  it('builds structured cfdi output for ingreso fixtures when satcfdi is available', async () => {
    const result = await analyzeCfdiWithPythonSatcfdiEngine(fixture('ingreso-clean.xml'));

    expect(result.engine).toBe('python-satcfdi');
    expect(result.profile).toBe('ingreso');
    expect(result.cfdi?.uuid).toBe('INGRESO-CLEAN-UUID');
    expect(result.ingresoRows).toHaveLength(1);
    expect(result.issues.filter((i) => i.fatal)).toHaveLength(0);
  });

  it('detects pagos profile through the python wrapper', async () => {
    const result = await analyzeCfdiWithPythonSatcfdiEngine(fixture('pagos-clean.xml'));

    expect(result.profile).toBe('pagos');
    expect(result.cfdi?.uuid).toBe('PAGOS-CLEAN-UUID');
    expect(result.pagoRows).toHaveLength(1);
  });

  it('returns parse failure for malformed xml', async () => {
    const result = await analyzeCfdiWithPythonSatcfdiEngine('<cfdi:Comprobante');

    expect(result.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'CFDI_PARSE_FAILED',
          fatal: true,
        }),
      ]),
    );
  });

  it('returns runtime failure when python binary is unavailable', async () => {
    const result = await analyzeCfdiWithPythonSatcfdiEngine(fixture('ingreso-clean.xml'), {
      pythonBinary: 'python3-does-not-exist',
    });

    expect(result.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'ENGINE_RUNTIME_FAILED',
          fatal: true,
        }),
      ]),
    );
  });

  it('returns runtime failure when wrapper emits invalid json', async () => {
    const wrapperPath = path.join(process.cwd(), 'src/cfdi/engine/python-satcfdi-invalid-wrapper.py');
    const result = await analyzeCfdiWithPythonSatcfdiEngine(fixture('ingreso-clean.xml'), {
      wrapperPath,
    });

    expect(result.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'ENGINE_RUNTIME_FAILED',
          fatal: true,
        }),
      ]),
    );
  });
});
