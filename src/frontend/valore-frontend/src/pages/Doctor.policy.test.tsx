import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioHealthResponse } from '../services/api';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { PENDING, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis } from '../test/pageHarness';
import { evaluation, policyRead, preview } from '../components/doctor/policy/testFixtures';
import { DoctorPage } from './Doctor.page';

const PORTFOLIOS = [portfolio(1, 'Core'), portfolio(2, 'Pensione')];

const health: PortfolioHealthResponse = {
  portfolio_id: 1,
  portfolio_ids: null,
  score: 72,
  summary: { risk_level: 'medium', diversification: 'good', overlap: 'low', cost_efficiency: 'low_cost' },
  metrics: {
    geographic_exposure: { usa: 60, europe: 30, emerging: 10 },
    sector_exposure: {},
    max_position_weight: 46.6,
    overlap_score: 10,
    portfolio_volatility: 12,
    weighted_ter: 0.2,
  },
  category_scores: { diversification: 15, risk: 15, concentration: 15, overlap: 15, cost_efficiency: 12 },
  alerts: [],
  suggestions: [],
};

const DOCTOR_CARDS = /\/(xray|monte-carlo|stress-test)(\?|$)/;

function mockDoctor(features: { policy_enabled: boolean; simulator_enabled: boolean }, extra?: (path: string, method: string) => unknown) {
  return installFetchMock(PORTFOLIOS, (request) => {
    const custom = extra?.(request.path, request.method);
    if (custom !== undefined) return custom;
    if (request.path === '/doctor/features') return features;
    if (request.path === '/doctor/metrics') return { metrics: [] };
    if (request.path === '/doctor/templates') return { templates: [] };
    if (request.path.startsWith('/doctor/policies?')) return { policy: policyRead() };
    if (request.path.startsWith('/doctor/evaluation?')) return evaluation();
    if (/\/health(\?|$)/.test(request.path)) return health;
    if (DOCTOR_CARDS.test(request.path)) return PENDING;
    return undefined;
  });
}

