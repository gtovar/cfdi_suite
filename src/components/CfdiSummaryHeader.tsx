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

export default function CfdiSummaryHeader({ summaryFields }: CfdiSummaryHeaderProps) {
  return (
    <div
      className={clsx(
        'grid shrink-0 border-b border-gray-200',
        summaryFields.length >= 4 ? 'grid-cols-4' : 'grid-cols-3',
      )}
    >
      {summaryFields.map((field, index) => {
        const Icon = field.icon;
        return (
          <div
            key={field.key}
            title={field.meaning}
            className={clsx(
              'flex items-start gap-3 p-4',
              index < summaryFields.length - 1 && 'border-r border-gray-200',
            )}
          >
            <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-500">
              <Icon size={15} />
            </div>
            <div className="min-w-0">
              <p className="text-tiny font-medium uppercase tracking-wider text-gray-500">{field.label}</p>
              <p className="mt-0.5 text-xs-plus font-semibold text-gray-900 truncate max-w-[180px]">
                {field.value}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
