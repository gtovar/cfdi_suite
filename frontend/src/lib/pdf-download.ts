export type PdfConversionState = 'idle' | 'converting' | 'done' | 'error';

function resolveApiBaseUrl() {
  const meta = import.meta as ImportMeta & {
    env?: Record<string, string | undefined>;
  };
  return meta.env?.VITE_API_BASE_URL || '';
}

// Estructura de control para el progreso global de un lote ZIP
export interface BatchProgressPayload {
  status: 'processing' | 'done' | 'error';
  total: number;
  done: number;
  error: number;
  converting: number;
  pending: number;
  percentage: number;
  message?: string;
}

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function waitForPdfJob(jobId: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const es = new EventSource(`/api/cfdi/pdf/${jobId}/progress`);
    const tid = setTimeout(() => {
      es.close();
      reject(new Error('Tiempo de espera agotado'));
    }, 180_000);
    es.onmessage = (ev) => {
      const d = JSON.parse(ev.data) as { status: string; error?: string };
      if (d.status === 'done') { clearTimeout(tid); es.close(); resolve(); }
      if (d.status === 'error') { clearTimeout(tid); es.close(); reject(new Error(d.error || 'Error generando PDF')); }
    };
    es.onerror = () => { clearTimeout(tid); es.close(); reject(new Error('Conexión perdida')); };
  });
}

export async function convertFileToPdf(file: File, templateId?: string): Promise<ArrayBuffer> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('engine', 'canvas_pipeline');
  if (templateId) fd.append('template', JSON.stringify({ _id: templateId }));
  const res = await fetch('/api/cfdi/pdf/start', { method: 'POST', body: fd });
  if (!res.ok) throw new Error(`Error ${res.status} al iniciar conversión`);
  const { jobId } = await res.json() as { jobId: string };
  await waitForPdfJob(jobId);
  const dl = await fetch(`/api/cfdi/pdf/${jobId}/download`);
  if (!dl.ok) throw new Error(`Error ${dl.status} al descargar PDF`);
  return dl.arrayBuffer();
}

// --- NUEVA FUNCIÓN: INICIAR EL PROCESAMIENTO DEL LOTE ZIP ---
export async function startZipConversion(file: File, templateId?: string): Promise<{ batchId: string; totalFiles: number }> {
  const fd = new FormData();
  fd.append('file', file);
  if (templateId) fd.append('template', JSON.stringify({ _id: templateId }));
  
  const res = await fetch(resolveApiBaseUrl() + "/api/cfdi/pdf/start-zip", { method: 'POST', body: fd });
  if (!res.ok) throw new Error(`Error ${res.status} al procesar el lote ZIP en el servidor`);
  return await res.json() as { batchId: string; totalFiles: number };
}

// --- NUEVA FUNCIÓN: ESCUCHAR LA PIZARRA GLOBAL DEL BATCH EN TIEMPO REAL ---
export function waitForBatchJob(batchId: string, onProgress: (data: BatchProgressPayload) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const es = new EventSource(resolveApiBaseUrl() + "/api/cfdi/pdf/batch/" + batchId + "/progress");
    
    // 10 minutos de tiempo límite máximo para lotes de miles de archivos
    const tid = setTimeout(() => {
      es.close();
      reject(new Error('Tiempo de espera del lote agotado en el navegador'));
    }, 600_000);

    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data) as BatchProgressPayload;
      onProgress(data);
      
      if (data.status === 'done') {
        clearTimeout(tid);
        es.close();
        resolve();
      }
      if (data.status === 'error') {
        clearTimeout(tid);
        es.close();
        reject(new Error(data.message || 'Ocurrió un error crítico en el lote'));
      }
    };

    es.onerror = () => {
      clearTimeout(tid);
      es.close();
      reject(new Error('La conexión de progreso en tiempo real se interrumpió'));
    };
  });
}

export class Semaphore {
  private _n: number;
  private _q: (() => void)[] = [];
  constructor(n: number) { this._n = n; }
  acquire(): Promise<void> {
    if (this._n > 0) { this._n--; return Promise.resolve(); }
    return new Promise(r => this._q.push(r));
  }
  release() {
    if (this._q.length) this._q.shift()!();
    else this._n++;
  }
}
