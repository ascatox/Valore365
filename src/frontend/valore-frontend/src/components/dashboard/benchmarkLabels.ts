import type { BenchmarkItem } from '../../services/api/types';

type BenchmarkLike = Pick<BenchmarkItem, 'symbol'> & { label?: string | null };

/** Short name used in the chart title, legend, tooltip and badge (e.g. "S&P 500"). */
export function benchmarkShortLabel(b: BenchmarkLike): string {
  const label = b.label?.trim();
  return label || b.symbol;
}

/** Selector option: index name plus the tracking ETF (e.g. "S&P 500 (SPY)"). */
export function benchmarkOptionLabel(b: BenchmarkLike): string {
  const label = b.label?.trim();
  return label && label !== b.symbol ? `${label} (${b.symbol})` : b.symbol;
}
