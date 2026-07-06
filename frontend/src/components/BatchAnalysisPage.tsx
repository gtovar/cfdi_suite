import clsx from 'clsx';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Download,
  FileDown,
  Filter,
  FolderOpen,
  Loader2,
  RotateCcw,
  Upload,
  XCircle,
  Zap,
} from 'lucide-react';
import {
  type ColumnDef,
  type Row,
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { batchAnalyzePool, batchDiot, type BatchFileResult } from '../lib/batch-api-client';
import {
  type PdfConversionState,
  convertFileToPdf,
  triggerBlobDownload,
  Semaphore,
} from '../lib/pdf-download';
import { runPreflight, type PreflightSummary } from '../lib/preflight';
import {
  useBatchStats,
  formatMonto,
  formatRemainingTime,
  formatTopMonth,
  type QueueEntry,
} from '../lib/useBatchStats';
import BatchPipelineIndicator from './BatchPipelineIndicator';
import BatchCompletionModal from './BatchCompletionModal';
import type { BatchProgressStatus } from './FloatingBatchWidget';

// ── Types ─────────────────────────────────────────────────────────────────────

type Phase = 'idle' | 'processing' | 'done';
type FilterStatus = 'all' | 'ok' | 'con_errores' | 'error';

interface BatchAnalysisPageProps {
  onProgressUpdate?: (status: BatchProgressStatus | null) => void;
  onSelectFile?: (file: File) => void;
  onBatchNav?: (orderedFiles: File[], currentIndex: number) => void;
  pendingFiles?: File[] | null;
  templateId?: string;
}

// ── Table columns ──────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  ok: { label: 'Sin errores', badge: 'bg-green-50 text-green-700', Icon: CheckCircle2 },
  con_errores: { label: 'Con hallazgos', badge: 'bg-yellow-50 text-yellow-700', Icon: AlertCircle },
  error: { label: 'Error de lectura', badge: 'bg-red-50 text-red-700', Icon: XCircle },
} as const;

const colHelper = createColumnHelper<BatchFileResult>();

const COLUMNS = [
  colHelper.accessor('filename', {
    header: 'Archivo',
    cell: (info) => (
      <span className="block max-w-[220px] truncate font-mono text-xs text-gray-800" title={info.getValue()}>
        {info.getValue()}
      </span>
    ),
  }),
  colHelper.accessor('status', {
    header: 'Estado',
    cell: (info) => {
      const cfg = STATUS_CONFIG[info.getValue()];
      return (
        <span className={clsx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-tiny font-medium', cfg.badge)}>
          <cfg.Icon size={11} />
          {cfg.label}
        </span>
      );
    },
  }),
  colHelper.accessor('profile', {
    header: 'Tipo',
    cell: (info) => {
      const v = info.getValue();
      return <span className="text-xs text-gray-600">{v === 'ingreso' ? 'Ingreso' : v === 'pagos' ? 'Pagos' : '—'}</span>;
    },
  }),
  colHelper.accessor('rfc_emisor', {
    header: 'RFC Emisor',
    cell: (info) => <span className="font-mono text-xs text-gray-700">{info.getValue() || '—'}</span>,
  }),
  colHelper.accessor('nombre_emisor', {
    header: 'Emisor',
    cell: (info) => (
      <span className="block max-w-[180px] truncate text-xs text-gray-600" title={info.getValue()}>
        {info.getValue() || '—'}
      </span>
    ),
  }),
  colHelper.accessor('total', {
    header: 'Total',
    cell: (info) => {
      const v = info.getValue();
      if (!v) return <span className="text-xs text-gray-400">—</span>;
      const n = parseFloat(v);
      if (isNaN(n)) return <span className="text-xs text-gray-700">{v}</span>;
      return (
        <span className="text-xs tabular-nums text-gray-800">
          {n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })}
        </span>
      );
    },
  }),
  colHelper.accessor('fecha', {
    header: 'Fecha',
    cell: (info) => <span className="text-xs text-gray-600">{info.getValue() || '—'}</span>,
  }),
  colHelper.accessor('findings_count', {
    header: 'Hallazgos',
    cell: (info) => {
      const n = info.getValue();
      if (n === 0) return <span className="text-xs text-gray-400">—</span>;
      return (
        <span className="inline-flex items-center justify-center rounded-full bg-yellow-100 px-2 py-0.5 text-tiny font-medium text-yellow-800">
          {n}
        </span>
      );
    },
  }),
  colHelper.display({
    id: 'action',
    cell: (info) =>
      info.row.original.status === 'error' ? null : (
        <ChevronRight
          size={13}
          className="text-gray-300 group-hover:text-primary-400 transition-colors duration-100"
        />
      ),
  }),
];

// ── Helpers ────────────────────────────────────────────────────────────────────

const MESES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

function defaultPeriod() {
  const d = new Date();
  const month = d.getMonth() === 0 ? 12 : d.getMonth();
  const year = d.getMonth() === 0 ? d.getFullYear() - 1 : d.getFullYear();
  return { month, year };
}

