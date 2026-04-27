import { useState } from 'react';
import type { CFDIData, CFDIIngresoRow, CFDIPagoRow, CFDIProfile } from '../../cfdi/public';
import { analyzeCFDI } from '../../lib/cfdi-api-client';
import type { CFDIAnalysisMeta } from '../../lib/cfdi-api-client';

export function useCfdiAnalysis() {
  const [profile, setProfile] = useState<CFDIProfile>('unknown');
  const [cfdi, setCfdi] = useState<CFDIData | null>(null);
  const [ingresoRows, setIngresoRows] = useState<CFDIIngresoRow[]>([]);
  const [pagoRows, setPagoRows] = useState<CFDIPagoRow[]>([]);
  const [analysisMeta, setAnalysisMeta] = useState<CFDIAnalysisMeta | null>(null);
  const [analysisStageLabel, setAnalysisStageLabel] = useState('Analizando estructura CFDI');
  const [analysisStageProgress, setAnalysisStageProgress] = useState(100);
  const [analysisStageDetail, setAnalysisStageDetail] = useState('');
  const [sourceXml, setSourceXml] = useState('');

  async function handleFileSelect(
    xml: string,
    options?: {
      onBeforeApply?: (nextProfile: CFDIProfile) => void;
      onAfterApply?: () => void;
    },
  ) {
    try {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
      const { result, meta } = await analyzeCFDI(xml, ({ label, progress, detail }) => {
        setAnalysisStageLabel(label);
        setAnalysisStageProgress(progress);
        setAnalysisStageDetail(detail ?? '');
      });
      const fatalIssue = result.issues.find((issue) => issue.fatal);
      if (fatalIssue || !result.cfdi) {
        throw new Error(fatalIssue?.message || 'No se pudo construir el analisis CFDI');
      }

      options?.onBeforeApply?.(result.profile);

      setSourceXml(xml);
      setCfdi(result.cfdi);
      setIngresoRows(result.ingresoRows);
      setPagoRows(result.pagoRows);
      setProfile(result.profile);
      setAnalysisMeta(meta);
      setAnalysisStageLabel('Analizando estructura CFDI');
      setAnalysisStageProgress(100);
      setAnalysisStageDetail('');

      options?.onAfterApply?.();
    } catch (error) {
      console.error('Error parsing CFDI:', error);
      const message = error instanceof TypeError
        ? 'No se pudo conectar con la API. Verifica que el backend esté corriendo.'
        : 'Error al procesar el XML. Asegúrate de que sea un CFDI válido.';
      alert(message);
    }
  }

  function resetAnalysis() {
    setCfdi(null);
    setIngresoRows([]);
    setPagoRows([]);
    setSourceXml('');
    setProfile('unknown');
    setAnalysisMeta(null);
    setAnalysisStageLabel('Analizando estructura CFDI');
    setAnalysisStageProgress(100);
    setAnalysisStageDetail('');
  }

  return {
    profile,
    cfdi,
    ingresoRows,
    pagoRows,
    analysisMeta,
    analysisStageLabel,
    analysisStageProgress,
    analysisStageDetail,
    sourceXml,
    handleFileSelect,
    resetAnalysis,
  };
}
