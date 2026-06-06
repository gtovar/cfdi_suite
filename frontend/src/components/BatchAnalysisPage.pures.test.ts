// @vitest-environment happy-dom

import { describe, expect, it } from 'vitest';
import { computeMonthBreakdown, splitByQuincena } from './BatchAnalysisPage';

// ── computeMonthBreakdown ──────────────────────────────────────────────────────

describe('computeMonthBreakdown', () => {
  it('returns [] for empty queue', () => {
    expect(computeMonthBreakdown([])).toEqual([]);
  });

  it('excludes entries with status error', () => {
    const queue = [{ result: { status: 'error', fecha: '2026-01-15', total: '100' } }];
    expect(computeMonthBreakdown(queue)).toEqual([]);
  });

  it('excludes entries with null result', () => {
    const queue = [{ result: null }];
    expect(computeMonthBreakdown(queue)).toEqual([]);
  });

  it('excludes entries with missing fecha', () => {
    const queue = [{ result: { status: 'ok', fecha: null, total: '100' } }];
    expect(computeMonthBreakdown(queue)).toEqual([]);
  });

  it('treats empty total as monto 0, not NaN', () => {
    const queue = [{ result: { status: 'ok', fecha: '2026-03-10', total: '' } }];
    const result = computeMonthBreakdown(queue);
    expect(result[0]!.monto).toBe(0);
    expect(Number.isNaN(result[0]!.monto)).toBe(false);
  });

  it('treats non-numeric total (e.g. N/A) as monto 0, not NaN', () => {
    const queue = [{ result: { status: 'ok', fecha: '2026-03-10', total: 'N/A' } }];
    const result = computeMonthBreakdown(queue);
    expect(result[0]!.monto).toBe(0);
    expect(Number.isNaN(result[0]!.monto)).toBe(false);
  });

  it('groups entries by YYYY-MM', () => {
    const queue = [
      { result: { status: 'ok', fecha: '2026-01-05', total: '100' } },
      { result: { status: 'ok', fecha: '2026-01-20', total: '200' } },
    ];
    const result = computeMonthBreakdown(queue);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({ month: '2026-01', count: 2, monto: 300 });
  });

  it('sorts by count descending', () => {
    const queue = [
      { result: { status: 'ok', fecha: '2026-01-01', total: '0' } },
      { result: { status: 'ok', fecha: '2026-02-01', total: '0' } },
      { result: { status: 'ok', fecha: '2026-02-15', total: '0' } },
    ];
    const result = computeMonthBreakdown(queue);
    expect(result[0]!.month).toBe('2026-02');
    expect(result[1]!.month).toBe('2026-01');
  });

  it('truncates to topN (default 3)', () => {
    const queue = [
      { result: { status: 'ok', fecha: '2026-01-01', total: '0' } },
      { result: { status: 'ok', fecha: '2026-02-01', total: '0' } },
      { result: { status: 'ok', fecha: '2026-03-01', total: '0' } },
      { result: { status: 'ok', fecha: '2026-04-01', total: '0' } },
    ];
    expect(computeMonthBreakdown(queue)).toHaveLength(3);
  });

  it('respects custom topN', () => {
    const queue = [
      { result: { status: 'ok', fecha: '2026-01-01', total: '0' } },
      { result: { status: 'ok', fecha: '2026-02-01', total: '0' } },
    ];
    expect(computeMonthBreakdown(queue, 1)).toHaveLength(1);
  });
});

// ── splitByQuincena ────────────────────────────────────────────────────────────

function makeFile(name: string): File {
  return new File([''], name);
}

describe('splitByQuincena', () => {
  it('puts all files with day ≤ 15 in first', () => {
    const files = [makeFile('a'), makeFile('b')];
    const { first, second } = splitByQuincena(files, () => 10);
    expect(first).toHaveLength(2);
    expect(second).toHaveLength(0);
  });

  it('puts all files with day > 15 in second', () => {
    const files = [makeFile('a'), makeFile('b')];
    const { first, second } = splitByQuincena(files, () => 20);
    expect(first).toHaveLength(0);
    expect(second).toHaveLength(2);
  });

  it('day 15 goes to first', () => {
    const files = [makeFile('a')];
    const { first } = splitByQuincena(files, () => 15);
    expect(first).toHaveLength(1);
  });

  it('day 16 goes to second', () => {
    const files = [makeFile('a')];
    const { second } = splitByQuincena(files, () => 16);
    expect(second).toHaveLength(1);
  });

  it('splits mixed set correctly', () => {
    const files = [makeFile('a'), makeFile('b'), makeFile('c'), makeFile('d')];
    let call = 0;
    const days = [5, 16, 1, 31];
    const { first, second } = splitByQuincena(files, () => days[call++]!);
    expect(first).toHaveLength(2);
    expect(second).toHaveLength(2);
  });

  it('first + second covers all input files without duplicates', () => {
    const files = [makeFile('x'), makeFile('y'), makeFile('z')];
    let call = 0;
    const days = [10, 20, 15];
    const { first, second } = splitByQuincena(files, () => days[call++]!);
    expect([...first, ...second]).toHaveLength(files.length);
    expect(new Set([...first, ...second]).size).toBe(files.length);
  });

  it('NaN day (empty fecha) routes file to second, not first', () => {
    const files = [makeFile('nan-file')];
    const { first, second } = splitByQuincena(files, () => NaN);
    expect(first).toHaveLength(0);
    expect(second).toHaveLength(1);
  });
});