function dedupeFiles(all: File[]): File[] {
  const seen = new Set<string>();
  return all.filter((f) => {
    const key = `${f.name}-${f.size}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function exportResultsCsv(results: BatchFileResult[], filename = 'cfdi-batch.csv') {
  const cols: (keyof BatchFileResult)[] = ['filename', 'status', 'profile', 'rfc_emisor', 'nombre_emisor', 'total', 'fecha', 'findings_count', 'error'];
  const header = cols.join(',');
  const rows = results.map(r =>
    cols.map(c => {
      const v = r[c];
      if (v === null || v === undefined || v === '') return '';
      return `"${String(v).replace(/"/g, '""')}"`;
    }).join(',')
  );
  const blob = new Blob(['﻿' + header + '\n' + rows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function formatDateRange(min: string, max: string): string {
  const fmt = (d: string) => {
    const [y, m] = d.split('-');
    return `${MESES[parseInt(m, 10) - 1]?.slice(0, 3) ?? m} ${y}`;
  };
  return min === max ? fmt(min) : `${fmt(min)} – ${fmt(max)}`;
}

export function computeMonthBreakdown(
  queue: Array<{ result: { status: string; fecha?: string | null; total?: string | null } | null }>,
  topN = 3,
): Array<{ month: string; count: number; monto: number }> {
  const map = new Map<string, { count: number; monto: number }>();
  queue.forEach(({ result: r }) => {
    if (!r || r.status === 'error' || !r.fecha) return;
    const key = r.fecha.slice(0, 7);
    const prev = map.get(key) ?? { count: 0, monto: 0 };
    const n = parseFloat(r.total || '0');
    map.set(key, { count: prev.count + 1, monto: prev.monto + (isNaN(n) ? 0 : n) });
  });
  return [...map.entries()]
    .map(([month, v]) => ({ month, ...v }))
    .sort((a, b) => b.count - a.count)
    .slice(0, topN);
}

export function splitByQuincena(
  files: File[],
  getDay: (f: File) => number,
): { first: File[]; second: File[] } {
  return files.reduce<{ first: File[]; second: File[] }>(
    (acc, f) => {
      const day = getDay(f);
      (Number.isFinite(day) && day <= 15 ? acc.first : acc.second).push(f);
      return acc;
    },
    { first: [], second: [] },
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function PreflightCard({
  preflight,
  loading,
}: {
  preflight: PreflightSummary | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-xs text-gray-500">
        <Loader2 size={12} className="animate-spin" />
        Escaneando muestra de archivos…
      </div>
    );
  }
  if (!preflight) return null;

  return (
    <div className="rounded-xl border border-primary-100 bg-primary-50/60 px-4 py-3">
      <p className="mb-1.5 text-tiny font-semibold uppercase tracking-wider text-primary-700">
        Pre-vuelo
      </p>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-700">
        <span>
          <span className="font-semibold text-gray-900">{preflight.validCfdi.toLocaleString('es-MX')}</span> facturas CFDI detectadas
          {preflight.sampleScanned < preflight.totalFiles && (
            <span className="text-gray-400"> (estimado de {preflight.sampleScanned} escaneados)</span>
          )}
        </span>
        {preflight.possibleDuplicates > 0 && (
          <span className="text-yellow-600">
            <AlertCircle size={11} className="inline mr-0.5" />
            {preflight.possibleDuplicates} posibles duplicados
          </span>
        )}
        {preflight.dateRange && (
          <span className="text-gray-500">
            Fechas: {formatDateRange(preflight.dateRange.min, preflight.dateRange.max)}
          </span>
        )}
        {preflight.topRfcEmisores.length > 0 && (
          <span className="text-gray-500">
            Emisores: {preflight.topRfcEmisores.join(', ')}
          </span>
        )}
      </div>
    </div>
  );
}

function StatsCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex-1 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
      <p className="text-tiny font-medium uppercase tracking-wider text-gray-400">{label}</p>
      <p className="mt-0.5 text-lg font-bold tabular-nums text-gray-900">{value}</p>
      {sub && <p className="text-tiny text-gray-400">{sub}</p>}
    </div>
  );
}

function InsightCard({ icon, label, value, sub }: { icon: string; label: string; value: string; sub?: string }) {
  return (
    <div className="insight-slide-in flex items-start gap-2.5 rounded-xl border border-gray-100 bg-white px-3 py-2.5 shadow-sm">
      <span className="mt-0.5 text-base">{icon}</span>
      <div className="min-w-0">
        <p className="text-tiny font-medium text-gray-400">{label}</p>
        <p className="truncate text-xs font-semibold text-gray-800">{value}</p>
        {sub && <p className="text-tiny text-gray-400">{sub}</p>}
      </div>
    </div>
  );
}

function TriageHeader({
  stats,
  filterStatus,
  onFilter,
}: {
  stats: ReturnType<typeof useBatchStats>;
  filterStatus: FilterStatus;
  onFilter: (s: FilterStatus) => void;
}) {
  const total = stats.ok + stats.conErrores + stats.errors;

  return (
    <div className="flex flex-col gap-3">
      {/* Status boxes — clicables para filtrar */}
      <div className="flex gap-3">
        <button
          onClick={() => onFilter(filterStatus === 'ok' ? 'all' : 'ok')}
          className={clsx(
            'flex-1 rounded-xl border px-4 py-3 text-left transition-all duration-150',
            filterStatus === 'ok'
              ? 'border-green-300 bg-green-50 ring-2 ring-green-300 ring-offset-1'
              : 'border-green-100 bg-green-50 hover:border-green-200 hover:ring-1 hover:ring-green-200 hover:ring-offset-1',
          )}
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className="text-green-500" />
            <span className="text-2xl font-bold tabular-nums text-green-700">{stats.ok.toLocaleString('es-MX')}</span>
          </div>
          <p className="mt-0.5 text-tiny font-medium text-green-600">
            Sin errores · {total > 0 ? Math.round((stats.ok / total) * 100) : 0}%
          </p>
        </button>
        {stats.conErrores > 0 && (
          <button
            onClick={() => onFilter(filterStatus === 'con_errores' ? 'all' : 'con_errores')}
            className={clsx(
              'flex-1 rounded-xl border px-4 py-3 text-left transition-all duration-150',
              filterStatus === 'con_errores'
                ? 'border-yellow-300 bg-yellow-50 ring-2 ring-yellow-300 ring-offset-1'
                : 'border-yellow-100 bg-yellow-50 hover:border-yellow-200 hover:ring-1 hover:ring-yellow-200 hover:ring-offset-1',
            )}
          >
            <div className="flex items-center gap-2">
              <AlertCircle size={16} className="text-yellow-500" />
              <span className="text-2xl font-bold tabular-nums text-yellow-700">{stats.conErrores.toLocaleString('es-MX')}</span>
            </div>
            <p className="mt-0.5 text-tiny font-medium text-yellow-600">
              Con hallazgos · {total > 0 ? Math.round((stats.conErrores / total) * 100) : 0}%
            </p>
          </button>
        )}
        {stats.errors > 0 && (
          <button
            onClick={() => onFilter(filterStatus === 'error' ? 'all' : 'error')}
            className={clsx(
              'flex-1 rounded-xl border px-4 py-3 text-left transition-all duration-150',
              filterStatus === 'error'
                ? 'border-red-300 bg-red-50 ring-2 ring-red-300 ring-offset-1'
                : 'border-red-100 bg-red-50 hover:border-red-200 hover:ring-1 hover:ring-red-200 hover:ring-offset-1',
            )}
          >
            <div className="flex items-center gap-2">
              <XCircle size={16} className="text-red-500" />
              <span className="text-2xl font-bold tabular-nums text-red-700">{stats.errors.toLocaleString('es-MX')}</span>
            </div>
            <p className="mt-0.5 text-tiny font-medium text-red-600">
              Errores · {total > 0 ? Math.round((stats.errors / total) * 100) : 0}%
            </p>
          </button>
        )}
      </div>

      {/* Filter pills */}
      <div className="flex items-center gap-2">
        <Filter size={12} className="shrink-0 text-gray-400" />
        {(
          [
            { key: 'all', label: 'Todas' },
            { key: 'ok', label: 'Sin errores' },
            { key: 'con_errores', label: 'Con hallazgos' },
            { key: 'error', label: 'Solo errores' },
          ] as { key: FilterStatus; label: string }[]
        ).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => onFilter(key)}
            className={clsx(
              'rounded-full px-3 py-1 text-tiny font-medium transition-colors duration-150',
              filterStatus === key
                ? 'bg-primary-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
            )}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function LiveQueueTable({ queue, flashSet }: { queue: QueueEntry[]; flashSet: Set<number> }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: queue.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 36,
    overscan: 5,
  });

  const vItems = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();
  const paddingTop = vItems[0]?.start ?? 0;
  const paddingBottom = vItems.length > 0 ? totalSize - (vItems[vItems.length - 1]!.end) : 0;

  return (
    <div ref={containerRef} className="overflow-auto h-72 rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="w-full text-left">
        <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50">
          <tr>
            <th className="px-3 py-2 text-tiny font-semibold uppercase tracking-wider text-gray-500">Archivo</th>
            <th className="px-3 py-2 text-tiny font-semibold uppercase tracking-wider text-gray-500">Estado</th>
            <th className="px-3 py-2 text-tiny font-semibold uppercase tracking-wider text-gray-500">RFC Emisor</th>
            <th className="px-3 py-2 text-tiny font-semibold uppercase tracking-wider text-gray-500">Emisor</th>
            <th className="px-3 py-2 text-tiny font-semibold uppercase tracking-wider text-gray-500">Total</th>
            <th className="px-3 py-2 text-tiny font-semibold uppercase tracking-wider text-gray-500">Fecha</th>
          </tr>
        </thead>
        <tbody>
          {paddingTop > 0 && <tr><td colSpan={6} style={{ height: `${paddingTop}px`, padding: 0 }} /></tr>}
          {vItems.map((vItem) => {
            const entry = queue[vItem.index]!;
            const r = entry.result;
            const isNew = flashSet.has(vItem.index);
            const flashClass = isNew && r
              ? r.status === 'ok' ? 'row-flash-ok' : r.status === 'con_errores' ? 'row-flash-yellow' : 'row-flash-red'
              : '';

            if (!r) {
              return (
                <tr key={vItem.key} className="border-b border-gray-100" style={{ height: 36 }}>
                  <td className="px-3 py-2">
                    <span className="block max-w-[200px] truncate font-mono text-xs text-gray-400">{entry.file.name}</span>
                  </td>
                  <td className="px-3 py-2"><div className="h-3.5 w-20 rounded-full bg-gray-200 animate-pulse" /></td>
                  <td className="px-3 py-2"><div className="h-3.5 w-24 rounded bg-gray-200 animate-pulse" /></td>
                  <td className="px-3 py-2"><div className="h-3.5 w-28 rounded bg-gray-200 animate-pulse" /></td>
                  <td className="px-3 py-2"><div className="h-3.5 w-16 rounded bg-gray-200 animate-pulse" /></td>
                  <td className="px-3 py-2"><div className="h-3.5 w-16 rounded bg-gray-200 animate-pulse" /></td>
                </tr>
              );
            }

            const cfg = STATUS_CONFIG[r.status];
            const totalNum = parseFloat(r.total);
            return (
              <tr key={vItem.key} className={clsx('border-b border-gray-100', flashClass)} style={{ height: 36 }}>
                <td className="px-3 py-2">
                  <span className="block max-w-[200px] truncate font-mono text-xs text-gray-800" title={r.filename}>{r.filename}</span>
                </td>
                <td className="px-3 py-2">
                  <span className={clsx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-tiny font-medium', cfg.badge)}>
                    <cfg.Icon size={11} />{cfg.label}
                  </span>
                </td>
                <td className="px-3 py-2"><span className="font-mono text-xs text-gray-700">{r.rfc_emisor || '—'}</span></td>
                <td className="px-3 py-2">
                  <span className="block max-w-[160px] truncate text-xs text-gray-600" title={r.nombre_emisor}>{r.nombre_emisor || '—'}</span>
                </td>
                <td className="px-3 py-2">
                  {isNaN(totalNum)
                    ? <span className="text-xs text-gray-700">{r.total || '—'}</span>
                    : <span className="text-xs tabular-nums text-gray-800">{totalNum.toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })}</span>}
                </td>
                <td className="px-3 py-2"><span className="text-xs text-gray-600">{r.fecha || '—'}</span></td>
              </tr>
            );
          })}
          {paddingBottom > 0 && <tr><td colSpan={6} style={{ height: `${paddingBottom}px`, padding: 0 }} /></tr>}
        </tbody>
      </table>
    </div>
  );
}

