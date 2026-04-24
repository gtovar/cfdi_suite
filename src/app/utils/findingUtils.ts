import type { CFDIConcept } from '../../cfdi/public';

export function getFindingOriginLabel(findingId: string) {
  if (findingId.startsWith('math-')) return 'Matemático';
  if (findingId.startsWith('tax-group-')) return 'Fiscal';
  if (findingId.startsWith('concept-')) return 'Concepto';
  return 'Operativo';
}

export function parseMathFindingId(findingId: string) {
  const parts = findingId.split('-');
  if (parts.length < 5 || parts[0] !== 'math') return null;

  return {
    code: parts[1],
    level: parts[2],
    conceptIndex: parts[3] === 'na' ? null : Number(parts[3]),
  };
}

export function getConceptPriorityScore(concept: CFDIConcept) {
  const taxDifference = concept.impuestos.reduce(
    (maxDiff, tax) => Math.max(maxDiff, Math.abs(tax.diferencia ?? 0)),
    0,
  );
  return Math.max(Math.abs(concept.diferencia ?? 0), taxDifference);
}
