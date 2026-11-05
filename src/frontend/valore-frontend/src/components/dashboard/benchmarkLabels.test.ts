import { describe, expect, it } from 'vitest';
import { benchmarkShortLabel } from './benchmarkLabels';

describe('benchmark labels', () => {
  it('uses the index name alone, without the ETF ticker', () => {
    expect(benchmarkShortLabel({ symbol: 'QQQ', label: 'Nasdaq 100' })).toBe('Nasdaq 100');
    expect(benchmarkShortLabel({ symbol: 'SPY', label: 'S&P 500' })).toBe('S&P 500');
    expect(benchmarkShortLabel({ symbol: 'EXSA.DE', label: 'STOXX Europe 600' })).toBe('STOXX Europe 600');
  });

  it('falls back to the symbol when the backend sends no label', () => {
    expect(benchmarkShortLabel({ symbol: 'SPY' })).toBe('SPY');
    expect(benchmarkShortLabel({ symbol: 'SPY', label: '  ' })).toBe('SPY');
    expect(benchmarkShortLabel({ symbol: 'SPY', label: null })).toBe('SPY');
  });
});
