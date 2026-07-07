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
  monthBreakdown: Array<{ month: string; count: number; monto: number }>;
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
    if (target === 0) return;
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

  return target === 0 ? 0 : value;
}

export function resolveCompletionStatus(totalProblematic: number, totalFiles: number) {
  const pct = totalFiles > 0 ? totalProblematic / totalFiles : 0;
  const headline =
    totalProblematic === 0 ? '¡Lote impecable!' :
    pct < 0.05 ? 'Casi perfecto' :
    pct < 0.25 ? '¡Lote completado!' :
    'Revisión requerida';
  const headlineColor =
    totalProblematic === 0 ? 'text-green-700' :
    pct < 0.05 ? 'text-green-700' :
    pct < 0.25 ? 'text-gray-900' :
    'text-yellow-700';
  const isHealthy = totalProblematic === 0 || pct < 0.25;
  const iconBg    = isHealthy ? 'bg-green-100' : 'bg-yellow-100';
  const iconColor  = isHealthy ? 'text-green-600' : 'text-yellow-600';
  return { headline, headlineColor, iconBg, iconColor };
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
  monthBreakdown,
  onViewTriage,
  onClose,
}: BatchCompletionModalProps) {
  const [visible, setVisible] = useState(false);
  const animatedFiles = useCountUp(totalFiles, 900);
  const animatedMonto = useCountUp(totalMonto, 1400);

  const totalProblematic = conErrores + errors;
  const { headline, headlineColor, iconBg, iconColor } = resolveCompletionStatus(totalProblematic, totalFiles);
  const filesPerSec = elapsedSeconds > 0 ? (totalFiles / elapsedSeconds).toFixed(1) : null;

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
          <div className={`flex h-10 w-10 items-center justify-center rounded-full ${iconBg}`}>
            <CheckCircle2 size={20} className={iconColor} />
          </div>
          <div>
            <p className={`text-sm font-bold ${headlineColor}`}>{headline}</p>
            <p className="text-xs text-gray-400">
              <span className="font-semibold tabular-nums text-gray-700">
                {animatedFiles.toLocaleString('es-MX')}
              </span>{' '}
              facturas procesadas
            </p>
          </div>
        </div>

        <div className="mb-3 space-y-2 rounded-xl border border-gray-100 bg-gray-50 p-3">
          <div className="metric-reveal flex items-center gap-2 text-xs text-gray-600" style={{ animationDelay: '80ms' }}>
            <Clock size={13} className="shrink-0 text-gray-400" />
            <span>Tiempo total: <span className="font-semibold text-gray-800">{formatElapsed(elapsedSeconds)}</span>
              {filesPerSec && <span className="ml-1 text-gray-400">· {filesPerSec} facts/seg</span>}
            </span>
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

          {topMonth && !monthBreakdown.length && (
            <div className="metric-reveal text-xs text-gray-600" style={{ animationDelay: '400ms' }}>
              <span className="mr-1">📅</span>
              Mes más activo:{' '}
              <span className="font-semibold text-gray-800">{formatTopMonth(topMonth.month)}</span>
              <span className="ml-1 text-gray-400">({topMonth.count} facturas)</span>
            </div>
          )}
        </div>

        {/* Month breakdown — "Wrapped" style */}
        {monthBreakdown.length > 0 && (
          <div className="metric-reveal mb-3 rounded-xl border border-gray-100 bg-gray-50 p-3" style={{ animationDelay: '420ms' }}>
            <p className="mb-2 text-tiny font-semibold uppercase tracking-wider text-gray-400">📅 Por mes</p>
            <div className="space-y-1.5">
              {monthBreakdown.map(({ month, count, monto }) => (
                <div key={month} className="flex items-center justify-between text-xs">
                  <span className="text-gray-700">{formatTopMonth(month)}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-gray-800">{count.toLocaleString('es-MX')} facts.</span>
                    {monto > 0 && <span className="text-gray-400">{formatMonto(monto)}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

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