describe('Doctor 2.0 sections', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
    storeScope({ mode: 'single', id: 1 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('hides Parametri and Laboratorio when the backend flags are off', async () => {
    const api = mockDoctor({ policy_enabled: false, simulator_enabled: false });
    renderWithApp(<DoctorPage />, { route: '/doctor?section=parametri' });
    expect(await screen.findByText('Dettaglio metriche')).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /I miei parametri/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Laboratorio/ })).not.toBeInTheDocument();
    expect(screen.queryByTestId('policy-summary-card')).not.toBeInTheDocument();
    expect(api.paths().some((path) => path.startsWith('/doctor/evaluation'))).toBe(false);
    expect(api.writes()).toEqual([]);
  });

  it('shows the compliance card next to the score (two distinct cards) in Diagnosi', async () => {
    const api = mockDoctor({ policy_enabled: true, simulator_enabled: true });
    renderWithApp(<DoctorPage />, { route: '/doctor' });
    expect(await screen.findByRole('tab', { name: /Diagnosi/ })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByTestId('policy-summary-text')).toHaveTextContent('2 rispettati · 1 violato · 2 non verificabili');
    expect(screen.getByText('Dettaglio metriche')).toBeInTheDocument();
    expect(api.paths()).toContain('/doctor/evaluation?portfolio_ids=1');
    expect(api.writes()).toEqual([]);
  });

  it('deep-links to «I miei parametri» and opens the evidence of a rule', async () => {
    mockDoctor({ policy_enabled: true, simulator_enabled: true });
    renderWithApp(<DoctorPage />, { route: '/doctor?section=parametri' });
    expect(await screen.findByRole('tab', { name: /I miei parametri/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('policy-scope')).toHaveTextContent('Si applica a: Core');
    expect(screen.queryByText('Dettaglio metriche')).not.toBeInTheDocument();
    fireEvent.click(await screen.findByTestId('rule-card-max-single'));
    const evidence = await screen.findByTestId('policy-evidence');
    expect(within(evidence).getByText('VWRA 46,6%: supera il tuo limite 35% di 11,6 punti percentuali')).toBeInTheDocument();
  });

  it('masks € amounts in Privacy Mode on the evidence of a rule', async () => {
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
    mockDoctor({ policy_enabled: true, simulator_enabled: true });
    renderWithApp(<DoctorPage />, { route: '/doctor?section=parametri' });
    fireEvent.click(await screen.findByTestId('rule-card-max-single'));
    expect(await screen.findByTestId('evidence-denominator-value')).toHaveTextContent('******');
  });

  it('«Simula» on a rule opens the Laboratorio prefilled', async () => {
    mockDoctor({ policy_enabled: true, simulator_enabled: true });
    renderWithApp(<DoctorPage />, { route: '/doctor?section=parametri' });
    fireEvent.click(await screen.findByTestId('rule-card-max-single'));
    fireEvent.click(await screen.findByRole('button', { name: 'Simula' }));
    expect(await screen.findByTestId('lab-prefill')).toHaveTextContent('Simulazione avviata dalla regola «Max singolo ETF».');
    expect(screen.getByRole('tab', { name: /Laboratorio/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByDisplayValue('Rientro: Max singolo ETF')).toBeInTheDocument();
  });

  it('runs a Laboratorio scenario on the backend and shows the disclaimer', async () => {
    const api = mockDoctor({ policy_enabled: true, simulator_enabled: true }, (path) => {
      if (path === '/doctor/scenarios/preview') {
        return {
          label: 'Scenario A', feasible: false, infeasible_reason: 'Servono almeno 41.000 € di nuova liquidità senza vendite',
          before: { metrics: {}, evaluation_summary: null }, after: null, changes: [], warnings: [], violations_resolved: [], violations_new: [],
          required_new_cash: 41000, total_before: 125000, total_after: null, cash_in: 0,
          costs: { total: 0, variable: 0, fixed: 0, operations: 0, fee_model: { pct: 0, fixed: 0 } },
          methodology_version: 'doctor-policy-1.0', snapshot_id: 'abc123', data_quality: null, disclaimer: 'Simulazione teorica; nessun ordine eseguito.',
        };
      }
      return undefined;
    });
    renderWithApp(<DoctorPage />, { route: '/doctor?section=laboratorio' });
    fireEvent.click(await screen.findByRole('button', { name: 'Simula scenario' }));
    expect(await screen.findByText('Scenario A: non fattibile')).toBeInTheDocument();
    expect(screen.getByTestId('lab-disclaimer')).toHaveTextContent('Simulazione teorica; nessun ordine eseguito.');
    expect(screen.getByRole('link', { name: 'Traduci in ordini nella pagina Portfolio' })).toHaveAttribute('href', '/portfolio');
    await waitFor(() => expect(api.writes().map((request) => request.path)).toEqual(['/doctor/scenarios/preview']));
  });

  it('shows the comparison explanation with € amounts masked in Privacy Mode', async () => {
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
    const side = {
      invested_value: 125000, cash_value: 0, total_value: 125000, metrics: {}, evaluation_status: 'ready', evaluation_summary: null, rule_results: [],
      volatility: { value: null, status: 'not_available', reason: 'Non stimabile' },
    };
    const scenario = (label: string) => ({
      label, mode: 'new_cash_only', feasible: true, infeasible_code: null, infeasible_reason: null, before: side, after: side, changes: [], warnings: [],
      violations_resolved: [], violations_new: [], required_new_cash: null, total_before: 125000, total_after: 125000, cash_in: 0,
      costs: { total: 0, variable: 0, fixed: 0, operations: 0, fee_model: { pct: 0, fixed: 0 } }, turnover_pct: 0,
      methodology_version: 'doctor-policy-1.0', snapshot_id: 'abc123', data_quality: null, disclaimer: 'Simulazione teorica; nessun ordine eseguito.',
    });
    mockDoctor({ policy_enabled: true, simulator_enabled: true }, (path) => {
      if (path === '/doctor/scenarios/compare') {
        return {
          current: side, scenarios: [scenario('Scenario A'), scenario('Scenario B')],
          ranking: [
            { index: 0, label: 'Scenario A', rank: 1, feasible: true, failed_after: 0, unknown_after: 0, violations_resolved: 1, violations_new: 0, costs: 0, cash_in: 0, turnover_pct: 0 },
            { index: 1, label: 'Scenario B', rank: 2, feasible: true, failed_after: 1, unknown_after: 0, violations_resolved: 0, violations_new: 0, costs: 0, cash_in: 0, turnover_pct: 0 },
          ],
          best_index: 0, explanation: 'Scenario A risolve 1 regola con 41.000 € di nuova liquidità (peso VWRA 34,9%).',
          snapshot_id: 'abc123', methodology_version: 'doctor-policy-1.0', disclaimer: 'Simulazione teorica; nessun ordine eseguito.',
        };
      }
      return undefined;
    });
    renderWithApp(<DoctorPage />, { route: '/doctor?section=laboratorio' });
    fireEvent.click(await screen.findByRole('button', { name: 'Aggiungi scenario' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confronta scenari' }));
    expect(await screen.findByTestId('lab-explanation')).toHaveTextContent('Scenario A risolve 1 regola con ****** di nuova liquidità (peso VWRA 34,9%).');
    expect(screen.queryByText(/41\.000/)).not.toBeInTheDocument();
  });
});

describe('Doctor page: Copilot draft → editor', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
    storeScope({ mode: 'single', id: 1 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('«Apri nell\'editor» opens I miei parametri with the draft loaded, saving nothing', async () => {
    const draft = { portfolio_ids: [1], preview: preview(), name: 'Prudente' };
    const api = mockDoctor({ policy_enabled: true, simulator_enabled: true }, (path) => {
      if (path === '/copilot/status') return { available: true };
      if (path === '/copilot/chat') {
        const body = [{ type: 'policy_draft', content: JSON.stringify(draft) }, { type: 'done' }]
          .map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
        return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
      }
      return undefined;
    });
    renderWithApp(<DoctorPage />, { route: '/doctor' });
    fireEvent.click(await screen.findByRole('button', { name: 'Apri Doctor Copilot' }));
    fireEvent.click(await screen.findByText('Spiega il punteggio Doctor in modo operativo'));
    const card = await screen.findByTestId('policy-draft-card');
    expect(card).toHaveTextContent('Portafoglio Core');
    fireEvent.click(within(card).getByRole('button', { name: "Apri nell'editor" }));
    expect(await screen.findByTestId('editor-copilot-draft')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /I miei parametri/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByLabelText('Valore massimo (%)')).toHaveValue('50');
    expect(screen.getByLabelText('Nome')).toHaveValue('Prudente');
    expect(api.writes().map((request) => request.path)).toEqual(['/copilot/chat']);
  });
});

