import type { CfdiAnalysisContractResult } from '../cfdi/public';
import { analyzeCFDIContract } from './cfdi';

export interface CFDIWorkerResponse {
  result: CfdiAnalysisContractResult;
  engine: 'worker' | 'fallback';
  reason?: string;
}

export interface CFDIWorkerProgress {
  label: string;
  progress: number;
  detail?: string;
}

export async function analyzeCFDIWithWorker(
  xml: string,
  onProgress?: (progress: CFDIWorkerProgress) => void
): Promise<CFDIWorkerResponse> {
  if (typeof Worker === 'undefined') {
    onProgress?.({ label: 'Analizando en hilo principal', progress: 100 });
    return {
      result: analyzeCFDIContract(xml),
      engine: 'fallback',
      reason: 'Worker no disponible en este entorno',
    };
  }

  try {
    const worker = new Worker(new URL('./cfdi-worker.ts', import.meta.url), { type: 'module' });

    const result = await new Promise<CfdiAnalysisContractResult>((resolve, reject) => {
      worker.onmessage = (event: MessageEvent<{ ok?: boolean; result?: CfdiAnalysisContractResult; error?: string; progress?: number; label?: string; detail?: string }>) => {
        if (typeof event.data.progress === 'number' && event.data.label) {
          onProgress?.({ progress: event.data.progress, label: event.data.label, detail: event.data.detail });
          return;
        }
        worker.terminate();
        if (event.data.ok && event.data.result) {
          resolve(event.data.result);
          return;
        }
        reject(new Error(event.data.error || 'Error al analizar CFDI en worker'));
      };

      worker.onerror = () => {
        worker.terminate();
        reject(new Error('Worker no disponible'));
      };

      worker.postMessage({ xml });
    });

    return {
      result,
      engine: 'worker',
    };
  } catch (error) {
    onProgress?.({ label: 'Analizando en hilo principal', progress: 100, detail: 'Worker no disponible, se usa procesamiento local completo.' });
    return {
      result: analyzeCFDIContract(xml),
      engine: 'fallback',
      reason: error instanceof Error ? error.message : 'Error desconocido en worker',
    };
  }
}
