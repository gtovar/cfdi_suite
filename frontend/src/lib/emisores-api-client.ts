export interface Emisor {
  rfc: string;
  pac: string;
  credential_id: string;
  certificate_number: string;
}

export interface EmisorCreate {
  rfc: string;
  pac: 'diverza';
  credential_id: string;
  credential_token: string;
  certificate_number: string;
}

const BASE = '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json();
  if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
  return body as T;
}

export async function listEmisores(): Promise<Emisor[]> {
  return request<Emisor[]>('/api/emisores');
}

export async function createEmisor(data: EmisorCreate): Promise<Emisor> {
  return request<Emisor>('/api/emisores', { method: 'POST', body: JSON.stringify(data) });
}

export async function updateEmisor(rfc: string, data: EmisorCreate): Promise<Emisor> {
  return request<Emisor>(`/api/emisores/${encodeURIComponent(rfc)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteEmisor(rfc: string): Promise<void> {
  return request<void>(`/api/emisores/${encodeURIComponent(rfc)}`, { method: 'DELETE' });
}
