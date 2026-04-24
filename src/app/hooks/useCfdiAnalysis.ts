import { useState } from 'react';
import type { CFDIData, CFDIIngresoRow, CFDIPagoRow, CFDIProfile } from '../../cfdi/public';
import { analyzeCFDI } from '../../lib/cfdi-api-client';
import type { CFDIAnalysisMeta } from '../../lib/cfdi-api-client';

export function useCfdiAnalysis() {
  const [profile, setProfile] = useState<CFDIProfile>('unknown');
  const [cfdi, setCfdi] = useState<CFDIData | null>(null);
  const [ingresoRows, setIngresoRows] = useState<CFDIIngresoRow[]>([]);
  const [pagoRows, setPagoRows] = useState<CFDIPagoRow[]>([]);
  const [analysisEngine, setAnalysisEngine] = useState<'idle' | 'api' | 'fallback'>('idle');
  const [analysisReason, setAnalysisReason] = useState('');
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
      const { result, engine, reason, meta } = await analyzeCFDI(xml, ({ label, progress, detail }) => {
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
      setAnalysisEngine(engine);
      setAnalysisReason(reason ?? result.issues.map((issue) => issue.message).join(' | '));
      setAnalysisMeta(meta ?? null);
      setAnalysisStageLabel('Analizando estructura CFDI');
      setAnalysisStageProgress(100);
      setAnalysisStageDetail('');

      options?.onAfterApply?.();
    } catch (error) {
      console.error('Error parsing CFDI:', error);
      alert('Error al procesar el XML. Asegúrate de que sea un CFDI válido.');
    }
  }

  function resetAnalysis() {
    setCfdi(null);
    setIngresoRows([]);
    setPagoRows([]);
    setSourceXml('');
    setProfile('unknown');
    setAnalysisEngine('idle');
    setAnalysisReason('');
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
    analysisEngine,
    analysisReason,
    analysisMeta,
    analysisStageLabel,
    analysisStageProgress,
    analysisStageDetail,
    sourceXml,
    handleFileSelect,
    resetAnalysis,
  };
}
