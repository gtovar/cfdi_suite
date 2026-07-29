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
const fetchZipEstimatedSize = vi.fn(async () => null as { estimatedBytes: number; knownCount: number; totalCount: number } | null);
const convertFileToPdf = vi.fn();

vi.mock('../lib/pdf-download', async () => {
  const actual = await vi.importActual<typeof import('../lib/pdf-download')>('../lib/pdf-download');
  return {
    ...actual,
    watchBatchProgress: (...args: Parameters<typeof watchBatchProgress>) => watchBatchProgress(...args),
    fetchReadyFileIds: (...args: Parameters<typeof fetchReadyFileIds>) => fetchReadyFileIds(...args),
    fetchZipEstimatedSize: (...args: Parameters<typeof fetchZipEstimatedSize>) => fetchZipEstimatedSize(...args),
    convertFileToPdf: (...args: Parameters<typeof convertFileToPdf>) => convertFileToPdf(...args),
  };
});

// Import dinámico tras el mock — vitest hoists vi.mock, pero mantenemos el
// import normal arriba del módulo para que TypeScript resuelva tipos.
import ConversionMasivaPage from './ConversionMasivaPage';

const ACTIVE_BATCH_KEY = 'cfdi-active-batch';
const PENDING_LOOSE_FILES_KEY = 'cfdi-pending-loose-files';

function seedActiveBatch(startedAt: number, batchId = 'batch-abc', total = 5) {
  localStorage.setItem(ACTIVE_BATCH_KEY, JSON.stringify({ batchId, total, startedAt }));
}

