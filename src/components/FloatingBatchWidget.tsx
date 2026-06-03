import { Loader2, X } from 'lucide-react';

export interface BatchProgressStatus {
  completed: number;
  total: number;
  phase: 'processing' | 'done';
}

interface FloatingBatchWidgetProps {
  status: BatchProgressStatus;
  onNavigate: () => void;
  onDismiss: () => void;
}

export default function FloatingBatchWidget({ status, onNavigate, onDismiss }: FloatingBatchWidgetProps) {
  const pct = status.total > 0 ? Math.round((status.completed / status.total) * 100) : 0;

  return (
    <div className="float-widget-in fixed bottom-5 right-5 z-40 w-72 rounded-xl border border-gray-200 bg-white shadow-2xl">
      <button
        onClick={onNavigate}
        className="block w-full rounded-xl p-3 text-left transition-colors hover:bg-gray-50"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {status.phase === 'processing' ? (
              <Loader2 size={13} className="shrink-0 animate-spin text-primary-500" />
            ) : (
              <span className="text-sm">✓</span>
            )}
            <span className="text-xs font-semibold text-gray-800">
              {status.phase === 'processing'
                ? `Procesando lote…`
                : 'Lote completado'}
            </span>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); onDismiss(); }}
            className="rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X size={12} />
          </button>
        </div>

        <div className="mt-2">
          <div className="mb-1 flex justify-between text-tiny text-gray-400">
            <span>{status.completed.toLocaleString('es-MX')} / {status.total.toLocaleString('es-MX')} facturas</span>
            <span>{pct}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-gray-100">
            <div
              className={`h-full rounded-full transition-[width] duration-300 ease-out ${status.phase === 'done' ? 'bg-green-500' : 'bg-primary-500'}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        {status.phase === 'processing' && (
          <p className="mt-1.5 text-tiny text-gray-400">
            Clic para ver el progreso en detalle →
          </p>
        )}
      </button>
    </div>
  );
}
