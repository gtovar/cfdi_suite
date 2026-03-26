import type { ExtractGridController } from './types';

interface ExtractWorkspaceToolbarProps {
  grid: ExtractGridController;
}

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
  const activeColumnLabel = extractColumns.find((column) => column.key === extractColumnFilterKey)?.label ?? 'columna';
  const searchScopeLabel = extractColumnFilterKey === 'all' ? 'todas las columnas' : activeColumnLabel;
  const searchSummary = extractSearchTerm.trim()
    ? `"${extractSearchTerm.trim()}" en ${searchScopeLabel}`
    : `sin busqueda global (${searchScopeLabel})`;

  return (
    <div className="p-4 border-b border-[#141414] bg-white/50 space-y-3">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest opacity-70">
            <span>Buscar en</span>
            <select
              value={extractColumnFilterKey}
              onChange={(e) => setColumnFilterKey(e.target.value)}
              className="border border-[#141414]/20 bg-transparent px-2 py-2 text-[10px] font-mono"
            >
              <option value="all">Todas</option>
              {extractColumns.map((column) => (
                <option key={column.key} value={column.key}>
                  {column.label}
                </option>
              ))}
            </select>
          </label>
          <div className="relative w-80">
            <input
              type="text"
              placeholder={`Buscar en ${extractColumnFilterKey === 'all' ? 'todas las columnas' : activeColumnLabel}...`}
              className="w-full pl-9 pr-4 py-2 text-xs font-mono bg-transparent border border-[#141414]/20 focus:border-[#141414] outline-none transition-colors"
              value={extractSearchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest opacity-70">
            <span>Filas por pagina</span>
            <select
              value={extractPageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
              className="border border-[#141414]/20 bg-transparent px-2 py-2 text-[10px] font-mono"
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
            className="border border-[#141414]/20 px-3 py-2 text-[10px] font-mono uppercase tracking-widest hover:border-[#141414] hover:bg-[#141414] hover:text-[#E4E3E0] transition-colors"
          >
            Reset grid
          </button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono uppercase tracking-widest opacity-60">
        <span className="opacity-40">Estado</span>
        <span className="px-2 py-1 border border-[#141414]/10 bg-white/60">
          {searchSummary}
        </span>
        <span className="px-2 py-1 border border-[#141414]/10 bg-white/60">
          {filteredExtractCount} de {totalExtractCount} visibles
        </span>
        <span className="px-2 py-1 border border-[#141414]/10 bg-white/60">
          {sorting.length} {sorting.length === 1 ? 'sort' : 'sorts'}
        </span>
        <span className="px-2 py-1 border border-[#141414]/10 bg-white/60">
          {grid.columnFilters.length} filtros de columna
        </span>
        <span className="px-2 py-1 border border-[#141414]/10 bg-white/60">
          {selectedRowCount} seleccionados
        </span>
        <span className="opacity-40">Sort y filtros finos viven en los headers</span>
        <span className="opacity-40">Shift + click agrega niveles de sort</span>
      </div>
    </div>
  );
}
