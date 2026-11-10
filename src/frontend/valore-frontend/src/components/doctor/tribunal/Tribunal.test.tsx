import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient, stubLayoutApis } from '../../../test/pageHarness';
import type {
  TribunalEvent,
  TribunalLatestResponse,
  TribunalSession,
  TribunalStatus,
} from '../../../services/api/tribunalTypes';
import { createFakeTribunalFetch, createFakeTribunalResponse, tribunalEventsFixture, tribunalSessionFixture } from './fixtures';
import { TribunalSection, type TribunalSectionProps } from './TribunalSection';
import {
  DISCLAIMER_TEXT,
  discardedTitle,
  factDisplayValue,
  formatLocalTime,
  formatSessionDate,
  splitTemplate,
  tribunalMessage,
} from './tribunalFormat';

// ---------------------------------------------------------------- harness

const PENDING = Symbol('pending');
type Answer = unknown | Response | typeof PENDING;

const statusOf = (overrides: Partial<TribunalStatus> = {}): TribunalStatus => ({
  available: true,
  reason: null,
  message: null,
  provider: 'openai',
  model: 'gpt-4o-mini',
  key_source: 'server',
  limit: { daily_limit: 3, used_today: 1, remaining: 2, resets_at: '2026-11-10T23:00:00Z' },
  scope: { portfolio_ids: [19], scope_type: 'single', fingerprint: 'p:19' },
  ...overrides,
});

const NO_SAVED: TribunalLatestResponse = { session: null, current_case_file_hash: null, data_changed: null };
const savedLatest = (session: TribunalSession = tribunalSessionFixture, dataChanged = false): TribunalLatestResponse => ({
  session,
  current_case_file_hash: session.case_file.hash,
  data_changed: dataChanged,
});

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const apiErrorBody = (code: string, message: string, details: Record<string, unknown> | null = null) => ({ error: { code, message, details } });

interface SetupOptions {
  features?: Answer;
  status?: Answer;
  latest?: Answer;
  stream?: () => Response;
  compact?: boolean;
  props?: Partial<TribunalSectionProps>;
}

interface RecordedPost {
  path: string;
  body: Record<string, unknown>;
}

