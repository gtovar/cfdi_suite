import type { CfdiAnalysisContractResult, CfdiEngineName } from '../engine/analysisContract';

export type BenchmarkFixtureCategory = 'base' | 'diagnostic' | 'coverage';

export interface BenchmarkFixtureExpectation {
  id: string;
  description: string;
  category: BenchmarkFixtureCategory;
  source: string;
  fileName: string;
  expectedByEngine: Partial<Record<CfdiEngineName, BenchmarkExpectedResult>>;
}

export interface BenchmarkExpectedResult {
  shouldParse: boolean;
  profile: CfdiAnalysisContractResult['profile'];
  ingresoRows: number;
  pagoRows: number;
  issueCodes: string[];
  fatalIssueCodes: string[];
  findingIds: string[];
}

export const benchmarkExpectations: BenchmarkFixtureExpectation[] = [
  {
    id: 'ingreso-clean',
    description: 'Ingreso valido, limpio y con un traslado base.',
    category: 'base',
    source: 'synthetic-local',
    fileName: 'ingreso-clean.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: [],
        fatalIssueCodes: [],
        findingIds: [],
      },
      'python-satcfdi': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: ['UNSUPPORTED_CAPABILITY'],
        fatalIssueCodes: [],
        findingIds: [],
      },
    },
  },
  {
    id: 'pagos-clean',
    description: 'Complemento de pagos valido con una fila extraible.',
    category: 'base',
    source: 'synthetic-local',
    fileName: 'pagos-clean.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: true,
        profile: 'pagos',
        ingresoRows: 0,
        pagoRows: 1,
        issueCodes: [],
        fatalIssueCodes: [],
        findingIds: [],
      },
      'python-satcfdi': {
        shouldParse: true,
        profile: 'pagos',
        ingresoRows: 0,
        pagoRows: 1,
        issueCodes: ['UNSUPPORTED_CAPABILITY'],
        fatalIssueCodes: [],
        findingIds: [],
      },
    },
  },
  {
    id: 'malformed-xml',
    description: 'XML malformado que debe fallar antes de parsear el CFDI.',
    category: 'base',
    source: 'synthetic-local',
    fileName: 'malformed-xml.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: false,
        profile: 'unknown',
        ingresoRows: 0,
        pagoRows: 0,
        issueCodes: ['PROFILE_DETECTION_FAILED'],
        fatalIssueCodes: ['PROFILE_DETECTION_FAILED'],
        findingIds: [],
      },
      'python-satcfdi': {
        shouldParse: false,
        profile: 'unknown',
        ingresoRows: 0,
        pagoRows: 0,
        issueCodes: ['CFDI_PARSE_FAILED'],
        fatalIssueCodes: ['CFDI_PARSE_FAILED'],
        findingIds: [],
      },
    },
  },
  {
    id: 'missing-comprobante',
    description: 'XML bien formado pero sin nodo Comprobante.',
    category: 'base',
    source: 'synthetic-local',
    fileName: 'missing-comprobante.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: false,
        profile: 'unknown',
        ingresoRows: 0,
        pagoRows: 0,
        issueCodes: ['PROFILE_DETECTION_FAILED'],
        fatalIssueCodes: ['PROFILE_DETECTION_FAILED'],
        findingIds: [],
      },
      'python-satcfdi': {
        shouldParse: false,
        profile: 'unknown',
        ingresoRows: 0,
        pagoRows: 0,
        issueCodes: ['CFDI_PARSE_FAILED'],
        fatalIssueCodes: ['CFDI_PARSE_FAILED'],
        findingIds: [],
      },
    },
  },
  {
    id: 'subtotal-mismatch',
    description: 'Subtotal declarado distinto a la suma de conceptos.',
    category: 'diagnostic',
    source: 'synthetic-local',
    fileName: 'subtotal-mismatch.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: [],
        fatalIssueCodes: [],
        findingIds: ['math-SUBTOTAL_MISMATCH-comprobante-na-na'],
      },
      'python-satcfdi': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: ['UNSUPPORTED_CAPABILITY'],
        fatalIssueCodes: [],
        findingIds: [],
      },
    },
  },
  {
    id: 'total-mismatch',
    description: 'Total declarado distinto a la reconstruccion matematica.',
    category: 'diagnostic',
    source: 'synthetic-local',
    fileName: 'total-mismatch.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: [],
        fatalIssueCodes: [],
        findingIds: ['math-TOTAL_MISMATCH-comprobante-na-na'],
      },
      'python-satcfdi': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: ['UNSUPPORTED_CAPABILITY'],
        fatalIssueCodes: [],
        findingIds: [],
      },
    },
  },
  {
    id: 'line-tax-mismatch',
    description: 'Traslado por linea inconsistente sin romper el total declarado.',
    category: 'diagnostic',
    source: 'synthetic-local',
    fileName: 'line-tax-mismatch.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: [],
        fatalIssueCodes: [],
        findingIds: ['math-LINE_TAX_MISMATCH-concept-0-0'],
      },
      'python-satcfdi': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: ['UNSUPPORTED_CAPABILITY'],
        fatalIssueCodes: [],
        findingIds: [],
      },
    },
  },
  {
    id: 'exento',
    description: 'Caso Exento que no se recalcula en v0.',
    category: 'diagnostic',
    source: 'synthetic-local',
    fileName: 'exento.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: [],
        fatalIssueCodes: [],
        findingIds: ['math-LINE_TAX_NOT_RECALCULATED-concept-0-0'],
      },
      'python-satcfdi': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: ['UNSUPPORTED_CAPABILITY'],
        fatalIssueCodes: [],
        findingIds: [],
      },
    },
  },
  {
    id: 'cuota',
    description: 'Caso Cuota que no se recalcula en v0.',
    category: 'diagnostic',
    source: 'synthetic-local',
    fileName: 'cuota.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: [],
        fatalIssueCodes: [],
        findingIds: ['math-LINE_TAX_NOT_RECALCULATED-concept-0-0'],
      },
      'python-satcfdi': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: ['UNSUPPORTED_CAPABILITY'],
        fatalIssueCodes: [],
        findingIds: [],
      },
    },
  },
  {
    id: 'nomina-like',
    description: 'Cobertura ampliada con complemento Nomina tratado como ingreso.',
    category: 'coverage',
    source: 'synthetic-local',
    fileName: 'nomina-like.xml',
    expectedByEngine: {
      'current-ts': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: [],
        fatalIssueCodes: [],
        findingIds: [],
      },
      'python-satcfdi': {
        shouldParse: true,
        profile: 'ingreso',
        ingresoRows: 1,
        pagoRows: 0,
        issueCodes: ['UNSUPPORTED_CAPABILITY'],
        fatalIssueCodes: [],
        findingIds: [],
      },
    },
  },
];

export function getBenchmarkExpectation(
  fixture: BenchmarkFixtureExpectation,
  engineName: CfdiEngineName,
): BenchmarkExpectedResult | null {
  return fixture.expectedByEngine[engineName] ?? null;
}
