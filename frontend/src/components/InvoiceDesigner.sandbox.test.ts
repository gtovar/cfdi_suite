import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

describe('InvoiceDesigner sandbox safety', () => {
  it('no debe tener allow-scripts en ningún sandbox de iframe', () => {
    const src = readFileSync(resolve(__dirname, 'InvoiceDesigner.jsx'), 'utf-8');
    const matches = src.match(/sandbox="([^"]*)"/g);
    expect(matches).not.toBeNull();
    for (const m of matches!) {
      expect(m).not.toMatch(/allow-scripts/);
    }
  });
});
