export interface BatchFileResult {
  filename: string;
  status: 'ok' | 'con_errores' | 'error';
  profile: 'ingreso' | 'pagos' | 'unknown';
  rfc_emisor: string;
  rfc_receptor: string;
  nombre_emisor: string;
  total: string;
  fecha: string;
  findings_count: number;
  error: string | null;
}

export interface DiotParams {
  year: number;
  month: number;
  rfc_presentante: string;
  razon_social?: string;
}

export interface BatchSummary {
  total_files: number;
  files_ok: number;
  files_con_errores: number;
  files_error: number;
  total_findings: number;
}

export interface BatchAnalyzeResponse {
  results: BatchFileResult[];
  summary: BatchSummary;
}

function makeErrorResult(
  filename: string,
  error: string,
  profile: BatchFileResult['profile'] = 'unknown',
): BatchFileResult {
  return {
    filename,
    status: 'error',
    profile,
    rfc_emisor: '',
    rfc_receptor: '',
    nombre_emisor: '',
    total: '',
    fecha: '',
    findings_count: 0,
    error,
  };
}

export async function batchAnalyze(files: File[]): Promise<BatchAnalyzeResponse> {
  const form = new FormData();
  for (const f of files) {
    form.append('files', f);
  }

  const res = await fetch('/api/cfdi/batch/analyze', {
    method: 'POST',
    body: form,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`La API respondió ${res.status}: ${text}`);
  }

  return res.json() as Promise<BatchAnalyzeResponse>;
}

export async function analyzeOneForBatch(
  file: File,
  signal?: AbortSignal,
): Promise<BatchFileResult> {
  try {
    const xml = await file.text();
    const res = await fetch('/api/cfdi/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ xml }),
      signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      const profile = 'unknown' as BatchFileResult['profile'];
      return makeErrorResult(file.name, `Error ${res.status}: ${text}`, profile);
    }

    const payload = await res.json() as Record<string, unknown>;

    const issues = payload.issues as Array<{ fatal: boolean; message: string }> | undefined;
    if (issues?.some((i) => i.fatal)) {
      const fatalIssue = issues.find((i) => i.fatal);
      return makeErrorResult(
        file.name,
        fatalIssue?.message || 'Error de análisis',
        (payload.profile as BatchFileResult['profile']) || 'unknown',
      );
    }

    const cfdi = payload.cfdi as Record<string, unknown> | null;
    const rawIngresoRows = (payload.ingresoRows as Array<Record<string, string>>) || [];
    const header = (payload.ingresoRowHeader as Record<string, string> | undefined) || {};
    const ingresoRows = Object.keys(header).length > 0
      ? rawIngresoRows.map((r) => ({ ...header, ...r }))
      : rawIngresoRows;
    const pagoRows = (payload.pagoRows as Array<Record<string, string>>) || [];

    const rfcEmisor = (ingresoRows[0]?.rfcEmisor || pagoRows[0]?.rfcEmisor || '').trim();
    const rfcReceptor = (ingresoRows[0]?.rfcReceptor || pagoRows[0]?.rfcReceptor || '').trim();
    const nombreEmisor = ingresoRows[0]?.nombreEmisor || '';
    const findings = (cfdi?.findings as unknown[]) || [];

    return {
      filename: file.name,
      status: findings.length > 0 ? 'con_errores' : 'ok',
      profile: (payload.profile as BatchFileResult['profile']) || 'unknown',
      rfc_emisor: rfcEmisor,
      rfc_receptor: rfcReceptor,
      nombre_emisor: nombreEmisor,
      total: cfdi?.total != null ? String(cfdi.total) : '',
      fecha: cfdi?.fecha ? String(cfdi.fecha).slice(0, 10) : '',
      findings_count: findings.length,
      error: null,
    };
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    return makeErrorResult(file.name, err instanceof Error ? err.message : String(err));
  }
}

export function batchAnalyzePool(
  files: File[],
  onResult: (result: BatchFileResult, index: number) => void,
  concurrency = 8,
): { promise: Promise<void>; cancel: () => void } {
  const controller = new AbortController();
  let cancelled = false;

  const promise = (async () => {
    if (files.length === 0) return;
    const queue: [number, File][] = files.map((f, i) => [i, f]);
    let active = 0;

    await new Promise<void>((resolve) => {
      function next() {
        while (active < concurrency && queue.length > 0) {
          const [idx, file] = queue.shift()!;
          active++;
          analyzeOneForBatch(file, controller.signal)
            .catch((err): BatchFileResult | null => {
              if (err instanceof DOMException && err.name === 'AbortError') return null;
              return makeErrorResult(file.name, err instanceof Error ? err.message : String(err));
            })
            .then((result) => {
              if (result !== null && !cancelled) onResult(result, idx);
              active--;
              if (queue.length === 0 && active === 0) resolve();
              else next();
            });
        }
      }
      next();
    });
  })();

  return {
    promise,
    cancel: () => {
      cancelled = true;
      controller.abort();
    },
  };
}

export async function batchDiot(files: File[], params: DiotParams): Promise<Blob> {
  const form = new FormData();
  for (const f of files) {
    form.append('files', f);
  }
  form.append('year', String(params.year));
  form.append('month', String(params.month));
  form.append('rfc_presentante', params.rfc_presentante);
  form.append('razon_social', params.razon_social ?? '');

  const res = await fetch('/api/cfdi/batch/diot', {
    method: 'POST',
    body: form,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`La API respondió ${res.status}: ${text}`);
  }

  return res.blob();
}
