import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { getAdminPortfolios, type Portfolio } from '../services/api';
import { PortfolioScopeProvider, readStoredPortfolioScope, usePortfolioScope } from './PortfolioScopeContext';

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/api')>()),
  getAdminPortfolios: vi.fn(),
}));

const portfoliosMock = vi.mocked(getAdminPortfolios);

const portfolio = (id: number, base_currency = 'EUR'): Portfolio => ({
  id,
  name: `P${id}`,
  base_currency,
  timezone: 'Europe/Rome',
  target_notional: null,
  cash_balance: 0,
  created_at: '2026-01-01T00:00:00Z',
});

const PORTFOLIOS = [portfolio(1), portfolio(2), portfolio(3, 'USD'), portfolio(4)];

function setup(list: Portfolio[] = PORTFOLIOS) {
  portfoliosMock.mockResolvedValue(list);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <PortfolioScopeProvider>{children}</PortfolioScopeProvider>
    </QueryClientProvider>
  );
  const view = renderHook(() => usePortfolioScope(), { wrapper });
  return { ...view, queryClient };
}

async function setupReady(list?: Portfolio[]) {
  const view = setup(list);
  await waitFor(() => expect(view.result.current.isReady).toBe(true));
  return view;
}

const storedScope = () => JSON.parse(window.localStorage.getItem(STORAGE_KEYS.portfolioScope) ?? 'null');

describe('PortfolioScopeContext', () => {
  beforeEach(() => {
    window.localStorage.clear();
    portfoliosMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('defaults to the first portfolio and persists it', async () => {
    const { result } = await setupReady();
    expect(result.current.scope).toEqual({ mode: 'single', id: 1 });
    expect(result.current.isAggregate).toBe(false);
    expect(result.current.baseCurrency).toBe('EUR');
    expect(storedScope()).toEqual({ mode: 'single', id: 1 });
  });

  it('migrates the selected portfolio of the pages', async () => {
    window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, '4');
    expect(readStoredPortfolioScope()).toEqual({ mode: 'single', id: 4 });
    const { result } = await setupReady();
    expect(result.current.scope).toEqual({ mode: 'single', id: 4 });
  });

  it('migrates the FIRE aggregate selection when FIRE was in aggregate mode', async () => {
    window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, '4');
    window.localStorage.setItem(STORAGE_KEYS.fireScopeMode, 'aggregate');
    window.localStorage.setItem(STORAGE_KEYS.fireAggregatePortfolioIds, JSON.stringify(['2', '1']));
    const { result } = await setupReady();
    expect(result.current.scope).toEqual({ mode: 'aggregate', ids: [1, 2] });
    expect(result.current.isAggregate).toBe(true);
    expect(result.current.selectedPortfolios.map((item) => item.id)).toEqual([1, 2]);
    expect(storedScope()).toEqual({ mode: 'aggregate', ids: [1, 2] });
  });

  it('ignores the FIRE selection when FIRE was in single mode', () => {
    window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, '4');
    window.localStorage.setItem(STORAGE_KEYS.fireScopeMode, 'single');
    window.localStorage.setItem(STORAGE_KEYS.fireAggregatePortfolioIds, JSON.stringify(['2', '1']));
    expect(readStoredPortfolioScope()).toEqual({ mode: 'single', id: 4 });
  });

  it('prefers the shared key over the legacy ones and survives corrupt JSON', () => {
    window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, '4');
    window.localStorage.setItem(STORAGE_KEYS.portfolioScope, JSON.stringify({ mode: 'aggregate', ids: [2, 1] }));
    expect(readStoredPortfolioScope()).toEqual({ mode: 'aggregate', ids: [1, 2] });
    window.localStorage.setItem(STORAGE_KEYS.portfolioScope, '{not json');
    expect(readStoredPortfolioScope()).toEqual({ mode: 'single', id: 4 });
  });

  it('sanitizes the stored scope: deleted ids and other currencies dropped', async () => {
    window.localStorage.setItem(STORAGE_KEYS.portfolioScope, JSON.stringify({ mode: 'aggregate', ids: [1, 3, 4, 99] }));
    const { result } = await setupReady();
    expect(result.current.scope).toEqual({ mode: 'aggregate', ids: [1, 4] });
    expect(storedScope()).toEqual({ mode: 'aggregate', ids: [1, 4] });
  });

  it('cleans up when a portfolio of the scope is deleted, back to single with one left', async () => {
    window.localStorage.setItem(STORAGE_KEYS.portfolioScope, JSON.stringify({ mode: 'aggregate', ids: [1, 2] }));
    window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, '2');
    const { result, queryClient } = await setupReady();
    expect(result.current.scope).toEqual({ mode: 'aggregate', ids: [1, 2] });

    act(() => {
      queryClient.setQueryData(['portfolios'], PORTFOLIOS.filter((item) => item.id !== 2));
    });
    await waitFor(() => expect(result.current.scope).toEqual({ mode: 'single', id: 1 }));
    expect(storedScope()).toEqual({ mode: 'single', id: 1 });
    // Sanitizing never rewrites the pages' own key.
    expect(window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId)).toBe('2');
  });

  it('falls back to the first portfolio when every portfolio of the scope is gone', async () => {
    window.localStorage.setItem(STORAGE_KEYS.portfolioScope, JSON.stringify({ mode: 'aggregate', ids: [7, 8] }));
    const { result } = await setupReady();
    expect(result.current.scope).toEqual({ mode: 'single', id: 1 });
  });

  it('has no scope without portfolios', async () => {
    const { result } = await setupReady([]);
    expect(result.current.scope).toBeNull();
    expect(result.current.selectedPortfolios).toEqual([]);
  });

  it('switches between single and aggregate and keeps the legacy key for single', async () => {
    const { result } = await setupReady();

    act(() => result.current.toggleInAggregate(2));
    expect(result.current.scope).toEqual({ mode: 'aggregate', ids: [1, 2] });
    expect(storedScope()).toEqual({ mode: 'aggregate', ids: [1, 2] });

    // Other base currency: not added.
    act(() => result.current.toggleInAggregate(3));
    expect(result.current.scope).toEqual({ mode: 'aggregate', ids: [1, 2] });
    expect(result.current.availableForAggregate().map((item) => item.id)).toEqual([1, 2, 4]);

    act(() => result.current.setAggregate([4, 1, 3]));
    expect(result.current.scope).toEqual({ mode: 'aggregate', ids: [1, 4] });

    act(() => result.current.toggleInAggregate(1));
    expect(result.current.scope).toEqual({ mode: 'single', id: 4 });
    expect(window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId)).toBe('4');

    act(() => result.current.setSingle(2));
    expect(result.current.scope).toEqual({ mode: 'single', id: 2 });
    expect(window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId)).toBe('2');
    expect(storedScope()).toEqual({ mode: 'single', id: 2 });
  });

  it('works when localStorage throws on every access', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readStoredPortfolioScope()).toBeNull();

    const { result } = await setupReady();
    expect(result.current.scope).toEqual({ mode: 'single', id: 1 });
    act(() => result.current.toggleInAggregate(2));
    expect(result.current.scope).toEqual({ mode: 'aggregate', ids: [1, 2] });
  });

  it('throws outside the provider', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => usePortfolioScope())).toThrow(/PortfolioScopeProvider/);
  });
});
