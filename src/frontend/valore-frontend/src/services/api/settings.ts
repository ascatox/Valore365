import { apiFetch } from './client';
import type {
  UserSettings,
  UserSettingsUpdateInput,
  CopilotStatus,
  InstantAnalyzeRequest,
  InstantAnalyzeResponse,
  InstantInsightExplainRequest,
  InstantInsightExplainResponse,
  AdminUsageSummary,
} from './types';

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

export const getAdminUsageSummary = async (): Promise<AdminUsageSummary> => {
  return apiFetch<AdminUsageSummary>('/admin/usage-summary');
};
