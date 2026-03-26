// @vitest-environment happy-dom

import { act, type ReactElement } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';
import FindingsSidebar from './FindingsSidebar';
import type { FindingContext } from './FindingsSidebar';
import type { CFDIConcept, CFDIData } from '../cfdi/public';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

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
    findings: [],
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

function createImpactedConcept(overrides: Partial<CFDIConcept> = {}): CFDIConcept {
  return {
    descripcion: 'Servicio impactado',
    cantidad: 1,
    valorUnitario: 100,
    importe: 100,
    importeCalculado: 100,
    diferencia: 0,
    claveProdServ: '10101504',
    impuestos: [],
    ...overrides,
  };
}

function findButtonByText(container: HTMLElement, text: string) {
  return Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes(text));
}

function renderSidebar(element: ReactElement) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  act(() => {
    root.render(element);
  });

  return { container, root };
}

describe('FindingsSidebar impacted concepts', () => {
  it('renders impacted concepts and delegates selection through the callback', () => {
    const selected: string[] = [];
    const findingContexts: FindingContext[] = [
      {
        findingId: 'tax-group-002|Tasa|0.16',
        explanation: 'Compara el detalle por concepto contra el agrupado del comprobante.',
        relationshipLabel: '5 concepto(s) en el grupo 002 16.00%',
        differenceLabel: 'Dif. real +0.02',
        conceptLinks: [
          { concept: createImpactedConcept({ descripcion: 'Concepto A' }), conceptIndex: 0, reason: 'Participa en el grupo fiscal 002 16.00%.' },
          { concept: createImpactedConcept({ descripcion: 'Concepto B' }), conceptIndex: 1, reason: 'Participa en el grupo fiscal 002 16.00%.' },
          { concept: createImpactedConcept({ descripcion: 'Concepto C' }), conceptIndex: 2, reason: 'Participa en el grupo fiscal 002 16.00%.' },
          { concept: createImpactedConcept({ descripcion: 'Concepto D' }), conceptIndex: 3, reason: 'Participa en el grupo fiscal 002 16.00%.' },
          { concept: createImpactedConcept({ descripcion: 'Concepto E' }), conceptIndex: 4, reason: 'Participa en el grupo fiscal 002 16.00%.' },
        ],
      },
    ];
    const { container } = renderSidebar(
      <FindingsSidebar
        cfdi={createCfdi({
          findings: [
            {
              id: 'tax-group-002|Tasa|0.16',
              severity: 'critical',
              title: 'Diferencia en traslado 002 16.00%',
              summary: 'Detalle 100.00 vs agrupado 100.02.',
            },
          ],
        })}
        findingContexts={findingContexts}
        activeDatasetType="ingresos"
        activeExtractMetrics={[]}
        subtotalDifference={0}
        totalDifference={0}
        formatExact={(value) => String(value)}
        getFindingOriginLabel={() => 'Matematico'}
        onSelectConcept={(concept) => selected.push(concept.descripcion ?? '')}
      />,
    );

    expect(container.textContent).toContain('Hallazgo enfocado');
    expect(container.textContent).toContain('Conceptos relacionados');
    expect(container.textContent).toContain('Relacionados con: Diferencia en traslado 002 16.00%');
    expect(container.textContent).toContain('Concepto A');
    expect(container.textContent).toContain('Concepto D');
    expect(container.textContent).not.toContain('Concepto E');
    expect(container.textContent).toContain('1 conceptos adicionales relacionados no visibles');
    expect(container.textContent).toContain('Participa en el grupo fiscal 002 16.00%.');

    const conceptButton = findButtonByText(container, 'Concepto B');
    expect(conceptButton).toBeTruthy();

    act(() => {
      conceptButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(selected).toEqual(['Concepto B']);
  });
});
