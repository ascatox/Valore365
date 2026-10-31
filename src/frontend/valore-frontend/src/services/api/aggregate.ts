// Read-only views of several portfolios as one ("vista aggregata") and
// scope-aware wrappers that pick the single or the aggregate route.
//
// The aggregate routes (`/portfolios/aggregate/<resource>?portfolio_ids=1&portfolio_ids=2`)
// take the same query params and return the same shapes as the single routes,
// with `portfolio_id: 0` and `portfolio_ids` set where the response has an id.
// For a single scope the wrappers call the existing single-portfolio
// functions, so those requests are unchanged.

import type { PortfolioScope } from '../../scope/portfolioScope';
import { normalizePortfolioIds } from '../../scope/portfolioScope';
import { apiFetch } from './client';
import {
  getAggregateDecumulationPlan,
  getDecumulationPlan,
  getMonteCarloProjection,
  getPortfolioHealth,
  getPortfolioXray,
  getStressTest,
  type DecumulationScheduleParams,
} from './doctor';
import {
  getDrawdown,
  getGainTimeseries,
  getHallOfFame,
  getMWRTimeseries,
  getMonthlyReturns,
  getPerformanceSummary,
  getRollingWindows,
  getTWRTimeseries,
  getYearlyReturns,
} from './performance';
import {
  getPortfolioAllocation,
  getPortfolioDataCoverage,
  getPortfolioIntradayTimeseries,
  getPortfolioPerformers,
  getPortfolioPositions,
  getPortfolioSummary,
  getPortfolioTimeseries,
} from './portfolio';
import { fetchMarkdownExport, getPortfolioMarkdown, type MarkdownExport } from './export';
import { getPortfolioTransactions } from './transactions';
import type {
  AggregateDecumulationPlanResponse,
  AllocationItem,
  DataCoverageResponse,
  DecumulationPlanResponse,
  DrawdownResponse,
  GainTimeseriesPoint,
  HallOfFameResponse,
  IntradayTimeseriesPoint,
  MWRResult,
  MWRTimeseriesPoint,
  MonteCarloProjectionResponse,
  MonthlyReturnsResponse,
  PerformanceSummary,
  PeriodPerformer,
  PortfolioHealthResponse,
  PortfolioSummary,
  Position,
  RollingWindowsResponse,
  StressTestResponse,
  TWRResult,
  TWRTimeseriesPoint,
  TimeSeriesPoint,
  TransactionListItem,
  XRayResponse,
  YearlyPerformanceResponse,
} from './types';

export type PerformancePeriod = '1m' | '3m' | '6m' | 'ytd' | '1y' | '3y' | 'all';

type QueryValue = string | number | null | undefined;

/**
 * Query string with `portfolio_ids` repeated once per id (normalized: sorted,
 * unique), followed by the given params; null/undefined params are skipped.
 */
export function buildPortfolioIdsQuery(portfolioIds: number[], params: Record<string, QueryValue> = {}): URLSearchParams {
  const query = new URLSearchParams();
  normalizePortfolioIds(portfolioIds).forEach((id) => query.append('portfolio_ids', String(id)));
  Object.entries(params).forEach(([key, value]) => {
    if (value != null && value !== '') query.set(key, String(value));
  });
  return query;
}

/** `/portfolios/aggregate/<resource>?portfolio_ids=...&...` */
export function aggregatePath(resource: string, portfolioIds: number[], params: Record<string, QueryValue> = {}): string {
  return `/portfolios/aggregate/${resource}?${buildPortfolioIdsQuery(portfolioIds, params).toString()}`;
}

// ---- Aggregate client functions ----

export const getAggregatePortfolioSummary = (ids: number[]) =>
  apiFetch<PortfolioSummary>(aggregatePath('summary', ids));

export const getAggregatePortfolioPositions = (ids: number[]) =>
  apiFetch<Position[]>(aggregatePath('positions', ids));

export const getAggregatePortfolioAllocation = (ids: number[]) =>
  apiFetch<AllocationItem[]>(aggregatePath('allocation', ids));

export const getAggregatePortfolioPerformers = (ids: number[], days: number) =>
  apiFetch<PeriodPerformer[]>(aggregatePath('performers', ids, { days }));

export const getAggregatePortfolioTimeseries = (ids: number[]) =>
  apiFetch<TimeSeriesPoint[]>(aggregatePath('timeseries', ids, { range: '1y', interval: '1d' }));

export const getAggregatePortfolioIntradayTimeseries = (ids: number[]) =>
  apiFetch<IntradayTimeseriesPoint[]>(aggregatePath('intraday-timeseries', ids));

/** Rows carry `portfolio_name`. */
export const getAggregatePortfolioTransactions = (ids: number[]) =>
  apiFetch<TransactionListItem[]>(aggregatePath('transactions', ids));

