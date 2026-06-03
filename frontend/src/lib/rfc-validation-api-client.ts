export interface RfcFormatResult {
  rfc: string;
  formatoValido: boolean;
  digitoVerificador: boolean;
  tipo: 'FISICA' | 'MORAL' | null;
  esGenerico: boolean;
  error: string | null;
}

export interface RfcSatResult {
  rfc: string;
  existeEnLrfc: boolean | null;
  razonSocialValida: boolean | null;
  error: string | null;
}

export interface FielStatus {
  configurada: boolean;
  rfc: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
  return body as T;
}

export async function validateRfcFormat(rfc: string, razonSocial?: string): Promise<RfcFormatResult> {
  return request<RfcFormatResult>('/api/rfc/validate/format', {
    method: 'POST',
    body: JSON.stringify({ rfc, razonSocial: razonSocial ?? null }),
  });
}

export async function validateRfcSat(rfc: string, razonSocial?: string): Promise<RfcSatResult> {
  return request<RfcSatResult>('/api/rfc/validate/sat', {
    method: 'POST',
    body: JSON.stringify({ rfc, razonSocial: razonSocial ?? null }),
  });
}

export async function getFielStatus(): Promise<FielStatus> {
  return request<FielStatus>('/api/fiel/status');
}

export async function configureFiel(cer: File, key: File, password: string): Promise<FielStatus> {
  const form = new FormData();
  form.append('cer', cer);
  form.append('key', key);
  form.append('password', password);
  const res = await fetch('/api/fiel/configure', { method: 'POST', body: form });
  const body = await res.json();
  if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
  return body as FielStatus;
}

export async function deleteFiel(): Promise<FielStatus> {
  return request<FielStatus>('/api/fiel/', { method: 'DELETE' });
}
