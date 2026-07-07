import clsx from 'clsx';
import { ArrowLeft, ChevronLeft, ChevronRight, Download, FileText, Loader2, Search, ShieldCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { EnquiryResult } from '../lib/sat-enquiry-api-client';
import RfcValidationPanel from './RfcValidationPanel';
import type { FielStatus, RfcFormatResult, RfcSatResult } from '../lib/rfc-validation-api-client';

interface SatEnquiryData {
  uuid: string;
  rfcEmisor: string;
  rfcReceptor: string;
  total: number;
}

interface RfcValidationData {
  rfc: string;
  formatLoading: boolean;
  satLoading: boolean;
  formatResult: RfcFormatResult | null;
  satResult: RfcSatResult | null;
  satError: string | null;
  fielStatus: FielStatus | null;
  onValidateFormat: () => void;
  onValidateSat: () => void;
}

interface InspectorHeaderProps {
  profileLabel: string;
  tableExported: boolean;
  tableExportError: boolean;
  onReset: () => void;
  onExport: () => void;
  satEnquiryData?: SatEnquiryData | null;
  satLoading?: boolean;
  satResult?: EnquiryResult | null;
  satError?: string | null;
  onConsultarSat?: () => void;
  rfcValidation?: RfcValidationData | null;
  inspectorTab?: 'auditoria' | 'nodo-xml';
  onTabChange?: (tab: 'auditoria' | 'nodo-xml') => void;
  hasFindings?: boolean;
  modifiedXml?: string | null;
  onDownloadModified?: () => void;
  onDownloadPdf?: () => void;
  onDownloadPdfReportlab?: () => void;
  onDownloadPdfGopdf?: () => void;
  onDownloadPdfCanvas?: () => void;
  pdfPhase?: 'idle' | 'parsing' | 'rendering_html' | 'generating_pdf' | 'error';
  pdfProgressDetail?: string;
  pdfError?: string;
  backLabel?: string;
  batchPosition?: {
    current: number;
    total: number;
    onPrev?: () => void;
    onNext?: () => void;
  } | null;
}

function SatResultBadge({ result }: { result: EnquiryResult }) {
  if (result.error) {
    return (
      <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-tiny font-medium bg-red-100 text-red-700">
        Error SAT
      </span>
    );
  }
  const isVigente = result.estado.toLowerCase().includes('vigente');
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-tiny font-medium',
        isVigente ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-600',
      )}
      title={[result.estado, result.es_cancelable, result.estatus_cancelacion]
        .filter(Boolean)
        .join(' · ')}
    >
      {result.estado || '—'}
    </span>
  );
}

const PROFILE_BADGE: Record<string, { label: string; class: string }> = {
  Ingreso: { label: 'Ingreso', class: 'bg-blue-100 text-blue-700' },
  Pagos:   { label: 'Pagos',   class: 'bg-violet-100 text-violet-700' },
};

