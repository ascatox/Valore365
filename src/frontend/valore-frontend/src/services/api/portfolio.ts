import { apiFetch } from './client';
import type {
  Portfolio,
  PortfolioCreateInput,
  PortfolioUpdateInput,
  PortfolioCloneInput,
  PortfolioCloneResponse,
  PortfolioSummary,
  Position,
  AllocationItem,
  TimeSeriesPoint,
  IntradayTimeseriesPoint,
  PortfolioTargetPerformanceResponse,
  PortfolioTargetIntradayResponse,
  PortfolioTargetAssetPerformanceResponse,
  PortfolioTargetAssetIntradayPerformanceResponse,
  PortfolioTargetAllocationItem,
  PriceRefreshResponse,
  DailyBackfillResponse,
  DataCoverageResponse,
  RebalancePreviewInput,
  RebalancePreviewResponse,
  RebalanceCommitInput,
  RebalanceCommitResponse,
} from './types';

export const getPortfolios = async (): Promise<Portfolio[]> => {
  return apiFetch<Portfolio[]>('/portfolios');
};

/** @deprecated Use getPortfolios instead */
export const getAdminPortfolios = getPortfolios;

export const createPortfolio = async (payload: PortfolioCreateInput): Promise<Portfolio> => {
  return apiFetch<Portfolio>('/portfolios', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const updatePortfolio = async (portfolioId: number, payload: PortfolioUpdateInput): Promise<Portfolio> => {
  return apiFetch<Portfolio>(`/portfolios/${portfolioId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
};

export const deletePortfolio = async (portfolioId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/portfolios/${portfolioId}`, {
    method: 'DELETE',
  });
};

export const clonePortfolio = async (portfolioId: number, payload: PortfolioCloneInput): Promise<PortfolioCloneResponse> => {
  return apiFetch<PortfolioCloneResponse>(`/portfolios/${portfolioId}/clone`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getPortfolioSummary = async (portfolioId: number): Promise<PortfolioSummary> => {
  return apiFetch<PortfolioSummary>(`/portfolios/${portfolioId}/summary`);
};

export const getPortfolioPositions = async (portfolioId: number): Promise<Position[]> => {
  return apiFetch<Position[]>(`/portfolios/${portfolioId}/positions`);
};

export const getPortfolioAllocation = async (portfolioId: number): Promise<AllocationItem[]> => {
  return apiFetch<AllocationItem[]>(`/portfolios/${portfolioId}/allocation`);
};

export const getPortfolioTimeseries = async (portfolioId: number): Promise<TimeSeriesPoint[]> => {
  return apiFetch<TimeSeriesPoint[]>(`/portfolios/${portfolioId}/timeseries?range=1y&interval=1d`);
};

export const getPortfolioIntradayTimeseries = async (portfolioId: number): Promise<IntradayTimeseriesPoint[]> => {
  return apiFetch<IntradayTimeseriesPoint[]>(`/portfolios/${portfolioId}/intraday-timeseries`);
};

export const getPortfolioTargetPerformance = async (portfolioId: number): Promise<PortfolioTargetPerformanceResponse> => {
  return apiFetch<PortfolioTargetPerformanceResponse>(`/portfolios/${portfolioId}/target-performance`);
};

export const getPortfolioTargetIntradayPerformance = async (
  portfolioId: number,
  date: string,
): Promise<PortfolioTargetIntradayResponse> => {
  return apiFetch<PortfolioTargetIntradayResponse>(
    `/portfolios/${portfolioId}/target-performance/intraday?date=${encodeURIComponent(date)}`,
  );
};

export const getPortfolioTargetAssetPerformance = async (
  portfolioId: number,
): Promise<PortfolioTargetAssetPerformanceResponse> => {
  return apiFetch<PortfolioTargetAssetPerformanceResponse>(`/portfolios/${portfolioId}/target-performance/assets`);
};

export const getPortfolioTargetAssetIntradayPerformance = async (
  portfolioId: number,
  date: string,
): Promise<PortfolioTargetAssetIntradayPerformanceResponse> => {
  return apiFetch<PortfolioTargetAssetIntradayPerformanceResponse>(
    `/portfolios/${portfolioId}/target-performance/assets/intraday?date=${encodeURIComponent(date)}`,
  );
};

export const refreshPortfolioPrices = async (
  portfolioId: number,
  assetScope: 'target' | 'transactions' | 'all' = 'target',
): Promise<PriceRefreshResponse> => {
  return apiFetch<PriceRefreshResponse>(`/prices/refresh?portfolio_id=${portfolioId}&asset_scope=${assetScope}`, {
    method: 'POST',
  });
};

export const backfillPortfolioDailyPrices = async (
  portfolioId: number,
  days = 365,
  assetScope: 'target' | 'transactions' | 'all' = 'target',
): Promise<DailyBackfillResponse> => {
  return apiFetch<DailyBackfillResponse>(
    `/prices/backfill-daily?portfolio_id=${portfolioId}&days=${days}&asset_scope=${assetScope}`,
    { method: 'POST' },
  );
};

export const reclassifyPortfolioAssets = async (
  portfolioId: number,
): Promise<{ updated: Array<{ symbol: string; old: string; new: string }>; total_checked: number }> => {
  return apiFetch(`/portfolios/${portfolioId}/reclassify-assets`, { method: 'POST' });
};

export const getPortfolioTargetAllocation = async (portfolioId: number): Promise<PortfolioTargetAllocationItem[]> => {
  return apiFetch<PortfolioTargetAllocationItem[]>(`/portfolios/${portfolioId}/target-allocation`);
};

export const upsertPortfolioTargetAllocation = async (
  portfolioId: number,
  payload: { asset_id: number; weight_pct: number },
): Promise<PortfolioTargetAllocationItem> => {
  return apiFetch<PortfolioTargetAllocationItem>(`/portfolios/${portfolioId}/target-allocation`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const deletePortfolioTargetAllocation = async (portfolioId: number, assetId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/portfolios/${portfolioId}/target-allocation/${assetId}`, {
    method: 'DELETE',
  });
};

export const getPortfolioRebalancePreview = async (
  portfolioId: number,
  payload: RebalancePreviewInput,
): Promise<RebalancePreviewResponse> => {
  return apiFetch<RebalancePreviewResponse>(`/portfolios/${portfolioId}/rebalance/preview`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const commitPortfolioRebalance = async (
  portfolioId: number,
  payload: RebalanceCommitInput,
): Promise<RebalanceCommitResponse> => {
  return apiFetch<RebalanceCommitResponse>(`/portfolios/${portfolioId}/rebalance/commit`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getPortfolioDataCoverage = async (
  portfolioId: number,
  days = 365,
  thresholdPct = 80,
): Promise<DataCoverageResponse> => {
  return apiFetch<DataCoverageResponse>(
    `/portfolios/${portfolioId}/data-coverage?days=${days}&threshold_pct=${thresholdPct}`,
  );
};
