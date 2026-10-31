import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  backfillPortfolioDailyPrices,
  getMarketCalendar,
  getMarketNews,
  getMarketQuotes,
  refreshPortfolioPrices,
} from '../../../services/api';
import { invalidatePortfolioQueries } from './invalidation';
import { matchesRefreshedPortfolios, useDashboardRefresh } from './useDashboardRefresh';

vi.mock('../../../services/api', () => ({
  refreshPortfolioPrices: vi.fn(),
  backfillPortfolioDailyPrices: vi.fn(),
  getMarketQuotes: vi.fn(),
  getMarketNews: vi.fn(),
  getMarketCalendar: vi.fn(),
}));

const refreshMock = vi.mocked(refreshPortfolioPrices);
const backfillMock = vi.mocked(backfillPortfolioDailyPrices);

function seededClient() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const keys = [
    ['portfolio-summary', 1],
    ['portfolio-summary', 3],
    ['portfolio-summary', 'aggregate:1,2'],
    ['portfolio-positions', 'aggregate:2,3'],
    ['portfolio-summary', 'aggregate:3,4'],
    ['target-allocation', null],
    ['portfolio-transactions', 'aggregate:1,2'],
    ['user-settings'],
  ];
  for (const key of keys) queryClient.setQueryData(key, { seeded: true });
  return queryClient;
}

const invalidated = (queryClient: QueryClient, key: unknown[]) => queryClient.getQueryState(key)?.isInvalidated ?? false;

describe('matchesRefreshedPortfolios', () => {
  it('matches single entries and aggregates that include a refreshed portfolio', () => {
    expect(matchesRefreshedPortfolios(['portfolio-summary', 1], [1, 2])).toBe(true);
    expect(matchesRefreshedPortfolios(['portfolio-summary', 'aggregate:1,2'], [1, 2])).toBe(true);
    expect(matchesRefreshedPortfolios(['portfolio-summary', 'aggregate:2,3'], [1])).toBe(false);
    expect(matchesRefreshedPortfolios(['portfolio-summary', 'aggregate:2,3'], [3])).toBe(true);
    expect(matchesRefreshedPortfolios(['portfolio-summary', 4], [1, 2])).toBe(false);
    // Keys without a portfolio (market data, per-portfolio hooks off in aggregate).
    expect(matchesRefreshedPortfolios(['market-quotes'], [1])).toBe(true);
    // Not price data.
    expect(matchesRefreshedPortfolios(['user-settings'], [1])).toBe(false);
  });
});

describe('useDashboardRefresh with an aggregate scope', () => {
  beforeEach(() => {
    refreshMock.mockReset().mockResolvedValue({ refreshed_assets: 2, requested_assets: 3 } as Awaited<ReturnType<typeof refreshPortfolioPrices>>);
    backfillMock.mockReset().mockResolvedValue({ assets_refreshed: 1, assets_requested: 2 } as Awaited<ReturnType<typeof backfillPortfolioDailyPrices>>);
    vi.mocked(getMarketQuotes).mockResolvedValue({ categories: [] } as unknown as Awaited<ReturnType<typeof getMarketQuotes>>);
    vi.mocked(getMarketNews).mockResolvedValue({ items: [] } as unknown as Awaited<ReturnType<typeof getMarketNews>>);
    vi.mocked(getMarketCalendar).mockResolvedValue({ days: [] } as unknown as Awaited<ReturnType<typeof getMarketCalendar>>);
  });

  it('refreshes every portfolio of the aggregate and invalidates the aggregate queries', async () => {
    const queryClient = seededClient();
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useDashboardRefresh({ mode: 'aggregate', ids: [1, 2] }), { wrapper });

    act(() => { window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard')); });
    await waitFor(() => expect(result.current.refreshMessage).not.toBeNull());

    expect(refreshMock.mock.calls.map(([id]) => id)).toEqual([1, 2]);
    expect(backfillMock.mock.calls.map(([id]) => id)).toEqual([1, 2]);
    expect(result.current.refreshMessage).toBe('Aggiornati prezzi: 4/6, storico: 2/4');

    expect(invalidated(queryClient, ['portfolio-summary', 'aggregate:1,2'])).toBe(true);
    expect(invalidated(queryClient, ['portfolio-positions', 'aggregate:2,3'])).toBe(true);
    expect(invalidated(queryClient, ['portfolio-summary', 1])).toBe(true);
    expect(invalidated(queryClient, ['target-allocation', null])).toBe(true);
    expect(invalidated(queryClient, ['portfolio-summary', 3])).toBe(false);
    expect(invalidated(queryClient, ['portfolio-summary', 'aggregate:3,4'])).toBe(false);
    expect(invalidated(queryClient, ['user-settings'])).toBe(false);
  });

  it('after a single-portfolio refresh also marks stale the aggregates that include it', async () => {
    const queryClient = seededClient();
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useDashboardRefresh(3), { wrapper });

    act(() => { window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard')); });
    await waitFor(() => expect(result.current.refreshMessage).not.toBeNull());

    expect(refreshMock.mock.calls.map(([id]) => id)).toEqual([3]);
    expect(invalidated(queryClient, ['portfolio-summary', 3])).toBe(true);
    expect(invalidated(queryClient, ['portfolio-positions', 'aggregate:2,3'])).toBe(true);
    expect(invalidated(queryClient, ['portfolio-summary', 'aggregate:3,4'])).toBe(true);
    expect(invalidated(queryClient, ['portfolio-summary', 'aggregate:1,2'])).toBe(false);
    expect(invalidated(queryClient, ['portfolio-summary', 1])).toBe(false);
  });
});

describe('invalidatePortfolioQueries', () => {
  it('marks stale the portfolio and the aggregates including it, nothing else', async () => {
    const queryClient = seededClient();
    await invalidatePortfolioQueries(queryClient, [2]);

    expect(invalidated(queryClient, ['portfolio-summary', 'aggregate:1,2'])).toBe(true);
    expect(invalidated(queryClient, ['portfolio-transactions', 'aggregate:1,2'])).toBe(true);
    expect(invalidated(queryClient, ['portfolio-positions', 'aggregate:2,3'])).toBe(true);
    expect(invalidated(queryClient, ['portfolio-summary', 1])).toBe(false);
    expect(invalidated(queryClient, ['portfolio-summary', 'aggregate:3,4'])).toBe(false);
    // Keys without a portfolio are not touched by a write to one portfolio.
    expect(invalidated(queryClient, ['target-allocation', null])).toBe(false);
    expect(invalidated(queryClient, ['user-settings'])).toBe(false);
  });
});
