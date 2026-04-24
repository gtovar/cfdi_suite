import { describe, expect, it } from 'vitest';
import { runBenchmark } from './runBenchmark';

describe('current-ts benchmark corpus', () => {
  it('stays reproducible against the versioned minimum corpus', async () => {
    const report = await runBenchmark('current-ts');

    expect(report.summary.totalFixtures).toBeGreaterThanOrEqual(10);
    expect(report.summary.failedFixtures).toBe(0);
    expect(report.summary.byCategory.base.total).toBeGreaterThanOrEqual(4);
    expect(report.summary.byCategory.diagnostic.total).toBeGreaterThanOrEqual(4);
    expect(report.summary.byCategory.coverage.total).toBeGreaterThanOrEqual(1);
  });

  it('can run python-satcfdi in strict mode over the same corpus with minimal contract coverage', async () => {
    const report = await runBenchmark('python-satcfdi');

    expect(report.summary.totalFixtures).toBeGreaterThanOrEqual(10);
    expect(report.summary.strictFixtures).toBeGreaterThanOrEqual(8);
    expect(report.summary.failedFixtures).toBe(0);
  }, 15000);
});
