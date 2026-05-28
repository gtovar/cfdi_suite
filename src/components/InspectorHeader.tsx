import clsx from 'clsx';
import { ArrowLeft, FileText, Loader2, Search } from 'lucide-react';
import type { EnquiryResult } from '../lib/sat-enquiry-api-client';

interface SatEnquiryData {
  uuid: string;
  rfcEmisor: string;
  rfcReceptor: string;
  total: number;
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
}

function SatResultBadge({ result }: { result: EnquiryResult }) {
  if (result.error) {
    return (
      <span className="inline-flex items-center rounded px-2 py-0.5 text-tiny font-medium bg-red-100 text-red-700">
        Error
      </span>
    );
  }
  const isVigente = result.estado.toLowerCase().includes('vigente');
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded px-2 py-0.5 text-tiny font-medium',
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
}: InspectorHeaderProps) {
  const canEnquire = !!satEnquiryData?.rfcEmisor && !satLoading;

  return (
    <header className="shrink-0 flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3">
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onReset}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-600 transition-colors duration-200 hover:border-gray-300 hover:bg-gray-100 hover:text-gray-800"
        >
          <ArrowLeft size={16} />
        </button>

        <span className="text-xs-plus font-medium text-gray-700 truncate">{profileLabel}</span>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {satResult && <SatResultBadge result={satResult} />}
        {satError && !satResult && (
          <span className="max-w-[120px] truncate text-xs text-red-500" title={satError}>
            {satError}
          </span>
        )}

        {satEnquiryData && (
          <button
            onClick={onConsultarSat}
            disabled={!canEnquire}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs-plus font-medium transition-colors duration-200',
              'border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-100',
              'disabled:cursor-not-allowed disabled:opacity-40',
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

        <button
          onClick={onExport}
          className={clsx(
            'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs-plus font-medium transition-colors duration-200',
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
