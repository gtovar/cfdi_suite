/**
 * user-error.ts — un solo camino para los errores que ve el usuario.
 *
 * Hallazgo #4, mitad de frontend. Varios hooks hacían
 * `err instanceof Error ? err.message : 'mensaje por defecto'`, o sea: cuando
 * el error venía con mensaje, se le mostraba tal cual. Eso puede ser el body
 * crudo de un 500 sin manejar (traza del servidor ASGI), una URL interna
 * dentro de un TypeError de fetch, o el texto de una excepción de red.
 *
 * El backend ya dejó de filtrar detalle (mismo hallazgo, mitad de servidor),
 * así que la mayoría de esos mensajes ahora son genéricos de origen. Esto
 * cierra el resto: lo que no venga de nuestra API con un mensaje pensado para
 * el usuario, no se muestra.
 *
 * La regla es la misma que en el backend:
 *
 *     el detalle completo va a Sentry, al usuario le llega un mensaje
 *     genérico en español que describe QUÉ falló, nunca POR QUÉ
 */
import * as Sentry from '@sentry/react';

/** Manda el detalle a Sentry sin producir un mensaje. Nunca lanza. */
export function reportSilently(err: unknown, contexto?: string): void {
  try {
    if (contexto) {
      Sentry.withScope((scope) => {
        scope.setTag('operacion', contexto);
        Sentry.captureException(err);
      });
    } else {
      Sentry.captureException(err);
    }
  } catch {
    /* nunca puede romper el flujo del usuario */
  }
}

/**
 * Mensaje seguro para mostrar en la UI.
 *
 * @param err       lo que atrapó el catch
 * @param fallback  qué falló, en español, desde el punto de vista del usuario
 * @param contexto  etiqueta corta para agrupar en Sentry; no se muestra
 */
export function userMessage(err: unknown, fallback: string, contexto?: string): string {
  try {
    if (contexto) {
      Sentry.withScope((scope) => {
        scope.setTag('operacion', contexto);
        Sentry.captureException(err);
      });
    } else {
      Sentry.captureException(err);
    }
  } catch {
    // El reporte de errores no puede ser, él mismo, una fuente de errores.
  }

  // Un fallo de red del navegador llega como TypeError y no trae nada útil ni
  // sensible; vale la pena distinguirlo porque la acción del usuario es otra
  // (revisar su conexión, no reintentar el mismo archivo).
  if (err instanceof TypeError) {
    return 'No se pudo conectar con el servidor. Revisa tu conexión.';
  }

  return fallback;
}
