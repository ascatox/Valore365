import type { IconProps } from '@tabler/icons-react';

export interface KpiStatCardProps {
  label: string;
  value: string;
  color?: string;
  diff?: number;
  diffLabel?: string;
  icon?: React.ComponentType<IconProps>;
  iconColor?: string;
  subtitle?: string;
  subtitleColor?: string;
  /** When set, renders a small semicircular gauge coloured by sign */
  gaugeValue?: number;
}

export interface ChartPoint {
  rawDate: string;
  date: string;
  value: number;
}

export interface GainChartPoint {
  rawDate: string;
  date: string;
  portfolioValue: number;
  netInvested: number;
}

export interface IntradayChartPoint {
  ts: string;
  time: string;
  value: number;
}

export interface AssetMiniChartData {
  asset_id: number;
  symbol: string;
  name: string;
  weight_pct: number;
  return_pct: number;
  as_of: string | null;
  chart: Array<{ rawDate?: string; date?: string; time?: string; value: number }>;
}

export interface ComparisonChartPoint {
  date: string;
  rawDate: string;
  portfolio: number;
  benchmark: number;
}

export interface AllocationDoughnutItem {
  name: string;
  value: number;
  asset_id?: number;
}

export interface PerformerItem {
  symbol: string;
  name: string;
  return_pct: number;
  as_of: string | null;
  asset_id: number;
}
