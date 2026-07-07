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
  it('renders finding cards and shows resolution button for findings with concept links', () => {
    const selectedFindings: string[] = [];
    const findingContexts: FindingContext[] = [
      {
        findingId: 'tax-group-002|Tasa|0.16',
        explanation: 'Compara el detalle por concepto contra el agrupado del comprobante.',
        relationshipLabel: '5 concepto(s) en el grupo 002 16.00%',
        whyItMatters: 'Si este grupo no cuadra, el impuesto total del comprobante puede distribuirse mal.',
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
        getFindingOriginLabel={() => 'Matematico'}
        selectedFindingId={null}
        onSelectFinding={(id) => { if (id) selectedFindings.push(id); }}
      />,
    );

    // Finding card content is visible
    expect(container.textContent).toContain('Diferencia en traslado 002 16.00%');
    expect(container.textContent).toContain('Detalle 100.00 vs agrupado 100.02.');
    expect(container.textContent).toContain('5 concepto(s) en el grupo 002 16.00%');
    expect(container.textContent).toContain('Dif. real +0.02');

    // Resolution button present for finding with concept links
    const resolveButton = findButtonByText(container, 'Ver cómo resolver');
    expect(resolveButton).toBeTruthy();

    // Clicking it calls onSelectFinding with the finding id
    act(() => {
      resolveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(selectedFindings).toEqual(['tax-group-002|Tasa|0.16']);

    // Guía de revisión section is no longer in the sidebar (moved to ResolutionPanel)
    expect(container.textContent).not.toContain('Guía de revisión');
    expect(container.textContent).not.toContain('Abrir concepto sugerido');
  });
});
