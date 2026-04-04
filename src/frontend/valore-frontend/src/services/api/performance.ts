import { apiFetch } from './client';
import type {
  DrawdownResponse,
  HallOfFameResponse,
  MonthlyReturnsResponse,
  PerformanceSummary,
  RollingWindowsResponse,
  TWRTimeseriesPoint,
  GainTimeseriesPoint,
  MWRTimeseriesPoint,
} from './types';

export const getPerformanceSummary = async (
  portfolioId: number,
  period: '1m' | '3m' | '6m' | 'ytd' | '1y' | '3y' | 'all',
): Promise<PerformanceSummary> => {
  return apiFetch<PerformanceSummary>(
    `/portfolios/${portfolioId}/performance/summary?period=${encodeURIComponent(period)}`,
  );
};

export const getTWRTimeseries = async (
  portfolioId: number,
  startDate?: string,
  endDate?: string,
): Promise<TWRTimeseriesPoint[]> => {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  const query = params.toString();
  return apiFetch<TWRTimeseriesPoint[]>(
    `/portfolios/${portfolioId}/performance/twr/timeseries${query ? `?${query}` : ''}`,
  );
};

export const getGainTimeseries = async (
  portfolioId: number,
  startDate?: string,
  endDate?: string,
): Promise<GainTimeseriesPoint[]> => {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  const query = params.toString();
  return apiFetch<GainTimeseriesPoint[]>(
    `/portfolios/${portfolioId}/performance/gain/timeseries${query ? `?${query}` : ''}`,
  );
};

export const getMWRTimeseries = async (
  portfolioId: number,
  startDate?: string,
  endDate?: string,
): Promise<MWRTimeseriesPoint[]> => {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  const query = params.toString();
  return apiFetch<MWRTimeseriesPoint[]>(
    `/portfolios/${portfolioId}/performance/mwr/timeseries${query ? `?${query}` : ''}`,
  );
};

export const getMonthlyReturns = async (
  portfolioId: number,
  startDate?: string,
  endDate?: string,
): Promise<MonthlyReturnsResponse> => {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  const query = params.toString();
  return apiFetch<MonthlyReturnsResponse>(
    `/portfolios/${portfolioId}/performance/monthly-returns${query ? `?${query}` : ''}`,
  );
};

export const getDrawdown = async (
  portfolioId: number,
  startDate?: string,
  endDate?: string,
): Promise<DrawdownResponse> => {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  const query = params.toString();
  return apiFetch<DrawdownResponse>(
    `/portfolios/${portfolioId}/performance/drawdown${query ? `?${query}` : ''}`,
  );
};

export const getRollingWindows = async (
  portfolioId: number,
  windowMonths = 12,
  riskFreeRate = 2,
  startDate?: string,
  endDate?: string,
): Promise<RollingWindowsResponse> => {
  const params = new URLSearchParams();
  params.set('window_months', String(windowMonths));
  params.set('risk_free_rate', String(riskFreeRate));
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  const query = params.toString();
  return apiFetch<RollingWindowsResponse>(
    `/portfolios/${portfolioId}/performance/rolling-windows?${query}`,
  );
};

export const getHallOfFame = async (
  portfolioId: number,
  topN = 5,
  startDate?: string,
  endDate?: string,
): Promise<HallOfFameResponse> => {
  const params = new URLSearchParams();
  params.set('top_n', String(topN));
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  const query = params.toString();
  return apiFetch<HallOfFameResponse>(
    `/portfolios/${portfolioId}/performance/hall-of-fame?${query}`,
  );
};
