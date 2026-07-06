export type PdfConversionState = 'idle' | 'converting' | 'done' | 'error';

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
