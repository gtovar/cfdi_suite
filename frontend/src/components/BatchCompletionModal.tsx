import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Clock, TrendingUp, Zap } from 'lucide-react';
import { formatMonto, formatTopMonth } from '../lib/useBatchStats';

interface BatchCompletionModalProps {
  totalFiles: number;
  ok: number;
  conErrores: number;
  errors: number;
  totalMonto: number;
  elapsedSeconds: number;
  topEmisor: { nombre: string; count: number } | null;
  topMonth: { month: string; count: number } | null;
  onViewTriage: () => void;
  onClose: () => void;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} segundos`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${mins}m ${secs}s` : `${mins} minutos`;
}

function estimateSavedHours(fileCount: number): string {
  const hours = Math.round((fileCount * 2) / 60);
  if (hours < 1) return `${fileCount * 2} minutos`;
  return `${hours} hora${hours !== 1 ? 's' : ''}`;
}

function useCountUp(target: number, duration = 1200): number {
  const [value, setValue] = useState(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (target === 0) { setValue(0); return; }
    let start: number | null = null;
    const step = (ts: number) => {
      if (start === null) start = ts;
      const progress = Math.min((ts - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(target * eased));
      if (progress < 1) rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => { if (rafRef.current !== null) cancelAnimationFrame(rafRef.current); };
  }, [target, duration]);

  return value;
}

export default function BatchCompletionModal({
  totalFiles,
  ok,
  conErrores,
  errors,
  totalMonto,
  elapsedSeconds,
  topEmisor,
  topMonth,
  onViewTriage,
  onClose,
}: BatchCompletionModalProps) {
  const [visible, setVisible] = useState(false);
  const animatedFiles = useCountUp(totalFiles, 900);
  const animatedMonto = useCountUp(totalMonto, 1400);

  useEffect(() => {
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, []);

  function handleViewTriage() {
    onViewTriage();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]">
      <div
        className={`modal-fade-in w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl transition-opacity duration-200 ${visible ? 'opacity-100' : 'opacity-0'}`}
      >
        {/* Header */}
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-green-100">
            <CheckCircle2 size={20} className="text-green-600" />
          </div>
          <div>
            <p className="text-sm font-bold text-gray-900">¡Lote completado!</p>
            <p className="text-xs text-gray-400">
              <span className="font-semibold tabular-nums text-gray-700">
                {animatedFiles.toLocaleString('es-MX')}
              </span>{' '}
              facturas procesadas
            </p>
          </div>
        </div>

        <div className="mb-4 space-y-2 rounded-xl border border-gray-100 bg-gray-50 p-3">
          <div className="metric-reveal flex items-center gap-2 text-xs text-gray-600" style={{ animationDelay: '80ms' }}>
            <Clock size={13} className="shrink-0 text-gray-400" />
            <span>Tiempo total: <span className="font-semibold text-gray-800">{formatElapsed(elapsedSeconds)}</span></span>
          </div>

          {totalMonto > 0 && (
            <div className="metric-reveal flex items-center gap-2 text-xs text-gray-600" style={{ animationDelay: '160ms' }}>
              <TrendingUp size={13} className="shrink-0 text-primary-500" />
              <span>
                Total en comprobantes:{' '}
                <span className="font-semibold text-gray-800">{formatMonto(animatedMonto)}</span>
              </span>
            </div>
          )}

          <div className="metric-reveal flex items-center gap-2 text-xs text-gray-600" style={{ animationDelay: '240ms' }}>
            <Zap size={13} className="shrink-0 text-yellow-500" />
            <span>
              Tiempo ahorrado estimado:{' '}
              <span className="font-semibold text-gray-800">{estimateSavedHours(totalFiles)}</span>
              {' '}de revisión manual
            </span>
          </div>

          {topEmisor && (
            <div className="metric-reveal text-xs text-gray-600" style={{ animationDelay: '320ms' }}>
              <span className="mr-1">🏆</span>
              Emisor top:{' '}
              <span className="font-semibold text-gray-800 truncate">{topEmisor.nombre}</span>
              <span className="ml-1 text-gray-400">({topEmisor.count} facturas)</span>
            </div>
          )}

          {topMonth && (
            <div className="metric-reveal text-xs text-gray-600" style={{ animationDelay: '400ms' }}>
              <span className="mr-1">📅</span>
              Mes más activo:{' '}
              <span className="font-semibold text-gray-800">{formatTopMonth(topMonth.month)}</span>
              <span className="ml-1 text-gray-400">({topMonth.count} facturas)</span>
            </div>
          )}
        </div>

        {/* Status summary */}
        <div className="metric-reveal mb-4 flex gap-2 text-xs" style={{ animationDelay: '480ms' }}>
          {ok > 0 && (
            <div className="flex-1 rounded-lg bg-green-50 py-2 text-center font-semibold text-green-700">
              {ok.toLocaleString('es-MX')} sin error
            </div>
          )}
          {conErrores > 0 && (
            <div className="flex-1 rounded-lg bg-yellow-50 py-2 text-center font-semibold text-yellow-700">
              {conErrores} hallazgos
            </div>
          )}
          {errors > 0 && (
            <div className="flex-1 rounded-lg bg-red-50 py-2 text-center font-semibold text-red-700">
              {errors} errores
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          {(conErrores > 0 || errors > 0) && (
            <button
              onClick={handleViewTriage}
              className="flex-1 rounded-lg bg-primary-600 py-2 text-xs font-semibold text-white transition-colors hover:bg-primary-700"
            >
              Ver hallazgos →
            </button>
          )}
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-gray-200 py-2 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
}
