// Tribunale del portafoglio — client API (docs/tribunale/api-contracts.md §3, §9;
// firme in docs/tribunale/architecture.md §3.1).
import { API_URL, ApiRequestError, apiFetch, getAuthToken, type ApiErrorPayload } from './client';
import { doctorScopeQuery } from './doctor';
import type { TribunalEvent, TribunalEventType, TribunalLatestResponse, TribunalStatus } from './tribunalTypes';

const TRIBUNAL_EVENT_TYPES: ReadonlySet<TribunalEventType> = new Set<TribunalEventType>([
  'session', 'case_file', 'phase', 'argument', 'rebuttal', 'discarded', 'voice_error', 'synthesis', 'done', 'error',
]);

function normalizedIds(portfolioIds: number[]): number[] {
  return [...new Set(portfolioIds)].sort((left, right) => left - right);
}

/** GET /doctor/tribunal/status?<doctorScopeQuery> (§3.1). */
export const getTribunalStatus = (portfolioIds: number[]): Promise<TribunalStatus> =>
  apiFetch<TribunalStatus>(`/doctor/tribunal/status?${doctorScopeQuery(portfolioIds)}`);

/**
 * GET /doctor/tribunal/sessions/latest (§3.3). `null` se l'endpoint non esiste
 * (404 senza `error.code`); rilancia ApiRequestError per not_found / feature_disabled.
 */
export async function getLatestTribunalSession(portfolioIds: number[]): Promise<TribunalLatestResponse | null> {
  try {
    return await apiFetch<TribunalLatestResponse>(`/doctor/tribunal/sessions/latest?${doctorScopeQuery(portfolioIds)}`);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404 && !error.code) return null;
    throw error;
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Payload di una riga `data: ` → evento. JSON.parse + controllo di forma minimo:
 * `type` noto e `content` oggetto, altrimenti `null` (evento da ignorare, §9.1).
 */
export function parseTribunalEvent(payload: string): TribunalEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    return null;
  }
  if (!isPlainObject(parsed)) return null;
  const { type, content } = parsed;
  if (typeof type !== 'string' || !TRIBUNAL_EVENT_TYPES.has(type as TribunalEventType)) return null;
  if (!isPlainObject(content)) return null;
  return { type, content } as TribunalEvent;
}

/**
 * Parser incrementale dello stream SSE, come CopilotChat: accumula il buffer, divide su
 * `\n`, considera solo le righe `data: `; keepalive (`: keepalive`) e righe vuote ignorati.
 */
export function createTribunalSseParser(onEvent: (event: TribunalEvent) => void) {
  let buffer = '';
  const handleLine = (rawLine: string) => {
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
    if (!line.startsWith('data: ')) return;
    const event = parseTribunalEvent(line.slice(6));
    if (event) onEvent(event);
  };
  return {
    push(text: string) {
      buffer += text;
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      lines.forEach(handleLine);
    },
    /** Fine dello stream: elabora un'eventuale ultima riga senza `\n`. */
    flush() {
      const rest = buffer;
      buffer = '';
      if (rest) handleLine(rest);
    },
  };
}

/** Tutti gli eventi validi di un testo SSE completo (es. la fixture `.sse.txt`). */
export function parseTribunalSseText(text: string): TribunalEvent[] {
  const events: TribunalEvent[] = [];
  const parser = createTribunalSseParser((event) => events.push(event));
  parser.push(text);
  parser.flush();
  return events;
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError');
}

/** Errore di una risposta non 2xx, con lo stesso risultato di apiFetch. */
async function responseError(response: Response): Promise<ApiRequestError> {
  let message = `HTTP ${response.status}`;
  let code: string | null = null;
  let details: Record<string, unknown> | null = null;
  const text = await response.text().catch(() => '');
  try {
    const body = JSON.parse(text) as ApiErrorPayload;
    if (body?.error?.message) message = body.error.message;
    code = body?.error?.code ?? null;
    details = body?.error?.details ?? null;
  } catch {
    if (text) message = text;
  }
  return new ApiRequestError({ message, code, status: response.status, details });
}

export interface StreamTribunalSessionOptions {
  portfolioIds: number[];
  forceNew?: boolean;
  signal?: AbortSignal;
  onEvent: (event: TribunalEvent) => void;
  fetchImpl?: typeof fetch;
}

/**
 * POST /doctor/tribunal/sessions (§3.2) e lettura dello stream SSE (§9).
 * Stesso token di apiFetch; risposta non 2xx → ApiRequestError; si risolve a fine stream;
 * l'abort rigetta con un AbortError.
 */
export async function streamTribunalSession(options: StreamTribunalSessionOptions): Promise<void> {
  const { portfolioIds, forceNew = false, signal, onEvent } = options;
  const fetchFn = options.fetchImpl ?? fetch;
  const token = await getAuthToken();
  if (signal?.aborted) throw abortError();
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'text/event-stream' };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetchFn(`${API_URL}/doctor/tribunal/sessions`, {
    method: 'POST',
    cache: 'no-store',
    headers,
    body: JSON.stringify({ portfolio_ids: normalizedIds(portfolioIds), force_new: forceNew }),
    signal,
  });
  if (!response.ok) throw await responseError(response);
  if (!response.body) return;

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createTribunalSseParser((event) => {
    if (!signal?.aborted) onEvent(event);
  });
  const onAbort = () => {
    reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener('abort', onAbort, { once: true });
  try {
    for (;;) {
      if (signal?.aborted) throw abortError();
      const chunk = await reader.read();
      if (signal?.aborted) throw abortError();
      if (chunk.done) break;
      parser.push(decoder.decode(chunk.value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.flush();
  } catch (error) {
    if (signal?.aborted) throw abortError();
    throw error;
  } finally {
    signal?.removeEventListener('abort', onAbort);
  }
}
