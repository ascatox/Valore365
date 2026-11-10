import { createElement, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TribunalEvent, TribunalSession } from '../../../services/api/tribunalTypes';
import docsSessionJson from '../../../../../../../docs/tribunale/fixtures/seduta-esempio.json?raw';
import docsSseText from '../../../../../../../docs/tribunale/fixtures/seduta-esempio.sse.txt?raw';
import localSessionJson from './fixtures/seduta-esempio.json?raw';
import localSseText from './fixtures/seduta-esempio.sse.txt?raw';
import {
  createFakeTribunalFetch,
  createFakeTribunalResponse,
  tribunalEventsFixture,
  tribunalSessionFixture,
} from './fixtures';
import {
  initialTribunalState,
  reduceTribunalEvent,
  sessionToReplayEvents,
  sessionToState,
  tribunalQueryKeys,
  useTribunalFeature,
  useTribunalSession,
  type TribunalSessionState,
} from './useTribunalSession';

const fold = (events: TribunalEvent[], from: TribunalSessionState = initialTribunalState) =>
  events.reduce(reduceTribunalEvent, from);

const indexOfType = (type: TribunalEvent['type'], occurrence = 1) => {
  let seen = 0;
  return tribunalEventsFixture.findIndex((event) => event.type === type && ++seen === occurrence);
};

const errorEvent: TribunalEvent = {
  type: 'error',
  content: { code: 'synthesis_failed', phase: 'sintesi', retryable: true, message: 'La sintesi non è riuscita.' },
};

describe('tribunal fixtures', () => {
  it('are unmodified copies of docs/tribunale/fixtures', () => {
    expect(localSessionJson).toBe(docsSessionJson);
    expect(localSseText).toBe(docsSseText);
  });

  it('expose the saved session and the 30 live events', () => {
    expect(tribunalSessionFixture.session_id).toBe('trb_5f0c2a9e7d41b386');
    expect(tribunalEventsFixture).toHaveLength(30);
    expect(tribunalEventsFixture[0].type).toBe('session');
    expect(tribunalEventsFixture[29].type).toBe('done');
  });
});

describe('reduceTribunalEvent', () => {
  it('folds the complete live session', () => {
    const state = fold(tribunalEventsFixture);
    expect(state.status).toBe('completed');
    expect(state.sessionId).toBe('trb_5f0c2a9e7d41b386');
    expect(state.reused).toBe(false);
    expect(state.createdAt).toBe('2026-11-10T14:03:12Z');
    expect(state.voices.map((voice) => voice.code)).toEqual(['IND', 'FAT', 'PRU']);
    expect(state.caseFile?.hash).toBe(tribunalSessionFixture.case_file.hash);
    expect(state.completedPhases).toEqual(['apertura', 'replica', 'sintesi']);
    expect(state.phase).toBe('sintesi');
    expect(state.argumentsByVoice.indicizzatore.map((item) => item.id)).toEqual(['A-IND-1', 'A-IND-2', 'A-IND-3']);
    expect(state.argumentsByVoice.fattoriale).toHaveLength(3);
    expect(state.argumentsByVoice.prudente).toHaveLength(3);
    expect(state.rebuttals.map((item) => item.id)).toEqual(['R-FAT-1', 'R-IND-1', 'R-IND-2', 'R-PRU-1']);
    expect(state.synthesis).toEqual(tribunalSessionFixture.synthesis);
    expect(state.totals).toEqual(tribunalSessionFixture.totals);
    expect(state.discarded.total).toBe(tribunalSessionFixture.totals.discarded);
    const sum = (phase: string | null, voice: string | null) => tribunalSessionFixture.discarded
      .filter((item) => (phase === null || item.phase === phase) && item.voice === voice)
      .reduce((total, item) => total + item.discarded, 0);
    expect(state.discarded.byVoice).toEqual({
      indicizzatore: sum(null, 'indicizzatore'), fattoriale: sum(null, 'fattoriale'), prudente: sum(null, 'prudente'),
    });
    expect(state.discarded.synthesis).toBe(sum('sintesi', null));
    expect(Object.values(state.discarded.byCode).reduce((a, b) => a + (b ?? 0), 0)).toBe(state.discarded.total);
    expect(state.error).toBeNull();
  });

  it('tracks the current phase while the stream is running', () => {
    const state = fold(tribunalEventsFixture.slice(0, indexOfType('rebuttal') + 1));
    expect(state.status).toBe('running');
    expect(state.phase).toBe('replica');
    expect(state.completedPhases).toEqual(['apertura']);
    expect(state.synthesis).toBeNull();
  });

  it('keeps what already arrived when an error event comes mid-session', () => {
    const beforeSynthesis = tribunalEventsFixture.slice(0, indexOfType('synthesis'));
    const state = fold([...beforeSynthesis, errorEvent]);
    expect(state.status).toBe('error');
    expect(state.error).toEqual({
      code: 'synthesis_failed', message: 'La sintesi non è riuscita.', retryable: true, phase: 'sintesi',
      resetsAt: null, httpStatus: null,
    });
    expect(state.argumentsByVoice.prudente).toHaveLength(3);
    expect(state.rebuttals).toHaveLength(4);
    expect(state.synthesis).toBeNull();
    // Nothing changes after the terminal event.
    expect(fold(tribunalEventsFixture.slice(indexOfType('synthesis')), state)).toBe(state);
  });

  it('ignores unknown or malformed events', () => {
    const running = fold(tribunalEventsFixture.slice(0, 5));
    const junk = [
      { type: 'verdict', content: { winner: 'prudente' } },
      { type: 'argument', content: { id: 'A-XXX-1', voice: 'oracolo', text: 'x' } },
      { type: 'argument', content: null },
      { type: 'discarded', content: { phase: 'apertura', voice: 'prudente', discarded: 'tanti' } },
      { type: 'phase', content: { phase: 'arringa', status: 'started' } },
    ] as unknown as TribunalEvent[];
    expect(fold(junk, running)).toBe(running);
    expect(fold([...tribunalEventsFixture.slice(0, 5), ...junk, ...tribunalEventsFixture.slice(5)]))
      .toEqual(fold(tribunalEventsFixture));
  });
});

