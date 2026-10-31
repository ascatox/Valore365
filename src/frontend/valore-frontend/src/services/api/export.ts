import { API_URL, ApiRequestError, getAuthToken } from './client';
import type { ApiErrorPayload } from './client';

export interface MarkdownExport {
  text: string;
  filename: string;
}

/**
 * GET a Markdown export (`text/markdown` attachment). Errors are thrown as
 * ApiRequestError with the API's status and code, like apiFetch.
 */
export async function fetchMarkdownExport(path: string, fallbackFilename: string): Promise<MarkdownExport> {
  const token = await getAuthToken();
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${API_URL}${path}`, {
    method: 'GET',
    headers: { ...authHeaders },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    let code: string | null = null;
    try {
      const body = (await response.json()) as ApiErrorPayload;
      if (body?.error?.message) message = body.error.message;
      code = body?.error?.code ?? null;
    } catch { /* ignore */ }
    throw new ApiRequestError({ message, code, status: response.status });
  }

  const text = await response.text();
  const disposition = response.headers.get('content-disposition') || '';
  const filenameMatch = disposition.match(/filename="([^"]+)"/i);
  return { text, filename: filenameMatch?.[1] || fallbackFilename };
}

export const getPortfolioMarkdown = (portfolioId: number): Promise<MarkdownExport> =>
  fetchMarkdownExport(`/portfolios/${portfolioId}/export/markdown`, `valore365-portfolio-${portfolioId}.md`);
