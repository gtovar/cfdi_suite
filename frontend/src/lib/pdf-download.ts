import Pusher from 'pusher-js';

export type PdfConversionState = 'idle' | 'converting' | 'done' | 'error';

function resolveApiBaseUrl() {
  // @ts-ignore
  const url = import.meta.env.VITE_API_BASE_URL || '';
  console.log("📡 URL BASE PARA ZIP DETECTADA EN PDF-DOWNLOAD:", url);
  return url;
}

// Estructura de control para el progreso global de un lote ZIP
export interface BatchProgressPayload {
  // 'extracting': el ZIP todavía se está desempaquetando y subiendo a GCS —
  // ningún XML ha empezado a convertirse. "percentage" en esta fase es el
  // % ya extraído, no el % convertido (son números distintos a propósito,
  // ver docs/propuesta-arquitectura-batch.md, 2026-07-12).
  status: 'extracting' | 'processing' | 'done' | 'error';
  total: number;
  done: number;
  error: number;
  converting: number;
  pending: number;
  percentage: number;
  message?: string;
  // Solo presente durante status "extracting" — cuántos XMLs ya se subieron.
  extracted?: number;
  // Job IDs terminados desde el tick anterior — evita que el frontend tenga
  // que volver a pedir /ready-files (O(n) sobre todo el batch) en cada tick.
  readyIds?: string[];
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
    let es: EventSource | undefined;
    let settled = false;

