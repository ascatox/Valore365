import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { STORAGE_KEYS } from '../dashboard/constants';
import { AuditorAdminPanel } from '../../pages/Admin.page';
import { getAuditorSummary, normalizeAuditorSummary, type AuditorAdminLatest, type AuditorSummary } from '../../services/api/auditor';
import { AuditIndicator, AuditIndicatorView, formatAuditDate, inReviewText } from './AuditIndicator';

const PASSED: AuditorSummary = {
  available: true,
  run_finished_at: '2026-11-11T00:05:00+00:00',
  checks_passed: 3,
  checks_in_review: 0,
  areas: [
    { area: 'stress', label: 'Stress test', status: 'passed', checks: [
      { title: "Nello stress test i contributi delle classi sommano all'impatto totale", status: 'passed' },
      { title: 'Lo stress test applica a ogni classe di attivo lo shock previsto', status: 'passed' },
    ] },
    { area: 'costs', label: 'Costi', status: 'passed', checks: [
      { title: 'I costi annui dei fondi (TER) sono in un intervallo plausibile', status: 'passed' },
    ] },
  ],
};

const IN_REVIEW: AuditorSummary = {
  ...PASSED,
  checks_passed: 2,
  checks_in_review: 1,
  areas: [
    { area: 'rebalance', label: 'Ribilanciamento e PAC', status: 'in_review', checks: [
      { title: "Nel PAC la somma dei versamenti per strumento è uguale all'importo indicato", status: 'in_review' },
    ] },
    PASSED.areas[1],
    { area: 'stress', label: 'Stress test', status: 'passed', checks: [PASSED.areas[0].checks[0]] },
  ],
};

// Gergo e dettagli interni che l'utente non deve mai vedere.
const JARGON = /\b[ABCD]-[A-Z0-9]+(?:-[A-Z0-9]+)*\b|\bP[012]\b|\bfail\b|\berror\b|\bskip\b|regola|severit|evidenz|invariant|auditor/i;

