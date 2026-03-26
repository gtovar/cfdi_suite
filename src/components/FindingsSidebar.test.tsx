// @vitest-environment happy-dom

import { act } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import FindingsSidebar from './FindingsSidebar';
import type { FindingContext } from './FindingsSidebar';
import type { CFDIData } from '../cfdi/public';
import { renderReact } from '../test/renderReact';

function createCfdi(overrides: Partial<CFDIData> = {}): CFDIData {
  return {
    version: '4.0',
    fecha: '2026-03-26T10:00:00',
    uuid: 'TEST-UUID-1',
    emisor: 'EMISOR SA DE CV',
    receptor: 'RECEPTOR SA DE CV',
    subtotal: 100,
    descuento: 0,
    total: 116,
    conceptos: [],
    impuestosGlobales: [],
    subtotalCalculado: 100,
    totalCalculado: 116,
    hallazgos: [],
    findings: [
      { id: 'math-1', severity: 'critical', title: 'Hallazgo 1', summary: 'Resumen 1' },
      { id: 'math-2', severity: 'critical', title: 'Hallazgo 2', summary: 'Resumen 2' },
      { id: 'math-3', severity: 'warning', title: 'Hallazgo 3', summary: 'Resumen 3' },
      { id: 'math-4', severity: 'warning', title: 'Hallazgo 4', summary: 'Resumen 4' },
      { id: 'math-5', severity: 'warning', title: 'Hallazgo 5', summary: 'Resumen 5' },
      { id: 'math-6', severity: 'warning', title: 'Hallazgo 6', summary: 'Resumen 6' },
    ],
    impactedConceptIndexes: [],
    taxAuditGroups: [],
    verdict: {
      status: 'review',
      title: 'Con revision',
      summary: 'Resumen',
    },
    supportText: '',
    ...overrides,
  };
}

function findButtonByText(container: HTMLElement, text: string) {
  return Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes(text));
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('FindingsSidebar', () => {
  const emptyFindingContexts: FindingContext[] = [];

  it('shows a compact default list with a hidden findings summary', () => {
    const { container } = renderReact(
      <FindingsSidebar
        cfdi={createCfdi()}
        findingContexts={emptyFindingContexts}
        activeDatasetType="ingresos"
        activeExtractMetrics={[]}
        subtotalDifference={0}
        totalDifference={0}
        formatExact={(value) => String(value)}
        getFindingOriginLabel={() => 'Matematico'}
        onSelectConcept={() => {}}
      />,
    );

    expect(container.textContent).toContain('Hallazgo 1');
    expect(container.textContent).toContain('Hallazgo 4');
    expect(container.textContent).not.toContain('Hallazgo 5');
    expect(container.textContent).toContain('2 hallazgos ocultos');
    expect(findButtonByText(container, 'Ver todos')).toBeTruthy();
  });

  it('expands the full list and resets to compact mode when the CFDI changes', () => {
    const initialCfdi = createCfdi();
    const rendered = renderReact(
      <FindingsSidebar
        cfdi={initialCfdi}
        findingContexts={emptyFindingContexts}
        activeDatasetType="ingresos"
        activeExtractMetrics={[]}
        subtotalDifference={0}
        totalDifference={0}
        formatExact={(value) => String(value)}
        getFindingOriginLabel={() => 'Matematico'}
        onSelectConcept={() => {}}
      />,
    );

    const expandButton = findButtonByText(rendered.container, 'Ver todos');
    expect(expandButton).toBeTruthy();

    act(() => {
      expandButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(rendered.container.textContent).toContain('Hallazgo 5');
    expect(rendered.container.textContent).toContain('Hallazgo 6');
    expect(rendered.container.textContent).toContain('Lista completa visible');

    rendered.rerender(
      <FindingsSidebar
        cfdi={createCfdi({ uuid: 'TEST-UUID-2' })}
        findingContexts={emptyFindingContexts}
        activeDatasetType="ingresos"
        activeExtractMetrics={[]}
        subtotalDifference={0}
        totalDifference={0}
        formatExact={(value) => String(value)}
        getFindingOriginLabel={() => 'Matematico'}
        onSelectConcept={() => {}}
      />,
    );

    expect(rendered.container.textContent).not.toContain('Hallazgo 5');
    expect(rendered.container.textContent).toContain('2 hallazgos ocultos');
    expect(findButtonByText(rendered.container, 'Ver todos')).toBeTruthy();
  });
});
