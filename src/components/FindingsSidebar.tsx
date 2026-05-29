import clsx from 'clsx';
import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { CFDIConcept, CFDIData } from '../cfdi/public';

export interface FindingConceptLink {
  concept: CFDIConcept;
  conceptIndex: number;
  reason: string;
}

export interface FindingContext {
  findingId: string;
  explanation: string;
  relationshipLabel: string;
  whyItMatters?: string;
  differenceLabel?: string;
  conceptLinks: FindingConceptLink[];
}

interface FindingsSidebarProps {
  cfdi: CFDIData;
  findingContexts: FindingContext[];
  getFindingOriginLabel: (findingId: string) => string;
  onSelectConcept: (concept: CFDIConcept) => void;
}

export default function FindingsSidebar({
  cfdi,
  findingContexts,
  getFindingOriginLabel,
  onSelectConcept,
}: FindingsSidebarProps) {
  const [showAllFindings, setShowAllFindings] = useState(false);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);

  const visibleFindings = showAllFindings ? cfdi.findings : cfdi.findings.slice(0, 4);
  const hiddenFindingsCount = Math.max(0, cfdi.findings.length - visibleFindings.length);
  const selectedFindingContext =
    findingContexts.find((ctx) => ctx.findingId === selectedFindingId) ??
    findingContexts.find((ctx) => ctx.conceptLinks.length > 0) ??
    null;
  const suggestedConceptLink = selectedFindingContext?.conceptLinks[0] ?? null;
  const remainingRelatedConcepts = Math.max(
    0,
    (selectedFindingContext?.conceptLinks.length ?? 0) - (suggestedConceptLink ? 1 : 0),
  );

  useEffect(() => {
    setShowAllFindings(false);
    setSelectedFindingId(
      findingContexts.find((ctx) => ctx.conceptLinks.length > 0)?.findingId ?? null,
    );
  }, [cfdi.uuid, findingContexts]);

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
          const isCritical = finding.severity === 'critical';
          const ctx = findingContexts.find((c) => c.findingId === finding.id);
          const isSelected = selectedFindingContext?.findingId === finding.id;
          return (
            <div
              key={finding.id}
              className={clsx(
                'rounded-xl border p-3',
                isCritical ? 'border-red-200 bg-red-50' : 'border-amber-200 bg-amber-50',
              )}
            >
              <div className="flex items-start gap-2">
                <AlertTriangle
                  size={13}
                  className={clsx('mt-0.5 shrink-0', isCritical ? 'text-red-500' : 'text-amber-500')}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5 mb-1">
                    <span
                      className={clsx(
                        'inline-flex rounded-full px-1.5 py-0.5 text-tiny font-medium',
                        isCritical ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700',
                      )}
                    >
                      {getFindingOriginLabel(finding.id)}
                    </span>
                    <p className={clsx('text-xs font-semibold', isCritical ? 'text-red-900' : 'text-amber-900')}>
                      {finding.title}
                    </p>
                  </div>
                  <p className={clsx('text-xs leading-relaxed', isCritical ? 'text-red-800' : 'text-amber-800')}>
                    {finding.summary}
                  </p>
                  {ctx && (
                    <div className="mt-2 space-y-2 border-t border-current/10 pt-2">
                      <p className={clsx('text-xs leading-relaxed', isCritical ? 'text-red-800/80' : 'text-amber-800/80')}>
                        {ctx.explanation}
                      </p>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={clsx(
                            'rounded px-1.5 py-0.5 text-tiny font-medium uppercase tracking-wide',
                            isCritical ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800',
                          )}
                        >
                          {ctx.relationshipLabel}
                        </span>
                        {ctx.differenceLabel && (
                          <span className="text-tiny opacity-60">{ctx.differenceLabel}</span>
                        )}
                      </div>
                      {ctx.conceptLinks.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setSelectedFindingId(finding.id)}
                          className={clsx(
                            'inline-flex items-center rounded-lg border px-2.5 py-1 text-tiny font-medium transition-colors duration-200',
                            isSelected
                              ? 'border-primary-600 bg-primary-600 text-white'
                              : 'border-gray-300 text-gray-600 hover:border-primary-400 hover:text-primary-600',
                          )}
                        >
                          {isSelected ? 'Hallazgo enfocado' : 'Ver conceptos relacionados'}
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

        {/* Review guide */}
        {selectedFindingContext && (
          <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
            <p className="text-tiny font-medium uppercase tracking-wider text-gray-500 mb-2">
              Guía de revisión
            </p>
            <p className="text-tiny text-gray-500 mb-1">
              Hallazgo: {cfdi.findings.find((f) => f.id === selectedFindingContext.findingId)?.title}
            </p>
            <p className="text-xs text-gray-600 leading-relaxed">{selectedFindingContext.explanation}</p>

            {selectedFindingContext.whyItMatters && (
              <div className="mt-2 rounded-lg border border-gray-200 bg-white p-2.5">
                <p className="text-tiny font-medium uppercase tracking-wider text-gray-500 mb-1">Por qué importa</p>
                <p className="text-xs text-gray-600 leading-relaxed">{selectedFindingContext.whyItMatters}</p>
              </div>
            )}

            <div className="mt-2 rounded-lg border border-gray-200 bg-white p-2.5">
              <p className="text-tiny font-medium uppercase tracking-wider text-gray-500 mb-1">Prioridad</p>
              <p className="text-xs text-gray-600 leading-relaxed">
                {suggestedConceptLink
                  ? `Este hallazgo toca ${selectedFindingContext.conceptLinks.length} concepto(s). Empieza por el concepto ${suggestedConceptLink.conceptIndex + 1}.`
                  : 'Este hallazgo no apunta a un concepto específico.'}
              </p>
              {suggestedConceptLink && (
                <div className="mt-2 rounded border border-gray-200 bg-gray-50 p-2">
                  <p className="text-tiny font-medium uppercase tracking-wider text-gray-500 mb-1">Concepto sugerido</p>
                  <p className="text-xs font-medium text-gray-800 truncate">
                    {suggestedConceptLink.concept.descripcion || `Concepto ${suggestedConceptLink.conceptIndex + 1}`}
                  </p>
                  <p className="mt-1 text-tiny text-gray-500 leading-relaxed">{suggestedConceptLink.reason}</p>
                </div>
              )}
            </div>

            {suggestedConceptLink && (
              <div className="mt-2">
                <button
                  type="button"
                  onClick={() => onSelectConcept(suggestedConceptLink.concept)}
                  className="inline-flex items-center rounded-lg border border-gray-300 px-2.5 py-1 text-tiny font-medium text-gray-700 transition-colors duration-200 hover:border-primary-400 hover:text-primary-600"
                >
                  Abrir concepto sugerido
                </button>
                {remainingRelatedConcepts > 0 && (
                  <p className="mt-2 text-tiny text-gray-400">
                    {remainingRelatedConcepts} conceptos adicionales disponibles en la tabla
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
