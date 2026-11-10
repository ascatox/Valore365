import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createFakeTribunalFetch,
  createFakeTribunalResponse,
  tribunalEventsFixture,
  tribunalSessionFixture,
  tribunalSseFixtureText,
} from '../../components/doctor/tribunal/fixtures';
import { ApiRequestError, setTokenGetter } from './client';
import {
  getLatestTribunalSession,
  getTribunalStatus,
  parseTribunalEvent,
  parseTribunalSseText,
  streamTribunalSession,
} from './tribunal';
import type {
  TribunalArgument,
  TribunalCaseFile,
  TribunalContestedPoint,
  TribunalContestedSide,
  TribunalDiscardSummary,
  TribunalDone,
  TribunalEvent,
  TribunalFact,
  TribunalInstrument,
  TribunalRebuttal,
  TribunalSession,
  TribunalSessionStart,
  TribunalSharedPoint,
  TribunalStatus,
  TribunalTotals,
  TribunalVoiceInfo,
} from './tribunalTypes';

// Compile-time check that a key list covers every field of the type (and nothing else).
type ExactKeys<T, K extends readonly (keyof T)[]> = Exclude<keyof T, K[number]> extends never ? K : never;
function keysOf<T>() {
  return <const K extends readonly (keyof T)[]>(keys: ExactKeys<T, K>) => [...keys].sort() as string[];
}
const sortedKeys = (value: object) => Object.keys(value).sort();

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('tribunal types vs contract fixture', () => {
  const session = tribunalSessionFixture;

  it('session, case file, facts and instruments have exactly the contract fields', () => {
    expect(sortedKeys(session)).toEqual(keysOf<TribunalSession>()([
      'session_id', 'scope', 'created_at', 'completed_at', 'contract_version', 'prompt_version', 'provider', 'model',
      'voices', 'case_file', 'arguments', 'rebuttals', 'synthesis', 'discarded', 'voice_errors', 'totals',
    ]));
    expect(sortedKeys(session.case_file)).toEqual(keysOf<TribunalCaseFile>()([
      'schema_version', 'contract_version', 'status', 'scope', 'generated_at', 'as_of', 'methodology_version', 'hash',
      'instruments', 'facts', 'counts', 'notes',
    ]));
    const factKeys = keysOf<TribunalFact>()([
      'id', 'key', 'group', 'label', 'value', 'unit', 'formatted', 'source', 'quality', 'citable', 'reason', 'subject',
      'sensitive',
    ]);
    session.case_file.facts.forEach((fact) => expect(sortedKeys(fact)).toEqual(factKeys));
    const instrumentKeys = keysOf<TribunalInstrument>()(['symbol', 'isin', 'name']);
    session.case_file.instruments.forEach((item) => expect(sortedKeys(item)).toEqual(instrumentKeys));
    const voiceKeys = keysOf<TribunalVoiceInfo>()(['id', 'code', 'name', 'mandate']);
    session.voices.forEach((voice) => expect(sortedKeys(voice)).toEqual(voiceKeys));
    expect(session.case_file.facts).toHaveLength(37);
  });

  it('arguments, rebuttals, synthesis, discards and totals have exactly the contract fields', () => {
    const argumentKeys = keysOf<TribunalArgument>()(['id', 'voice', 'phase', 'theme', 'stance', 'text', 'text_template', 'fact_ids']);
    session.arguments.forEach((item) => expect(sortedKeys(item)).toEqual(argumentKeys));
    const rebuttalKeys = keysOf<TribunalRebuttal>()([
      'id', 'voice', 'phase', 'target_argument_id', 'target_voice', 'stance', 'text', 'text_template', 'fact_ids',
    ]);
    session.rebuttals.forEach((item) => expect(sortedKeys(item)).toEqual(rebuttalKeys));
    const sharedKeys = keysOf<TribunalSharedPoint>()(['id', 'text', 'text_template', 'fact_ids', 'argument_ids', 'voices']);
    session.synthesis.shared_points.forEach((item) => expect(sortedKeys(item)).toEqual(sharedKeys));
    const contestedKeys = keysOf<TribunalContestedPoint>()(['id', 'text', 'text_template', 'fact_ids', 'metric_codes', 'sides']);
    const sideKeys = keysOf<TribunalContestedSide>()(['voices', 'argument_ids', 'summary', 'summary_template', 'fact_ids']);
    session.synthesis.contested_points.forEach((item) => {
      expect(sortedKeys(item)).toEqual(contestedKeys);
      expect(item.sides).toHaveLength(2);
      item.sides.forEach((side) => expect(sortedKeys(side)).toEqual(sideKeys));
    });
    session.synthesis.open_questions.forEach((item) => expect(sortedKeys(item)).toEqual(['id', 'text']));
    const discardKeys = keysOf<TribunalDiscardSummary>()(['phase', 'voice', 'admitted', 'discarded', 'by_code']);
    session.discarded.forEach((item) => expect(sortedKeys(item)).toEqual(discardKeys));
    expect(sortedKeys(session.totals)).toEqual(keysOf<TribunalTotals>()([
      'arguments', 'rebuttals', 'shared_points', 'contested_points', 'open_questions', 'discarded',
    ]));
  });

  it('session and done events have exactly the contract fields', () => {
    const sessionEvent = tribunalEventsFixture[0];
    const doneEvent = tribunalEventsFixture[tribunalEventsFixture.length - 1];
    expect(sessionEvent.type).toBe('session');
    expect(doneEvent.type).toBe('done');
    expect(sortedKeys(sessionEvent.content)).toEqual(keysOf<TribunalSessionStart>()([
      'session_id', 'scope', 'reused', 'created_at', 'contract_version', 'prompt_version', 'provider', 'model', 'voices',
    ]));
    expect(sortedKeys(doneEvent.content)).toEqual(keysOf<TribunalDone>()(['session_id', 'reused', 'saved', 'duration_ms', 'totals']));
  });
});

