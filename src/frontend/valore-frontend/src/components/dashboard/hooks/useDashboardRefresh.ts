import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { refreshPortfolioPrices, backfillPortfolioDailyPrices } from '../../../services/api';

const DASHBOARD_QUERY_PREFIXES = new Set([
  'portfolio-summary',
  'portfolio-positions',
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
  'portfolio-drawdown',
  'rolling-windows',
  'hall-of-fame',
  'benchmark-prices',
  'benchmarks',
  'market-quotes',
  'market-news',
  'portfolios',
]);

export function useDashboardRefresh(portfolioId: number | null) {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);

  const doRefresh = useCallback(async () => {
    if (!portfolioId || !Number.isFinite(portfolioId)) {
      setRefreshMessage('Seleziona un portfolio prima di aggiornare');
      return;
    }

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

      await queryClient.resetQueries({ predicate: matchesPortfolio });
      await queryClient.refetchQueries({ predicate: matchesPortfolio, type: 'active' });

      setRefreshVersion((current) => current + 1);
      setRefreshMessage(
        `Aggiornati prezzi: ${refreshResult.refreshed_assets}/${refreshResult.requested_assets}, storico: ${backfillResult.assets_refreshed}/${backfillResult.assets_requested}`,
      );
    } catch (err) {
      setRefreshError(err instanceof Error ? err.message : 'Errore durante aggiornamento prezzi');
    } finally {
      setRefreshing(false);
    }
  }, [portfolioId, queryClient]);

  useEffect(() => {
    const onRefresh = () => { doRefresh(); };
    window.addEventListener('valore365:refresh-dashboard', onRefresh);
    return () => { window.removeEventListener('valore365:refresh-dashboard', onRefresh); };
  }, [doRefresh]);

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
