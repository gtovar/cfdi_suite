import type { CFDIConcept } from '../../cfdi/public';

const FINDING_ORIGIN_LABELS: Record<string, string> = {
  'math-': 'Matemático',
  'tax-group-': 'Fiscal',
  'sat-rounding-': 'SAT Redondeo',
  'concept-': 'Concepto',
};

export function getFindingOriginLabel(findingId: string): string {
  for (const [prefix, label] of Object.entries(FINDING_ORIGIN_LABELS)) {
    if (findingId.startsWith(prefix)) return label;
  }
  return 'Operativo';
}

export type MathFindingId = {
  code: string;
  level: string;
  conceptIndex: number | null;
};

export function parseMathFindingId(findingId: string): MathFindingId | null {
  const parts = findingId.split('-');
  if (parts.length < 5 || parts[0] !== 'math') return null;

  return {
    code: parts[1],
    level: parts[2],
    conceptIndex: parts[3] === 'na' ? null : Number(parts[3]),
  };
}

export type SeverityColors = {
  containerBorder: string;
  containerBg: string;
  icon: string;
  badge: string;
  title: string;
  body: string;
  bodyMuted: string;
  relBadge: string;
};

export function getSeverityColors(severity: string): SeverityColors {
  return severity === 'critical'
    ? {
        containerBorder: 'border-red-200',
        containerBg: 'bg-red-50',
        icon: 'text-red-500',
        badge: 'bg-red-100 text-red-700',
        title: 'text-red-900',
        body: 'text-red-800',
        bodyMuted: 'text-red-800/80',
        relBadge: 'bg-red-100 text-red-800',
      }
    : {
        containerBorder: 'border-amber-200',
        containerBg: 'bg-amber-50',
        icon: 'text-amber-500',
        badge: 'bg-amber-100 text-amber-700',
        title: 'text-amber-900',
        body: 'text-amber-800',
        bodyMuted: 'text-amber-800/80',
        relBadge: 'bg-amber-100 text-amber-800',
      };
}

export function getConceptPriorityScore(concept: CFDIConcept): number {
  const taxDifference = concept.impuestos.reduce(
    (maxDiff, tax) => Math.max(maxDiff, Math.abs(tax.diferencia ?? 0)),
    0,
  );
  return Math.max(Math.abs(concept.diferencia ?? 0), taxDifference);
}
