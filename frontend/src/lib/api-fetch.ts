import { clearAuthToken, getAuthToken } from './auth-store';

function resolveApiBaseUrl(): string {
  try {
    return (import.meta as any).env.VITE_API_BASE_URL || '';
  } catch {
    return '';
  }
}

export function apiUrl(path: string): string {
  return resolveApiBaseUrl() + path;
}

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const res = await fetch(apiUrl(path), { ...init, headers });
  if (res.status === 401) {
    clearAuthToken();
  }
  return res;
}

export async function apiFetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  const body = await res.json();
  if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
  return body as T;
}
