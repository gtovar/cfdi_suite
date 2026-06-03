import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { CfdiAnalysisContractResult, CfdiAnalysisEngine, CfdiEngineName } from '../engine/analysisContract';
import { currentTsEngine } from '../engine/currentTsEngine';
import { pythonSatcfdiEngine } from '../engine/pythonSatcfdiEngine';
import { benchmarkExpectations, getBenchmarkExpectation, type BenchmarkExpectedResult, type BenchmarkFixtureExpectation } from './expectations';

export interface BenchmarkActualResult {
  success: boolean;
  profile: CfdiAnalysisContractResult['profile'];
  cfdiPresent: boolean;
  ingresoRows: number;
  pagoRows: number;
  issueCodes: string[];
  fatalIssueCodes: string[];
  findingIds: string[];
}

export interface BenchmarkCaseResult {
  id: string;
  description: string;
  category: BenchmarkFixtureExpectation['category'];
  fixturePath: string;
  expectationMode: 'strict' | 'observational';
  passed: boolean | null;
  divergences: string[];
  expected: BenchmarkExpectedResult | null;
  actual: BenchmarkActualResult;
}

export interface BenchmarkSummary {
  engine: CfdiEngineName;
  totalFixtures: number;
  strictFixtures: number;
  observationalFixtures: number;
  passedFixtures: number;
  failedFixtures: number;
  parsedFixtures: number;
  failedParses: number;
  totalFatalIssues: number;
  totalNonFatalIssues: number;
  totalFindings: number;
  byCategory: Record<BenchmarkFixtureExpectation['category'], { total: number; passed: number; failed: number }>;
}

export interface BenchmarkReport {
  engine: CfdiEngineName;
  generatedAt: string;
  summary: BenchmarkSummary;
  results: BenchmarkCaseResult[];
}

const engineRegistry: Partial<Record<CfdiEngineName, CfdiAnalysisEngine>> = {
  'current-ts': currentTsEngine,
  'python-satcfdi': pythonSatcfdiEngine,
};

const benchmarkDir = fileURLToPath(new URL('.', import.meta.url));
const fixturesDir = path.join(benchmarkDir, 'fixtures');

export async function runBenchmark(engineName: CfdiEngineName): Promise<BenchmarkReport> {
  const engine = engineRegistry[engineName];
  if (!engine) {
    throw new Error(`No hay runner configurado para el motor ${engineName}`);
  }

  const results: BenchmarkCaseResult[] = [];

  for (const fixture of benchmarkExpectations) {
    const expected = getBenchmarkExpectation(fixture, engineName);

    const fixturePath = path.join(fixturesDir, fixture.fileName);
    const xml = await readFile(fixturePath, 'utf8');
    const analysis = await engine.analyze(xml);
    const actual = toActualResult(analysis);
    const divergences = expected ? compareResult(expected, actual) : [];
    const passed = expected ? divergences.length === 0 : null;

    results.push({
      id: fixture.id,
      description: fixture.description,
      category: fixture.category,
      fixturePath,
      expectationMode: expected ? 'strict' : 'observational',
      passed,
      divergences,
      expected,
      actual,
    });
  }

  return {
    engine: engineName,
    generatedAt: new Date().toISOString(),
    summary: buildSummary(engineName, results),
    results,
  };
}

function toActualResult(result: CfdiAnalysisContractResult): BenchmarkActualResult {
  return {
    success: result.cfdi !== null && !result.issues.some((issue) => issue.fatal),
    profile: result.profile,
    cfdiPresent: result.cfdi !== null,
    ingresoRows: result.ingresoRows.length,
    pagoRows: result.pagoRows.length,
    issueCodes: sortStrings(result.issues.map((issue) => issue.code)),
    fatalIssueCodes: sortStrings(result.issues.filter((issue) => issue.fatal).map((issue) => issue.code)),
    findingIds: sortStrings(result.cfdi?.findings.map((finding) => finding.id) ?? []),
  };
}

function compareResult(expected: BenchmarkExpectedResult, actual: BenchmarkActualResult): string[] {
  const divergences: string[] = [];

  if (expected.shouldParse !== actual.success) {
    divergences.push(`shouldParse esperado=${expected.shouldParse} actual=${actual.success}`);
  }

  if (expected.profile !== actual.profile) {
    divergences.push(`profile esperado=${expected.profile} actual=${actual.profile}`);
  }

  if (expected.ingresoRows !== actual.ingresoRows) {
    divergences.push(`ingresoRows esperado=${expected.ingresoRows} actual=${actual.ingresoRows}`);
  }

  if (expected.pagoRows !== actual.pagoRows) {
    divergences.push(`pagoRows esperado=${expected.pagoRows} actual=${actual.pagoRows}`);
  }

  if (!sameStringArray(expected.issueCodes, actual.issueCodes)) {
    divergences.push(`issueCodes esperado=${expected.issueCodes.join(',') || '[]'} actual=${actual.issueCodes.join(',') || '[]'}`);
  }

  if (!sameStringArray(expected.fatalIssueCodes, actual.fatalIssueCodes)) {
    divergences.push(`fatalIssueCodes esperado=${expected.fatalIssueCodes.join(',') || '[]'} actual=${actual.fatalIssueCodes.join(',') || '[]'}`);
  }

  if (!sameStringArray(expected.findingIds, actual.findingIds)) {
    divergences.push(`findingIds esperado=${expected.findingIds.join(',') || '[]'} actual=${actual.findingIds.join(',') || '[]'}`);
  }

  return divergences;
}