export default function InspectorHeader({
  profileLabel,
  tableExported,
  tableExportError,
  onReset,
  onExport,
  satEnquiryData,
  satLoading = false,
  satResult,
  satError,
  onConsultarSat,
  rfcValidation,
  inspectorTab,
  onTabChange,
  hasFindings = false,
  modifiedXml,
  onDownloadModified,
  onDownloadPdf,
  onDownloadPdfReportlab,
  onDownloadPdfGopdf,
  onDownloadPdfCanvas,
  pdfPhase = 'idle',
  pdfProgressDetail,
  pdfError,
  backLabel,
  batchPosition,
}: InspectorHeaderProps) {
  const canEnquire = !!satEnquiryData?.rfcEmisor && !satLoading;
  const profileBadge = PROFILE_BADGE[profileLabel];
  const [rfcPanelOpen, setRfcPanelOpen] = useState(false);
  const rfcPanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!rfcPanelOpen) return;
    function onOutsideClick(e: MouseEvent) {
      if (rfcPanelRef.current && !rfcPanelRef.current.contains(e.target as Node)) {
        setRfcPanelOpen(false);
      }
    }
    document.addEventListener('mousedown', onOutsideClick);
    return () => document.removeEventListener('mousedown', onOutsideClick);
  }, [rfcPanelOpen]);

  const rfcFormatOk = rfcValidation?.formatResult?.formatoValido && rfcValidation?.formatResult?.digitoVerificador;

  return (
    <header className="shrink-0 flex items-center gap-4 border-b border-gray-200 bg-white px-5 py-3.5">
      {/* Izquierda: nav + título */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onReset}
          className={clsx(
            'flex shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-500 transition-colors duration-200 hover:border-gray-300 hover:bg-gray-100 hover:text-gray-700',
            backLabel ? 'gap-1.5 px-2.5 h-8' : 'size-8',
          )}
        >
          <ArrowLeft size={16} />
          {backLabel && (
            <span className="text-tiny font-medium leading-none">{backLabel}</span>
          )}
        </button>

        {batchPosition && (
          <div className="flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 px-1 py-0.5">
            <button
              onClick={batchPosition.onPrev}
              disabled={!batchPosition.onPrev}
              className="rounded p-1 text-gray-400 transition-colors hover:bg-white hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-30"
              title="CFDI anterior en el lote"
            >
              <ChevronLeft size={14} />
            </button>
            <span className="select-none px-1 text-tiny tabular-nums text-gray-400">
              {batchPosition.current + 1} / {batchPosition.total}
            </span>
            <button
              onClick={batchPosition.onNext}
              disabled={!batchPosition.onNext}
              className="rounded p-1 text-gray-400 transition-colors hover:bg-white hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-30"
              title="CFDI siguiente en el lote"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}

        <div className="flex items-center gap-2 min-w-0">
          {profileBadge && (
            <span className={clsx('inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-tiny font-semibold', profileBadge.class)}>
              {profileBadge.label}
            </span>
          )}
          <span className="text-sm font-semibold text-gray-800 truncate">Inspector</span>
        </div>
      </div>

      {/* Centro: toggle de pantalla */}
      <div className="flex flex-1 justify-center">
        {hasFindings && inspectorTab && onTabChange && (
          <div className="flex items-center rounded-lg border border-gray-200 bg-gray-50 p-0.5 gap-0.5">
            {(['auditoria', 'nodo-xml'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => onTabChange(tab)}
                className={clsx(
                  'rounded-md px-3 py-1 text-xs font-medium transition-all duration-150',
                  inspectorTab === tab
                    ? 'bg-white text-gray-800 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700',
                )}
              >
                {tab === 'auditoria' ? 'Auditoría' : 'Nodo XML'}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Derecha: acciones */}
      <div className="flex items-center gap-2 shrink-0">
        {satResult && <SatResultBadge result={satResult} />}
        {satError && !satResult && (
          <span className="max-w-[220px] text-xs text-red-500 leading-tight" title={satError}>
            {satError.includes('no configurado')
              ? 'RFC emisor sin credenciales — configura en Emisores'
              : satError}
          </span>
        )}

        {/* Validar RFC button + popover */}
        {rfcValidation && (
          <div className="relative" ref={rfcPanelRef}>
            <button
              onClick={() => {
                setRfcPanelOpen((v) => !v);
                if (!rfcValidation.formatResult && !rfcValidation.formatLoading) {
                  rfcValidation.onValidateFormat();
                }
              }}
              title="Verifica que el RFC del emisor tenga formato correcto y exista en el SAT"
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors duration-200',
                rfcFormatOk === true
                  ? 'border-emerald-200 text-emerald-700 hover:border-emerald-300 hover:bg-emerald-50'
                  : rfcFormatOk === false
                    ? 'border-red-200 text-red-700 hover:border-red-300 hover:bg-red-50'
                    : 'border-violet-200 text-violet-700 hover:border-violet-300 hover:bg-violet-50',
              )}
            >
              {rfcValidation.formatLoading || rfcValidation.satLoading ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <ShieldCheck size={13} />
              )}
              Validar RFC
            </button>

            {rfcPanelOpen && (
              <div className="absolute right-0 top-full mt-2 z-50 shadow-lg">
                <RfcValidationPanel
                  rfc={rfcValidation.rfc}
                  formatLoading={rfcValidation.formatLoading}
                  satLoading={rfcValidation.satLoading}
                  formatResult={rfcValidation.formatResult}
                  satResult={rfcValidation.satResult}
                  satError={rfcValidation.satError}
                  fielStatus={rfcValidation.fielStatus}
                  onValidateFormat={rfcValidation.onValidateFormat}
                  onValidateSat={rfcValidation.onValidateSat}
                />
              </div>
            )}
          </div>
        )}

        {satEnquiryData && (
          <button
            onClick={onConsultarSat}
            disabled={!canEnquire}
            title="Pregunta al SAT si este CFDI está vigente, cancelado o puede cancelarse"
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors duration-200',
              canEnquire
                ? 'border-blue-200 text-blue-700 hover:border-blue-300 hover:bg-blue-50'
                : 'border-gray-200 text-gray-400 cursor-not-allowed opacity-50',
            )}
          >
            {satLoading ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Search size={13} />
            )}
            {satLoading ? 'Consultando…' : 'Consultar SAT'}
          </button>
        )}

        {modifiedXml && onDownloadModified && (
          <button
            onClick={onDownloadModified}
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 px-3 py-1.5 text-xs font-medium text-emerald-700 transition-colors duration-200 hover:bg-emerald-50"
          >
            <Download size={13} />
            Descargar corregido
          </button>
        )}

        {onDownloadPdf && pdfPhase === 'idle' && (
          <div className="inline-flex rounded-lg border border-gray-200 overflow-hidden">
            <button
              onClick={onDownloadPdf}
              title="PDF oficial — layout SAT exacto"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors duration-200 hover:bg-gray-50 border-r border-gray-200"
            >
              <Download size={13} />
              PDF
            </button>
            {onDownloadPdfReportlab && (
              <button
                onClick={onDownloadPdfReportlab}
                title="PDF personalizado — diseño propio, generación rápida"
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-blue-600 transition-colors duration-200 hover:bg-blue-50 border-r border-gray-200"
              >
                ⚡ PDF Pro
              </button>
            )}
            {onDownloadPdfGopdf && (
              <button
                onClick={onDownloadPdfGopdf}
                title="Experimento masivo — Motor GoPdfSuit"
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-purple-600 transition-colors duration-200 hover:bg-purple-50 border-r border-gray-200"
              >
                🚀 Go PDF
              </button>
            )}
            {onDownloadPdfCanvas && (
              <button
                onClick={onDownloadPdfCanvas}
                title="Canvas Pipeline — header + conceptos streaming + footer, escala a 100k+"
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-emerald-600 transition-colors duration-200 hover:bg-emerald-50"
              >
                ⚡ Canvas
              </button>
            )}
          </div>
        )}

        {pdfPhase !== 'idle' && (
          <div className={clsx(
            'inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium',
            pdfPhase === 'error'
              ? 'border-red-200 bg-red-50 text-red-700'
              : 'border-blue-200 bg-blue-50 text-blue-700',
          )}>
            {pdfPhase !== 'error' && <Loader2 size={13} className="animate-spin shrink-0" />}
            <span className="flex flex-col leading-tight">
              <span>
                {pdfPhase === 'parsing' && 'Analizando XML…'}
                {pdfPhase === 'rendering_html' && 'Generando vista…'}
                {pdfPhase === 'generating_pdf' && 'Creando PDF…'}
                {pdfPhase === 'error' && (pdfError ?? 'Error al generar PDF')}
              </span>
              {pdfProgressDetail && pdfPhase !== 'error' && (
                <span className="text-blue-500 font-normal">{pdfProgressDetail}</span>
              )}
            </span>
          </div>
        )}

        <button
          onClick={onExport}
          className={clsx(
            'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-200',
            tableExported
              ? 'bg-emerald-600 text-white hover:bg-emerald-700'
              : tableExportError
                ? 'bg-red-600 text-white hover:bg-red-700'
                : 'bg-primary-600 text-white hover:bg-primary-700',
          )}
        >
          <FileText size={13} />
          {tableExported ? 'Exportado' : tableExportError ? 'Sin datos' : 'Exportar'}
        </button>
      </div>
    </header>
  );
}
