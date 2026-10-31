import { keepPreviousData, queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';
import {
  backfillBenchmarkPrices,
  getAdminPortfolios,
  getAggregateDecumulationPlan,
  getAssetPriceTimeseries,
  getDecumulationPlan,
  getDecumulationPlanForScope,
  getBenchmarks,
  getDrawdownForScope,
  getGainTimeseriesForScope,
  getHallOfFameForScope,
  getMarketCalendar,
  getMarketNews,
  getMarketQuotes,
  getMonteCarloProjectionForScope,
  getMonthlyReturnsForScope,
  getMWRTimeseriesForScope,
  getPerformanceSummaryForScope,
  getPortfolioAllocationForScope,
  getPortfolioDataCoverageForScope,
  getPortfolioHealthForScope,
  getPortfolioIntradayTimeseriesForScope,
  getPortfolioPerformersForScope,
  getPortfolioPositionsForScope,
  getPortfolioSummaryForScope,
  getPortfolioTargetAllocation,
  getPortfolioTargetAssetIntradayPerformance,
  getPortfolioTargetAssetPerformance,
  getPortfolioTargetIntradayPerformance,
  getPortfolioTargetPerformance,
  getPortfolioTimeseriesForScope,
  getPortfolioTransactionsForScope,
  getPortfolioXrayForScope,
  getRollingWindowsForScope,
  getStressTestForScope,
  getTWRTimeseriesForScope,
  getUserSettings,
  getYearlyReturnsForScope,
  type DecumulationScheduleParams,
  type PerformancePeriod,
} from '../../../services/api';
import {
  portfolioScopeKey,
  scopePortfolioIds,
  singlePortfolioId,
  toPortfolioScope,
  type PortfolioScopeInput,
} from '../../../scope/portfolioScope';

// Portfolio hooks take a `PortfolioScopeInput`: a bare portfolio id (as the
// pages pass today) or a PortfolioScope. The second key segment is
// `portfolioScopeKey(scope)`: the bare id for a single portfolio, so existing
// keys and invalidations are unchanged, and `'aggregate:<sorted ids>'` for an
// aggregate, which never shares a cache entry with a single portfolio.
//
// Target allocation / target performance / intraday detail are per portfolio
// and have no aggregate route: with an aggregate scope those hooks stay
// disabled.

function todayLocalDate(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

// ---- Core portfolio data ----

export function usePortfolios() {
  return useQuery({
    queryKey: ['portfolios'],
    queryFn: getAdminPortfolios,
  });
}

export function usePortfolioSummary(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-summary', portfolioScopeKey(scope)],
    queryFn: () => getPortfolioSummaryForScope(scope!),
    enabled: scope != null,
  });
}

export function useUserSettings() {
  return useQuery({
    queryKey: ['user-settings'],
    queryFn: getUserSettings,
  });
}

export function usePortfolioHealth(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-health', portfolioScopeKey(scope)],
    queryFn: () => getPortfolioHealthForScope(scope!),
    enabled: scope != null,
  });
}

export function usePortfolioXray(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-xray', portfolioScopeKey(scope)],
    queryFn: () => getPortfolioXrayForScope(scope!),
    enabled: scope != null,
  });
}

export function useMonteCarloProjection(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['monte-carlo-projection', portfolioScopeKey(scope)],
    queryFn: () => getMonteCarloProjectionForScope(scope!),
    enabled: scope != null,
  });
}

export function useStressTest(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['stress-test', portfolioScopeKey(scope)],
    queryFn: () => getStressTestForScope(scope!),
    enabled: scope != null,
  });
}

type DecumulationHookParams = {
  annualWithdrawal: number;
  years: number;
  inflationRatePct: number;
  otherIncomeAnnual: number;
  capitalGainsTaxRatePct: number;
  currentAge: number | null;
} & DecumulationScheduleParams;

export function useDecumulationPlan(
  portfolioId: number | null,
  params: DecumulationHookParams,
  enabled = true,
) {
  return useQuery({
    queryKey: ['decumulation-plan', portfolioId, params],
    queryFn: () => getDecumulationPlan(portfolioId!, params),
    enabled: portfolioId != null && enabled,
  });
}

export function useAggregateDecumulationPlan(
  portfolioIds: number[],
  params: DecumulationHookParams,
  enabled = true,
) {
  return useQuery({
    queryKey: ['aggregate-decumulation-plan', portfolioIds, params],
    queryFn: () => getAggregateDecumulationPlan(portfolioIds, params),
    enabled: portfolioIds.length > 0 && enabled,
  });
}

/**
 * Decumulation plan for a scope. The data is a `DecumulationPlanResponse`
 * for a single portfolio and an `AggregateDecumulationPlanResponse` for an
 * aggregate (same projection fields, `portfolio_ids` instead of `portfolio_id`).
 */
export function useDecumulationPlanForScope(
  portfolio: PortfolioScopeInput,
  params: DecumulationHookParams,
  enabled = true,
) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['decumulation-plan', portfolioScopeKey(scope), params],
    queryFn: () => getDecumulationPlanForScope(scope!, params),
    enabled: scope != null && enabled,
  });
}