// ── PDF helpers ───────────────────────────────────────────────────────────────

function IndeterminateCheckbox({
  checked,
  indeterminate,
  onChange,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (checked: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = !!indeterminate;
  }, [indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      onClick={(e) => e.stopPropagation()}
      className="h-3.5 w-3.5 cursor-pointer rounded border-gray-300 text-primary-600 accent-primary-600"
    />
  );
}

function PdfDownloadButton({
  state,
  onClick,
}: {
  state: PdfConversionState;
  onClick: () => void;
}) {
  if (state === 'converting') {
    return <Loader2 size={12} className="animate-spin text-primary-400" />;
  }
  if (state === 'done') {
    return <CheckCircle2 size={12} className="text-green-500" title="PDF descargado" />;
  }
  if (state === 'error') {
    return (
      <button
        onClick={(e) => { e.stopPropagation(); onClick(); }}
        title="Error — clic para reintentar"
        className="transition-colors text-red-400 hover:text-red-600"
      >
        <XCircle size={12} />
      </button>
    );
  }
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      title="Descargar PDF"
      className="flex items-center gap-1 rounded px-1.5 py-0.5 text-tiny font-medium text-gray-400 transition-colors hover:bg-primary-50 hover:text-primary-600"
    >
      <FileDown size={11} />
      PDF
    </button>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function BatchAnalysisPage({ onProgressUpdate, onSelectFile, onBatchNav, pendingFiles, templateId }: BatchAnalysisPageProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [phase, setPhase] = useState<Phase>('idle');
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [preflight, setPreflight] = useState<PreflightSummary | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');
  const [doneView, setDoneView] = useState<'resultados' | 'diot'>('resultados');
  const [showModal, setShowModal] = useState(false);
  const [processStartTime, setProcessStartTime] = useState<number | null>(null);
  const [processEndTime, setProcessEndTime] = useState<number | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const poolCancelRef = useRef<(() => void) | null>(null);
  const cancelledRef = useRef(false);
  const runIdRef = useRef(0);
  const completionTimestampsRef = useRef<Map<number, number>>(new Map());
  const doneTableRef = useRef<HTMLDivElement>(null);

  const { month: defaultMonth, year: defaultYear } = defaultPeriod();
  const [diotMonth, setDiotMonth] = useState(defaultMonth);
  const [diotYear, setDiotYear] = useState(defaultYear);
  const [diotRfc, setDiotRfc] = useState('');
  const [diotLoading, setDiotLoading] = useState(false);
  const [diotError, setDiotError] = useState<string | null>(null);
  const [diotSuccess, setDiotSuccess] = useState(false);
  const [diotHalves, setDiotHalves] = useState<{ first: File[]; second: File[] } | null>(null);
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());
  const [pdfStates, setPdfStates] = useState<Map<string, PdfConversionState>>(new Map());

  // ── Derived ──────────────────────────────────────────────────────────────────
  const stats = useBatchStats(queue, files.length);

  const flashSet = useMemo(() => {
    const now = Date.now();
    const s = new Set<number>();
    completionTimestampsRef.current.forEach((ts, idx) => {
      if (now - ts < 1200) s.add(idx);
    });
    return s;
  }, [stats.completed]);

  const filteredResults = useMemo(
    () =>
      queue
        .filter((e) => e.result !== null && (filterStatus === 'all' || e.result.status === filterStatus))
        .map((e) => e.result!),
    [queue, filterStatus],
  );

  const monthBreakdown = useMemo(() => computeMonthBreakdown(queue), [queue]);

  const fileByName = useMemo(
    () => new Map(queue.map((e) => [e.file.name, e.file])),
    [queue],
  );

  const someAreConverting = useMemo(
    () => Array.from(selectedRows).some((n) => pdfStates.get(n) === 'converting'),
    [selectedRows, pdfStates],
  );

  const handleDownloadPdf = useCallback(async (filename: string) => {
    const file = fileByName.get(filename);
    if (!file || pdfStates.get(filename) === 'converting') return;
    setPdfStates((prev) => new Map(prev).set(filename, 'converting'));
    try {
      const buf = await convertFileToPdf(file, templateId);
      triggerBlobDownload(
        new Blob([buf], { type: 'application/pdf' }),
        filename.replace(/\.xml$/i, '.pdf'),
      );
      setPdfStates((prev) => new Map(prev).set(filename, 'done'));
    } catch {
      setPdfStates((prev) => new Map(prev).set(filename, 'error'));
    }
  }, [fileByName, pdfStates, templateId]);

  const extendedColumns = useMemo((): ColumnDef<BatchFileResult>[] => {
    const allFiltered = filteredResults.length > 0 && filteredResults.every((r) => selectedRows.has(r.filename));
    const someFiltered = filteredResults.some((r) => selectedRows.has(r.filename));

    const checkboxCol = colHelper.display({
      id: '_select',
      enableSorting: false,
      header: () => (
        <IndeterminateCheckbox
          checked={allFiltered}
          indeterminate={someFiltered && !allFiltered}
          onChange={(checked) => {
            setSelectedRows((prev) => {
              const next = new Set(prev);
              filteredResults.forEach((r) => (checked ? next.add(r.filename) : next.delete(r.filename)));
              return next;
            });
          }}
        />
      ),
      cell: (info) => (
        <IndeterminateCheckbox
          checked={selectedRows.has(info.row.original.filename)}
          onChange={(checked) => {
            setSelectedRows((prev) => {
              const next = new Set(prev);
              checked ? next.add(info.row.original.filename) : next.delete(info.row.original.filename);
              return next;
            });
          }}
        />
      ),
    });

    const pdfCol = colHelper.display({
      id: '_pdf',
      enableSorting: false,
      header: () => null,
      cell: (info) => {
        if (info.row.original.status === 'error') return null;
        const filename = info.row.original.filename;
        const state = pdfStates.get(filename) ?? 'idle';
        return <PdfDownloadButton state={state} onClick={() => handleDownloadPdf(filename)} />;
      },
    });

    // Splice: checkbox at start, pdf before the action chevron at end
    const dataColumns = COLUMNS.slice(0, -1);
    const actionColumn = COLUMNS[COLUMNS.length - 1]!;
    return [checkboxCol, ...dataColumns, pdfCol, actionColumn];
  }, [filteredResults, selectedRows, pdfStates, handleDownloadPdf]);

  const diotMonthStr = useMemo(
    () => `${diotYear}-${String(diotMonth).padStart(2, '0')}`,
    [diotYear, diotMonth],
  );

  const diotMonthCount = useMemo(
    () => queue.filter(
      (e) => e.result && e.result.status !== 'error' && e.result.fecha?.startsWith(diotMonthStr)
    ).length,
    [queue, diotMonthStr],
  );

  const table = useReactTable<BatchFileResult>({
    data: filteredResults as BatchFileResult[],
    columns: extendedColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const doneRows: Row<BatchFileResult>[] = table.getRowModel().rows;
  const doneVirtualizer = useVirtualizer({
    count: doneRows.length,
    getScrollElement: () => doneTableRef.current,
    estimateSize: () => 36,
    overscan: 10,
  });

  const elapsedSeconds = processStartTime
    ? ((processEndTime ?? Date.now()) - processStartTime) / 1000
    : 0;

  // ── Effects ───────────────────────────────────────────────────────────────────

  // Set webkitdirectory attribute on folder input (TypeScript doesn't allow it as JSX prop)
  // Must re-run when phase changes because the input unmounts/remounts with the idle block
  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute('webkitdirectory', '');
      folderInputRef.current.setAttribute('directory', '');
    }
  }, [phase]);

  // Cancel pool on unmount
  useEffect(() => {
    return () => { poolCancelRef.current?.(); };
  }, []);

  // Consume files forwarded from the Inspector FileUpload (N-file redirect)
  useEffect(() => {
    if (!pendingFiles?.length) return;
    setFiles((prev) => dedupeFiles([...prev, ...pendingFiles]));
  }, [pendingFiles]);

  // Run preflight when files are selected
  useEffect(() => {
    if (files.length === 0) { setPreflight(null); setPreflightLoading(false); return; }
    setPreflightLoading(true);
    setPreflight(null);
    runPreflight(files).then((result) => {
      setPreflight(result);
      setPreflightLoading(false);
    });
  }, [files]);

  // Auto-detect RFC presentante from completed results
  useEffect(() => {
    if (diotRfc) return;
    for (const e of queue) {
      const rfc = e.result?.rfc_receptor;
      if (rfc && rfc !== 'XAXX010101000' && rfc !== 'XEXX010101000') {
        setDiotRfc(rfc);
        break;
      }
    }
  }, [stats.completed]); // eslint-disable-line react-hooks/exhaustive-deps

  // Propagate progress to App.tsx for FloatingBatchWidget
  useEffect(() => {
    if (phase === 'processing') {
      onProgressUpdate?.({ completed: stats.completed, total: files.length, phase: 'processing' });
    } else if (phase === 'done') {
      onProgressUpdate?.({ completed: files.length, total: files.length, phase: 'done' });
    }
  }, [stats.completed, phase]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Handlers ─────────────────────────────────────────────────────────────────

  function handleFileDrop(e: React.DragEvent) {
    e.preventDefault();
    const dropped = Array.from<File>(e.dataTransfer.files).filter((f) => f.name.endsWith('.xml'));
    if (dropped.length) setFiles((prev) => dedupeFiles([...prev, ...dropped]));
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from<File>(e.target.files ?? []).filter((f) => f.name.endsWith('.xml'));
    if (selected.length) setFiles((prev) => dedupeFiles([...prev, ...selected]));
    e.target.value = '';
  }

  function clearAll() {
    cancelledRef.current = true;
    poolCancelRef.current?.();
    poolCancelRef.current = null;
    completionTimestampsRef.current.clear();
    setFiles([]);
    setQueue([]);
    setPhase('idle');
    setPreflight(null);
    setPreflightLoading(false);
    setFilterStatus('all');
    setDoneView('resultados');
    setShowModal(false);
    setProcessStartTime(null);
    setProcessEndTime(null);
    setDiotRfc('');
    setDiotError(null);
    setDiotSuccess(false);
    setDiotHalves(null);
    setSelectedRows(new Set());
    setPdfStates(new Map());
    onProgressUpdate?.(null);
  }

  function handleProcess() {
    if (!files.length) return;
    cancelledRef.current = false;
    const runId = ++runIdRef.current;
    const startTime = Date.now();
    setProcessStartTime(startTime);
    setProcessEndTime(null);
    setPhase('processing');
    setShowModal(false);
    setFilterStatus('all');

    const initialQueue: QueueEntry[] = files.map((file) => ({ file, result: null }));
    setQueue(initialQueue);

    completionTimestampsRef.current.clear();
    const { promise, cancel } = batchAnalyzePool(
      files,
      (result, index) => {
        completionTimestampsRef.current.set(index, Date.now());
        setQueue((prev) => {
          const next = [...prev];
          if (next[index]) next[index] = { ...next[index]!, result };
          return next;
        });
      },
      8,
    );

    poolCancelRef.current = cancel;

    promise
      .then(() => {
        if (cancelledRef.current || runIdRef.current !== runId) return;
        setPhase('done');
        setProcessEndTime(Date.now());
        setShowModal(true);
      })
      .catch((err) => {
        if (cancelledRef.current || runIdRef.current !== runId) return;
        console.error('[batch] pool error:', err);
        setPhase('done');
        setProcessEndTime(Date.now());
      });
  }

  async function handleDiotDownload() {
    if (!files.length) return;

    // When analysis results are available, filter to the selected month/year
    const diotFiles = stats.completed > 0
      ? queue
          .filter((e) => e.result && e.result.status !== 'error' && e.result.fecha?.startsWith(diotMonthStr))
          .map((e) => e.file)
      : files;

    const filesToUse = diotFiles.length > 0 ? diotFiles : files;

    if (stats.completed > 0 && diotFiles.length === 0) {
      setDiotError(`No hay facturas de ${MESES[diotMonth - 1]!} ${diotYear} en el lote analizado.`);
      return;
    }

    if (filesToUse.length > 500) {
      const fileByResult = new Map<File, BatchFileResult | null>(queue.map((e) => [e.file, e.result]));
      const halves = splitByQuincena(filesToUse, (f) =>
        parseInt(fileByResult.get(f)?.fecha?.slice(8, 10) || '1', 10),
      );
      setDiotHalves(halves);
      setDiotError(`${filesToUse.length} facturas exceden el límite de 500. Descarga por quincenas:`);
      return;
    }
    setDiotHalves(null);

    setDiotLoading(true);
    setDiotError(null);
    setDiotSuccess(false);
    try {
      const blob = await batchDiot(filesToUse, { year: diotYear, month: diotMonth, rfc_presentante: diotRfc });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `DIOT_${diotRfc || 'PRESENTANTE'}_${diotYear}${String(diotMonth).padStart(2, '0')}.txt`;
      a.click();
      URL.revokeObjectURL(url);
      setDiotSuccess(true);
    } catch (err) {
      setDiotError(err instanceof Error ? err.message : String(err));
    } finally {
      setDiotLoading(false);
    }
  }

  async function handleDiotHalfDownload(halfFiles: File[], suffix: string) {
    setDiotLoading(true);
    setDiotError(null);
    setDiotSuccess(false);
    try {
      const blob = await batchDiot(halfFiles, { year: diotYear, month: diotMonth, rfc_presentante: diotRfc });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `DIOT_${diotRfc || 'PRESENTANTE'}_${diotYear}${String(diotMonth).padStart(2, '0')}_${suffix}.txt`;
      a.click();
      URL.revokeObjectURL(url);
      setDiotSuccess(true);
    } catch (err) {
      setDiotError(err instanceof Error ? err.message : String(err));
    } finally {
      setDiotLoading(false);
    }
  }

  async function handleDownloadSelected() {
    const filenames = Array.from(selectedRows).filter((n) => pdfStates.get(n) !== 'converting');
    if (!filenames.length) return;

    if (filenames.length === 1) {
      await handleDownloadPdf(filenames[0]!);
      return;
    }

    const sem = new Semaphore(2);
    const usedNames = new Set<string>();

    const entries = await Promise.all(
      filenames.map(async (filename: string) => {
        await sem.acquire();
        try {
          const file = fileByName.get(filename);
          if (!file) return null;
          setPdfStates((prev) => new Map(prev).set(filename, 'converting'));
          const buf = await convertFileToPdf(file);
          setPdfStates((prev) => new Map(prev).set(filename, 'done'));
          let pdfName = filename.replace(/\.xml$/i, '.pdf');
          if (usedNames.has(pdfName)) {
            const base = pdfName.replace(/\.pdf$/i, '');
            let i = 1;
            while (usedNames.has(`${base}_${i}.pdf`)) i++;
            pdfName = `${base}_${i}.pdf`;
          }
          usedNames.add(pdfName);
          return { name: pdfName, buf };
        } catch {
          setPdfStates((prev) => new Map(prev).set(filename, 'error'));
          return null;
        } finally {
          sem.release();
        }
      }),
    );

    const valid = entries.filter(Boolean) as { name: string; buf: ArrayBuffer }[];
    if (!valid.length) return;

    const { default: JSZip } = await import('jszip');
    const zip = new JSZip();
    for (const { name, buf } of valid) {
      zip.file(name, buf);
    }
    const blob = await zip.generateAsync({
      type: 'blob',
      compression: 'DEFLATE',
      compressionOptions: { level: 3 },
    });
    triggerBlobDownload(blob, `cfdi-pdfs-${new Date().toISOString().slice(0, 10)}.zip`);
  }

  function handleRetryFailed() {
    const failedEntries = queue
      .map((entry, idx) => ({ entry, idx }))
      .filter(({ entry }) => entry.result?.status === 'error');

    if (!failedEntries.length) return;

    const failedFiles = failedEntries.map(({ entry }) => entry.file);
    const failedIndices = failedEntries.map(({ idx }) => idx);

    setQueue((prev) => {
      const next = [...prev];
      failedIndices.forEach((i) => { next[i] = { ...next[i]!, result: null }; });
      return next;
    });

    cancelledRef.current = false;
    const runId = ++runIdRef.current;
    setPhase('processing');
    setShowModal(false);

    const { promise, cancel } = batchAnalyzePool(
      failedFiles,
      (result, localIndex) => {
        const globalIndex = failedIndices[localIndex]!;
        completionTimestampsRef.current.set(globalIndex, Date.now());
        setQueue((prev) => {
          const next = [...prev];
          if (next[globalIndex]) next[globalIndex] = { ...next[globalIndex]!, result };
          return next;
        });
      },
      8,
    );

    poolCancelRef.current = cancel;

    promise
      .then(() => {
        if (cancelledRef.current || runIdRef.current !== runId) return;
        setPhase('done');
        setProcessEndTime(Date.now());
      })
      .catch((err) => {
        if (cancelledRef.current || runIdRef.current !== runId) return;
        console.error('[batch] retry error:', err);
        setPhase('done');
        setProcessEndTime(Date.now());
      });
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col md:h-full md:overflow-hidden">

      {/* Wrapped modal */}
      {showModal && (
        <BatchCompletionModal
          totalFiles={files.length}
          ok={stats.ok}
          conErrores={stats.conErrores}
          errors={stats.errors}
          totalMonto={stats.totalMonto}
          elapsedSeconds={elapsedSeconds}
          topEmisor={stats.topEmisores[0] ?? null}
          topMonth={stats.topMonth}
          monthBreakdown={monthBreakdown}
          onViewTriage={() => setFilterStatus(stats.conErrores > 0 ? 'con_errores' : 'error')}
          onClose={() => setShowModal(false)}
        />
      )}

      <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">

        {/* ═══════ PHASE: IDLE ═══════ */}
        {phase === 'idle' && (
          <>
            {/* Drop zone */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
              className={clsx(
                'flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 transition-colors duration-200',
                files.length
                  ? 'border-primary-300 bg-primary-50/40'
                  : 'border-gray-300 bg-gray-50 hover:border-primary-300 hover:bg-primary-50/20',
              )}
            >
              <Upload size={28} className="text-gray-400" />
              <div className="text-center">
                <p className="text-sm font-medium text-gray-700">
                  Arrastra XMLs o carpetas aquí, o selecciona:
                </p>
                <div className="mt-2 flex justify-center gap-2">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:border-primary-300 hover:bg-primary-50 hover:text-primary-700"
                  >
                    <Upload size={12} />
                    Archivos
                  </button>
                  <button
                    onClick={() => folderInputRef.current?.click()}
                    className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:border-primary-300 hover:bg-primary-50 hover:text-primary-700"
                  >
                    <FolderOpen size={12} />
                    Carpeta
                  </button>
                </div>
                <p className="mt-2 text-xs text-gray-400">
                  Solo .xml · Cualquier cantidad — se procesa por lotes
                </p>
              </div>
              {files.length > 0 && (
                <p className="text-xs font-semibold text-primary-600">
                  {files.length.toLocaleString('es-MX')} {files.length === 1 ? 'archivo seleccionado' : 'archivos seleccionados'}
                </p>
              )}

              <input ref={fileInputRef} type="file" multiple accept=".xml" className="hidden" onChange={handleFileSelect} />
              <input ref={folderInputRef} type="file" multiple accept=".xml" className="hidden" onChange={handleFileSelect} />
            </div>

            {/* Pre-flight card */}
            <PreflightCard preflight={preflight} loading={preflightLoading} />

            {/* Actions */}
            {files.length > 0 && (
              <div className="flex items-center gap-3">
                <button
                  onClick={handleProcess}
                  className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-primary-700"
                >
                  <Zap size={13} />
                  Procesar {files.length.toLocaleString('es-MX')} facturas
                </button>
                <button
                  onClick={clearAll}
                  className="rounded-lg border border-gray-200 px-4 py-2 text-xs font-medium text-gray-600 transition-colors hover:border-gray-300 hover:bg-gray-50"
                >
                  Limpiar
                </button>
              </div>
            )}
          </>
        )}

        {/* ═══════ PHASE: PROCESSING ═══════ */}
        {phase === 'processing' && (
          <>
            {/* Pipeline indicator */}
            <BatchPipelineIndicator
              stage="processing"
              completed={stats.completed}
              total={files.length}
              errors={stats.errors}
            />

            {/* Stats cards */}
            <div className="flex gap-3">
              <StatsCard
                label="Velocidad"
                value={stats.filesPerSecond >= 1 ? `${stats.filesPerSecond.toFixed(1)} /seg` : '…'}
                sub="facturas por segundo"
              />
              {stats.totalMonto > 0 && (
                <StatsCard
                  label="Total acumulado"
                  value={formatMonto(stats.totalMonto)}
                  sub="en comprobantes procesados"
                />
              )}
              {stats.filesPerSecond > 0 && stats.completed < files.length && (
                <StatsCard
                  label="Tiempo restante"
                  value={`~${formatRemainingTime(stats.estimatedRemainingSeconds)}`}
                  sub={`${stats.completed.toLocaleString('es-MX')} de ${files.length.toLocaleString('es-MX')} listas`}
                />
              )}
            </div>

            {/* Live insights */}
            {(stats.topEmisores.length > 0 || stats.topMonth) && (
              <div className="flex flex-wrap gap-2">
                {stats.topEmisores[0] && (
                  <InsightCard
                    icon="🏆"
                    label="Emisor más frecuente (hasta ahora)"
                    value={stats.topEmisores[0].nombre}
                    sub={`${stats.topEmisores[0].count} facturas · ${stats.topEmisores[0].rfc}`}
                  />
                )}
                {stats.topMonth && (
                  <InsightCard
                    icon="📅"
                    label="Mes más activo"
                    value={formatTopMonth(stats.topMonth.month)}
                    sub={`${stats.topMonth.count} facturas`}
                  />
                )}
              </div>
            )}

            {/* Status counters during processing */}
            <div className="flex gap-2">
              {stats.ok > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-1 text-tiny font-medium text-green-700">
                  <CheckCircle2 size={10} /> {stats.ok.toLocaleString('es-MX')} ok
                </span>
              )}
              {stats.conErrores > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-yellow-50 px-2.5 py-1 text-tiny font-medium text-yellow-700">
                  <AlertCircle size={10} /> {stats.conErrores.toLocaleString('es-MX')} hallazgos
                </span>
              )}
              {stats.errors > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-tiny font-medium text-red-700">
                  <XCircle size={10} /> {stats.errors.toLocaleString('es-MX')} errores
                </span>
              )}
            </div>

            {/* Live file-by-file table */}
            {queue.length > 0 && <LiveQueueTable queue={queue} flashSet={flashSet} />}

            {/* Cancel button */}
            <div>
              <button
                onClick={clearAll}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-500 transition-colors hover:border-gray-300 hover:bg-gray-50"
              >
                Cancelar
              </button>
            </div>
          </>
        )}

        {/* ═══════ PHASE: DONE ═══════ */}
        {phase === 'done' && (
          <>
            {/* Pipeline — done state */}
            <BatchPipelineIndicator
              stage="done"
              completed={stats.completed}
              total={files.length}
              errors={stats.errors}
            />

            {/* Tab selector: Resultados / Reporte DIOT */}
            {(stats.ok + stats.conErrores) > 0 && (
              <div className="flex items-center gap-1 self-start rounded-lg border border-gray-200 bg-gray-50 p-0.5">
                {(['resultados', 'diot'] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setDoneView(v)}
                    className={clsx(
                      'rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150',
                      doneView === v
                        ? 'bg-white text-gray-800 shadow-sm'
                        : 'text-gray-500 hover:text-gray-700',
                    )}
                  >
                    {v === 'resultados' ? 'Resultados' : 'Reporte DIOT'}
                  </button>
                ))}
              </div>
            )}

            {/* Triage header — solo en tab Resultados */}
            {doneView === 'resultados' && (
              <TriageHeader stats={stats} filterStatus={filterStatus} onFilter={setFilterStatus} />
            )}

            {/* Selection toolbar — solo en tab Resultados cuando hay selección */}
            {doneView === 'resultados' && selectedRows.size > 0 && (
              <div className="flex items-center gap-3 rounded-lg border border-primary-200 bg-primary-50 px-3 py-2">
                <span className="text-xs font-medium text-primary-700">
                  {selectedRows.size} {selectedRows.size === 1 ? 'seleccionado' : 'seleccionados'}
                </span>
                <button
                  onClick={handleDownloadSelected}
                  disabled={someAreConverting}
                  className="flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {someAreConverting
                    ? <Loader2 size={11} className="animate-spin" />
                    : <Download size={11} />}
                  {someAreConverting
                    ? 'Convirtiendo…'
                    : selectedRows.size === 1
                      ? 'Descargar PDF'
                      : `Descargar ZIP (${selectedRows.size})`}
                </button>
                <button
                  onClick={() => setSelectedRows(new Set())}
                  className="text-xs text-primary-500 hover:text-primary-700"
                >
                  Deseleccionar
                </button>
              </div>
            )}

            {/* Results table — solo en tab Resultados */}
            {doneView === 'resultados' && (filteredResults.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                <div ref={doneTableRef} className="max-h-[560px] overflow-auto">
                  {(() => {
                    const doneVItems = doneVirtualizer.getVirtualItems();
                    const doneTotalSize = doneVirtualizer.getTotalSize();
                    const donePaddingTop = doneVItems[0]?.start ?? 0;
                    const donePaddingBottom = doneVItems.length > 0 ? doneTotalSize - (doneVItems[doneVItems.length - 1]!.end) : 0;
                    return (
                      <table className="w-full text-left">
                        <thead className="border-b border-gray-200 bg-gray-50">
                          {table.getHeaderGroups().map((hg) => (
                            <tr key={hg.id}>
                              {hg.headers.map((header) => (
                                <th
                                  key={header.id}
                                  onClick={header.column.getToggleSortingHandler()}
                                  className={clsx(
                                    'whitespace-nowrap px-3 py-2.5 text-tiny font-semibold uppercase tracking-wider text-gray-500',
                                    header.column.getCanSort() && 'cursor-pointer select-none hover:text-gray-700',
                                  )}
                                >
                                  {flexRender(header.column.columnDef.header, header.getContext())}
                                  {header.column.getIsSorted() === 'asc' && ' ↑'}
                                  {header.column.getIsSorted() === 'desc' && ' ↓'}
                                </th>
                              ))}
                            </tr>
                          ))}
                        </thead>
                        <tbody>
                          {donePaddingTop > 0 && <tr><td colSpan={table.getAllLeafColumns().length} style={{ height: `${donePaddingTop}px`, padding: 0 }} /></tr>}
                          {doneVItems.map((vRow) => {
                            const row = doneRows[vRow.index]!;
                            const isClickable = !!onSelectFile && row.original.status !== 'error';
                            return (
                              <tr
                                key={row.id}
                                onClick={isClickable
                                  ? () => {
                                      const file = fileByName.get(row.original.filename);
                                      if (!file) return;
                                      onSelectFile?.(file);
                                      if (onBatchNav) {
                                        const clickableRows = doneRows.filter((r) => r.original.status !== 'error');
                                        const clickIndex = clickableRows.findIndex((r) => r.id === row.id);
                                        const clickableFiles = clickableRows
                                          .map((r) => fileByName.get(r.original.filename))
                                          .filter(Boolean) as File[];
                                        if (clickIndex >= 0) onBatchNav(clickableFiles, clickIndex);
                                      }
                                    }
                                  : undefined}
                                className={clsx(
                                  'border-b border-gray-100 transition-colors duration-100 last:border-0',
                                  vRow.index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50',
                                  isClickable
                                    ? 'cursor-pointer hover:bg-primary-50/60 group'
                                    : 'hover:bg-primary-50/30',
                                )}
                                style={{ height: 36 }}
                              >
                                {row.getVisibleCells().map((cell) => (
                                  <td key={cell.id} className="px-3 py-2">
                                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                  </td>
                                ))}
                              </tr>
                            );
                          })}
                          {donePaddingBottom > 0 && <tr><td colSpan={table.getAllLeafColumns().length} style={{ height: `${donePaddingBottom}px`, padding: 0 }} /></tr>}
                        </tbody>
                      </table>
                    );
                  })()}
                </div>
                <div className="border-t border-gray-100 px-3 py-2 flex items-center justify-between text-tiny text-gray-400">
                  <span>
                    {filteredResults.length.toLocaleString('es-MX')} {filteredResults.length === 1 ? 'archivo' : 'archivos'}
                    {filterStatus !== 'all' && (
                      <span className="ml-2 text-primary-500">
                        (filtrado — <button onClick={() => setFilterStatus('all')} className="underline hover:text-primary-700">ver todas</button>)
                      </span>
                    )}
                  </span>
                  <button
                    onClick={() => exportResultsCsv(filteredResults, `cfdi-batch-${new Date().toISOString().slice(0, 10)}.csv`)}
                    className="flex items-center gap-1 text-gray-400 transition-colors hover:text-gray-700"
                    title="Descargar resultados como CSV"
                  >
                    <Download size={11} />
                    CSV
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 py-10 text-gray-400">
                <Filter size={24} />
                <p className="text-sm">Ningún archivo coincide con el filtro activo</p>
                <button onClick={() => setFilterStatus('all')} className="text-xs text-primary-600 hover:underline">
                  Ver todas
                </button>
              </div>
            ))}

            {/* Reporte DIOT — solo en tab DIOT */}
            {doneView === 'diot' && <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">Reportes</p>
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-tiny font-medium text-gray-500">Mes</label>
                  <select
                    value={diotMonth}
                    onChange={(e) => { setDiotMonth(Number(e.target.value)); setDiotHalves(null); setDiotError(null); }}
                    className="rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs text-gray-700 outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-200"
                  >
                    {MESES.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
                  </select>
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-tiny font-medium text-gray-500">Año</label>
                  <input
                    type="number"
                    value={diotYear}
                    onChange={(e) => { setDiotYear(Number(e.target.value)); setDiotHalves(null); setDiotError(null); }}
                    min={2020}
                    max={2099}
                    className="w-20 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs text-gray-700 outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-200"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-tiny font-medium text-gray-500">RFC presentante</label>
                  <input
                    type="text"
                    value={diotRfc}
                    onChange={(e) => setDiotRfc(e.target.value.toUpperCase())}
                    placeholder="AUTO"
                    maxLength={13}
                    className="w-36 rounded-lg border border-gray-200 px-2.5 py-1.5 font-mono text-xs text-gray-700 outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-200"
                  />
                </div>
                <button
                  onClick={handleDiotDownload}
                  disabled={diotLoading}
                  className="flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {diotLoading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                  {diotLoading ? 'Generando…' : 'Descargar DIOT (.txt)'}
                </button>
                {diotSuccess && (
                  <span className="flex items-center gap-1 text-xs text-green-600">
                    <CheckCircle2 size={12} /> Descargado
                  </span>
                )}
              </div>
              {stats.completed > 0 && (
                <p className="mt-1.5 text-tiny text-gray-400">
                  {diotMonthCount > 0
                    ? `${diotMonthCount.toLocaleString('es-MX')} facturas de ${MESES[diotMonth - 1]!} ${diotYear} en el lote`
                    : `Sin facturas de ${MESES[diotMonth - 1]!} ${diotYear} en el lote analizado`}
                </p>
              )}
              {diotError && (
                <div className="mt-2">
                  <p className="text-xs text-red-600">{diotError}</p>
                  {diotHalves && (
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => handleDiotHalfDownload(diotHalves.first, 'Q1')}
                        disabled={diotLoading || diotHalves.first.length === 0}
                        className="flex items-center gap-1.5 rounded-lg border border-primary-200 bg-primary-50 px-3 py-1.5 text-xs font-medium text-primary-700 transition-colors hover:bg-primary-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {diotLoading ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
                        1ra quincena ({diotHalves.first.length})
                      </button>
                      <button
                        onClick={() => handleDiotHalfDownload(diotHalves.second, 'Q2')}
                        disabled={diotLoading || diotHalves.second.length === 0}
                        className="flex items-center gap-1.5 rounded-lg border border-primary-200 bg-primary-50 px-3 py-1.5 text-xs font-medium text-primary-700 transition-colors hover:bg-primary-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {diotLoading ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
                        2da quincena ({diotHalves.second.length})
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>}

            {/* Acciones post-análisis */}
            <div className="flex items-center gap-2 pb-2">
              {stats.errors > 0 && (
                <button
                  onClick={handleRetryFailed}
                  className="flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-700 transition-colors hover:border-amber-300 hover:bg-amber-100"
                >
                  <RotateCcw size={12} />
                  Reintentar fallidos ({stats.errors})
                </button>
              )}
              <button
                onClick={clearAll}
                className="rounded-lg border border-gray-200 px-4 py-2 text-xs font-medium text-gray-600 transition-colors hover:border-gray-300 hover:bg-gray-50"
              >
                Nueva carga
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
