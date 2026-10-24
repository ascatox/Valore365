import { apiFetch } from './client';
import type {
  PortfolioHealthResponse,
  XRayResponse,
  MonteCarloProjectionResponse,
  StressTestResponse,
  DecumulationPlanResponse,
  AggregateDecumulationPlanResponse,
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