function buildSummary(engine: CfdiEngineName, results: BenchmarkCaseResult[]): BenchmarkSummary {
  const byCategory: BenchmarkSummary['byCategory'] = {
    base: { total: 0, passed: 0, failed: 0 },
    diagnostic: { total: 0, passed: 0, failed: 0 },
    coverage: { total: 0, passed: 0, failed: 0 },
  };

  results.forEach((result) => {
    byCategory[result.category].total += 1;
    if (result.passed) {
      byCategory[result.category].passed += 1;
    } else if (result.passed === false) {
      byCategory[result.category].failed += 1;
    }
  });

  const strictResults = results.filter((result) => result.expectationMode === 'strict');

  return {
    engine,
    totalFixtures: results.length,
    strictFixtures: strictResults.length,
    observationalFixtures: results.length - strictResults.length,
    passedFixtures: strictResults.filter((result) => result.passed === true).length,
    failedFixtures: strictResults.filter((result) => result.passed === false).length,
    parsedFixtures: results.filter((result) => result.actual.success).length,
    failedParses: results.filter((result) => !result.actual.success).length,
    totalFatalIssues: results.reduce((acc, result) => acc + result.actual.fatalIssueCodes.length, 0),
    totalNonFatalIssues: results.reduce((acc, result) => acc + (result.actual.issueCodes.length - result.actual.fatalIssueCodes.length), 0),
    totalFindings: results.reduce((acc, result) => acc + result.actual.findingIds.length, 0),
    byCategory,
  };
}

function sortStrings(values: string[]): string[] {
  return [...values].sort((left, right) => left.localeCompare(right, 'en'));
}

function sameStringArray(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }

  const normalizedLeft = sortStrings(left);
  const normalizedRight = sortStrings(right);
  return normalizedLeft.every((value, index) => value === normalizedRight[index]);
}

function parseCliArgs(argv: string[]) {
  let engine: CfdiEngineName = 'current-ts';
  let format: 'text' | 'json' = 'text';

  argv.forEach((arg) => {
    if (arg.startsWith('--engine=')) {
      engine = arg.slice('--engine='.length) as CfdiEngineName;
    }

    if (arg === '--json' || arg === '--format=json') {
      format = 'json';
    }
  });

  return { engine, format } as { engine: CfdiEngineName; format: 'text' | 'json' };
}

function renderTextReport(report: BenchmarkReport): string {
  const lines: string[] = [];
  lines.push(`Benchmark CFDI engine: ${report.engine}`);
  lines.push(`Generado: ${report.generatedAt}`);
  lines.push(
    `Resumen: ${report.summary.passedFixtures}/${report.summary.strictFixtures} fixtures OK en modo estricto, ` +
    `${report.summary.failedFixtures} con divergencias, ` +
    `${report.summary.observationalFixtures} observacionales, ` +
    `${report.summary.totalFindings} findings, ` +
    `${report.summary.totalFatalIssues} fatal issues.`,
  );
  lines.push(
    `Categorias: base ${report.summary.byCategory.base.passed}/${report.summary.byCategory.base.total}, ` +
    `diagnostic ${report.summary.byCategory.diagnostic.passed}/${report.summary.byCategory.diagnostic.total}, ` +
    `coverage ${report.summary.byCategory.coverage.passed}/${report.summary.byCategory.coverage.total}.`,
  );
  lines.push('');

  report.results.forEach((result) => {
    const status = result.passed === null ? 'OBSERVE' : result.passed ? 'PASS' : 'FAIL';
    lines.push(`${status} ${result.id} (${result.category})`);
    lines.push(`  fixture: ${path.basename(result.fixturePath)}`);
    lines.push(`  mode: ${result.expectationMode}`);
    lines.push(`  profile: ${result.actual.profile}`);
    lines.push(`  rows: ingreso=${result.actual.ingresoRows} pago=${result.actual.pagoRows}`);
    lines.push(`  findings: ${result.actual.findingIds.join(', ') || '[]'}`);
    lines.push(`  issues: ${result.actual.issueCodes.join(', ') || '[]'}`);
    if (result.divergences.length > 0) {
      result.divergences.forEach((divergence) => {
        lines.push(`  diff: ${divergence}`);
      });
    }
  });

  return lines.join('\n');
}

async function main() {
  const { engine, format } = parseCliArgs(process.argv.slice(2));
  const report = await runBenchmark(engine);

  if (format === 'json') {
    console.log(JSON.stringify(report, null, 2));
    return;
  }

  console.log(renderTextReport(report));
  process.exitCode = report.summary.failedFixtures > 0 ? 1 : 0;
}

const entryPath = process.argv[1] ? path.resolve(process.argv[1]) : null;
if (entryPath && fileURLToPath(import.meta.url) === entryPath) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
