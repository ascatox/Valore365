import type { ReactNode } from 'react';
import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { STORAGE_KEYS } from '../../dashboard/constants';
import { createTestQueryClient, installFetchMock, stubLayoutApis } from '../../../test/pageHarness';
import { DoctorPolicySummaryCard } from './DoctorPolicySummaryCard';
import { DoctorPolicyRulesList } from './DoctorPolicyRulesList';
import { DoctorPolicyRuleEditor } from './DoctorPolicyRuleEditor';
import { PolicyEvidenceDrawer } from './PolicyEvidenceDrawer';
import { PolicyVersionHistory } from './PolicyVersionHistory';
import { PolicyDraftCard, parsePolicyDraft } from './PolicyDraftCard';
import { formatComplianceSummary, formatMoney, formatPctValue, isDoctorPrivacyMode, maskMoneyInText } from './policyFormat';
import { METRICS, errorResponse, evaluation, policyRead, preview, ruleResult } from './testFixtures';

function wrap(ui: ReactNode) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={createTestQueryClient()}>{ui}</QueryClientProvider>
    </MantineProvider>,
  );
}

const bodyOf = (fetchMock: ReturnType<typeof vi.fn>, pathPart: string) => {
  const call = fetchMock.mock.calls.find(([url, init]) => String(url).includes(pathPart) && (init as RequestInit | undefined)?.method === 'POST');
  return call ? JSON.parse(String((call[1] as RequestInit).body)) : null;
};

