/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import clsx from 'clsx';
import { useEffect, useMemo, useState } from 'react';
import type { CFDIIngresoRow, CFDIPagoRow } from './cfdi/public';
import { useCfdiAnalysis } from './app/hooks/useCfdiAnalysis';
import { useCfdiExports } from './app/hooks/useCfdiExports';
import { useDiagnoseState } from './app/hooks/useDiagnoseState';
import { useExtractGridState } from './app/hooks/useExtractGridState';
import { useFindingContexts } from './app/hooks/useFindingContexts';
import { useSatEnquiry } from './app/hooks/useSatEnquiry';
import { useRfcValidation } from './app/hooks/useRfcValidation';
import { buildSummaryFields, getProfileLabel } from './app/view-models/cfdiViewModels';
import { formatExact, getExplainedMeaning, getExplainedTaxLabel } from './app/utils/cfdiFormatters';
import { getFindingOriginLabel } from './app/utils/findingUtils';
import AppSidebar, { type AppView } from './components/AppNav';
import AppHeader from './components/AppHeader';
import CfdiSummaryHeader from './components/CfdiSummaryHeader';
import CleanStatePanel from './components/CleanStatePanel';
import ConceptDetailModal from './components/ConceptDetailModal';
import ConsultasSATPage from './components/ConsultasSATPage';
import EmisoresPage from './components/EmisoresPage';
import ExtractWorkspace from './components/ExtractWorkspace';
import type { ExtractMode } from './components/extract-workspace/types';
import FindingsSidebar from './components/FindingsSidebar';
import FileUpload from './components/FileUpload';
import InspectorHeader from './components/InspectorHeader';
import ResolutionPanel from './components/ResolutionPanel';
import TaxAuditPanel from './components/TaxAuditPanel';
import XmlNodeViewer from './components/XmlNodeViewer';

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
    sourceFile,
    handleFileSelect,
    resetAnalysis,
  } = useCfdiAnalysis();

  const [taxAuditExpanded, setTaxAuditExpanded] = useState(false);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<'auditoria' | 'nodo-xml'>('auditoria');
  const [modifiedXml, setModifiedXml] = useState<string | null>(null);
  const [pdfPhase, setPdfPhase] = useState<'idle' | 'parsing' | 'rendering_html' | 'generating_pdf' | 'error'>('idle');
  const [pdfError, setPdfError] = useState<string | undefined>();

  const diagnose = useDiagnoseState(cfdi);
  const findingContexts = useFindingContexts(cfdi);

  useEffect(() => {
    const defaultId = findingContexts.find((ctx) => ctx.correctionSteps)?.findingId ?? null;
    setSelectedFindingId(defaultId);
    setInspectorTab('auditoria');
    setModifiedXml(null);
  }, [cfdi?.uuid]);

  const selectedFindingContext = useMemo(
    () => findingContexts.find((ctx) => ctx.findingId === selectedFindingId) ?? null,
    [selectedFindingId, findingContexts],
  );

  const selectedFinding = useMemo(
    () => cfdi?.findings.find((f) => f.id === selectedFindingId) ?? null,
    [selectedFindingId, cfdi],
  );
  const satEnquiry = useSatEnquiry();
  const rfcValidation = useRfcValidation();

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
  const nombreEmisor =
    (profile === 'pagos' ? '' : ingresoRows[0]?.nombreEmisor) ?? '';
  const rfcReceptor =
    (profile === 'pagos' ? pagoRows[0]?.rfcReceptor : ingresoRows[0]?.rfcReceptor) ?? '';
  const satEnquiryData =
    cfdi && rfcEmisor
      ? { uuid: cfdi.uuid, rfcEmisor, rfcReceptor, total: cfdi.total }
      : null;

  const rfcValidationProps = rfcEmisor
    ? {
        rfc: rfcEmisor,
        razonSocial: nombreEmisor || undefined,
        formatLoading: rfcValidation.formatLoading,
        satLoading: rfcValidation.satLoading,
        formatResult: rfcValidation.formatResult,
        satResult: rfcValidation.satResult,
        satError: rfcValidation.satError,
        fielStatus: rfcValidation.fielStatus,
        onValidateFormat: () => {
          rfcValidation.validateFormat({ rfc: rfcEmisor, razonSocial: nombreEmisor || undefined });
          if (!rfcValidation.fielStatus) {
            rfcValidation.checkFielStatus();
          }
        },
        onValidateSat: () =>
          rfcValidation.validateSat({ rfc: rfcEmisor, razonSocial: nombreEmisor || undefined }),
      }
    : null;

  function resetForFileSelect(nextProfile: ExtractMode) {
    resetForNewAnalysis(nextProfile);
    diagnose.reset();
    satEnquiry.reset();
    rfcValidation.reset();
    setTaxAuditExpanded(false);
    setSelectedFindingId(null);
  }

  function resetAll() {
    resetAnalysis();
    resetExtractState();
    diagnose.reset();
    satEnquiry.reset();
    rfcValidation.reset();
    setTaxAuditExpanded(false);
    setSelectedFindingId(null);
    setModifiedXml(null);
  }

  async function handleDownloadPdf() {
    if (!sourceFile) return;
    setPdfPhase('parsing');
    setPdfError(undefined);
    try {
      const form = new FormData();
      form.append('file', sourceFile);
      const startRes = await fetch('/api/cfdi/pdf/start', { method: 'POST', body: form });
      if (!startRes.ok) throw new Error(`HTTP ${startRes.status}`);
      const { jobId } = await startRes.json();

      await new Promise<void>((resolve, reject) => {
        const es = new EventSource(`/api/cfdi/pdf/${jobId}/progress`);
        es.onmessage = (e) => {
          const { status, error } = JSON.parse(e.data) as { status: string; error: string };
          if (status === 'done') {
            es.close();
            resolve();
          } else if (status === 'error') {
            es.close();
            reject(new Error(error || 'Error generando PDF'));
          } else {
            setPdfPhase(status as typeof pdfPhase);
          }
        };
        es.onerror = () => { es.close(); reject(new Error('Conexión perdida')); };
      });

      const dlRes = await fetch(`/api/cfdi/pdf/${jobId}/download`);
      if (!dlRes.ok) throw new Error(`HTTP ${dlRes.status}`);
      const blob = await dlRes.blob();
      const filename = dlRes.headers.get('content-disposition')?.match(/filename=(.+)/)?.[1] ?? 'cfdi.pdf';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : 'Error generando PDF');
      setPdfPhase('error');
      setTimeout(() => setPdfPhase('idle'), 5000);
      return;
    }
    setPdfPhase('idle');
  }

  function handleDownloadModified() {
    if (!modifiedXml || !cfdi) return;
    const blob = new Blob([modifiedXml], { type: 'text/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cfdi-corregido-${cfdi.uuid.slice(0, 8)}.xml`;
    a.click();
    URL.revokeObjectURL(url);
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
                  onFileSelect={(file) =>
                    handleFileSelect(file, {
                      onBeforeApply: (nextProfile) => {
                        resetForFileSelect(nextProfile === 'pagos' ? 'pagos' : 'ingresos');
                      },
                    })
                  }
                  analysisLabel={analysisStageLabel}
                  analysisProgress={analysisStageProgress}
                  analysisDetail={analysisStageDetail}
                />

                {/* Capability map */}
                <div className="mt-5 rounded-xl border border-gray-200 bg-white px-5 py-4">
                  <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-gray-400">Qué puedes hacer</p>
                  <div className="space-y-2">
                    {([
                      { dot: 'bg-emerald-400', label: 'Sin configurar nada', desc: 'Leer el XML · Ver todos los campos y conceptos · Validar el formato del RFC · Exportar a Excel' },
                      { dot: 'bg-blue-400',    label: 'Con credenciales Diverza (una por RFC emisor)', desc: 'Consultar si el CFDI está vigente, cancelado o puede cancelarse ante el SAT' },
                      { dot: 'bg-violet-400',  label: 'Con e.Firma (una sola para toda la app)', desc: 'Verificar si un RFC existe en el SAT y validar que la Razón Social coincida' },
                    ] as const).map(({ dot, label, desc }) => (
                      <div key={label} className="flex items-start gap-3">
                        <span className={`mt-1.5 size-2 shrink-0 rounded-full ${dot}`} />
                        <div className="text-xs leading-snug">
                          <span className="font-medium text-gray-700">{label}</span>
                          <span className="text-gray-400"> — {desc}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-[11px] text-gray-400">
                    Credenciales y e.Firma se configuran en{' '}
                    <button
                      onClick={() => setActiveView('emisores')}
                      className="font-medium text-primary-600 hover:underline"
                    >
                      Emisores →
                    </button>
                  </p>
                </div>
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
                rfcValidation={rfcValidationProps}
                inspectorTab={cfdi.findings.length > 0 ? inspectorTab : undefined}
                onTabChange={setInspectorTab}
                hasFindings={cfdi.findings.length > 0}
                modifiedXml={modifiedXml}
                onDownloadModified={handleDownloadModified}
                onDownloadPdf={sourceFile && pdfPhase === 'idle' ? handleDownloadPdf : undefined}
                pdfPhase={pdfPhase}
                pdfError={pdfError}
              />

              <main className="flex-1 min-h-0 flex flex-col overflow-hidden bg-gray-50 p-4 gap-4">
                {/* Fila 1 y 2: ocultas en modo Nodo XML para pantalla limpia */}
                {inspectorTab !== 'nodo-xml' && (
                  <>
                    <CfdiSummaryHeader summaryFields={summaryFields} />
                  </>
                )}

                {/* Fila 3: [Hallazgos si los hay] + panel principal */}
                <div className="relative flex flex-1 min-h-0 gap-4 overflow-hidden">
                  {cfdi.findings.length > 0 && (
                    <FindingsSidebar
                      cfdi={cfdi}
                      findingContexts={findingContexts}
                      getFindingOriginLabel={getFindingOriginLabel}
                      onSelectConcept={diagnose.setSelectedConcept}
                      selectedFindingId={selectedFindingId}
                      onSelectFinding={setSelectedFindingId}
                    />
                  )}

                  {inspectorTab === 'nodo-xml' && cfdi.findings.length > 0 ? (
                    <XmlNodeViewer
                      finding={selectedFinding}
                      sourceFile={sourceFile}
                      modifiedXml={modifiedXml}
                      onAcceptChange={setModifiedXml}
                    />
                  ) : (
                    <div className="flex-1 min-h-0 flex flex-col rounded-2xl bg-white shadow-sm overflow-hidden">
                      {/* Panel contextual: limpio / resolución / auditoría */}
                      {cfdi.findings.length === 0 ? (
                        <CleanStatePanel
                          showDetail={taxAuditExpanded}
                          onToggleDetail={() => setTaxAuditExpanded((v) => !v)}
                        />
                      ) : selectedFinding && selectedFindingContext?.correctionSteps ? (
                        <ResolutionPanel
                          finding={selectedFinding}
                          findingContext={selectedFindingContext}
                          correctionSteps={selectedFindingContext.correctionSteps}
                          uuid={cfdi.uuid}
                          onSelectConcept={diagnose.setSelectedConcept}
                        />
                      ) : (
                        <TaxAuditPanel
                          cfdi={cfdi}
                          taxAuditExpanded={taxAuditExpanded}
                          onToggle={() => setTaxAuditExpanded((current) => !current)}
                          getExplainedMeaning={getExplainedMeaning}
                          getExplainedTaxLabel={getExplainedTaxLabel}
                          formatExact={formatExact}
                        />
                      )}
                      <ExtractWorkspace
                        embedded
                        activeDatasetType={activeDatasetType}
                        grid={extractGrid}
                      />
                    </div>
                  )}

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
