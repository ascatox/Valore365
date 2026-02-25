import { IconCoin, IconActivity, IconArrowUpRight, IconChartPie } from '@tabler/icons-react';
import { KpiStatsGrid } from '../summary/KpiStatsGrid';
import { formatPct, formatShortDate } from '../formatters';
import type { PortfolioTargetPerformanceResponse, PortfolioTargetAllocationItem, Portfolio } from '../../../services/api';

interface AnalysisKpiGridProps {
  indexCardStats: { index: number; diffPts: number; diffPct: number } | null;
  totalAssignedWeight: number;
  targetPerformance: PortfolioTargetPerformanceResponse | null;
  allocation: PortfolioTargetAllocationItem[];
  selectedPortfolio: Portfolio | null;
}

export function AnalysisKpiGrid({
  indexCardStats,
  totalAssignedWeight,
  targetPerformance,
}: AnalysisKpiGridProps) {
  const best = targetPerformance?.best ?? null;
  const worst = targetPerformance?.worst ?? null;

  const items = [
    {
      label: 'Indice Portafoglio',
      value: indexCardStats ? indexCardStats.index.toFixed(2) : 'N/D',
      icon: IconCoin,
      iconColor: 'blue' as const,
    },
    {
      label: 'Peso Assegnato',
      value: `${totalAssignedWeight.toFixed(2)}%`,
      icon: IconActivity,
      iconColor: 'teal' as const,
    },
    {
      label: best?.as_of ? `Migliore (al ${formatShortDate(best.as_of)})` : 'Titolo Migliore',
      value: best ? `${best.symbol} ${formatPct(best.return_pct)}` : 'N/D',
      color: 'green',
      icon: IconArrowUpRight,
      iconColor: 'green' as const,
    },
    {
      label: worst?.as_of ? `Peggiore (al ${formatShortDate(worst.as_of)})` : 'Titolo Peggiore',
      value: worst ? `${worst.symbol} ${formatPct(worst.return_pct)}` : 'N/D',
      color: 'red',
      icon: IconChartPie,
      iconColor: 'orange' as const,
    },
  ];

  return <KpiStatsGrid items={items} cols={{ base: 2, sm: 2, md: 4 }} />;
}
