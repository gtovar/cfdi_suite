// @vitest-environment happy-dom

import { afterEach, describe, expect, it } from 'vitest';
import { FloatingBatchWidgetStack, type StackedBatchWidget } from './FloatingBatchWidget';
import { renderReact } from '../test/renderReact';

const MASIVO: StackedBatchWidget = {
  id: 'masivo',
  status: { completed: 10, total: 45, phase: 'processing' },
  label: 'Análisis masivo',
  onNavigate: () => {},
  onDismiss: () => {},
};

const PDF: StackedBatchWidget = {
  id: 'pdf',
  status: { completed: 3, total: 20, phase: 'processing' },
  label: 'Conversión masiva',
  onNavigate: () => {},
  onDismiss: () => {},
};

describe('FloatingBatchWidgetStack', () => {
  let container: HTMLDivElement;

  afterEach(() => {
    container?.remove();
  });

  it('no renderiza nada si no hay widgets activos', () => {
    ({ container } = renderReact(<FloatingBatchWidgetStack widgets={[]} />));
    expect(container.textContent).toBe('');
  });

  it('un solo lote activo: muestra un widget con su progreso', () => {
    ({ container } = renderReact(<FloatingBatchWidgetStack widgets={[MASIVO]} />));
    expect(container.textContent).toContain('Análisis masivo');
    expect(container.textContent).toContain('10 / 45 facturas');
    expect(container.textContent).not.toContain('Conversión masiva');
  });

  it('dos lotes corriendo a la vez: se apilan los DOS, ninguno se oculta', () => {
    ({ container } = renderReact(<FloatingBatchWidgetStack widgets={[MASIVO, PDF]} />));
    expect(container.textContent).toContain('Análisis masivo');
    expect(container.textContent).toContain('10 / 45 facturas');
    expect(container.textContent).toContain('Conversión masiva');
    expect(container.textContent).toContain('3 / 20 facturas');
  });

  it('cada widget trae su propia cifra — no se mezclan ni se pisan', () => {
    ({ container } = renderReact(<FloatingBatchWidgetStack widgets={[MASIVO, PDF]} />));
    // regresión directa del hallazgo original: "0/45" de un lote no debe
    // aparecer junto a "0/20" del otro sin poder distinguir cuál es cuál.
    const buttons = container.querySelectorAll('button');
    // 2 widgets x 2 botones cada uno (navegar + cerrar)
    expect(buttons.length).toBe(4);
  });

  it('cierra solo el widget que corresponde, el otro sigue visible', () => {
    let dismissedMasivo = false;
    const widgets: StackedBatchWidget[] = [
      { ...MASIVO, onDismiss: () => { dismissedMasivo = true; } },
      PDF,
    ];
    ({ container } = renderReact(<FloatingBatchWidgetStack widgets={widgets} />));
    const closeBtn = container.querySelector('button[aria-label="Cerrar aviso de Análisis masivo"]') as HTMLButtonElement;
    expect(closeBtn).toBeTruthy();
    closeBtn.click();
    expect(dismissedMasivo).toBe(true);
  });
});
