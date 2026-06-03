import clsx from 'clsx';
import React, { useRef, useState } from 'react';
import { Download, FileSpreadsheet, Loader2, Upload } from 'lucide-react';
import {
  downloadBatchResult,
  enquiryBatch,
  type BatchProgressEvent,
} from '../lib/sat-enquiry-api-client';

type Phase = 'idle' | 'processing' | 'done' | 'error';

const FORMAT_COLUMNS = [
  ['UUID', 'Sí', 'UUID del CFDI (folio fiscal)'],
  ['RFC emisor', 'Sí', 'RFC del emisor (debe estar configurado)'],
  ['RFC receptor', 'Sí', 'RFC del receptor'],
  ['TotalCFDI', 'Sí', 'Total del comprobante'],
  ['Motive', 'Sí', 'Motivo de cancelación: 01–04'],
];

export default function ConsultasSATPage() {
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [processed, setProcessed] = useState(0);
  const [total, setTotal] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  function handleFileDrop(e: React.DragEvent) {
    e.preventDefault();
    const dropped = e.dataTransfer.files[0];
    if (dropped?.name.endsWith('.xlsx')) setFile(dropped);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  }

  async function handleStart() {
    if (!file) return;
    setPhase('processing');
    setProcessed(0);
    setTotal(0);
    setJobId(null);
    setError(null);

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      await enquiryBatch(
        file,
        (event: BatchProgressEvent) => {
          if (event.type === 'progress') {
            setProcessed(event.processed);
            setTotal(event.total);
          } else if (event.type === 'done') {
            setJobId(event.job_id);
            setTotal(event.total);
            setPhase('done');
          }
        },
        abort.signal,
      );
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError(err instanceof Error ? err.message : 'Error desconocido');
        setPhase('error');
      }
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
    setPhase('idle');
  }

  async function handleDownload() {
    if (!jobId) return;
    try {
      await downloadBatchResult(jobId);
      setJobId(null);
      setFile(null);
      setPhase('idle');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error descargando resultado');
    }
  }

  function handleReset() {
    setFile(null);
    setPhase('idle');
    setError(null);
    setJobId(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-auto bg-gray-50">
      <div className="mx-auto w-full max-w-2xl px-6 py-8">
        {/* Page heading */}
        <div className="mb-8">
          <h2 className="text-base font-semibold text-gray-900">Consultas SAT</h2>
          <p className="mt-1 text-sm text-gray-500">
            Verifica el estado de tus CFDIs ante el SAT: si están vigentes o si ya fueron cancelados.
          </p>
          <p className="mt-2 text-xs text-gray-400">
            Sube un archivo Excel con tu lista de facturas y obtén el estado de cada una en un solo paso.
          </p>
        </div>

        {/* Prerequisites notice */}
        <div className="mb-5 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-xs text-blue-700 space-y-1">
          <p className="font-medium">¿Qué necesitas para usar esto?</p>
          <p>
            Credenciales Diverza configuradas para cada RFC emisor de las facturas que quieras consultar.
            Si no eres el emisor y no tienes cuenta Diverza, esas facturas mostrarán error.
          </p>
          <p>
            Configura en <span className="font-medium">Emisores</span> (menú izquierdo → Configuración).
          </p>
        </div>

        {/* Upload card */}
        <div className="rounded-lg border border-gray-200 bg-white shadow-soft">
          <div className="border-b border-gray-200 px-5 py-4">
            <h3 className="text-sm font-medium text-gray-800">Batch — Excel</h3>
          </div>
          <div className="p-5 space-y-4">
            {/* Drop zone */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
              onClick={() => fileInputRef.current?.click()}
              className={clsx(
                'cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors duration-200',
                file
                  ? 'border-primary-300 bg-primary-50'
                  : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50',
              )}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx"
                onChange={handleFileSelect}
                className="hidden"
              />
              {file ? (
                <div className="flex items-center justify-center gap-2.5">
                  <FileSpreadsheet size={18} className="text-primary-600 shrink-0" />
                  <span className="text-sm font-medium text-primary-700">{file.name}</span>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex justify-center">
                    <Upload size={20} className="text-gray-400" />
                  </div>
                  <p className="text-sm text-gray-600">Arrastra un .xlsx o haz clic para seleccionar</p>
                  <p className="text-tiny text-gray-400 uppercase tracking-wider">
                    Columnas: UUID · RFC emisor · RFC receptor · TotalCFDI · Motive
                  </p>
                </div>
              )}
            </div>

            {/* Progress */}
            {phase === 'processing' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>{processed} / {total} CFDIs</span>
                  <span>{pct}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-gray-200">
                  <div
                    className="h-full rounded-full bg-primary-600 transition-all duration-200"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            )}

            {/* Done */}
            {phase === 'done' && (
              <div className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
                <span className="text-sm text-emerald-700 font-medium">{total} CFDIs consultados</span>
                <button
                  onClick={handleDownload}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors duration-200 hover:bg-emerald-700"
                >
                  <Download size={13} />
                  Descargar Excel
                </button>
              </div>
            )}

            {/* Error */}
            {(phase === 'error' || error) && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2.5">
              {(phase === 'idle' || phase === 'error') && (
                <button
                  onClick={handleStart}
                  disabled={!file}
                  className={clsx(
                    'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium text-white transition-colors duration-200',
                    'bg-primary-600 hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-40',
                  )}
                >
                  Iniciar consulta
                </button>
              )}
              {phase === 'processing' && (
                <button
                  onClick={handleCancel}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2 text-xs font-medium text-gray-700 transition-colors duration-200 hover:bg-gray-100"
                >
                  <Loader2 size={13} className="animate-spin" />
                  Cancelar
                </button>
              )}
              {file && phase !== 'processing' && (
                <button
                  onClick={handleReset}
                  className="text-xs text-gray-500 transition-colors duration-200 hover:text-gray-700"
                >
                  Limpiar
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Format reference card */}
        <div className="mt-5 rounded-lg border border-gray-200 bg-white shadow-soft">
          <div className="border-b border-gray-200 px-5 py-3">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
              Formato de entrada
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 text-left">
                  {['Columna', 'Requerida', 'Descripción'].map((h) => (
                    <th key={h} className="px-5 py-2.5 text-tiny font-medium uppercase tracking-wider text-gray-500">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {FORMAT_COLUMNS.map(([col, req, desc]) => (
                  <tr key={col} className="hover:bg-gray-50 transition-colors duration-150">
                    <td className="px-5 py-2.5 text-xs font-medium text-gray-800">{col}</td>
                    <td className="px-5 py-2.5 text-xs text-gray-600">{req}</td>
                    <td className="px-5 py-2.5 text-xs text-gray-600">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-gray-100 px-5 py-3">
            <p className="text-tiny text-gray-400">
              El resultado incluye: estado · es_cancelable · estatus_cancelacion · error (si aplica)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
