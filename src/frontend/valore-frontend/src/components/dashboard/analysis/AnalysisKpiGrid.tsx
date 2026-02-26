import { IconCoin, IconActivity, IconArrowUpRight, IconChartPie } from '@tabler/icons-react';
import { KpiStatsGrid } from '../summary/KpiStatsGrid';
import { formatMoney, formatPct, formatShortDate, getVariationColor } from '../formatters';
import type { PortfolioTargetAllocationItem, Portfolio, PortfolioSummary } from '../../../services/api';
import type { PerformerItem } from '../types';

interface AnalysisKpiGridProps {
  indexCardStats: { index: number; diffPts: number; diffPct: number } | null;
  totalAssignedWeight: number;
  allocation: PortfolioTargetAllocationItem[];
  selectedPortfolio: Portfolio | null;
  portfolioSummary: PortfolioSummary | null;
  currency: string;
  bestPerformer: PerformerItem | null;
  worstPerformer: PerformerItem | null;
}

export function AnalysisKpiGrid({
  indexCardStats,
  totalAssignedWeight,
  portfolioSummary,
  currency,
  bestPerformer,
  worstPerformer,
}: AnalysisKpiGridProps) {
  const best = bestPerformer;
  const worst = worstPerformer;

  const items = [
    {
      label: 'Var. Attuale Portafoglio',
      value: portfolioSummary
        ? `${formatMoney(portfolioSummary.day_change, currency, true)} (${formatPct(portfolioSummary.day_change_pct)})`
        : 'N/D',
      color: getVariationColor(portfolioSummary?.day_change ?? 0),
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
