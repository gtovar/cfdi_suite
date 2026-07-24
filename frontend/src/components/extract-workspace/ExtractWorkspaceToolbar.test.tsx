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
  // Actualizado 2026-07-23: el commit bd40ab3 ("rediseño inspector-ingreso
  // con lenguaje visual Tailux") simplificó esta fila de estado a propósito
  // ("chips de debug → estado inteligente") -- el alcance de búsqueda
  // ("en Descripcion") y el contador de filtros de columna se quitaron sin
  // reemplazo, y el contador de seleccionados se movió a
  // ExtractWorkspacePagination.tsx (ver su propio test). Estas pruebas
  // quedaron sin actualizar desde entonces (documentado como "preexistente"
  // en PROJECT_STATE.md sin investigar cuál de los dos -- test o componente
  // -- estaba desalineado; confirmado ahora con `git log -p` que fue el
  // test el que no siguió al rediseño intencional).
  it('renders the search term chip and filtered row summary in the status area', () => {
    const { container } = renderReact(<ExtractWorkspaceToolbar grid={createGrid()} />);

    expect(container.textContent).toContain('“servicio”');
    expect(container.textContent).toContain('3 de 12 registros');
    expect(container.textContent).toContain('1 orden');
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

    expect(container.textContent).not.toContain('“servicio”');
    expect(container.textContent).toContain('12 de 12 registros');
    expect(container.textContent).toContain('1 orden');
  });
});