function setMediaQuery(compact: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: compact && query.includes('max-width'),
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

function setup(options: SetupOptions = {}) {
  const {
    features = { tribunal_enabled: true },
    status = statusOf(),
    latest = NO_SAVED,
    stream = () => createFakeTribunalResponse(tribunalEventsFixture),
    compact = false,
    props = {},
  } = options;
  setMediaQuery(compact);
  const posts: RecordedPost[] = [];
  const streamFetch = createFakeTribunalFetch(() => stream());
  const answer = (value: Answer): Promise<Response> => {
    if (value === PENDING) return new Promise<Response>(() => {});
    if (value instanceof Response) return Promise.resolve(value);
    return Promise.resolve(json(value));
  };
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(/^https?:\/\/[^/]+/, '').replace(/^\/api/, '');
    if ((init?.method ?? 'GET').toUpperCase() === 'POST') {
      posts.push({ path, body: JSON.parse(String(init?.body ?? '{}')) });
      return streamFetch(input, init);
    }
    if (path.startsWith('/doctor/features')) return answer(features);
    if (path.startsWith('/doctor/tribunal/status')) return answer(status);
    if (path.startsWith('/doctor/tribunal/sessions/latest')) return answer(latest);
    return json({});
  }));

  const ui = (
    <MantineProvider env="test">
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={['/doctor?section=tribunale']}>
          <Routes>
            <Route
              path="/doctor"
              element={<TribunalSection portfolioIds={[19]} isAggregate={false} privacy={false} {...props} />}
            />
            <Route path="/settings" element={<div>Pagina Impostazioni</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
  const view = render(ui);
  return { ...view, posts };
}

const section = () => screen.getByTestId('tribunal-section');
const waitForState = (state: string) => waitFor(() => expect(section()).toHaveAttribute('data-state', state));
const argumentCard = (id: string) => document.getElementById(`tribunal-${id}`) as HTMLElement;
const startSession = () => fireEvent.click(screen.getByRole('button', { name: 'Avvia la seduta' }));

/** Eventi della fixture fino all'indice indicato (escluso) più quelli aggiunti. */
const firstEvents = (count: number, ...extra: TribunalEvent[]) => [...tribunalEventsFixture.slice(0, count), ...extra];

const FORBIDDEN_UI_TERMS = /vincitor|vince |verdetto|esito|conclusione|classifica|punteggio|adeguat|mifid|consigli|raccomand|pericolos|dovresti|devi /i;

beforeEach(() => {
  window.localStorage.clear();
  stubLayoutApis();
  if (!window.HTMLElement.prototype.scrollIntoView) window.HTMLElement.prototype.scrollIntoView = () => {};
});

afterEach(() => {
  vi.unstubAllGlobals();
  setMediaQuery(false);
});

// ---------------------------------------------------------------- formattazione

describe('tribunalFormat', () => {
  it('splits a template on {Fn} placeholders only', () => {
    expect(splitTemplate('Il TER è {F9}, le prime tre {F6}.')).toEqual([
      { kind: 'text', value: 'Il TER è ' },
      { kind: 'fact', id: 'F9' },
      { kind: 'text', value: ', le prime tre ' },
      { kind: 'fact', id: 'F6' },
      { kind: 'text', value: '.' },
    ]);
    expect(splitTemplate('{F0} {F1234} {Fx}')).toEqual([{ kind: 'text', value: '{F0} {F1234} {Fx}' }]);
  });

  it('shows formatted verbatim and masks only sensitive facts in Privacy Mode', () => {
    expect(factDisplayValue({ formatted: '71/100', sensitive: true }, true)).toBe('******');
    expect(factDisplayValue({ formatted: '71/100', sensitive: true }, false)).toBe('71/100');
    expect(factDisplayValue({ formatted: '46,6%', sensitive: false }, true)).toBe('46,6%');
  });

  it('uses the spec messages by code and the backend message only for unknown codes', () => {
    expect(tribunalMessage('copilot_unavailable', 'x')).toMatch(/^Il Tribunale usa il Copilot, che non è ancora configurato/);
    expect(tribunalMessage('mystery', 'Saldo di 1.500 €', { privacy: true })).toBe('Saldo di ******');
    expect(tribunalMessage('daily_limit_reached', null, { resetsAt: '2026-11-10T23:00:00Z' }))
      .toContain(`dalle ${formatLocalTime('2026-11-10T23:00:00Z')}`);
    expect(discardedTitle(1)).toBe('1 affermazione scartata dal controllo automatico');
    expect(discardedTitle(7)).toBe('7 affermazioni scartate dal controllo automatico');
    expect(formatSessionDate('2026-11-10T14:03:12Z')).toMatch(/^\d{1,2} novembre 2026, \d{2}:\d{2}$/);
  });
});

// ---------------------------------------------------------------- stati

describe('TribunalSection states', () => {
  it('loading: skeleton with the disclaimer always visible', async () => {
    setup({ status: PENDING });
    await waitForState('loading');
    expect(screen.getByTestId('tribunal-disclaimer')).toHaveTextContent(DISCLAIMER_TEXT);
  });

  it('disabled feature: the section is not shown, no status request', async () => {
    setup({ features: { tribunal_enabled: false } });
    await waitForState('disabled');
    expect(section()).not.toBeVisible();
    const calls = vi.mocked(fetch).mock.calls.map(([url]) => String(url));
    expect(calls.some((url) => url.includes('/tribunal/status'))).toBe(false);
  });

  it('unavailable: reason message, link to Impostazioni and the saved session read-only', async () => {
    setup({ status: statusOf({ available: false, reason: 'copilot_not_configured', provider: null, model: null, key_source: null, limit: null }), latest: savedLatest() });
    await waitForState('unavailable');
    expect(screen.getByText(/Il Tribunale usa il Copilot, che non è ancora configurato\. Aggiungi una chiave API in Impostazioni → Copilot\./)).toBeInTheDocument();
    expect(screen.getByTestId('tribunal-disclaimer')).toBeInTheDocument();
    expect(screen.getByTestId('tribunal-content')).toHaveAttribute('data-read-only', 'true');
    expect(screen.queryByTestId('tribunal-redo')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Apri Impostazioni' }));
    expect(await screen.findByText('Pagina Impostazioni')).toBeInTheDocument();
  });

  it('unavailable: provider without structured output', async () => {
    setup({ status: statusOf({ available: false, reason: 'provider_not_supported', key_source: 'user', limit: null }) });
    await waitForState('unavailable');
    expect(screen.getByText(/scegli OpenAI, Anthropic, Gemini oppure OpenRouter\./)).toBeInTheDocument();
  });

  it('ready: introduction, the three voices, daily usage, provider; never starts by itself', async () => {
    const { posts } = setup();
    await waitForState('ready');
    const card = screen.getByTestId('tribunal-state-card');
    expect(within(card).getByText("L'indicizzatore")).toBeInTheDocument();
    expect(within(card).getByText('Il fattoriale')).toBeInTheDocument();
    expect(within(card).getByText('Il prudente')).toBeInTheDocument();
    expect(card).toHaveTextContent('Basso costo, ampia diversificazione, semplicità.');
    expect(screen.getByTestId('tribunal-daily-usage')).toHaveTextContent('Sedute disponibili oggi: 2 di 3');
    expect(screen.getByTestId('tribunal-provider')).toHaveTextContent('Usa il Copilot configurato (OpenAI · gpt-4o-mini)');
    expect(screen.getByRole('button', { name: 'Avvia la seduta' })).toBeEnabled();
    expect(posts).toHaveLength(0);
  });

  it('running: phase indicator, columns filling up, skeletons for waiting voices, «Interrompi» → aborted', async () => {
    const { posts } = setup({ stream: () => createFakeTribunalResponse(tribunalEventsFixture, { pauseAfterEvents: 7 }) });
    await waitForState('ready');
    startSession();
    await waitFor(() => expect(argumentCard('A-PRU-3')).toBeInTheDocument());
    expect(section()).toHaveAttribute('data-state', 'running');
    expect(section()).toHaveAttribute('data-phase', 'apertura');
    expect(posts[0]).toEqual({ path: '/doctor/tribunal/sessions', body: { portfolio_ids: [19], force_new: false } });
    const phases = screen.getByTestId('tribunal-phases');
    expect(within(phases).getByRole('button', { name: 'Apertura' })).toHaveAttribute('aria-current', 'step');
    expect(screen.getByTestId('tribunal-live')).toHaveTextContent('Apertura in corso');
    expect(within(screen.getByTestId('tribunal-voice-indicizzatore')).getByTestId('tribunal-voice-skeleton')).toBeInTheDocument();
    expect(within(screen.getByTestId('tribunal-voice-prudente')).queryByTestId('tribunal-voice-skeleton')).not.toBeInTheDocument();
    expect(screen.getByTestId('tribunal-disclaimer')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Interrompi' }));
    await waitForState('aborted');
    expect(screen.getByText('Seduta interrotta: non è stata salvata.')).toBeInTheDocument();
    expect(argumentCard('A-PRU-1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Avvia la seduta' })).toBeInTheDocument();
  });

  it('running: replica phase announced, rebuttals arrive under their targets', async () => {
    setup({ stream: () => createFakeTribunalResponse(tribunalEventsFixture, { pauseAfterEvents: 18 }) });
    await waitForState('ready');
    startSession();
    await waitFor(() => expect(section()).toHaveAttribute('data-phase', 'replica'));
    expect(screen.getByTestId('tribunal-live')).toHaveTextContent('Replica in corso');
    expect(within(argumentCard('A-IND-2')).getByTestId('tribunal-rebuttal')).toHaveAttribute('data-rebuttal-id', 'R-FAT-1');
  });

  it('running: sintesi phase shows the synthesis placeholder', async () => {
    setup({ stream: () => createFakeTribunalResponse(tribunalEventsFixture, { pauseAfterEvents: 26 }) });
    await waitForState('ready');
    startSession();
    await waitFor(() => expect(section()).toHaveAttribute('data-phase', 'sintesi'));
    expect(screen.getByTestId('tribunal-synthesis')).toHaveAttribute('data-pending', 'true');
  });

  it('completed (live): the full session, rebuttals linked, synthesis without any winner', async () => {
    setup();
    await waitForState('ready');
    startSession();
    await waitForState('completed');
    expect(section()).toHaveAttribute('data-source', 'live');
    expect(screen.getByTestId('tribunal-live')).toHaveTextContent('Seduta conclusa');
    expect(screen.getAllByTestId('tribunal-argument')).toHaveLength(9);

    // replica sotto il bersaglio, nella colonna della voce bersaglio, con aria-describedby
    const rebuttal = within(argumentCard('A-IND-2')).getByTestId('tribunal-rebuttal');
    expect(rebuttal).toHaveTextContent('Replica di Il fattoriale · Contesta');
    expect(rebuttal).toHaveAttribute('aria-describedby', 'tribunal-A-IND-2-text');
    expect(document.getElementById('tribunal-A-IND-2-text')).not.toBeNull();
    expect(within(screen.getByTestId('tribunal-voice-indicizzatore')).getByTestId('tribunal-rebuttal')).toBe(rebuttal);
    // la voce che replica ha il collegamento al bersaglio
    const given = within(screen.getByTestId('tribunal-voice-fattoriale')).getByRole('button', { name: "Ha replicato a L'indicizzatore" });
    fireEvent.click(given);
    await waitFor(() => expect(document.activeElement).toBe(argumentCard('A-IND-2')));

    // posizione con icona e testo
    expect(within(argumentCard('A-IND-1')).getByTestId('tribunal-stance')).toHaveTextContent('Punto di forza');
    expect(within(argumentCard('A-IND-2')).getByTestId('tribunal-stance')).toHaveTextContent('Criticità');
    expect(within(argumentCard('A-FAT-1')).getByTestId('tribunal-stance')).toHaveTextContent('Osservazione');

    // sintesi
    const synthesis = screen.getByTestId('tribunal-synthesis');
    expect(within(synthesis).getByText('Punti condivisi')).toBeInTheDocument();
    expect(within(synthesis).getByText('Concordano: Il fattoriale, Il prudente')).toBeInTheDocument();
    const contested = within(synthesis).getAllByTestId('tribunal-contested-point');
    expect(contested).toHaveLength(2);
    const sides = within(contested[0]).getAllByTestId('tribunal-contested-side');
    expect(sides).toHaveLength(2);
    expect(within(sides[0]).getByTestId('tribunal-side-voice')).toHaveTextContent("L'indicizzatore");
    expect(within(sides[1]).getByTestId('tribunal-side-voice')).toHaveTextContent('Il fattoriale');
    expect(sides[0].getAttribute('style')).toBe(sides[1].getAttribute('style'));
    expect(within(synthesis).getByText('Domande per te')).toBeInTheDocument();
    expect(synthesis.querySelectorAll('ol > li')).toHaveLength(2);
    expect(synthesis.textContent).not.toMatch(FORBIDDEN_UI_TERMS);
    expect(synthesis.textContent).not.toMatch(/\d+ punti di forza|contro \d/);
    // collegamento della sintesi verso un argomento
    fireEvent.click(within(sides[1]).getByRole('button', { name: 'Il fattoriale · argomento' }));
    await waitFor(() => expect(document.activeElement).toBe(argumentCard('A-FAT-2')));

    // l'intestazione delle voci mostra solo il numero dei propri argomenti
    expect(within(screen.getByTestId('tribunal-voice-prudente')).getByTestId('tribunal-voice-status')).toHaveTextContent('3 argomenti');
    expect(screen.getByRole('button', { name: 'Rifai la seduta' })).toBeInTheDocument();
  });

  it('completed (saved): date, data changed warning, «Rifai la seduta» with force_new', async () => {
    const { posts } = setup({ latest: savedLatest(tribunalSessionFixture, true) });
    await waitForState('completed');
    expect(section()).toHaveAttribute('data-source', 'saved');
    expect(screen.getByTestId('tribunal-scope')).toHaveTextContent(`Seduta del ${formatSessionDate(tribunalSessionFixture.created_at)}`);
    expect(screen.getByTestId('tribunal-data-changed')).toHaveTextContent(
      'I dati del portafoglio sono cambiati da questa seduta: alcuni valori potrebbero non essere più attuali.',
    );
    expect(screen.getByText('Usa una delle sedute di oggi')).toBeInTheDocument();
    expect(posts).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Rifai la seduta' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body).toEqual({ portfolio_ids: [19], force_new: true });
    await waitForState('completed');
    expect(section()).toHaveAttribute('data-source', 'live');
  });

  it('error mid-stream: message, retry and everything already received kept', async () => {
    setup({ stream: () => createFakeTribunalResponse(tribunalEventsFixture, { failAfterEvents: 16 }) });
    await waitForState('ready');
    startSession();
    await waitForState('error');
    expect(screen.getByTestId('tribunal-error-message')).toHaveTextContent('La connessione si è interrotta prima della fine della seduta.');
    expect(screen.getByText('Seduta incompleta: non è stata salvata.')).toBeInTheDocument();
    expect(screen.getAllByTestId('tribunal-argument')).toHaveLength(9);
    expect(screen.getByTestId('tribunal-disclaimer')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Riprova' })).toBeInTheDocument();
  });

  it('error event from the stream uses the spec text', async () => {
    const events = firstEvents(25, { type: 'error', content: { code: 'synthesis_failed', phase: 'sintesi', retryable: true, message: 'x' } });
    setup({ stream: () => createFakeTribunalResponse(events) });
    await waitForState('ready');
    startSession();
    await waitForState('error');
    expect(screen.getByTestId('tribunal-error-message')).toHaveTextContent('La sintesi non è riuscita. Gli argomenti delle voci restano visibili.');
    expect(screen.queryByTestId('tribunal-synthesis')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('tribunal-rebuttal')).toHaveLength(4);
  });

  it('error before the stream: HTTP message, no retry when not retryable', async () => {
    setup({
      stream: () => createFakeTribunalResponse([], {
        status: 409,
        errorBody: apiErrorBody('empty_portfolio', 'Portfolio vuoto', { retryable: false }),
      }),
    });
    await waitForState('ready');
    startSession();
    await waitForState('error');
    expect(screen.getByTestId('tribunal-error-message')).toHaveTextContent('Il portafoglio non ha posizioni investite: non c\'è ancora nulla da discutere.');
    expect(screen.queryByRole('button', { name: 'Riprova' })).not.toBeInTheDocument();
    expect(screen.queryByText('Seduta incompleta: non è stata salvata.')).not.toBeInTheDocument();
  });

  it('limit reached at opening: reset time, start disabled, saved session still visible', async () => {
    const resetsAt = '2026-11-10T23:00:00Z';
    setup({
      status: statusOf({ available: false, reason: 'daily_limit_reached', limit: { daily_limit: 3, used_today: 3, remaining: 0, resets_at: resetsAt } }),
      latest: savedLatest(),
    });
    await waitForState('limit_reached');
    expect(screen.getByTestId('tribunal-state-card')).toHaveTextContent(
      `Hai usato tutte le sedute di oggi disponibili con la chiave del server. Potrai avviarne un'altra dalle ${formatLocalTime(resetsAt)}.`,
    );
    expect(screen.getByRole('button', { name: 'Avvia la seduta' })).toBeDisabled();
    expect(screen.getAllByTestId('tribunal-argument')).toHaveLength(9);
  });

  it('limit reached on start (429)', async () => {
    setup({
      stream: () => createFakeTribunalResponse([], {
        status: 429,
        errorBody: apiErrorBody('daily_limit_reached', 'Limite', { resets_at: '2026-11-10T23:00:00Z' }),
      }),
    });
    await waitForState('ready');
    startSession();
    await waitForState('limit_reached');
    expect(screen.getByRole('button', { name: 'Avvia la seduta' })).toBeDisabled();
    expect(screen.getByTestId('tribunal-disclaimer')).toBeInTheDocument();
  });

  it('voice error and a voice with no admitted argument', async () => {
    const [session, caseFile, aperturaStarted] = tribunalEventsFixture;
    const events: TribunalEvent[] = [
      session, caseFile, aperturaStarted,
      ...tribunalEventsFixture.slice(7, 11),
      { type: 'voice_error', content: { phase: 'apertura', voice: 'fattoriale', code: 'timeout', message: 'x', retryable: true } },
      { type: 'discarded', content: { phase: 'apertura', voice: 'prudente', admitted: 0, discarded: 2, by_code: { cifra_libera: 2 } } },
      { type: 'phase', content: { phase: 'apertura', status: 'completed' } },
    ];
    setup({ stream: () => createFakeTribunalResponse(events, { pauseAfterEvents: events.length }) });
    await waitForState('ready');
    startSession();
    await waitFor(() => expect(screen.getByTestId('tribunal-voice-error')).toBeInTheDocument());
    expect(within(screen.getByTestId('tribunal-voice-fattoriale')).getByTestId('tribunal-voice-error'))
      .toHaveTextContent('Il fattoriale non ha risposto in tempo: la seduta prosegue con le altre voci.');
    expect(within(screen.getByTestId('tribunal-voice-prudente')).getByTestId('tribunal-voice-none'))
      .toHaveTextContent('Nessun argomento ha superato la verifica.');
    expect(within(screen.getByTestId('tribunal-voice-indicizzatore')).getAllByTestId('tribunal-argument')).toHaveLength(3);
  });

  it('empty synthesis message', async () => {
    const empty = { ...tribunalSessionFixture, synthesis: { shared_points: [], contested_points: [], open_questions: [] } };
    setup({ latest: savedLatest(empty) });
    await waitForState('completed');
    expect(screen.getByTestId('tribunal-synthesis-empty')).toHaveTextContent(
      'La sintesi non ha prodotto punti verificabili. Gli argomenti delle voci restano consultabili qui sopra.',
    );
  });

  it('renders the contested actions slot with point and context', async () => {
    const renderContestedActions = vi.fn((point: { id: string }) => <span data-testid="slot">{`azioni ${point.id}`}</span>);
    setup({ latest: savedLatest(), props: { renderContestedActions } });
    await waitForState('completed');
    expect(screen.getAllByTestId('slot').map((node) => node.textContent)).toEqual(['azioni C1', 'azioni C2']);
    expect(renderContestedActions).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'C1' }),
      expect.objectContaining({ caseFile: expect.objectContaining({ hash: tribunalSessionFixture.case_file.hash }), voices: expect.any(Array) }),
    );
  });
});

