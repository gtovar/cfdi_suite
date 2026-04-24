/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo, useState } from 'react';
import { CheckCircle2, ArrowLeft, Sparkles } from 'lucide-react';
import type { CFDIData, CFDIConcept, CFDIIngresoRow, CFDIPagoRow } from './cfdi/public';
import { useCfdiAnalysis } from './app/hooks/useCfdiAnalysis';
import { useCfdiExports } from './app/hooks/useCfdiExports';
import { useExtractGridState } from './app/hooks/useExtractGridState';
import { buildExtractMetrics, buildSummaryFields, getProfileLabel } from './app/view-models/cfdiViewModels';
import { explainCfdiField } from './cfdi/domain/explainCfdiField';
import CfdiSummaryHeader from './components/CfdiSummaryHeader';
import ConceptDetailModal from './components/ConceptDetailModal';
import ExtractWorkspace from './components/ExtractWorkspace';
import type { ExtractMode, ExtractSortDirection } from './components/extract-workspace/types';
import FindingsSidebar from './components/FindingsSidebar';
import type { FindingConceptLink, FindingContext } from './components/FindingsSidebar';
import FileUpload from './components/FileUpload';
import InspectorHeader from './components/InspectorHeader';
import TaxAuditPanel from './components/TaxAuditPanel';

function formatExact(value: number) {
  return value.toLocaleString('es-MX', {
    useGrouping: false,
    minimumFractionDigits: 0,
    maximumFractionDigits: 20,
  });
}

const INGRESO_COLUMNS = [
  { key: 'uuid', label: 'UUID' },
  { key: 'claveProdServ', label: 'Clave' },
  { key: 'descripcion', label: 'Descripcion' },
  { key: 'objetoImp', label: 'ObjetoImp' },
  { key: 'tipoImp', label: 'Tipo Imp' },
  { key: 'impuesto', label: 'Impuesto' },
  { key: 'tasaCuota', label: 'Tasa/Cuota' },
  { key: 'importeImp', label: 'Importe Imp' },
] as const;

const PAGO_COLUMNS = [
  { key: 'uuidCFDI', label: 'UUID CFDI' },
  { key: 'fechaPago', label: 'Fecha Pago' },
  { key: 'uuidDR', label: 'UUID DR' },
  { key: 'parcialidad', label: 'Parcialidad' },
  { key: 'impPagado', label: 'Imp Pagado' },
  { key: 'baseDR', label: 'Base DR' },
  { key: 'impuestoDR', label: 'Impuesto DR' },
  { key: 'importeDR', label: 'Importe DR' },
] as const;

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
    case 'claveProdServ':
      return concept.claveProdServ ?? '';
    case 'descripcion':
      return concept.descripcion ?? '';
    case 'cantidad':
      return String(concept.cantidad ?? '');
    case 'valorUnitario':
      return String(concept.valorUnitario ?? '');
    case 'importe':
      return String(concept.importe ?? '');
    case 'importeCalculado':
      return String(concept.importeCalculado ?? '');
    case 'diferencia':
      return String(concept.diferencia ?? '');
    case 'status':
      return concept.diferencia !== 0 ? 'discrepancia' : 'ok';
    default:
      return '';
  }
}

function getExplainedMeaning(key: string, value: string | number | null) {
  return explainCfdiField(key, value).meaning;
}

function getExplainedTaxLabel(code: string) {
  const explained = explainCfdiField('impuesto', code);
  return explained.meaning.includes('sin catalogo')
    ? code
    : `${code} · ${explained.meaning.split('.')[0]}`;
}

function getFindingOriginLabel(findingId: string) {
  if (findingId.startsWith('math-')) return 'Matemático';
  if (findingId.startsWith('tax-group-')) return 'Fiscal';
  if (findingId.startsWith('concept-')) return 'Concepto';
  return 'Operativo';
}

function parseMathFindingId(findingId: string) {
  const parts = findingId.split('-');
  if (parts.length < 5 || parts[0] !== 'math') return null;

  return {
    code: parts[1],
    level: parts[2],
    conceptIndex: parts[3] === 'na' ? null : Number(parts[3]),
  };
}

function formatSignedExact(value: number) {
  if (value === 0) return '0';
  return `${value > 0 ? '+' : '-'}${formatExact(Math.abs(value))}`;
}

