import clsx from 'clsx';
import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { CFDIConcept, CFDIData } from '../cfdi/public';

interface SummaryMetricCard {
  key: string;
  label: string;
  value: string;
}

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
  activeDatasetType: 'ingresos' | 'pagos';
  activeExtractMetrics: SummaryMetricCard[];
  subtotalDifference: number;
  totalDifference: number;
  formatExact: (value: number) => string;
  getFindingOriginLabel: (findingId: string) => string;
  onSelectConcept: (concept: CFDIConcept) => void;
}

export default function FindingsSidebar({
  cfdi,
  findingContexts,
  activeDatasetType,
  activeExtractMetrics,
  subtotalDifference,
  totalDifference,
  formatExact,
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

  const hasFindings = cfdi.findings.length > 0;

  return (
    <aside className="flex w-80 min-h-0 shrink-0 flex-col rounded-lg bg-white shadow-soft overflow-hidden">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-4 py-3">
        <div className="flex items-center gap-2">
          {hasFindings ? (
            <AlertTriangle size={14} className="text-amber-500 shrink-0" />
          ) : (
            <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
          )}
          <p className="text-xs font-medium text-gray-700">Hallazgos</p>
        </div>
        <span
          className={clsx(
            'inline-flex items-center rounded-full px-2 py-0.5 text-tiny font-medium',
            hasFindings ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700',
          )}
        >
          {cfdi.findings.length === 0 ? '0 alertas' : `${cfdi.findings.length} alertas`}
        </span>
      </div>

      {/* Findings list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {!hasFindings ? (
          <p className="text-xs text-gray-500 leading-relaxed">
            No se detectaron discrepancias con las reglas actualmente implementadas.
          </p>
        ) : (
          <div className="space-y-2">
            {visibleFindings.map((finding) => {
              const isCritical = finding.severity === 'critical';
              const ctx = findingContexts.find((c) => c.findingId === finding.id);
              const isSelected = selectedFindingContext?.findingId === finding.id;
              return (
                <div
                  key={finding.id}
                  className={clsx(
                    'rounded-lg border p-3',
                    isCritical
                      ? 'border-red-200 bg-red-50'
                      : 'border-amber-200 bg-amber-50',
                  )}
                >
                  <div className="flex items-start gap-2">
                    <AlertTriangle
                      size={13}
                      className={clsx(
                        'mt-0.5 shrink-0',
                        isCritical ? 'text-red-500' : 'text-amber-500',
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5 mb-1">
                        <span
                          className={clsx(
                            'inline-flex rounded-full px-1.5 py-0.5 text-tiny font-medium',
                            isCritical
                              ? 'bg-red-100 text-red-700'
                              : 'bg-amber-100 text-amber-700',
                          )}
                        >
                          {getFindingOriginLabel(finding.id)}
                        </span>
                        <p
                          className={clsx(
                            'text-xs font-semibold',
                            isCritical ? 'text-red-900' : 'text-amber-900',
                          )}
                        >
                          {finding.title}
                        </p>
                      </div>
                      <p
                        className={clsx(
                          'text-xs leading-relaxed',
                          isCritical ? 'text-red-800' : 'text-amber-800',
                        )}
                      >
                        {finding.summary}
                      </p>
                      {ctx && (
                        <div className="mt-2 space-y-2 border-t border-current/10 pt-2">
                          <p
                            className={clsx(
                              'text-xs leading-relaxed',
                              isCritical ? 'text-red-800/80' : 'text-amber-800/80',
                            )}
                          >
                            {ctx.explanation}
                          </p>
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span
                              className={clsx(
                                'rounded px-1.5 py-0.5 text-tiny font-medium uppercase tracking-wide',
                                isCritical
                                  ? 'bg-red-100 text-red-800'
                                  : 'bg-amber-100 text-amber-800',
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
              <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
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
        )}

        {/* Review guide */}
        {selectedFindingContext && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
            <p className="text-tiny font-medium uppercase tracking-wider text-gray-500 mb-2">
              Guía de revisión
            </p>
            <p className="text-tiny text-gray-500 mb-1">
              Hallazgo enfocado: {cfdi.findings.find((f) => f.id === selectedFindingContext.findingId)?.title}
            </p>
            <p className="text-xs text-gray-600 leading-relaxed">
              {selectedFindingContext.explanation}
            </p>

            {selectedFindingContext.whyItMatters && (
              <div className="mt-2 rounded border border-gray-200 bg-white p-2.5">
                <p className="text-tiny font-medium uppercase tracking-wider text-gray-500 mb-1">Por qué importa</p>
                <p className="text-xs text-gray-600 leading-relaxed">{selectedFindingContext.whyItMatters}</p>
              </div>
            )}

            <div className="mt-2 rounded border border-gray-200 bg-white p-2.5">
              <p className="text-tiny font-medium uppercase tracking-wider text-gray-500 mb-1">Prioridad</p>
              <p className="text-xs text-gray-600 leading-relaxed">
                {suggestedConceptLink
                  ? `Este hallazgo toca ${selectedFindingContext.conceptLinks.length} concepto(s). Empieza por revisar el concepto ${suggestedConceptLink.conceptIndex + 1}.`
                  : 'Este hallazgo no apunta a un concepto específico; úsalo como contexto general del comprobante.'}
              </p>
              {suggestedConceptLink && (
                <div className="mt-2 rounded border border-gray-200 bg-gray-50 p-2">
                  <p className="text-tiny font-medium uppercase tracking-wider text-gray-500 mb-1">Concepto sugerido</p>
                  <p className="text-xs font-medium text-gray-800 truncate">
                    {suggestedConceptLink.concept.descripcion || `Concepto ${suggestedConceptLink.conceptIndex + 1}`}
                  </p>
                  <p className="mt-1 text-tiny text-gray-500 leading-relaxed">
                    {suggestedConceptLink.reason}
                  </p>
                </div>
              )}
            </div>

            {suggestedConceptLink && (
              <div className="mt-2">
                <div className="mb-1">
                  <p className="text-tiny font-medium uppercase tracking-wider text-gray-500">Acción</p>
                  <p className="mt-1 text-xs text-gray-600 leading-relaxed">
                    Abre el concepto sugerido para inspeccionar su detalle.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onSelectConcept(suggestedConceptLink.concept)}
                  className="inline-flex items-center rounded-lg border border-gray-300 px-2.5 py-1 text-tiny font-medium text-gray-700 transition-colors duration-200 hover:border-primary-400 hover:text-primary-600"
                >
                  Abrir concepto sugerido
                </button>
                {remainingRelatedConcepts > 0 && (
                  <p className="mt-2 text-tiny text-gray-400">
                    {remainingRelatedConcepts} conceptos adicionales siguen disponibles en la tabla principal
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Summary footer */}
      <div className="shrink-0 border-t border-gray-200 bg-gray-50 p-3">
        <p className="mb-2 text-tiny font-medium uppercase tracking-wider text-gray-500">Resumen</p>
        <div className="space-y-1.5 text-xs">
          {activeDatasetType === 'ingresos' ? (
            <>
              {[
                { label: 'Subtotal XML', value: `$${cfdi.subtotal.toLocaleString('es-MX', { minimumFractionDigits: 2 })}`, color: '' },
                { label: 'Subtotal Calc.', value: `$${cfdi.subtotalCalculado.toLocaleString('es-MX', { minimumFractionDigits: 2 })}`, color: 'text-blue-600' },
                { label: 'Dif. Subtotal', value: `$${formatExact(subtotalDifference)}`, color: subtotalDifference !== 0 ? 'text-red-600' : 'text-emerald-600' },
                { label: 'Total XML', value: `$${cfdi.total.toLocaleString('es-MX', { minimumFractionDigits: 2 })}`, color: '', divider: true },
                { label: 'Total Calc.', value: `$${cfdi.totalCalculado.toLocaleString('es-MX', { minimumFractionDigits: 2 })}`, color: 'text-blue-600' },
                { label: 'Dif. Total', value: `$${formatExact(totalDifference)}`, color: totalDifference !== 0 ? 'text-red-600' : 'text-emerald-600' },
              ].map((row, i) => (
                <div
                  key={i}
                  className={clsx(
                    'flex justify-between gap-2',
                    row.divider && 'mt-1.5 border-t border-gray-200 pt-1.5',
                  )}
                >
                  <span className="text-gray-500">{row.label}</span>
                  <span className={clsx('font-medium tabular-nums', row.color || 'text-gray-800')}>
                    {row.value}
                  </span>
                </div>
              ))}
            </>
          ) : (
            activeExtractMetrics.map((metric) => (
              <div key={metric.key} className="flex justify-between gap-2">
                <span className="text-gray-500">{metric.label}</span>
                <span className="font-medium text-gray-800">{metric.value}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}
