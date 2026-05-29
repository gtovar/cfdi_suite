import clsx from 'clsx';
import type { ExtractGridController } from './types';

interface ExtractWorkspaceToolbarProps {
  grid: ExtractGridController;
}

const SELECT_CLASS = clsx(
  'rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700 outline-none',
  'transition-colors duration-200 focus:border-primary-400 focus:ring-1 focus:ring-primary-400/30',
);

export default function ExtractWorkspaceToolbar({ grid }: ExtractWorkspaceToolbarProps) {
  const {
    extractColumns,
    extractColumnFilterKey,
    extractSearchTerm,
    sorting,
    extractPageSize,
    filteredExtractCount,
    totalExtractCount,
    setColumnFilterKey,
    setSearchTerm,
    setPageSize,
    resetGrid,
  } = grid;

  const activeColumnLabel =
    extractColumns.find((col) => col.key === extractColumnFilterKey)?.label ?? 'columna';
  const searchScopeLabel =
    extractColumnFilterKey === 'all' ? 'todas las columnas' : activeColumnLabel;

  return (
    <div className="shrink-0 space-y-2 border-b border-gray-200 bg-white px-4 py-3">
      {/* Controls row */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <label className="flex shrink-0 items-center gap-1.5 text-xs text-gray-600">
            <span>Buscar en</span>
            <select
              value={extractColumnFilterKey}
              onChange={(e) => setColumnFilterKey(e.target.value)}
              className={SELECT_CLASS}
            >
              <option value="all">Todas</option>
              {extractColumns.map((col) => (
                <option key={col.key} value={col.key}>
                  {col.label}
                </option>
              ))}
            </select>
          </label>

          <input
            type="text"
            placeholder={`Buscar en ${searchScopeLabel}…`}
            value={extractSearchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className={clsx(
              'w-80 rounded-lg border px-3 py-1.5 text-xs text-gray-700 outline-none',
              'placeholder:text-gray-400 transition-colors duration-200',
              'focus:ring-1 focus:ring-primary-400/30',
              extractSearchTerm
                ? 'border-primary-300 bg-primary-50/40 focus:border-primary-400'
                : 'border-gray-200 focus:border-primary-400',
            )}
          />
        </div>

        <div className="flex items-center gap-2.5">
          <label className="flex shrink-0 items-center gap-1.5 text-xs text-gray-600">
            <span>Filas</span>
            <select
              value={extractPageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
              className={SELECT_CLASS}
            >
              {[50, 100, 250, 500, 1000].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>

          <button
            onClick={resetGrid}
            className={clsx(
              'rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600',
              'transition-colors duration-200 hover:border-gray-300 hover:bg-gray-100 hover:text-gray-800',
            )}
          >
            Reset
          </button>
        </div>
      </div>

      {/* Status row — solo estado significativo */}
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span className="tabular-nums">
          {filteredExtractCount.toLocaleString('es-MX')} de {totalExtractCount.toLocaleString('es-MX')} registros
        </span>

        {extractSearchTerm.trim() && (
          <span className="inline-flex items-center gap-1 rounded-full border border-primary-200 bg-primary-50 px-2 py-0.5 text-tiny text-primary-700">
            &ldquo;{extractSearchTerm.trim()}&rdquo;
            <button
              type="button"
              onClick={() => setSearchTerm('')}
              className="ml-0.5 leading-none hover:text-primary-900 transition-colors"
              aria-label="Limpiar búsqueda"
            >
              ×
            </button>
          </span>
        )}

        {sorting.length > 0 && (
          <>
            <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-tiny text-gray-600">
              {sorting.length} {sorting.length === 1 ? 'orden' : 'órdenes'}
            </span>
            <span className="text-tiny text-gray-400">· Shift+click agrega niveles</span>
          </>
        )}
      </div>
    </div>
  );
}
