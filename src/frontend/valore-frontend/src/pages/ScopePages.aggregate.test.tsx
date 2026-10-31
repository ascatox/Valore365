import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { Link, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import type { PortfolioHealthResponse } from '../services/api';
import { PENDING, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis, summary } from '../test/pageHarness';
import { DashboardPage } from './Dashboard.page';
import { DoctorPage } from './Doctor.page';
import { FirePage } from './Fire.page';

const PORTFOLIOS = [portfolio(1, 'Core'), portfolio(2, 'Pensione'), portfolio(3, 'Dollari', 'USD')];
const AGG = 'portfolio_ids=1&portfolio_ids=2';

const health = (portfolioId: number): PortfolioHealthResponse => ({
  portfolio_id: portfolioId,
  portfolio_ids: portfolioId === 0 ? [1, 2] : null,
  score: 72,
  summary: { risk_level: 'medium', diversification: 'good', overlap: 'low', cost_efficiency: 'low_cost' },
  metrics: {
    geographic_exposure: { USA: 60, Europa: 40 },
    sector_exposure: { Tech: 30 },
    max_position_weight: 40,
    overlap_score: 10,
    portfolio_volatility: 12,
    weighted_ter: 0.2,
  },
  category_scores: { diversification: 15, risk: 15, concentration: 15, overlap: 15, cost_efficiency: 12 },
  alerts: [],
  suggestions: [],
});

// The Doctor cards under the report only need to have been asked for.
const DOCTOR_CARDS = /\/(xray|monte-carlo|stress-test)(\?|$)/;

describe('Doctor in the aggregate view', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('runs every analysis on the aggregate endpoints', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    const api = installFetchMock(PORTFOLIOS, (request) => {
      if (request.path === `/portfolios/aggregate/health?${AGG}`) return health(0);
      if (DOCTOR_CARDS.test(request.path)) return PENDING;
      return undefined;
    });
    renderWithApp(<DoctorPage />);

    await waitFor(() => expect(api.paths()).toContain(`/portfolios/aggregate/xray?${AGG}`));
    expect(api.paths()).toContain(`/portfolios/aggregate/summary?${AGG}`);
    expect(api.paths()).toContain(`/portfolios/aggregate/monte-carlo?${AGG}`);
    expect(api.paths()).toContain(`/portfolios/aggregate/stress-test?${AGG}`);
    expect(api.paths().some((path) => /^\/portfolios\/\d+\//.test(path))).toBe(false);
    expect(api.writes()).toEqual([]);
  });
});

describe('FIRE in the aggregate view', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('takes summary and Monte Carlo from the aggregate endpoints, without summing per portfolio', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    const api = installFetchMock(PORTFOLIOS, (request) => {
      if (request.path === `/portfolios/aggregate/summary?${AGG}`) {
        return { ...summary(0, { market_value: 150000, cash_balance: 10000 }), portfolio_ids: [1, 2] };
      }
      if (request.path.includes('monte-carlo')) return PENDING;
      return undefined;
    });
    renderWithApp(<FirePage />);

    await waitFor(() => expect(api.paths()).toContain(`/portfolios/aggregate/monte-carlo?${AGG}`));
    expect(api.paths()).toContain(`/portfolios/aggregate/summary?${AGG}`);
    // The old client-side aggregate asked each portfolio separately.
    expect(api.paths().some((path) => /^\/portfolios\/\d+\//.test(path))).toBe(false);
    // Net worth is the aggregate summary as is (market value + cash).
    expect((await screen.findAllByText(/Patrimonio attuale/)).some((node) => /160\.000/.test(node.textContent ?? ''))).toBe(true);
    expect(screen.getByText(/Perimetro FIRE aggregato · 2 portafogli inclusi/)).toBeInTheDocument();
    // The FIRE-only aggregate selection is gone (the shared switcher drives it).
    expect(screen.queryByRole('radio', { name: 'Aggregato' })).not.toBeInTheDocument();
    expect(window.localStorage.getItem(STORAGE_KEYS.fireAggregatePortfolioIds)).toBeNull();
  });

  it('plans the decumulation on the aggregate endpoint', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    window.localStorage.setItem(STORAGE_KEYS.fireMode, 'decumulation');
    const api = installFetchMock(PORTFOLIOS, (request) => {
      if (request.path === '/settings/user') return { fire_annual_expenses: 24000 };
      if (request.path.includes('monte-carlo') || request.path.includes('decumulation')) return PENDING;
      return undefined;
    });
    renderWithApp(<FirePage />);

    await waitFor(() => expect(api.paths().some((path) => path.startsWith('/portfolios/aggregate/decumulation?') && path.includes(AGG))).toBe(true));
    expect(api.paths().some((path) => /^\/portfolios\/\d+\/decumulation/.test(path))).toBe(false);
  });

  it('keeps the single-portfolio endpoints for a single scope', async () => {
    storeScope({ mode: 'single', id: 2 });
    const api = installFetchMock(PORTFOLIOS, (request) => (request.path.includes('monte-carlo') ? PENDING : undefined));
    renderWithApp(<FirePage />);

    await waitFor(() => expect(api.paths()).toContain('/portfolios/2/monte-carlo'));
    expect(api.paths()).toContain('/portfolios/2/summary');
    expect(api.paths().some((path) => path.includes('/aggregate/'))).toBe(false);
  });
});

describe('shared scope across pages', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('a portfolio chosen on the Dashboard is the one the Doctor opens with', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    const api = installFetchMock(PORTFOLIOS, (request) => {
      if (/\/health(\?|$)/.test(request.path)) return health(2);
      if (DOCTOR_CARDS.test(request.path)) return PENDING;
      return undefined;
    });
    renderWithApp(
      <>
        <Link to="/doctor">vai al doctor</Link>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/doctor" element={<DoctorPage />} />
        </Routes>
      </>,
    );

    await waitFor(() => expect(api.paths()).toContain(`/portfolios/aggregate/summary?${AGG}`));
    // Open the switcher and pick a single portfolio.
    fireEvent.click(screen.getAllByText('Vista aggregata')[0]);
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByText('Pensione'));

    await waitFor(() => expect(api.paths()).toContain('/portfolios/2/summary'));
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEYS.portfolioScope) ?? 'null')).toEqual({ mode: 'single', id: 2 });

    fireEvent.click(screen.getByText('vai al doctor'));
    await waitFor(() => expect(api.paths()).toContain('/portfolios/2/health'));
    expect(api.paths().some((path) => path.startsWith('/portfolios/aggregate/health'))).toBe(false);
  });
});