// ---------------------------------------------------------------- fatti, scartati, privacy

describe('Tribunal facts, discarded and privacy', () => {
  it('opens a cited fact in a popover with label, value, source and quality; Esc closes it', async () => {
    setup({ latest: savedLatest() });
    await waitForState('completed');
    const chip = within(argumentCard('A-IND-1')).getByRole('button', { name: 'Dato F9: TER medio ponderato, 0,19%. Apri i dettagli' });
    expect(chip).toHaveTextContent('0,19%');
    chip.focus();
    fireEvent.click(chip);
    const dialog = await screen.findByRole('dialog', { name: 'Dettagli del dato F9' });
    expect(within(dialog).getByText('TER medio ponderato')).toBeInTheDocument();
    expect(within(dialog).getByTestId('tribunal-fact-value')).toHaveTextContent('0,19%');
    expect(within(dialog).getByText('Metriche del Doctor')).toBeInTheDocument();
    expect(within(dialog).getByTestId('tribunal-fact-quality')).toHaveTextContent('Dato completo');
    expect(within(dialog).getByText('Dato F9')).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Dettagli del dato F9' })).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).toBe(chip));
  });

  it('shows partial quality with its reason and the subject of a fact', async () => {
    setup({ latest: savedLatest() });
    await waitForState('completed');
    fireEvent.click(within(argumentCard('A-PRU-1')).getByRole('button', { name: /^Dato F21:/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Dettagli del dato F21' });
    expect(within(dialog).getByTestId('tribunal-fact-quality')).toHaveTextContent('Dato parziale');
    expect(within(dialog).getByText(/Stima con proxy di classe/)).toBeInTheDocument();
    expect(within(dialog).getByText('Stress test storici')).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: 'Escape' });

    fireEvent.click(within(argumentCard('A-IND-2')).getAllByRole('button', { name: /^Dato F5:/ })[0]);
    const second = await screen.findByRole('dialog', { name: 'Dettagli del dato F5' });
    expect(within(second).getByText('VWCE.DE')).toBeInTheDocument();
  });

  it('counts discarded statements with the explanation and the detail by voice and reason', async () => {
    setup({ latest: savedLatest() });
    await waitForState('completed');
    const notice = screen.getByTestId('tribunal-discarded');
    expect(within(notice).getByTestId('tribunal-discarded-title')).toHaveTextContent('7 affermazioni scartate dal controllo automatico');
    expect(notice).toHaveTextContent(/Prima di mostrarti una frase, il Tribunale controlla che ogni numero venga dai dati del Doctor/);
    const toggle = within(notice).getByRole('button', { name: 'Mostra il dettaglio' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    const detail = within(notice).getByTestId('tribunal-discarded-detail');
    expect(detail).toHaveTextContent("L'indicizzatore: 1");
    expect(detail).toHaveTextContent('Il prudente: 3');
    expect(detail).toHaveTextContent('Sintesi: 1');
    expect(detail).toHaveTextContent('indicazione di acquisto, vendita o consiglio: 2');
    expect(detail).toHaveTextContent('numero scritto senza prenderlo dai dati: 1');
    // gli scartati per voce non compaiono nelle intestazioni delle voci
    expect(within(screen.getByTestId('tribunal-voice-prudente')).getByTestId('tribunal-voice-status')).toHaveTextContent(/^3 argomenti$/);
  });

  it('Privacy Mode masks the health score everywhere and keeps percentages visible', async () => {
    setup({ latest: savedLatest(), props: { privacy: true } });
    await waitForState('completed');
    const rebuttal = within(argumentCard('A-IND-2')).getByTestId('tribunal-rebuttal');
    const chip = within(rebuttal).getByRole('button', { name: /^Dato F10:/ });
    expect(chip).toHaveTextContent('******');
    expect(chip).toHaveAccessibleName('Dato F10: Punteggio di salute del Doctor, nascosto. Apri i dettagli');
    expect(section().textContent).not.toContain('71/100');
    expect(within(argumentCard('A-IND-2')).getAllByText('46,6%').length).toBeGreaterThan(0);
    fireEvent.click(chip);
    const dialog = await screen.findByRole('dialog', { name: 'Dettagli del dato F10' });
    expect(within(dialog).getByTestId('tribunal-fact-value')).toHaveTextContent('******');
  });

  it('a placeholder pointing to a missing fact falls back to the final text', async () => {
    const broken: TribunalSession = {
      ...tribunalSessionFixture,
      arguments: tribunalSessionFixture.arguments.map((item) => (item.id === 'A-IND-1'
        ? { ...item, text_template: 'Il TER è {F99}.', text: 'Il TER è 0,19%.' }
        : item)),
    };
    setup({ latest: savedLatest(broken) });
    await waitForState('completed');
    const card = argumentCard('A-IND-1');
    expect(card).toHaveTextContent('Il TER è 0,19%.');
    expect(within(card).queryByTestId('tribunal-fact-chip')).not.toBeInTheDocument();
  });

  it('lists the case file by group', async () => {
    setup({ latest: savedLatest() });
    await waitForState('completed');
    const panel = screen.getByTestId('tribunal-case-file');
    expect(panel).toHaveTextContent('Fascicolo: 37 dati del Doctor (35 citabili)');
  });
});

// ---------------------------------------------------------------- mobile

describe('Tribunal on mobile', () => {
  it('shows the voices as tabs, the synthesis below, details in a bottom sheet, no horizontal overflow', async () => {
    setup({ latest: savedLatest(), compact: true });
    await waitForState('completed');
    const voices = screen.getByTestId('tribunal-voices');
    expect(voices).toHaveAttribute('data-layout', 'tabs');
    const tabs = within(voices).getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Indicizzatore3', 'Fattoriale3', 'Prudente3']);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tribunal-voice-indicizzatore')).toBeVisible();
    expect(screen.getByTestId('tribunal-voice-fattoriale')).not.toBeVisible();
    // sintesi fuori dalle schede, sempre visibile
    expect(voices).not.toContainElement(screen.getByTestId('tribunal-synthesis'));
    expect(screen.getByTestId('tribunal-synthesis')).toBeVisible();
    // nessuno scorrimento orizzontale: testi che vanno a capo, pulsanti a tutta larghezza
    expect(section().style.overflowWrap).toBe('anywhere');
    expect(section().style.minWidth).toBe('0px');
    expect(screen.getByTestId('tribunal-redo')).toHaveAttribute('data-block', 'true');

    // «Ha replicato a …» cambia scheda e porta il focus sul bersaglio
    fireEvent.click(within(screen.getByTestId('tribunal-voice-indicizzatore')).getByRole('button', { name: 'Ha replicato a Il fattoriale' }));
    await waitFor(() => expect(tabs[1]).toHaveAttribute('aria-selected', 'true'));
    await waitFor(() => expect(document.activeElement).toBe(argumentCard('A-FAT-2')));

    // il dettaglio di un fatto si apre in un bottom sheet
    fireEvent.click(within(argumentCard('A-FAT-2')).getByRole('button', { name: /^Dato F8:/ }));
    const sheet = await screen.findByRole('dialog');
    expect(within(sheet).getByText('Dettaglio del dato')).toBeInTheDocument();
    expect(within(sheet).getByText('Dato F8')).toBeInTheDocument();
    expect(within(sheet).getByTestId('tribunal-fact-details')).toHaveTextContent('Numero di posizioni');
    expect(within(sheet).getByTestId('tribunal-fact-details')).toHaveTextContent('Posizioni del portafoglio');
  });

  it('keeps the disclaimer compact with «Leggi tutto», full text in the DOM', async () => {
    setup({ compact: true });
    await waitForState('ready');
    const disclaimer = screen.getByTestId('tribunal-disclaimer');
    expect(disclaimer.textContent).toContain(DISCLAIMER_TEXT);
    const toggle = within(disclaimer).getByRole('button', { name: 'Leggi tutto' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(within(disclaimer).getByText(/Ogni numero viene dai calcoli del Doctor/)).not.toBeVisible();
    act(() => { fireEvent.click(toggle); });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(within(disclaimer).getByText(/Ogni numero viene dai calcoli del Doctor/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Avvia la seduta' })).toHaveAttribute('data-block', 'true');
  });

  it('shows a loader in the tab of a voice that is still waiting', async () => {
    setup({ compact: true, stream: () => createFakeTribunalResponse(tribunalEventsFixture, { pauseAfterEvents: 7 }) });
    await waitForState('ready');
    startSession();
    await waitFor(() => expect(argumentCard('A-PRU-1')).toBeInTheDocument());
    const tabs = within(screen.getByTestId('tribunal-voices')).getAllByRole('tab');
    expect(within(tabs[0]).getByLabelText('In attesa')).toBeInTheDocument();
    expect(tabs[2]).toHaveTextContent('Prudente3');
  });
});