export const getAggregatePortfolioDataCoverage = (ids: number[], days = 365, thresholdPct = 80) =>
  apiFetch<DataCoverageResponse>(aggregatePath('data-coverage', ids, { days, threshold_pct: thresholdPct }));

export const getAggregatePerformanceSummary = (ids: number[], period: PerformancePeriod) =>
  apiFetch<PerformanceSummary>(aggregatePath('performance/summary', ids, { period }));

export const getAggregateTWR = (ids: number[], startDate?: string, endDate?: string) =>
  apiFetch<TWRResult>(aggregatePath('performance/twr', ids, { start_date: startDate, end_date: endDate }));

export const getAggregateTWRTimeseries = (ids: number[], startDate?: string, endDate?: string) =>
  apiFetch<TWRTimeseriesPoint[]>(
    aggregatePath('performance/twr/timeseries', ids, { start_date: startDate, end_date: endDate }),
  );

export const getAggregateMWR = (ids: number[], startDate?: string, endDate?: string) =>
  apiFetch<MWRResult>(aggregatePath('performance/mwr', ids, { start_date: startDate, end_date: endDate }));

export const getAggregateMWRTimeseries = (ids: number[], startDate?: string, endDate?: string) =>
  apiFetch<MWRTimeseriesPoint[]>(
    aggregatePath('performance/mwr/timeseries', ids, { start_date: startDate, end_date: endDate }),
  );

export const getAggregateGainTimeseries = (ids: number[], startDate?: string, endDate?: string) =>
  apiFetch<GainTimeseriesPoint[]>(
    aggregatePath('performance/gain/timeseries', ids, { start_date: startDate, end_date: endDate }),
  );

export const getAggregateMonthlyReturns = (ids: number[], startDate?: string, endDate?: string) =>
  apiFetch<MonthlyReturnsResponse>(
    aggregatePath('performance/monthly-returns', ids, { start_date: startDate, end_date: endDate }),
  );

export const getAggregateYearlyReturns = (ids: number[]) =>
  apiFetch<YearlyPerformanceResponse>(aggregatePath('performance/yearly', ids));

export const getAggregateDrawdown = (ids: number[], startDate?: string, endDate?: string) =>
  apiFetch<DrawdownResponse>(
    aggregatePath('performance/drawdown', ids, { start_date: startDate, end_date: endDate }),
  );

export const getAggregateRollingWindows = (
  ids: number[],
  windowMonths = 12,
  riskFreeRate = 2,
  startDate?: string,
  endDate?: string,
) =>
  apiFetch<RollingWindowsResponse>(
    aggregatePath('performance/rolling-windows', ids, {
      window_months: windowMonths,
      risk_free_rate: riskFreeRate,
      start_date: startDate,
      end_date: endDate,
    }),
  );

export const getAggregateHallOfFame = (ids: number[], topN = 5, startDate?: string, endDate?: string) =>
  apiFetch<HallOfFameResponse>(
    aggregatePath('performance/hall-of-fame', ids, { top_n: topN, start_date: startDate, end_date: endDate }),
  );

export const getAggregatePortfolioHealth = (ids: number[]) =>
  apiFetch<PortfolioHealthResponse>(aggregatePath('health', ids));

export const getAggregateMonteCarloProjection = (ids: number[]) =>
  apiFetch<MonteCarloProjectionResponse>(aggregatePath('monte-carlo', ids));

export const getAggregateStressTest = (ids: number[]) =>
  apiFetch<StressTestResponse>(aggregatePath('stress-test', ids));

export const getAggregatePortfolioXray = (ids: number[]) =>
  apiFetch<XRayResponse>(aggregatePath('xray', ids));

/** Markdown snapshot of the aggregate ("Vista aggregata: A, B"), for an external AI. */
export const getAggregatePortfolioMarkdown = (ids: number[]): Promise<MarkdownExport> =>
  fetchMarkdownExport(
    aggregatePath('export/markdown', ids),
    `valore365-aggregato-${new Date().toISOString().slice(0, 10)}.md`,
  );

// ---- Scope-aware wrappers: single route for a single scope, aggregate route otherwise ----

export const getPortfolioSummaryForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getPortfolioSummary(scope.id) : getAggregatePortfolioSummary(scope.ids);

export const getPortfolioPositionsForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getPortfolioPositions(scope.id) : getAggregatePortfolioPositions(scope.ids);

export const getPortfolioAllocationForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getPortfolioAllocation(scope.id) : getAggregatePortfolioAllocation(scope.ids);

export const getPortfolioPerformersForScope = (scope: PortfolioScope, days: number) =>
  scope.mode === 'single' ? getPortfolioPerformers(scope.id, days) : getAggregatePortfolioPerformers(scope.ids, days);

export const getPortfolioTimeseriesForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getPortfolioTimeseries(scope.id) : getAggregatePortfolioTimeseries(scope.ids);

export const getPortfolioIntradayTimeseriesForScope = (scope: PortfolioScope) =>
  scope.mode === 'single'
    ? getPortfolioIntradayTimeseries(scope.id)
    : getAggregatePortfolioIntradayTimeseries(scope.ids);

export const getPortfolioTransactionsForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getPortfolioTransactions(scope.id) : getAggregatePortfolioTransactions(scope.ids);

export const getPortfolioDataCoverageForScope = (scope: PortfolioScope, days = 365, thresholdPct = 80) =>
  scope.mode === 'single'
    ? getPortfolioDataCoverage(scope.id, days, thresholdPct)
    : getAggregatePortfolioDataCoverage(scope.ids, days, thresholdPct);

export const getPerformanceSummaryForScope = (scope: PortfolioScope, period: PerformancePeriod) =>
  scope.mode === 'single' ? getPerformanceSummary(scope.id, period) : getAggregatePerformanceSummary(scope.ids, period);

export const getTWRTimeseriesForScope = (scope: PortfolioScope, startDate?: string, endDate?: string) =>
  scope.mode === 'single'
    ? getTWRTimeseries(scope.id, startDate, endDate)
    : getAggregateTWRTimeseries(scope.ids, startDate, endDate);

export const getMWRTimeseriesForScope = (scope: PortfolioScope, startDate?: string, endDate?: string) =>
  scope.mode === 'single'
    ? getMWRTimeseries(scope.id, startDate, endDate)
    : getAggregateMWRTimeseries(scope.ids, startDate, endDate);

export const getGainTimeseriesForScope = (scope: PortfolioScope, startDate?: string, endDate?: string) =>
  scope.mode === 'single'
    ? getGainTimeseries(scope.id, startDate, endDate)
    : getAggregateGainTimeseries(scope.ids, startDate, endDate);

export const getMonthlyReturnsForScope = (scope: PortfolioScope, startDate?: string, endDate?: string) =>
  scope.mode === 'single'
    ? getMonthlyReturns(scope.id, startDate, endDate)
    : getAggregateMonthlyReturns(scope.ids, startDate, endDate);

export const getYearlyReturnsForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getYearlyReturns(scope.id) : getAggregateYearlyReturns(scope.ids);

export const getDrawdownForScope = (scope: PortfolioScope, startDate?: string, endDate?: string) =>
  scope.mode === 'single'
    ? getDrawdown(scope.id, startDate, endDate)
    : getAggregateDrawdown(scope.ids, startDate, endDate);

export const getRollingWindowsForScope = (
  scope: PortfolioScope,
  windowMonths = 12,
  riskFreeRate = 2,
  startDate?: string,
  endDate?: string,
) =>
  scope.mode === 'single'
    ? getRollingWindows(scope.id, windowMonths, riskFreeRate, startDate, endDate)
    : getAggregateRollingWindows(scope.ids, windowMonths, riskFreeRate, startDate, endDate);

export const getHallOfFameForScope = (scope: PortfolioScope, topN = 5, startDate?: string, endDate?: string) =>
  scope.mode === 'single'
    ? getHallOfFame(scope.id, topN, startDate, endDate)
    : getAggregateHallOfFame(scope.ids, topN, startDate, endDate);

export const getPortfolioHealthForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getPortfolioHealth(scope.id) : getAggregatePortfolioHealth(scope.ids);

export const getMonteCarloProjectionForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getMonteCarloProjection(scope.id) : getAggregateMonteCarloProjection(scope.ids);

export const getStressTestForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getStressTest(scope.id) : getAggregateStressTest(scope.ids);

export const getPortfolioXrayForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getPortfolioXray(scope.id) : getAggregatePortfolioXray(scope.ids);

export type DecumulationPlanParams = {
  annualWithdrawal: number;
  years: number;
  inflationRatePct?: number;
  otherIncomeAnnual?: number;
  capitalGainsTaxRatePct?: number;
  currentAge?: number | null;
} & DecumulationScheduleParams;

/**
 * The aggregate decumulation response has `portfolio_ids` and `base_currency`
 * instead of `portfolio_id`; the projection fields are the same.
 */
export const getDecumulationPlanForScope = (
  scope: PortfolioScope,
  params: DecumulationPlanParams,
): Promise<DecumulationPlanResponse | AggregateDecumulationPlanResponse> =>
  scope.mode === 'single' ? getDecumulationPlan(scope.id, params) : getAggregateDecumulationPlan(scope.ids, params);

export const getPortfolioMarkdownForScope = (scope: PortfolioScope) =>
  scope.mode === 'single' ? getPortfolioMarkdown(scope.id) : getAggregatePortfolioMarkdown(scope.ids);
