import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
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
  const selectedFindingContext = findingContexts.find((context) => context.findingId === selectedFindingId)
    ?? findingContexts.find((context) => context.conceptLinks.length > 0)
    ?? null;
  const visibleConceptLinks = selectedFindingContext?.conceptLinks.slice(0, 4) ?? [];
  const hiddenImpactedConceptCount = Math.max(
    0,
    (selectedFindingContext?.conceptLinks.length ?? 0) - visibleConceptLinks.length,
  );

  useEffect(() => {
    setShowAllFindings(false);
    setSelectedFindingId(findingContexts.find((context) => context.conceptLinks.length > 0)?.findingId ?? null);
  }, [cfdi.uuid, findingContexts]);

  return (
    <aside className="w-80 min-h-0 border-r border-[#141414] flex flex-col bg-[#E4E3E0]">
      <div className="p-4 border-b border-[#141414]">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className={`w-2 h-2 rounded-full shrink-0 ${cfdi.findings.length > 0 ? 'bg-red-600' : 'bg-green-600'}`} />
            <p className="text-[10px] font-mono uppercase tracking-[0.2em] opacity-60">Hallazgos encontrados</p>
          </div>
          <span
            className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-mono ${
              cfdi.findings.length > 0
                ? 'bg-red-100 text-red-600'
                : 'bg-green-100 text-green-700'
            }`}
          >
            {cfdi.findings.length === 0 ? '0 alertas' : `${cfdi.findings.length} alertas`}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {cfdi.findings.length === 0 ? (
          <p className="text-[11px] font-mono opacity-55 leading-relaxed">
            No se detectaron discrepancias con las reglas actualmente implementadas para este XML.
          </p>
        ) : (
          <div className="space-y-3">
            {visibleFindings.map((finding) => (
              <div
                key={finding.id}
                className={`p-3 border rounded flex gap-3 ${
                  finding.severity === 'critical'
                    ? 'border-red-500/30 bg-red-50'
                    : 'border-amber-500/30 bg-amber-50'
                }`}
              >
                <AlertTriangle
                  className={finding.severity === 'critical' ? 'text-red-500 shrink-0' : 'text-amber-500 shrink-0'}
                  size={16}
                />
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-mono ${
                      finding.severity === 'critical'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-amber-100 text-amber-700'
                    }`}>
                      {getFindingOriginLabel(finding.id)}
                    </span>
                    <p className={`text-xs font-semibold ${finding.severity === 'critical' ? 'text-red-900' : 'text-amber-900'}`}>
                      {finding.title}
                    </p>
                  </div>
                  <p className={`text-xs font-mono leading-relaxed mt-1 ${finding.severity === 'critical' ? 'text-red-900' : 'text-amber-900'}`}>
                    {finding.summary}
                  </p>
                  {findingContexts.find((context) => context.findingId === finding.id) ? (
                    <div className="mt-3 space-y-2 border-t border-current/10 pt-3">
                      <p className={`text-[10px] font-mono leading-relaxed ${finding.severity === 'critical' ? 'text-red-900/80' : 'text-amber-900/80'}`}>
                        {findingContexts.find((context) => context.findingId === finding.id)?.explanation}
                      </p>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`px-2 py-1 text-[10px] font-mono uppercase tracking-widest ${
                          finding.severity === 'critical'
                            ? 'bg-red-100/80 text-red-800'
                            : 'bg-amber-100/80 text-amber-800'
                        }`}>
                          {findingContexts.find((context) => context.findingId === finding.id)?.relationshipLabel}
                        </span>
                        {findingContexts.find((context) => context.findingId === finding.id)?.differenceLabel ? (
                          <span className="text-[10px] font-mono uppercase tracking-widest opacity-70">
                            {findingContexts.find((context) => context.findingId === finding.id)?.differenceLabel}
                          </span>
                        ) : null}
                      </div>
                      {(findingContexts.find((context) => context.findingId === finding.id)?.conceptLinks.length ?? 0) > 0 ? (
                        <button
                          type="button"
                          onClick={() => setSelectedFindingId(finding.id)}
                          className={`border px-2.5 py-1 text-[10px] font-mono uppercase tracking-widest transition-colors ${
                            selectedFindingContext?.findingId === finding.id
                              ? 'border-[#141414] bg-[#141414] text-[#E4E3E0]'
                              : 'border-[#141414]/20 hover:border-[#141414] hover:bg-[#141414] hover:text-[#E4E3E0]'
                          }`}
                        >
                          {selectedFindingContext?.findingId === finding.id ? 'Hallazgo enfocado' : 'Ver conceptos relacionados'}
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
            {cfdi.findings.length > 4 ? (
              <div className="flex items-center justify-between gap-3 rounded border border-[#141414]/10 bg-white/50 px-3 py-2 text-[10px] font-mono uppercase tracking-widest">
                <span className="opacity-55">
                  {showAllFindings ? 'Lista completa visible' : `${hiddenFindingsCount} hallazgos ocultos`}
                </span>
                <button
                  type="button"
                  onClick={() => setShowAllFindings((current) => !current)}
                  className="border border-[#141414]/20 px-2.5 py-1 text-[10px] hover:border-[#141414] hover:bg-[#141414] hover:text-[#E4E3E0] transition-colors"
                >
                  {showAllFindings ? 'Ver menos' : 'Ver todos'}
                </button>
              </div>
            ) : null}
          </div>
        )}

        {selectedFindingContext && selectedFindingContext.conceptLinks.length > 0 ? (
          <div className="border border-[#141414]/10 bg-white/40 rounded p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[10px] font-mono uppercase tracking-widest opacity-50">
                Conceptos relacionados
              </p>
              <span className="text-[10px] font-mono uppercase opacity-45">
                {selectedFindingContext.conceptLinks.length}
              </span>
            </div>
            <p className="mt-3 text-[10px] font-mono uppercase tracking-widest opacity-45">
              Relacionados con: {cfdi.findings.find((finding) => finding.id === selectedFindingContext.findingId)?.title}
            </p>
            <p className="mt-2 text-[11px] font-mono leading-relaxed opacity-60">
              {selectedFindingContext.explanation}
            </p>
            <div className="mt-3 space-y-2">
              {visibleConceptLinks.map((link) => (
                <button
                  key={`${link.concept.claveProdServ}-${link.concept.descripcion}-${link.conceptIndex}`}
                  type="button"
                  onClick={() => onSelectConcept(link.concept)}
                  className="w-full border border-[#141414]/10 bg-white/70 px-3 py-2 text-left hover:border-[#141414] hover:bg-[#141414] hover:text-[#E4E3E0] transition-colors"
                >
                  <p className="text-[10px] font-mono uppercase tracking-widest opacity-55">
                    Concepto {link.conceptIndex + 1}
                  </p>
                  <p className="mt-1 text-xs font-semibold truncate">
                    {link.concept.descripcion || 'Sin descripcion'}
                  </p>
                  <p className="mt-2 text-[10px] font-mono leading-relaxed opacity-60 normal-case tracking-normal">
                    {link.reason}
                  </p>
                </button>
              ))}
            </div>
            {hiddenImpactedConceptCount > 0 ? (
              <p className="mt-3 text-[10px] font-mono uppercase tracking-widest opacity-40">
                {hiddenImpactedConceptCount} conceptos adicionales relacionados no visibles
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="p-4 border-t border-[#141414] bg-[#141414]/5">
        <h3 className="text-[10px] font-mono uppercase tracking-widest opacity-50 mb-3">Resumen</h3>
        <div className="space-y-2 text-[11px] font-mono">
          {activeDatasetType === 'ingresos' ? (
            <>
              <div className="flex justify-between gap-3">
                <span>Subtotal XML</span>
                <span>${cfdi.subtotal.toLocaleString('es-MX', { minimumFractionDigits: 2 })}</span>
              </div>
              <div className="flex justify-between gap-3 text-blue-600 italic">
                <span>Subtotal Calc.</span>
                <span>${cfdi.subtotalCalculado.toLocaleString('es-MX', { minimumFractionDigits: 2 })}</span>
              </div>
              <div className={`flex justify-between gap-3 ${subtotalDifference !== 0 ? 'text-red-600' : 'text-green-600'}`}>
                <span>Dif. Subtotal</span>
                <span>${formatExact(subtotalDifference)}</span>
              </div>
              <div className="flex justify-between gap-3 border-t border-[#141414]/10 pt-2">
                <span>Total XML</span>
                <span>${cfdi.total.toLocaleString('es-MX', { minimumFractionDigits: 2 })}</span>
              </div>
              <div className="flex justify-between gap-3 text-blue-600 italic">
                <span>Total Calc.</span>
                <span>${cfdi.totalCalculado.toLocaleString('es-MX', { minimumFractionDigits: 2 })}</span>
              </div>
              <div className={`flex justify-between gap-3 ${totalDifference !== 0 ? 'text-red-600' : 'text-green-600'}`}>
                <span>Dif. Total</span>
                <span>${formatExact(totalDifference)}</span>
              </div>
            </>
          ) : (
            activeExtractMetrics.map((metric) => (
              <div key={metric.key} className="flex justify-between gap-3">
                <span>{metric.label}</span>
                <span>{metric.value}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}
