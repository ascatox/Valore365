import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { refreshPortfolioPrices, backfillPortfolioDailyPrices } from '../../../services/api';
import { prefetchMarketData } from './queries';

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

export function useDashboardRefresh(portfolioId: number | null) {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  // The refresh button, pull-to-refresh and auto-refresh all fire the same
  // event, and each run downloads every asset's prices: one run at a time.
  const inFlightRef = useRef(false);

  const doRefresh = useCallback(async () => {
    if (!portfolioId || !Number.isFinite(portfolioId)) {
      setRefreshMessage('Seleziona un portfolio prima di aggiornare');
      return;
    }
    if (inFlightRef.current) return;
    inFlightRef.current = true;

    setRefreshError(null);
    setRefreshMessage(null);
    setRefreshing(true);

    try {
      const refreshResult = await refreshPortfolioPrices(portfolioId, 'all');
      const backfillResult = await backfillPortfolioDailyPrices(portfolioId, 365, 'all');

      const matchesPortfolio = (query: { queryKey: readonly unknown[] }) => {
        const [prefix, queryPortfolioId] = query.queryKey as [string | undefined, unknown];
        if (!prefix || !DASHBOARD_QUERY_PREFIXES.has(prefix)) return false;
        if (queryPortfolioId == null) return true;
        return queryPortfolioId === portfolioId;
      };

      // invalidateQueries refetches active queries once and marks the others
      // stale. resetQueries + refetchQueries fetched every active query twice.
      await queryClient.invalidateQueries({ predicate: matchesPortfolio, refetchType: 'active' });
      // Mercati is usually not the open tab, so its invalidated quotes and
      // news would wait for the tab to open: reload them now, in background.
      void prefetchMarketData(queryClient);

      setRefreshVersion((current) => current + 1);
      setRefreshMessage(
        `Aggiornati prezzi: ${refreshResult.refreshed_assets}/${refreshResult.requested_assets}, storico: ${backfillResult.assets_refreshed}/${backfillResult.assets_requested}`,
      );
    } catch (err) {
      setRefreshError(err instanceof Error ? err.message : 'Errore durante aggiornamento prezzi');
    } finally {
      inFlightRef.current = false;
      setRefreshing(false);
    }
  }, [portfolioId, queryClient]);

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
