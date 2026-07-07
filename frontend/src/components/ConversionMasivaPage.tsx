import clsx from 'clsx';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  Download,
  FileDown,
  FolderOpen,
  Loader2,
  Upload,
  XCircle,
} from 'lucide-react';
import {
  type PdfConversionState,
  convertFileToPdf,
  triggerBlobDownload,
  Semaphore,
} from '../lib/pdf-download';

// ── Types ──────────────────────────────────────────────────────────────────────

interface ConversionEntry {
  file: File;
  state: PdfConversionState;
  error?: string;
  buffer?: ArrayBuffer;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function dedupeFiles(all: File[]): File[] {
  const seen = new Set<string>();
  return all.filter((f) => {
    const key = `${f.name}-${f.size}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

const STATE_CONFIG: Record<PdfConversionState, { label: string; className: string }> = {
  idle: { label: 'Pendiente', className: 'bg-gray-100 text-gray-500' },
  converting: { label: 'Convirtiendo…', className: 'bg-primary-50 text-primary-600' },
  done: { label: 'Listo', className: 'bg-green-50 text-green-700' },
  error: { label: 'Error', className: 'bg-red-50 text-red-600' },
};

function StateChip({ state }: { state: PdfConversionState }) {
  const cfg = STATE_CONFIG[state];
  return (
    <span className={clsx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-tiny font-medium', cfg.className)}>
      {state === 'converting' && <Loader2 size={10} className="animate-spin" />}
      {state === 'done' && <CheckCircle2 size={10} />}
      {state === 'error' && <XCircle size={10} />}
      {cfg.label}
    </span>
  );
}

// ── Main component ──────────────────────────────────────────────────────────────

interface ConversionMasivaPageProps {
  templateId?: string;
}

export default function ConversionMasivaPage({ templateId }: ConversionMasivaPageProps) {
  const [entries, setEntries] = useState<ConversionEntry[]>([]);
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());
  const [phase, setPhase] = useState<'idle' | 'running' | 'done'>('idle');
  const [isDownloadingAll, setIsDownloadingAll] = useState(false);
  const [isDownloadingSelected, setIsDownloadingSelected] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const cancelledRef = useRef(false);

  // Set webkitdirectory on folder input (not a valid JSX attr in TS)
  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute('webkitdirectory', '');
      folderInputRef.current.setAttribute('directory', '');
    }
  }, []);

  // ── Derived ────────────────────────────────────────────────────────────────

  const done = entries.filter((e) => e.state === 'done').length;
  const errors = entries.filter((e) => e.state === 'error').length;
  const total = entries.length;
  const allDone = total > 0 && done + errors === total;

  const allSelected =
    entries.length > 0 && entries.every((e) => selectedRows.has(e.file.name));
  const someSelected = entries.some((e) => selectedRows.has(e.file.name));

  // ── Handlers ────────────────────────────────────────────────────────────────

  function addFiles(files: File[]) {
    const xmlFiles = files.filter((f) => f.name.endsWith('.xml'));
    if (!xmlFiles.length) return;
    setEntries((prev) =>
      dedupeFiles([...prev.map((e) => e.file), ...xmlFiles]).map((f) => {
        const existing = prev.find((e) => e.file === f);
        return existing ?? { file: f, state: 'idle' };
      }),
    );
  }

  function handleFileDrop(e: React.DragEvent) {
    e.preventDefault();
    addFiles(Array.from(e.dataTransfer.files));
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    addFiles(Array.from(e.target.files ?? []));
    e.target.value = '';
  }

  function clearAll() {
    cancelledRef.current = true;
    setEntries([]);
    setSelectedRows(new Set());
    setPhase('idle');
  }

  function toggleSelectAll(checked: boolean) {
    if (checked) setSelectedRows(new Set(entries.map((e) => e.file.name)));
    else setSelectedRows(new Set());
  }

    const startConversion = useCallback(async () => {
        if (!entries.length) return;
        cancelledRef.current = false;
        setPhase('running');

        const sem = new Semaphore(2);

        await Promise.all(
            entries.map(async (entry) => {
                if (cancelledRef.current) return;
                await sem.acquire();
                try {
                    if (cancelledRef.current) return;
                    setEntries((prev) =>
                        prev.map((e) => e.file === entry.file ? { ...e, state: 'converting' } : e),
                    );

                    // 1. Ejecutamos la conversión y guardamos el ArrayBuffer devuelto en 'buf'
                    const buf = await convertFileToPdf(entry.file, templateId);

                    // 2. Inyectamos explícitamente el 'buf' en la propiedad 'buffer' del estado
                    setEntries((prev) =>
                        prev.map((e) => e.file === entry.file ? { ...e, state: 'done', buffer: buf } : e),
                    );
                } catch (err) {
                    setEntries((prev) =>
                        prev.map((e) =>
                            e.file === entry.file
                            ? { ...e, state: 'error', error: err instanceof Error ? err.message : String(err) }
                            : e,
                        ),
                    );
                } finally {
                    sem.release();
                }
            }),
        );

        if (!cancelledRef.current) setPhase('done');
    }, [entries, templateId]);

    async function handleDownloadOne(entry: ConversionEntry) {
        if (entry.state === 'converting') return;

        // Si ya lo tenemos en memoria, lo descargamos instantáneamente
        if (entry.buffer) {
            triggerBlobDownload(
                new Blob([entry.buffer], { type: 'application/pdf' }), 
                entry.file.name.replace(/\.xml$/i, '.pdf')
            );
            return;
        }

        // Fallback: si no lo tiene, lo descarga de la API
        setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'converting', error: undefined } : e));
        try {
            const buf = await convertFileToPdf(entry.file, templateId);
            triggerBlobDownload(new Blob([buf], { type: 'application/pdf' }), entry.file.name.replace(/\.xml$/i, '.pdf'));
            setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'done', buffer: buf } : e));
        } catch (err) {
            setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'error', error: String(err) } : e));
        }
    }

    async function handleDownloadSelected() {
        const targets = entries.filter((e) => selectedRows.has(e.file.name) && e.state !== 'converting');
        if (!targets.length) return;

        if (targets.length === 1) {
            await handleDownloadOne(targets[0]!);
            return;
        }

        setIsDownloadingSelected(true); // Bloqueamos la UI
        try {
            const { default: JSZip } = await import('jszip');
            const zip = new JSZip();
            const sem = new Semaphore(2);
            const usedNames = new Set<string>();

            const results = await Promise.all(
                targets.map(async (entry) => {
                    let buf = entry.buffer;
                    // Si por alguna razón no tiene buffer, lo pide
                    if (!buf) {
                        await sem.acquire();
                        try {
                            buf = await convertFileToPdf(entry.file, templateId);
                            setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'done', buffer: buf } : e));
                        } catch {
                            return null;
                        } finally { sem.release(); }
                    }

                    let pdfName = entry.file.name.replace(/\.xml$/i, '.pdf');
                    if (usedNames.has(pdfName)) {
                        const base = pdfName.replace(/\.pdf$/i, '');
                        let i = 1;
                        while (usedNames.has(`${base}_${i}.pdf`)) i++;
                        pdfName = `${base}_${i}.pdf`;
                    }
                    usedNames.add(pdfName);
                    return { name: pdfName, buf };
                }),
            );

            for (const r of results) {
                if (r && r.buf) zip.file(r.name, r.buf);
            }

            const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 3 } });
            triggerBlobDownload(blob, `cfdi-pdfs-${new Date().toISOString().slice(0, 10)}.zip`);
        } finally {
            setIsDownloadingSelected(false); // Liberamos la UI
        }
    }

    async function handleDownloadAll() {
    // Tomamos todos los que dicen "done", sin importar si tienen el buffer o no
    const doneEntries = entries.filter((e) => e.state === 'done');
    if (!doneEntries.length) return;

    setIsDownloadingAll(true);
    try {
      const { default: JSZip } = await import('jszip');
      const zip = new JSZip();
      const sem = new Semaphore(2);

      await Promise.all(
        doneEntries.map(async (entry) => {
          let buf = entry.buffer;

          // Fallback: Si no se guardó el buffer, no lo ignora, lo pide a la API
          if (!buf) {
            await sem.acquire();
            try {
              buf = await convertFileToPdf(entry.file, templateId);
              setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'done', buffer: buf } : e));
            } catch (err) {
              return null;
            } finally {
              sem.release();
            }
          }

          // Metemos el archivo al empaquetador ZIP
          if (buf) {
            zip.file(entry.file.name.replace(/\.xml$/i, '.pdf'), buf);
          }
        })
      );

      const blob = await zip.generateAsync({
        type: 'blob',
        compression: 'DEFLATE',
        compressionOptions: { level: 3 },
      });
      triggerBlobDownload(blob, `cfdi-pdfs-${new Date().toISOString().slice(0, 10)}.zip`);
    } finally {
      setIsDownloadingAll(false);
    }
  }
  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col md:h-full md:overflow-hidden">
      <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">

        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Conversión masiva XML → PDF</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Carga tus XMLs ya corregidos y descárgalos como PDF.
              Motor canvas_pipeline — ~2 s por archivo.
            </p>
          </div>
          {entries.length > 0 && (
            <button
              onClick={clearAll}
              className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              Limpiar todo
            </button>
          )}
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleFileDrop}
          className={clsx(
            'flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-8 transition-colors duration-200',
            entries.length
              ? 'border-primary-300 bg-primary-50/40'
              : 'border-gray-300 bg-gray-50 hover:border-primary-300 hover:bg-primary-50/20',
          )}
        >
          <Upload size={24} className="text-gray-400" />
          <div className="text-center">
            <p className="text-sm font-medium text-gray-700">Arrastra XMLs o carpetas aquí, o selecciona:</p>
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
          </div>
          {entries.length > 0 && (
            <p className="text-xs font-semibold text-primary-600">
              {entries.length.toLocaleString('es-MX')} {entries.length === 1 ? 'archivo' : 'archivos'} cargados
            </p>
          )}
          <input ref={fileInputRef} type="file" multiple accept=".xml" className="hidden" onChange={handleFileSelect} />
          <input ref={folderInputRef} type="file" multiple accept=".xml" className="hidden" onChange={handleFileSelect} />
        </div>

        {/* Progress header */}
        {entries.length > 0 && phase !== 'idle' && (
          <div className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
            <div className="flex-1">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="font-medium text-gray-700">
                  {done.toLocaleString('es-MX')} / {total.toLocaleString('es-MX')} convertidos
                  {errors > 0 && (
                    <span className="ml-2 text-red-500">· {errors} errores</span>
                  )}
                </span>
                {phase === 'done' && (
                  <span className="flex items-center gap-1 text-green-600">
                    <CheckCircle2 size={12} /> Completado
                  </span>
                )}
                {phase === 'running' && (
                  <span className="flex items-center gap-1 text-primary-600">
                    <Loader2 size={12} className="animate-spin" /> En proceso…
                  </span>
                )}
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                <div
                  className="h-full rounded-full bg-primary-500 transition-all duration-300"
                  style={{ width: total > 0 ? `${((done + errors) / total) * 100}%` : '0%' }}
                />
              </div>
            </div>
            {allDone && done > 0 && (
              <button
                onClick={handleDownloadAll}
                disabled={isDownloadingAll}
                className="flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDownloadingAll ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                {isDownloadingAll ? 'Empaquetando ZIP...' : 'Descargar todos (ZIP)'}
              </button>
            )}
          </div>
        )}

        {/* Action buttons */}
        {entries.length > 0 && (
          <div className="flex items-center gap-3 flex-wrap">
            {phase === 'idle' && (
              <button
                onClick={startConversion}
                className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-primary-700"
              >
                <FileDown size={13} />
                Convertir {entries.length.toLocaleString('es-MX')} {entries.length === 1 ? 'archivo' : 'archivos'}
              </button>
            )}
            {someSelected && (
              <button
                onClick={handleDownloadSelected}
                disabled={isDownloadingSelected}
                className="flex items-center gap-1.5 rounded-lg border border-primary-200 bg-primary-50 px-3 py-2 text-xs font-semibold text-primary-700 transition-colors hover:bg-primary-100 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDownloadingSelected ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                {isDownloadingSelected
                   ? 'Empaquetando...'
                   : (selectedRows.size === 1 ? 'Descargar PDF' : `Descargar ZIP (${selectedRows.size})`)}
              </button>
            )}
          </div>
        )}

        {/* Table */}
        {entries.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="max-h-[560px] overflow-auto">
              <table className="w-full text-left">
                <thead className="border-b border-gray-200 bg-gray-50">
                  <tr>
                    <th className="px-3 py-2.5">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={(e) => toggleSelectAll(e.target.checked)}
                        className="h-3.5 w-3.5 cursor-pointer rounded border-gray-300 accent-primary-600"
                      />
                    </th>
                    <th className="px-3 py-2.5 text-tiny font-semibold uppercase tracking-wider text-gray-500">
                      Archivo
                    </th>
                    <th className="px-3 py-2.5 text-tiny font-semibold uppercase tracking-wider text-gray-500">
                      Tamaño
                    </th>
                    <th className="px-3 py-2.5 text-tiny font-semibold uppercase tracking-wider text-gray-500">
                      Estado
                    </th>
                    <th className="px-3 py-2.5" />
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry, i) => (
                    <tr
                      key={entry.file.name}
                      className={clsx(
                        'border-b border-gray-100 last:border-0',
                        i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50',
                      )}
                      style={{ height: 36 }}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selectedRows.has(entry.file.name)}
                          onChange={(e) => {
                            setSelectedRows((prev) => {
                              const next = new Set(prev);
                              e.target.checked
                                ? next.add(entry.file.name)
                                : next.delete(entry.file.name);
                              return next;
                            });
                          }}
                          className="h-3.5 w-3.5 cursor-pointer rounded border-gray-300 accent-primary-600"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className="block max-w-[280px] truncate font-mono text-xs text-gray-800"
                          title={entry.file.name}
                        >
                          {entry.file.name}
                        </span>
                        {entry.error && (
                          <span className="block truncate text-tiny text-red-500" title={entry.error}>
                            {entry.error}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-xs tabular-nums text-gray-400">
                          {formatBytes(entry.file.size)}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <StateChip state={entry.state} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        {entry.state === 'converting' ? (
                          <Loader2 size={12} className="animate-spin text-primary-400 inline" />
                        ) : entry.state === 'done' ? (
                          <button
                            onClick={() => handleDownloadOne(entry)}
                            title="Descargar PDF"
                            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-tiny font-medium text-green-600 transition-colors hover:bg-green-50"
                          >
                            <Download size={11} />
                            PDF
                          </button>
                        ) : (
                          <button
                            onClick={() => handleDownloadOne(entry)}
                            title={entry.state === 'error' ? 'Reintentar' : 'Descargar PDF'}
                            className={clsx(
                              'flex items-center gap-1 rounded px-1.5 py-0.5 text-tiny font-medium transition-colors',
                              entry.state === 'error'
                                ? 'text-red-400 hover:bg-red-50 hover:text-red-600'
                                : 'text-gray-400 hover:bg-primary-50 hover:text-primary-600',
                            )}
                          >
                            <FileDown size={11} />
                            {entry.state === 'error' ? 'Reintentar' : 'PDF'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-gray-100 px-3 py-2 text-tiny text-gray-400">
              {entries.length.toLocaleString('es-MX')} {entries.length === 1 ? 'archivo' : 'archivos'}
              {done > 0 && (
                <span className="ml-2 text-green-600">
                  · {done.toLocaleString('es-MX')} listos
                </span>
              )}
            </div>
          </div>
        )}

        {/* Empty state */}
        {entries.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-10 text-gray-400">
            <FileDown size={28} />
            <p className="text-sm">Carga tus XMLs para comenzar</p>
            <p className="text-xs">
              El motor canvas_pipeline convierte cada XML en ~2 s, 4 en paralelo.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
