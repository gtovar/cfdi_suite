import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {MotionConfig} from 'motion/react';
import * as Sentry from '@sentry/react';
import App from './App.tsx';
import './index.css';

// El DSN es publicable por diseño (viaja en el bundle de cualquier SPA con
// Sentry). Mientras no exista un proyecto Sentry propio para el frontend,
// se reporta al mismo proyecto que el backend, separado por environment;
// VITE_SENTRY_DSN en Vercel lo puede sobreescribir sin tocar código.
Sentry.init({
  dsn: (import.meta as any).env.VITE_SENTRY_DSN
    || 'https://0b2dd31686cd90353df8ca205a1b0a26@o4511702278340608.ingest.us.sentry.io/4511702363275269',
  environment: `frontend-${(import.meta as any).env.MODE}`,
});

console.log("📡 TODAS LAS VARIABLES VISIBLES POR VITE:", (import.meta as any).env);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </StrictMode>,
);
