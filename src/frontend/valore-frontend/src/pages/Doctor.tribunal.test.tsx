import type { ComponentProps } from 'react';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioHealthResponse } from '../services/api';
import type { TribunalLatestResponse, TribunalStatus } from '../services/api/tribunalTypes';
import { PENDING, apiError, installFetchMock, portfolio, renderWithApp, storeScope, stubLayoutApis } from '../test/pageHarness';
import { usePortfolioScope } from '../scope/PortfolioScopeContext';
import {
  createFakeTribunalFetch,
  createFakeTribunalResponse,
  tribunalEventsFixture,
  tribunalSessionFixture,
} from '../components/doctor/tribunal/fixtures';
import { formatSessionDate } from '../components/doctor/tribunal/tribunalFormat';
import { DoctorPage } from './Doctor.page';

// Doctor page × Tribunale (TASK-69): the real page, hooks and TribunalSection
// against a stubbed `fetch`; the SSE stream comes from the TASK-67 fixture.

const crash = vi.hoisted(() => ({ tribunal: false }));

vi.mock('../components/doctor/tribunal/TribunalSection', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../components/doctor/tribunal/TribunalSection')>();
  function TribunalSection(props: ComponentProps<typeof actual.TribunalSection>) {
    if (crash.tribunal) throw new Error('tribunal render failure');
    return <actual.TribunalSection {...props} />;
  }
  return { ...actual, TribunalSection };
});

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

const NO_SAVED: TribunalLatestResponse = { session: null, current_case_file_hash: null, data_changed: null };

interface TribunalMockOptions {
  tribunalEnabled?: boolean;
  status?: (ids: number[]) => unknown;
  latest?: (ids: number[]) => unknown;
  stream?: () => Response;
}

const idsOf = (path: string) => new URLSearchParams(path.split('?')[1] ?? '').getAll('portfolio_ids').map(Number);

function mockDoctor({
  tribunalEnabled = true,
  status = (ids) => statusOf(ids),
  latest = () => NO_SAVED,
  stream = () => createFakeTribunalResponse(tribunalEventsFixture),
}: TribunalMockOptions = {}) {
  const posts: { path: string; body: Record<string, unknown> }[] = [];
  const streamFetch = createFakeTribunalFetch(() => stream());
  const api = installFetchMock(PORTFOLIOS, (request) => {
    if (request.path === '/doctor/features') {
      return { policy_enabled: true, simulator_enabled: true, tribunal_enabled: tribunalEnabled };
    }
    if (request.path.startsWith('/doctor/tribunal/status?')) return status(idsOf(request.path));
    if (request.path.startsWith('/doctor/tribunal/sessions/latest?')) return latest(idsOf(request.path));
    if (request.path === '/doctor/metrics') return { metrics: [] };
    if (request.path === '/doctor/templates') return { templates: [] };
    if (request.path.startsWith('/doctor/policies?')) return { policy: null };
    if (request.path.startsWith('/doctor/evaluation?')) return PENDING;
    if (/\/health(\?|$)/.test(request.path)) return health;
    if (DOCTOR_CARDS.test(request.path)) return PENDING;
    return undefined;
  });
  // The session POST is an SSE stream that must honour the abort signal.
  const recorded = globalThis.fetch as unknown as (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    if ((init?.method ?? 'GET').toUpperCase() === 'POST' && url.includes('/doctor/tribunal/sessions')) {
      posts.push({ path: url.replace(/^https?:\/\/[^/]+/, '').replace(/^\/api/, ''), body: JSON.parse(String(init?.body ?? '{}')) });
      return streamFetch(input, init);
    }
    return recorded(input, init);
  }));
  return { ...api, posts, tribunalPaths: () => api.paths().filter((path) => path.startsWith('/doctor/tribunal/')) };
}

/** Test-only control on the shared scope, as the PortfolioSwitcher would change it. */
function ScopeControls() {
  const { setSingle, setScope } = usePortfolioScope();
  return (
    <div>
      <button type="button" onClick={() => setSingle(2)}>scope-pensione</button>
      <button type="button" onClick={() => setScope({ mode: 'aggregate', ids: [1, 2] })}>scope-aggregato</button>
    </div>
  );
}

function renderDoctor(route = '/doctor?section=tribunale') {
  return renderWithApp(
    <>
      <ScopeControls />
      <Routes>
        <Route path="/doctor" element={<DoctorPage />} />
        <Route path="/settings" element={<div>Pagina Impostazioni</div>} />
      </Routes>
    </>,
    { route },
  );
}

const tribunalSection = () => screen.getByTestId('tribunal-section');
const waitForState = (state: string) => waitFor(() => expect(tribunalSection()).toHaveAttribute('data-state', state));

