import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { CFDIData, CFDIIngresoRow, CFDIImpuesto, CFDIPagoRow } from '../application/cfdiTypes';
import type { CfdiAnalysisContractResult, CfdiAnalysisEngine, CfdiAnalysisIssue } from './analysisContract';

interface PythonWrapperTax {
  tipo: CFDIImpuesto['tipo'];
  impuesto: string;
  base: number;
  tipoFactor: string;
  tasaOCuota: number;
  importe: number;
}

interface PythonWrapperConcept {
  descripcion: string;
  cantidad: number;
  valorUnitario: number;
  importe: number;
  claveProdServ: string;
  impuestos: PythonWrapperTax[];
  objetoImp?: string;
}

interface PythonWrapperCfdi {
  version: string;
  fecha: string;
  uuid: string;
  emisor: string;
  receptor: string;
  subtotal: number;
  descuento: number;
  total: number;
  conceptos: PythonWrapperConcept[];
  impuestosGlobales: PythonWrapperTax[];
}

interface PythonWrapperPayload {
  ok: boolean;
  profile?: CfdiAnalysisContractResult['profile'];
  satcfdiAvailable?: boolean;
  unsupportedCapabilities?: string[];
  errorType?: 'parse' | 'runtime';
  errorMessage?: string;
  traceback?: string;
  cfdi?: PythonWrapperCfdi;
  ingresoRows?: CFDIIngresoRow[];
  pagoRows?: CFDIPagoRow[];
}

const engineDir = fileURLToPath(new URL('.', import.meta.url));
const repoRoot = path.resolve(engineDir, '..', '..', '..');
const defaultWrapperPath = path.join(engineDir, 'python-satcfdi-wrapper.py');
const repoVenvPython = path.join(repoRoot, '.venv-satcfdi', 'bin', 'python');

export interface PythonSatcfdiEngineOptions {
  pythonBinary?: string;
  wrapperPath?: string;
}

export async function analyzeCfdiWithPythonSatcfdiEngine(
  xml: string,
  options: PythonSatcfdiEngineOptions = {},
): Promise<CfdiAnalysisContractResult> {
  const pythonBinary = options.pythonBinary ?? (existsSync(repoVenvPython) ? repoVenvPython : 'python3');
  const wrapperPath = options.wrapperPath ?? defaultWrapperPath;

  let payload: PythonWrapperPayload;

  try {
    payload = await runPythonWrapper(xml, pythonBinary, wrapperPath);
  } catch (error) {
    return {
      engine: 'python-satcfdi',
      profile: 'unknown',
      cfdi: null,
      ingresoRows: [],
      pagoRows: [],
      issues: [
        createIssue(
          'ENGINE_RUNTIME_FAILED',
          error instanceof Error ? error.message : 'No se pudo ejecutar el wrapper Python',
          'parse',
          true,
        ),
      ],
    };
  }

  const profile = payload.profile ?? 'unknown';
  const issues: CfdiAnalysisIssue[] = [];

  if (payload.errorType === 'parse') {
    issues.push(createIssue('CFDI_PARSE_FAILED', payload.errorMessage ?? 'No se pudo parsear el CFDI en Python', 'parse', true));
  } else if (payload.errorType === 'runtime') {
    issues.push(createIssue('ENGINE_RUNTIME_FAILED', payload.errorMessage ?? 'Error de ejecución del motor Python', 'parse', true));
  }

  const hasFatalIssue = issues.some((issue) => issue.fatal);

  if (payload.satcfdiAvailable === false) {
    issues.push(createIssue(
      'UNSUPPORTED_CAPABILITY',
      payload.unsupportedCapabilities?.join(' | ') || 'python-satcfdi no está disponible en este entorno',
      'parse',
      false,
    ));
  }

  if (!hasFatalIssue && payload.satcfdiAvailable && payload.unsupportedCapabilities?.length) {
    issues.push(createIssue(
      'UNSUPPORTED_CAPABILITY',
      payload.unsupportedCapabilities.join(' | '),
      'extract',
      false,
    ));
  }

  return {
    engine: 'python-satcfdi',
    profile,
    cfdi: payload.cfdi ? toCfdiData(payload.cfdi) : null,
    ingresoRows: payload.ingresoRows ?? [],
    pagoRows: payload.pagoRows ?? [],
    issues,
  };
}