describe('parseTribunalEvent', () => {
  it('accepts a known type with an object content', () => {
    expect(parseTribunalEvent('{"type": "phase", "content": {"phase": "apertura", "status": "started"}}'))
      .toEqual({ type: 'phase', content: { phase: 'apertura', status: 'started' } });
  });

  it.each([
    ['malformed JSON', '{"type": "phase", "content": {'],
    ['unknown type', '{"type": "verdict", "content": {}}'],
    ['missing type', '{"content": {}}'],
    ['string content', '{"type": "argument", "content": "{\\"id\\": \\"A-IND-1\\"}"}'],
    ['array content', '{"type": "argument", "content": []}'],
    ['null content', '{"type": "done", "content": null}'],
    ['not an object', '"done"'],
  ])('returns null for %s', (_label, payload) => {
    expect(parseTribunalEvent(payload)).toBeNull();
  });

  it('parses the contract SSE fixture into 30 events, ignoring keepalives', () => {
    const events = parseTribunalSseText(tribunalSseFixtureText);
    expect(events).toHaveLength(30);
    expect(events.map((event) => event.type).slice(0, 3)).toEqual(['session', 'case_file', 'phase']);
    expect(events).toEqual(tribunalEventsFixture);
  });
});

describe('tribunal REST endpoints', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    setTokenGetter(async () => 'tok-123');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setTokenGetter(async () => null);
  });

  it('getTribunalStatus uses the Doctor scope query and the auth token', async () => {
    const status: Partial<TribunalStatus> = { available: true, reason: null };
    fetchMock.mockResolvedValue(jsonResponse(status));
    await expect(getTribunalStatus([26, 19, 19])).resolves.toEqual(status);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/doctor/tribunal/status?portfolio_ids=19&portfolio_ids=26');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123');
  });

  it('getLatestTribunalSession returns the body for the exact scope', async () => {
    const body = { session: tribunalSessionFixture, current_case_file_hash: 'abc', data_changed: true };
    fetchMock.mockResolvedValue(jsonResponse(body));
    await expect(getLatestTribunalSession([19])).resolves.toEqual(body);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/doctor/tribunal/sessions/latest?portfolio_ids=19');
  });

  it('getLatestTribunalSession degrades to null when the endpoint does not exist', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Not Found' }, 404));
    await expect(getLatestTribunalSession([19])).resolves.toBeNull();
  });

  it.each(['not_found', 'feature_disabled'])('getLatestTribunalSession rethrows 404 %s', async (code) => {
    fetchMock.mockResolvedValue(jsonResponse({ error: { code, message: 'x', details: {} } }, 404));
    await expect(getLatestTribunalSession([19])).rejects.toMatchObject({ name: 'ApiRequestError', code, status: 404 });
  });
});

