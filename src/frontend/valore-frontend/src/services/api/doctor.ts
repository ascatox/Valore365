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

export const getDecumulationPlan = async (
  portfolioId: number,
  params: {
    annualWithdrawal: number;
    years: number;
    inflationRatePct?: number;
    otherIncomeAnnual?: number;
    currentAge?: number | null;
  },
): Promise<DecumulationPlanResponse> => {
  const query = new URLSearchParams({
    annual_withdrawal: String(params.annualWithdrawal),
    years: String(params.years),
    inflation_rate_pct: String(params.inflationRatePct ?? 2),
    other_income_annual: String(params.otherIncomeAnnual ?? 0),
  });
  if (params.currentAge != null && Number.isFinite(params.currentAge)) {
    query.set('current_age', String(params.currentAge));
  }
  return apiFetch<DecumulationPlanResponse>(`/portfolios/${portfolioId}/decumulation?${query.toString()}`);
};

export const getAggregateDecumulationPlan = async (
  portfolioIds: number[],
  params: {
    annualWithdrawal: number;
    years: number;
    inflationRatePct?: number;
    otherIncomeAnnual?: number;
    currentAge?: number | null;
  },
): Promise<AggregateDecumulationPlanResponse> => {
  const query = new URLSearchParams({
    annual_withdrawal: String(params.annualWithdrawal),
    years: String(params.years),
    inflation_rate_pct: String(params.inflationRatePct ?? 2),
    other_income_annual: String(params.otherIncomeAnnual ?? 0),
  });
  portfolioIds.forEach((portfolioId) => query.append('portfolio_ids', String(portfolioId)));
  if (params.currentAge != null && Number.isFinite(params.currentAge)) {
    query.set('current_age', String(params.currentAge));
  }
  return apiFetch<AggregateDecumulationPlanResponse>(`/portfolios/aggregate/decumulation?${query.toString()}`);
};