export const pythonSatcfdiEngine: CfdiAnalysisEngine = {
  name: 'python-satcfdi',
  analyze(xml: string) {
    return analyzeCfdiWithPythonSatcfdiEngine(xml);
  },
};

function toCfdiData(source: PythonWrapperCfdi): CFDIData {
  const conceptos = source.conceptos.map((concepto) => ({
    descripcion: concepto.descripcion,
    cantidad: concepto.cantidad,
    valorUnitario: concepto.valorUnitario,
    importe: concepto.importe,
    importeCalculado: Number((concepto.cantidad * concepto.valorUnitario).toFixed(6)),
    diferencia: Math.abs(concepto.importe - (concepto.cantidad * concepto.valorUnitario)),
    claveProdServ: concepto.claveProdServ,
    impuestos: concepto.impuestos.map(toCfdiImpuesto),
  }));

  return {
    version: source.version,
    fecha: source.fecha,
    uuid: source.uuid,
    emisor: source.emisor,
    receptor: source.receptor,
    subtotal: source.subtotal,
    descuento: source.descuento,
    total: source.total,
    conceptos,
    impuestosGlobales: source.impuestosGlobales.map(toCfdiImpuesto),
    subtotalCalculado: Number(conceptos.reduce((acc, concepto) => acc + concepto.importe, 0).toFixed(2)),
    totalCalculado: Number(source.total.toFixed(2)),
    hallazgos: [],
    findings: [],
    impactedConceptIndexes: [],
    taxAuditGroups: [],
    verdict: {
      status: 'clean',
      title: 'Sin discrepancias detectadas',
      summary: 'El motor python-satcfdi aún no emite hallazgos equivalentes al motor TypeScript.',
    },
    supportText: 'Resultado estructurado desde python-satcfdi sin findings equivalentes todavía.',
  };
}

function toCfdiImpuesto(tax: PythonWrapperTax): CFDIImpuesto {
  const importeCalculado = tax.tipoFactor === 'Tasa'
    ? Number((tax.base * tax.tasaOCuota).toFixed(6))
    : 0;

  return {
    tipo: tax.tipo,
    impuesto: tax.impuesto,
    base: tax.base,
    tipoFactor: tax.tipoFactor,
    tasaOCuota: tax.tasaOCuota,
    importe: tax.importe,
    importeCalculado,
    diferencia: tax.tipoFactor === 'Tasa'
      ? Math.abs(tax.importe - (tax.base * tax.tasaOCuota))
      : 0,
  };
}

function createIssue(
  code: CfdiAnalysisIssue['code'],
  message: string,
  stage: CfdiAnalysisIssue['stage'],
  fatal: boolean,
): CfdiAnalysisIssue {
  return {
    code,
    message,
    stage,
    fatal,
  };
}

async function runPythonWrapper(
  xml: string,
  pythonBinary: string,
  wrapperPath: string,
): Promise<PythonWrapperPayload> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBinary, [wrapperPath], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => {
      stdout += String(chunk);
    });

    child.stderr.on('data', (chunk) => {
      stderr += String(chunk);
    });

    child.on('error', (error) => {
      reject(new Error(`No se pudo iniciar ${pythonBinary}: ${error.message}`));
    });

    child.on('close', (code) => {
      if (code !== 0 && stdout.trim().length === 0) {
        reject(new Error(stderr.trim() || `El wrapper Python terminó con código ${code}`));
        return;
      }

      try {
        resolve(JSON.parse(stdout) as PythonWrapperPayload);
      } catch {
        reject(new Error(`El wrapper Python devolvió JSON inválido. Salida: ${stdout || stderr}`));
      }
    });

    child.stdin.write(xml);
    child.stdin.end();
  });
}