export function usePortfolioPositions(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-positions', portfolioScopeKey(scope)],
    queryFn: () => getPortfolioPositionsForScope(scope!),
    enabled: scope != null,
  });
}

export function usePortfolioPerformers(portfolio: PortfolioScopeInput, days: number, enabled = true) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-performers', portfolioScopeKey(scope), days],
    queryFn: () => getPortfolioPerformersForScope(scope!, days),
    enabled: scope != null && enabled,
  });
}

export function usePortfolioAllocation(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-allocation', portfolioScopeKey(scope)],
    queryFn: () => getPortfolioAllocationForScope(scope!),
    enabled: scope != null,
  });
}

export function usePortfolioTimeseries(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-timeseries', portfolioScopeKey(scope)],
    queryFn: () => getPortfolioTimeseriesForScope(scope!),
    enabled: scope != null,
  });
}

export function usePortfolioDataCoverage(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-data-coverage', portfolioScopeKey(scope)],
    queryFn: () => getPortfolioDataCoverageForScope(scope!),
    enabled: scope != null,
  });
}

/** Transactions of a scope; aggregate rows carry `portfolio_name`. */
export function usePortfolioTransactions(portfolio: PortfolioScopeInput, enabled = true) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-transactions', portfolioScopeKey(scope)],
    queryFn: () => getPortfolioTransactionsForScope(scope!),
    enabled: scope != null && enabled,
  });
}

// ---- Target allocation (single portfolio only) ----

export function useTargetAllocation(portfolio: PortfolioScopeInput) {
  const portfolioId = singlePortfolioId(portfolio);
  return useQuery({
    queryKey: ['target-allocation', portfolioId],
    queryFn: () => getPortfolioTargetAllocation(portfolioId!),
    enabled: portfolioId != null,
    // placeholderData, not initialData: initialData counts as fresh for the
    // 60s staleTime, so the request never ran and targets stayed empty.
    placeholderData: [] as Awaited<ReturnType<typeof getPortfolioTargetAllocation>>,
  });
}

export function useTargetPerformance(portfolio: PortfolioScopeInput) {
  const portfolioId = singlePortfolioId(portfolio);
  return useQuery({
    queryKey: ['target-performance', portfolioId],
    queryFn: () => getPortfolioTargetPerformance(portfolioId!),
    enabled: portfolioId != null,
  });
}

export function useTargetAssetPerformance(portfolio: PortfolioScopeInput) {
  const portfolioId = singlePortfolioId(portfolio);
  return useQuery({
    queryKey: ['target-asset-performance', portfolioId],
    queryFn: () => getPortfolioTargetAssetPerformance(portfolioId!),
    enabled: portfolioId != null,
  });
}

// ---- Intraday data ----

export function useIntradayTargetPerformance(portfolio: PortfolioScopeInput, isIntraday: boolean) {
  const portfolioId = singlePortfolioId(portfolio);
  const date = todayLocalDate();
  return useQuery({
    queryKey: ['intraday-target-performance', portfolioId, date],
    queryFn: () => getPortfolioTargetIntradayPerformance(portfolioId!, date),
    enabled: portfolioId != null && isIntraday,
  });
}

export function useAssetIntradayTargetPerformance(portfolio: PortfolioScopeInput, isIntraday: boolean) {
  const portfolioId = singlePortfolioId(portfolio);
  const date = todayLocalDate();
  return useQuery({
    queryKey: ['asset-intraday-target-performance', portfolioId, date],
    queryFn: () => getPortfolioTargetAssetIntradayPerformance(portfolioId!, date),
    enabled: portfolioId != null && isIntraday,
  });
}

export function usePortfolioIntradayTimeseries(portfolio: PortfolioScopeInput, isIntraday: boolean) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-intraday-timeseries', portfolioScopeKey(scope)],
    queryFn: () => getPortfolioIntradayTimeseriesForScope(scope!),
    enabled: scope != null && isIntraday,
  });
}

export function useIntradayDetail(portfolio: PortfolioScopeInput, date: string | null) {
  const portfolioId = singlePortfolioId(portfolio);
  return useQuery({
    queryKey: ['intraday-detail', portfolioId, date],
    queryFn: () => getPortfolioTargetIntradayPerformance(portfolioId!, date!),
    enabled: portfolioId != null && date != null,
  });
}

// ---- Timeseries ----

export function useGainTimeseries(portfolio: PortfolioScopeInput, startDate?: string) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['gain-timeseries', portfolioScopeKey(scope), startDate ?? 'all'],
    queryFn: () => getGainTimeseriesForScope(scope!, startDate),
    enabled: scope != null,
  });
}

// ---- Benchmarks ----

export function useBenchmarks() {
  return useQuery({
    queryKey: ['benchmarks'],
    queryFn: getBenchmarks,
  });
}

