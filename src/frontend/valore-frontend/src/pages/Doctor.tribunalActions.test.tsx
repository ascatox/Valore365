import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioHealthResponse } from '../services/api';
import type { TribunalLatestResponse, TribunalStatus } from '../services/api/tribunalTypes';
import { PENDING, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis } from '../test/pageHarness';
import { tribunalSessionFixture } from '../components/doctor/tribunal/fixtures';
import { buildContestedCopilotPrompt } from '../components/doctor/tribunal/TribunalContestedActions';
import { METRICS, evaluation, policyRead } from '../components/doctor/policy/testFixtures';
import { DoctorPage } from './Doctor.page';

// Doctor page × Tribunale actions (TASK-70): from a contested point of the saved session to the
// Copilot, «I miei parametri» and the Laboratorio, against a stubbed `fetch`.

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

const idsOf = (path: string) => new URLSearchParams(path.split('?')[1] ?? '').getAll('portfolio_ids').map(Number);

const statusOf = (portfolioIds: number[], overrides: Partial<TribunalStatus> = {}): TribunalStatus => ({
  available: true,
  reason: null,
  message: null,
  provider: 'openai',
  model: 'gpt-4o-mini',
  key_source: 'server',
  limit: { daily_limit: 3, used_today: 1, remaining: 2, resets_at: '2026-11-10T23:00:00Z' },
  scope: {
    portfolio_ids: portfolioIds,
    scope_type: portfolioIds.length > 1 ? 'aggregate' : 'single',
    fingerprint: portfolioIds.map((id) => `p:${id}`).join(','),
  },
  ...overrides,
});

const SAVED: TribunalLatestResponse = {
  session: tribunalSessionFixture,
  current_case_file_hash: tribunalSessionFixture.case_file.hash,
  data_changed: false,
};

interface Options {
  policyEnabled?: boolean;
  simulatorEnabled?: boolean;
  copilotAvailable?: boolean;
  status?: (ids: number[]) => TribunalStatus;
}

function mockDoctor({ policyEnabled = true, simulatorEnabled = true, copilotAvailable = true, status = (ids) => statusOf(ids) }: Options = {}) {
  return installFetchMock(PORTFOLIOS, (request) => {
    if (request.path === '/copilot/status') return { available: copilotAvailable };
    if (request.path === '/copilot/chat') return new Response('', { status: 200 });
    if (request.path === '/doctor/features') {
      return { policy_enabled: policyEnabled, simulator_enabled: simulatorEnabled, tribunal_enabled: true };
    }
    if (request.path.startsWith('/doctor/tribunal/status?')) return status(idsOf(request.path));
    if (request.path.startsWith('/doctor/tribunal/sessions/latest?')) return SAVED;
    if (request.path === '/doctor/metrics') return { metrics: METRICS };
    if (request.path === '/doctor/templates') return { templates: [] };
    if (request.path.startsWith('/doctor/policies?')) return { policy: policyRead() };
    if (request.path.startsWith('/doctor/evaluation?')) return evaluation();
    if (/\/health(\?|$)/.test(request.path)) return health;
    if (DOCTOR_CARDS.test(request.path)) return PENDING;
    return undefined;
  });
}

function renderDoctor(route = '/doctor?section=tribunale') {
  return renderWithApp(
    <Routes>
      <Route path="/doctor" element={<DoctorPage />} />
    </Routes>,
    { route },
  );
}

const contestedPoint = async (id: string) => {
  await waitFor(() => expect(screen.getByTestId('tribunal-section')).toHaveAttribute('data-state', 'completed'));
  return screen.getAllByTestId('tribunal-contested-point').find((card) => card.getAttribute('data-point-id') === id)!;
};

/** Waits for the actions of a point (they depend on the Copilot status and the features). */
const actionsOf = async (id: string) => {
  const card = await contestedPoint(id);
  return waitFor(() => within(card).getByTestId('tribunal-contested-actions'));
};

