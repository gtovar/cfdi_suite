// @vitest-environment happy-dom

import { act, useEffect } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CfdiAnalysisContractResult, CFDIData } from '../../cfdi/public';
import { renderReact } from '../../test/renderReact';
import { useCfdiAnalysis } from './useCfdiAnalysis';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const analyzeCFDI = vi.fn();

vi.mock('../../lib/cfdi-api-client', () => ({
  analyzeCFDI: (...args: unknown[]) => analyzeCFDI(...args),
}));

const baseCfdi: CFDIData = {
  version: '4.0',
  fecha: '2026-04-17T10:00:00',
  uuid: 'HOOK-TEST-UUID',
  emisor: 'EMISOR SA DE CV',
  receptor: 'RECEPTOR SA DE CV',
  subtotal: 100,
  descuento: 0,
  total: 116,
  conceptos: [],
  impuestosGlobales: [],
  subtotalCalculado: 100,
  totalCalculado: 116,
  hallazgos: [],
  findings: [],
  impactedConceptIndexes: [],
  taxAuditGroups: [],
  verdict: {
    status: 'clean',
    title: 'Sin discrepancias',
    summary: 'Resumen limpio',
  },
  supportText: '',
};

function buildResult(overrides: Partial<CfdiAnalysisContractResult> = {}): CfdiAnalysisContractResult {
  return {
    engine: 'current-ts',
    profile: 'ingreso',
    cfdi: baseCfdi,
    ingresoRows: [],
    pagoRows: [],
    issues: [],
    ...overrides,
  };
}

function HookProbe(props: {
  xml: string;
  onSnapshot: (snapshot: ReturnType<typeof useCfdiAnalysis>) => void;
  onBeforeApply?: (profile: 'ingreso' | 'pagos' | 'unknown') => void;
  onAfterApply?: () => void;
}) {
  const analysis = useCfdiAnalysis();

  useEffect(() => {
    props.onSnapshot(analysis);
  }, [analysis, props]);

  useEffect(() => {
    void analysis.handleFileSelect(props.xml, {
      onBeforeApply: props.onBeforeApply,
      onAfterApply: props.onAfterApply,
    });
  }, [analysis, props]);

  return null;
}

describe('useCfdiAnalysis', () => {
  beforeEach(() => {
    analyzeCFDI.mockReset();
    vi.restoreAllMocks();
    vi.stubGlobal('alert', vi.fn());
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('applies contract results directly without converting to the legacy bundle', async () => {
    analyzeCFDI.mockResolvedValue({
      result: buildResult({
        profile: 'pagos',
        pagoRows: [{ uuidCFDI: '1', fechaCFDI: '2026-04-17', rfcEmisor: 'AAA', rfcReceptor: 'BBB', fechaPago: '2026-04-17', formaPago: '03', monedaP: 'MXN', monto: '116.00', uuidDR: 'DOC-1', serieFolio: 'A-1', parcialidad: '1', impPagado: '116.00', saldoInsoluto: '0.00', baseDR: '100.00', impuestoDR: '002', tipoFactorDR: 'Tasa', tasaCuotaDR: '0.160000', importeDR: '16.00' }],
      }),
      engine: 'api',
      reason: 'api ok',
      meta: {
        contractVersion: 'v1',
        capability: 'analyze_cfdi',
        provider: 'python-satcfdi',
        providerMode: 'bridge',
        degraded: false,
        requestId: 'req-123',
      },
    });

    const alerts: string[] = [];
    const beforeApply = vi.fn();
    const afterApply = vi.fn();
    const snapshots: Array<ReturnType<typeof useCfdiAnalysis>> = [];
    vi.mocked(globalThis.alert).mockImplementation((message?: string) => {
      alerts.push(String(message ?? ''));
    });

    const rendered = renderReact(
      <HookProbe
        xml="<xml />"
        onSnapshot={(snapshot) => snapshots.push(snapshot)}
        onBeforeApply={beforeApply}
        onAfterApply={afterApply}
      />,
    );

    await act(async () => {
      await vi.runAllTimersAsync();
      await Promise.resolve();
    });

    const latest = snapshots.at(-1);

    expect(latest?.profile).toBe('pagos');
    expect(latest?.cfdi?.uuid).toBe('HOOK-TEST-UUID');
    expect(latest?.pagoRows).toHaveLength(1);
    expect(latest?.analysisMeta?.requestId).toBe('req-123');
    expect(latest?.analysisMeta?.providerMode).toBe('bridge');
    expect(beforeApply).toHaveBeenCalledWith('pagos');
    expect(afterApply).toHaveBeenCalled();
    expect(alerts).toEqual([]);

    rendered.unmount();
  });

  it('surfaces fatal contract issues as the current user-facing error', async () => {
    analyzeCFDI.mockResolvedValue({
      result: buildResult({
        cfdi: null,
        issues: [
          {
            code: 'CFDI_PARSE_FAILED',
            message: 'XML invalido',
            stage: 'parse',
            fatal: true,
          },
        ],
      }),
      engine: 'fallback',
      reason: 'fatal',
      meta: undefined,
    });

    const alerts: string[] = [];
    vi.mocked(globalThis.alert).mockImplementation((message?: string) => {
      alerts.push(String(message ?? ''));
    });
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    const rendered = renderReact(
      <HookProbe
        xml="<xml />"
        onSnapshot={() => {}}
      />,
    );

    await act(async () => {
      await vi.runAllTimersAsync();
      await Promise.resolve();
    });

    expect(alerts).toEqual(['Error al procesar el XML. Asegúrate de que sea un CFDI válido.']);
    expect(consoleError).toHaveBeenCalled();

    rendered.unmount();
  });
});
