import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import {
  backfillPortfolioDailyPrices,
  getMarketCalendar,
  getMarketNews,
  getMarketQuotes,
  refreshPortfolioPrices,
} from '../../../services/api';
import { useDashboardRefresh } from './useDashboardRefresh';

vi.mock('../../../services/api', () => ({
  refreshPortfolioPrices: vi.fn(),
  backfillPortfolioDailyPrices: vi.fn(),
  getMarketQuotes: vi.fn(),
  getMarketNews: vi.fn(),
  getMarketCalendar: vi.fn(),
}));

const refreshMock = vi.mocked(refreshPortfolioPrices);
const backfillMock = vi.mocked(backfillPortfolioDailyPrices);
const quotesMock = vi.mocked(getMarketQuotes);
const newsMock = vi.mocked(getMarketNews);
const calendarMock = vi.mocked(getMarketCalendar);

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

const fireRefresh = () => {
  act(() => {
    window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard'));
  });
};

describe('useDashboardRefresh', () => {
  beforeEach(() => {
    refreshMock.mockReset();
    backfillMock.mockReset();
    quotesMock.mockReset().mockResolvedValue({ categories: [] } as unknown as Awaited<ReturnType<typeof getMarketQuotes>>);
    newsMock.mockReset().mockResolvedValue({ items: [] } as unknown as Awaited<ReturnType<typeof getMarketNews>>);
    calendarMock.mockReset().mockResolvedValue({ days: [] } as unknown as Awaited<ReturnType<typeof getMarketCalendar>>);
  });

  it('reloads the Mercati data with the prices, even when that tab is closed', async () => {
    refreshMock.mockResolvedValue({ refreshed_assets: 3, requested_assets: 3 } as Awaited<ReturnType<typeof refreshPortfolioPrices>>);
    backfillMock.mockResolvedValue({ assets_refreshed: 3, assets_requested: 3 } as Awaited<ReturnType<typeof backfillPortfolioDailyPrices>>);

    const { result } = renderHook(() => useDashboardRefresh(26), { wrapper });
    fireRefresh();
    await waitFor(() => expect(result.current.refreshing).toBe(false));

    await waitFor(() => expect(quotesMock).toHaveBeenCalledTimes(1));
    expect(newsMock).toHaveBeenCalledTimes(1);
    expect(calendarMock).toHaveBeenCalledWith(3);
  });

  it('ignores refresh requests while one is running', async () => {
    let finishRefresh: (value: Awaited<ReturnType<typeof refreshPortfolioPrices>>) => void = () => {};
    refreshMock.mockImplementation(() => new Promise((resolve) => { finishRefresh = resolve; }));
    backfillMock.mockResolvedValue({ assets_refreshed: 14, assets_requested: 14 } as Awaited<ReturnType<typeof backfillPortfolioDailyPrices>>);

    const { result } = renderHook(() => useDashboardRefresh(26), { wrapper });

    // Refresh button, then pull-to-refresh and auto-refresh while it runs.
    fireRefresh();
    fireRefresh();
    fireRefresh();
    expect(refreshMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      finishRefresh({ refreshed_assets: 14, requested_assets: 14 } as Awaited<ReturnType<typeof refreshPortfolioPrices>>);
    });
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    expect(backfillMock).toHaveBeenCalledTimes(1);

    // Once it is over, the next request runs again.
    refreshMock.mockResolvedValue({ refreshed_assets: 14, requested_assets: 14 } as Awaited<ReturnType<typeof refreshPortfolioPrices>>);
    fireRefresh();
    await waitFor(() => expect(result.current.refreshing).toBe(false));
    expect(refreshMock).toHaveBeenCalledTimes(2);
  });
});
