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
