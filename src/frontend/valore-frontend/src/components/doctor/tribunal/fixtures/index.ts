// Seduta di esempio del contratto (docs/tribunale/fixtures/, copiata senza modifiche) e un
// finto stream per test e sviluppo dell'interfaccia senza backend (architecture.md §3.1).
import { parseTribunalSseText } from '../../../../services/api/tribunal';
import type { TribunalEvent, TribunalSession } from '../../../../services/api/tribunalTypes';
import sessionFixtureRaw from './seduta-esempio.json?raw';
import sseFixtureRaw from './seduta-esempio.sse.txt?raw';

/** Testo SSE della fixture, così come lo invia il backend (con keepalive). */
export const tribunalSseFixtureText: string = sseFixtureRaw;

/** `session` di seduta-esempio.json. */
export const tribunalSessionFixture: TribunalSession = (JSON.parse(sessionFixtureRaw) as { session: TribunalSession }).session;

/** Gli eventi di seduta-esempio.sse.txt, nell'ordine dello stream dal vivo. */
export const tribunalEventsFixture: TribunalEvent[] = parseTribunalSseText(sseFixtureRaw);

export interface FakeTribunalResponseOptions {
  /** Divide i byte dello stream in pezzi di questa dimensione (righe e caratteri spezzati). */
  chunkSize?: number;
  /** Dopo questo numero di eventi lo stream fallisce (connessione caduta). */
  failAfterEvents?: number;
  /** Status HTTP; se non 2xx la risposta è JSON con `errorBody`. */
  status?: number;
  /** Corpo JSON di una risposta non 2xx (default: formato errori del Doctor con codice generico). */
  errorBody?: unknown;
  /** Dopo questo numero di eventi lo stream resta aperto senza inviare altro (seduta in corso). */
  pauseAfterEvents?: number;
}

function toSseBlocks(events: TribunalEvent[] | string): { text: string; isEvent: boolean }[] {
  if (typeof events !== 'string') {
    return events.map((event) => ({ text: `data: ${JSON.stringify(event)}\n\n`, isEvent: true }));
  }
  const blocks: { text: string; isEvent: boolean }[] = [];
  const parts = events.split('\n\n');
  parts.forEach((part, index) => {
    const isLast = index === parts.length - 1;
    const text = isLast ? part : `${part}\n\n`;
    if (text) blocks.push({ text, isEvent: part.split('\n').some((line) => line.startsWith('data: ')) });
  });
  return blocks;
}

/**
 * Risposta finta di POST /doctor/tribunal/sessions: stream SSE degli eventi (o testo SSE grezzo),
 * oppure errore JSON se `status` non è 2xx.
 */
export function createFakeTribunalResponse(
  events: TribunalEvent[] | string,
  options: FakeTribunalResponseOptions = {},
): Response {
  const status = options.status ?? 200;
  if (status < 200 || status > 299) {
    const body = options.errorBody ?? {
      error: { code: 'internal_error', message: `HTTP ${status}`, details: { retryable: false } },
    };
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  }

  const encoder = new TextEncoder();
  const blocks = toSseBlocks(events);
  const limit = options.failAfterEvents ?? options.pauseAfterEvents;
  let text = '';
  let eventCount = 0;
  for (const block of blocks) {
    if (limit !== undefined && block.isEvent && eventCount >= limit) break;
    text += block.text;
    if (block.isEvent) eventCount += 1;
  }
  const bytes = encoder.encode(text);
  const chunkSize = options.chunkSize && options.chunkSize > 0 ? options.chunkSize : null;
  const chunks: Uint8Array[] = [];
  if (chunkSize) {
    for (let offset = 0; offset < bytes.length; offset += chunkSize) chunks.push(bytes.slice(offset, offset + chunkSize));
  } else {
    let pending = '';
    let count = 0;
    for (const block of blocks) {
      if (limit !== undefined && block.isEvent && count >= limit) break;
      pending += block.text;
      if (block.isEvent) {
        chunks.push(encoder.encode(pending));
        pending = '';
        count += 1;
      }
    }
    if (pending) chunks.push(encoder.encode(pending));
  }

  let index = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(chunks[index]);
        index += 1;
        return;
      }
      if (options.failAfterEvents !== undefined) {
        controller.error(new TypeError('network error'));
      } else if (options.pauseAfterEvents !== undefined) {
        return new Promise<void>(() => undefined); // resta aperto finché non viene annullato
      } else {
        controller.close();
      }
      return undefined;
    },
  });
  return new Response(body, {
    status,
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
  });
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError');
}

/**
 * `fetch` finto che restituisce `responseFactory()` e rispetta `init.signal` come fetch:
 * abort prima della risposta → AbortError; abort durante la lettura → lo stream fallisce con AbortError.
 */
export function createFakeTribunalFetch(responseFactory: () => Response): typeof fetch {
  const fakeFetch = async (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const signal = init?.signal ?? undefined;
    if (signal?.aborted) throw abortError();
    const response = responseFactory();
    if (!response.body || !signal) return response;
    const reader = response.body.getReader();
    const wrapped = new ReadableStream<Uint8Array>({
      start(controller) {
        signal.addEventListener('abort', () => {
          try {
            controller.error(abortError());
          } catch {
            // già chiuso
          }
          reader.cancel().catch(() => undefined);
        }, { once: true });
      },
      async pull(controller) {
        try {
          const chunk = await reader.read();
          if (chunk.done) controller.close();
          else controller.enqueue(chunk.value);
        } catch (error) {
          try {
            controller.error(signal.aborted ? abortError() : error);
          } catch {
            // già in errore
          }
        }
      },
      cancel(reason) {
        return reader.cancel(reason);
      },
    });
    return new Response(wrapped, { status: response.status, statusText: response.statusText, headers: response.headers });
  };
  return fakeFetch as typeof fetch;
}
