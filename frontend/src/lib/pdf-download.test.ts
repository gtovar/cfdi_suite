import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { downloadWithProgress, fetchZipEstimatedSize, watchBatchProgress } from './pdf-download';

// --- Mock de pusher-js para las pruebas de watchBatchProgress ---
// Expone los mismos métodos que el código real usa (connection.bind,
// subscribe().bind(), unsubscribe, disconnect) para poder disparar eventos
// de progreso y de conexión manualmente desde cada prueba.
const mockChannelHandlers: Record<string, (data: unknown) => void> = {};
const mockConnectionHandlers: Record<string, (data?: unknown) => void> = {};
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
  // Este archivo corre en entorno "node" (no jsdom); se stubea un `document`
  // mínimo con hidden + addEventListener/removeEventListener reales (no
  // no-ops) para poder simular visibilitychange desde las pruebas.
  let mockDocument: { hidden: boolean; addEventListener: ReturnType<typeof vi.fn>; removeEventListener: ReturnType<typeof vi.fn> };
  let visibilityListeners: Array<() => void>;

  const fireVisibilityChange = (hidden: boolean) => {
    mockDocument.hidden = hidden;
    for (const cb of visibilityListeners) cb();
  };

  beforeEach(() => {
    for (const k of Object.keys(mockChannelHandlers)) delete mockChannelHandlers[k];
    for (const k of Object.keys(mockConnectionHandlers)) delete mockConnectionHandlers[k];
    mockPusherInstance.unsubscribe.mockClear();
    mockPusherInstance.disconnect.mockClear();
    vi.stubGlobal('fetch', vi.fn());
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ status: 'processing', total: 10, done: 0, error: 0, converting: 0, pending: 10, percentage: 0 }), { status: 200 }),
    );

    visibilityListeners = [];
    mockDocument = {
      hidden: false,
      addEventListener: vi.fn((event: string, cb: () => void) => {
        if (event === 'visibilitychange') visibilityListeners.push(cb);
      }),
      removeEventListener: vi.fn((event: string, cb: () => void) => {
        if (event === 'visibilitychange') {
          const idx = visibilityListeners.indexOf(cb);
          if (idx >= 0) visibilityListeners.splice(idx, 1);
        }
      }),
    };
    vi.stubGlobal('document', mockDocument);
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

  it('la red de seguridad SOBREVIVE a una respuesta no exitosa -- vuelve a dispararse en su propio reloj', async () => {
    // Regresión directa del defecto que motivó el rediseño: con el diseño
    // anterior, una sola respuesta no-ok desarmaba el mecanismo para
    // siempre. Aquí el setInterval es independiente del resultado de
    // cualquier intento individual.
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0); // snapshot inicial (call #1, ok)

    vi.mocked(globalThis.fetch).mockResolvedValueOnce(new Response(null, { status: 503 }));
    await vi.advanceTimersByTimeAsync(75_000); // primer disparo de la red de seguridad (call #2, no-ok)
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(75_000); // segundo disparo -- debe seguir latiendo
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
  });

  it('la red de seguridad SOBREVIVE a la pestaña oculta -- vuelve a dispararse en su propio reloj', async () => {
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0); // snapshot inicial (call #1)

    mockDocument.hidden = true;
    await vi.advanceTimersByTimeAsync(75_000); // primer disparo: sale temprano por hidden, sin fetch nuevo
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    mockDocument.hidden = false;
    await vi.advanceTimersByTimeAsync(75_000); // segundo disparo: el intervalo nunca se detuvo
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('un state_change que sale de "connected" dispara una reconciliación inmediata', async () => {
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0); // snapshot inicial

    mockConnectionHandlers['state_change']?.({ previous: 'connected', current: 'unavailable' });
    await vi.advanceTimersByTimeAsync(0);

    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('un state_change que REGRESA a "connected" también dispara una reconciliación (el hueco real de pérdida de Pusher)', async () => {
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0);

    mockConnectionHandlers['state_change']?.({ previous: 'unavailable', current: 'connected' });
    await vi.advanceTimersByTimeAsync(0);

    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('volver a primer plano (visibilitychange) dispara una reconciliación inmediata', async () => {
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0); // snapshot inicial

    fireVisibilityChange(true); // se oculta -- no debe disparar nada
    await vi.advanceTimersByTimeAsync(0);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    fireVisibilityChange(false); // vuelve a primer plano -- sí reconcilia
    await vi.advanceTimersByTimeAsync(0);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('NO pide snapshots extra mientras Pusher solo entregue ticks normales de progreso', async () => {
    watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0); // snapshot inicial

    // 3 ticks de 20s = 60s transcurridos, por debajo del primer disparo de
    // la red de seguridad (75s) -- confirma que los ticks de progreso en sí
    // mismos no generan ninguna llamada a fetch, sin cruzar el reloj
    // independiente de la red de seguridad (probado aparte).
    for (let i = 0; i < 3; i++) {
      await vi.advanceTimersByTimeAsync(20_000);
      mockChannelHandlers['progress']?.({ status: 'processing', total: 10, done: i + 1, error: 0, converting: 0, pending: 10 - i - 1, percentage: (i + 1) * 10 });
    }

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('resuelve y deja de vigilar (incluida la red de seguridad y el listener de visibilitychange) cuando el batch termina', async () => {
    const promise = watchBatchProgress('batch-1', () => {});
    await vi.advanceTimersByTimeAsync(0);

    mockChannelHandlers['progress']?.({ status: 'done', total: 10, done: 10, error: 0, converting: 0, pending: 0, percentage: 100 });
    await expect(promise).resolves.toBeUndefined();

    const callsAtFinish = vi.mocked(globalThis.fetch).mock.calls.length;
    await vi.advanceTimersByTimeAsync(200_000); // varias veces el intervalo de la red de seguridad
    expect(globalThis.fetch).toHaveBeenCalledTimes(callsAtFinish);

    // El listener de visibilitychange también se limpia -- una reconciliación
    // manual después de terminar no debería hacer nada.
    fireVisibilityChange(true);
    fireVisibilityChange(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(globalThis.fetch).toHaveBeenCalledTimes(callsAtFinish);
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