function renderView(summary: AuditorSummary | null | undefined, defaultOpened = false) {
  return render(
    <MantineProvider>
      <AuditIndicatorView summary={summary} defaultOpened={defaultOpened} />
    </MantineProvider>,
  );
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('AuditIndicatorView', () => {
  it('shows a discreet closed line with passed count and date, all checks passed', () => {
    renderView(PASSED);
    const indicator = screen.getByTestId('audit-indicator');
    expect(indicator).toHaveAttribute('data-state', 'passed');
    expect(screen.getByTestId('audit-indicator-label')).toHaveTextContent('Calcoli verificati: 3 controlli superati');
    expect(within(indicator).getByText('Ultima verifica 11 novembre 2026')).toBeInTheDocument();
    expect(screen.queryByTestId('audit-indicator-review')).toBeNull();
    const toggle = within(indicator).getByRole('button');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(indicator.textContent).not.toMatch(JARGON);
  });

  it('opens on the list of checks by title, grouped by area, with the outcome', () => {
    renderView(PASSED);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true');
    const panel = screen.getByTestId('audit-indicator-panel');
    const areas = within(panel).getAllByTestId('audit-area');
    expect(areas.map((area) => area.querySelector('p')?.textContent)).toEqual(['Stress test', 'Costi']);
    expect(within(areas[0]).getAllByRole('listitem')).toHaveLength(2);
    expect(within(areas[1]).getByText('I costi annui dei fondi (TER) sono in un intervallo plausibile')).toBeInTheDocument();
    expect(within(panel).getAllByText(/superato/)).toHaveLength(3);
    expect(panel.textContent).not.toMatch(JARGON);
  });

  it('says neutrally that a calculation is under review and in which area', () => {
    renderView(IN_REVIEW, true);
    const indicator = screen.getByTestId('audit-indicator');
    expect(indicator).toHaveAttribute('data-state', 'in_review');
    expect(screen.getByTestId('audit-indicator-label')).toHaveTextContent('Calcoli verificati: 2 controlli superati');
    expect(screen.getByTestId('audit-indicator-review')).toHaveTextContent("Un calcolo è in verifica nell'area Ribilanciamento e PAC");
    const reviewArea = screen.getAllByTestId('audit-area')[0];
    expect(reviewArea).toHaveAttribute('data-status', 'in_review');
    expect(within(reviewArea).getByText(/in verifica/)).toBeInTheDocument();
    expect(screen.getByText(/non devi fare nulla/)).toBeInTheDocument();
    // Niente allarmi: nessuna parola da errore o difetto.
    expect(indicator.textContent).not.toMatch(/errore|difetto|sbagliat|anomal|attenzione:|problema/i);
    expect(indicator.textContent).not.toMatch(JARGON);
  });

  it('pluralizes the review text over several areas', () => {
    expect(inReviewText({
      checks_in_review: 3,
      areas: [
        { area: 'costs', label: 'Costi', status: 'in_review', checks: [] },
        { area: 'stress', label: 'Stress test', status: 'passed', checks: [] },
        { area: 'income', label: 'Reddito e dividendi', status: 'in_review', checks: [] },
        { area: 'daily', label: 'Variazioni giornaliere', status: 'in_review', checks: [] },
      ],
    })).toBe('3 calcoli sono in verifica nelle aree Costi, Reddito e dividendi e Variazioni giornaliere');
    expect(inReviewText({ checks_in_review: 0, areas: [] })).toBeNull();
  });

  it('uses the singular for one passed check', () => {
    renderView({ ...PASSED, checks_passed: 1, areas: [PASSED.areas[1]] });
    expect(screen.getByTestId('audit-indicator-label')).toHaveTextContent('Calcoli verificati: 1 controllo superato');
  });

  it('renders nothing when the run is missing or too old (available: false) or data is absent', () => {
    for (const summary of [null, undefined, { ...PASSED, available: false, run_finished_at: null, areas: [] }]) {
      const { container, unmount } = renderView(summary as AuditorSummary | null);
      expect(container.querySelector('[data-testid="audit-indicator"]')).toBeNull();
      unmount();
    }
  });

  it('shows the same content with Privacy Mode on: no amounts or weights to mask', () => {
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
    renderView(IN_REVIEW, true);
    const text = screen.getByTestId('audit-indicator').textContent ?? '';
    expect(text).not.toMatch(/€|\$|%|\d+[.,]\d+/);
  });

  it('formats the date in Italian', () => {
    expect(formatAuditDate('2026-11-09T23:59:00+00:00')).toMatch(/novembre 2026$/);
    expect(formatAuditDate('nope')).toBe('');
  });
});

describe('normalizeAuditorSummary', () => {
  it('turns anything malformed into unavailable and recomputes counts from the checks', () => {
    expect(normalizeAuditorSummary({}).available).toBe(false);
    expect(normalizeAuditorSummary(null).available).toBe(false);
    expect(normalizeAuditorSummary({ available: true, run_finished_at: null, areas: [] }).available).toBe(false);
    expect(normalizeAuditorSummary({ ...PASSED, areas: [] }).available).toBe(false);
    const weird = normalizeAuditorSummary({
      ...IN_REVIEW,
      checks_passed: 99,
      areas: [...IN_REVIEW.areas, { label: 'X', checks: [{ title: 'bad', status: 'fail' }] }, 'junk'],
    });
    expect(weird.checks_passed).toBe(2);
    expect(weird.checks_in_review).toBe(1);
    expect(weird.areas).toHaveLength(3);
  });
});

describe('AuditIndicator (API)', () => {
  function renderLive(ids: number[]) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <MantineProvider>
          <AuditIndicator portfolioIds={ids} />
        </MantineProvider>
      </QueryClientProvider>,
    );
  }

  it('asks for the single portfolio and for the aggregate scope', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(PASSED));
    vi.stubGlobal('fetch', fetchMock);
    renderLive([7]);
    expect(await screen.findByTestId('audit-indicator')).toBeInTheDocument();
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toMatch(/\/doctor\/auditor\/summary\?portfolio_ids=7$/);

    await getAuditorSummary([5, 2, 5]);
    expect(String((fetchMock.mock.calls[1] as unknown[])[0])).toMatch(/\/doctor\/auditor\/summary\?portfolio_ids=2&portfolio_ids=5$/);
  });

  it('stays hidden on an API error or when unavailable', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: { code: 'not_found', message: 'x' } }, 404));
    vi.stubGlobal('fetch', fetchMock);
    const { container } = renderLive([1]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(container.querySelector('[data-testid="audit-indicator"]')).toBeNull();

    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ ...PASSED, available: false })));
    const second = renderLive([2]);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(second.container.querySelector('[data-testid="audit-indicator"]')).toBeNull();
  });
});