export function useBenchmarkPrices(
  benchmarkId: number | null,
  portfolio: PortfolioScopeInput,
  startDate: string,
) {
  // The backfill only needs a portfolio to run against: the first of the scope.
  const portfolioId = scopePortfolioIds(toPortfolioScope(portfolio))[0] ?? null;
  return useQuery({
    queryKey: ['benchmark-prices', benchmarkId, startDate],
    queryFn: async () => {
      const pts = await getAssetPriceTimeseries(benchmarkId!, startDate);
      if (pts.length === 0 && portfolioId) {
        await backfillBenchmarkPrices(benchmarkId!, portfolioId, 365);
        return getAssetPriceTimeseries(benchmarkId!, startDate);
      }
      return pts;
    },
    enabled: benchmarkId != null,
  });
}

// ---- Market quotes ----

// Shared by the hooks and by prefetchMarketData, so both use the same keys
// and freshness.
const marketQuotesQuery = queryOptions({
  queryKey: ['market-quotes'],
  queryFn: getMarketQuotes,
});

const marketNewsQuery = queryOptions({
  queryKey: ['market-news'],
  queryFn: getMarketNews,
});

const marketCalendarQuery = (days: number) => queryOptions({
  queryKey: ['market-calendar', days],
  queryFn: () => getMarketCalendar(days),
  staleTime: 15 * 60 * 1000, // the backend caches the calendar for 30 minutes
});

// Range the Mercati calendar card opens with.
export const DEFAULT_MARKET_CALENDAR_DAYS = 3;

export function useMarketQuotes() {
  return useQuery(marketQuotesQuery);
}

export function useMarketNews() {
  return useQuery({
    ...marketNewsQuery,
    refetchInterval: 5 * 60 * 1000, // refresh every 5 minutes
  });
}

export function useMarketCalendar(days: number) {
  return useQuery({
    ...marketCalendarQuery(days),
    placeholderData: keepPreviousData, // keep the current days on screen while switching range
  });
}

/**
 * Load what the Mercati tab shows (quotes, news, the default calendar range)
 * into the cache without rendering it, so the tab opens with data. Fresh
 * entries are not fetched again.
 */
export function prefetchMarketData(queryClient: QueryClient) {
  return Promise.all([
    queryClient.prefetchQuery(marketQuotesQuery),
    queryClient.prefetchQuery(marketNewsQuery),
    queryClient.prefetchQuery(marketCalendarQuery(DEFAULT_MARKET_CALENDAR_DAYS)),
  ]);
}

// ---- Performance metrics (TWR, MWR, Gain) ----

export function usePerformanceSummary(portfolio: PortfolioScopeInput, period: string) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['performance-summary', portfolioScopeKey(scope), period],
    queryFn: () => getPerformanceSummaryForScope(scope!, period as PerformancePeriod),
    enabled: scope != null,
  });
}

export function useTWRTimeseries(portfolio: PortfolioScopeInput, startDate?: string) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['twr-timeseries', portfolioScopeKey(scope), startDate ?? 'all'],
    queryFn: () => getTWRTimeseriesForScope(scope!, startDate),
    enabled: scope != null,
  });
}

export function useMWRTimeseries(portfolio: PortfolioScopeInput, startDate?: string) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['mwr-timeseries', portfolioScopeKey(scope), startDate ?? 'all'],
    queryFn: () => getMWRTimeseriesForScope(scope!, startDate),
    enabled: scope != null,
  });
}

export function useMonthlyReturns(portfolio: PortfolioScopeInput, startDate?: string) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['monthly-returns', portfolioScopeKey(scope), startDate ?? 'all'],
    queryFn: () => getMonthlyReturnsForScope(scope!, startDate),
    enabled: scope != null,
  });
}

export function useYearlyReturns(portfolio: PortfolioScopeInput) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['yearly-returns', portfolioScopeKey(scope)],
    queryFn: () => getYearlyReturnsForScope(scope!),
    enabled: scope != null,
  });
}

export function usePortfolioDrawdown(portfolio: PortfolioScopeInput, startDate?: string) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['portfolio-drawdown', portfolioScopeKey(scope), startDate ?? 'all'],
    queryFn: () => getDrawdownForScope(scope!, startDate),
    enabled: scope != null,
  });
}

export function useRollingWindows(
  portfolio: PortfolioScopeInput,
  windowMonths: number,
  riskFreeRate = 2,
  startDate?: string,
) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['rolling-windows', portfolioScopeKey(scope), windowMonths, riskFreeRate, startDate ?? 'all'],
    queryFn: () => getRollingWindowsForScope(scope!, windowMonths, riskFreeRate, startDate),
    enabled: scope != null,
  });
}

export function useHallOfFame(portfolio: PortfolioScopeInput, topN = 5, startDate?: string) {
  const scope = toPortfolioScope(portfolio);
  return useQuery({
    queryKey: ['hall-of-fame', portfolioScopeKey(scope), topN, startDate ?? 'all'],
    queryFn: () => getHallOfFameForScope(scope!, topN, startDate),
    enabled: scope != null,
  });
}
