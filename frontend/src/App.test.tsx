// @vitest-environment happy-dom

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import type { CFDIData } from './cfdi/public';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const impactedConcept = {
  descripcion: 'Concepto impactado de prueba',
  cantidad: 1,
  valorUnitario: 100,
  importe: 100,
  importeCalculado: 100,
  diferencia: 0,
  claveProdServ: '10101504',
  impuestos: [],
};

const cfdi: CFDIData = {
  version: '4.0',
  fecha: '2026-03-26T10:00:00',
  uuid: 'APP-TEST-UUID',
  emisor: 'EMISOR SA DE CV',
  receptor: 'RECEPTOR SA DE CV',
  subtotal: 100,
  descuento: 0,
  total: 116,
  conceptos: [impactedConcept],
  impuestosGlobales: [],
  subtotalCalculado: 100,
  totalCalculado: 116,
  hallazgos: [],
  findings: [
    {
      id: 'concept-0',
      severity: 'critical',
      title: 'Importe inconsistente en concepto 1',
      summary: 'Concepto impactado de prueba: XML 100.00 vs cálculo 100.01.',
    },
  ],
  impactedConceptIndexes: [0],
  taxAuditGroups: [],
  verdict: {
    status: 'review',
    title: 'Con revision',
    summary: 'Resumen',
  },
  supportText: '',
};

function renderApp() {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  act(() => {
    root.render(<App />);
  });

  return {
    container,
    rerender: () => {
      act(() => {
        root.render(<App />);
      });
    },
  };
}

vi.mock('./app/hooks/useCfdiAnalysis', () => ({
  useCfdiAnalysis: () => ({
    profile: 'ingresos',
    cfdi,
    ingresoRows: [],
    pagoRows: [],
    analysisEngine: 'idle',
    analysisReason: '',
    analysisStageLabel: 'Analizando',
    analysisStageProgress: 100,
    analysisStageDetail: '',
    handleFileSelect: vi.fn(),
    resetAnalysis: vi.fn(),
  }),
}));

vi.mock('./app/hooks/useCfdiExports', () => ({
  useCfdiExports: () => ({
    reportExported: false,
    taxesExported: false,
    ingresosExported: false,
    pagosExported: false,
    pagosExportError: false,
    tableExported: false,
    tableExportError: false,
    exportReport: vi.fn(),
    exportTaxBreakdown: vi.fn(),
    exportIngresosCsv: vi.fn(),
    exportPagosCsv: vi.fn(),
    exportCurrentTable: vi.fn(),
  }),
}));

vi.mock('./app/hooks/useExtractGridState', () => ({
  useExtractGridState: () => ({
    extractGrid: {
      extractColumns: [],
      activeHiddenColumns: [],
      columnFilters: [],
      extractColumnFilterKey: 'all',
      extractSearchTerm: '',
      sorting: [],
      extractPageSize: 100,
      filteredExtractCount: 0,
      totalExtractCount: 0,
      safeExtractPage: 1,
      extractTotalPages: 1,
      extractPageStart: 0,
      selectedRowCount: 0,
      table: {} as never,
      setColumnFilterKey: vi.fn(),
      setColumnFilterValue: vi.fn(),
      setSearchTerm: vi.fn(),
      setPageSize: vi.fn(),
      resetGrid: vi.fn(),
      toggleColumn: vi.fn(),
      moveColumn: vi.fn(),
      toggleAllPageRowsSelected: vi.fn(),
      goToPreviousPage: vi.fn(),
      goToNextPage: vi.fn(),
    },
    extractSearchTerm: '',
    filteredExtractRows: [],
    resetForNewAnalysis: vi.fn(),
    resetAll: vi.fn(),
  }),
}));

vi.mock('./app/view-models/cfdiViewModels', () => ({
  buildExtractMetrics: () => [],
  buildSummaryFields: () => [],
  getProfileLabel: () => 'Ingresos',
}));

vi.mock('./cfdi/domain/explainCfdiField', () => ({
  explainCfdiField: () => ({ meaning: 'explicacion' }),
}));

vi.mock('./components/InspectorHeader', () => ({
  default: () => <div>InspectorHeader</div>,
}));

vi.mock('./components/CfdiSummaryHeader', () => ({
  default: () => <div>CfdiSummaryHeader</div>,
}));

vi.mock('./components/TaxAuditPanel', () => ({
  default: () => <div>TaxAuditPanel</div>,
}));

vi.mock('./components/ExtractWorkspace', () => ({
  default: () => <div>ExtractWorkspace</div>,
}));

vi.mock('./components/FileUpload', () => ({
  default: () => <div>FileUpload</div>,
}));

vi.mock('./components/FindingsSidebar', () => ({
  default: ({ findingContexts, onSelectConcept }: { findingContexts: Array<{ conceptLinks: Array<{ concept: typeof impactedConcept }> }>; onSelectConcept: (concept: typeof impactedConcept) => void }) => (
    <button type="button" onClick={() => onSelectConcept(findingContexts[0].conceptLinks[0].concept)}>
      Abrir concepto impactado
    </button>
  ),
}));

vi.mock('./components/ConceptDetailModal', () => ({
  default: ({ selectedConcept }: { selectedConcept: typeof impactedConcept | null }) => (
    selectedConcept ? <div>Modal abierto: {selectedConcept.descripcion}</div> : null
  ),
}));

describe('App integration', () => {
  it('opens concept detail when the sidebar selects an impacted concept', () => {
    const rendered = renderApp();

    expect(rendered.container.textContent).not.toContain('Modal abierto: Concepto impactado de prueba');

    const trigger = Array.from(rendered.container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Abrir concepto impactado'),
    );

    expect(trigger).toBeTruthy();

    act(() => {
      trigger?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(rendered.container.textContent).toContain('Modal abierto: Concepto impactado de prueba');
  });
});
