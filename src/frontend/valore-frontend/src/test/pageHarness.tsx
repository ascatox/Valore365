import type { ReactNode } from 'react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { PortfolioScopeProvider } from '../scope/PortfolioScopeContext';
import type { PortfolioScope } from '../scope/portfolioScope';
import type { Portfolio, PortfolioSummary } from '../services/api';

// Page tests run the real pages, hooks and API client against a stubbed
// `fetch`: every request is recorded (method + path), so a test can assert
// which endpoints a page used (single vs aggregate) and that no write call
// (POST/PUT/PATCH/DELETE) went out.

export interface RecordedRequest {
  method: string;
  /** Path after the API base, with the query string (e.g. `/portfolios/aggregate/summary?portfolio_ids=1`). */
  path: string;
}

/** A route answer: a JSON body, or `PENDING` for a request that never resolves. */
export const PENDING = Symbol('pending');
export type RouteHandler = (request: RecordedRequest) => unknown;

export const portfolio = (id: number, name: string, base_currency = 'EUR'): Portfolio => ({
  id,
  name,
  base_currency,
  timezone: 'Europe/Rome',
  target_notional: null,
  cash_balance: 100,
  created_at: '2026-01-01T00:00:00Z',
});

export const summary = (portfolio_id: number, overrides: Partial<PortfolioSummary> = {}): PortfolioSummary => ({
  portfolio_id,
  base_currency: 'EUR',
  market_value: 1000,
  cost_basis: 900,
  unrealized_pl: 100,
  unrealized_pl_pct: 11.1,
  day_change: 5,
  day_change_pct: 0.5,
  cash_balance: 50,
  ...overrides,
});

const LIST_RESOURCE = /\/(positions|performers|timeseries|intraday-timeseries|transactions|allocation|target-allocation|benchmarks)(\?|$)/;

/** Default answers: lists for list resources, a summary, Copilot off, `{}` otherwise. */
function defaultAnswer(request: RecordedRequest, portfolios: Portfolio[]): unknown {
  const path = request.path.split('?')[0];
  if (path === '/portfolios') return portfolios;
  if (path === '/copilot/status') return { available: false };
  if (path === '/settings/user') return {};
  if (path.endsWith('/summary') && !path.includes('/performance/')) {
    const single = path.match(/^\/portfolios\/(\d+)\/summary$/);
    return summary(single ? Number(single[1]) : 0);
  }
  if (LIST_RESOURCE.test(path)) return [];
  return {};
}

export function installFetchMock(portfolios: Portfolio[], handler?: RouteHandler) {
  const requests: RecordedRequest[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(/^https?:\/\/[^/]+/, '').replace(/^\/api/, '');
    const request = { method: (init?.method ?? 'GET').toUpperCase(), path };
    requests.push(request);
    const custom = handler?.(request);
    if (custom === PENDING) return new Promise<Response>(() => {});
    const body = custom !== undefined ? custom : defaultAnswer(request, portfolios);
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  return {
    requests,
    paths: (method = 'GET') => requests.filter((request) => request.method === method).map((request) => request.path),
    writes: () => requests.filter((request) => request.method !== 'GET'),
  };
}

export function storeScope(scope: PortfolioScope) {
  window.localStorage.setItem(STORAGE_KEYS.portfolioScope, JSON.stringify(scope));
}

/** jsdom lacks what Mantine/Recharts measure with. */
export function stubLayoutApis() {
  if (!('ResizeObserver' in window)) {
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    });
  }
  if (!window.HTMLElement.prototype.scrollTo) {
    window.HTMLElement.prototype.scrollTo = () => {};
  }
}

export function renderWithApp(ui: ReactNode, { route = '/' }: { route?: string } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <MantineProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>
          <PortfolioScopeProvider>{ui}</PortfolioScopeProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
  return { ...view, queryClient };
}
