// @vitest-environment happy-dom

import { afterEach, describe, expect, it, vi } from 'vitest';
import ExtractWorkspacePagination from './ExtractWorkspacePagination';
import type { ExtractGridController } from './types';
import { renderReact } from '../../test/renderReact';

const noop = () => {};

function createGrid(overrides: Partial<ExtractGridController> = {}): ExtractGridController {
  return {
    extractColumns: [
      { key: 'uuid', label: 'UUID' },
      { key: 'descripcion', label: 'Descripcion' },
    ],
    activeHiddenColumns: [],
    columnFilters: [],
    extractColumnFilterKey: 'all',
    extractSearchTerm: '',
    sorting: [],
    extractPageSize: 100,
    filteredExtractCount: 12,
    totalExtractCount: 12,
    safeExtractPage: 1,
    extractTotalPages: 1,
    extractPageStart: 0,
    selectedRowCount: 0,
    table: { getRowModel: () => ({ rows: new Array(12).fill(null) }) } as unknown as ExtractGridController['table'],
    setColumnFilterKey: vi.fn(),
    setColumnFilterValue: vi.fn(),
    setSearchTerm: vi.fn(),
    setPageSize: vi.fn(),
    resetGrid: vi.fn(),
    toggleColumn: noop,
    moveColumn: noop,
    toggleAllPageRowsSelected: noop,
    goToPreviousPage: noop,
    goToNextPage: noop,
    ...overrides,
  };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('ExtractWorkspacePagination', () => {
  // Cobertura nueva 2026-07-23: "N seleccionados" existe en producción
  // (movido aquí desde ExtractWorkspaceToolbar en el rediseño Tailux,
  // commit bd40ab3) pero no tenía ninguna prueba -- un cambio que lo
  // rompiera hubiera pasado desapercibido sin que nadie lo notara.
  it('muestra el contador de seleccionados cuando hay filas seleccionadas', () => {
    const { container } = renderReact(
      <ExtractWorkspacePagination grid={createGrid({ selectedRowCount: 2 })} />,
    );

    expect(container.textContent).toContain('2 seleccionados');
  });

  it('no muestra el contador de seleccionados cuando no hay ninguna fila seleccionada', () => {
    const { container } = renderReact(
      <ExtractWorkspacePagination grid={createGrid({ selectedRowCount: 0 })} />,
    );

    expect(container.textContent).not.toContain('seleccionados');
  });

  it('muestra el rango de filas visibles de la página actual', () => {
    const { container } = renderReact(
      <ExtractWorkspacePagination
        grid={createGrid({ filteredExtractCount: 12, extractPageStart: 0 })}
      />,
    );

    expect(container.textContent).toContain('1–12 de 12');
  });
});
