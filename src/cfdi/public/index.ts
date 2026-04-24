export type {
  AuditFinding,
  CFDIConcept,
  CFDIData,
  CFDIImpuesto,
  CFDIIngresoRow,
  CFDIPagoRow,
  CFDIProfile,
  TaxAuditGroup,
} from '../application/cfdiTypes';

export type {
  CfdiAnalysisContractResult,
  CfdiAnalysisEngine,
  CfdiAnalysisIssue,
  CfdiAnalysisStage,
  CfdiEngineName,
} from '../engine/analysisContract';

export { extractIngresoRowsData as extractIngresoRows, extractPagoRowsData as extractPagoRows } from '../application/cfdiExtractionService';
export { buildCfdiData as parseCFDI } from '../application/cfdiAnalysisService';
export { analyzeCfdiWithCurrentTsEngine as analyzeCFDIContract, currentTsEngine } from '../engine/currentTsEngine';

import { detectCfdiProfile } from '../application/cfdiAnalysisService';
import type { CFDIProfile } from '../application/cfdiTypes';

export function detectCFDIProfile(xmlString: string): CFDIProfile {
  try {
    return detectCfdiProfile(xmlString);
  } catch {
    return 'unknown';
  }
}
