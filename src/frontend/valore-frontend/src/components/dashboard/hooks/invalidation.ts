import type { QueryClient } from '@tanstack/react-query';
import { portfolioScopeKeyIncludes } from '../../../scope/portfolioScope';

// Portfolio query keys are `[prefix, portfolioScopeKey(scope), ...]`: the bare
// id for a single portfolio, `'aggregate:1,2'` for an aggregate. A change to
// one portfolio makes stale both its own entries and every aggregate that
// includes it, so the predicates below match on `portfolioScopeKeyIncludes`
// instead of comparing `queryKey[1] === portfolioId`.

/** Every query prefix whose data belongs to a portfolio (or an aggregate of portfolios). */
export const PORTFOLIO_QUERY_PREFIXES = new Set([
  'portfolio-summary',
  'portfolio-positions',
  'portfolio-performers',
  'portfolio-allocation',
  'portfolio-timeseries',
  'portfolio-data-coverage',
  'portfolio-transactions',
  'portfolio-health',
  'portfolio-xray',
  'monte-carlo-projection',
  'stress-test',
  'decumulation-plan',
  'target-allocation',
  'target-performance',
  'target-asset-performance',
  'intraday-target-performance',
  'asset-intraday-target-performance',
  'portfolio-intraday-timeseries',
  'intraday-detail',
  'gain-timeseries',
  'performance-summary',
  'twr-timeseries',
  'mwr-timeseries',
  'monthly-returns',
  'yearly-returns',
  'portfolio-drawdown',
  'rolling-windows',
  'hall-of-fame',
]);

/** Whether a query key segment (see `portfolioScopeKey`) covers any of the portfolios. */
export function scopeKeyCoversAny(keySegment: unknown, portfolioIds: readonly number[]): boolean {
  return portfolioIds.some((portfolioId) => portfolioScopeKeyIncludes(keySegment, portfolioId));
}

/**
 * Mark stale (and refetch when on screen) every portfolio query of the given
 * portfolios: their single entries and the aggregates that include them.
 * Used after writes (transactions, imports) so the other pages do not keep
 * showing the old numbers for the 60s staleTime.
 */
export function invalidatePortfolioQueries(queryClient: QueryClient, portfolioIds: readonly number[]) {
  if (!portfolioIds.length) return Promise.resolve();
  return queryClient.invalidateQueries({
    predicate: (query) => {
      const [prefix, keySegment] = query.queryKey as [unknown, unknown];
      return typeof prefix === 'string'
        && PORTFOLIO_QUERY_PREFIXES.has(prefix)
        && scopeKeyCoversAny(keySegment, portfolioIds);
    },
  });
}
