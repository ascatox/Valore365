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

export type CreatorMethod = 'model' | 'profile' | 'manual';
