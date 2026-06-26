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
import BatchAnalysisPage from './components/BatchAnalysisPage';
import FloatingBatchWidget, { type BatchProgressStatus } from './components/FloatingBatchWidget';
import CleanStatePanel from './components/CleanStatePanel';
import ConceptDetailModal from './components/ConceptDetailModal';
import ConsultasSATPage from './components/ConsultasSATPage';
import EmisoresPage from './components/EmisoresPage';
import ExtractWorkspace from './components/ExtractWorkspace';
import type { ExtractMode } from './components/extract-workspace/types';
import FindingsSidebar from './components/FindingsSidebar';
import CfdiAnalysisLoader from './components/CfdiAnalysisLoader';
import InspectorHeader from './components/InspectorHeader';
import { type TemplateConfig, DEFAULT_TEMPLATE } from './components/PdfTemplateBuilder';
import PdfTemplatesPage from './components/PdfTemplatesPage';
import ConversionMasivaPage from './components/ConversionMasivaPage';
import ResolutionPanel from './components/ResolutionPanel';
import TaxAuditPanel from './components/TaxAuditPanel';
import XmlNodeViewer from './components/XmlNodeViewer';
import Editor from './pages/Editor';

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
  const [activeView, setActiveView] = useState<AppView>('masivo');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  function handleToggleSidebar() {
    if (window.innerWidth < 768) {
      setMobileNavOpen(c => !c);
    } else {
      setSidebarCollapsed(c => !c);
    }
  }

  const {
    profile,
    cfdi,
    ingresoRows,
    pagoRows,
    analysisStageLabel,
    analysisStageProgress,
    analysisStageDetail,
    sourceFile,
    errorMessage,
    handleFileSelect,
    resetAnalysis,
  } = useCfdiAnalysis();

  const [batchFiles, setBatchFiles] = useState<File[] | null>(null);
  const [fromMasivo, setFromMasivo] = useState(false);
  const [pendingFileName, setPendingFileName] = useState<string | null>(null);
  const [batchMasivoStatus, setBatchMasivoStatus] = useState<BatchProgressStatus | null>(null);
  const [batchNavFiles, setBatchNavFiles] = useState<File[]>([]);
  const [batchNavIndex, setBatchNavIndex] = useState(0);
  const [widgetDismissed, setWidgetDismissed] = useState(false);
  const [taxAuditExpanded, setTaxAuditExpanded] = useState(false);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<'auditoria' | 'nodo-xml'>('auditoria');
  const [modifiedXml, setModifiedXml] = useState<string | null>(null);
  const [pdfPhase, setPdfPhase] = useState<'idle' | 'parsing' | 'rendering_html' | 'generating_pdf' | 'error'>('idle');
  const [pdfProgressDetail, setPdfProgressDetail] = useState<string | undefined>();
  const [pdfError, setPdfError] = useState<string | undefined>();
  const [templateConfig, setTemplateConfig] = useState<TemplateConfig>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('cfdi-pdf-template') ?? '');
      return stored ? { ...DEFAULT_TEMPLATE, ...stored } : DEFAULT_TEMPLATE;
    } catch { return DEFAULT_TEMPLATE; }
  });

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
    setBatchFiles(null);
    setFromMasivo(false);
  }

  function resetForBatch() {
    resetAnalysis();
    resetExtractState();
    diagnose.reset();
    satEnquiry.reset();
    rfcValidation.reset();
    setTaxAuditExpanded(false);
    setSelectedFindingId(null);
    setModifiedXml(null);
    // batchFiles y fromMasivo se preservan — volvemos al origen
  }

  function handleBatchNavigate(file: File, newIndex: number) {
    setPendingFileName(file.name);
    setBatchNavIndex(newIndex);
    resetForBatch();
    handleFileSelect(file, {
      onBeforeApply: (nextProfile) => {
        resetForFileSelect(nextProfile === 'pagos' ? 'pagos' : 'ingresos');
      },
    });
    // activeView permanece en 'inspector'
  }

  async function handleDownloadPdf(engine: 'playwright' | 'reportlab' | 'gopdfsuit' | 'canvas_pipeline' = 'reportlab', template?: TemplateConfig) {
    if (!sourceFile) return;
    setPdfPhase('parsing');
    setPdfError(undefined);
    try {
      const form = new FormData();
      form.append('file', sourceFile);
      form.append('engine', engine);
      if (template) form.append('template', JSON.stringify(template));
      const startRes = await fetch('/api/cfdi/pdf/start', { method: 'POST', body: form });
      if (!startRes.ok) {
        let msg = `Error ${startRes.status}`;
        try { const b = await startRes.json(); msg = b.detail ?? b.message ?? msg; } catch {}
        throw new Error(msg);
      }
      const { jobId } = await startRes.json();

      await new Promise<void>((resolve, reject) => {
        const es = new EventSource(`/api/cfdi/pdf/${jobId}/progress`);
        es.onmessage = (e) => {
          const { status, progress_detail, error } = JSON.parse(e.data) as { status: string; progress_detail: string; error: string };
          if (progress_detail !== undefined) setPdfProgressDetail(progress_detail || undefined);
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
      if (!dlRes.ok) {
        let msg = `Error ${dlRes.status}`;
        try { const b = await dlRes.json(); msg = b.detail ?? b.message ?? msg; } catch {}
        throw new Error(msg);
      }
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
      setPdfProgressDetail(undefined);
      setPdfPhase('error');
      setTimeout(() => setPdfPhase('idle'), 5000);
      return;
    }
    setPdfPhase('idle');
    setPdfProgressDetail(undefined);
  }

  function handleSaveTemplate(t: TemplateConfig) {
    setTemplateConfig(t);
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
    <div className="flex flex-col md:h-screen">
      <AppHeader
        activeView={activeView}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={handleToggleSidebar}
      />

      <div className="relative flex flex-1 md:min-h-0">
        {mobileNavOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/40 md:hidden"
            onClick={() => setMobileNavOpen(false)}
          />
        )}
        <AppSidebar
          activeView={activeView}
          onViewChange={setActiveView}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
          mobileOpen={mobileNavOpen}
          onMobileClose={() => setMobileNavOpen(false)}
        />

      <div className="flex flex-1 min-w-0 flex-col md:overflow-hidden">
      {activeView === 'consultas-sat' && <ConsultasSATPage />}
      {/* BatchAnalysisPage stays mounted to preserve pool state when navigating away */}
      <div className={activeView === 'masivo' ? 'flex flex-col md:h-full md:overflow-hidden' : 'hidden'}>
        <BatchAnalysisPage
          onProgressUpdate={(status) => {
            if (status?.phase === 'processing' && status.completed === 0) setWidgetDismissed(false);
            setBatchMasivoStatus(status);
          }}
          pendingFiles={batchFiles}
          onSelectFile={(file) => {
            setPendingFileName(file.name);
            setFromMasivo(true);
            resetForBatch();
            handleFileSelect(file, {
              onBeforeApply: (nextProfile) => {
                resetForFileSelect(nextProfile === 'pagos' ? 'pagos' : 'ingresos');
              },
            });
            setActiveView('inspector');
          }}
          onBatchNav={(files, index) => {
            setBatchNavFiles(files);
            setBatchNavIndex(index);
          }}
        />
      </div>
      {activeView === 'conversion-masiva' && <ConversionMasivaPage />}
      {activeView === 'emisores' && <EmisoresPage />}
      {activeView === 'pdf-templates' && (
          <div className="flex-1 flex flex-col md:h-full md:overflow-hidden">
          {/* Cargamos el editor financiero premium directo en tu pantalla */}
          <Editor 
          initialTemplate={templateConfig} 
          onSave={handleSaveTemplate} 
          />
          </div>
      )}
      {activeView === 'inspector' && (
        <>
          {/* Loader del análisis — drill-down desde Análisis masivo */}
          {!cfdi && (
            <div className="flex-1 flex items-center justify-center p-8 bg-gray-50">
              <CfdiAnalysisLoader
                fileName={pendingFileName}
                analysisLabel={analysisStageLabel}
                analysisProgress={analysisStageProgress}
                analysisDetail={analysisStageDetail}
              />
            </div>
          )}

          {/* Inspector completo — cuando hay un cfdi cargado */}
          {cfdi && (
            <>
              <InspectorHeader
                profileLabel={getProfileLabel(profile)}
                tableExported={tableExported}
                tableExportError={tableExportError}
                onExport={exportCurrentTable}
                onReset={fromMasivo
                  ? () => { setFromMasivo(false); setBatchNavFiles([]); resetForBatch(); setActiveView('masivo'); }
                  : resetAll}
                backLabel={fromMasivo ? 'Análisis masivo' : undefined}
                batchPosition={fromMasivo && batchNavFiles.length > 1 ? {
                  current: batchNavIndex,
                  total: batchNavFiles.length,
                  onPrev: batchNavIndex > 0
                    ? () => handleBatchNavigate(batchNavFiles[batchNavIndex - 1]!, batchNavIndex - 1)
                    : undefined,
                  onNext: batchNavIndex < batchNavFiles.length - 1
                    ? () => handleBatchNavigate(batchNavFiles[batchNavIndex + 1]!, batchNavIndex + 1)
                    : undefined,
                } : null}
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
                onDownloadPdfReportlab={sourceFile && pdfPhase === 'idle' ? () => handleDownloadPdf('reportlab', templateConfig) : undefined}
                onDownloadPdfGopdf={sourceFile && pdfPhase === 'idle' ? () => handleDownloadPdf('gopdfsuit', templateConfig) : undefined}
                onDownloadPdfCanvas={sourceFile && pdfPhase === 'idle' ? () => handleDownloadPdf('canvas_pipeline') : undefined}
                pdfPhase={pdfPhase}
                pdfProgressDetail={pdfProgressDetail}
                pdfError={pdfError}
              />

              <main className="flex flex-col bg-gray-50 p-4 gap-4 md:flex-1 md:min-h-0 md:overflow-hidden">
                {/* Fila 1 y 2: ocultas en modo Nodo XML para pantalla limpia */}
                {inspectorTab !== 'nodo-xml' && (
                  <>
                    <CfdiSummaryHeader summaryFields={summaryFields} />
                  </>
                )}

                {/* Fila 3: [Hallazgos si los hay] + panel principal */}
                <div className="relative flex flex-col gap-4 md:flex-row md:flex-1 md:min-h-0 md:overflow-hidden">
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

      {/* Floating progress widget — visible when batch is running and user is on another view */}
      {batchMasivoStatus && batchMasivoStatus.phase === 'processing' && activeView !== 'masivo' && !widgetDismissed && (
        <FloatingBatchWidget
          status={batchMasivoStatus}
          onNavigate={() => setActiveView('masivo')}
          onDismiss={() => setWidgetDismissed(true)}
        />
      )}
    </div>
  );
}
