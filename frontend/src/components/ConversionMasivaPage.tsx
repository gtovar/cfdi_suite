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
  FileArchive,
  BarChart3
} from 'lucide-react';
import {
  type PdfConversionState,
  type BatchProgressPayload,
  convertFileToPdf,
  triggerBlobDownload,
  startZipConversion,
  watchBatchProgress,
  getBatchDownloadUrl,
  fetchReadyFileIds,
  fetchPdfDownloadUrl,
  fetchZipEstimatedSize,
  downloadWithProgress,
  ZIP_PROGRESS_SIZE_LIMIT_BYTES,
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

interface ConversionMasivaPageProps {
  templateId?: string;
}

// Lote en curso guardado para sobrevivir un refresh — el trabajo del servidor
// sigue vivo aunque la UI se recargue. El tope de edad coincide con el
// overallTimeoutMs de waitForBatchJob (45 min): más viejo que eso ya no hay
// stream que retomar.
const ACTIVE_BATCH_KEY = 'cfdi-active-batch';
const ACTIVE_BATCH_MAX_AGE_MS = 45 * 60 * 1000;

export default function ConversionMasivaPage({ templateId }: ConversionMasivaPageProps) {
  // Estados para el flujo tradicional (XMLs sueltos)
  const [entries, setEntries] = useState<ConversionEntry[]>([]);
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());
  const [phase, setPhase] = useState<'idle' | 'running' | 'done'>('idle');
  const [isDownloadingAll, setIsDownloadingAll] = useState(false);
  const [isDownloadingSelected, setIsDownloadingSelected] = useState(false);

  // NUEVOS ESTADOS PARA EL FLUJO MASIVO (.ZIP)
  const [isZipMode, setIsZipMode] = useState(false);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchProgress, setBatchProgress] = useState<BatchProgressPayload | null>(null);
  const [batchConnState, setBatchConnState] = useState<{ state: 'connected' | 'reconnecting'; attempt: number } | null>(null);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [readyFileIds, setReadyFileIds] = useState<string[]>([]);

  // Progreso de descarga (0-100%) del ZIP consolidado y de PDFs individuales.
  // null = sin descarga en curso; percentage null = tamaño desconocido (no
  // debería pasar salvo fallback, en cuyo caso ni se llega a usar este estado).
  const [zipDownloadProgress, setZipDownloadProgress] = useState<{ loaded: number; total: number | null } | null>(null);
  const [fileDownloadProgress, setFileDownloadProgress] = useState<Record<string, { loaded: number; total: number | null }>>({});

  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const cancelledRef = useRef(false);
  const restoredBatchRef = useRef(false);

  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute('webkitdirectory', '');
      folderInputRef.current.setAttribute('directory', '');
    }
  }, []);

  const done = entries.filter((e) => e.state === 'done').length;
  const errors = entries.filter((e) => e.state === 'error').length;
  const total = entries.length;
  const allDone = total > 0 && done + errors === total;

  const allSelected = entries.length > 0 && entries.every((e) => selectedRows.has(e.file.name));
  const someSelected = entries.some((e) => selectedRows.has(e.file.name));

  // ── Handlers ────────────────────────────────────────────────────────────────

  function addFiles(files: File[]) {
    // Verificamos si el usuario subió un archivo comprimido .zip
    const zipped = files.find((f) => f.name.endsWith('.zip'));
    
    if (zipped) {
      clearAll();
      setIsZipMode(true);
      setZipFile(zipped);
      return;
    }

    // Flujo normal si son archivos XML sueltos
    const xmlFiles = files.filter((f) => f.name.endsWith('.xml'));
    if (!xmlFiles.length) return;
    setIsZipMode(false);
    setZipFile(null);
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
    setIsZipMode(false);
    setZipFile(null);
    setBatchId(null);
    setBatchProgress(null);
    setBatchConnState(null);
    setBatchError(null);
    setReadyFileIds([]);
    localStorage.removeItem(ACTIVE_BATCH_KEY);
  }

  function toggleSelectAll(checked: boolean) {
    if (checked) setSelectedRows(new Set(entries.map((e) => e.file.name)));
    else setSelectedRows(new Set());
  }

  // Escucha el progreso vía Pusher (snapshot inicial + eventos en vivo +
  // reconciliación cada 30s). No lanza: los cortes de conexión se reportan
  // en batchError para mostrarse inline, sin alert() bloqueante.
  //
  // Los IDs listos para descarga individual viajan dentro de cada tick
  // (progress.readyIds) en vez de pedirse aparte — antes esto disparaba un
  // GET /ready-files por tick (O(n) sobre todo el batch en Redis, ~371
  // llamadas en un lote de 2,000). Al terminar se reconcilia una vez con
  // fetchReadyFileIds por si algún tick con readyIds no llegó a publicarse.
  const listenToBatch = useCallback(async (id: string) => {
    setBatchError(null);
    setBatchConnState(null);
    try {
      await watchBatchProgress(
        id,
        (progress) => {
          setBatchProgress(progress);
          if (progress.readyIds?.length) {
            setReadyFileIds((prev) => {
              const seen = new Set(prev);
              const additions = progress.readyIds!.filter((jid) => !seen.has(jid));
              return additions.length ? [...prev, ...additions] : prev;
            });
          }
          if (progress.status === 'done') {
            fetchReadyFileIds(id).then(setReadyFileIds).catch(() => {});
          }
        },
        (state, attempt) => setBatchConnState({ state, attempt }),
      );
      setPhase('done');
      localStorage.removeItem(ACTIVE_BATCH_KEY);
    } catch (err) {
      setBatchError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  // Reconexión tras refresh: si quedó un lote en curso guardado, volver a
  // escuchar su progreso en vez de obligar a resubir el ZIP.
  useEffect(() => {
    if (restoredBatchRef.current) return;
    restoredBatchRef.current = true;
    const raw = localStorage.getItem(ACTIVE_BATCH_KEY);
    if (!raw) return;
    try {
      const saved = JSON.parse(raw) as { batchId: string; total: number; startedAt: number };
      if (!saved.batchId || Date.now() - saved.startedAt > ACTIVE_BATCH_MAX_AGE_MS) {
        localStorage.removeItem(ACTIVE_BATCH_KEY);
        return;
      }
      setIsZipMode(true);
      setPhase('running');
      setBatchId(saved.batchId);
      setBatchProgress({
        status: 'processing',
        total: saved.total,
        done: 0,
        error: 0,
        converting: 0,
        pending: saved.total,
        percentage: 0
      });
      // Hidratación única: cualquier archivo terminado antes de que el
      // listener de Pusher esté conectado no se pierde.
      fetchReadyFileIds(saved.batchId).then(setReadyFileIds).catch(() => {});
      void listenToBatch(saved.batchId);
    } catch {
      localStorage.removeItem(ACTIVE_BATCH_KEY);
    }
  }, [listenToBatch]);

  function handleRetryBatchConnection() {
    if (batchId) void listenToBatch(batchId);
  }

  const startConversion = useCallback(async () => {
    cancelledRef.current = false;
    setPhase('running');

    // --- EJECUCIÓN DEL MODO MASIVO (ZIP) ---
    if (isZipMode && zipFile) {
      try {
        const res = await startZipConversion(zipFile, templateId);
        setBatchId(res.batchId);
        localStorage.setItem(ACTIVE_BATCH_KEY, JSON.stringify({
          batchId: res.batchId,
          total: res.totalFiles,
          startedAt: Date.now()
        }));

        setBatchProgress({
          status: 'processing',
          total: res.totalFiles,
          done: 0,
          error: 0,
          converting: 0,
          pending: res.totalFiles,
          percentage: 0
        });

        await listenToBatch(res.batchId);
      } catch (err) {
        setPhase('idle');
        alert(err instanceof Error ? err.message : String(err));
      }
      return;
    }

    // --- EJECUCIÓN DEL MODO TRADICIONAL (XML SUELTOS DE 4 EN 4) ---
    if (!entries.length) return;
    const sem = new Semaphore(4);

    await Promise.all(
      entries.map(async (entry) => {
        if (cancelledRef.current) return;
        await sem.acquire();
        try {
          if (cancelledRef.current) return;
          setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'converting' } : e));
          const buf = await convertFileToPdf(entry.file, templateId);
          setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'done', buffer: buf } : e));
        } catch (err) {
          setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'error', error: err instanceof Error ? err.message : String(err) } : e));
        } finally {
          sem.release();
        }
      }),
    );

    if (!cancelledRef.current) setPhase('done');
  }, [entries, isZipMode, zipFile, templateId]);

  async function handleDownloadBatchZip() {
    if (!batchId) return;
    const downloadUrl = getBatchDownloadUrl(batchId);

    // El ZIP se arma al vuelo en el backend (streaming) y no tiene
    // Content-Length real, así que usamos la suma de tamaños originales de
    // los PDFs como estimado. Si es desconocido o el lote es muy grande,
    // fetch+ReadableStream retendría el archivo completo en memoria del
    // navegador antes de poder guardarlo — mejor la descarga nativa sin
    // barra de progreso que arriesgar tronar la pestaña.
    const estimate = await fetchZipEstimatedSize(batchId);
    const knownTotal = estimate?.knownCount ? estimate.estimatedBytes : null;
    if (knownTotal === null || knownTotal > ZIP_PROGRESS_SIZE_LIMIT_BYTES) {
      // window.open tras un await ya no cuenta como gesto del usuario y el
      // popup blocker lo cancela en silencio (mismo motivo que
      // handleDownloadReadyFile usa window.location.assign en vez de open).
      window.location.assign(downloadUrl);
      return;
    }

    setZipDownloadProgress({ loaded: 0, total: knownTotal });
    try {
      const blob = await downloadWithProgress(downloadUrl, knownTotal, (loaded, total) => {
        setZipDownloadProgress({ loaded, total });
      });
      triggerBlobDownload(blob, `resultado_pdfs_${batchId}.zip`);
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setZipDownloadProgress(null);
    }
  }

  async function handleDownloadReadyFile(jobId: string) {
    setFileDownloadProgress((prev) => ({ ...prev, [jobId]: { loaded: 0, total: null } }));
    try {
      const url = await fetchPdfDownloadUrl(jobId);
      const blob = await downloadWithProgress(url, null, (loaded, total) => {
        setFileDownloadProgress((prev) => ({ ...prev, [jobId]: { loaded, total } }));
      });
      triggerBlobDownload(blob, `cfdi_${jobId}.pdf`);
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setFileDownloadProgress((prev) => {
        const next = { ...prev };
        delete next[jobId];
        return next;
      });
    }
  }

  async function handleDownloadOne(entry: ConversionEntry) {
    if (entry.state === 'converting') return;
    if (entry.buffer) {
      triggerBlobDownload(new Blob([entry.buffer], { type: 'application/pdf' }), entry.file.name.replace(/\.xml$/i, '.pdf'));
      return;
    }
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
    if (targets.length === 1) { await handleDownloadOne(targets[0]!); return; }

    setIsDownloadingSelected(true);
    try {
      const { default: JSZip } = await import('jszip');
      const zip = new JSZip();
      const sem = new Semaphore(2);
      const usedNames = new Set<string>();

      const results = await Promise.all(
        targets.map(async (entry) => {
          let buf = entry.buffer;
          if (!buf) {
            await sem.acquire();
            try {
              buf = await convertFileToPdf(entry.file, templateId);
              setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'done', buffer: buf } : e));
            } catch { return null; } finally { sem.release(); }
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

      for (const r of results) { if (r && r.buf) zip.file(r.name, r.buf); }
      const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 3 } });
      triggerBlobDownload(blob, `cfdi-pdfs-${new Date().toISOString().slice(0, 10)}.zip`);
    } finally { setIsDownloadingSelected(false); }
  }

  async function handleDownloadAll() {
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
          if (!buf) {
            await sem.acquire();
            try {
              buf = await convertFileToPdf(entry.file, templateId);
              setEntries((prev) => prev.map((e) => e.file === entry.file ? { ...e, state: 'done', buffer: buf } : e));
            } catch { return null; } finally { sem.release(); }
          }
          if (buf) zip.file(entry.file.name.replace(/\.xml$/i, '.pdf'), buf);
        })
      );
      const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 3 } });
      triggerBlobDownload(blob, `cfdi-pdfs-${new Date().toISOString().slice(0, 10)}.zip`);
    } finally { setIsDownloadingAll(false); }
  }

  return (
    <div className="flex flex-col md:h-full md:overflow-hidden">
      <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">

        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Conversión masiva XML → PDF</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Soporta archivos sueltos (.xml) o paquetes masivos comprimidos (.zip).
            </p>
          </div>
          {(entries.length > 0 || zipFile) && (
            <button onClick={clearAll} className="text-xs text-gray-400 hover:text-gray-600 transition-colors">
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
            entries.length || zipFile ? 'border-primary-300 bg-primary-50/40' : 'border-gray-300 bg-gray-50 hover:border-primary-300 hover:bg-primary-50/20'
          )}
        >
          {isZipMode ? <FileArchive size={24} className="text-primary-500" /> : <Upload size={24} className="text-gray-400" />}
          <div className="text-center">
            <p className="text-sm font-medium text-gray-700">Arrastra tus XMLs o un archivo .ZIP aquí:</p>
            <div className="mt-2 flex justify-center gap-2">
              <button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50">
                <Upload size={12} /> Seleccionar archivos / .ZIP
              </button>
            </div>
          </div>
          {isZipMode && zipFile && (
            <p className="text-xs font-semibold text-primary-600">
              Paquete detectado: {zipFile.name} ({formatBytes(zipFile.size)})
            </p>
          )}
          {!isZipMode && entries.length > 0 && (
            <p className="text-xs font-semibold text-primary-600">
              {entries.length.toLocaleString('es-MX')} archivos XML listos
            </p>
          )}
          <input ref={fileInputRef} type="file" multiple accept=".xml,.zip" className="hidden" onChange={handleFileSelect} />
        </div>

      {/* --- INDICADOR DE CARGA INICIAL (FEEDBACK INMEDIATO AL USUARIO) --- */}
      {isZipMode && !batchProgress && phase === 'running' && (
          <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm flex flex-col items-center justify-center gap-4 transition-all animate-pulse">
          <Loader2 className="animate-spin text-primary-500" size={36} />
          <div>
          <p className="text-sm font-semibold text-gray-800">Desempaquetando y registrando lote en la nube...</p>
          <p className="mt-1 text-xs text-gray-400">
          Estamos creando la fila de tareas en Google Cloud de forma segura. Por favor, mantén esta pestaña abierta.
          </p>
          </div>
          </div>
      )}
      {/* --- INTERFAZ MONOLÍTICA HÍBRIDA OPCIÓN A (MODO ZIP ACTIVO) --- */}
      {isZipMode && batchProgress && (
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BarChart3 className="text-primary-500" size={18} />
                <h3 className="text-sm font-semibold text-gray-900">Estado del Procesamiento en la Nube</h3>
              </div>
              {batchProgress.status === 'processing' && (
                <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700">
                  <Loader2 size={12} className="animate-spin" /> Convirtiendo en ráfaga...
                </span>
              )}
              {batchProgress.status === 'done' && (
                <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700">
                  <CheckCircle2 size={12} /> Lote completado con éxito
                </span>
              )}
              {batchConnState?.state === 'reconnecting' && !batchError && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700">
                  <Loader2 size={12} className="animate-spin" /> Reconectando… (intento {batchConnState.attempt}/5)
                </span>
              )}
            </div>

            {/* Aviso de conexión perdida tras agotar reintentos: el lote sigue vivo en el
                servidor, solo se perdió la conexión de progreso. Se puede reintentar sin
                volver a subir el ZIP. */}
            {batchError && (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
                <p className="text-xs text-amber-800">
                  Se perdió la conexión de progreso en tiempo real, pero tu lote sigue procesándose en la nube. {batchError}
                </p>
                <button
                  onClick={handleRetryBatchConnection}
                  className="shrink-0 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
                >
                  Reintentar conexión
                </button>
              </div>
            )}

            {/* Barra de progreso unificada */}
            <div className="w-full">
              <div className="mb-2 flex items-center justify-between text-xs font-medium text-gray-600">
                <span>Progreso General</span>
                <span className="text-sm font-bold text-primary-600 tabular-nums">{batchProgress.percentage}%</span>
              </div>
              <div className="h-3 w-full overflow-hidden rounded-full bg-gray-100">
                <div 
                  className="h-full bg-primary-500 transition-all duration-300 rounded-full" 
                  style={{ width: `${batchProgress.percentage}%` }}
                />
              </div>
            </div>

            {/* Tablero de contadores en ráfaga */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
              <div className="rounded-lg bg-gray-50 p-3 text-center border border-gray-100">
                <p className="text-tiny font-medium text-gray-400 uppercase">Total XMLs</p>
                <p className="mt-1 text-lg font-bold text-gray-800 tabular-nums">{batchProgress.total}</p>
              </div>
              <div className="rounded-lg bg-green-50/50 p-3 text-center border border-green-100/50">
                <p className="text-tiny font-medium text-green-600 uppercase">Listos</p>
                <p className="mt-1 text-lg font-bold text-green-700 tabular-nums">{batchProgress.done}</p>
              </div>
              <div className="rounded-lg bg-blue-50/30 p-3 text-center border border-blue-100/30">
                <p className="text-tiny font-medium text-blue-500 uppercase">En Proceso</p>
                <p className="mt-1 text-lg font-bold text-blue-600 tabular-nums">{batchProgress.converting}</p>
              </div>
              <div className="rounded-lg bg-red-50/50 p-3 text-center border border-red-100/50">
                <p className="text-tiny font-medium text-red-500 uppercase">Errores</p>
                <p className="mt-1 text-lg font-bold text-red-600 tabular-nums">{batchProgress.error}</p>
              </div>
            </div>

            {/* Tabla progresiva: los PDFs ya listos se pueden bajar uno por uno
                sin esperar a que termine todo el lote */}
            {readyFileIds.length > 0 && (
              <div className="overflow-hidden rounded-xl border border-gray-200">
                <div className="flex items-center justify-between border-b border-gray-100 bg-gray-50 px-3 py-2">
                  <span className="text-tiny font-semibold uppercase tracking-wider text-gray-500">
                    PDFs listos para descargar ({readyFileIds.length})
                  </span>
                </div>
                <div className="max-h-64 overflow-auto">
                  {readyFileIds.map((jobId, i) => {
                    const dl = fileDownloadProgress[jobId];
                    const pct = dl?.total ? Math.min(99, Math.round((dl.loaded / dl.total) * 100)) : null;
                    return (
                      <div
                        key={jobId}
                        className={clsx(
                          'flex items-center justify-between gap-3 px-3 py-1.5 text-xs',
                          i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                        )}
                      >
                        <span className="truncate font-mono text-gray-600">Factura {i + 1}</span>
                        <button
                          onClick={() => handleDownloadReadyFile(jobId)}
                          disabled={!!dl}
                          className="flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-tiny font-medium text-green-600 hover:bg-green-50 disabled:opacity-60"
                        >
                          {dl ? (
                            <>
                              <Loader2 size={11} className="animate-spin" />
                              {pct !== null ? `${pct}%` : formatBytes(dl.loaded)}
                            </>
                          ) : (
                            <>
                              <Download size={11} /> PDF
                            </>
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Botón único de descarga consolidada, o su barra de progreso
                mientras fetch + ReadableStream trae el ZIP */}
            {batchProgress.status === 'done' && (
              zipDownloadProgress ? (
                <div className="mt-2 w-full rounded-xl border border-green-200 bg-green-50 px-4 py-3">
                  <div className="mb-2 flex items-center justify-between text-xs font-medium text-green-800">
                    <span className="flex items-center gap-1.5">
                      <Loader2 size={13} className="animate-spin" /> Descargando ZIP…
                    </span>
                    <span className="tabular-nums">
                      {zipDownloadProgress.total
                        ? `${Math.min(99, Math.round((zipDownloadProgress.loaded / zipDownloadProgress.total) * 100))}%`
                        : formatBytes(zipDownloadProgress.loaded)}
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-green-100">
                    <div
                      className="h-full bg-green-600 transition-all duration-300 rounded-full"
                      style={{
                        width: zipDownloadProgress.total
                          ? `${Math.min(99, Math.round((zipDownloadProgress.loaded / zipDownloadProgress.total) * 100))}%`
                          : '100%',
                      }}
                    />
                  </div>
                </div>
              ) : (
                <button
                  onClick={handleDownloadBatchZip}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-green-600 py-3 text-sm font-semibold text-white transition-colors hover:bg-green-700 shadow-sm"
                >
                  <Download size={16} /> Descargar paquete de PDFs final (.ZIP)
                </button>
              )
            )}
          </div>
        )}

        {/* --- INTERFAZ TRADICIONAL OPCIÓN B (MODO XML SUELTO ACTIVO) --- */}
        {!isZipMode && entries.length > 0 && phase !== 'idle' && (
          <div className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
            <div className="flex-1">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="font-medium text-gray-700">
                  {done.toLocaleString('es-MX')} / {total.toLocaleString('es-MX')} convertidos
                  {errors > 0 && <span className="ml-2 text-red-500">· {errors} errores</span>}
                </span>
                {phase === 'done' && <span className="flex items-center gap-1 text-green-600"><CheckCircle2 size={12} /> Completado</span>}
                {phase === 'running' && <span className="flex items-center gap-1 text-primary-600"><Loader2 size={12} className="animate-spin" /> Procesando de 4 en 4...</span>}
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                <div className="h-full rounded-full bg-primary-500 transition-all duration-300" style={{ width: total > 0 ? `${((done + errors) / total) * 100}%` : '0%' }} />
              </div>
            </div>
            {allDone && done > 0 && (
              <button onClick={handleDownloadAll} disabled={isDownloadingAll} className="flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-primary-700 disabled:opacity-50">
                {isDownloadingAll ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                {isDownloadingAll ? 'Empaquetando...' : 'Descargar todos (ZIP)'}
              </button>
            )}
          </div>
        )}

        {/* Botones de acción */}
        {phase === 'idle' && (entries.length > 0 || zipFile) && (
          <div className="flex items-center gap-3">
            <button
              onClick={startConversion}
              className="flex items-center gap-2 rounded-lg bg-primary-600 px-5 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-primary-700 shadow-sm"
            >
              <FileDown size={14} />
              Iniciar conversión masiva en paralelo
            </button>
          </div>
        )}

        {/* Tabla tradicional (Solo visible para XMLs sueltos) */}
        {!isZipMode && entries.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="max-h-[560px] overflow-auto">
              <table className="w-full text-left">
                <thead className="border-b border-gray-200 bg-gray-50">
                  <tr>
                    <th className="px-3 py-2.5"><input type="checkbox" checked={allSelected} onChange={(e) => toggleSelectAll(e.target.checked)} className="h-3.5 w-3.5 cursor-pointer rounded border-gray-300 accent-primary-600" /></th>
                    <th className="px-3 py-2.5 text-tiny font-semibold uppercase tracking-wider text-gray-500">Archivo</th>
                    <th className="px-3 py-2.5 text-tiny font-semibold uppercase tracking-wider text-gray-500">Tamaño</th>
                    <th className="px-3 py-2.5 text-tiny font-semibold uppercase tracking-wider text-gray-500">Estado</th>
                    <th className="px-3 py-2.5" />
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry, i) => (
                    <tr key={entry.file.name} className={clsx('border-b border-gray-100 last:border-0', i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50')} style={{ height: 36 }}>
                      <td className="px-3 py-2">
                        <input type="checkbox" checked={selectedRows.has(entry.file.name)} onChange={(e) => { setSelectedRows((prev) => { const next = new Set(prev); e.target.checked ? next.add(entry.file.name) : next.delete(entry.file.name); return next; }); }} className="h-3.5 w-3.5 cursor-pointer rounded border-gray-300 accent-primary-600" />
                      </td>
                      <td className="px-3 py-2">
                        <span className="block max-w-[280px] truncate font-mono text-xs text-gray-800" title={entry.file.name}>{entry.file.name}</span>
                        {entry.error && <span className="block truncate text-tiny text-red-500" title={entry.error}>{entry.error}</span>}
                      </td>
                      <td className="px-3 py-2"><span className="text-xs tabular-nums text-gray-400">{formatBytes(entry.file.size)}</span></td>
                      <td className="px-3 py-2"><StateChip state={entry.state} /></td>
                      <td className="px-3 py-2 text-right">
                        {entry.state === 'converting' ? (
                          <Loader2 size={12} className="animate-spin text-primary-400 inline" />
                        ) : entry.state === 'done' ? (
                          <button onClick={() => handleDownloadOne(entry)} className="flex items-center gap-1 rounded px-1.5 py-0.5 text-tiny font-medium text-green-600 hover:bg-green-50"><Download size={11} /> PDF</button>
                        ) : (
                          <button onClick={() => handleDownloadOne(entry)} className={clsx('flex items-center gap-1 rounded px-1.5 py-0.5 text-tiny font-medium transition-colors', entry.state === 'error' ? 'text-red-400 hover:bg-red-50' : 'text-gray-400 hover:bg-primary-50')}><FileDown size={11} /> {entry.state === 'error' ? 'Reintentar' : 'PDF'}</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Empty state */}
        {entries.length === 0 && !zipFile && (
          <div className="flex flex-col items-center gap-2 py-10 text-gray-400">
            <FileDown size={28} />
            <p className="text-sm">Carga tus XMLs o un archivo .ZIP para comenzar</p>
          </div>
        )}
      </div>
    </div>
  );
}
