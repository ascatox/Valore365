import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioScope } from '../../scope/portfolioScope';
import {
  aggregatePath,
  buildPortfolioIdsQuery,
  getAggregatePortfolioTransactions,
  getDecumulationPlanForScope,
  getDrawdownForScope,
  getHallOfFameForScope,
  getPerformanceSummaryForScope,
  getPortfolioDataCoverageForScope,
  getPortfolioHealthForScope,
  getPortfolioPerformersForScope,
  getPortfolioSummaryForScope,
  getPortfolioTimeseriesForScope,
  getRollingWindowsForScope,
  getTWRTimeseriesForScope,
} from './aggregate';

const fetchMock = vi.fn();

function requestedPath(call = 0): string {
  const url = String(fetchMock.mock.calls[call][0]);
  return url.replace(/^.*?\/api/, '');
}

describe('aggregate API client', () => {
  beforeEach(() => {
    fetchMock.mockReset().mockImplementation(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('repeats portfolio_ids once per id, sorted and unique, before the other params', () => {
    expect(buildPortfolioIdsQuery([3, 1, 3], { days: 7, skip: undefined, empty: null }).toString())
      .toBe('portfolio_ids=1&portfolio_ids=3&days=7');
    expect(aggregatePath('performance/twr/timeseries', [2, 1], { start_date: '2026-01-01' }))
      .toBe('/portfolios/aggregate/performance/twr/timeseries?portfolio_ids=1&portfolio_ids=2&start_date=2026-01-01');
  });

  it('uses the single routes, unchanged, for a single scope', async () => {
    const single: PortfolioScope = { mode: 'single', id: 5 };
    await getPortfolioSummaryForScope(single);
    await getPortfolioPerformersForScope(single, 30);
    await getTWRTimeseriesForScope(single, '2026-01-01');
    await getPortfolioTimeseriesForScope(single);
    expect(requestedPath(0)).toBe('/portfolios/5/summary');
    expect(requestedPath(1)).toBe('/portfolios/5/performers?days=30');
    expect(requestedPath(2)).toBe('/portfolios/5/performance/twr/timeseries?start_date=2026-01-01');
    expect(requestedPath(3)).toBe('/portfolios/5/timeseries?range=1y&interval=1d');
  });

  it('uses the aggregate routes with the same params for an aggregate scope', async () => {
    const aggregate: PortfolioScope = { mode: 'aggregate', ids: [4, 2] };
    await getPortfolioSummaryForScope(aggregate);
    await getPortfolioPerformersForScope(aggregate, 30);
    await getPortfolioTimeseriesForScope(aggregate);
    await getPortfolioDataCoverageForScope(aggregate);
    await getPerformanceSummaryForScope(aggregate, 'ytd');
    await getTWRTimeseriesForScope(aggregate);
    await getDrawdownForScope(aggregate, '2025-01-01');
    await getRollingWindowsForScope(aggregate, 24, 2);
    await getHallOfFameForScope(aggregate, 3);
    await getPortfolioHealthForScope(aggregate);
    await getAggregatePortfolioTransactions([2, 4]);

    const ids = 'portfolio_ids=2&portfolio_ids=4';
    expect(fetchMock.mock.calls.map((_, index) => requestedPath(index))).toEqual([
      `/portfolios/aggregate/summary?${ids}`,
      `/portfolios/aggregate/performers?${ids}&days=30`,
      `/portfolios/aggregate/timeseries?${ids}&range=1y&interval=1d`,
      `/portfolios/aggregate/data-coverage?${ids}&days=365&threshold_pct=80`,
      `/portfolios/aggregate/performance/summary?${ids}&period=ytd`,
      `/portfolios/aggregate/performance/twr/timeseries?${ids}`,
      `/portfolios/aggregate/performance/drawdown?${ids}&start_date=2025-01-01`,
      `/portfolios/aggregate/performance/rolling-windows?${ids}&window_months=24&risk_free_rate=2`,
      `/portfolios/aggregate/performance/hall-of-fame?${ids}&top_n=3`,
      `/portfolios/aggregate/health?${ids}`,
      `/portfolios/aggregate/transactions?${ids}`,
    ]);
  });

  it('routes the decumulation plan by scope', async () => {
    const params = { annualWithdrawal: 20000, years: 30 };
    await getDecumulationPlanForScope({ mode: 'single', id: 5 }, params);
    await getDecumulationPlanForScope({ mode: 'aggregate', ids: [1, 2] }, params);
    expect(requestedPath(0)).toMatch(/^\/portfolios\/5\/decumulation\?annual_withdrawal=20000&years=30/);
    expect(requestedPath(1)).toMatch(/^\/portfolios\/aggregate\/decumulation\?.*portfolio_ids=1&portfolio_ids=2/);
  });
});
