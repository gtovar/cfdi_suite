import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { ExtractGridController } from './types';

interface ExtractWorkspacePaginationProps {
  grid: ExtractGridController;
}

export default function ExtractWorkspacePagination({ grid }: ExtractWorkspacePaginationProps) {
  const {
    safeExtractPage,
    extractTotalPages,
    filteredExtractCount,
    extractPageStart,
    selectedRowCount,
    table,
    goToPreviousPage,
    goToNextPage,
  } = grid;
  const currentPageRowCount = table.getRowModel().rows.length;

  return (
    <div className="shrink-0 flex items-center justify-between border-t border-gray-200 bg-white px-4 py-3">
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span>
          Página <span className="font-medium text-gray-700">{safeExtractPage}</span> de{' '}
          <span className="font-medium text-gray-700">{extractTotalPages}</span>
        </span>
        <span>
          {filteredExtractCount === 0
            ? '0 registros'
            : `${extractPageStart + 1}–${Math.min(
                extractPageStart + currentPageRowCount,
                filteredExtractCount,
              )} de ${filteredExtractCount.toLocaleString('es-MX')}`}
        </span>
        {selectedRowCount > 0 && (
          <span className="inline-flex items-center rounded-full border border-primary-200 bg-primary-50 px-2 py-0.5 text-tiny text-primary-700">
            {selectedRowCount} seleccionados
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={goToPreviousPage}
          disabled={safeExtractPage === 1}
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors duration-200 hover:border-gray-300 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft size={13} />
          Anterior
        </button>
        <button
          onClick={goToNextPage}
          disabled={safeExtractPage === extractTotalPages}
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors duration-200 hover:border-gray-300 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Siguiente
          <ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}
