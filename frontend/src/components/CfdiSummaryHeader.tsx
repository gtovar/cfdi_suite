import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';

export interface SummaryFieldCard {
  key: string;
  label: string;
  value: string;
  icon: LucideIcon;
  meaning?: string;
}

interface CfdiSummaryHeaderProps {
  summaryFields: SummaryFieldCard[];
}

const CARD_STYLES: Record<string, { gradient: string; glow: string }> = {
  emisor:   { gradient: 'bg-gradient-to-br from-violet-400 to-violet-600', glow: 'shadow-violet-500/30' },
  uuid:     { gradient: 'bg-gradient-to-br from-blue-400 to-blue-600',     glow: 'shadow-blue-500/30'   },
  receptor: { gradient: 'bg-gradient-to-br from-teal-400 to-teal-600',     glow: 'shadow-teal-500/30'   },
  fecha:    { gradient: 'bg-gradient-to-br from-amber-400 to-amber-600',   glow: 'shadow-amber-500/30'  },
};

export default function CfdiSummaryHeader({ summaryFields }: CfdiSummaryHeaderProps) {
  return (
    <div className={clsx(
      'grid shrink-0 gap-4',
      summaryFields.length >= 4 ? 'grid-cols-4' : 'grid-cols-3',
    )}>
      {summaryFields.map((field) => {
        const Icon = field.icon;
        const style = CARD_STYLES[field.key] ?? {
          gradient: 'bg-gradient-to-br from-gray-400 to-gray-600',
          glow: 'shadow-gray-400/30',
        };
        return (
          <div
            key={field.key}
            title={field.meaning}
            className="flex flex-col gap-4 rounded-2xl bg-white p-5 shadow-sm"
          >
            <div
              className={clsx(
                'flex h-12 w-12 shrink-0 items-center justify-center rounded-xl shadow-lg',
                style.gradient,
                style.glow,
              )}
            >
              <Icon size={22} className="text-white" />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">
                {field.label}
              </p>
              <p className="mt-1 truncate text-sm font-bold text-gray-900">
                {field.value}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