beforeEach(() => {
  window.localStorage.clear();
  stubLayoutApis();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('compliance wording', () => {
  it('spells out UNKNOWN rules and never collapses them into «x/y rispettati»', () => {
    const text = formatComplianceSummary({ passed: 4, failed: 1, unknown: 1, not_applicable: 0, inactive: 0, near_limit: 0, total: 6 });
    expect(text).toBe('4 rispettati · 1 violato · 1 non verificabile');
    expect(text).not.toMatch(/\d+\/\d+/);
  });

  it('formats in Italian and masks only absolute amounts in Privacy Mode', () => {
    expect(formatPctValue(46.6)).toBe('46,6%');
    expect(formatPctValue(null)).toBe('N/D');
    expect(formatMoney(1250, 'EUR', true)).toBe('******');
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
    expect(isDoctorPrivacyMode()).toBe(true);
  });
});

describe('DoctorPolicySummaryCard', () => {
  const props = { isLoading: false, error: null, isAggregate: false, scopeLabel: 'Core', onOpenParametri: () => {} };

  it('shows the compliance summary apart from the score, with UNKNOWN spelled out', () => {
    wrap(<DoctorPolicySummaryCard {...props} evaluation={evaluation()} />);
    expect(screen.getByTestId('policy-summary-text')).toHaveTextContent('2 rispettati · 1 violato · 2 non verificabili');
    expect(screen.getByText('di cui 1 vicino al limite')).toBeInTheDocument();
    expect(screen.getByText('VWRA 46,6%: supera il tuo limite 35% di 11,6 punti percentuali')).toBeInTheDocument();
    expect(screen.getByText(/separata dal punteggio Doctor/)).toBeInTheDocument();
  });

  it.each([
    ['no_policy', evaluation({ status: 'no_policy', results: [], policy_id: null }), 'Non hai ancora impostato parametri per questo ambito.'],
    ['empty_portfolio', evaluation({ status: 'empty_portfolio', results: [] }), 'Nessuna posizione: i parametri si verificano dopo le prime transazioni.'],
  ])('renders the %s state', (_state, value, message) => {
    wrap(<DoctorPolicySummaryCard {...props} evaluation={value} />);
    expect(screen.getByText(message)).toBeInTheDocument();
  });

  it('renders loading, error and stale states', () => {
    const { rerender } = wrap(<DoctorPolicySummaryCard {...props} evaluation={null} isLoading />);
    expect(screen.getByText('Verifica dei tuoi parametri…')).toBeInTheDocument();
    rerender(
      <MantineProvider><DoctorPolicySummaryCard {...props} evaluation={null} error={new Error('boom')} /></MantineProvider>,
    );
    expect(screen.getByText(/Non riusciamo a verificare i tuoi parametri ora\. boom/)).toBeInTheDocument();
    rerender(
      <MantineProvider>
        <DoctorPolicySummaryCard {...props} evaluation={evaluation({ data_quality: { ...evaluation().data_quality, status: 'stale' } })} />
      </MantineProvider>,
    );
    expect(screen.getByText(/Quotazioni non aggiornate/)).toBeInTheDocument();
  });

  it('names the aggregate scope and its independent policy', () => {
    wrap(<DoctorPolicySummaryCard {...props} isAggregate scopeLabel="Vista aggregata (Core, Pensione)" evaluation={evaluation()} />);
    expect(screen.getByText(/Vista aggregata \(Core, Pensione\): parametri indipendenti/)).toBeInTheDocument();
  });
});

describe('DoctorPolicyRulesList', () => {
  it('shows each rule with status icon+label, value, threshold, deviation and data quality', () => {
    wrap(<DoctorPolicyRulesList evaluation={evaluation()} metrics={METRICS} onSelect={() => {}} />);
    const fail = screen.getByTestId('rule-card-max-single');
    expect(within(fail).getByText('Max singolo ETF')).toBeInTheDocument();
    expect(within(fail).getByTestId('rule-status')).toHaveTextContent('Violato');
    expect(within(fail).getByText('46,6%')).toBeInTheDocument();
    expect(within(fail).getByText('max 35,0%')).toBeInTheDocument();
    expect(within(fail).getByText('11,6 pp')).toBeInTheDocument();

    const unknown = screen.getByTestId('rule-card-usa-max');
    expect(within(unknown).getByTestId('rule-status')).toHaveTextContent('Non verificabile');
    expect(within(unknown).getByText('tra 52,0% e 71,0%')).toBeInTheDocument();
    expect(within(unknown).getByText('Non possiamo verificare il limite USA: copertura insufficiente')).toBeInTheDocument();
    expect(within(unknown).getByText('Dati parziali')).toBeInTheDocument();

    expect(within(screen.getByTestId('rule-card-equity-range')).getByTestId('rule-status')).toHaveTextContent('Vicino al limite');
    expect(within(screen.getByTestId('rule-card-top3')).getByTestId('rule-status')).toHaveTextContent('Rispettato');
    expect(within(screen.getByTestId('rule-card-ter')).getByText('Dati non aggiornati')).toBeInTheDocument();
    expect(screen.getByTestId('rules-summary')).toHaveTextContent('2 rispettati · 1 violato · 2 non verificabili');
  });

  it('never invents a 0 for a missing value', () => {
    const value = evaluation({ results: [ruleResult({ rule_id: 'x', status: 'UNKNOWN', actual: null, breach_amount: null, reason: 'Dato mancante' })] });
    wrap(<DoctorPolicyRulesList evaluation={value} metrics={METRICS} onSelect={() => {}} />);
    expect(within(screen.getByTestId('rule-card-x')).getByText('N/D')).toBeInTheDocument();
    expect(within(screen.getByTestId('rule-card-x')).queryByText('0,0%')).not.toBeInTheDocument();
  });

  it('shows the empty portfolio state and opens a rule with the keyboard', () => {
    const onSelect = vi.fn();
    const { unmount } = wrap(<DoctorPolicyRulesList evaluation={evaluation({ status: 'empty_portfolio', results: [] })} onSelect={onSelect} />);
    expect(screen.getByText(/Nessuna posizione nell'ambito/)).toBeInTheDocument();
    unmount();
    wrap(<DoctorPolicyRulesList evaluation={evaluation()} metrics={METRICS} onSelect={onSelect} />);
    const button = screen.getByRole('button', { name: /Max singolo ETF: Violato/ });
    button.focus();
    fireEvent.click(button);
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ rule_id: 'max-single' }));
  });
});

describe('PolicyEvidenceDrawer', () => {
  const handlers = { onClose: () => {}, onExplain: vi.fn(), onSimulate: vi.fn(), onEdit: vi.fn() };

  it('shows methodology, evidence, contributors, denominator, quote date and actions', () => {
    wrap(
      <PolicyEvidenceDrawer rule={ruleResult()} metrics={METRICS} privacy={false} currency="EUR" isMobile={false} canExplain canSimulate {...handlers} />,
    );
    expect(screen.getByText(/Peso della security canonica più grande/)).toBeInTheDocument();
    expect(screen.getByText('Valore investito escluso cash')).toBeInTheDocument();
    expect(screen.getByTestId('evidence-denominator-value').textContent).toMatch(/125\.000/);
    expect(screen.getByText('VWRA · Vanguard FTSE All-World')).toBeInTheDocument();
    expect(screen.getByText('IE00BK5BQT80')).toBeInTheDocument();
    expect(screen.getByText(/03\/11\/2026/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Spiega' }));
    fireEvent.click(screen.getByRole('button', { name: 'Simula' }));
    fireEvent.click(screen.getByRole('button', { name: 'Modifica' }));
    expect(handlers.onExplain).toHaveBeenCalled();
    expect(handlers.onSimulate).toHaveBeenCalled();
    expect(handlers.onEdit).toHaveBeenCalled();
  });

  it('masks the € denominator in Privacy Mode but keeps the percentages', () => {
    wrap(
      <PolicyEvidenceDrawer rule={ruleResult()} metrics={METRICS} privacy currency="EUR" isMobile={false} canExplain canSimulate {...handlers} />,
    );
    expect(screen.getByTestId('evidence-denominator-value')).toHaveTextContent('******');
    expect(screen.queryByText(/125\.000/)).not.toBeInTheDocument();
    expect(screen.getAllByText('46,6%').length).toBeGreaterThan(0);
  });
});

describe('DoctorPolicyRuleEditor', () => {
  const baseProps = {
    onClose: () => {}, portfolioIds: [1], scopeLabel: 'Portafoglio Core', metrics: METRICS, templates: [], onReload: vi.fn(), isMobile: false,
  };

  it('shows the inline field errors of /validate and does not preview', async () => {
    const api = installFetchMock([], (request) => {
      if (request.path === '/doctor/policies/validate') {
        return { valid: false, field_errors: [{ field: 'rules[0].max_value', code: 'out_of_range', message: 'Il valore deve essere tra 0 e 100' }], normalized_document: null };
      }
      return undefined;
    });
    wrap(<DoctorPolicyRuleEditor {...baseProps} policy={policyRead()} onSaved={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Verifica e anteprima' }));
    expect(await screen.findByText('Il valore deve essere tra 0 e 100')).toBeInTheDocument();
    expect(api.paths('POST')).toEqual(['/doctor/policies/validate']);
  });

  it('validate → preview → confirm sends the token and base_version', async () => {
    const onSaved = vi.fn();
    installFetchMock([], (request) => {
      if (request.path === '/doctor/policies/validate') return { valid: true, field_errors: [], normalized_document: preview().normalized_document };
      if (request.path === '/doctor/policies/preview') return preview();
      if (request.path === '/doctor/policies' && request.method === 'POST') return policyRead({ current_version: 4 });
      return undefined;
    });
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    wrap(<DoctorPolicyRuleEditor {...baseProps} policy={policyRead()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText('Valore massimo (%)'), { target: { value: '50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verifica e anteprima' }));

    expect(await screen.findByText('Conferma le modifiche')).toBeInTheDocument();
    expect(screen.getByTestId('policy-diff')).toHaveTextContent('max 35,0% → max 50,0%');
    expect(screen.getByText(/Prima:/).parentElement).toHaveTextContent('2 rispettati · 1 violato · 2 non verificabili');
    expect(screen.getByText(/Dopo:/).parentElement).toHaveTextContent('3 rispettati · 0 violati · 2 non verificabili');
    expect(onSaved).not.toHaveBeenCalled();
    expect(bodyOf(fetchMock, '/doctor/policies/preview')).toMatchObject({ portfolio_ids: [1], base_version: 3, source: 'manual' });
    expect(bodyOf(fetchMock, '/doctor/policies/validate').document.rules[0].max_value).toBe(50);

    fireEvent.click(screen.getByRole('button', { name: 'Conferma e salva' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const saved = fetchMock.mock.calls.find(([url, init]) => /\/doctor\/policies$/.test(String(url)) && (init as RequestInit)?.method === 'POST');
    expect(JSON.parse(String((saved![1] as RequestInit).body))).toMatchObject({
      portfolio_ids: [1], confirmation_token: 'tok-123', base_version: 3, name: 'I miei parametri',
    });
  });

  it('shows the 409 version_conflict message with a reload action', async () => {
    const onReload = vi.fn();
    installFetchMock([], (request) => {
      if (request.path === '/doctor/policies/validate') return { valid: true, field_errors: [], normalized_document: null };
      if (request.path === '/doctor/policies/preview') return preview();
      if (request.path === '/doctor/policies') return errorResponse(409, 'version_conflict', 'conflict');
      return undefined;
    });
    wrap(<DoctorPolicyRuleEditor {...baseProps} onReload={onReload} policy={policyRead()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Verifica e anteprima' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Conferma e salva' }));
    expect(await screen.findByText("La policy è stata modificata in un'altra scheda: ricarica")).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ricarica' }));
    expect(onReload).toHaveBeenCalled();
  });

  it('goes back to editing on 409 confirmation_invalid', async () => {
    installFetchMock([], (request) => {
      if (request.path === '/doctor/policies/validate') return { valid: true, field_errors: [], normalized_document: null };
      if (request.path === '/doctor/policies/preview') return preview();
      if (request.path === '/doctor/policies') return errorResponse(409, 'confirmation_invalid', 'token');
      return undefined;
    });
    wrap(<DoctorPolicyRuleEditor {...baseProps} policy={policyRead()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Verifica e anteprima' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Conferma e salva' }));
    expect(await screen.findByText(/La conferma non è più valida/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verifica e anteprima' })).toBeInTheDocument();
  });

  it('can start from empty rules (no policy yet) and says templates are illustrative', () => {
    installFetchMock([]);
    wrap(
      <DoctorPolicyRuleEditor
        {...baseProps}
        policy={null}
        onSaved={vi.fn()}
        templates={[{ template_id: 'bilanciato', illustrative: true, name: 'Bilanciato', document: policyRead().document }]}
      />,
    );
    expect(screen.getByText('Nessuna regola. Aggiungi una metrica qui sotto.')).toBeInTheDocument();
    expect(screen.getByText(/I modelli sono esempi illustrativi, non raccomandazioni/)).toBeInTheDocument();
  });
});

describe('PolicyVersionHistory', () => {
  it('lists versions and restores one with confirmation and base_version', async () => {
    const onRestored = vi.fn();
    installFetchMock([], (request) => {
      if (request.path === '/doctor/policies/7/versions') {
        return [
          { version_number: 3, source: 'copilot', confirmed_at: '2026-11-01T10:00:00Z', diff: preview().diff },
          { version_number: 2, source: 'manual', confirmed_at: '2026-10-20T10:00:00Z', diff: [] },
        ];
      }
      if (request.path === '/doctor/policies/7/restore') return policyRead({ current_version: 4 });
      return undefined;
    });
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    wrap(<PolicyVersionHistory policy={policyRead()} metrics={METRICS} onRestored={onRestored} onReload={vi.fn()} />);
    expect(await screen.findByTestId('policy-version-3')).toHaveTextContent('Copilot (confermata da te)');
    expect(screen.getByTestId('policy-version-3')).toHaveTextContent('Attuale');
    fireEvent.click(screen.getByRole('button', { name: 'Ripristina la versione 2' }));
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/restore'))).toBe(false);
    fireEvent.click(await screen.findByRole('button', { name: 'Conferma ripristino' }));
    await waitFor(() => expect(onRestored).toHaveBeenCalled());
    expect(bodyOf(fetchMock, '/doctor/policies/7/restore')).toEqual({ version_number: 2, base_version: 3 });
  });
});

describe('PolicyDraftCard (Copilot)', () => {
  it('parses the SSE payload (string or object)', () => {
    const payload = { portfolio_ids: [1], preview: preview() };
    expect(parsePolicyDraft(JSON.stringify(payload))?.portfolio_ids).toEqual([1]);
    expect(parsePolicyDraft(payload)?.preview.confirmation_token).toBe('tok-123');
    expect(parsePolicyDraft('not json')).toBeNull();
  });

  it('saves nothing until «Conferma e salva», then posts the token', async () => {
    const onSaved = vi.fn();
    const api = installFetchMock([], (request) => (request.path === '/doctor/policies' ? policyRead({ current_version: 4 }) : undefined));
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    wrap(<PolicyDraftCard draft={{ portfolio_ids: [1], preview: preview() }} onSaved={onSaved} />);
    expect(screen.getByText('Non ancora salvata')).toBeInTheDocument();
    expect(screen.getByTestId('policy-diff')).toHaveTextContent('max 35,0% → max 50,0%');
    expect(api.writes()).toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Conferma e salva' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(bodyOf(fetchMock, '/doctor/policies')).toMatchObject({ confirmation_token: 'tok-123', base_version: 3, portfolio_ids: [1] });
    expect(screen.getByText('Salvata')).toBeInTheDocument();
  });

  it('«Annulla» discards the draft without any request', () => {
    const api = installFetchMock([]);
    wrap(<PolicyDraftCard draft={{ portfolio_ids: [1], preview: preview() }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Annulla' }));
    expect(screen.getByText('Annullata')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Conferma e salva' })).not.toBeInTheDocument();
    expect(api.writes()).toEqual([]);
  });
});

describe('Privacy Mode in backend free text (review fix)', () => {
  const handlers = { onClose: () => {}, onExplain: vi.fn(), onSimulate: vi.fn(), onEdit: vi.fn() };

  it('maskMoneyInText masks € / EUR amounts and keeps percentages', () => {
    const text = 'Servono 227.029 € (€ 10.000 + 1.500,50 EUR + EUR 41000 + 10 euro + 41.000,00\u00a0€); peso 46,6% oltre il 35%.';
    expect(maskMoneyInText(text, true)).toBe('Servono ****** (****** + ****** + ****** + ****** + ******); peso 46,6% oltre il 35%.');
    expect(maskMoneyInText(text, false)).toBe(text);
    expect(maskMoneyInText(null, true)).toBeNull();
    expect(maskMoneyInText('Nessun importo: 3 regole, 46,6%', true)).toBe('Nessun importo: 3 regole, 46,6%');
    // Without an explicit flag it follows the stored Privacy Mode.
    expect(maskMoneyInText('Vale 5.000 €')).toBe('Vale 5.000 €');
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
    expect(maskMoneyInText('Vale 5.000 €')).toBe('Vale ******');
  });

  it('masks € amounts in the rule reason of the summary card and of the rule cards', () => {
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
    const value = evaluation({ results: [ruleResult({ reason: 'VWRA 46,6% (58.250 €) supera il tuo limite 35%' })] });
    const { unmount } = wrap(
      <DoctorPolicySummaryCard isLoading={false} error={null} isAggregate={false} scopeLabel="Core" onOpenParametri={() => {}} evaluation={value} />,
    );
    expect(screen.getByText('VWRA 46,6% (******) supera il tuo limite 35%')).toBeInTheDocument();
    unmount();
    wrap(<DoctorPolicyRulesList evaluation={value} metrics={METRICS} onSelect={() => {}} />);
    expect(within(screen.getByTestId('rule-card-max-single')).getByText('VWRA 46,6% (******) supera il tuo limite 35%')).toBeInTheDocument();
    expect(screen.queryByText(/58\.250/)).not.toBeInTheDocument();
  });

  it('masks € amounts in the evidence reason and notes', () => {
    const rule = ruleResult({
      reason: 'Posizione da 58.250 € oltre il 35%',
      evidence: { ...ruleResult().evidence, notes: ['Denominatore 125.000 € (escluso cash)', 'Copertura 100%'] },
    });
    wrap(<PolicyEvidenceDrawer rule={rule} metrics={METRICS} privacy currency="EUR" isMobile={false} canExplain canSimulate {...handlers} />);
    expect(screen.getByText('Posizione da ****** oltre il 35%')).toBeInTheDocument();
    expect(screen.getByText('Denominatore ****** (escluso cash)')).toBeInTheDocument();
    expect(screen.getByText('Copertura 100%')).toBeInTheDocument();
    expect(screen.queryByText(/58\.250|125\.000/)).not.toBeInTheDocument();
  });

  it('masks € amounts in the Copilot draft card messages', () => {
    window.localStorage.setItem(STORAGE_KEYS.privacyModeEnabled, 'true');
    installFetchMock([]);
    const invalid = preview({ valid: false, confirmation_token: null, field_errors: [{ field: 'rules', code: 'infeasible', message: 'Servirebbero 10.000 € di liquidità' }] });
    wrap(<PolicyDraftCard draft={{ portfolio_ids: [1], preview: invalid }} />);
    expect(screen.getByText('Servirebbero ****** di liquidità')).toBeInTheDocument();
  });
});

describe('policy name on save (review fix)', () => {
  const baseProps = {
    onClose: () => {}, portfolioIds: [1], scopeLabel: 'Portafoglio Core', metrics: METRICS, templates: [], onReload: vi.fn(), isMobile: false,
  };
  const savedBody = (fetchMock: ReturnType<typeof vi.fn>) => {
    const call = fetchMock.mock.calls.find(([url, init]) => /\/doctor\/policies$/.test(String(url)) && (init as RequestInit)?.method === 'POST');
    return call ? JSON.parse(String((call[1] as RequestInit).body)) : null;
  };

  it('the Copilot draft sends name null when it has none (keeps the existing name)', async () => {
    const onSaved = vi.fn();
    installFetchMock([], (request) => (request.path === '/doctor/policies' ? policyRead({ name: 'Pensione', current_version: 4 }) : undefined));
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    wrap(<PolicyDraftCard draft={{ portfolio_ids: [1], preview: preview() }} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: 'Conferma e salva' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(savedBody(fetchMock).name).toBeNull();
  });

  it('the Copilot draft sends its own name when it provides one', async () => {
    const onSaved = vi.fn();
    installFetchMock([], (request) => (request.path === '/doctor/policies' ? policyRead({ current_version: 4 }) : undefined));
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    wrap(<PolicyDraftCard draft={{ portfolio_ids: [1], preview: preview(), name: '  Prudente ' }} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: 'Conferma e salva' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(savedBody(fetchMock).name).toBe('Prudente');
  });

  async function saveFromEditor(policy: ReturnType<typeof policyRead>, nameInput: string) {
    const onSaved = vi.fn();
    installFetchMock([], (request) => {
      if (request.path === '/doctor/policies/validate') return { valid: true, field_errors: [], normalized_document: preview().normalized_document };
      if (request.path === '/doctor/policies/preview') return preview();
      if (request.path === '/doctor/policies' && request.method === 'POST') return policyRead({ current_version: 4 });
      return undefined;
    });
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    wrap(<DoctorPolicyRuleEditor {...baseProps} policy={policy} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText('Nome'), { target: { value: nameInput } });
    fireEvent.click(screen.getByRole('button', { name: 'Verifica e anteprima' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Conferma e salva' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    return savedBody(fetchMock);
  }

  it('the manual editor keeps the current name of an existing policy', async () => {
    expect((await saveFromEditor(policyRead({ name: 'Pensione' }), 'Pensione')).name).toBe('Pensione');
  });

  it('the manual editor sends null (never a default) when the name of an existing policy is cleared', async () => {
    expect((await saveFromEditor(policyRead({ name: 'Pensione' }), '   ')).name).toBeNull();
  });
});

describe('optional rule fields left empty (review fix)', () => {
  it('clearing «Copertura minima» and «Età massima quote» keeps null (backend default), never 0', async () => {
    installFetchMock([], (request) => {
      if (request.path === '/doctor/policies/validate') {
        return { valid: false, field_errors: [{ field: 'rules[0].max_value', code: 'out_of_range', message: 'stop' }], normalized_document: null };
      }
      return undefined;
    });
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    wrap(
      <DoctorPolicyRuleEditor
        onClose={() => {}} portfolioIds={[1]} scopeLabel="Core" metrics={METRICS} templates={[]} onReload={vi.fn()} isMobile={false}
        policy={policyRead()} onSaved={vi.fn()}
      />,
    );
    const coverage = screen.getByLabelText('Copertura minima (%)');
    const age = screen.getByLabelText('Età massima quote (giorni)');
    fireEvent.change(coverage, { target: { value: '' } });
    fireEvent.change(age, { target: { value: '' } });
    expect(coverage).toHaveValue('');
    expect(age).toHaveValue('');
    expect(coverage).toHaveAttribute('placeholder', 'Predefinita (80%)');
    fireEvent.click(screen.getByRole('button', { name: 'Verifica e anteprima' }));
    await screen.findByText('stop');
    const rule = bodyOf(fetchMock, '/doctor/policies/validate').document.rules[0];
    expect(rule.min_coverage_pct).toBeNull();
    expect(rule.max_data_age_days).toBeNull();
  });
});
