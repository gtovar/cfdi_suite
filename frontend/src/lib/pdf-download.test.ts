import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { downloadWithProgress, fetchZipEstimatedSize, watchBatchProgress } from './pdf-download';

// --- Mock de pusher-js para las pruebas de watchBatchProgress ---
// Expone los mismos métodos que el código real usa (connection.bind,
// subscribe().bind(), unsubscribe, disconnect) para poder disparar eventos
// de progreso y de conexión manualmente desde cada prueba.
const mockChannelHandlers: Record<string, (data: unknown) => void> = {};
const mockConnectionHandlers: Record<string, () => void> = {};
const mockPusherInstance = {
  connection: {
    bind: vi.fn((event: string, cb: () => void) => {
      mockConnectionHandlers[event] = cb;
    }),
  },
  subscribe: vi.fn(() => ({
    bind: vi.fn((event: string, cb: (data: unknown) => void) => {
      mockChannelHandlers[event] = cb;
    }),
  })),
  unsubscribe: vi.fn(),
  disconnect: vi.fn(),
};

vi.mock('pusher-js', () => ({
  // Función regular (no flecha): "new Pusher(...)" en el código real
  // requiere un constructor válido -- las funciones flecha no se pueden
  // invocar con `new`.
  default: vi.fn(function MockPusher() { return mockPusherInstance; }),
}));

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

describe('watchBatchProgress', () => {
  beforeEach(() => {
    for (const k of Object.keys(mockChannelHandlers)) delete mockChannelHandlers[k];
    for (const k of Object.keys(mockConnectionHandlers)) delete mockConnectionHandlers[k];
    mockPusherInstance.unsubscribe.mockClear();
    mockPusherInstance.disconnect.mockClear();
    vi.stubGlobal('fetch', vi.fn());
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ status: 'processing', total: 10, done: 0, error: 0, converting: 0, pending: 10, percentage: 0 }), { status: 200 }),
    );
    // Este archivo corre en entorno "node" (no jsdom); fetchSnapshot revisa
    // document.hidden para no consultar mientras la pestaña está oculta --
    // se stubea el mínimo necesario en vez de traer un entorno DOM completo.
    vi.stubGlobal('document', { hidden: false });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('pide un snapshot inicial al arrancar (Pusher no cuenta la historia)', async () => {
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('NO pide snapshots extra mientras Pusher siga entregando eventos dentro de la ventana de sospecha', async () => {
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0); // snapshot inicial

    // Pusher entrega un tick cada 20s -- por debajo de los 35s de sospecha.
    for (let i = 0; i < 4; i++) {
      await vi.advanceTimersByTimeAsync(20_000);
      mockChannelHandlers['progress']?.({ status: 'processing', total: 10, done: i + 1, error: 0, converting: 0, pending: 10 - i - 1, percentage: (i + 1) * 10 });
    }

    // Solo el snapshot inicial -- ningún poll de sospecha se disparó porque
    // siempre llegó algo antes de que se cumplieran los 35s.
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('SÍ pide un snapshot si no llega nada de Pusher por más de la ventana de sospecha', async () => {
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0); // snapshot inicial

    // Silencio total de Pusher por 36s -- debe disparar la sospecha.
    await vi.advanceTimersByTimeAsync(36_000);

    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('pide un snapshot de inmediato si Pusher reporta "unavailable", sin esperar la ventana de sospecha', async () => {
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0); // snapshot inicial

    mockConnectionHandlers['unavailable']?.();
    await vi.advanceTimersByTimeAsync(0);

    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('resuelve y deja de vigilar cuando el batch termina', async () => {
    const promise = watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0);

    mockChannelHandlers['progress']?.({ status: 'done', total: 10, done: 10, error: 0, converting: 0, pending: 0, percentage: 100 });
    await expect(promise).resolves.toBeUndefined();

    const callsAtFinish = vi.mocked(globalThis.fetch).mock.calls.length;
    await vi.advanceTimersByTimeAsync(60_000); // mucho más que la ventana de sospecha
    expect(globalThis.fetch).toHaveBeenCalledTimes(callsAtFinish); // sin más llamadas después de terminar
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
