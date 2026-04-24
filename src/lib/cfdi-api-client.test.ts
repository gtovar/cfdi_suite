import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { analyzeCFDI } from './cfdi-api-client';

const analyzeCFDIContract = vi.fn();

vi.mock('./cfdi', () => ({
  analyzeCFDIContract: (...args: unknown[]) => analyzeCFDIContract(...args),
}));

describe('cfdi-api-client', () => {
  beforeEach(() => {
    analyzeCFDIContract.mockReset();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('preserves contractual meta from API responses', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({
        profile: 'ingreso',
        cfdi: null,
        ingresoRows: [],
        pagoRows: [],
        issues: [],
        meta: {
          contractVersion: 'v1',
          capability: 'analyze_cfdi',
          provider: 'python-satcfdi',
          providerMode: 'bridge',
          degraded: false,
          requestId: 'req-api-1',
        },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const response = await analyzeCFDI('<xml />');

    expect(response.engine).toBe('api');
    expect(response.meta?.requestId).toBe('req-api-1');
    expect(response.meta?.providerMode).toBe('bridge');
  });

  it('uses fallback only for eligible technical failures', async () => {
    analyzeCFDIContract.mockReturnValue({
      engine: 'current-ts',
      profile: 'unknown',
      cfdi: null,
      ingresoRows: [],
      pagoRows: [],
      issues: [],
    });
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError('network down'));

    const response = await analyzeCFDI('<xml />');

    expect(response.engine).toBe('fallback');
    expect(analyzeCFDIContract).toHaveBeenCalledWith('<xml />');
  });

  it('does not use fallback for backend http errors without a contractual body', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response('bad request', { status: 400 }),
    );

    await expect(analyzeCFDI('<xml />')).rejects.toThrow('La API respondió 400');
    expect(analyzeCFDIContract).not.toHaveBeenCalled();
  });

  it('uses backend contractual fallback responses without invoking local fallback', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({
        profile: 'ingreso',
        cfdi: null,
        ingresoRows: [],
        pagoRows: [],
        issues: [],
        meta: {
          contractVersion: 'v1',
          capability: 'analyze_cfdi',
          provider: 'current-ts',
          providerMode: 'fallback',
          degraded: false,
          requestId: 'req-api-fallback-1',
          fallbackReason: 'provider_runtime_failure',
        },
      }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const response = await analyzeCFDI('<xml />');

    expect(response.engine).toBe('api');
    expect(response.meta?.provider).toBe('current-ts');
    expect(response.meta?.providerMode).toBe('fallback');
    expect(analyzeCFDIContract).not.toHaveBeenCalled();
  });
});
