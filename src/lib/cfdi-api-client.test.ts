import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { analyzeCFDI } from './cfdi-api-client';

describe('cfdi-api-client', () => {
  beforeEach(() => {
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
    expect(response.meta.requestId).toBe('req-api-1');
    expect(response.meta.providerMode).toBe('bridge');
  });

  it('throws on network errors instead of falling back locally', async () => {
    vi.mocked(globalThis.fetch).mockRejectedValue(new TypeError('network down'));

    await expect(analyzeCFDI('<xml />')).rejects.toThrow('network down');
  });

  it('throws on backend http errors without a contractual body', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response('bad request', { status: 400 }),
    );

    await expect(analyzeCFDI('<xml />')).rejects.toThrow('La API respondió 400');
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
    expect(response.meta.provider).toBe('current-ts');
    expect(response.meta.providerMode).toBe('fallback');
  });
});
