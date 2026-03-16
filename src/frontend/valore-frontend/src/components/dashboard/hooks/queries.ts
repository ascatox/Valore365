import { useQuery } from '@tanstack/react-query';
import {
  backfillBenchmarkPrices,
  getAdminPortfolios,
  getAggregateDecumulationPlan,
  getAssetPriceTimeseries,
  getDecumulationPlan,
  getBenchmarks,
  getGainTimeseries,
  getMarketQuotes,
  getMonteCarloProjection,
  getMWRTimeseries,
  getPerformanceSummary,
  getPortfolioAllocation,
  getPortfolioDataCoverage,
  getPortfolioHealth,
  getPortfolioIntradayTimeseries,
  getPortfolioXray,
  getPortfolioPositions,
  getPortfolioSummary,
  getPortfolioTargetAllocation,
  getPortfolioTargetAssetIntradayPerformance,
  getPortfolioTargetAssetPerformance,
  getPortfolioTargetIntradayPerformance,
  getPortfolioTargetPerformance,
  getPortfolioTimeseries,
  getStressTest,
  getTWRTimeseries,
  getUserSettings,
} from '../../../services/api';
import { ENABLE_TARGET_ALLOCATION } from '../../../features';

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

export function usePortfolioSummary(portfolioId: number | null) {
  return useQuery({
    queryKey: ['portfolio-summary', portfolioId],
    queryFn: () => getPortfolioSummary(portfolioId!),
    enabled: portfolioId != null,
  });
}

export function useUserSettings() {
  return useQuery({
    queryKey: ['user-settings'],
    queryFn: getUserSettings,
  });
}

export function usePortfolioHealth(portfolioId: number | null) {
  return useQuery({
    queryKey: ['portfolio-health', portfolioId],
    queryFn: () => getPortfolioHealth(portfolioId!),
    enabled: portfolioId != null,
  });
}

export function usePortfolioXray(portfolioId: number | null) {
  return useQuery({
    queryKey: ['portfolio-xray', portfolioId],
    queryFn: () => getPortfolioXray(portfolioId!),
    enabled: portfolioId != null,
  });
}

export function useMonteCarloProjection(portfolioId: number | null) {
  return useQuery({
    queryKey: ['monte-carlo-projection', portfolioId],
    queryFn: () => getMonteCarloProjection(portfolioId!),
    enabled: portfolioId != null,
  });
}

export function useStressTest(portfolioId: number | null) {
  return useQuery({
    queryKey: ['stress-test', portfolioId],
    queryFn: () => getStressTest(portfolioId!),
    enabled: portfolioId != null,
  });
}

export function useDecumulationPlan(
  portfolioId: number | null,
  params: {
    annualWithdrawal: number;
    years: number;
    inflationRatePct: number;
    otherIncomeAnnual: number;
    currentAge: number | null;
  },
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
  params: {
    annualWithdrawal: number;
    years: number;
    inflationRatePct: number;
    otherIncomeAnnual: number;
    currentAge: number | null;
  },
  enabled = true,
) {
  return useQuery({
    queryKey: ['aggregate-decumulation-plan', portfolioIds, params],
    queryFn: () => getAggregateDecumulationPlan(portfolioIds, params),
    enabled: portfolioIds.length > 0 && enabled,
  });
}

export function usePortfolioPositions(portfolioId: number | null) {
  return useQuery({
    queryKey: ['portfolio-positions', portfolioId],
    queryFn: () => getPortfolioPositions(portfolioId!),
    enabled: portfolioId != null,
  });
}

export function usePortfolioAllocation(portfolioId: number | null) {
  return useQuery({
    queryKey: ['portfolio-allocation', portfolioId],
    queryFn: () => getPortfolioAllocation(portfolioId!),
    enabled: portfolioId != null,
  });
}

export function usePortfolioTimeseries(portfolioId: number | null) {
  return useQuery({
    queryKey: ['portfolio-timeseries', portfolioId],
    queryFn: () => getPortfolioTimeseries(portfolioId!),
    enabled: portfolioId != null,
  });
}

export function usePortfolioDataCoverage(portfolioId: number | null) {
  return useQuery({
    queryKey: ['portfolio-data-coverage', portfolioId],
    queryFn: () => getPortfolioDataCoverage(portfolioId!),
    enabled: portfolioId != null && ENABLE_TARGET_ALLOCATION,
  });
}

