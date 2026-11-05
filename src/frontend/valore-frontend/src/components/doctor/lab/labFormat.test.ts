import { describe, expect, it } from 'vitest';
import { formatRequiredCash } from './labFormat';

const normalize = (text: string) => text.replace(/[  ]/g, ' ');

describe('formatRequiredCash', () => {
  it('shows the PRD golden required capital as whole euros rounded up (227.028,58 → 227.029 €)', () => {
    expect(normalize(formatRequiredCash(227028.58, 'EUR', false))).toBe('227.029 €');
  });

  it('never understates a minimum and keeps exact whole amounts', () => {
    expect(normalize(formatRequiredCash(41000, 'EUR', false))).toBe('41.000 €');
    expect(normalize(formatRequiredCash(41000.01, 'EUR', false))).toBe('41.001 €');
  });

  it('masks in Privacy Mode and shows N/D without a value', () => {
    expect(formatRequiredCash(227028.58, 'EUR', true)).toBe('******');
    expect(formatRequiredCash(null, 'EUR', false)).toBe('N/D');
  });
});
