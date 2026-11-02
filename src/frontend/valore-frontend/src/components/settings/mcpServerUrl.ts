import { API_URL } from '../../services/api/client';

export const MCP_USER_GUIDE_URL = 'https://github.com/ascatox/Valore365/blob/main/docs/mcp-guida-utente.md';

/**
 * URL of the backend MCP endpoint. The server is mounted at `/mcp` on the
 * backend origin (outside the `/api` prefix), so it is derived from the
 * origin of the configured API base URL. VITE_MCP_SERVER_URL overrides it,
 * for deployments where the frontend calls the API through a relative path
 * that does not also forward `/mcp`.
 */
export function resolveMcpServerUrl(
  apiUrl: string,
  pageOrigin: string,
  override?: string,
): string {
  const explicit = override?.trim();
  if (explicit) return explicit.replace(/\/+$/, '');
  try {
    return `${new URL(apiUrl, pageOrigin).origin}/mcp`;
  } catch {
    return `${pageOrigin.replace(/\/+$/, '')}/mcp`;
  }
}

export function getMcpServerUrl(): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
  return resolveMcpServerUrl(API_URL, origin, import.meta.env.VITE_MCP_SERVER_URL as string | undefined);
}
