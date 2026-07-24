import type { CfdiAnalysisContractResult } from '../cfdi/public';

export interface CFDIAnalysisMeta {
  contractVersion: string;
  capability: 'analyze_cfdi' | string;
  provider: 'python-satcfdi' | 'current-ts' | string;
  providerMode: 'primary' | 'fallback' | 'comparison' | 'bridge' | string;
  degraded: boolean;
  requestId: string;
  providerVersion?: string | null;
  warnings?: string[];
  timingMs?: number | null;
  fallbackReason?: string | null;
}

export interface CFDIAnalysisResponse {
  result: CfdiAnalysisContractResult;
  engine: 'api';
  meta: CFDIAnalysisMeta;
}

export interface CFDIAnalysisProgress {
  label: string;
  progress: number;
  detail?: string;
}

interface ApiAnalyzeResponse extends Omit<CfdiAnalysisContractResult, 'engine'> {
  meta: CFDIAnalysisMeta;
  ingresoRowHeader?: Record<string, string>;
}

function resolveApiBaseUrl() {
  // @ts-ignore
  return import.meta.env.VITE_API_BASE_URL || '';
}

export async function analyzeCFDI(
  file: File,
  onProgress?: (progress: CFDIAnalysisProgress) => void,
): Promise<CFDIAnalysisResponse> {
  onProgress?.({
    label: 'Subiendo XML a la API',
    progress: 20,
    detail: 'Enviando el archivo al backend Python.',
  });

  const xml = await file.text();
  const response = await fetch(`${resolveApiBaseUrl()}/api/cfdi/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ xml }),
  });

  onProgress?.({
    label: 'Procesando respuesta del backend',
    progress: 76,
    detail: 'Consolidando respuesta contractual para la UI.',
  });

  // Un body contractual válido (con meta.requestId) se usa sin importar el
  // status HTTP -- el backend puede señalar degradación/fallback en el JSON
  // (meta.providerMode), no necesariamente con un status de error (hoy
  // analyze_cfdi siempre responde 200, pero el contrato no lo exige). Se
  // intenta sobre un clone() para no consumir el body real todavía -- lo
  // necesitamos disponible si esto no encuentra un contrato válido.
  const payload = await tryReadContractualPayload(response.clone());
  if (!payload?.meta?.requestId) {
    if (!response.ok) {
      let errorDetail = `La API respondió ${response.status}`;
      try {
        // Intentamos extraer el JSON del error de FastAPI/Python
        const errorData = await response.json();
        if (errorData.detail) {
          // FastAPI suele mandar los errores en la propiedad "detail"
          errorDetail = typeof errorData.detail === 'string'
            ? errorData.detail
            : JSON.stringify(errorData.detail);
        }
      } catch {
        // No es JSON -- se deja el mensaje genérico. Nunca se vuelve a leer
        // el body aquí (antes se intentaba .text() tras el .json() fallido
        // sobre el MISMO Response, lo cual siempre fallaba con "Body is
        // unusable: Body has already been read" en vez del error real).
      }
      // Este throw será atrapado por el catch de useCfdiAnalysis.ts
      throw new Error(errorDetail);
    }
    throw new Error('La API devolvió una respuesta contractual inválida');
  }

  const header = payload.ingresoRowHeader;
  const ingresoRows = (header && Object.keys(header).length > 0)
    ? payload.ingresoRows.map((row) => ({ ...header, ...row }) as import('../cfdi/application/cfdiTypes').CFDIIngresoRow)
    : payload.ingresoRows as import('../cfdi/application/cfdiTypes').CFDIIngresoRow[];

  const result: CfdiAnalysisContractResult = {
    engine: payload.meta.provider === 'current-ts' ? 'current-ts' : 'python-satcfdi',
    profile: payload.profile,
    cfdi: payload.cfdi,
    ingresoRows,
    pagoRows: payload.pagoRows,
    issues: payload.issues,
  };

  onProgress?.({
    label: 'Resultado listo',
    progress: 100,
    detail: payload.profile === 'pagos'
      ? `Filas: ${payload.pagoRows.length.toLocaleString('es-MX')}`
      : `Filas: ${payload.ingresoRows.length.toLocaleString('es-MX')}`,
  });

  return {
    result,
    engine: 'api',
    meta: payload.meta,
  };
}

async function tryReadContractualPayload(response: Response): Promise<ApiAnalyzeResponse | null> {
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) {
    return null;
  }

  try {
    return await response.json() as ApiAnalyzeResponse;
  } catch {
    return null;
  }
}