describe('Doctor page: actions on the Tribunale contested points', () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubLayoutApis();
    if (!window.HTMLElement.prototype.scrollIntoView) window.HTMLElement.prototype.scrollIntoView = () => {};
    storeScope({ mode: 'single', id: 1 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the three actions on every contested point when the destinations are on', async () => {
    mockDoctor();
    renderDoctor();
    for (const id of ['C1', 'C2']) {
      const actions = await actionsOf(id);
      await waitFor(() => expect(within(actions).getByRole('button', { name: 'Approfondisci con il Copilot' })).toBeInTheDocument());
      expect(within(actions).getByRole('button', { name: /Fissa un tuo parametro/ })).toBeInTheDocument();
      expect(within(actions).getByRole('button', { name: 'Prova uno scenario' })).toBeInTheDocument();
    }
  });

  it('opens the Copilot with the pre-filled question on the point and its facts', async () => {
    mockDoctor();
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    renderDoctor();
    const actions = await actionsOf('C2');
    fireEvent.click(await within(actions).findByRole('button', { name: 'Approfondisci con il Copilot' }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/copilot/chat'))).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/copilot/chat'))!;
    const body = JSON.parse(String((init as RequestInit).body));
    const sent = body.messages[body.messages.length - 1].content as string;
    const [, drawdown] = tribunalSessionFixture.synthesis!.contested_points;
    expect(sent).toBe(buildContestedCopilotPrompt(drawdown, tribunalSessionFixture.case_file, tribunalSessionFixture.voices));
    expect(sent).toContain('«La tenuta del portafoglio nei ribassi profondi, stimata in -38,2% per uno scenario come il 2008.»');
    expect(sent).toContain('Quota azionaria: 75,6%');
    expect(sent).toContain('Nessuna indicazione di acquisto o vendita.');
  });

  it('opens «I miei parametri» with a new rule on the metric, without thresholds and without saving', async () => {
    const api = mockDoctor();
    renderDoctor();
    const actions = await actionsOf('C2');
    fireEvent.click(within(actions).getByRole('button', { name: 'Fissa un tuo parametro' }));

    expect(await screen.findByRole('tab', { name: /I miei parametri/ })).toHaveAttribute('aria-selected', 'true');
    const notice = await screen.findByTestId('editor-tribunal-rule');
    expect(notice).toHaveAttribute('data-kind', 'added');
    expect(notice).toHaveTextContent('Nuova regola su «Quota azionaria» aggiunta senza soglie');
    expect(notice).toHaveTextContent('Nulla è salvato finché non confermi.');

    // The saved rule stays; the new one has empty thresholds chosen by nobody.
    expect(screen.getByTestId('rule-editor-max-single')).toBeInTheDocument();
    const rule = screen.getByTestId('rule-editor-equity-weight');
    expect(within(rule).getByLabelText(/Valore massimo/)).toHaveValue('');
    expect(screen.queryByTestId('editor-copilot-draft')).not.toBeInTheDocument();
    expect(api.writes()).toEqual([]);

    // Cancelling leaves everything as it was.
    fireEvent.click(screen.getByRole('button', { name: 'Annulla' }));
    await waitFor(() => expect(screen.queryByTestId('editor-tribunal-rule')).not.toBeInTheDocument());
    expect(api.writes()).toEqual([]);
  });

  it('highlights the existing rule when the metric already has one, and offers only registry metrics', async () => {
    const api = mockDoctor();
    renderDoctor();
    // C1 cites max_single_position_pct and top3_positions_pct: only the first is in the registry
    // of this test, so the action opens it directly (no metric menu).
    const actions = await actionsOf('C1');
    const button = within(actions).getByRole('button', { name: 'Fissa un tuo parametro' });
    expect(button).not.toHaveAttribute('aria-haspopup');
    fireEvent.click(button);

    const notice = await screen.findByTestId('editor-tribunal-rule');
    expect(notice).toHaveAttribute('data-kind', 'existing');
    expect(notice).toHaveTextContent('Hai già una regola su «Peso massimo singola posizione»');
    expect(screen.getAllByTestId(/^rule-editor-/)).toHaveLength(1);
    expect(within(screen.getByTestId('rule-editor-max-single')).getByLabelText(/Valore massimo/)).toHaveValue('35');
    expect(api.writes()).toEqual([]);
  });

  it('opens the Laboratorio on an empty scenario', async () => {
    const api = mockDoctor();
    renderDoctor();
    const actions = await actionsOf('C1');
    fireEvent.click(within(actions).getByRole('button', { name: 'Prova uno scenario' }));

    expect(await screen.findByRole('tab', { name: /Laboratorio/ })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByRole('button', { name: 'Simula scenario' })).toBeInTheDocument();
    expect(screen.queryByTestId('lab-results')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lab-prefill')).not.toBeInTheDocument();
    expect(api.writes()).toEqual([]);
  });

  it('hides each action whose destination is off', async () => {
    mockDoctor({ policyEnabled: false, simulatorEnabled: true, copilotAvailable: false });
    renderDoctor();
    const actions = await actionsOf('C1');
    expect(within(actions).getByRole('button', { name: 'Prova uno scenario' })).toBeInTheDocument();
    expect(within(actions).queryByRole('button', { name: /Fissa un tuo parametro/ })).not.toBeInTheDocument();
    expect(within(actions).queryByRole('button', { name: 'Approfondisci con il Copilot' })).not.toBeInTheDocument();
  });

  it('shows no actions when every destination is off', async () => {
    mockDoctor({ policyEnabled: false, simulatorEnabled: false, copilotAvailable: false });
    renderDoctor();
    const card = await contestedPoint('C1');
    expect(within(card).queryByTestId('tribunal-contested-actions')).not.toBeInTheDocument();
    expect(screen.queryByTestId('tribunal-contested-actions')).not.toBeInTheDocument();
  });

  it('shows no actions on a saved session in read-only mode (daily limit reached)', async () => {
    mockDoctor({
      status: (ids) => statusOf(ids, {
        available: false,
        reason: 'daily_limit_reached',
        message: 'Limite giornaliero raggiunto',
        limit: { daily_limit: 3, used_today: 3, remaining: 0, resets_at: '2026-11-10T23:00:00Z' },
      }),
    });
    renderDoctor();
    await waitFor(() => expect(screen.getAllByTestId('tribunal-contested-point')).toHaveLength(2));
    expect(screen.queryByTestId('tribunal-contested-actions')).not.toBeInTheDocument();
  });

  it('keeps the actions in the aggregate view, with the scope note, and opens the aggregate parameters', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    const api = mockDoctor();
    renderDoctor();
    const actions = await actionsOf('C2');
    await waitFor(() => expect(within(actions).getAllByRole('button')).toHaveLength(3));
    expect(within(actions).getByTestId('tribunal-actions-aggregate-note')).toBeInTheDocument();

    fireEvent.click(within(actions).getByRole('button', { name: 'Fissa un tuo parametro' }));
    expect(await screen.findByTestId('editor-tribunal-rule')).toHaveAttribute('data-kind', 'added');
    // The existing scope notice of «I miei parametri» stays in the aggregate view.
    expect(screen.getByText(/indipendenti da quelli dei singoli portafogli/)).toBeInTheDocument();
    expect(api.paths()).toContain('/doctor/policies?portfolio_ids=1&portfolio_ids=2');
    expect(api.writes()).toEqual([]);
  });
});
