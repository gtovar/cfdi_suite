import { useMemo, useState } from 'react';
import type { CFDIConcept, CFDIData } from '../../cfdi/public';
import type { ExtractSortDirection } from '../../components/extract-workspace/types';

const DIAGNOSE_COLUMNS = [
  { key: 'claveProdServ', label: 'Clave' },
  { key: 'descripcion', label: 'Descripcion' },
  { key: 'cantidad', label: 'Cant.' },
  { key: 'valorUnitario', label: 'V. Unitario' },
  { key: 'importe', label: 'Importe XML' },
  { key: 'importeCalculado', label: 'Importe Calc.' },
  { key: 'diferencia', label: 'Dif.' },
  { key: 'status', label: 'Status' },
] as const;

function getDiagnoseCellValue(concept: CFDIConcept, key: string) {
  switch (key) {
    case 'claveProdServ': return concept.claveProdServ ?? '';
    case 'descripcion': return concept.descripcion ?? '';
    case 'cantidad': return String(concept.cantidad ?? '');
    case 'valorUnitario': return String(concept.valorUnitario ?? '');
    case 'importe': return String(concept.importe ?? '');
    case 'importeCalculado': return String(concept.importeCalculado ?? '');
    case 'diferencia': return String(concept.diferencia ?? '');
    case 'status': return concept.diferencia !== 0 ? 'discrepancia' : 'ok';
    default: return '';
  }
}

export function useDiagnoseState(cfdi: CFDIData | null) {
  const [diagnoseSearchTerm, setDiagnoseSearchTerm] = useState('');
  const [diagnoseColumnFilterKey, setDiagnoseColumnFilterKey] = useState<string>('all');
  const [onlyImpacted, setOnlyImpacted] = useState(true);
  const [selectedConcept, setSelectedConcept] = useState<CFDIConcept | null>(null);
  const [hiddenDiagnoseColumns, setHiddenDiagnoseColumns] = useState<string[]>([]);
  const [diagnosePage, setDiagnosePage] = useState(1);
  const [diagnosePageSize, setDiagnosePageSize] = useState(100);
  const [diagnoseSortKey, setDiagnoseSortKey] = useState<string>('diferencia');
  const [diagnoseSortDirection, setDiagnoseSortDirection] = useState<ExtractSortDirection>('desc');

  const conceptPool = cfdi
    ? (onlyImpacted
        ? cfdi.impactedConceptIndexes.map((index) => cfdi.conceptos[index]).filter(Boolean)
        : cfdi.conceptos)
    : [];

  const visibleDiagnoseColumns = DIAGNOSE_COLUMNS.filter((col) => !hiddenDiagnoseColumns.includes(col.key));

  const filteredConceptos = conceptPool.filter((concept) => {
    const search = diagnoseSearchTerm.trim().toLowerCase();
    if (!search) return true;
    if (diagnoseColumnFilterKey === 'all') {
      return DIAGNOSE_COLUMNS.some((col) => getDiagnoseCellValue(concept, col.key).toLowerCase().includes(search));
    }
    return getDiagnoseCellValue(concept, diagnoseColumnFilterKey).toLowerCase().includes(search);
  });

  const sortedDiagnoseRows = useMemo(() => {
    const rows = [...filteredConceptos];
    rows.sort((left, right) => {
      const getValue = (concept: CFDIConcept) => {
        switch (diagnoseSortKey) {
          case 'claveProdServ': return concept.claveProdServ;
          case 'descripcion': return concept.descripcion;
          case 'cantidad': return concept.cantidad;
          case 'valorUnitario': return concept.valorUnitario;
          case 'importe': return concept.importe;
          case 'importeCalculado': return concept.importeCalculado;
          case 'diferencia':
          default:
            return concept.diferencia;
        }
      };

      const leftValue = getValue(left);
      const rightValue = getValue(right);

      if (typeof leftValue === 'number' && typeof rightValue === 'number') {
        return diagnoseSortDirection === 'asc' ? leftValue - rightValue : rightValue - leftValue;
      }

      const comparison = String(leftValue).localeCompare(String(rightValue), 'es', { numeric: true, sensitivity: 'base' });
      return diagnoseSortDirection === 'asc' ? comparison : -comparison;
    });
    return rows;
  }, [filteredConceptos, diagnoseSortDirection, diagnoseSortKey]);

  const filteredDiagnoseCount = sortedDiagnoseRows.length;
  const diagnoseTotalPages = Math.max(1, Math.ceil(filteredDiagnoseCount / diagnosePageSize));
  const safeDiagnosePage = Math.min(diagnosePage, diagnoseTotalPages);
  const diagnosePageStart = filteredDiagnoseCount === 0 ? 0 : (safeDiagnosePage - 1) * diagnosePageSize;
  const currentDiagnoseRows = sortedDiagnoseRows.slice(diagnosePageStart, diagnosePageStart + diagnosePageSize);

  function reset() {
    setDiagnoseSearchTerm('');
    setDiagnoseColumnFilterKey('all');
    setDiagnosePage(1);
    setDiagnosePageSize(100);
    setDiagnoseSortKey('diferencia');
    setDiagnoseSortDirection('desc');
    setHiddenDiagnoseColumns([]);
    setSelectedConcept(null);
  }

  return {
    diagnoseSearchTerm,
    setDiagnoseSearchTerm,
    diagnoseColumnFilterKey,
    setDiagnoseColumnFilterKey,
    onlyImpacted,
    setOnlyImpacted,
    selectedConcept,
    setSelectedConcept,
    hiddenDiagnoseColumns,
    setHiddenDiagnoseColumns,
    diagnosePage,
    setDiagnosePage,
    diagnosePageSize,
    setDiagnosePageSize,
    diagnoseSortKey,
    setDiagnoseSortKey,
    diagnoseSortDirection,
    setDiagnoseSortDirection,
    visibleDiagnoseColumns,
    currentDiagnoseRows,
    filteredDiagnoseCount,
    diagnoseTotalPages,
    safeDiagnosePage,
    reset,
  };
}
