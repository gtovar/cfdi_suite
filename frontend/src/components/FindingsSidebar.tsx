import clsx from 'clsx';
import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import type { CFDIConcept, CFDIData } from '../cfdi/public';
import { getSeverityColors } from '../app/utils/findingUtils';

export interface FindingConceptLink {
  concept: CFDIConcept;
  conceptIndex: number;
  reason: string;
}

export interface CorrectionStep {
  text: string;
  copyValue?: string;
  copyLabel?: string;
}

export interface FindingContext {
  findingId: string;
  explanation: string;
  relationshipLabel: string;
  whyItMatters?: string;
  differenceLabel?: string;
  conceptLinks: FindingConceptLink[];
  correctionSteps?: CorrectionStep[];
}

interface FindingsSidebarProps {
  cfdi: CFDIData;
  findingContexts: FindingContext[];
  getFindingOriginLabel: (findingId: string) => string;
  selectedFindingId: string | null;
  onSelectFinding: (id: string | null) => void;
}

export default function FindingsSidebar({
  cfdi,
  findingContexts,
  getFindingOriginLabel,
  selectedFindingId,
  onSelectFinding,
}: FindingsSidebarProps) {

    const [showAllFindings, setShowAllFindings] = useState(false);
    const [prevUuid, setPrevUuid] = useState(cfdi.uuid);

    if (cfdi.uuid !== prevUuid) {
        setPrevUuid(cfdi.uuid);
        setShowAllFindings(false);
    }
  const visibleFindings = showAllFindings ? cfdi.findings : cfdi.findings.slice(0, 4);
  const hiddenFindingsCount = Math.max(0, cfdi.findings.length - visibleFindings.length);

  return (
    <aside className="flex w-80 min-h-0 shrink-0 flex-col rounded-2xl bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-gray-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <AlertTriangle size={14} className="text-amber-500 shrink-0" />
          <p className="text-xs font-semibold text-gray-700">Hallazgos</p>
        </div>
        <span className="inline-flex shrink-0 items-center rounded-full bg-amber-50 px-2 py-0.5 text-tiny font-semibold text-amber-700">
          {cfdi.findings.length} {cfdi.findings.length === 1 ? 'alerta' : 'alertas'}
        </span>
      </div>

      {/* Findings list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {visibleFindings.map((finding) => {
          const colors = getSeverityColors(finding.severity);
          const ctx = findingContexts.find((c) => c.findingId === finding.id);
          const isSelected = selectedFindingId === finding.id;
          return (
            <div
              key={finding.id}
              className={clsx('rounded-xl border p-3', colors.containerBorder, colors.containerBg)}
            >
              <div className="flex items-start gap-2">
                <AlertTriangle size={13} className={clsx('mt-0.5 shrink-0', colors.icon)} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5 mb-1">
                    <span className={clsx('inline-flex rounded-full px-1.5 py-0.5 text-tiny font-medium', colors.badge)}>
                      {getFindingOriginLabel(finding.id)}
                    </span>
                    <p className={clsx('text-xs font-semibold', colors.title)}>
                      {finding.title}
                    </p>
                  </div>
                  <p className={clsx('text-xs leading-relaxed', colors.body)}>
                    {finding.summary}
                  </p>
                  {ctx && (
                    <div className="mt-2 space-y-2 border-t border-current/10 pt-2">
                      {!isSelected && (
                        <p className={clsx('text-xs leading-relaxed', colors.bodyMuted)}>
                          {ctx.explanation}
                        </p>
                      )}
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className={clsx('rounded px-1.5 py-0.5 text-tiny font-medium uppercase tracking-wide', colors.relBadge)}>
                          {ctx.relationshipLabel}
                        </span>
                        {!isSelected && ctx.differenceLabel && (
                          <span className="text-tiny opacity-60">{ctx.differenceLabel}</span>
                        )}
                      </div>
                      {(ctx.conceptLinks.length > 0 || ctx.correctionSteps) && (
                        <button
                          type="button"
                          onClick={() => onSelectFinding(isSelected ? null : finding.id)}
                          className={clsx(
                            'inline-flex items-center rounded-lg border px-2.5 py-1 text-tiny font-medium transition-colors duration-200',
                            isSelected
                              ? 'border-primary-600 bg-primary-600 text-white'
                              : 'border-gray-300 text-gray-600 hover:border-primary-400 hover:text-primary-600',
                          )}
                        >
                          {isSelected ? 'Enfocado' : 'Ver cómo resolver'}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {cfdi.findings.length > 4 && (
          <div className="flex items-center justify-between rounded-xl border border-gray-200 bg-gray-50 px-3 py-2">
            <span className="text-tiny text-gray-500">
              {showAllFindings ? 'Lista completa visible' : `${hiddenFindingsCount} hallazgos ocultos`}
            </span>
            <button
              type="button"
              onClick={() => setShowAllFindings((v) => !v)}
              className="rounded px-2 py-0.5 text-tiny font-medium text-primary-600 hover:bg-primary-50 transition-colors duration-200"
            >
              {showAllFindings ? 'Ver menos' : 'Ver todos'}
            </button>
          </div>
        )}

      </div>
    </aside>
  );
}
