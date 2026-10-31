import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { PENDING, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis } from '../test/pageHarness';
import { DashboardPage } from './Dashboard.page';

const PORTFOLIOS = [portfolio(1, 'Core'), portfolio(2, 'Pensione'), portfolio(3, 'Dollari', 'USD')];
const AGG = 'portfolio_ids=1&portfolio_ids=2';

describe('DashboardPage in the aggregate view', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads the overview from the aggregate endpoints, never from a single portfolio', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    const api = installFetchMock(PORTFOLIOS);
    renderWithApp(<DashboardPage />);

    await waitFor(() => expect(api.paths()).toContain(`/portfolios/aggregate/summary?${AGG}`));
    await waitFor(() => expect(api.paths()).toContain(`/portfolios/aggregate/positions?${AGG}`));
    expect(api.paths()).toContain(`/portfolios/aggregate/timeseries?${AGG}&range=1y&interval=1d`);
    expect(api.paths().some((path) => path.startsWith('/portfolios/aggregate/performers?'))).toBe(true);
    // Per-portfolio data (target performance) is not asked for in aggregate.
    expect(api.paths().some((path) => /^\/portfolios\/\d+\//.test(path))).toBe(false);
    expect(screen.getAllByText('Aggregato (2)').length).toBeGreaterThan(0);
  });

  it('uses the aggregate performance endpoints on the Performance tab', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    window.localStorage.setItem(STORAGE_KEYS.activeTab, 'performance');
    // Only which endpoints are called matters here: their answers never arrive.
    const api = installFetchMock(PORTFOLIOS, (request) => (request.path.includes('/performance/') ? PENDING : undefined));
    renderWithApp(<DashboardPage />);

    await waitFor(() => expect(api.paths().some((path) => path.startsWith(`/portfolios/aggregate/performance/summary?${AGG}`))).toBe(true));
    expect(api.paths().some((path) => path.startsWith(`/portfolios/aggregate/performance/twr/timeseries?${AGG}`))).toBe(true);
    expect(api.paths().some((path) => /^\/portfolios\/\d+\//.test(path))).toBe(false);
  });

  it('disables reclassify on the Posizioni tab and asks for no target weights', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    window.localStorage.setItem(STORAGE_KEYS.activeTab, 'posizioni');
    const api = installFetchMock(PORTFOLIOS, (request) => (
      request.path.startsWith('/portfolios/aggregate/positions')
        ? [{
          asset_id: 10, symbol: 'VWCE', name: 'All World', asset_type: 'etf', quantity: 3, avg_cost: 100,
          market_price: 110, market_value: 330, unrealized_pl: 30, unrealized_pl_pct: 10, day_change_pct: 0.2,
          weight: 100, first_trade_at: null, price_stale: false,
        }]
        : undefined
    ));
    renderWithApp(<DashboardPage />);

    const reclassify = await screen.findByRole('button', { name: 'Reclassifica tipi' });
    expect(reclassify).toBeDisabled();
    expect(reclassify.closest('[data-aggregate-read-only]')).not.toBeNull();
    expect(api.paths().some((path) => path.includes('target-allocation'))).toBe(false);
    fireEvent.click(reclassify);
    expect(api.writes()).toEqual([]);
  });

  it('keeps the single-portfolio URLs for a single scope', async () => {
    storeScope({ mode: 'single', id: 2 });
    const api = installFetchMock(PORTFOLIOS);
    renderWithApp(<DashboardPage />);

    await waitFor(() => expect(api.paths()).toContain('/portfolios/2/summary'));
    expect(api.paths()).toContain('/portfolios/2/target-performance');
    expect(api.paths().some((path) => path.includes('/aggregate/'))).toBe(false);
  });
});