describe('sessionToState', () => {
  it('turns a saved session into a completed, reused state equal to the live one', () => {
    const saved = sessionToState(tribunalSessionFixture);
    const live = fold(tribunalEventsFixture);
    expect(saved.status).toBe('completed');
    expect(saved.reused).toBe(true);
    expect(saved.createdAt).toBe(tribunalSessionFixture.created_at);
    expect(saved.argumentsByVoice).toEqual(live.argumentsByVoice);
    expect([...saved.rebuttals].sort((a, b) => a.id.localeCompare(b.id)))
      .toEqual([...live.rebuttals].sort((a, b) => a.id.localeCompare(b.id)));
    expect(saved.discarded).toEqual(live.discarded);
    expect(saved.synthesis).toEqual(live.synthesis);
    expect(saved.totals).toEqual(live.totals);
  });

  it('replays the saved session in canonical order (§9.4)', () => {
    const events = sessionToReplayEvents(tribunalSessionFixture);
    expect(events).toHaveLength(tribunalEventsFixture.length);
    expect(events[0]).toMatchObject({ type: 'session', content: { reused: true } });
    expect(events.at(-1)).toMatchObject({ type: 'done', content: { reused: true, saved: false, duration_ms: 0 } });
    const voicesOf = (type: 'argument' | 'rebuttal') => events
      .filter((event) => event.type === type)
      .map((event) => (event.content as { voice: string }).voice);
    expect([...new Set(voicesOf('argument'))]).toEqual(['indicizzatore', 'fattoriale', 'prudente']);
    expect([...new Set(voicesOf('rebuttal'))]).toEqual(['indicizzatore', 'fattoriale', 'prudente']);
  });
});

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

type FetchCall = { url: string; init: RequestInit };

function setupHook(responseFactory: () => Response, initialIds: number[] = [19]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const calls: FetchCall[] = [];
  const fake = createFakeTribunalFetch(responseFactory);
  vi.stubGlobal('fetch', ((input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init: init ?? {} });
    return fake(input, init);
  }) as typeof fetch);
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
  const hook = renderHook(({ ids }: { ids: number[] }) => useTribunalSession(ids), { wrapper, initialProps: { ids: initialIds } });
  return { ...hook, calls, invalidate, queryClient };
}

