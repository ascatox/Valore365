import { apiFetch } from './client';
import type {
  MarketQuotesResponse,
  MarketNewsResponse,
  AssetInfo,
  BenchmarkItem,
} from './types';

export const getMarketQuotes = async (): Promise<MarketQuotesResponse> => {
  return apiFetch<MarketQuotesResponse>('/markets/quotes');
};

export const getMarketNews = async (): Promise<MarketNewsResponse> => {
  return apiFetch<MarketNewsResponse>('/markets/news');
};

export const getMarketSymbolInfo = async (symbol: string): Promise<AssetInfo> => {
  return apiFetch<AssetInfo>(`/markets/symbol-info?symbol=${encodeURIComponent(symbol)}`);
};

export const getBenchmarks = async (): Promise<BenchmarkItem[]> => {
  return apiFetch<BenchmarkItem[]>('/benchmarks');
};

export const backfillBenchmarkPrices = async (
  assetId: number,
  portfolioId: number,
  days = 365,
): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(
    `/benchmarks/${assetId}/backfill?portfolio_id=${portfolioId}&days=${days}`,
    { method: 'POST' },
  );
};
