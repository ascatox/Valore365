import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { refreshPortfolioPrices, backfillPortfolioDailyPrices } from '../../../services/api';
import { prefetchMarketData } from './queries';
import { scopeKeyCoversAny } from './invalidation';
import { scopePortfolioIds, toPortfolioScope, type PortfolioScopeInput } from '../../../scope/portfolioScope';

// Queries whose data depends on prices. Static lists (portfolios, benchmark
// catalogue) are left out: a price refresh doesn't change them.
const DASHBOARD_QUERY_PREFIXES = new Set([
  'portfolio-summary',
  'portfolio-positions',
  'portfolio-performers',
  'portfolio-allocation',
  'portfolio-timeseries',
  'portfolio-data-coverage',
  'portfolio-health',
  'portfolio-xray',
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
  'benchmark-prices',
  'market-quotes',
  'market-news',
]);

/**
 * Whether a query must be refreshed after the prices of `portfolioIds` were
 * downloaded: a price-dependent prefix whose key has no portfolio (market
 * data, per-portfolio hooks disabled in aggregate) or covers one of them,
 * single entry or aggregate (see `portfolioScopeKeyIncludes`).
 */
export function matchesRefreshedPortfolios(queryKey: readonly unknown[], portfolioIds: readonly number[]): boolean {
  const [prefix, keySegment] = queryKey as [string | undefined, unknown];
  if (!prefix || !DASHBOARD_QUERY_PREFIXES.has(prefix)) return false;
  if (keySegment == null) return true;
  return scopeKeyCoversAny(keySegment, portfolioIds);
}

/**
 * Price refresh for the Dashboard scope. With an aggregate scope the prices
 * of every portfolio of the aggregate are refreshed (one at a time) and the
 * aggregate queries are invalidated with the single ones.
 */
export function useDashboardRefresh(portfolio: PortfolioScopeInput) {
  const scopeIdsKey = scopePortfolioIds(toPortfolioScope(portfolio)).join(',');
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  // The refresh button, pull-to-refresh and auto-refresh all fire the same
  // event, and each run downloads every asset's prices: one run at a time.
  const inFlightRef = useRef(false);

  const doRefresh = useCallback(async () => {
    const portfolioIds = scopeIdsKey ? scopeIdsKey.split(',').map(Number) : [];
    if (!portfolioIds.length) {
      setRefreshMessage('Seleziona un portfolio prima di aggiornare');
      return;
    }
    if (inFlightRef.current) return;
    inFlightRef.current = true;

    setRefreshError(null);
    setRefreshMessage(null);
    setRefreshing(true);

    try {
      const totals = { refreshed: 0, requested: 0, backfilled: 0, backfillRequested: 0 };
      for (const portfolioId of portfolioIds) {
        const refreshResult = await refreshPortfolioPrices(portfolioId, 'all');
        const backfillResult = await backfillPortfolioDailyPrices(portfolioId, 365, 'all');
        totals.refreshed += refreshResult.refreshed_assets;
        totals.requested += refreshResult.requested_assets;
        totals.backfilled += backfillResult.assets_refreshed;
        totals.backfillRequested += backfillResult.assets_requested;
      }

      const matchesPortfolio = (query: { queryKey: readonly unknown[] }) => (
        matchesRefreshedPortfolios(query.queryKey, portfolioIds)
      );

      // invalidateQueries refetches active queries once and marks the others
      // stale. resetQueries + refetchQueries fetched every active query twice.
      await queryClient.invalidateQueries({ predicate: matchesPortfolio, refetchType: 'active' });
      // Mercati is usually not the open tab, so its invalidated quotes and
      // news would wait for the tab to open: reload them now, in background.
      void prefetchMarketData(queryClient);

      setRefreshVersion((current) => current + 1);
      setRefreshMessage(
        `Aggiornati prezzi: ${totals.refreshed}/${totals.requested}, storico: ${totals.backfilled}/${totals.backfillRequested}`,
      );
    } catch (err) {
      setRefreshError(err instanceof Error ? err.message : 'Errore durante aggiornamento prezzi');
    } finally {
      inFlightRef.current = false;
      setRefreshing(false);
    }
  }, [scopeIdsKey, queryClient]);

  useEffect(() => {
    const onRefresh = () => { doRefresh(); };
    window.addEventListener('valore365:refresh-dashboard', onRefresh);
    return () => { window.removeEventListener('valore365:refresh-dashboard', onRefresh); };
  }, [doRefresh]);

  // Lets the app header show progress without a status line in the page.
  useEffect(() => {
    if (!refreshing) return;
    window.dispatchEvent(new CustomEvent('valore365:refresh-state', { detail: true }));
    return () => { window.dispatchEvent(new CustomEvent('valore365:refresh-state', { detail: false })); };
  }, [refreshing]);

  useEffect(() => {
    if (!refreshMessage) return;
    const timer = window.setTimeout(() => setRefreshMessage(null), 5000);
    return () => window.clearTimeout(timer);
  }, [refreshMessage]);

  const handleRefresh = useCallback(() => {
    window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard'));
  }, []);

  return { refreshing, refreshMessage, refreshError, refreshVersion, handleRefresh };
}