describe('ConversionMasivaPage — recuperación de lote (Fase 3)', () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    localStorage.clear();
    watchBatchProgress.mockClear();
    fetchReadyFileIds.mockClear();
    fetchZipEstimatedSize.mockClear();
    convertFileToPdf.mockClear();
    fetchZipEstimatedSize.mockResolvedValue(null);
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

  it('explica qué pasó con XMLs sueltos tras un refresh sin prometer restaurarlos', () => {
    sessionStorage.setItem(PENDING_LOOSE_FILES_KEY, JSON.stringify({
      count: 150,
      totalBytes: 629_527_686,
      savedAt: Date.now(),
    }));
    ({ container } = renderReact(<ConversionMasivaPage />));

    expect(container.textContent).toContain('150 XMLs');
    expect(container.textContent).toContain('no puede restaurar sus archivos');
  });

  it('un lote durable de XML sueltos descarga el ZIP del backend y nunca reconvierte los XML', async () => {
    const batchId = 'loose-durable-150';
    const jobs = Array.from({ length: 3 }, (_, index) => ({
      jobId: `job-${index + 1}`,
      filename: `factura-${index + 1}.xml`,
      size: 100,
      state: 'done' as const,
      schedulingAttempts: 0,
    }));
    localStorage.setItem(ACTIVE_BATCH_KEY, JSON.stringify({ batchId, total: jobs.length, startedAt: Date.now(), kind: 'loose' }));
    sessionStorage.setItem(PENDING_LOOSE_FILES_KEY, JSON.stringify({
      count: jobs.length, totalBytes: 300, savedAt: Date.now(), batchId, jobs,
    }));
    fetchZipEstimatedSize.mockResolvedValueOnce({ estimatedBytes: 0, knownCount: 0, totalCount: jobs.length });
    const assign = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', { configurable: true, value: { ...originalLocation, assign } });

    try {
      await act(async () => {
        ({ container } = renderReact(<ConversionMasivaPage />));
        await flushMicrotasks();
      });
      const button = Array.from(container.querySelectorAll('button')).find((item) =>
        item.textContent?.includes('Descargar todos (ZIP)'),
      );
      expect(button).toBeTruthy();
      await act(async () => {
        button!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await flushMicrotasks();
      });
      expect(assign).toHaveBeenCalledWith(expect.stringContaining(`/batch/${batchId}/download`));
      expect(convertFileToPdf).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    }
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

  // Reproduce el hallazgo real de producción 2026-07-24: si Redis pierde el
  // detalle de status de un lote, batchProgress.status puede quedarse en
  // "processing" (degradado) para siempre, aunque todos los PDFs ya existan
  // en Storage -- list_ready_files sí los ve (reconcilia contra GCS). El
  // botón de descarga no debe depender solo de status === 'done'.
  it('el botón de descarga aparece vía readyFileIds aunque el status se quede degradado para siempre', async () => {
    fetchReadyFileIds.mockResolvedValueOnce(['job-1', 'job-2', 'job-3', 'job-4', 'job-5']);
    watchBatchProgress.mockImplementationOnce(async (_id, onProgress) => {
      onProgress({
        status: 'processing',
        total: 5,
        done: 0,
        error: 0,
        converting: 0,
        pending: 5,
        percentage: 0,
      });
      return new Promise<void>(() => {}); // nunca resuelve -- status nunca llega a "done"
    });

    await act(async () => {
      ({ container } = renderReact(<ConversionMasivaPage restoreBatchId="shared-xyz" />));
      await flushMicrotasks();
    });

    const zipButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Descargar paquete de PDFs final')
      || b.textContent?.includes('Descargar los'),
    );
    expect(zipButton).toBeTruthy();
    expect(container.textContent).toContain('Lote completado con éxito');
  });

  it('con solo algunos archivos listos, el botón ofrece la descarga parcial con su propia etiqueta', async () => {
    fetchReadyFileIds.mockResolvedValueOnce(['job-1', 'job-2']); // solo 2 de 5
    watchBatchProgress.mockImplementationOnce(async (_id, onProgress) => {
      onProgress({ status: 'processing', total: 5, done: 2, error: 0, converting: 1, pending: 2, percentage: 40 });
      return new Promise<void>(() => {});
    });

    await act(async () => {
      ({ container } = renderReact(<ConversionMasivaPage restoreBatchId="shared-xyz" />));
      await flushMicrotasks();
    });

    const zipButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Descargar los 2 de 5 listos'),
    );
    expect(zipButton).toBeTruthy();
    // Todavía no está "completo" -- ni el badge ni el banner de "listo" deben mostrarse.
    expect(container.textContent).not.toContain('Lote completado con éxito');
  });

  it('sin ningún archivo listo, el botón de descarga no aparece', async () => {
    fetchReadyFileIds.mockResolvedValueOnce([]);
    watchBatchProgress.mockImplementationOnce(async (_id, onProgress) => {
      onProgress({ status: 'processing', total: 5, done: 0, error: 0, converting: 1, pending: 4, percentage: 0 });
      return new Promise<void>(() => {});
    });

    await act(async () => {
      ({ container } = renderReact(<ConversionMasivaPage restoreBatchId="shared-xyz" />));
      await flushMicrotasks();
    });

    const zipButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Descargar paquete de PDFs final')
      || b.textContent?.includes('Descargar los'),
    );
    expect(zipButton).toBeFalsy();
  });

  // El botón de descarga ahora es alcanzable durante una degradación (tests
  // de arriba) -- eso expone el estimado de tamaño (batch_estimated_size) a
  // un caso que antes casi nunca se ejercitaba con el botón visible: Redis
  // sin los tamaños de ningún PDF (knownCount: 0) durante la misma caída. Si
  // eso se tratara como "0 bytes" en vez de "desconocido", handleDownloadBatchZip
  // tomaría el camino de fetch + ReadableStream (retiene el ZIP completo en
  // memoria) en vez de la descarga nativa -- para un lote grande, eso
  // tronaría la pestaña.
  it('con el estimado degradado (knownCount: 0) la descarga cae a la ruta nativa, no a la de memoria', async () => {
    fetchReadyFileIds.mockResolvedValueOnce(['job-1', 'job-2', 'job-3', 'job-4', 'job-5']);
    fetchZipEstimatedSize.mockResolvedValueOnce({ estimatedBytes: 0, knownCount: 0, totalCount: 5 });
    watchBatchProgress.mockImplementationOnce(async (_id, onProgress) => {
      onProgress({ status: 'processing', total: 5, done: 0, error: 0, converting: 0, pending: 5, percentage: 0 });
      return new Promise<void>(() => {});
    });

    const assign = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, assign },
    });

    try {
      await act(async () => {
        ({ container } = renderReact(<ConversionMasivaPage restoreBatchId="shared-xyz" />));
        await flushMicrotasks();
      });

      const zipButton = Array.from(container.querySelectorAll('button')).find((b) =>
        b.textContent?.includes('Descargar paquete de PDFs final')
        || b.textContent?.includes('Descargar los'),
      );
      expect(zipButton).toBeTruthy();

      await act(async () => {
        zipButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await flushMicrotasks();
      });

      expect(assign).toHaveBeenCalledWith(expect.stringContaining('shared-xyz'));
      expect(container.textContent).not.toContain('Descargando ZIP');
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
    }
  });
});
