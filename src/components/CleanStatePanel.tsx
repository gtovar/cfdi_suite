import { CheckCircle2, ChevronRight } from 'lucide-react';
import clsx from 'clsx';

const CHECKS = [
  'Matemática de cada concepto (Cantidad × ValorUnitario)',
  'Coherencia de traslados por renglón (Base × Tasa)',
  'Acumulación de impuestos según regla SAT',
  'Subtotal y Total del comprobante',
];

interface CleanStatePanelProps {
  showDetail: boolean;
  onToggleDetail: () => void;
}

export default function CleanStatePanel({ showDetail, onToggleDetail }: CleanStatePanelProps) {
  return (
    <div className="shrink-0 border-t border-gray-200 bg-emerald-50">
      <button
        type="button"
        onClick={onToggleDetail}
        className="flex w-full items-center justify-between gap-4 px-4 py-2.5 text-left transition-colors duration-200 hover:bg-emerald-100/60"
      >
        <div className="flex items-center gap-2">
          <CheckCircle2 size={14} className="text-emerald-600 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-emerald-800">Esta factura no tiene problemas detectados</p>
            <p className="mt-0.5 text-tiny text-emerald-700">
              Revisamos {CHECKS.length} verificaciones — todo en orden.
            </p>
          </div>
        </div>
        <ChevronRight
          size={14}
          className={clsx(
            'shrink-0 text-emerald-500 transition-transform duration-200',
            showDetail && 'rotate-90',
          )}
        />
      </button>

      {showDetail && (
        <div className="border-t border-emerald-200 px-4 py-3">
          <p className="text-tiny font-medium uppercase tracking-wider text-emerald-700 mb-2">
            Qué revisamos
          </p>
          <ul className="space-y-1.5">
            {CHECKS.map((check) => (
              <li key={check} className="flex items-start gap-2">
                <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-500" />
                <span className="text-xs text-emerald-800">{check}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
