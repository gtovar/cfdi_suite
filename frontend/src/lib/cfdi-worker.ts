import { detectCfdiProfile } from '../cfdi/application/cfdiAnalysisService';
import { analyzeCfdiWithCurrentTsEngine } from '../cfdi/engine/currentTsEngine';

self.onmessage = async (event: MessageEvent<{ xml: string }>) => {
  try {
    const { xml } = event.data;
    self.postMessage({ progress: 8, label: 'Detectando perfil CFDI', detail: 'Leyendo estructura base del comprobante.' });
    const profile = detectCfdiProfile(xml);

    self.postMessage({ progress: 28, label: 'Calculando diagnóstico fiscal', detail: `Perfil detectado: ${profile}.` });
    const result = analyzeCfdiWithCurrentTsEngine(xml);
    const fatalIssue = result.issues.find((issue) => issue.fatal);
    if (fatalIssue || !result.cfdi) {
      throw new Error(fatalIssue?.message || 'No se pudo construir el analisis CFDI');
    }

    self.postMessage({
      progress: 72,
      label: profile === 'pagos' ? 'Extrayendo filas de pagos' : 'Extrayendo filas de ingresos',
      detail: `${result.cfdi.conceptos.length.toLocaleString('es-MX')} conceptos detectados · ${result.cfdi.findings.length.toLocaleString('es-MX')} hallazgos.`,
    });

    const finalDetail =
      profile === 'pagos'
        ? `Filas: ${result.pagoRows.length.toLocaleString('es-MX')}`
        : `Filas: ${result.ingresoRows.length.toLocaleString('es-MX')}`;

    self.postMessage({
      progress: 96,
      label: 'Consolidando resultados del archivo',
      detail: finalDetail,
    });
    self.postMessage({ ok: true, result });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Error desconocido al analizar CFDI';
    self.postMessage({ ok: false, error: message });
  }
};

export {};
