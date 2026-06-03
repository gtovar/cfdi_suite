import type { CFDIData, CFDIIngresoRow, CFDIPagoRow, CFDIProfile } from '../application/cfdiTypes';

export type CfdiEngineName = 'current-ts' | 'python-satcfdi';
export type CfdiAnalysisStage = 'profile' | 'parse' | 'extract';

export interface CfdiAnalysisIssue {
  code:
    | 'PROFILE_DETECTION_FAILED'
    | 'CFDI_PARSE_FAILED'
    | 'INGRESO_EXTRACTION_FAILED'
    | 'PAGO_EXTRACTION_FAILED'
    | 'UNSUPPORTED_CAPABILITY'
    | 'ENGINE_RUNTIME_FAILED'
    | 'RESULT_DEGRADED';
  message: string;
  stage: CfdiAnalysisStage;
  fatal: boolean;
}

export interface CfdiAnalysisEngine {
  readonly name: CfdiEngineName;
  analyze(xml: string): CfdiAnalysisContractResult | Promise<CfdiAnalysisContractResult>;
}

export interface CfdiAnalysisContractResult {
  engine: CfdiEngineName;
  profile: CFDIProfile;
  cfdi: CFDIData | null;
  ingresoRows: CFDIIngresoRow[];
  pagoRows: CFDIPagoRow[];
  issues: CfdiAnalysisIssue[];
}
