import { apiFetch } from './client';
import type {
  PortfolioHealthResponse,
  XRayResponse,
  MonteCarloProjectionResponse,
  StressTestResponse,
  DecumulationPlanResponse,
  AggregateDecumulationPlanResponse,
  DoctorFeatures,
  DoctorMetricDefinition,
  DoctorPolicyDocument,
  DoctorPolicyEvaluation,
  DoctorPolicyPreviewResponse,
  DoctorPolicyRead,
  DoctorPolicySource,
  DoctorPolicyTemplate,
  DoctorPolicyValidateResponse,
  DoctorPolicyVersion,
  DoctorScenarioCompareRequest,
  DoctorScenarioCompareResponse,
  DoctorScenarioRequest,
  DoctorScenarioResult,
} from './types';

export const getPortfolioHealth = async (portfolioId: number): Promise<PortfolioHealthResponse> => {
  return apiFetch<PortfolioHealthResponse>(`/portfolios/${portfolioId}/health`);
};

export const getPortfolioXray = async (portfolioId: number): Promise<XRayResponse> => {
  return apiFetch<XRayResponse>(`/portfolios/${portfolioId}/xray`);
};

export const getMonteCarloProjection = async (portfolioId: number): Promise<MonteCarloProjectionResponse> => {
  return apiFetch<MonteCarloProjectionResponse>(`/portfolios/${portfolioId}/monte-carlo`);
};

export const getStressTest = async (portfolioId: number): Promise<StressTestResponse> => {
  return apiFetch<StressTestResponse>(`/portfolios/${portfolioId}/stress-test`);
};

export interface DecumulationScheduleParams {
  capitalFloor?: number;
  pensionAnnual?: number;
  pensionStartAge?: number | null;
  oneOffExpenses?: Array<{ age: number; amount: number }>;
  /** Desired range of the capital left at the end of the horizon, in today's money. */
  terminalTargetMin?: number;
  terminalTargetMax?: number;
}

function appendDecumulationScheduleParams(query: URLSearchParams, params: DecumulationScheduleParams) {
  if (params.capitalFloor && params.capitalFloor > 0) {
    query.set('capital_floor', String(params.capitalFloor));
  }
  if (params.pensionAnnual && params.pensionAnnual > 0) {
    query.set('pension_annual', String(params.pensionAnnual));
    if (params.pensionStartAge != null && Number.isFinite(params.pensionStartAge)) {
      query.set('pension_start_age', String(params.pensionStartAge));
    }
  }
  (params.oneOffExpenses ?? []).forEach((expense) => {
    query.append('one_off_ages', String(expense.age));
    query.append('one_off_amounts', String(expense.amount));
  });
  if (params.terminalTargetMin && params.terminalTargetMin > 0) {
    query.set('terminal_target_min', String(params.terminalTargetMin));
  }
  if (params.terminalTargetMax && params.terminalTargetMax > 0) {
    query.set('terminal_target_max', String(params.terminalTargetMax));
  }
}

export const getDecumulationPlan = async (
  portfolioId: number,
  params: {
    annualWithdrawal: number;
    years: number;
    inflationRatePct?: number;
    otherIncomeAnnual?: number;
    capitalGainsTaxRatePct?: number;
    currentAge?: number | null;
  } & DecumulationScheduleParams,
): Promise<DecumulationPlanResponse> => {
  const query = new URLSearchParams({
    annual_withdrawal: String(params.annualWithdrawal),
    years: String(params.years),
    inflation_rate_pct: String(params.inflationRatePct ?? 2),
    other_income_annual: String(params.otherIncomeAnnual ?? 0),
    capital_gains_tax_rate_pct: String(params.capitalGainsTaxRatePct ?? 26),
  });
  if (params.currentAge != null && Number.isFinite(params.currentAge)) {
    query.set('current_age', String(params.currentAge));
  }
  appendDecumulationScheduleParams(query, params);
  return apiFetch<DecumulationPlanResponse>(`/portfolios/${portfolioId}/decumulation?${query.toString()}`);
};

export const getAggregateDecumulationPlan = async (
  portfolioIds: number[],
  params: {
    annualWithdrawal: number;
    years: number;
    inflationRatePct?: number;
    otherIncomeAnnual?: number;
    capitalGainsTaxRatePct?: number;
    currentAge?: number | null;
  } & DecumulationScheduleParams,
): Promise<AggregateDecumulationPlanResponse> => {
  const query = new URLSearchParams({
    annual_withdrawal: String(params.annualWithdrawal),
    years: String(params.years),
    inflation_rate_pct: String(params.inflationRatePct ?? 2),
    other_income_annual: String(params.otherIncomeAnnual ?? 0),
    capital_gains_tax_rate_pct: String(params.capitalGainsTaxRatePct ?? 26),
  });
  portfolioIds.forEach((portfolioId) => query.append('portfolio_ids', String(portfolioId)));
  if (params.currentAge != null && Number.isFinite(params.currentAge)) {
    query.set('current_age', String(params.currentAge));
  }
  appendDecumulationScheduleParams(query, params);
  return apiFetch<AggregateDecumulationPlanResponse>(`/portfolios/aggregate/decumulation?${query.toString()}`);
};