function getConceptPriorityScore(concept: CFDIConcept) {
  const taxDifference = concept.impuestos.reduce((maxDifference, tax) => (
    Math.max(maxDifference, Math.abs(tax.diferencia ?? 0))
  ), 0);

  return Math.max(Math.abs(concept.diferencia ?? 0), taxDifference);
}

export default function App() {
  const {
    profile,
    cfdi,
    ingresoRows,
    pagoRows,
    analysisEngine,
    analysisReason,
    analysisStageLabel,
    analysisStageProgress,
    analysisStageDetail,
    handleFileSelect,
    resetAnalysis,
  } = useCfdiAnalysis();
  const [diagnoseSearchTerm, setDiagnoseSearchTerm] = useState('');
  const [diagnoseColumnFilterKey, setDiagnoseColumnFilterKey] = useState<string>('all');
  const [onlyImpacted, setOnlyImpacted] = useState(true);
  const [selectedConcept, setSelectedConcept] = useState<CFDIConcept | null>(null);
  const [hiddenDiagnoseColumns, setHiddenDiagnoseColumns] = useState<string[]>([]);
  const [diagnosePage, setDiagnosePage] = useState(1);
  const [diagnosePageSize, setDiagnosePageSize] = useState(100);
  const [diagnoseSortKey, setDiagnoseSortKey] = useState<string>('diferencia');
  const [diagnoseSortDirection, setDiagnoseSortDirection] = useState<ExtractSortDirection>('desc');
  const [taxAuditExpanded, setTaxAuditExpanded] = useState(true);

  const conceptPool = cfdi
    ? (onlyImpacted ? cfdi.impactedConceptIndexes.map((index) => cfdi.conceptos[index]).filter(Boolean) : cfdi.conceptos)
    : [];

  const activeDatasetType: ExtractMode = profile === 'pagos' ? 'pagos' : 'ingresos';
  const extractColumns = activeDatasetType === 'ingresos' ? INGRESO_COLUMNS : PAGO_COLUMNS;
  const {
    extractGrid,
    extractSearchTerm,
    filteredExtractRows,
    resetForNewAnalysis,
    resetAll: resetExtractState,
  } = useExtractGridState({
    activeDatasetType,
    ingresoRows,
    pagoRows,
    extractColumns,
  });
  const visibleDiagnoseColumns = DIAGNOSE_COLUMNS.filter((column) => !hiddenDiagnoseColumns.includes(column.key));
  const filteredIngresoRows = activeDatasetType === 'ingresos' ? filteredExtractRows as CFDIIngresoRow[] : ingresoRows;
  const filteredPagoRows = activeDatasetType === 'pagos' ? filteredExtractRows as CFDIPagoRow[] : pagoRows;

  const filteredConceptos = conceptPool.filter((concept) => {
    const search = diagnoseSearchTerm.trim().toLowerCase();
    if (!search) return true;

    if (diagnoseColumnFilterKey === 'all') {
      return DIAGNOSE_COLUMNS.some((column) => getDiagnoseCellValue(concept, column.key).toLowerCase().includes(search));
    }

    return getDiagnoseCellValue(concept, diagnoseColumnFilterKey).toLowerCase().includes(search);
  });
  const subtotalDifference = Math.abs((cfdi?.subtotalCalculado ?? 0) - (cfdi?.subtotal ?? 0));
  const totalDifference = Math.abs((cfdi?.totalCalculado ?? 0) - (cfdi?.total ?? 0));
  const findingContexts = useMemo<FindingContext[]>(() => {
    if (!cfdi) return [];

    const buildConceptLink = (conceptIndex: number, reason: string): FindingConceptLink | null => {
      const concept = cfdi.conceptos[conceptIndex];
      if (!concept) return null;
      return { concept, conceptIndex, reason };
    };

    const sortConceptLinks = (links: FindingConceptLink[]) =>
      [...links].sort((left, right) => {
        const scoreDifference = getConceptPriorityScore(right.concept) - getConceptPriorityScore(left.concept);
        if (scoreDifference !== 0) return scoreDifference;
        return left.conceptIndex - right.conceptIndex;
      });

    return cfdi.findings.map((finding) => {
      if (finding.id.startsWith('tax-group-')) {
        const groupKey = finding.id.slice('tax-group-'.length);
        const group = cfdi.taxAuditGroups.find((taxGroup) => taxGroup.key === groupKey);
        if (!group) {
          return {
            findingId: finding.id,
            explanation: 'Este hallazgo fiscal no pudo mapearse al grupo de impuestos actual.',
            relationshipLabel: 'Sin relacion visible',
            conceptLinks: [],
          };
        }

        const conceptLinks = sortConceptLinks(
          group.conceptos
            .map((conceptIndex) => buildConceptLink(
              conceptIndex,
              `Participa en el grupo fiscal ${group.impuesto} ${group.tipoFactor} ${(group.tasaOCuota * 100).toFixed(2)}% comparado contra el agrupado.`,
            ))
            .filter((link): link is FindingConceptLink => Boolean(link)),
        );

        return {
          findingId: finding.id,
          explanation: 'Compara la suma de traslados por concepto contra el impuesto agrupado del comprobante. Los conceptos de abajo participan en ese mismo grupo fiscal.',
          relationshipLabel: `${group.conceptos.length} concepto(s) en el grupo ${group.impuesto} ${(group.tasaOCuota * 100).toFixed(2)}%`,
          whyItMatters: 'Si este grupo no cuadra, el impuesto total del comprobante puede verse correcto a simple vista pero estar distribuido de forma inconsistente en el detalle.',
          differenceLabel: `Dif. real ${formatSignedExact(group.diferencia)}`,
          conceptLinks,
        };
      }

      if (finding.id.startsWith('concept-')) {
        const conceptIndex = Number(finding.id.slice('concept-'.length));
        return {
          findingId: finding.id,
          explanation: 'Este hallazgo señala directamente un concepto cuyo importe no coincide con el cálculo esperado.',
          relationshipLabel: '1 concepto directamente afectado',
          whyItMatters: 'Si el importe del concepto está mal, puede arrastrar discrepancias en subtotal, total o impuestos del comprobante.',
          conceptLinks: [buildConceptLink(conceptIndex, 'El importe de este concepto no coincide con cantidad × valor unitario.')]
            .filter((link): link is FindingConceptLink => Boolean(link)),
        };
      }

      if (finding.id.startsWith('math-')) {
        const parsed = parseMathFindingId(finding.id);
        if (parsed?.conceptIndex !== null && parsed?.conceptIndex !== undefined) {
          const reason = parsed.code === 'LINE_TAX_MISMATCH'
            ? 'El traslado de este concepto no coincide con Base × Tasa.'
            : parsed.code === 'LINE_TAX_NOT_RECALCULATED'
              ? 'Este traslado no se recalcula automáticamente por su tipo de factor.'
              : 'Este hallazgo matemático apunta a un concepto específico.';

          return {
            findingId: finding.id,
            explanation: 'Este hallazgo matemático sí apunta a un concepto específico dentro del comprobante.',
            relationshipLabel: '1 concepto directamente afectado',
            whyItMatters: 'Este concepto es una pista directa del origen del problema matemático detectado por el sistema.',
            conceptLinks: [buildConceptLink(parsed.conceptIndex, reason)]
              .filter((link): link is FindingConceptLink => Boolean(link)),
          };
        }

        return {
          findingId: finding.id,
          explanation: 'Este hallazgo resume una discrepancia global del comprobante y no señala por sí solo un concepto individual.',
          relationshipLabel: 'Sin concepto directo',
          whyItMatters: 'Sirve para interpretar el estado general del comprobante, pero no para elegir por sí solo un concepto específico.',
          conceptLinks: [],
        };
      }

      return {
        findingId: finding.id,
        explanation: 'Hallazgo operativo sin relacion detallada con conceptos en esta version.',
        relationshipLabel: 'Sin relacion detallada',
        whyItMatters: 'Aporta contexto operativo, pero no ofrece todavía una ruta directa hacia conceptos específicos.',
        conceptLinks: [],
      };
    });
  }, [cfdi]);
  const sortedDiagnoseRows = useMemo(() => {
    const rows = [...filteredConceptos];
    rows.sort((left, right) => {
      const getValue = (concept: CFDIConcept) => {
        switch (diagnoseSortKey) {
          case 'claveProdServ':
            return concept.claveProdServ;
          case 'descripcion':
            return concept.descripcion;
          case 'cantidad':
            return concept.cantidad;
          case 'valorUnitario':
            return concept.valorUnitario;
          case 'importe':
            return concept.importe;
          case 'importeCalculado':
            return concept.importeCalculado;
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

  const summaryFields = buildSummaryFields({ profile, cfdi, pagoRows });
  const activeExtractMetrics = buildExtractMetrics({
    activeDatasetType,
    extractSearchTerm,
    filteredIngresoRows,
    filteredPagoRows,
    ingresoRows,
    pagoRows,
  });
  const {
    reportExported,
    taxesExported,
    ingresosExported,
    pagosExported,
    pagosExportError,
    tableExported,
    tableExportError,
    exportReport,
    exportTaxBreakdown,
    exportIngresosCsv,
    exportPagosCsv,
    exportCurrentTable,
  } = useCfdiExports({
    cfdi,
    ingresoRows,
    pagoRows,
    activeDatasetType,
    extractGrid,
  });

  if (!cfdi) {
    return (
      <div className="min-h-screen bg-[#E4E3E0] flex items-center justify-center p-6">
        <div className="max-w-2xl w-full">
          <div className="mb-8 text-center">
            <h1 className="text-4xl font-serif italic mb-2 text-[#141414]">CFDI Inspector</h1>
            <p className="text-[#141414]/60 font-mono text-sm uppercase tracking-widest">Auditoría y Validación de Facturas XML</p>
          </div>
          <FileUpload
            onFileSelect={(xml) =>
              handleFileSelect(xml, {
                onBeforeApply: (nextProfile) => {
                  resetForNewAnalysis(nextProfile === 'pagos' ? 'pagos' : 'ingresos');
                  setDiagnoseSearchTerm('');
                  setDiagnoseColumnFilterKey('all');
                  setDiagnosePage(1);
                  setDiagnosePageSize(100);
                  setDiagnoseSortKey('diferencia');
                  setDiagnoseSortDirection('desc');
                  setTaxAuditExpanded(true);
                  setHiddenDiagnoseColumns([]);
                },
              })
            }
            analysisLabel={analysisStageLabel}
            analysisProgress={analysisStageProgress}
            analysisDetail={analysisStageDetail}
            analysisEngine={analysisEngine}
            analysisReason={analysisReason}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-[#E4E3E0] text-[#141414] font-sans flex flex-col">
      <InspectorHeader
        profileLabel={getProfileLabel(profile)}
        tableExported={tableExported}
        tableExportError={tableExportError}
        onExport={exportCurrentTable}
        onReset={() => {
          resetAnalysis();
          resetExtractState();
          setDiagnoseSearchTerm('');
          setDiagnoseColumnFilterKey('all');
          setDiagnosePage(1);
          setDiagnosePageSize(100);
          setDiagnoseSortKey('diferencia');
          setDiagnoseSortDirection('desc');
          setTaxAuditExpanded(true);
          setHiddenDiagnoseColumns([]);
        }}
      />

      <main className="flex-1 min-h-0 flex overflow-hidden">
        <FindingsSidebar
          cfdi={cfdi}
          findingContexts={findingContexts}
          activeDatasetType={activeDatasetType}
          activeExtractMetrics={activeExtractMetrics}
          subtotalDifference={subtotalDifference}
          totalDifference={totalDifference}
          formatExact={formatExact}
          getFindingOriginLabel={getFindingOriginLabel}
          onSelectConcept={setSelectedConcept}
        />

        <section className="flex-1 min-h-0 flex flex-col overflow-hidden relative">
          <CfdiSummaryHeader summaryFields={summaryFields} />
          <TaxAuditPanel
            cfdi={cfdi}
            taxAuditExpanded={taxAuditExpanded}
            onToggle={() => setTaxAuditExpanded((current) => !current)}
            getExplainedMeaning={getExplainedMeaning}
            getExplainedTaxLabel={getExplainedTaxLabel}
            formatExact={formatExact}
          />
          <div className="flex-1 min-h-0 flex flex-col">
            <ExtractWorkspace
              embedded
              activeDatasetType={activeDatasetType}
              grid={extractGrid}
            />
          </div>

          <ConceptDetailModal
            selectedConcept={selectedConcept}
            onClose={() => setSelectedConcept(null)}
            formatExact={formatExact}
            getExplainedMeaning={getExplainedMeaning}
            getExplainedTaxLabel={getExplainedTaxLabel}
          />
        </section>
      </main>
    </div>
  );
}