describe('useTribunalSession', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('runs a complete session and invalidates status and latest of the scope', async () => {
    const { result, calls, invalidate } = setupHook(() => createFakeTribunalResponse(tribunalEventsFixture, { chunkSize: 64 }));
    expect(result.current.status).toBe('idle');
    act(() => result.current.start());
    expect(result.current.status).toBe('running');
    await waitFor(() => expect(result.current.status).toBe('completed'));
    expect(result.current.argumentsByVoice.fattoriale).toHaveLength(3);
    expect(result.current.rebuttals).toHaveLength(4);
    expect(result.current.synthesis?.contested_points).toHaveLength(2);
    expect(result.current.discarded.total).toBe(7);
    expect(result.current.error).toBeNull();
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ portfolio_ids: [19], force_new: false });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: tribunalQueryKeys.status('p:19') });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: tribunalQueryKeys.latest('p:19') });
  });

  it('redo asks for a new session (force_new true)', async () => {
    const { result, calls } = setupHook(() => createFakeTribunalResponse(tribunalEventsFixture));
    act(() => result.current.redo());
    await waitFor(() => expect(result.current.status).toBe('completed'));
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ portfolio_ids: [19], force_new: true });
  });

  it('keeps what arrived when an error event comes mid-session', async () => {
    const events = [...tribunalEventsFixture.slice(0, indexOfType('synthesis')), errorEvent];
    const { result } = setupHook(() => createFakeTribunalResponse(events));
    act(() => result.current.start());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error?.code).toBe('synthesis_failed');
    expect(result.current.error?.retryable).toBe(true);
    expect(result.current.argumentsByVoice.indicizzatore).toHaveLength(3);
    expect(result.current.rebuttals).toHaveLength(4);
  });

  it('reports stream_interrupted when the stream ends without done or error, keeping the content', async () => {
    const { result } = setupHook(() => createFakeTribunalResponse(tribunalEventsFixture.slice(0, 10)));
    act(() => result.current.start());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error).toMatchObject({ code: 'stream_interrupted', retryable: true, phase: 'apertura' });
    expect(result.current.caseFile).not.toBeNull();
  });

  it('reports stream_interrupted when the connection drops mid-stream', async () => {
    const { result } = setupHook(() => createFakeTribunalResponse(tribunalEventsFixture, { failAfterEvents: 8 }));
    act(() => result.current.start());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error?.code).toBe('stream_interrupted');
    expect(result.current.argumentsByVoice.prudente).toHaveLength(3);
  });

  it('reports network_error when fetch fails before the response', async () => {
    const { result } = setupHook(() => {
      throw new TypeError('Failed to fetch');
    });
    act(() => result.current.start());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error).toMatchObject({ code: 'network_error', httpStatus: null });
  });

  it('ignores unknown and malformed events in the stream', async () => {
    const lines = tribunalEventsFixture.map((event) => `data: ${JSON.stringify(event)}\n\n`);
    lines.splice(5, 0, 'data: {"type": "verdict", "content": {"winner": "prudente"}}\n\n', 'data: {broken\n\n',
      'data: {"type": "argument", "content": "not an object"}\n\n', ': keepalive\n\n');
    const { result } = setupHook(() => createFakeTribunalResponse(lines.join(''), { chunkSize: 13 }));
    act(() => result.current.start());
    await waitFor(() => expect(result.current.status).toBe('completed'));
    expect(result.current.argumentsByVoice.prudente).toHaveLength(3);
    expect(result.current.totals).toEqual(tribunalSessionFixture.totals);
  });

  it('maps 429 daily_limit_reached to limit_reached with resetsAt', async () => {
    const errorBody = {
      error: {
        code: 'daily_limit_reached', message: 'Limite',
        details: { daily_limit: 3, used_today: 3, resets_at: '2026-11-10T23:00:00Z', retryable: false },
      },
    };
    const { result } = setupHook(() => createFakeTribunalResponse([], { status: 429, errorBody }));
    act(() => result.current.start());
    await waitFor(() => expect(result.current.status).toBe('limit_reached'));
    expect(result.current.error).toEqual({
      code: 'daily_limit_reached', message: 'Limite', retryable: false, phase: null,
      resetsAt: '2026-11-10T23:00:00Z', httpStatus: 429,
    });
  });

  it('maps other HTTP errors to error with the backend code', async () => {
    const errorBody = { error: { code: 'session_in_progress', message: 'In corso', details: { retryable: true } } };
    const { result } = setupHook(() => createFakeTribunalResponse([], { status: 409, errorBody }));
    act(() => result.current.start());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error).toMatchObject({ code: 'session_in_progress', retryable: true, httpStatus: 409 });
  });

  describe('closing the connection', () => {
    let paused: () => Response;
    beforeEach(() => {
      paused = () => createFakeTribunalResponse(tribunalEventsFixture, { pauseAfterEvents: 6 });
    });

    it('stop aborts the connection and keeps the content', async () => {
      const { result, calls } = setupHook(paused);
      act(() => result.current.start());
      await waitFor(() => expect(result.current.argumentsByVoice.prudente).toHaveLength(3));
      act(() => result.current.stop());
      expect(result.current.status).toBe('aborted');
      expect(calls[0].init.signal?.aborted).toBe(true);
      expect(result.current.argumentsByVoice.prudente).toHaveLength(3);
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(result.current.status).toBe('aborted');
      expect(result.current.error).toBeNull();
    });

    it('changing the scope aborts the connection and resets the state', async () => {
      const { result, calls, rerender } = setupHook(paused);
      act(() => result.current.start());
      await waitFor(() => expect(result.current.caseFile).not.toBeNull());
      rerender({ ids: [19, 26] });
      expect(calls[0].init.signal?.aborted).toBe(true);
      expect(result.current.status).toBe('idle');
      expect(result.current.caseFile).toBeNull();
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(result.current.status).toBe('idle');
    });

    it('the same scope in a different order does not reset', async () => {
      const { result, calls, rerender } = setupHook(paused, [26, 19]);
      act(() => result.current.start());
      await waitFor(() => expect(result.current.caseFile).not.toBeNull());
      rerender({ ids: [19, 26] });
      expect(calls[0].init.signal?.aborted).toBe(false);
      expect(result.current.status).toBe('running');
    });

    it('unmounting aborts the connection', async () => {
      const { result, calls, unmount } = setupHook(paused);
      act(() => result.current.start());
      await waitFor(() => expect(result.current.caseFile).not.toBeNull());
      unmount();
      expect(calls[0].init.signal?.aborted).toBe(true);
    });

    it('a new start cancels the previous stream', async () => {
      let call = 0;
      const { result, calls } = setupHook(() => (call++ === 0 ? paused() : createFakeTribunalResponse(tribunalEventsFixture)));
      act(() => result.current.start());
      await waitFor(() => expect(result.current.caseFile).not.toBeNull());
      act(() => result.current.redo());
      expect(calls[0].init.signal?.aborted).toBe(true);
      await waitFor(() => expect(result.current.status).toBe('completed'));
      expect(result.current.argumentsByVoice.prudente).toHaveLength(3);
    });
  });

  it('loadSaved shows a saved session as completed and reused; reset goes back to idle', () => {
    const { result } = setupHook(() => createFakeTribunalResponse(tribunalEventsFixture));
    act(() => result.current.loadSaved(tribunalSessionFixture as TribunalSession));
    expect(result.current.status).toBe('completed');
    expect(result.current.reused).toBe(true);
    expect(result.current.synthesis).toEqual(tribunalSessionFixture.synthesis);
    act(() => result.current.reset());
    expect(result.current.status).toBe('idle');
    expect(result.current.synthesis).toBeNull();
  });
});

describe('useTribunalFeature', () => {
  afterEach(() => vi.unstubAllGlobals());

  it.each([
    [{ policy_enabled: true, simulator_enabled: true, tribunal_enabled: true }, true],
    [{ policy_enabled: true, simulator_enabled: true, tribunal_enabled: false }, false],
    [{ policy_enabled: true, simulator_enabled: true }, false],
  ])('reads tribunal_enabled from /doctor/features (%o)', async (features, expected) => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(features), { status: 200 })));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
    const { result } = renderHook(() => useTribunalFeature(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.enabled).toBe(expected);
    expect(queryClient.getQueryData(['doctor-features'])).toEqual(features);
  });
});
