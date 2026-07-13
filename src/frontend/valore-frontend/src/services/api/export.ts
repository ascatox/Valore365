import { API_URL, getAuthToken } from './client';
import type { ApiErrorPayload } from './client';

export const getPortfolioMarkdown = async (
  portfolioId: number,
): Promise<{ text: string; filename: string }> => {
  const token = await getAuthToken();
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${API_URL}/portfolios/${portfolioId}/export/markdown`, {
    method: 'GET',
    headers: { ...authHeaders },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorPayload;
      if (body?.error?.message) message = body.error.message;
    } catch { /* ignore */ }
    throw new Error(message);
  }

  const text = await response.text();
  const disposition = response.headers.get('content-disposition') || '';
  const filenameMatch = disposition.match(/filename="([^"]+)"/i);
  return {
    text,
    filename: filenameMatch?.[1] || `valore365-portfolio-${portfolioId}.md`,
  };
};
