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
    selectedRowCount,
    setColumnFilterKey,
    setSearchTerm,
    setPageSize,
    resetGrid,
  } = grid;

  const activeColumnLabel =
    extractColumns.find((col) => col.key === extractColumnFilterKey)?.label ?? 'columna';
  const searchScopeLabel =
    extractColumnFilterKey === 'all' ? 'todas las columnas' : activeColumnLabel;
  const searchSummary = extractSearchTerm.trim()
    ? `"${extractSearchTerm.trim()}" en ${searchScopeLabel}`
    : `sin busqueda global (${searchScopeLabel})`;

  return (
    <div className="shrink-0 space-y-2.5 border-b border-gray-200 bg-white px-4 py-3">
      {/* Controls row */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
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
              'w-72 rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-700 outline-none',
              'placeholder:text-gray-400 transition-colors duration-200',
              'focus:border-primary-400 focus:ring-1 focus:ring-primary-400/30',
            )}
          />
        </div>

        <div className="flex items-center gap-2.5">
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
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

      {/* Status chips */}
      <div className="flex flex-wrap items-center gap-1.5">
        {[
          searchSummary,
          `${filteredExtractCount} de ${totalExtractCount} visibles`,
          `${sorting.length} sorts`,
          `${grid.columnFilters.length} filtros de columna`,
          `${selectedRowCount} seleccionados`,
        ].map((label, i) => (
          <span
            key={i}
            className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-tiny text-gray-500"
          >
            {label}
          </span>
        ))}
        <span className="text-tiny text-gray-400">· Shift+click agrega niveles de sort</span>
      </div>
    </div>
  );
}
