/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState } from 'react';
import type { CFDIIngresoRow, CFDIPagoRow } from './cfdi/public';
import { useCfdiAnalysis } from './app/hooks/useCfdiAnalysis';
import { useCfdiExports } from './app/hooks/useCfdiExports';
import { useDiagnoseState } from './app/hooks/useDiagnoseState';
import { useExtractGridState } from './app/hooks/useExtractGridState';
import { useFindingContexts } from './app/hooks/useFindingContexts';
import { buildExtractMetrics, buildSummaryFields, getProfileLabel } from './app/view-models/cfdiViewModels';
import { formatExact, getExplainedMeaning, getExplainedTaxLabel } from './app/utils/cfdiFormatters';
import { getFindingOriginLabel } from './app/utils/findingUtils';
import CfdiSummaryHeader from './components/CfdiSummaryHeader';
import ConceptDetailModal from './components/ConceptDetailModal';
import ExtractWorkspace from './components/ExtractWorkspace';
import type { ExtractMode } from './components/extract-workspace/types';
import FindingsSidebar from './components/FindingsSidebar';
import FileUpload from './components/FileUpload';
import InspectorHeader from './components/InspectorHeader';
import TaxAuditPanel from './components/TaxAuditPanel';

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

  const [taxAuditExpanded, setTaxAuditExpanded] = useState(true);

  const diagnose = useDiagnoseState(cfdi);
  const findingContexts = useFindingContexts(cfdi);

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

  const filteredIngresoRows = activeDatasetType === 'ingresos' ? (filteredExtractRows as CFDIIngresoRow[]) : ingresoRows;
  const filteredPagoRows = activeDatasetType === 'pagos' ? (filteredExtractRows as CFDIPagoRow[]) : pagoRows;

  const subtotalDifference = Math.abs((cfdi?.subtotalCalculado ?? 0) - (cfdi?.subtotal ?? 0));
  const totalDifference = Math.abs((cfdi?.totalCalculado ?? 0) - (cfdi?.total ?? 0));

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
    tableExported,
    tableExportError,
    exportCurrentTable,
  } = useCfdiExports({
    cfdi,
    ingresoRows,
    pagoRows,
    activeDatasetType,
    extractGrid,
  });

  function resetForFileSelect(nextProfile: ExtractMode) {
    resetForNewAnalysis(nextProfile);
    diagnose.reset();
    setTaxAuditExpanded(true);
  }

  function resetAll() {
    resetAnalysis();
    resetExtractState();
    diagnose.reset();
    setTaxAuditExpanded(true);
  }

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
                  resetForFileSelect(nextProfile === 'pagos' ? 'pagos' : 'ingresos');
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
        onReset={resetAll}
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
          onSelectConcept={diagnose.setSelectedConcept}
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
            selectedConcept={diagnose.selectedConcept}
            onClose={() => diagnose.setSelectedConcept(null)}
            formatExact={formatExact}
            getExplainedMeaning={getExplainedMeaning}
            getExplainedTaxLabel={getExplainedTaxLabel}
          />
        </section>
      </main>
    </div>
  );
}
