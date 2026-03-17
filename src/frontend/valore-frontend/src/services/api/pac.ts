import { apiFetch } from './client';
import type {
  PacRuleCreateInput,
  PacRuleRead,
  PacRuleUpdateInput,
  PacExecutionRead,
  PacExecutionConfirmInput,
} from './types';

export const createPacRule = async (portfolioId: number, payload: PacRuleCreateInput): Promise<PacRuleRead> => {
  return apiFetch<PacRuleRead>(`/portfolios/${portfolioId}/pac-rules`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getPortfolioPacRules = async (portfolioId: number): Promise<PacRuleRead[]> => {
  return apiFetch<PacRuleRead[]>(`/portfolios/${portfolioId}/pac-rules`);
};

export const getPacRule = async (ruleId: number): Promise<PacRuleRead> => {
  return apiFetch<PacRuleRead>(`/pac-rules/${ruleId}`);
};

export const updatePacRule = async (ruleId: number, payload: PacRuleUpdateInput): Promise<PacRuleRead> => {
  return apiFetch<PacRuleRead>(`/pac-rules/${ruleId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
};

export const deletePacRule = async (ruleId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/pac-rules/${ruleId}`, {
    method: 'DELETE',
  });
};

export const getPacRuleExecutions = async (ruleId: number): Promise<PacExecutionRead[]> => {
  return apiFetch<PacExecutionRead[]>(`/pac-rules/${ruleId}/executions`);
};

export const getPendingPacExecutions = async (portfolioId: number): Promise<PacExecutionRead[]> => {
  return apiFetch<PacExecutionRead[]>(`/portfolios/${portfolioId}/pac-executions/pending`);
};

export const confirmPacExecution = async (
  executionId: number,
  payload: PacExecutionConfirmInput,
): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/pac-executions/${executionId}/confirm`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const skipPacExecution = async (executionId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/pac-executions/${executionId}/skip`, {
    method: 'POST',
  });
};