describe('AuditorAdminPanel', () => {
  const LATEST: AuditorAdminLatest = {
    run: {
      run_id: 'f'.repeat(32), status: 'completed_with_failures', trigger: 'external', app_version: '1.0',
      started_at: '2026-11-10T23:35:00+00:00', finished_at: '2026-11-11T00:05:00+00:00',
      portfolios_total: 120, rules_total: 53, counts: { pass: 4100, fail: 5, skip: 900, error: 1 },
      failing_rules: [{ rule_id: 'B-PAC-SUM', severity: 'P1', portfolios: 3 }],
    },
    failing: [
      { rule_id: 'C-COST-COHERENCE', title: 'Il costo annuo stimato è coerente con il TER medio e il valore coperto',
        area: 'costs', severity: 'P0', portfolios_failing: 1, since: '2026-11-09T23:35:00+00:00' },
      { rule_id: 'B-PAC-SUM', title: "Nel PAC la somma dei versamenti per strumento è uguale all'importo indicato",
        area: 'rebalance', severity: 'P1', portfolios_failing: 3, since: '2026-11-10T23:35:00+00:00' },
    ],
    errors: [{ rule_id: 'D-PERF-RECOMPUTE', portfolios: 2 }],
  };

  const renderPanel = (props: Parameters<typeof AuditorAdminPanel>[0]) =>
    render(<MantineProvider><AuditorAdminPanel {...props} /></MantineProvider>);

  it('lists failing rules with portfolios involved, since when and severity', () => {
    renderPanel({ data: LATEST, error: null, loading: false });
    expect(screen.getByTestId('admin-auditor-status')).toHaveTextContent('Conclusa con regole che falliscono');
    expect(screen.getByText('2 regole falliscono')).toBeInTheDocument();
    const rules = screen.getAllByTestId('admin-auditor-rule');
    expect(rules).toHaveLength(2);
    expect(within(rules[0]).getByText('P0')).toBeInTheDocument();
    expect(within(rules[0]).getByText('C-COST-COHERENCE · Costi')).toBeInTheDocument();
    expect(within(rules[0]).getByText(/^1 portafoglio coinvolto · dal \d{2}\/11\/2026/)).toBeInTheDocument();
    expect(within(rules[1]).getByText(/3 portafogli coinvolti/)).toBeInTheDocument();
    expect(within(screen.getByTestId('admin-auditor-errors')).getByText('D-PERF-RECOMPUTE · 2 portafogli')).toBeInTheDocument();
  });

  it('covers no run, success without failures, loading and error', () => {
    const { unmount } = renderPanel({ data: { run: null, failing: [], errors: [] }, error: null, loading: false });
    expect(screen.getByTestId('admin-auditor-empty')).toBeInTheDocument();
    unmount();
    const ok = renderPanel({ data: { ...LATEST, run: { ...LATEST.run!, status: 'success' }, failing: [], errors: [] }, error: null, loading: false });
    expect(screen.getByTestId('admin-auditor-status')).toHaveTextContent('Tutto in ordine');
    expect(screen.getByTestId('admin-auditor-none-failing')).toBeInTheDocument();
    ok.unmount();
    const loading = renderPanel({ data: null, error: null, loading: true });
    expect(screen.getByText(/Caricamento/)).toBeInTheDocument();
    loading.unmount();
    renderPanel({ data: null, error: 'Admin access required', loading: false });
    expect(screen.getByText('Admin access required')).toBeInTheDocument();
  });
});
