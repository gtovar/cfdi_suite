export type PdfConversionState = 'idle' | 'converting' | 'done' | 'error';

function resolveApiBaseUrl() {
  // @ts-ignore
  const url = import.meta.env.VITE_API_BASE_URL || '';
  console.log("📡 URL BASE PARA ZIP DETECTADA EN PDF-DOWNLOAD:", url);
  return url;
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

//  ESTA ES LA NUEVA FUNCIÓN OPTIMIZADA CON GCS:
export async function startZipConversion(file: File, templateId?: string): Promise<{ batchId: string; totalFiles: number }> {
  const baseUrl = resolveApiBaseUrl();

  // Paso A: Pedirle al backend la URL firmada temporal de Google Cloud Storage
  const resUrl = await fetch(baseUrl + "/api/cfdi/pdf/request-upload", { 
    method: 'POST' 
  });
  if (!resUrl.ok) {
    throw new Error(`Error (${resUrl.status}) al preparar el espacio de subida segura.`);
  }
  const { uploadUrl, gcsPath } = await resUrl.json() as { uploadUrl: string; gcsPath: string };

  // Paso B: Subir el ZIP pesado (los 350 MB) DIRECTO al Bucket de Google Storage usando PUT
  // Aquí es donde evitamos pasar por Cloud Run, por lo que nunca más verás el error 413
  const resUpload = await fetch(uploadUrl, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/zip'
    },
    body: file // Enviamos el archivo binario nativo crudo
  });
  if (!resUpload.ok) {
    throw new Error("No se pudo depositar el archivo en el almacén de la nube. Verifica tu conexión.");
  }

  // Paso C: Avisarle al backend que el archivo ya se encuentra en GCS para que lo procese
  const resProcess = await fetch(baseUrl + "/api/cfdi/pdf/start-zip-gcs", {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      gcsPath: gcsPath,
      template: templateId ? JSON.stringify({ _id: templateId }) : undefined
    })
  });
  if (!resProcess.ok) {
    const errorText = await resProcess.text().catch(() => 'Error desconocido');
    throw new Error(`Error al iniciar la descompresión interna: ${errorText}`);
  }

  // Devolvemos el batchId y totalFiles exactamente igual que antes
  return await resProcess.json() as { batchId: string; totalFiles: number };
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
