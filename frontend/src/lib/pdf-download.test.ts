import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { downloadWithProgress, fetchZipEstimatedSize } from './pdf-download';

function streamResponse(chunks: Uint8Array[], headers: Record<string, string> = {}): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers });
}

describe('downloadWithProgress', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reports incremental progress using Content-Length when no external total is given', async () => {
    const chunkA = new Uint8Array(1000);
    const chunkB = new Uint8Array(500);
    vi.mocked(globalThis.fetch).mockResolvedValue(
      streamResponse([chunkA, chunkB], { 'Content-Length': '1500', 'Content-Type': 'application/pdf' }),
    );

    const progressCalls: Array<{ loaded: number; total: number | null }> = [];
    const blob = await downloadWithProgress('https://example.com/pdf', null, (loaded, total) => {
      progressCalls.push({ loaded, total });
    });

    expect(progressCalls).toEqual([
      { loaded: 1000, total: 1500 },
      { loaded: 1500, total: 1500 },
    ]);
    expect(blob.size).toBe(1500);
    expect(blob.type).toBe('application/pdf');
  });

  it('uses the externally supplied total when the response has no Content-Length (streamed ZIP case)', async () => {
    const chunkA = new Uint8Array(2000);
    vi.mocked(globalThis.fetch).mockResolvedValue(streamResponse([chunkA], { 'Content-Type': 'application/zip' }));

    const progressCalls: Array<{ loaded: number; total: number | null }> = [];
    const blob = await downloadWithProgress('https://example.com/zip', 4_000_000, (loaded, total) => {
      progressCalls.push({ loaded, total });
    });

    expect(progressCalls).toEqual([{ loaded: 2000, total: 4_000_000 }]);
    expect(blob.size).toBe(2000);
  });

  it('throws when the response is not ok', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(new Response(null, { status: 404 }));
    await expect(downloadWithProgress('https://example.com/missing', null, () => {})).rejects.toThrow('404');
  });
});

describe('fetchZipEstimatedSize', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the parsed estimate on success', async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ estimatedBytes: 3_145_728, knownCount: 2, totalCount: 3 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const result = await fetchZipEstimatedSize('batch-1');
    expect(result).toEqual({ estimatedBytes: 3_145_728, knownCount: 2, totalCount: 3 });
  });

  it('returns null when the request fails outright', async () => {
    vi.mocked(globalThis.fetch).mockRejectedValue(new Error('network down'));
    const result = await fetchZipEstimatedSize('batch-1');
    expect(result).toBeNull();
  });
});