function setViewport(mobile: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: mobile && query.includes('max-width'),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

describe('Doctor page: Tribunale section', () => {
  beforeEach(() => {
    window.localStorage.clear();
    crash.tribunal = false;
    stubLayoutApis();
    setViewport(false);
    if (!window.HTMLElement.prototype.scrollIntoView) window.HTMLElement.prototype.scrollIntoView = () => {};
    storeScope({ mode: 'single', id: 1 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setViewport(false);
  });

  it('shows the «Tribunale» tab last when the backend feature is on, and opens it without starting a session', async () => {
    const api = mockDoctor();
    renderDoctor('/doctor');
    const tab = await screen.findByRole('tab', { name: /Tribunale/ });
    const tabs = screen.getAllByRole('tab').map((item) => item.textContent);
    expect(tabs).toEqual(['Diagnosi', 'I miei parametri', 'Laboratorio', 'Tribunale']);
    expect(api.tribunalPaths()).toEqual([]);

    fireEvent.click(tab);
    expect(screen.getByRole('tab', { name: /Tribunale/ })).toHaveAttribute('aria-selected', 'true');
    await waitForState('ready');
    expect(screen.queryByText('Dettaglio metriche')).not.toBeInTheDocument();
    expect(api.tribunalPaths()).toEqual([
      '/doctor/tribunal/status?portfolio_ids=1',
      '/doctor/tribunal/sessions/latest?portfolio_ids=1',
    ]);
    expect(api.writes()).toEqual([]);
    expect(api.posts).toEqual([]);
  });

  it('hides the tab when the backend feature is off; the deep link falls back to Diagnosi', async () => {
    const api = mockDoctor({ tribunalEnabled: false });
    renderDoctor('/doctor?section=tribunale');
    expect(await screen.findByRole('tab', { name: /Laboratorio/ })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Tribunale/ })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Diagnosi/ })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('Dettaglio metriche')).toBeInTheDocument();
    expect(screen.queryByTestId('tribunal-section')).not.toBeInTheDocument();
    expect(api.tribunalPaths()).toEqual([]);
  });

  it('does not show the tab while /doctor/features has not answered', async () => {
    installFetchMock(PORTFOLIOS, (request) => {
      if (request.path === '/doctor/features') return PENDING;
      if (/\/health(\?|$)/.test(request.path)) return health;
      if (DOCTOR_CARDS.test(request.path)) return PENDING;
      return undefined;
    });
    renderDoctor('/doctor?section=tribunale');
    expect(await screen.findByText('Dettaglio metriche')).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Tribunale/ })).not.toBeInTheDocument();
    expect(screen.queryByTestId('tribunal-section')).not.toBeInTheDocument();
  });

  it('starts a session only on «Avvia la seduta», for the selected portfolio', async () => {
    const api = mockDoctor();
    renderDoctor();
    await waitForState('ready');
    expect(api.posts).toEqual([]);
    fireEvent.click(screen.getByRole('button', { name: 'Avvia la seduta' }));
    await waitForState('completed');
    expect(tribunalSection()).toHaveAttribute('data-source', 'live');
    expect(api.posts).toEqual([{ path: '/doctor/tribunal/sessions', body: expect.objectContaining({ portfolio_ids: [1] }) }]);
  });

  it('resets the section when the scope changes: the stream closes and the new scope is read', async () => {
    let aborted = false;
    const api = mockDoctor({
      stream: () => createFakeTribunalResponse(tribunalEventsFixture, { pauseAfterEvents: 3 }),
    });
    const fetchWithAbortSpy = globalThis.fetch as unknown as (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      init?.signal?.addEventListener('abort', () => { aborted = true; });
      return fetchWithAbortSpy(input, init);
    }));
    renderDoctor();
    await waitForState('ready');
    fireEvent.click(screen.getByRole('button', { name: 'Avvia la seduta' }));
    await waitForState('running');

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'scope-pensione' })); });
    await waitForState('ready');
    expect(aborted).toBe(true);
    expect(screen.queryByRole('button', { name: 'Interrompi' })).not.toBeInTheDocument();
    expect(api.tribunalPaths()).toContain('/doctor/tribunal/status?portfolio_ids=2');
    expect(api.tribunalPaths()).toContain('/doctor/tribunal/sessions/latest?portfolio_ids=2');
    expect(screen.getByRole('tab', { name: /Tribunale/ })).toHaveAttribute('aria-selected', 'true');
    expect(api.posts).toHaveLength(1);
  });

  it('works on the aggregate view: aggregate scope in every call and in the header', async () => {
    storeScope({ mode: 'aggregate', ids: [1, 2] });
    const api = mockDoctor();
    renderDoctor();
    await waitForState('ready');
    expect(api.tribunalPaths()).toEqual([
      '/doctor/tribunal/status?portfolio_ids=1&portfolio_ids=2',
      '/doctor/tribunal/sessions/latest?portfolio_ids=1&portfolio_ids=2',
    ]);
    expect(within(tribunalSection()).getByText(/Vista aggregata di 2 portafogli/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Avvia la seduta' }));
    await waitForState('completed');
    expect(api.posts[0].body).toEqual(expect.objectContaining({ portfolio_ids: [1, 2] }));
  });

  it('switching from a single portfolio to the aggregate view remounts the section on the new scope', async () => {
    const api = mockDoctor();
    renderDoctor();
    await waitForState('ready');
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'scope-aggregato' })); });
    await waitFor(() => expect(within(tribunalSection()).getByText(/Vista aggregata di 2 portafogli/)).toBeInTheDocument());
    expect(api.tribunalPaths()).toContain('/doctor/tribunal/status?portfolio_ids=1&portfolio_ids=2');
  });

  it('opens on the last saved session with its date and the «data changed» notice, without starting one', async () => {
    const api = mockDoctor({
      latest: () => ({ session: tribunalSessionFixture, current_case_file_hash: 'altro', data_changed: true }),
    });
    renderDoctor();
    await waitForState('completed');
    expect(tribunalSection()).toHaveAttribute('data-source', 'saved');
    const sessionDate = formatSessionDate(tribunalSessionFixture.created_at);
    expect(sessionDate).toBeTruthy();
    expect(tribunalSection()).toHaveTextContent(`Seduta del ${sessionDate}`);
    expect(within(tribunalSection()).getByText(/I dati del portafoglio sono cambiati da questa seduta/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rifai la seduta' })).toBeInTheDocument();
    expect(api.posts).toEqual([]);
  });

  it('degrades without errors when the «latest» endpoint does not exist yet', async () => {
    const api = mockDoctor({ latest: () => new Response('Not Found', { status: 404 }) });
    renderDoctor();
    await waitForState('ready');
    expect(screen.getByRole('button', { name: 'Avvia la seduta' })).toBeEnabled();
    expect(screen.queryByTestId('doctor-section-error')).not.toBeInTheDocument();
    expect(api.posts).toEqual([]);
  });

  it('explains a missing Copilot and points to Impostazioni → Copilot', async () => {
    mockDoctor({
      status: (ids) => statusOf(ids, {
        available: false,
        reason: 'copilot_not_configured',
        message: null,
        provider: null,
        model: null,
        key_source: null,
        limit: null,
      }),
    });
    renderDoctor();
    await waitForState('unavailable');
    expect(tribunalSection()).toHaveTextContent('Impostazioni → Copilot');
    expect(screen.queryByRole('button', { name: 'Avvia la seduta' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Apri Impostazioni/ }));
    expect(await screen.findByText('Pagina Impostazioni')).toBeInTheDocument();
  });

  it('explains an unsuitable provider and points to Impostazioni → Copilot', async () => {
    mockDoctor({
      status: (ids) => statusOf(ids, { available: false, reason: 'provider_not_supported', message: null, limit: null }),
    });
    renderDoctor();
    await waitForState('unavailable');
    expect(tribunalSection()).toHaveTextContent('Impostazioni → Copilot');
    expect(screen.getByRole('button', { name: /Apri Impostazioni/ })).toBeInTheDocument();
  });

  it('an HTTP error on the status stays inside the section', async () => {
    mockDoctor({ status: () => apiError(400, 'invalid_request', 'Richiesta non valida') });
    renderDoctor();
    await waitForState('error');
    expect(screen.getByRole('tab', { name: /Diagnosi/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Diagnosi/ }));
    expect(await screen.findByText('Dettaglio metriche')).toBeInTheDocument();
  });

  it('a render error in the Tribunale does not break the other Doctor sections', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    crash.tribunal = true;
    mockDoctor();
    renderDoctor();
    const fallback = await screen.findByTestId('doctor-section-error');
    expect(fallback).toHaveTextContent('La sezione Tribunale non è disponibile ora. Le altre sezioni restano utilizzabili.');
    fireEvent.click(screen.getByRole('tab', { name: /Diagnosi/ }));
    expect(await screen.findByText('Dettaglio metriche')).toBeInTheDocument();
    expect(screen.queryByTestId('doctor-section-error')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /I miei parametri/ }));
    expect(await screen.findByRole('tab', { name: /I miei parametri/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByTestId('doctor-section-error')).not.toBeInTheDocument();
    consoleError.mockRestore();
  });

  it('on mobile the four sections are a 2×2 grid with full labels', async () => {
    setViewport(true);
    mockDoctor();
    renderDoctor('/doctor');
    await screen.findByRole('tab', { name: /Tribunale/ });
    const list = screen.getByTestId('doctor-section-tabs');
    expect(list).toHaveAttribute('data-layout', 'grid');
    expect(list).toHaveStyle({ display: 'grid', gridTemplateColumns: '1fr 1fr' });
    const tabs = within(list).getAllByRole('tab');
    expect(tabs.map((item) => item.textContent)).toEqual(['Diagnosi', 'I miei parametri', 'Laboratorio', 'Tribunale']);
    tabs.forEach((item) => {
      expect(item).toHaveStyle({ whiteSpace: 'normal' });
      expect(item).not.toHaveStyle({ textOverflow: 'ellipsis' });
    });
  });

  it('on desktop the sections stay on one row', async () => {
    mockDoctor();
    renderDoctor('/doctor');
    await screen.findByRole('tab', { name: /Tribunale/ });
    expect(screen.getByTestId('doctor-section-tabs')).toHaveAttribute('data-layout', 'row');
  });
});
