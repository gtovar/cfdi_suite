// @vitest-environment happy-dom

import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderReact } from '../test/renderReact';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function flushMicrotasks() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

const watchBatchProgress = vi.fn(() => new Promise<void>(() => {})); // nunca resuelve — solo probamos si se llamó
const fetchReadyFileIds = vi.fn(async () => []);

vi.mock('../lib/pdf-download', async () => {
  const actual = await vi.importActual<typeof import('../lib/pdf-download')>('../lib/pdf-download');
  return {
    ...actual,
    watchBatchProgress: (...args: Parameters<typeof watchBatchProgress>) => watchBatchProgress(...args),
    fetchReadyFileIds: (...args: Parameters<typeof fetchReadyFileIds>) => fetchReadyFileIds(...args),
  };
});

// Import dinámico tras el mock — vitest hoists vi.mock, pero mantenemos el
// import normal arriba del módulo para que TypeScript resuelva tipos.
import ConversionMasivaPage from './ConversionMasivaPage';

const ACTIVE_BATCH_KEY = 'cfdi-active-batch';

function seedActiveBatch(startedAt: number, batchId = 'batch-abc', total = 5) {
  localStorage.setItem(ACTIVE_BATCH_KEY, JSON.stringify({ batchId, total, startedAt }));
}

describe('ConversionMasivaPage — recuperación de lote (Fase 3)', () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    localStorage.clear();
    watchBatchProgress.mockClear();
    fetchReadyFileIds.mockClear();
  });

  afterEach(() => {
    container?.remove();
  });

  it('restaura un lote de hace 46 minutos — con el tope viejo de 45 min se habría perdido', () => {
    seedActiveBatch(Date.now() - 46 * 60 * 1000);
    ({ container } = renderReact(<ConversionMasivaPage />));

    expect(watchBatchProgress).toHaveBeenCalledWith('batch-abc', expect.any(Function), expect.any(Function));
    expect(container.textContent).toContain('Recuperamos tu lote anterior');
    expect(localStorage.getItem(ACTIVE_BATCH_KEY)).not.toBeNull();
  });

  it('NO restaura un lote de hace más de 24h — respeta el nuevo tope, no lo elimina', () => {
    seedActiveBatch(Date.now() - 25 * 60 * 60 * 1000);
    ({ container } = renderReact(<ConversionMasivaPage />));

    expect(watchBatchProgress).not.toHaveBeenCalled();
    expect(container.textContent).not.toContain('Recuperamos tu lote anterior');
    expect(localStorage.getItem(ACTIVE_BATCH_KEY)).toBeNull();
  });

  it('restaura un lote de hace 23h59m — dentro del nuevo tope de 24h', () => {
    seedActiveBatch(Date.now() - (23 * 60 + 59) * 60 * 1000);
    ({ container } = renderReact(<ConversionMasivaPage />));

    expect(watchBatchProgress).toHaveBeenCalledWith('batch-abc', expect.any(Function), expect.any(Function));
    expect(container.textContent).toContain('Recuperamos tu lote anterior');
  });

  it('restoreBatchId (link compartido) tiene prioridad y no requiere localStorage', () => {
    ({ container } = renderReact(<ConversionMasivaPage restoreBatchId="shared-xyz" />));

    expect(watchBatchProgress).toHaveBeenCalledWith('shared-xyz', expect.any(Function), expect.any(Function));
    expect(fetchReadyFileIds).toHaveBeenCalledWith('shared-xyz');
    expect(container.textContent).toContain('Recuperamos tu lote anterior');
  });

  it('muestra el link persistente con el batch_id cuando hay un lote activo', () => {
    ({ container } = renderReact(<ConversionMasivaPage restoreBatchId="shared-xyz" />));

    const input = container.querySelector('input[readonly]') as HTMLInputElement | null;
    expect(input?.value).toContain('shared-xyz');
    expect(input?.value).toContain('?batch=shared-xyz');
  });

  it('propaga progreso a onProgressUpdate desde que arranca, sin esperar el primer snapshot', () => {
    // watchBatchProgress está mockeado para nunca resolver/llamar a onProgress
    // en este test — simula el hueco real donde el primer fetch de /status
    // tarda o falla. El widget flotante (App.tsx) depende de que este
    // callback se dispare igual, aunque sea con total desconocido (0).
    const onProgressUpdate = vi.fn();
    ({ container } = renderReact(
      <ConversionMasivaPage restoreBatchId="shared-xyz" onProgressUpdate={onProgressUpdate} />,
    ));

    expect(onProgressUpdate).toHaveBeenCalledWith({ completed: 0, total: 0, phase: 'processing' });
  });

  it('el botón Copiar link copia la URL con el batch_id al portapapeles', async () => {
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });

    ({ container } = renderReact(<ConversionMasivaPage restoreBatchId="shared-xyz" />));
    const copyButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Copiar link'),
    );
    expect(copyButton).toBeTruthy();
    copyButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await Promise.resolve();

    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('?batch=shared-xyz'));
  });

  // watchBatchProgress() solo produce exactamente 2 mensajes de rechazo
  // reales (ver pdf-download.ts): timeout de cliente (el batch sigue vivo
  // en el servidor -- banner ámbar, se puede reintentar la conexión) o un
  // error crítico reportado por el servidor vía Pusher (el batch murió de
  // verdad -- banner rojo, no tiene caso "reintentar conexión", solo limpiar
  // y empezar de nuevo).
  it('banner ámbar + "Reintentar conexión" cuando se agota el timeout del navegador', async () => {
    // El banner de error vive dentro de {isZipMode && batchProgress && (...)}
    // -- en producción real siempre llegan ticks de progreso antes de un
    // timeout/error, así que el mock debe simular al menos uno primero.
    watchBatchProgress.mockImplementationOnce(async (_id, onProgress) => {
      onProgress({ status: 'processing', total: 5, done: 1, error: 0, converting: 1, pending: 3, percentage: 20 });
      throw new Error('Tiempo de espera agotado en el navegador');
    });

    await act(async () => {
      ({ container } = renderReact(<ConversionMasivaPage restoreBatchId="shared-xyz" />));
      await flushMicrotasks();
    });

    expect(container.textContent).toContain(
      'Se perdió la conexión de progreso en tiempo real, pero tu lote sigue procesándose en la nube.',
    );
    expect(container.textContent).not.toContain('Error en el lote');

    const retryButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Reintentar conexión'),
    );
    expect(retryButton).toBeTruthy();
  });

  it('banner ROJO + "Limpiar y empezar" cuando el servidor reporta un error crítico real', async () => {
    watchBatchProgress.mockImplementationOnce(async (_id, onProgress) => {
      onProgress({ status: 'processing', total: 5, done: 1, error: 0, converting: 1, pending: 3, percentage: 20 });
      throw new Error('Ocurrió un error crítico en el lote');
    });

    await act(async () => {
      ({ container } = renderReact(<ConversionMasivaPage restoreBatchId="shared-xyz" />));
      await flushMicrotasks();
    });

    expect(container.textContent).toContain('Error en el lote: Ocurrió un error crítico en el lote');

    const clearButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Limpiar y empezar'),
    );
    expect(clearButton).toBeTruthy();

    act(() => {
      clearButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(container.textContent).not.toContain('Error en el lote');
  });
});