    const overallTid = setTimeout(() => {
      settled = true;
      es?.close();
      document.removeEventListener('visibilitychange', onVisibility);
      reject(new Error('Tiempo de espera agotado en el navegador'));
    }, overallTimeoutMs);

    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(overallTid);
      es?.close();
      document.removeEventListener('visibilitychange', onVisibility);
      fn();
    };

    // Pestaña oculta = sin nadie mirando la barra de progreso: cerramos el
    // stream para no quemar comandos de Redis ni retener una instancia de
    // Cloud Run (concurrency=1), y reconectamos al volver a ser visible.
    const onVisibility = () => {
      if (document.hidden) es?.close();
      else if (!settled) connect();
    };
    document.addEventListener('visibilitychange', onVisibility);

    const connect = () => {
      if (settled || document.hidden) return;
      es?.close();
      es = new EventSource(url);

      es.onmessage = (ev) => {
        attempt = 0;
        onStatusChange?.('connected', 0);
        const result = onMessage(ev.data);
        if (result.action === 'resolve') finish(resolve);
        if (result.action === 'reject') finish(() => reject(new Error(result.error)));
      };

      es.onerror = () => {
        es?.close();
        if (settled) return;
        if (document.hidden) return;
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




// --- PROGRESO DEL BATCH VÍA PUSHER (Fase C) ---
// El SSE anterior retenía una instancia entera de Cloud Run por espectador
// (concurrency=1, obligatorio por el bug de heap nativo) y consultaba Redis
// cada segundo. Aquí la conexión persistente vive en la infraestructura de
// Pusher: cero instancias retenidas y cero polling en el caso normal.
//
// Reconciliación por SOSPECHA, no por temporizador fijo (cambiado
// 2026-07-13): la versión anterior pedía un snapshot cada 30s sin importar
// si Pusher ya había entregado todo correctamente -- funcionaba, pero
// preguntaba de más en el caso común (Pusher sano). Aquí, cualquier dato
// real recibido (evento de Pusher O snapshot) reinicia un temporizador de
// "sospecha"; solo si pasan IDLE_SUSPICION_MS sin ninguna noticia se pide
// un snapshot, y también de inmediato si Pusher reporta 'unavailable'. La
// razón de seguir teniendo ESTE respaldo (no solo confiar en el estado de
// conexión de Pusher) es que un socket puede seguir "conectado" y aun así
// perder un mensaje puntual en silencio -- por eso el reloj de sospecha usa
// como verdad "¿ha llegado algo de verdad?", no solo el estado del socket.
const IDLE_SUSPICION_MS = 35_000;

export function watchBatchProgress(
  batchId: string,
  onProgress: (data: BatchProgressPayload) => void,
  onStatusChange?: (state: SseConnectionState, attempt: number) => void,
): Promise<void> {
  // La key de Pusher es pública por diseño (viaja en el bundle de cualquier
  // SPA que use pusher-js); VITE_PUSHER_KEY en Vercel la sobreescribe.
  const key = (import.meta as any).env.VITE_PUSHER_KEY || 'ec582a031473e2da1654'; // pragma: allowlist secret
  const cluster = (import.meta as any).env.VITE_PUSHER_CLUSTER || 'us2';
  const statusUrl = resolveApiBaseUrl() + '/api/cfdi/pdf/batch/' + batchId + '/status';

  return new Promise((resolve, reject) => {
    let settled = false;
    let maxProcessed = -1;
    let pusher: Pusher | null = null;
    let idleTid: ReturnType<typeof setTimeout> | undefined;
    let overallTid: ReturnType<typeof setTimeout> | undefined;

    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      if (overallTid) clearTimeout(overallTid);
      if (idleTid) clearTimeout(idleTid);
      try {
        pusher?.unsubscribe('pdf-batch-' + batchId);
        pusher?.disconnect();
      } catch { /* desconexión best-effort */ }
      fn();
    };

    overallTid = setTimeout(
      () => finish(() => reject(new Error('Tiempo de espera agotado en el navegador'))),
      2_700_000,
    );

    const fetchSnapshot = async () => {
      if (settled || document.hidden) return;
      try {
        const res = await fetch(statusUrl);
        if (res.ok) handle(await res.json() as BatchProgressPayload);
      } catch {
        // Transitorio: si el snapshot en sí falla (red caída), no dejamos
        // de vigilar -- se vuelve a intentar cuando el reloj de sospecha
        // vuelva a cumplirse.
        resetIdleTimer();
      }
    };

    const resetIdleTimer = () => {
      if (idleTid) clearTimeout(idleTid);
      if (settled) return;
      idleTid = setTimeout(() => { void fetchSnapshot(); }, IDLE_SUSPICION_MS);
    };

    const handle = (data: BatchProgressPayload) => {
      if (settled) return;
      resetIdleTimer(); // cualquier dato real -- de Pusher o de un snapshot -- disipa la sospecha
      const processed = (data.done ?? 0) + (data.error ?? 0);
      // Los ticks de Pusher y los snapshots pueden llegar fuera de orden:
      // nunca retroceder la barra mientras el lote siga en proceso.
      if (data.status === 'processing' && processed < maxProcessed) return;
      maxProcessed = Math.max(maxProcessed, processed);
      onProgress(data);
      if (data.status === 'done') finish(resolve);
      else if (data.status === 'error') finish(() => reject(new Error(data.message || 'Ocurrió un error crítico en el lote')));
    };

    pusher = new Pusher(key, { cluster, forceTLS: true });
    pusher.connection.bind('connected', () => onStatusChange?.('connected', 0));
    pusher.connection.bind('unavailable', () => {
      onStatusChange?.('reconnecting', 1);
      // Señal fuerte y explícita de posible pérdida -- se pide un snapshot
      // de inmediato en vez de esperar a que se cumpla el reloj de sospecha.
      void fetchSnapshot();
    });
    pusher.subscribe('pdf-batch-' + batchId).bind('progress', handle);

    void fetchSnapshot(); // snapshot inicial -- Pusher no cuenta la historia, solo eventos nuevos
    resetIdleTimer();
  });
}

// --- ESCUCHAR LA PIZARRA GLOBAL DEL BATCH EN TIEMPO REAL (con reconexión) ---
// Conservado como fallback manual del SSE legacy; el flujo activo usa
// watchBatchProgress (Pusher).
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

// Suma de tamaños (bytes originales) de los PDFs ya generados del lote —
// el ZIP se arma al vuelo en el backend (streaming, sin Content-Length real
// posible), así que esto es lo más cercano a un tamaño total conocido de
// antemano para poder mostrar una barra de progreso real.
export async function fetchZipEstimatedSize(batchId: string): Promise<{ estimatedBytes: number; knownCount: number; totalCount: number } | null> {
  try {
    const res = await fetch(resolveApiBaseUrl() + "/api/cfdi/pdf/batch/" + batchId + "/estimated-size");
    if (!res.ok) return null;
    return await res.json() as { estimatedBytes: number; knownCount: number; totalCount: number };
  } catch {
    return null;
  }
}

// Por encima de este tamaño (estimado), la descarga con fetch + ReadableStream
// se descarta: retiene el archivo completo en memoria del navegador antes de
// poder guardarlo (a diferencia de window.open, que deja al navegador nativo
// ir escribiendo a disco), y un lote muy grande podría tronar la pestaña.
export const ZIP_PROGRESS_SIZE_LIMIT_BYTES = 500 * 1024 * 1024;

// Descarga con progreso real vía fetch + ReadableStream, leyendo los chunks
// conforme llegan. `knownTotal` permite pasar un tamaño estimado externo
// (caso del ZIP, cuyo Content-Length no existe porque se arma al vuelo);
// si no se pasa, se usa el Content-Length de la respuesta (caso de los PDFs
// individuales, que sí lo tienen porque GCS sirve un objeto ya existente).
export async function downloadWithProgress(
  url: string,
  knownTotal: number | null,
  onProgress: (loaded: number, total: number | null) => void,
): Promise<Blob> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Error ${res.status} al descargar`);

  const contentLength = res.headers.get('Content-Length');
  const total = knownTotal ?? (contentLength ? parseInt(contentLength, 10) : null);
  const contentType = res.headers.get('Content-Type') || 'application/octet-stream';

  const reader = res.body?.getReader();
  if (!reader) {
    // Navegador sin soporte de streaming en fetch: sin progreso incremental,
    // pero la descarga en sí sigue funcionando igual.
    const blob = await res.blob();
    onProgress(blob.size, total ?? blob.size);
    return blob;
  }

  const chunks: BlobPart[] = [];
  let loaded = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      chunks.push(value);
      loaded += value.byteLength;
      onProgress(loaded, total);
    }
  }
  return new Blob(chunks, { type: contentType });
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
