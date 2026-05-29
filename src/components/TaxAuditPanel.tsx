import clsx from 'clsx';
import { ChevronRight } from 'lucide-react';
import type { CFDIData } from '../cfdi/public';

interface TaxAuditPanelProps {
  cfdi: CFDIData;
  taxAuditExpanded: boolean;
  onToggle: () => void;
  getExplainedMeaning: (key: string, value: string | number | null) => string;
  getExplainedTaxLabel: (code: string) => string;
  formatExact: (value: number) => string;
}

export default function TaxAuditPanel({
  cfdi,
  taxAuditExpanded,
  onToggle,
  getExplainedMeaning,
  getExplainedTaxLabel,
  formatExact,
}: TaxAuditPanelProps) {
  const diffCount = cfdi.taxAuditGroups.filter((g) => Math.abs(g.diferencia) !== 0).length;

  return (
    <div className="shrink-0 border-t border-gray-200">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-4 px-4 py-2.5 text-left transition-colors duration-200 hover:bg-gray-50"
      >
        <div>
          <p className="text-sm font-semibold text-gray-700">Auditoría de Traslados</p>
          <p className="mt-0.5 text-tiny text-gray-500">
            Comparación entre el detalle por concepto y el agrupado del comprobante.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {diffCount > 0 ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-700">
              <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
              {diffCount} {diffCount === 1 ? 'diferencia' : 'diferencias'}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Sin diferencias
            </span>
          )}
          <ChevronRight
            size={14}
            className={clsx(
              'text-gray-400 transition-transform duration-200',
              taxAuditExpanded && 'rotate-90',
            )}
          />
        </div>
      </button>

      {taxAuditExpanded && (
        <div className="max-h-36 overflow-auto border-t border-gray-200">
          <table className="w-full border-collapse">
            <thead className="sticky top-0 z-10 bg-gray-50">
              <tr className="border-b border-gray-200 text-left">
                {['Impuesto', 'Tipo', 'Tasa', 'Detalle', 'Agrupado', 'Dif.'].map((h, i) => (
                  <th
                    key={h}
                    className={clsx(
                      'px-3 py-2 text-tiny font-medium uppercase tracking-wider text-gray-500',
                      i >= 2 && 'text-right',
                    )}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {cfdi.taxAuditGroups.map((group) => {
                const hasDiff = Math.abs(group.diferencia) !== 0;
                return (
                  <tr key={group.key} className="hover:bg-gray-50 transition-colors duration-150">
                    <td className="px-3 py-2" title={getExplainedMeaning('impuesto', group.impuesto)}>
                      <p className="text-xs text-gray-800">{getExplainedTaxLabel(group.impuesto)}</p>
                      <p className="text-tiny text-gray-400">{getExplainedMeaning('impuesto', group.impuesto)}</p>
                    </td>
                    <td className="px-3 py-2" title={getExplainedMeaning('tipoFactor', group.tipoFactor)}>
                      <p className="text-xs text-gray-800">{group.tipoFactor}</p>
                      <p className="text-tiny text-gray-400">{getExplainedMeaning('tipoFactor', group.tipoFactor)}</p>
                    </td>
                    <td className="px-3 py-2 text-right" title={getExplainedMeaning('tasaOCuota', group.tasaOCuota)}>
                      <p className="text-xs text-gray-800 tabular-nums">{(group.tasaOCuota * 100).toFixed(2)}%</p>
                    </td>
                    <td className="px-3 py-2 text-right text-xs text-gray-800 tabular-nums">
                      ${group.importeDetalle.toFixed(2)}
                    </td>
                    <td className="px-3 py-2 text-right text-xs text-gray-800 tabular-nums">
                      ${group.importeAgrupado.toFixed(2)}
                    </td>
                    <td
                      className={clsx(
                        'px-3 py-2 text-right text-xs font-medium tabular-nums',
                        hasDiff ? 'text-red-600' : 'text-emerald-600',
                      )}
                    >
                      ${formatExact(group.diferencia)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
