import clsx from 'clsx';

interface FinancialSummaryCardProps {
  subtotal: number;
  subtotalCalculado: number;
  total: number;
  totalCalculado: number;
  formatExact: (value: number) => string;
}

function fmt(n: number) {
  return `$${n.toLocaleString('es-MX', { minimumFractionDigits: 2 })}`;
}

function DiffBadge({ diff }: { diff: number }) {
  const isZero = diff === 0;
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold tabular-nums',
        isZero
          ? 'bg-emerald-50 text-emerald-700'
          : 'bg-red-50 text-red-700',
      )}
    >
      <span
        className={clsx(
          'h-1.5 w-1.5 rounded-full',
          isZero ? 'bg-emerald-500' : 'bg-red-500',
        )}
      />
      {isZero ? '$0.00' : `$${diff.toFixed(2)}`}
    </span>
  );
}

export default function FinancialSummaryCard({
  subtotal,
  subtotalCalculado,
  total,
  totalCalculado,
  formatExact,
}: FinancialSummaryCardProps) {
  const subtotalDiff = Math.abs(subtotalCalculado - subtotal);
  const totalDiff = Math.abs(totalCalculado - total);
  const allClear = subtotalDiff === 0 && totalDiff === 0;

  return (
    <div className="shrink-0 rounded-2xl border border-slate-200 bg-slate-50 px-6 py-4 flex items-center gap-8">

      {/* Subtotal block */}
      <div className="flex items-center gap-5">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Subtotal XML</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-gray-800">{fmt(subtotal)}</p>
        </div>
        <span className="text-slate-300 text-base font-light select-none">vs</span>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Subtotal Calc.</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-blue-600">{fmt(subtotalCalculado)}</p>
        </div>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Diferencia</p>
          <div className="mt-0.5">
            <DiffBadge diff={subtotalDiff} />
          </div>
        </div>
      </div>

      {/* Vertical divider */}
      <div className="h-10 w-px bg-slate-200 shrink-0" />

      {/* Total block */}
      <div className="flex items-center gap-5">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Total XML</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-gray-800">{fmt(total)}</p>
        </div>
        <span className="text-slate-300 text-base font-light select-none">vs</span>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Total Calc.</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-blue-600">{fmt(totalCalculado)}</p>
        </div>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Diferencia</p>
          <div className="mt-0.5">
            <DiffBadge diff={totalDiff} />
          </div>
        </div>
      </div>

      {/* Estado global — empujado a la derecha */}
      <div className="ml-auto shrink-0">
        {allClear ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Cuadra
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700">
            <span className="h-2 w-2 rounded-full bg-red-500" />
            Diferencias detectadas
          </span>
        )}
      </div>
    </div>
  );
}
