import clsx from 'clsx';
import { Building2, FileDown, FolderOpen, Palette, PanelLeftClose, PanelLeftOpen, Search, XCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type AppView = 'inspector' | 'consultas-sat' | 'masivo' | 'conversion-masiva' | 'cancelaciones' | 'emisores' | 'pdf-templates';

interface NavItem {
  id: AppView;
  label: string;
  hint: string;
  Icon: LucideIcon;
  disabled?: boolean;
  phase?: string;
}

interface NavSection {
  label?: string;
  items: NavItem[];
}

const NAVIGATION: NavSection[] = [
  {
    label: 'Operaciones',
    items: [
      { id: 'consultas-sat', label: 'Consultas SAT', hint: 'Verifica si tus CFDIs están vigentes o cancelados — procesa varios a la vez', Icon: Search },
      { id: 'masivo', label: 'Análisis masivo', hint: 'Carga cientos de XMLs, audítalos en batch y descarga reportes (DIOT, IVA/ISR)', Icon: FolderOpen },
      { id: 'conversion-masiva', label: 'Conversión masiva', hint: 'Convierte miles de XMLs a PDF de una sola solicitud', Icon: FileDown },
      { id: 'cancelaciones', label: 'Cancelaciones', hint: 'Envía solicitudes de cancelación al SAT (próximamente)', Icon: XCircle, disabled: true, phase: 'F4' },
    ],
  },
  {
    label: 'Configuración',
    items: [
      { id: 'emisores', label: 'Emisores', hint: 'Configura los RFCs y e.Firmas de tus empresas', Icon: Building2 },
      { id: 'pdf-templates', label: 'Templates PDF', hint: 'Diseña el layout de tus PDF Pro', Icon: Palette },
    ],
  },
];

interface AppSidebarProps {
  activeView: AppView;
  onViewChange: (view: AppView) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export default function AppSidebar({
  activeView,
  onViewChange,
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onMobileClose,
}: AppSidebarProps) {
  return (
    <div
      className={clsx(
        'flex h-full flex-col overflow-hidden border-r border-gray-200 bg-white transition-[width,transform] duration-200 ease-in-out',
        'fixed inset-y-0 left-0 z-40 w-64 shrink-0',
        mobileOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full',
        'md:relative md:inset-y-auto md:left-auto md:z-auto md:translate-x-0 md:shadow-none',
        collapsed ? 'md:w-[60px]' : 'md:w-52',
      )}
    >
      {/* Brand — same height as AppHeader */}
      <div className="flex h-[65px] shrink-0 items-center border-b border-gray-200 px-4">
        <div className={clsx('flex items-center gap-3', collapsed && 'justify-center w-full')}>
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-600 text-sm font-bold text-white select-none">
            CS
          </span>
          {!collapsed && (
            <span className="whitespace-nowrap text-sm font-semibold tracking-wide text-gray-900">
              CFDI Suite
            </span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-x-hidden overflow-y-auto px-3 py-3">
        {NAVIGATION.map((section, si) => (
          <div key={si} className={clsx(si > 0 && 'mt-5')}>
            {section.label && !collapsed && (
              <p className="mb-1 px-2 pb-1 pt-1 text-tiny font-medium uppercase tracking-wider text-gray-500">
                {section.label}
              </p>
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const isActive = activeView === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    disabled={item.disabled}
                    onClick={() => { if (!item.disabled) { onViewChange(item.id); onMobileClose(); } }}
                    title={collapsed ? item.label : item.hint}
                    style={{ height: '34px' }}
                    className={clsx(
                      'flex w-full items-center rounded-lg text-xs-plus tracking-wide outline-hidden transition-colors duration-200',
                      collapsed ? 'justify-center px-2' : 'gap-2.5 px-3',
                      item.disabled
                        ? 'cursor-not-allowed opacity-40'
                        : isActive
                          ? 'bg-primary-600/[.08] font-medium text-primary-600'
                          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                    )}
                  >
                    <item.Icon
                      size={16}
                      className={clsx('shrink-0', isActive && !item.disabled && 'text-primary-600')}
                    />
                    {!collapsed && (
                      <>
                        <span className="flex-1 truncate text-left">{item.label}</span>
                        {item.phase && (
                          <span
                            className={clsx(
                              'shrink-0 rounded px-1.5 py-0.5 text-tiny font-medium',
                              isActive
                                ? 'bg-primary-600/10 text-primary-600'
                                : 'bg-gray-150 text-gray-500',
                            )}
                          >
                            {item.phase}
                          </span>
                        )}
                      </>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Collapse toggle */}
      <div className="shrink-0 border-t border-gray-200 p-3">
        <button
          type="button"
          onClick={onToggleCollapse}
          title={collapsed ? 'Expandir sidebar' : 'Colapsar sidebar'}
          className={clsx(
            'flex w-full items-center rounded-lg p-2 text-gray-500 transition-colors duration-200 hover:bg-gray-100 hover:text-gray-700',
            collapsed ? 'justify-center' : 'gap-2.5',
          )}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          {!collapsed && <span className="text-xs-plus">Colapsar</span>}
        </button>
      </div>
    </div>
  );
}
