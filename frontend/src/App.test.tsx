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

// App.tsx es hoy una app multi-página (Consultas SAT / Análisis masivo /
// Conversión masiva / Cancelaciones); activeView inicia en 'masivo' y solo
// pasa a 'inspector' (la vista que este test necesita, con FindingsSidebar)
// vía el drill-down real de BatchAnalysisPage.onSelectFile. Se mockea aquí
// con el mismo patrón que el resto de componentes de este archivo -- un
// botón simple que dispara ese callback -- para no tener que simular una
// subida de archivo real dentro del componente completo de Análisis masivo.
vi.mock('./components/BatchAnalysisPage', () => ({
  default: ({ onSelectFile }: { onSelectFile?: (file: File) => void }) => (
    <button type="button" onClick={() => onSelectFile?.(new File(['<xml/>'], 'test.xml'))}>
      Abrir detalle de archivo
    </button>
  ),
}));

// FindingsSidebar selecciona un FINDING (por id), no un concepto directo --
// eso pasa un nivel más adentro, en ResolutionPanel (ver su mock abajo).
vi.mock('./components/FindingsSidebar', () => ({
  default: ({ onSelectFinding }: { onSelectFinding: (findingId: string) => void }) => (
    <button type="button" onClick={() => onSelectFinding('concept-0')}>
      Abrir hallazgo
    </button>
  ),
}));

// El fixture `cfdi.findings[0].id === 'concept-0'` coincide a propósito con
// la rama real de useFindingContexts (finding.id.startsWith('concept-')),
// SIN mockear ese hook -- así ResolutionPanel sí se renderiza (requiere
// selectedFindingContext.correctionSteps truthy) con datos reales, y solo
// se mockea la selección de concepto dentro de él.
vi.mock('./components/ResolutionPanel', () => ({
  default: ({ onSelectConcept }: { onSelectConcept: (concept: typeof impactedConcept) => void }) => (
    <button type="button" onClick={() => onSelectConcept(impactedConcept)}>
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

    // activeView inicia en 'masivo' -- primero hay que hacer drill-down a un
    // archivo (como en producción) para llegar a la vista de inspector.
    const openInspector = Array.from(rendered.container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Abrir detalle de archivo'),
    );
    expect(openInspector).toBeTruthy();
    act(() => {
      openInspector?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(rendered.container.textContent).not.toContain('Modal abierto: Concepto impactado de prueba');

    // Paso 1: seleccionar el finding en FindingsSidebar (activa ResolutionPanel).
    const openFinding = Array.from(rendered.container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Abrir hallazgo'),
    );
    expect(openFinding).toBeTruthy();
    act(() => {
      openFinding?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    // Paso 2: dentro de ResolutionPanel, seleccionar el concepto impactado.
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
