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
import { useSatEnquiry } from './app/hooks/useSatEnquiry';
import { buildExtractMetrics, buildSummaryFields, getProfileLabel } from './app/view-models/cfdiViewModels';
import { formatExact, getExplainedMeaning, getExplainedTaxLabel } from './app/utils/cfdiFormatters';
import { getFindingOriginLabel } from './app/utils/findingUtils';
import AppSidebar, { type AppView } from './components/AppNav';
import AppHeader from './components/AppHeader';
import CfdiSummaryHeader from './components/CfdiSummaryHeader';
import ConceptDetailModal from './components/ConceptDetailModal';
import ConsultasSATPage from './components/ConsultasSATPage';
import EmisoresPage from './components/EmisoresPage';
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
  const [activeView, setActiveView] = useState<AppView>('inspector');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const {
    profile,
    cfdi,
    ingresoRows,
    pagoRows,
    analysisStageLabel,
    analysisStageProgress,
    analysisStageDetail,
    handleFileSelect,
    resetAnalysis,
  } = useCfdiAnalysis();

  const [taxAuditExpanded, setTaxAuditExpanded] = useState(true);

  const diagnose = useDiagnoseState(cfdi);
  const findingContexts = useFindingContexts(cfdi);
  const satEnquiry = useSatEnquiry();

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

  const rfcEmisor =
    (profile === 'pagos' ? pagoRows[0]?.rfcEmisor : ingresoRows[0]?.rfcEmisor) ?? '';
  const rfcReceptor =
    (profile === 'pagos' ? pagoRows[0]?.rfcReceptor : ingresoRows[0]?.rfcReceptor) ?? '';
  const satEnquiryData =
    cfdi && rfcEmisor
      ? { uuid: cfdi.uuid, rfcEmisor, rfcReceptor, total: cfdi.total }
      : null;

  function resetForFileSelect(nextProfile: ExtractMode) {
    resetForNewAnalysis(nextProfile);
    diagnose.reset();
    satEnquiry.reset();
    setTaxAuditExpanded(true);
  }

  function resetAll() {
    resetAnalysis();
    resetExtractState();
    diagnose.reset();
    satEnquiry.reset();
    setTaxAuditExpanded(true);
  }

  return (
    <div className="flex h-screen flex-col">
      <AppHeader
        activeView={activeView}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={() => setSidebarCollapsed((c) => !c)}
      />

      <div className="flex flex-1 min-h-0">
        <AppSidebar
          activeView={activeView}
          onViewChange={setActiveView}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
        />

      <div className="flex flex-1 min-w-0 flex-col overflow-hidden">
      {activeView === 'consultas-sat' && <ConsultasSATPage />}
      {activeView === 'emisores' && <EmisoresPage />}

      {activeView === 'inspector' && (
        <>
          {!cfdi ? (
            <div className="flex-1 flex items-center justify-center p-8 bg-gray-50">
              <div className="max-w-2xl w-full">
                <div className="mb-8 text-center">
                  <p className="text-xs font-medium uppercase tracking-widest text-gray-400">
                    Auditoría y Validación de Facturas XML
                  </p>
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
                />
              </div>
            </div>
          ) : (
            <>
              <InspectorHeader
                profileLabel={getProfileLabel(profile)}
                tableExported={tableExported}
                tableExportError={tableExportError}
                onExport={exportCurrentTable}
                onReset={resetAll}
                satEnquiryData={satEnquiryData}
                satLoading={satEnquiry.loading}
                satResult={satEnquiry.result}
                satError={satEnquiry.error}
                onConsultarSat={() =>
                  satEnquiryData && satEnquiry.consult(satEnquiryData)
                }
              />

              <main className="flex-1 min-h-0 flex overflow-hidden bg-gray-50 p-3 gap-3">
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

                <div className="flex-1 min-h-0 relative flex flex-col gap-3 overflow-hidden">
                  <div className="shrink-0 rounded-lg bg-white shadow-soft overflow-hidden">
                    <CfdiSummaryHeader summaryFields={summaryFields} />
                    <TaxAuditPanel
                      cfdi={cfdi}
                      taxAuditExpanded={taxAuditExpanded}
                      onToggle={() => setTaxAuditExpanded((current) => !current)}
                      getExplainedMeaning={getExplainedMeaning}
                      getExplainedTaxLabel={getExplainedTaxLabel}
                      formatExact={formatExact}
                    />
                  </div>

                  <div className="flex-1 min-h-0 flex flex-col rounded-lg bg-white shadow-soft overflow-hidden">
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
                </div>
              </main>
            </>
          )}
        </>
      )}
      </div>
      </div>
    </div>
  );
}
