import { screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioHealthResponse } from '../services/api';
import { PENDING, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis } from '../test/pageHarness';
import { DoctorPage } from './Doctor.page';

const health = (ids: number[] | null): PortfolioHealthResponse => ({
  portfolio_id: ids ? 0 : 1,
  portfolio_ids: ids,
  score: 70,
  summary: { risk_level: 'medium', diversification: 'good', overlap: 'low', cost_efficiency: 'low_cost' },
  metrics: {
    geographic_exposure: {}, sector_exposure: {}, max_position_weight: 20, overlap_score: 10,
    portfolio_volatility: 10, weighted_ter: 0.2,
  },
  category_scores: { diversification: 20, risk: 20, concentration: 15, overlap: 10, cost_efficiency: 12 },
  alerts: [],
  suggestions: [],
});

const SUMMARY = {
  available: true,
  run_finished_at: '2026-11-11T00:05:00+00:00',
  checks_passed: 1,
  checks_in_review: 1,
  areas: [
    { area: 'costs', label: 'Costi', status: 'in_review', checks: [{ title: 'Costo coerente', status: 'in_review' }] },
    { area: 'stress', label: 'Stress test', status: 'passed', checks: [{ title: 'Shock previsto', status: 'passed' }] },
  ],
};

describe('Doctor page: audit indicator', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
  });
  afterEach(() => vi.unstubAllGlobals());

  const route = (aggregate: boolean) => (request: { path: string }) => {
    if (/\/health(\?|$)/.test(request.path)) return health(aggregate ? [1, 2] : null);
    if (/\/(xray|monte-carlo|stress-test)(\?|$)/.test(request.path)) return PENDING;
    if (request.path.startsWith('/doctor/auditor/summary')) return SUMMARY;
    return undefined;
  };

  it('asks for the single portfolio and shows the indicator', async () => {
    storeScope({ mode: 'single', id: 1 });
    const mock = installFetchMock([portfolio(1, 'Core'), portfolio(2, 'Satellite')], route(false));
    renderWithApp(<DoctorPage />, { route: '/doctor' });
    expect(await screen.findByTestId('audit-indicator')).toHaveTextContent('Calcoli verificati: 1 controllo superato');
    expect(screen.getByTestId('audit-indicator-review')).toHaveTextContent("Un calcolo è in verifica nell'area Costi");
    expect(mock.paths()).toContain('/doctor/auditor/summary?portfolio_ids=1');
    expect(mock.writes()).toEqual([]);
  });

  it('asks for every portfolio of the aggregate view', async () => {
    storeScope({ mode: 'aggregate', ids: [2, 1] });
    const mock = installFetchMock([portfolio(1, 'Core'), portfolio(2, 'Satellite')], route(true));
    renderWithApp(<DoctorPage />, { route: '/doctor' });
    expect(await screen.findByTestId('audit-indicator')).toBeInTheDocument();
    await waitFor(() => expect(mock.paths()).toContain('/doctor/auditor/summary?portfolio_ids=1&portfolio_ids=2'));
  });

  it('shows nothing when the backend says no recent run', async () => {
    storeScope({ mode: 'single', id: 1 });
    installFetchMock([portfolio(1, 'Core')], (request) => {
      if (request.path.startsWith('/doctor/auditor/summary')) {
        return { available: false, run_finished_at: null, checks_passed: 0, checks_in_review: 0, areas: [] };
      }
      return route(false)(request);
    });
    renderWithApp(<DoctorPage />, { route: '/doctor' });
    expect(await screen.findByText('Segnali principali')).toBeInTheDocument();
    expect(screen.queryByTestId('audit-indicator')).toBeNull();
  });
});
