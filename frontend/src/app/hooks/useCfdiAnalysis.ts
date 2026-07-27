import { useState } from 'react';
import type { CFDIData, CFDIIngresoRow, CFDIPagoRow, CFDIProfile } from '../../cfdi/public';
import { analyzeCFDI } from '../../lib/cfdi-api-client';
import type { CFDIAnalysisMeta } from '../../lib/cfdi-api-client';
import { userMessage } from '../../lib/user-error';

type ProgressState = {
  label: string;
  progress: number;
  detail: string;
};

type ResultState = {
  profile: CFDIProfile;
  cfdi: CFDIData | null;
  ingresoRows: CFDIIngresoRow[];
  pagoRows: CFDIPagoRow[];
  analysisMeta: CFDIAnalysisMeta | null;
  sourceFile: File | null;
  errorMessage: string | null;
};

const INITIAL_PROGRESS: ProgressState = {
  label: 'Analizando estructura CFDI',
  progress: 100,
  detail: '',
};

const INITIAL_RESULT: ResultState = {
  profile: 'unknown',
  cfdi: null,
  ingresoRows: [],
  pagoRows: [],
  analysisMeta: null,
  sourceFile: null,
  errorMessage: null,
};

export function useCfdiAnalysis() {
  const [progress, setProgress] = useState<ProgressState>(INITIAL_PROGRESS);
  const [result, setResult] = useState<ResultState>(INITIAL_RESULT);

  async function handleFileSelect(
    file: File,
    options?: {
      onBeforeApply?: (nextProfile: CFDIProfile) => void;
      onAfterApply?: () => void;
    },
  ) {
    try {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
      const { result: apiResult, meta } = await analyzeCFDI(file, ({ label, progress: prog, detail }) => {
        setProgress({ label, progress: prog, detail: detail ?? '' });
      });
      const fatalIssue = apiResult.issues.find((issue) => issue.fatal);
      if (fatalIssue || !apiResult.cfdi) {
        throw new Error('Error al procesar el XML. Asegúrate de que sea un CFDI válido.');
      }

      options?.onBeforeApply?.(apiResult.profile);

      setProgress(INITIAL_PROGRESS);
      setResult({
        profile: apiResult.profile,
        cfdi: apiResult.cfdi,
        ingresoRows: apiResult.ingresoRows,
        pagoRows: apiResult.pagoRows,
        analysisMeta: meta,
        sourceFile: file,
        errorMessage: null,
      });

      options?.onAfterApply?.();
    } catch (error) {
      // Antes: si el error traía mensaje, se mostraba tal cual -- podía ser el
      // cuerpo crudo de un 500 o una URL interna dentro de un error de fetch.
      const message = userMessage(
        error,
        'Error al procesar el XML. Asegúrate de que sea un CFDI válido.',
        'analizar_cfdi',
      );
     // 1. Detenemos el spinner/progreso devolviéndolo a su estado inicial
      setProgress(INITIAL_PROGRESS);

      // 2. Opcional: También puedes crear un estado específico de error para el progreso si tu UI lo soporta
      // setProgress({ label: 'Error', progress: 0, detail: message });
      setResult((prev) => ({ ...prev, errorMessage: message }));
    }
  }

  function resetAnalysis() {
    setProgress(INITIAL_PROGRESS);
    setResult(INITIAL_RESULT);
  }

  return {
    profile: result.profile,
    cfdi: result.cfdi,
    ingresoRows: result.ingresoRows,
    pagoRows: result.pagoRows,
    analysisMeta: result.analysisMeta,
    analysisStageLabel: progress.label,
    analysisStageProgress: progress.progress,
    analysisStageDetail: progress.detail,
    sourceFile: result.sourceFile,
    errorMessage: result.errorMessage,
    handleFileSelect,
    resetAnalysis,
  };
}
