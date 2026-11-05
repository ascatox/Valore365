import { describe, expect, it } from 'vitest';
import { benchmarkOptionLabel, benchmarkShortLabel } from './benchmarkLabels';

describe('benchmark labels', () => {
  it('uses the index name with the ETF symbol in the selector', () => {
    expect(benchmarkOptionLabel({ symbol: 'SPY', label: 'S&P 500' })).toBe('S&P 500 (SPY)');
    expect(benchmarkOptionLabel({ symbol: 'EXSA.DE', label: 'STOXX Europe 600' })).toBe('STOXX Europe 600 (EXSA.DE)');
  });

  it('uses the index name alone for the chart title and badges', () => {
    expect(benchmarkShortLabel({ symbol: 'QQQ', label: 'Nasdaq 100' })).toBe('Nasdaq 100');
  });

  it('falls back to the symbol when the backend sends no label', () => {
    expect(benchmarkOptionLabel({ symbol: 'SPY' })).toBe('SPY');
    expect(benchmarkOptionLabel({ symbol: 'SPY', label: '  ' })).toBe('SPY');
    expect(benchmarkShortLabel({ symbol: 'SPY', label: null })).toBe('SPY');
  });
});
