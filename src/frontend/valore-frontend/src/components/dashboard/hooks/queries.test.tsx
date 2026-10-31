import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getAggregatePortfolioSummary,
  getPortfolioSummary,
  getPortfolioTargetAllocation,
  getRollingWindowsForScope,
  type PortfolioSummary,
} from '../../../services/api';
import { usePortfolioSummary, useRollingWindows, useTargetAllocation } from './queries';

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>();
  return {
    ...actual,
    // The scope wrappers pick the route; the leaf calls are mocked.
    getPortfolioSummaryForScope: vi.fn((scope) => (
      scope.mode === 'single' ? getPortfolioSummaryMock(scope.id) : getAggregateSummaryMock(scope.ids)
    )),
    getPortfolioSummary: vi.fn(),
    getAggregatePortfolioSummary: vi.fn(),
    getPortfolioTargetAllocation: vi.fn(),
    getRollingWindowsForScope: vi.fn(),
  };
});

const getPortfolioSummaryMock = (id: number) => vi.mocked(getPortfolioSummary)(id);
const getAggregateSummaryMock = (ids: number[]) => vi.mocked(getAggregatePortfolioSummary)(ids);

const summary = (portfolio_id: number) => ({ portfolio_id, base_currency: 'EUR', market_value: portfolio_id } as PortfolioSummary);

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const keys = () => queryClient.getQueryCache().getAll().map((query) => query.queryKey);
  return { queryClient, wrapper, keys };
}

describe('scope-aware query hooks', () => {
  beforeEach(() => {
    vi.mocked(getPortfolioSummary).mockReset().mockImplementation(async (id) => summary(id));
    vi.mocked(getAggregatePortfolioSummary).mockReset().mockResolvedValue(summary(0));
    vi.mocked(getPortfolioTargetAllocation).mockReset().mockResolvedValue([]);
    vi.mocked(getRollingWindowsForScope).mockReset().mockResolvedValue({
      portfolio_id: 0, window_months: 12, risk_free_rate_pct: 2, points: [],
    });
  });

  it('keeps the existing key for a bare id and for a single scope', async () => {
    const { wrapper, keys } = setup();
    const byId = renderHook(() => usePortfolioSummary(3), { wrapper });
    const byScope = renderHook(() => usePortfolioSummary({ mode: 'single', id: 3 }), { wrapper });
    await waitFor(() => expect(byId.result.current.data?.portfolio_id).toBe(3));
    await waitFor(() => expect(byScope.result.current.data?.portfolio_id).toBe(3));
    expect(keys()).toEqual([['portfolio-summary', 3]]);
    expect(getPortfolioSummary).toHaveBeenCalledTimes(1);
  });

  it('never shares cache entries between single and aggregate, whatever the id order', async () => {
    const { wrapper, keys } = setup();
    renderHook(() => usePortfolioSummary(1), { wrapper });
    const aggregate = renderHook(() => usePortfolioSummary({ mode: 'aggregate', ids: [2, 1] }), { wrapper });
    const sameAggregate = renderHook(() => usePortfolioSummary({ mode: 'aggregate', ids: [1, 2, 2] }), { wrapper });
    await waitFor(() => expect(aggregate.result.current.data?.portfolio_id).toBe(0));
    await waitFor(() => expect(sameAggregate.result.current.data?.portfolio_id).toBe(0));

    expect(keys()).toEqual([['portfolio-summary', 1], ['portfolio-summary', 'aggregate:1,2']]);
    expect(getAggregatePortfolioSummary).toHaveBeenCalledTimes(1);
    expect(getAggregatePortfolioSummary).toHaveBeenCalledWith([1, 2]);
  });

  it('includes the scope key next to the other params', async () => {
    const { wrapper, keys } = setup();
    const view = renderHook(() => useRollingWindows({ mode: 'aggregate', ids: [5, 4] }, 24, 2, '2025-01-01'), { wrapper });
    await waitFor(() => expect(view.result.current.isSuccess).toBe(true));
    expect(keys()).toEqual([['rolling-windows', 'aggregate:4,5', 24, 2, '2025-01-01']]);
    expect(getRollingWindowsForScope).toHaveBeenCalledWith({ mode: 'aggregate', ids: [4, 5] }, 24, 2, '2025-01-01');
  });

  it('stays idle without a scope', () => {
    const { wrapper } = setup();
    const view = renderHook(() => usePortfolioSummary(null), { wrapper });
    expect(view.result.current.fetchStatus).toBe('idle');
    expect(getPortfolioSummary).not.toHaveBeenCalled();
  });

  it('disables per-portfolio hooks (target allocation) for an aggregate scope', async () => {
    const { wrapper } = setup();
    const aggregate = renderHook(() => useTargetAllocation({ mode: 'aggregate', ids: [1, 2] }), { wrapper });
    expect(aggregate.result.current.fetchStatus).toBe('idle');
    const single = renderHook(() => useTargetAllocation(7), { wrapper });
    await waitFor(() => expect(single.result.current.isFetched).toBe(true));
    expect(getPortfolioTargetAllocation).toHaveBeenCalledTimes(1);
    expect(getPortfolioTargetAllocation).toHaveBeenCalledWith(7);
  });
});
