// @vitest-environment happy-dom

import { afterEach, describe, expect, it } from 'vitest';
import BatchCompletionModal, { resolveCompletionStatus } from './BatchCompletionModal';
import { renderReact } from '../test/renderReact';

// ── resolveCompletionStatus (función pura) ────────────────────────────────────

describe('resolveCompletionStatus', () => {
  it('0 problemáticos → ¡Lote impecable! en verde', () => {
    const { headline, headlineColor } = resolveCompletionStatus(0, 100);
    expect(headline).toBe('¡Lote impecable!');
    expect(headlineColor).toContain('green');
  });

  it('1% → Casi perfecto en verde', () => {
    const { headline, headlineColor } = resolveCompletionStatus(1, 100);
    expect(headline).toBe('Casi perfecto');
    expect(headlineColor).toContain('green');
  });

  it('10% → ¡Lote completado! en gris', () => {
    const { headline, headlineColor } = resolveCompletionStatus(10, 100);
    expect(headline).toBe('¡Lote completado!');
    expect(headlineColor).toContain('gray');
  });

  it('30% → Revisión requerida en amarillo', () => {
    const { headline, headlineColor } = resolveCompletionStatus(30, 100);
    expect(headline).toBe('Revisión requerida');
    expect(headlineColor).toContain('yellow');
  });

  it('totalFiles 0 no lanza error de división', () => {
    expect(() => resolveCompletionStatus(0, 0)).not.toThrow();
    const { headline } = resolveCompletionStatus(0, 0);
    expect(headline).toBe('¡Lote impecable!');
  });

  it('icono verde cuando < 25% de errores', () => {
    const { iconBg, iconColor } = resolveCompletionStatus(24, 100);
    expect(iconBg).toContain('green');
    expect(iconColor).toContain('green');
  });

  it('icono amarillo cuando ≥ 25% de errores', () => {
    const { iconBg, iconColor } = resolveCompletionStatus(25, 100);
    expect(iconBg).toContain('yellow');
    expect(iconColor).toContain('yellow');
  });

  it('icono amarillo cuando hay errores pero totalFiles es 0 (pct=0 no debe forzar verde)', () => {
    const { iconColor } = resolveCompletionStatus(1, 0);
    expect(iconColor).toContain('yellow');
  });
});

// ── BatchCompletionModal (render) ─────────────────────────────────────────────

const BASE_PROPS = {
  totalFiles: 100,
  ok: 100,
  conErrores: 0,
  errors: 0,
  totalMonto: 0,
  elapsedSeconds: 5,
  topEmisor: null,
  topMonth: null,
  monthBreakdown: [] as Array<{ month: string; count: number; monto: number }>,
  onViewTriage: () => {},
  onClose: () => {},
};

describe('BatchCompletionModal render', () => {
  let container: HTMLDivElement;

  afterEach(() => {
    container?.remove();
  });

  it('muestra headline ¡Lote impecable! cuando no hay errores', () => {
    ({ container } = renderReact(<BatchCompletionModal {...BASE_PROPS} />));
    expect(container.textContent).toContain('¡Lote impecable!');
  });

  it('muestra headline Revisión requerida cuando ≥ 25% errores', () => {
    ({ container } = renderReact(
      <BatchCompletionModal {...BASE_PROPS} ok={70} conErrores={20} errors={10} />,
    ));
    expect(container.textContent).toContain('Revisión requerida');
  });

  it('muestra sección Por mes cuando monthBreakdown tiene datos', () => {
    const breakdown = [{ month: '2026-01', count: 50, monto: 5000 }];
    ({ container } = renderReact(
      <BatchCompletionModal {...BASE_PROPS} monthBreakdown={breakdown} />,
    ));
    expect(container.textContent).toContain('Por mes');
  });

  it('NO muestra sección Por mes cuando monthBreakdown está vacío', () => {
    ({ container } = renderReact(<BatchCompletionModal {...BASE_PROPS} monthBreakdown={[]} />));
    expect(container.textContent).not.toContain('Por mes');
  });

  it('muestra facts/seg cuando elapsedSeconds > 0', () => {
    ({ container } = renderReact(
      <BatchCompletionModal {...BASE_PROPS} totalFiles={100} elapsedSeconds={10} />,
    ));
    expect(container.textContent).toContain('facts/seg');
  });

  it('NO muestra facts/seg cuando elapsedSeconds es 0', () => {
    ({ container } = renderReact(
      <BatchCompletionModal {...BASE_PROPS} elapsedSeconds={0} />,
    ));
    expect(container.textContent).not.toContain('facts/seg');
  });
});
