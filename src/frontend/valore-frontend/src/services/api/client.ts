export const API_URL = import.meta.env.VITE_API_BASE_URL || '/api';

type TokenGetter = () => Promise<string | null>;
let _getToken: TokenGetter = async () => null;
export function setTokenGetter(fn: TokenGetter): void {
  _getToken = fn;
}
export function getAuthToken(): Promise<string | null> {
  return _getToken();
}

export interface ApiErrorPayload {
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown> | null;
  };
}

export class ApiRequestError extends Error {
  code: string | null;
  status: number;
  details: Record<string, unknown> | null;

  constructor({
    message,
    code,
    status,
    details,
  }: {
    message: string;
    code?: string | null;
    status: number;
    details?: Record<string, unknown> | null;
  }) {
    super(message);
    this.name = 'ApiRequestError';
    this.code = code ?? null;
    this.status = status;
    this.details = details ?? null;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await _getToken();
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${API_URL}${path}`, {
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    let code: string | null = null;
    let details: Record<string, unknown> | null = null;
    try {
      const body = (await response.json()) as ApiErrorPayload;
      if (body?.error?.message) {
        message = body.error.message;
      }
      code = body?.error?.code ?? null;
      details = body?.error?.details ?? null;
    } catch {
      const text = await response.text().catch(() => '');
      if (text) {
        message = text;
      }
    }
    throw new ApiRequestError({ message, code, status: response.status, details });
  }

  return response.json() as Promise<T>;
}
