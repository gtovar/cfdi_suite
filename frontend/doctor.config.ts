// Configuración de react-doctor — cada supresión tiene un veredicto razonado
// en docs/react-doctor-veredictos.md (§Veredictos emitidos). NO deshabilitar
// reglas aquí sin registrar el veredicto allá primero.
export default {
  rules: {
    // Falso positivo (2026-07-13): los 8 hallazgos son el efecto de
    // restauración mount-only de ConversionMasivaPage.tsx (guardado por
    // restoredBatchRef) — hidratación + arranque de suscripciones, no ajuste
    // de estado por cambio de prop. Reactivar si aparece código nuevo con
    // estado derivado de props real.
    'react-doctor/no-adjust-state-on-prop-change': 'off',

    // Falso positivo (2026-07-13): el único hallazgo (App.tsx) es un
    // EventSource SSE same-origin (/api/...), no un handler de
    // window.postMessage entre ventanas. Reactivar si se agrega mensajería
    // cross-window real.
    'react-doctor/postmessage-origin-risk': 'off',

    // Falso positivo (2026-07-13): el único hallazgo (PdfTemplateBuilder) es
    // un iframe de preview con blob URL creado por nosotros vía
    // URL.createObjectURL — no hay URL controlable por atacante ni flujo de
    // redirect. Reactivar si se agregan redirects con URLs externas.
    'react-doctor/clickjacking-redirect-risk': 'off',

    // NOTA: iframe-missing-sandbox se queda ACTIVA a propósito — veredicto
    // "mejorable": los iframes embeben PDFs propios (blob URLs), pero agregar
    // sandbox requiere prueba manual en navegadores (puede romper el visor de
    // PDF). Ver veredictos doc.

    // Falso positivo (2026-07-13, escalada team agents): el único hallazgo
    // (App.tsx handleDownloadPdf) es un pipeline start→poll→download donde
    // cada await depende del resultado del anterior — no son operaciones
    // independientes candidatas a Promise.all. Reactivar si aparece un fetch
    // paralelo real mal escrito como awaits secuenciales.
    'react-doctor/async-parallel': 'off',
  },
};