// ---------------------------------------------------------------------------
// Portfolio Doctor 2.0 (docs/doctor2/api-contracts.md §5, §8)
// ---------------------------------------------------------------------------

/** `portfolio_ids=1&portfolio_ids=2` for the exact scope (sorted, unique). */
export function doctorScopeQuery(portfolioIds: number[]): string {
  const query = new URLSearchParams();
  [...new Set(portfolioIds)].sort((left, right) => left - right)
    .forEach((id) => query.append('portfolio_ids', String(id)));
  return query.toString();
}

/** Same string as the backend `scope_fingerprint` (used as a cache key). */
export function doctorScopeFingerprint(portfolioIds: number[]): string {
  return `p:${[...new Set(portfolioIds)].sort((left, right) => left - right).join(',')}`;
}

const postJson = <T>(path: string, body: unknown) => apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body) });

export const getDoctorFeatures = () => apiFetch<DoctorFeatures>('/doctor/features');

export const getDoctorMetrics = async (): Promise<DoctorMetricDefinition[]> => {
  const body = await apiFetch<DoctorMetricDefinition[] | { metrics: DoctorMetricDefinition[] }>('/doctor/metrics');
  return Array.isArray(body) ? body : (body?.metrics ?? []);
};

export const getDoctorTemplates = async (): Promise<DoctorPolicyTemplate[]> => {
  const body = await apiFetch<DoctorPolicyTemplate[] | { templates: DoctorPolicyTemplate[] }>('/doctor/templates');
  return Array.isArray(body) ? body : (body?.templates ?? []);
};

export const getDoctorPolicy = async (portfolioIds: number[]): Promise<DoctorPolicyRead | null> => {
  const body = await apiFetch<{ policy?: DoctorPolicyRead | null }>(`/doctor/policies?${doctorScopeQuery(portfolioIds)}`);
  return body?.policy ?? null;
};

export const getDoctorEvaluation = (portfolioIds: number[]) =>
  apiFetch<DoctorPolicyEvaluation>(`/doctor/evaluation?${doctorScopeQuery(portfolioIds)}`);

export const validateDoctorPolicy = (portfolioIds: number[], document: DoctorPolicyDocument) =>
  postJson<DoctorPolicyValidateResponse>('/doctor/policies/validate', { portfolio_ids: portfolioIds, document });

export const previewDoctorPolicy = (params: {
  portfolioIds: number[];
  document: DoctorPolicyDocument;
  baseVersion: number | null;
  source: DoctorPolicySource;
}) => postJson<DoctorPolicyPreviewResponse>('/doctor/policies/preview', {
  portfolio_ids: params.portfolioIds,
  document: params.document,
  base_version: params.baseVersion,
  source: params.source,
});

export const saveDoctorPolicy = (params: {
  portfolioIds: number[];
  name: string;
  document: DoctorPolicyDocument;
  baseVersion: number | null;
  confirmationToken: string;
}) => postJson<DoctorPolicyRead>('/doctor/policies', {
  portfolio_ids: params.portfolioIds,
  name: params.name,
  document: params.document,
  base_version: params.baseVersion,
  confirmation_token: params.confirmationToken,
});

export const getDoctorPolicyVersions = async (policyId: number): Promise<DoctorPolicyVersion[]> => {
  const body = await apiFetch<DoctorPolicyVersion[] | { versions: DoctorPolicyVersion[] }>(`/doctor/policies/${policyId}/versions`);
  return Array.isArray(body) ? body : (body?.versions ?? []);
};

export const restoreDoctorPolicyVersion = (policyId: number, versionNumber: number, baseVersion: number) =>
  postJson<DoctorPolicyRead>(`/doctor/policies/${policyId}/restore`, { version_number: versionNumber, base_version: baseVersion });

export const previewDoctorScenario = (request: DoctorScenarioRequest) =>
  postJson<DoctorScenarioResult>('/doctor/scenarios/preview', request);

export const compareDoctorScenarios = (request: DoctorScenarioCompareRequest) =>
  postJson<DoctorScenarioCompareResponse>('/doctor/scenarios/compare', request);
