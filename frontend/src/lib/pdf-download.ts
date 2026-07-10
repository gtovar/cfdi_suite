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

// ── SSE con reconexión resiliente ─────────────────────────────────────────
// EventSource nativo ya reintenta la conexión por sí solo; el bug histórico
// era que onerror cerraba y fallaba de inmediato, cancelando ese reintento.
// Este helper retoma el control con backoff exponencial y un tope de intentos
// consecutivos (que se resetea con cada mensaje exitoso), sin bloquear al
// usuario con un error ante el primer parpadeo de red.

export type SseConnectionState = 'connected' | 'reconnecting';
type SseMessageResult = { action: 'continue' } | { action: 'resolve' } | { action: 'reject'; error: string };

interface SseRetryConfig {
  url: string;
  overallTimeoutMs: number;
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  onMessage: (raw: string) => SseMessageResult;
  onStatusChange?: (state: SseConnectionState, attempt: number) => void;
}

function subscribeWithRetry(config: SseRetryConfig): Promise<void> {
  const { url, overallTimeoutMs, maxRetries = 5, baseDelayMs = 1000, maxDelayMs = 15_000, onMessage, onStatusChange } = config;

  return new Promise((resolve, reject) => {
    let attempt = 0;
    let es: EventSource;
    let settled = false;

    const overallTid = setTimeout(() => {
      settled = true;
      es?.close();
      reject(new Error('Tiempo de espera agotado en el navegador'));
    }, overallTimeoutMs);

    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(overallTid);
      es.close();
      fn();
    };

    const connect = () => {
      es = new EventSource(url);

      es.onmessage = (ev) => {
        attempt = 0;
        onStatusChange?.('connected', 0);
        const result = onMessage(ev.data);
        if (result.action === 'resolve') finish(resolve);
        if (result.action === 'reject') finish(() => reject(new Error(result.error)));
      };

      es.onerror = () => {
        es.close();
        if (settled) return;
        if (attempt >= maxRetries) {
          finish(() => reject(new Error('La conexión de progreso en tiempo real se interrumpió después de varios intentos')));
          return;
        }
        attempt++;
        onStatusChange?.('reconnecting', attempt);
        const delay = Math.min(baseDelayMs * 2 ** attempt, maxDelayMs);
        setTimeout(connect, delay);
      };
    };

    connect();
  });
}

export function waitForPdfJob(
  jobId: string,
  onStatusChange?: (state: SseConnectionState, attempt: number) => void,
): Promise<void> {
  return subscribeWithRetry({
    url: `/api/cfdi/pdf/${jobId}/progress`,
    overallTimeoutMs: 180_000,
    maxRetries: 3,
    onStatusChange,
    onMessage: (raw) => {
      const d = JSON.parse(raw) as { status: string; error?: string };
      if (d.status === 'done') return { action: 'resolve' };
      if (d.status === 'error') return { action: 'reject', error: d.error || 'Error generando PDF' };
      return { action: 'continue' };
    },
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


export async function startZipConversion(
  file: File, 
  templateId?: string,
  onUploadProgress?: (percent: number) => void // <-- NUEVO: Callback para el Frontend
): Promise<{ batchId: string; totalFiles: number }> {
  const baseUrl = resolveApiBaseUrl();

  // Paso A: Pedirle al backend la URL firmada
  const resUrl = await fetch(baseUrl + "/api/cfdi/pdf/request-upload", { 
    method: 'POST' 
  });
  
  if (!resUrl.ok) {
    if (resUrl.status === 429) {
      throw new Error("El sistema está saturado. Por favor, intenta en unos minutos.");
    }
    throw new Error(`Error (${resUrl.status}) al preparar el espacio de subida segura.`);
  }
  
  const { uploadUrl, gcsPath } = await resUrl.json() as { uploadUrl: string; gcsPath: string };

  // Paso B: Subir el ZIP usando XMLHttpRequest para rastrear el progreso exacto
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', uploadUrl, true);
    xhr.setRequestHeader('Content-Type', 'application/zip');
    
    // Escuchar el progreso de subida de los bytes reales
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onUploadProgress) {
        const percentComplete = Math.round((e.loaded / e.total) * 100);
        onUploadProgress(percentComplete);
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Falló la subida a la nube: ${xhr.statusText}`));
      }
    };
    
    xhr.onerror = () => reject(new Error("Error de red al intentar subir el archivo."));
    xhr.send(file);
  });

  // Paso C: Avisarle al backend que procese el archivo (AQUÍ ES DONDE SUELE SALTAR EL 429 SI SE LLENA)
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
    
    // AQUÍ CACHAMOS EL MICRO-PASO 1 DEL BACKEND
    if (resProcess.status === 429) {
      throw new Error("El motor de procesamiento está a máxima capacidad. Por favor, espera unos minutos e intenta de nuevo.");
    }
    
    throw new Error(`Error al iniciar la descompresión interna: ${errorText}`);
  }

  return await resProcess.json() as { batchId: string; totalFiles: number };
}




// --- ESCUCHAR LA PIZARRA GLOBAL DEL BATCH EN TIEMPO REAL (con reconexión) ---
export function waitForBatchJob(
  batchId: string,
  onProgress: (data: BatchProgressPayload) => void,
  onStatusChange?: (state: SseConnectionState, attempt: number) => void,
): Promise<void> {
  return subscribeWithRetry({
    url: resolveApiBaseUrl() + "/api/cfdi/pdf/batch/" + batchId + "/progress",
    // 45 minutos: con reconexión activa, un lote de miles de archivos puede
    // legítimamente tardar más de los 10 min que teníamos antes.
    overallTimeoutMs: 2_700_000,
    maxRetries: 5,
    onStatusChange,
    onMessage: (raw) => {
      const data = JSON.parse(raw) as BatchProgressPayload;
      onProgress(data);
      if (data.status === 'done') return { action: 'resolve' };
      if (data.status === 'error') return { action: 'reject', error: data.message || 'Ocurrió un error crítico en el lote' };
      return { action: 'continue' };
    },
  });
}

// URL de descarga del ZIP consolidado, directa a Cloud Run — bypasea el
// rewrite de Vercel, que tiene un límite fijo de 120s para destinos
// externos (insuficiente para lotes grandes).
export function getBatchDownloadUrl(batchId: string): string {
  return resolveApiBaseUrl() + "/api/cfdi/pdf/batch/" + batchId + "/download";
}

// IDs de los archivos ya convertidos hasta ahora, para ir llenando la
// tabla de descargas individuales sin esperar a que todo el lote termine.
export async function fetchReadyFileIds(batchId: string): Promise<string[]> {
  const res = await fetch(resolveApiBaseUrl() + "/api/cfdi/pdf/batch/" + batchId + "/ready-files");
  if (!res.ok) return [];
  const data = await res.json() as { jobIds: string[] };
  return data.jobIds;
}

// Signed URL de descarga directa de GCS para un PDF individual — igual que
// el ZIP consolidado, evita pasar por Vercel/Cloud Run para el archivo en sí.
export async function fetchPdfDownloadUrl(jobId: string): Promise<string> {
  const res = await fetch(resolveApiBaseUrl() + "/api/cfdi/pdf/" + jobId + "/download-url");
  if (!res.ok) throw new Error(`Error ${res.status} al generar el enlace de descarga`);
  const data = await res.json() as { downloadUrl: string };
  return data.downloadUrl;
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
