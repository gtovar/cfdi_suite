export interface EnquiryRequest {
  uuid: string;
  rfc_emisor: string;
  rfc_receptor: string;
  total_cfdi: string;
  motive: string;
}

export interface EnquiryResult {
  uuid: string;
  estado: string;
  es_cancelable: string;
  estatus_cancelacion: string;
  error: string | null;
}

export type BatchProgressEvent =
  | { type: 'progress'; processed: number; total: number }
  // `download_token`, no `job_id`: el job_id viaja en claro por el SSE y ya no
  // sirve para descargar nada (hallazgo #3). `descartadas` son las filas del
  // Excel cuyo UUID estaba malformado y no se consultaron (#38).
  | { type: 'done'; download_token: string; total: number; descartadas?: number }
  | { type: 'error'; message: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
  return body as T;
}

export async function enquirySingle(data: EnquiryRequest): Promise<EnquiryResult> {
  return request<EnquiryResult>('/api/sat/enquiry', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function downloadBatchResult(downloadToken: string): Promise<void> {
  const res = await fetch(
    `/api/sat/enquiry/batch/result?token=${encodeURIComponent(downloadToken)}`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'consultas_sat.xlsx';
  a.click();
  URL.revokeObjectURL(url);
}

export async function enquiryBatch(
  file: File,
  onEvent: (event: BatchProgressEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch('/api/sat/enquiry/batch', {
    method: 'POST',
    body: formData,
    signal,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const event = JSON.parse(line.slice(6)) as BatchProgressEvent;
        onEvent(event);
      } catch {
        // ignore malformed events
      }
    }
  }
}
