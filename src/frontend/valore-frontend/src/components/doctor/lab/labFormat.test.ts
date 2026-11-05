import { describe, expect, it } from 'vitest';
import { formatMetric, formatRequiredCash } from './labFormat';

const normalize = (text: string) => text.replace(/[\u00A0\u202F]/g, ' ');

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

describe('formatMetric', () => {
  const m = (code: string, value: number | null, lower: number | null, upper: number | null) => ({
    code, value, lower, upper, unit: 'pct', coverage_pct: 80, quality: 'partial' as const,
  });

  it('shows «tra X% e Y%» (not the point value) when the bounds differ', () => {
    expect(formatMetric(m('usa_exposure_pct', 45.1, 40.9, 50.3))).toBe('tra 40,9% e 50,3%');
    expect(formatMetric(m('equity_weight_pct', 51.4, 46.6, 56.0))).toBe('tra 46,6% e 56,0%');
  });

  it('shows the point value when the bounds are absent or equal at the shown precision', () => {
    expect(formatMetric(m('usa_exposure_pct', 45.1, null, null))).toBe('45,1%');
    expect(formatMetric(m('usa_exposure_pct', 45.1, 45.08, 45.12))).toBe('45,1%');
    expect(formatMetric(m('usa_exposure_pct', null, 30, 30))).toBe('30,0%');
    expect(formatMetric(m('usa_exposure_pct', null, null, null))).toBe('N/D');
  });
});
