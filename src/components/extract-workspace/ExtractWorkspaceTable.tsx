import { flexRender } from '@tanstack/react-table';
import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { ExtractGridController, ExtractMode } from './types';

const ROW_HEIGHT = 36;
const OVERSCAN = 8;

interface ExtractWorkspaceTableProps {
  activeDatasetType: ExtractMode;
  grid: ExtractGridController;
}

export default function ExtractWorkspaceTable({ activeDatasetType, grid }: ExtractWorkspaceTableProps) {
  const { filteredExtractCount, table, toggleAllPageRowsSelected } = grid;
  const visibleColumns = table.getVisibleLeafColumns();
  const rows = table.getRowModel().rows;
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(520);

  const virtualization = useMemo(() => {
    const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    const visibleCount = Math.ceil(viewportHeight / ROW_HEIGHT) + OVERSCAN * 2;
    const endIndex = Math.min(rows.length, startIndex + visibleCount);
    return {
      startIndex,
      endIndex,
      topSpacerHeight: startIndex * ROW_HEIGHT,
      bottomSpacerHeight: Math.max(0, (rows.length - endIndex) * ROW_HEIGHT),
      visibleRows: rows.slice(startIndex, endIndex),
    };
  }, [rows, scrollTop, viewportHeight]);

  if (visibleColumns.length === 0) {
    return (
      <div className="p-16 text-center text-xs text-gray-400">
        Todas las columnas están ocultas. Usa los toggles de columnas o el botón Reset.
      </div>
    );
  }

  if (filteredExtractCount === 0) {
    return (
      <div className="p-16 text-center text-xs text-gray-400">
        {activeDatasetType === 'ingresos'
          ? 'No hay registros de ingresos para mostrar con el filtro actual.'
          : 'No hay registros de pagos para mostrar con el filtro actual.'}
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-auto"
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
      ref={(node) => {
        if (!node) return;
        const nextHeight = node.clientHeight || 520;
        if (nextHeight !== viewportHeight) {
          setViewportHeight(nextHeight);
        }
      }}
    >
      <table className="w-full border-collapse table-fixed">
        <thead className="sticky top-0 z-10 bg-slate-50 border-b border-slate-200">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="text-left">
              <th className="w-10 px-2 py-2.5 font-normal">
                <input
                  type="checkbox"
                  checked={table.getIsAllPageRowsSelected()}
                  ref={(node) => {
                    if (node) node.indeterminate = table.getIsSomePageRowsSelected() && !table.getIsAllPageRowsSelected();
                  }}
                  onChange={toggleAllPageRowsSelected}
                />
              </th>
              {headerGroup.headers.map((header) => {
                const sorted = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    className="px-3 py-2.5 whitespace-nowrap text-left text-xs font-medium uppercase tracking-wider text-gray-500 relative"
                    style={{ width: header.getSize() }}
                  >
                    {header.isPlaceholder ? null : (
                      <button
                        type="button"
                        onClick={(event) => header.column.toggleSorting(undefined, event.shiftKey)}
                        className="inline-flex items-center gap-1 hover:text-gray-700 transition-colors duration-150"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sorted === 'asc' && <ChevronUp size={11} />}
                        {sorted === 'desc' && <ChevronDown size={11} />}
                        {!sorted && <ChevronsUpDown size={11} className="opacity-30" />}
                      </button>
                    )}
                    <div
                      onMouseDown={header.getResizeHandler()}
                      onTouchStart={header.getResizeHandler()}
                      className={`absolute top-0 right-0 h-full w-1 cursor-col-resize select-none transition-colors ${
                        header.column.getIsResizing() ? 'bg-primary-500' : 'hover:bg-gray-300'
                      }`}
                    />
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {virtualization.topSpacerHeight > 0 ? (
            <tr>
              <td colSpan={visibleColumns.length + 1} style={{ height: virtualization.topSpacerHeight }} />
            </tr>
          ) : null}
          {virtualization.visibleRows.map((row) => (
            <tr
              key={row.id}
              className={`border-b border-gray-100 transition-colors duration-100 ${
                row.getIsSelected() ? 'bg-primary-50' : 'hover:bg-gray-50'
              }`}
              style={{ height: ROW_HEIGHT }}
            >
              <td className="px-2 py-2 text-center">
                <input
                  type="checkbox"
                  checked={row.getIsSelected()}
                  onChange={row.getToggleSelectedHandler()}
                />
              </td>
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  className={`px-3 py-2 whitespace-nowrap overflow-hidden text-ellipsis ${
                    cell.column.id === 'descripcion'
                      ? 'text-xs text-gray-800 font-medium max-w-[320px]'
                      : 'text-xs text-gray-700 tabular-nums max-w-[240px]'
                  }`}
                  style={{ width: cell.column.getSize() }}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext()) || '-'}
                </td>
              ))}
            </tr>
          ))}
          {virtualization.bottomSpacerHeight > 0 ? (
            <tr>
              <td colSpan={visibleColumns.length + 1} style={{ height: virtualization.bottomSpacerHeight }} />
            </tr>
          ) : null}
        </tbody>
      </table>
      {table.getState().sorting.length > 0 ? (
        <div className="px-4 py-2 border-t border-gray-100 bg-gray-50 text-tiny text-gray-400 sticky bottom-0">
          Multi-sort activo · Shift + click para agregar o quitar niveles de ordenamiento
        </div>
      ) : null}
    </div>
  );
}
