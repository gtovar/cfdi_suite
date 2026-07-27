import { type ReactNode, useCallback, useEffect, useState, type FormEvent } from 'react';
import { getAuthToken, onAuthChange, setAuthToken } from '../lib/auth-store';

interface Props {
  children: ReactNode;
}

export default function AuthGate({ children }: Props) {
  const [token, setToken] = useState<string | null>(() => getAuthToken());
  const [input, setInput] = useState('');
  const [error, setError] = useState('');

  useEffect(() => onAuthChange(() => setToken(getAuthToken())), []);

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      const trimmed = input.trim();
      if (!trimmed) {
        setError('Ingresa el token de acceso');
        return;
      }
      setError('');
      setAuthToken(trimmed);
    },
    [input],
  );

  if (token) return <>{children}</>;

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        backgroundColor: '#111827',
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: '100%',
          maxWidth: 400,
          padding: '2rem',
          borderRadius: 8,
          backgroundColor: '#1f2937',
        }}
      >
        <h1 style={{ color: '#f9fafb', fontSize: '1.25rem', marginBottom: '1.5rem' }}>
          cfdi-suite
        </h1>
        <label
          style={{ display: 'block', color: '#d1d5db', fontSize: '0.875rem', marginBottom: '0.5rem' }}
        >
          Token de acceso
        </label>
        <input
          type="password"
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onInput={() => error && setError('')}
          style={{
            width: '100%',
            padding: '0.625rem 0.75rem',
            backgroundColor: '#374151',
            border: '1px solid #4b5563',
            borderRadius: 6,
            color: '#f9fafb',
            fontSize: '0.9375rem',
            boxSizing: 'border-box',
          }}
        />
        {error && (
          <p style={{ color: '#fca5a5', fontSize: '0.8125rem', marginTop: '0.5rem' }}>
            {error}
          </p>
        )}
        <button
          type="submit"
          style={{
            width: '100%',
            marginTop: '1rem',
            padding: '0.625rem',
            backgroundColor: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            fontSize: '0.9375rem',
            cursor: 'pointer',
          }}
        >
          Acceder
        </button>
      </form>
    </div>
  );
}
