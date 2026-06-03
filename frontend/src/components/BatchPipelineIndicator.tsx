import clsx from 'clsx';
import { AlertTriangle, Check, Loader2 } from 'lucide-react';

type PipelineStage = 'idle' | 'processing' | 'done';

interface BatchPipelineIndicatorProps {
  stage: PipelineStage;
  completed: number;
  total: number;
  errors?: number;
}

const STAGES = [
  { key: 'ready', label: 'Archivos listos' },
  { key: 'analyzing', label: 'Analizando' },
  { key: 'results', label: 'Resultados' },
] as const;

export default function BatchPipelineIndicator({ stage, completed, total, errors = 0 }: BatchPipelineIndicatorProps) {
  const activeIdx = stage === 'idle' ? 0 : stage === 'processing' ? 1 : 2;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const doneWithErrors = stage === 'done' && errors > 0;
  const doneClean = stage === 'done' && errors === 0;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-0">
        {STAGES.map((s, i) => {
          const isDone = i < activeIdx;
          const isActive = i === activeIdx;
          const isPending = i > activeIdx;
          const isLastDone = isActive && stage === 'done';

          return (
            <div key={s.key} className="flex items-center">
              {/* Node */}
              <div className="flex flex-col items-center gap-1">
                <div
                  className={clsx(
                    'flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold transition-all duration-300',
                    isDone && 'bg-primary-600 text-white',
                    isActive && !isLastDone && 'border-2 border-primary-500 bg-primary-50 text-primary-700',
                    isLastDone && doneClean && 'bg-green-500 text-white',
                    isLastDone && doneWithErrors && 'bg-amber-400 text-white',
                    isPending && 'border-2 border-gray-200 bg-white text-gray-300',
                  )}
                >
                  {isDone ? (
                    <Check size={13} strokeWidth={2.5} />
                  ) : isLastDone && doneClean ? (
                    <Check size={13} strokeWidth={2.5} />
                  ) : isLastDone && doneWithErrors ? (
                    <AlertTriangle size={12} strokeWidth={2.5} />
                  ) : isActive && stage === 'processing' ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <span>{i + 1}</span>
                  )}
                </div>
                <span
                  className={clsx(
                    'whitespace-nowrap text-tiny font-medium',
                    isDone && 'text-primary-600',
                    isActive && !isLastDone && 'text-gray-800',
                    isLastDone && doneClean && 'text-green-600',
                    isLastDone && doneWithErrors && 'text-amber-600',
                    isPending && 'text-gray-300',
                  )}
                >
                  {isActive && stage === 'processing'
                    ? `${s.label} ${completed}/${total}`
                    : isLastDone && doneWithErrors
                    ? `${errors} con errores`
                    : s.label}
                </span>
              </div>

              {/* Connector */}
              {i < STAGES.length - 1 && (
                <div className="mx-2 mb-[22px] h-0.5 w-16 rounded-full bg-gray-200">
                  {isDone && <div className="h-full w-full rounded-full bg-primary-400" />}
                  {isActive && stage === 'processing' && (
                    <div
                      className="h-full rounded-full bg-primary-400 transition-all duration-300"
                      style={{ width: `${pct}%` }}
                    />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar — thin line below stages */}
      {stage === 'processing' && (
        <div className="h-1 w-full rounded-full bg-gray-100">
          <div
            className="h-full rounded-full bg-primary-500 transition-[width] duration-300 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}
