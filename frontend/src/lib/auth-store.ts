const STORAGE_KEY = 'cfdi-suite-auth-token';

let _token: string | null = null;
let _listeners: Array<() => void> = [];

function notify(): void {
  for (const fn of _listeners) fn();
}

export function getAuthToken(): string | null {
  if (_token) return _token;
  try {
    _token = localStorage.getItem(STORAGE_KEY);
  } catch {
    _token = null;
  }
  return _token;
}

export function setAuthToken(token: string): void {
  _token = token;
  try {
    localStorage.setItem(STORAGE_KEY, token);
  } catch { /* localStorage no disponible */ }
  notify();
}

export function clearAuthToken(): void {
  _token = null;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch { /* localStorage no disponible */ }
  notify();
}

export function onAuthChange(fn: () => void): () => void {
  _listeners.push(fn);
  return () => {
    _listeners = _listeners.filter((f) => f !== fn);
  };
}
