import type { IconProps } from '@tabler/icons-react';
import type {
  AllocationItem,
  Portfolio,
  PortfolioSummary,
  PortfolioTargetAllocationItem,
  PortfolioTargetAssetPerformanceResponse,
  PortfolioTargetAssetIntradayPerformanceResponse,
  PortfolioTargetIntradayResponse,
  PortfolioTargetPerformanceResponse,
  Position,
  TimeSeriesPoint,
} from '../../services/api';

export interface KpiStatCardProps {
  label: string;
  value: string;
  color?: string;
  diff?: number;
  diffLabel?: string;
  icon?: React.ComponentType<IconProps>;
  iconColor?: string;
}

export interface ChartPoint {
  rawDate: string;
  date: string;
  value: number;
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

export interface DashboardData {
  portfolios: Portfolio[];
  selectedPortfolioId: string | null;
  setSelectedPortfolioId: (id: string | null) => void;
  selectedPortfolio: Portfolio | null;
  allocation: PortfolioTargetAllocationItem[];
  portfolioSummary: PortfolioSummary | null;
  portfolioPositions: Position[];
  portfolioAllocation: AllocationItem[];
  portfolioTimeseries: TimeSeriesPoint[];
  targetPerformance: PortfolioTargetPerformanceResponse | null;
  assetPerformance: PortfolioTargetAssetPerformanceResponse | null;
  assetIntradayPerformance: PortfolioTargetAssetIntradayPerformanceResponse | null;
  mainIntradayData: PortfolioTargetIntradayResponse | null;
  chartWindow: string;
  setChartWindow: (w: string) => void;
  chartData: ChartPoint[];
  mainIntradayChartData: IntradayChartPoint[];
  assetMiniCharts: AssetMiniChartData[];
  loading: boolean;
  dataLoading: boolean;
  refreshing: boolean;
  mainIntradayLoading: boolean;
  assetIntradayLoading: boolean;
  error: string | null;
  refreshMessage: string | null;
  chartWindowDays: number;
  mvpCurrency: string;
  mvpTimeseriesData: ChartPoint[];
  mvpTimeseriesStats: { last: number; pct: number } | null;
  handleDailyChartClick: (state: any) => void;
  intradayOpen: boolean;
  setIntradayOpen: (open: boolean) => void;
  intradayLoading: boolean;
  intradayError: string | null;
  intradayChartData: IntradayChartPoint[];
  intradayStats: { open: number; last: number; min: number; max: number; dayPct: number } | null;
  intradayDateLabel: string | null;
  indexCardStats: { index: number; diffPts: number; diffPct: number } | null;
  mainChartStats: { last: number; periodPct: number } | null;
}
