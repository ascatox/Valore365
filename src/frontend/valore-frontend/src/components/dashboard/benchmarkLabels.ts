import type { BenchmarkItem } from '../../services/api/types';

type BenchmarkLike = Pick<BenchmarkItem, 'symbol'> & { label?: string | null };

/** Index name used in the selector, chart title, legend, tooltip and badge (e.g. "S&P 500"). */
export function benchmarkShortLabel(b: BenchmarkLike): string {
  const label = b.label?.trim();
  return label || b.symbol;
}
