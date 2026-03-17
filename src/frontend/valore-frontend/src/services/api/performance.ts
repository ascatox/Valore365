import { apiFetch } from './client';
import type {
  PerformanceSummary,
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