// ---- Target allocation (feature-gated) ----

export function useTargetAllocation(portfolioId: number | null) {
  return useQuery({
    queryKey: ['target-allocation', portfolioId],
    queryFn: () => getPortfolioTargetAllocation(portfolioId!),
    enabled: portfolioId != null && ENABLE_TARGET_ALLOCATION,
    initialData: [] as Awaited<ReturnType<typeof getPortfolioTargetAllocation>>,
  });
}

export function useTargetPerformance(portfolioId: number | null) {
  return useQuery({
    queryKey: ['target-performance', portfolioId],
    queryFn: () => getPortfolioTargetPerformance(portfolioId!),
    enabled: portfolioId != null && ENABLE_TARGET_ALLOCATION,
  });
}

export function useTargetAssetPerformance(portfolioId: number | null) {
  return useQuery({
    queryKey: ['target-asset-performance', portfolioId],
    queryFn: () => getPortfolioTargetAssetPerformance(portfolioId!),
    enabled: portfolioId != null && ENABLE_TARGET_ALLOCATION,
  });
}

// ---- Intraday data ----

export function useIntradayTargetPerformance(portfolioId: number | null, isIntraday: boolean) {
  const date = todayLocalDate();
  return useQuery({
    queryKey: ['intraday-target-performance', portfolioId, date],
    queryFn: () => getPortfolioTargetIntradayPerformance(portfolioId!, date),
    enabled: portfolioId != null && isIntraday && ENABLE_TARGET_ALLOCATION,
  });
}

export function useAssetIntradayTargetPerformance(portfolioId: number | null, isIntraday: boolean) {
  const date = todayLocalDate();
  return useQuery({
    queryKey: ['asset-intraday-target-performance', portfolioId, date],
    queryFn: () => getPortfolioTargetAssetIntradayPerformance(portfolioId!, date),
    enabled: portfolioId != null && isIntraday && ENABLE_TARGET_ALLOCATION,
  });
}

export function usePortfolioIntradayTimeseries(portfolioId: number | null, isIntraday: boolean) {
  return useQuery({
    queryKey: ['portfolio-intraday-timeseries', portfolioId],
    queryFn: () => getPortfolioIntradayTimeseries(portfolioId!),
    enabled: portfolioId != null && isIntraday,
  });
}

export function useIntradayDetail(portfolioId: number | null, date: string | null) {
  return useQuery({
    queryKey: ['intraday-detail', portfolioId, date],
    queryFn: () => getPortfolioTargetIntradayPerformance(portfolioId!, date!),
    enabled: portfolioId != null && date != null && ENABLE_TARGET_ALLOCATION,
  });
}

// ---- Timeseries ----

export function useGainTimeseries(portfolioId: number | null, startDate?: string) {
  return useQuery({
    queryKey: ['gain-timeseries', portfolioId, startDate ?? 'all'],
    queryFn: () => getGainTimeseries(portfolioId!, startDate),
    enabled: portfolioId != null,
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
  portfolioId: number | null,
  startDate: string,
) {
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

export function useMarketQuotes() {
  return useQuery({
    queryKey: ['market-quotes'],
    queryFn: getMarketQuotes,
  });
}

// ---- Performance metrics (TWR, MWR, Gain) ----

export function usePerformanceSummary(portfolioId: number | null, period: string) {
  return useQuery({
    queryKey: ['performance-summary', portfolioId, period],
    queryFn: () => getPerformanceSummary(portfolioId!, period as any),
    enabled: portfolioId != null,
  });
}

export function useTWRTimeseries(portfolioId: number | null, startDate?: string) {
  return useQuery({
    queryKey: ['twr-timeseries', portfolioId, startDate ?? 'all'],
    queryFn: () => getTWRTimeseries(portfolioId!, startDate),
    enabled: portfolioId != null,
  });
}

export function useMWRTimeseries(portfolioId: number | null, startDate?: string) {
  return useQuery({
    queryKey: ['mwr-timeseries', portfolioId, startDate ?? 'all'],
    queryFn: () => getMWRTimeseries(portfolioId!, startDate),
    enabled: portfolioId != null,
  });
}
