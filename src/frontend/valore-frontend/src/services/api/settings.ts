import { apiFetch } from './client';
import type {
  UserSettings,
  UserSettingsUpdateInput,
  CopilotStatus,
  InstantAnalyzeRequest,
  InstantAnalyzeResponse,
  InstantPortfolioImportResponse,
  InstantInsightExplainRequest,
  InstantInsightExplainResponse,
  AdminUsageSummary,
} from './types';
import type { ApiErrorPayload } from './client';
import { API_URL } from './client';

export const getUserSettings = async (): Promise<UserSettings> => {
  return apiFetch<UserSettings>('/settings/user');
};

export const updateUserSettings = async (payload: UserSettingsUpdateInput): Promise<UserSettings> => {
  return apiFetch<UserSettings>('/settings/user', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
};

export const getCopilotStatus = async (): Promise<CopilotStatus> => {
  return apiFetch<CopilotStatus>('/copilot/status');
};

export const analyzeInstantPortfolio = async (payload: InstantAnalyzeRequest): Promise<InstantAnalyzeResponse> => {
  return apiFetch<InstantAnalyzeResponse>('/public/portfolio/analyze', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const explainInstantInsight = async (
  payload: InstantInsightExplainRequest,
): Promise<InstantInsightExplainResponse> => {
  return apiFetch<InstantInsightExplainResponse>('/public/portfolio/explain-insight', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const importInstantPortfolioCsv = async (
  file: File,
  broker = 'fineco',
): Promise<InstantPortfolioImportResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('broker', broker);

  const response = await fetch(`${API_URL}/public/portfolio/import-csv`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorPayload;
      if (body?.error?.message) message = body.error.message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  return response.json() as Promise<InstantPortfolioImportResponse>;
};

export const getAdminUsageSummary = async (): Promise<AdminUsageSummary> => {
  return apiFetch<AdminUsageSummary>('/admin/usage-summary');
};
