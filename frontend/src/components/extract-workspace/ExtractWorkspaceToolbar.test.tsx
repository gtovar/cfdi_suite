// @vitest-environment happy-dom

import { afterEach, describe, expect, it, vi } from 'vitest';
import ExtractWorkspaceToolbar from './ExtractWorkspaceToolbar';
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
    columnFilters: [{ id: 'uuid', value: 'ABC' }],
    extractColumnFilterKey: 'descripcion',
    extractSearchTerm: 'servicio',
    sorting: [{ id: 'descripcion', desc: false }],
    extractPageSize: 100,
    filteredExtractCount: 3,
    totalExtractCount: 12,
    safeExtractPage: 1,
    extractTotalPages: 1,
    extractPageStart: 0,
    selectedRowCount: 2,
    table: {} as ExtractGridController['table'],
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

describe('ExtractWorkspaceToolbar', () => {
  it('renders the search scope and filtered row summary in the status area', () => {
    const { container } = renderReact(<ExtractWorkspaceToolbar grid={createGrid()} />);

    expect(container.textContent).toContain('"servicio" en Descripcion');
    expect(container.textContent).toContain('3 de 12 visibles');
    expect(container.textContent).toContain('1 filtros de columna');
    expect(container.textContent).toContain('2 seleccionados');
  });

  it('shows the no-search summary when the global search is empty', () => {
    const { container } = renderReact(
      <ExtractWorkspaceToolbar
        grid={createGrid({
          extractColumnFilterKey: 'all',
          extractSearchTerm: '',
          columnFilters: [],
          filteredExtractCount: 12,
          totalExtractCount: 12,
          selectedRowCount: 0,
        })}
      />,
    );

    expect(container.textContent).toContain('sin busqueda global (todas las columnas)');
    expect(container.textContent).toContain('12 de 12 visibles');
    expect(container.textContent).toContain('0 filtros de columna');
    expect(container.textContent).toContain('0 seleccionados');
  });
});