describe('streamTribunalSession', () => {
  beforeEach(() => setTokenGetter(async () => 'tok-xyz'));
  afterEach(() => setTokenGetter(async () => null));

  it('posts the scope with the auth token and delivers every event, even with split chunks', async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const fake = createFakeTribunalFetch(() => createFakeTribunalResponse(tribunalSseFixtureText, { chunkSize: 7 }));
    const fetchImpl: typeof fetch = (input, init) => {
      calls.push({ url: String(input), init: init ?? {} });
      return fake(input, init);
    };
    const received: TribunalEvent[] = [];
    await streamTribunalSession({ portfolioIds: [26, 19], forceNew: true, fetchImpl, onEvent: (event) => received.push(event) });

    expect(received).toEqual(tribunalEventsFixture);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/doctor/tribunal/sessions');
    expect(calls[0].init.method).toBe('POST');
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ portfolio_ids: [19, 26], force_new: true });
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe('Bearer tok-xyz');
  });

  it('ignores unknown and malformed events without stopping', async () => {
    const raw = [
      'data: {"type": "phase", "content": {"phase": "apertura", "status": "started"}}',
      '',
      'data: {not json',
      '',
      'data: {"type": "mystery", "content": {}}',
      '',
      ': keepalive',
      '',
      'event: ignored',
      'data: {"type": "phase", "content": {"phase": "apertura", "status": "completed"}}',
    ].join('\n'); // last line without trailing newline: flushed at end of stream
    const received: TribunalEvent[] = [];
    await streamTribunalSession({
      portfolioIds: [19],
      fetchImpl: createFakeTribunalFetch(() => createFakeTribunalResponse(raw, { chunkSize: 5 })),
      onEvent: (event) => received.push(event),
    });
    expect(received.map((event) => event.content)).toEqual([
      { phase: 'apertura', status: 'started' },
      { phase: 'apertura', status: 'completed' },
    ]);
  });

  it('throws ApiRequestError with code and details for a non-2xx response', async () => {
    const errorBody = {
      error: {
        code: 'daily_limit_reached',
        message: 'Limite raggiunto',
        details: { daily_limit: 3, used_today: 3, resets_at: '2026-11-10T23:00:00Z', retryable: false },
      },
    };
    const promise = streamTribunalSession({
      portfolioIds: [19],
      fetchImpl: createFakeTribunalFetch(() => createFakeTribunalResponse([], { status: 429, errorBody })),
      onEvent: () => undefined,
    });
    await expect(promise).rejects.toBeInstanceOf(ApiRequestError);
    await expect(promise).rejects.toMatchObject({
      status: 429, code: 'daily_limit_reached', message: 'Limite raggiunto',
      details: { resets_at: '2026-11-10T23:00:00Z' },
    });
  });

  it('rejects with AbortError when aborted mid-stream and stops delivering events', async () => {
    const controller = new AbortController();
    const received: TribunalEvent[] = [];
    const promise = streamTribunalSession({
      portfolioIds: [19],
      signal: controller.signal,
      fetchImpl: createFakeTribunalFetch(() => createFakeTribunalResponse(tribunalEventsFixture, { pauseAfterEvents: 4 })),
      onEvent: (event) => {
        received.push(event);
        if (received.length === 4) controller.abort();
      },
    });
    await expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    expect(received).toHaveLength(4);
  });

  it('rejects with the stream error when the connection drops', async () => {
    const received: TribunalEvent[] = [];
    const promise = streamTribunalSession({
      portfolioIds: [19],
      fetchImpl: createFakeTribunalFetch(() => createFakeTribunalResponse(tribunalEventsFixture, { failAfterEvents: 6 })),
      onEvent: (event) => received.push(event),
    });
    await expect(promise).rejects.toBeInstanceOf(TypeError);
    expect(received).toEqual(tribunalEventsFixture.slice(0, 6));
  });
});
