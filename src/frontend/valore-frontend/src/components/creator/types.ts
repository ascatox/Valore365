export type RiskLevel = 'low' | 'medium-low' | 'medium' | 'high' | 'very-high';

export interface AllocationSlot {
  label: string;
  weight: number;
  color: string;
  ticker?: string;
  isin?: string;
}

export interface PortfolioModel {
  id: string;
  name: string;
  subtitle: string;
  description: string;
  risk: RiskLevel;
  slots: AllocationSlot[];
  tags: string[];
}

export interface ProfileAnswers {
  horizon: 'lt5' | '5to10' | '10to20' | 'gt20';
  riskTolerance: 'sell_all' | 'sell_some' | 'hold' | 'buy_more';
  objective: 'capital_preservation' | 'moderate_growth' | 'max_growth' | 'income';
}

export interface PortfolioModelRecommendation {
  model: PortfolioModel;
  score: number;
  reason: string;
}

export type CreatorMethod = 'model' | 'profile' | 'manual';
