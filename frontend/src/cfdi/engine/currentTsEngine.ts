import { buildCfdiData, detectCfdiProfile } from '../application/cfdiAnalysisService';
import { extractIngresoRowsData, extractPagoRowsData } from '../application/cfdiExtractionService';
import type { CfdiAnalysisContractResult, CfdiAnalysisEngine } from './analysisContract';

interface CurrentTsEngineDependencies {
  extractIngresoRows: typeof extractIngresoRowsData;
  extractPagoRows: typeof extractPagoRowsData;
}

const defaultDependencies: CurrentTsEngineDependencies = {
  extractIngresoRows: extractIngresoRowsData,
  extractPagoRows: extractPagoRowsData,
};

export function analyzeCfdiWithCurrentTsEngine(
  xml: string,
  dependencies: CurrentTsEngineDependencies = defaultDependencies,
): CfdiAnalysisContractResult {
  const issues: CfdiAnalysisContractResult['issues'] = [];
  let profile: CfdiAnalysisContractResult['profile'] = 'unknown';

  try {
    profile = detectCfdiProfile(xml);
  } catch (error) {
    issues.push({
      code: 'PROFILE_DETECTION_FAILED',
      message: error instanceof Error ? error.message : 'No se pudo detectar el perfil CFDI',
      stage: 'profile',
      fatal: true,
    });
  }

  if (issues.some((issue) => issue.fatal)) {
    return {
      engine: 'current-ts',
      profile,
      cfdi: null,
      ingresoRows: [],
      pagoRows: [],
      issues,
    };
  }

  let cfdi: CfdiAnalysisContractResult['cfdi'] = null;

  try {
    cfdi = buildCfdiData(xml);
  } catch (error) {
    issues.push({
      code: 'CFDI_PARSE_FAILED',
      message: error instanceof Error ? error.message : 'No se pudo procesar el CFDI',
      stage: 'parse',
      fatal: true,
    });
  }

  if (issues.some((issue) => issue.fatal) || !cfdi) {
    return {
      engine: 'current-ts',
      profile,
      cfdi: null,
      ingresoRows: [],
      pagoRows: [],
      issues,
    };
  }

  const ingresoRows = profile === 'ingreso'
    ? extractIngresoRowsSafely(xml, issues, dependencies.extractIngresoRows)
    : [];
  const pagoRows = profile === 'pagos'
    ? extractPagoRowsSafely(xml, issues, dependencies.extractPagoRows)
    : [];

  return {
    engine: 'current-ts',
    profile,
    cfdi,
    ingresoRows,
    pagoRows,
    issues,
  };
}

export const currentTsEngine: CfdiAnalysisEngine = {
  name: 'current-ts',
  analyze(xml: string) {
    return analyzeCfdiWithCurrentTsEngine(xml);
  },
};

function extractIngresoRowsSafely(
  xml: string,
  issues: CfdiAnalysisContractResult['issues'],
  extractIngresoRows: CurrentTsEngineDependencies['extractIngresoRows'],
): CfdiAnalysisContractResult['ingresoRows'] {
  try {
    return extractIngresoRows(xml);
  } catch (error) {
    issues.push({
      code: 'INGRESO_EXTRACTION_FAILED',
      message: error instanceof Error ? error.message : 'No se pudieron extraer las filas de ingresos',
      stage: 'extract',
      fatal: false,
    });
    return [];
  }
}

function extractPagoRowsSafely(
  xml: string,
  issues: CfdiAnalysisContractResult['issues'],
  extractPagoRows: CurrentTsEngineDependencies['extractPagoRows'],
): CfdiAnalysisContractResult['pagoRows'] {
  try {
    return extractPagoRows(xml);
  } catch (error) {
    issues.push({
      code: 'PAGO_EXTRACTION_FAILED',
      message: error instanceof Error ? error.message : 'No se pudieron extraer las filas de pagos',
      stage: 'extract',
      fatal: false,
    });
    return [];
  }
}
