// Tribunale del portafoglio — stato della seduta e lettura dello stream
// (docs/tribunale/api-contracts.md §9; firme in docs/tribunale/architecture.md §3.1).
import { useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { ApiRequestError } from '../../../services/api/client';
import { doctorScopeFingerprint, getDoctorFeatures } from '../../../services/api/doctor';
import { getLatestTribunalSession, getTribunalStatus, streamTribunalSession } from '../../../services/api/tribunal';
import {
  TRIBUNAL_VOICE_IDS,
  type TribunalArgument,
  type TribunalCaseFile,
  type TribunalDiscardCode,
  type TribunalEvent,
  type TribunalLatestResponse,
  type TribunalPhase,
  type TribunalRebuttal,
  type TribunalSession,
  type TribunalStatus,
  type TribunalSynthesis,
  type TribunalTotals,
  type TribunalVoiceError,
  type TribunalVoiceId,
  type TribunalVoiceInfo,
} from '../../../services/api/tribunalTypes';
import { doctorQueryKeys } from '../policy/hooks';

export type TribunalRunStatus = 'idle' | 'running' | 'completed' | 'error' | 'limit_reached' | 'aborted';

/** code: codici HTTP (§3.4) o SSE (§9.3.10), oppure lato client 'stream_interrupted' | 'network_error'. */
export interface TribunalClientError {
  code: string;
  message: string;
  retryable: boolean;
  phase: TribunalPhase | null;
  resetsAt: string | null;
  httpStatus: number | null;
}

export interface TribunalSessionState {
  status: TribunalRunStatus;
  /** Fase in corso. */
  phase: TribunalPhase | null;
  completedPhases: TribunalPhase[];
  sessionId: string | null;
  reused: boolean;
  createdAt: string | null;
  voices: TribunalVoiceInfo[];
  caseFile: TribunalCaseFile | null;
  argumentsByVoice: Record<TribunalVoiceId, TribunalArgument[]>;
  rebuttals: TribunalRebuttal[];
  synthesis: TribunalSynthesis | null;
  discarded: {
    total: number;
    byVoice: Record<TribunalVoiceId, number>;
    synthesis: number;
    byCode: Partial<Record<TribunalDiscardCode, number>>;
  };
  voiceErrors: TribunalVoiceError[];
  totals: TribunalTotals | null;
  error: TribunalClientError | null;
}

const PHASES: readonly TribunalPhase[] = ['apertura', 'replica', 'sintesi'];

function emptyByVoice<T>(make: () => T): Record<TribunalVoiceId, T> {
  return { indicizzatore: make(), fattoriale: make(), prudente: make() };
}

export const initialTribunalState: TribunalSessionState = Object.freeze({
  status: 'idle',
  phase: null,
  completedPhases: [],
  sessionId: null,
  reused: false,
  createdAt: null,
  voices: [],
  caseFile: null,
  argumentsByVoice: emptyByVoice<TribunalArgument[]>(() => []),
  rebuttals: [],
  synthesis: null,
  discarded: { total: 0, byVoice: emptyByVoice(() => 0), synthesis: 0, byCode: {} },
  voiceErrors: [],
  totals: null,
  error: null,
}) as TribunalSessionState;

const TERMINAL: ReadonlySet<TribunalRunStatus> = new Set(['completed', 'error', 'limit_reached', 'aborted']);

const isVoiceId = (value: unknown): value is TribunalVoiceId =>
  typeof value === 'string' && (TRIBUNAL_VOICE_IDS as readonly string[]).includes(value);
const isPhase = (value: unknown): value is TribunalPhase =>
  typeof value === 'string' && (PHASES as readonly string[]).includes(value);
const isCount = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const isString = (value: unknown): value is string => typeof value === 'string';

/**
 * Applica un evento allo stato (funzione pura). Eventi con contenuto non riconoscibile
 * ed eventi dopo la fine della seduta lasciano lo stato invariato (§9.1).
 */
export function reduceTribunalEvent(state: TribunalSessionState, event: TribunalEvent): TribunalSessionState {
  if (TERMINAL.has(state.status)) return state;
  const content = event?.content as unknown as Record<string, unknown> | undefined;
  if (!content || typeof content !== 'object') return state;
  const base: TribunalSessionState = state.status === 'idle' ? { ...state, status: 'running' } : state;

  switch (event.type) {
    case 'session': {
      const value = event.content;
      if (!isString(value.session_id)) return state;
      return {
        ...base,
        sessionId: value.session_id,
        reused: value.reused === true,
        createdAt: isString(value.created_at) ? value.created_at : null,
        voices: Array.isArray(value.voices) ? value.voices.filter((voice) => isVoiceId(voice?.id)) : [],
      };
    }
    case 'case_file': {
      if (!Array.isArray(event.content.facts)) return state;
      return { ...base, caseFile: event.content };
    }
    case 'phase': {
      const { phase, status } = event.content;
      if (!isPhase(phase)) return state;
      if (status === 'started') return { ...base, phase };
      if (status === 'completed') {
        return base.completedPhases.includes(phase) ? base : { ...base, completedPhases: [...base.completedPhases, phase] };
      }
      return state;
    }
    case 'argument': {
      const argument = event.content;
      if (!isVoiceId(argument.voice) || !isString(argument.id) || !isString(argument.text)) return state;
      const current = base.argumentsByVoice[argument.voice];
      const next = current.some((item) => item.id === argument.id)
        ? current.map((item) => (item.id === argument.id ? argument : item))
        : [...current, argument];
      return { ...base, argumentsByVoice: { ...base.argumentsByVoice, [argument.voice]: next } };
    }
    case 'rebuttal': {
      const rebuttal = event.content;
      if (!isVoiceId(rebuttal.voice) || !isString(rebuttal.id) || !isString(rebuttal.text)) return state;
      const next = base.rebuttals.some((item) => item.id === rebuttal.id)
        ? base.rebuttals.map((item) => (item.id === rebuttal.id ? rebuttal : item))
        : [...base.rebuttals, rebuttal];
      return { ...base, rebuttals: next };
    }
    case 'discarded': {
      const summary = event.content;
      if (!isPhase(summary.phase) || !isCount(summary.discarded)) return state;
      if (summary.voice !== null && !isVoiceId(summary.voice)) return state;
      const byCode = { ...base.discarded.byCode };
      if (summary.by_code && typeof summary.by_code === 'object') {
        Object.entries(summary.by_code).forEach(([code, count]) => {
          if (isCount(count)) {
            const key = code as TribunalDiscardCode;
            byCode[key] = (byCode[key] ?? 0) + count;
          }
        });
      }
      return {
        ...base,
        discarded: {
          total: base.discarded.total + summary.discarded,
          byVoice: summary.voice === null
            ? base.discarded.byVoice
            : { ...base.discarded.byVoice, [summary.voice]: base.discarded.byVoice[summary.voice] + summary.discarded },
          synthesis: summary.voice === null ? base.discarded.synthesis + summary.discarded : base.discarded.synthesis,
          byCode,
        },
      };
    }
    case 'voice_error': {
      const voiceError = event.content;
      if (!isVoiceId(voiceError.voice) || !isPhase(voiceError.phase)) return state;
      return { ...base, voiceErrors: [...base.voiceErrors, voiceError] };
    }
    case 'synthesis': {
      const synthesis = event.content;
      if (!Array.isArray(synthesis.shared_points) || !Array.isArray(synthesis.contested_points)
        || !Array.isArray(synthesis.open_questions)) return state;
      return { ...base, synthesis };
    }
    case 'done': {
      const done = event.content;
      return {
        ...base,
        status: 'completed',
        sessionId: isString(done.session_id) ? done.session_id : base.sessionId,
        reused: typeof done.reused === 'boolean' ? done.reused : base.reused,
        totals: done.totals && typeof done.totals === 'object' ? done.totals : base.totals,
        error: null,
      };
    }
    case 'error': {
      const streamError = event.content;
      return {
        ...base,
        status: 'error',
        error: {
          code: isString(streamError.code) ? streamError.code : 'internal_error',
          message: isString(streamError.message) ? streamError.message : '',
          retryable: streamError.retryable === true,
          phase: isPhase(streamError.phase) ? streamError.phase : null,
          resetsAt: null,
          httpStatus: null,
        },
      };
    }
    default:
      return state;
  }
}

/** Eventi della riproduzione di una seduta salvata, in ordine canonico (§9.4). */
export function sessionToReplayEvents(session: TribunalSession): TribunalEvent[] {
  const events: TribunalEvent[] = [
    {
      type: 'session',
      content: {
        session_id: session.session_id,
        scope: session.scope,
        reused: true,
        created_at: session.created_at,
        contract_version: session.contract_version,
        prompt_version: session.prompt_version,
        provider: session.provider,
        model: session.model,
        voices: session.voices,
      },
    },
    { type: 'case_file', content: session.case_file },
  ];
  const closingOf = (phase: TribunalPhase, voice: TribunalVoiceId): TribunalEvent | null => {
    const summary = session.discarded.find((item) => item.phase === phase && item.voice === voice);
    if (summary) return { type: 'discarded', content: summary };
    const voiceError = session.voice_errors.find((item) => item.phase === phase && item.voice === voice);
    return voiceError ? { type: 'voice_error', content: voiceError } : null;
  };
  (['apertura', 'replica'] as const).forEach((phase) => {
    events.push({ type: 'phase', content: { phase, status: 'started' } });
    TRIBUNAL_VOICE_IDS.forEach((voice) => {
      const items: TribunalEvent[] = phase === 'apertura'
        ? session.arguments.filter((item) => item.voice === voice).map((content) => ({ type: 'argument', content }))
        : session.rebuttals.filter((item) => item.voice === voice).map((content) => ({ type: 'rebuttal', content }));
      const closing = closingOf(phase, voice);
      if (!closing && items.length === 0) return; // voce che non ha partecipato alla fase
      events.push(...items);
      if (closing) events.push(closing);
    });
    events.push({ type: 'phase', content: { phase, status: 'completed' } });
  });
  events.push({ type: 'phase', content: { phase: 'sintesi', status: 'started' } });
  events.push({ type: 'synthesis', content: session.synthesis });
  const synthesisSummary = session.discarded.find((item) => item.phase === 'sintesi');
  if (synthesisSummary) events.push({ type: 'discarded', content: synthesisSummary });
  events.push({ type: 'phase', content: { phase: 'sintesi', status: 'completed' } });
  events.push({
    type: 'done',
    content: { session_id: session.session_id, reused: true, saved: false, duration_ms: 0, totals: session.totals },
  });
  return events;
}

/** Seduta salvata → stato `completed` con `reused: true` (identico alla sua riproduzione). */
export function sessionToState(session: TribunalSession): TribunalSessionState {
  return sessionToReplayEvents(session).reduce(reduceTribunalEvent, initialTribunalState);
}

type Action =
  | { kind: 'event'; event: TribunalEvent }
  | { kind: 'start' }
  | { kind: 'reset' }
  | { kind: 'abort' }
  | { kind: 'load'; session: TribunalSession }
  | { kind: 'fail'; status: 'error' | 'limit_reached'; error: TribunalClientError }
  | { kind: 'end' };

function sessionReducer(state: TribunalSessionState, action: Action): TribunalSessionState {
  switch (action.kind) {
    case 'event':
      return state.status === 'running' ? reduceTribunalEvent(state, action.event) : state;
    case 'start':
      return { ...initialTribunalState, status: 'running' };
    case 'reset':
      return initialTribunalState;
    case 'abort':
      return state.status === 'running' ? { ...state, status: 'aborted' } : state;
    case 'load':
      return sessionToState(action.session);
    case 'fail':
      return state.status === 'running' ? { ...state, status: action.status, error: action.error } : state;
    case 'end':
      // Fine dello stream senza done/error.
      return state.status === 'running'
        ? {
          ...state,
          status: 'error',
          error: {
            code: 'stream_interrupted',
            message: 'La connessione si è interrotta prima della fine della seduta.',
            retryable: true,
            phase: state.phase,
            resetsAt: null,
            httpStatus: null,
          },
        }
        : state;
    default:
      return state;
  }
}

function clientErrorOf(error: unknown, receivedEvents: boolean, phase: TribunalPhase | null): {
  status: 'error' | 'limit_reached'; error: TribunalClientError;
} {
  if (error instanceof ApiRequestError) {
    const details = error.details ?? {};
    const resetsAt = typeof details.resets_at === 'string' ? details.resets_at : null;
    const limitReached = error.status === 429 && error.code === 'daily_limit_reached';
    return {
      status: limitReached ? 'limit_reached' : 'error',
      error: {
        code: error.code ?? (error.status >= 500 ? 'internal_error' : 'invalid_request'),
        message: error.message,
        retryable: typeof details.retryable === 'boolean' ? details.retryable : error.status >= 500,
        phase: null,
        resetsAt,
        httpStatus: error.status,
      },
    };
  }
  return {
    status: 'error',
    error: receivedEvents
      ? {
        code: 'stream_interrupted',
        message: 'La connessione si è interrotta prima della fine della seduta.',
        retryable: true,
        phase,
        resetsAt: null,
        httpStatus: null,
      }
      : {
        code: 'network_error',
        message: 'Connessione interrotta prima della risposta. Controlla la rete e riprova.',
        retryable: true,
        phase: null,
        resetsAt: null,
        httpStatus: null,
      },
  };
}

export const tribunalQueryKeys = {
  status: (fingerprint: string) => ['doctor-tribunal-status', fingerprint] as const,
  latest: (fingerprint: string) => ['doctor-tribunal-latest', fingerprint] as const,
};

export interface UseTribunalSessionResult extends TribunalSessionState {
  /** Avvia la seduta (force_new false: il backend può riprodurre quella salvata). */
  start: () => void;
  /** «Rifai la seduta» (force_new true). */
  redo: () => void;
  /** Chiude la connessione → status 'aborted', contenuto conservato. */
  stop: () => void;
  loadSaved: (session: TribunalSession) => void;
  reset: () => void;
}

/**
 * Seduta del Tribunale sullo scope indicato. Cambio di fingerprint o smontaggio → abort +
 * reset; un nuovo start annulla lo stream precedente.
 */
export function useTribunalSession(portfolioIds: number[]): UseTribunalSessionResult {
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(sessionReducer, initialTribunalState);
  const fingerprint = doctorScopeFingerprint(portfolioIds);
  const idsRef = useRef(portfolioIds);
  const controllerRef = useRef<AbortController | null>(null);
  const runRef = useRef(0);

  useEffect(() => {
    idsRef.current = portfolioIds;
  });

  const cancelRun = useCallback(() => {
    runRef.current += 1;
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  useEffect(() => () => {
    cancelRun();
    dispatch({ kind: 'reset' });
  }, [fingerprint, cancelRun]);

  const run = useCallback((forceNew: boolean) => {
    cancelRun();
    const runId = runRef.current;
    const controller = new AbortController();
    controllerRef.current = controller;
    const ids = idsRef.current;
    const scopeFingerprint = doctorScopeFingerprint(ids);
    let receivedEvents = false;
    let finished = false;
    let lastPhase: TribunalPhase | null = null;
    const isCurrent = () => runRef.current === runId && !controller.signal.aborted;
    dispatch({ kind: 'start' });

    streamTribunalSession({
      portfolioIds: ids,
      forceNew,
      signal: controller.signal,
      onEvent: (event) => {
        if (!isCurrent() || finished) return;
        receivedEvents = true;
        if (event.type === 'phase' && event.content.status === 'started') lastPhase = event.content.phase;
        if (event.type === 'done' || event.type === 'error') finished = true;
        dispatch({ kind: 'event', event });
        if (event.type === 'done') {
          void queryClient.invalidateQueries({ queryKey: tribunalQueryKeys.status(scopeFingerprint) });
          void queryClient.invalidateQueries({ queryKey: tribunalQueryKeys.latest(scopeFingerprint) });
        }
      },
    }).then(
      () => {
        if (isCurrent()) dispatch({ kind: 'end' });
      },
      (error: unknown) => {
        if (!isCurrent()) return; // abort voluto (stop, cambio di scope, nuovo start, smontaggio)
        const failure = clientErrorOf(error, receivedEvents, lastPhase);
        dispatch({ kind: 'fail', status: failure.status, error: failure.error });
      },
    ).finally(() => {
      if (controllerRef.current === controller) controllerRef.current = null;
    });
  }, [cancelRun, queryClient]);

  const start = useCallback(() => run(false), [run]);
  const redo = useCallback(() => run(true), [run]);
  const stop = useCallback(() => {
    cancelRun();
    dispatch({ kind: 'abort' });
  }, [cancelRun]);
  const loadSaved = useCallback((session: TribunalSession) => {
    cancelRun();
    dispatch({ kind: 'load', session });
  }, [cancelRun]);
  const reset = useCallback(() => {
    cancelRun();
    dispatch({ kind: 'reset' });
  }, [cancelRun]);

  return { ...state, start, redo, stop, loadSaved, reset };
}

// Client errors (404 feature_disabled, 409, 429) are answers, not glitches.
function retryServerErrors(failureCount: number, error: Error): boolean {
  if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 2;
}

/** `tribunal_enabled` di GET /doctor/features (cache condivisa con useDoctorFeatures). */
export function useTribunalFeature(): { isLoading: boolean; enabled: boolean } {
  const query = useQuery({
    queryKey: doctorQueryKeys.features,
    queryFn: getDoctorFeatures,
    staleTime: 5 * 60 * 1000,
    retry: retryServerErrors,
  });
  return { isLoading: query.isLoading, enabled: query.data?.tribunal_enabled === true };
}

export function useTribunalStatus(portfolioIds: number[], enabled: boolean): UseQueryResult<TribunalStatus> {
  const fingerprint = doctorScopeFingerprint(portfolioIds);
  return useQuery({
    queryKey: tribunalQueryKeys.status(fingerprint),
    queryFn: () => getTribunalStatus(portfolioIds),
    enabled: enabled && portfolioIds.length > 0,
    retry: retryServerErrors,
  });
}

export function useTribunalLatest(portfolioIds: number[], enabled: boolean): UseQueryResult<TribunalLatestResponse | null> {
  const fingerprint = doctorScopeFingerprint(portfolioIds);
  return useQuery({
    queryKey: tribunalQueryKeys.latest(fingerprint),
    queryFn: () => getLatestTribunalSession(portfolioIds),
    enabled: enabled && portfolioIds.length > 0,
    retry: retryServerErrors,
  });
}
