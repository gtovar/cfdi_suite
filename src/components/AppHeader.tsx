import clsx from 'clsx';
import { Menu } from 'lucide-react';
import type { AppView } from './AppNav';

const BREADCRUMBS: Record<AppView, { section: string; label: string }> = {
  inspector: { section: 'CFDI Suite', label: 'Inspector' },
  'consultas-sat': { section: 'Operaciones', label: 'Consultas SAT' },
  reprint: { section: 'Operaciones', label: 'Reprint' },
  cancelaciones: { section: 'Operaciones', label: 'Cancelaciones' },
  emisores: { section: 'Configuración', label: 'Emisores' },
};

interface AppHeaderProps {
  activeView: AppView;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
}

export default function AppHeader({ activeView, onToggleSidebar }: AppHeaderProps) {
  const crumb = BREADCRUMBS[activeView];

  return (
    <header className="sticky top-0 z-20 flex h-[65px] shrink-0 items-center justify-between border-b border-gray-200 bg-white/80 px-4 backdrop-blur-sm backdrop-saturate-150">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className={clsx(
            'flex size-8 items-center justify-center rounded-lg text-gray-600',
            'transition-colors duration-200 hover:bg-gray-100 hover:text-gray-800',
          )}
        >
          <Menu size={18} />
        </button>

        <nav className="flex items-center gap-1.5 text-xs-plus text-gray-500">
          <span>{crumb.section}</span>
          <span className="text-gray-300">/</span>
          <span className="font-medium text-gray-800">{crumb.label}</span>
        </nav>
      </div>
    </header>
  );
}
