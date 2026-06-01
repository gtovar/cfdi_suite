import { useState } from 'react';
import { Check, ClipboardCopy, Wrench } from 'lucide-react';
import clsx from 'clsx';
import type { AuditFinding } from '../cfdi/public';
import type { CorrectionStep, FindingContext } from './FindingsSidebar';

interface ResolutionPanelProps {
  finding: AuditFinding;
  findingContext: FindingContext;
  correctionSteps: CorrectionStep[];
  uuid: string;
  onSelectConcept?: (concept: import('../cfdi/public').CFDIConcept) => void;
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-0.5 text-tiny font-medium text-gray-600 transition-colors duration-150 hover:border-primary-400 hover:text-primary-600 shrink-0"
    >
      {copied ? <Check size={11} className="text-emerald-500" /> : <ClipboardCopy size={11} />}
      {copied ? 'Copiado' : label}
    </button>
  );
}


export default function ResolutionPanel({
  finding,
  findingContext,
  correctionSteps,
  uuid,
  onSelectConcept,
}: ResolutionPanelProps) {
  const [checkedSteps, setCheckedSteps] = useState<Set<number>>(new Set());
  const isCritical = finding.severity === 'critical';

  function toggleStep(index: number) {
    setCheckedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  const suggestedConcept = findingContext.conceptLinks[0] ?? null;

  return (
    <div className="shrink-0 border-t border-gray-200 bg-white">
      {/* Header */}
      <div className="flex items-start gap-2.5 px-4 py-3 border-b border-gray-100">
        <Wrench size={13} className="mt-0.5 shrink-0 text-primary-500" />
        <div className="min-w-0 flex-1">
          <p className="text-tiny font-semibold uppercase tracking-wider text-primary-600">
            Cómo resolver
          </p>
          <p className={`text-xs font-semibold mt-0.5 ${isCritical ? 'text-red-900' : 'text-amber-900'}`}>
            {finding.title}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-tiny text-gray-400">UUID:</span>
          <code className="text-tiny text-gray-600 font-mono truncate max-w-[140px]">{uuid}</code>
          <CopyButton value={uuid} label="Copiar UUID" />
        </div>
      </div>

      {/* Steps */}
      <div className="px-4 pt-3 pb-1 space-y-2 max-h-36 overflow-y-auto">
        {correctionSteps.map((step, index) => {
          const checked = checkedSteps.has(index);
          return (
            <div key={index} className="flex items-start gap-2.5">
              <button
                type="button"
                onClick={() => toggleStep(index)}
                className={`mt-0.5 size-4 shrink-0 rounded border flex items-center justify-center transition-colors duration-150 ${
                  checked
                    ? 'bg-emerald-500 border-emerald-500'
                    : 'border-gray-300 bg-white hover:border-primary-400'
                }`}
              >
                {checked && <Check size={10} className="text-white" />}
              </button>
              <div className="min-w-0 flex-1">
                <p className={`text-xs leading-relaxed ${checked ? 'text-gray-400 line-through' : 'text-gray-700'}`}>
                  <span className="font-medium text-gray-400 mr-1">{index + 1}.</span>
                  {step.text}
                </p>
              </div>
              {step.copyValue && !checked && (
                <CopyButton value={step.copyValue} label={step.copyLabel ?? 'Copiar'} />
              )}
            </div>
          );
        })}

        {suggestedConcept && onSelectConcept && (
          <div className="mt-2 pt-2 border-t border-gray-100">
            <p className="text-tiny text-gray-500 mb-1.5">
              Concepto afectado:{' '}
              <span className="font-medium text-gray-700">
                {suggestedConcept.concept.descripcion || `Concepto ${suggestedConcept.conceptIndex + 1}`}
              </span>
            </p>
            <button
              type="button"
              onClick={() => onSelectConcept(suggestedConcept.concept)}
              className="inline-flex items-center rounded-lg border border-gray-300 px-2.5 py-1 text-tiny font-medium text-gray-700 transition-colors duration-200 hover:border-primary-400 hover:text-primary-600"
            >
              Ver detalle del concepto
            </button>
          </div>
        )}
      </div>

    </div>
  );
}
