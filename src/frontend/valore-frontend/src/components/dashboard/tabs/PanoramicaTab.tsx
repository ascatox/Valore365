import { useMemo } from 'react';
import { Alert, Grid, Paper, SegmentedControl, Text } from '@mantine/core';
import { IconAlertTriangle, IconCoin, IconActivity, IconArrowUpRight } from '@tabler/icons-react';
import { KpiStatsGrid } from '../summary/KpiStatsGrid';
import { PerformanceChart } from '../summary/PerformanceChart';
import { AllocationDoughnut } from '../summary/AllocationDoughnut';
import { BestWorstCards } from '../summary/BestWorstCards';
import { DASHBOARD_WINDOWS } from '../constants';
import { formatMoney, formatPct, getVariationColor } from '../formatters';
import type { DashboardData, PerformerItem, AllocationDoughnutItem } from '../types';

interface PanoramicaTabProps {
  data: DashboardData;
}

export function PanoramicaTab({ data }: PanoramicaTabProps) {
  const {
    portfolioSummary,
    portfolioAllocation,
    mvpCurrency,
    mvpTimeseriesData,
    mvpTimeseriesStats,
    chartWindow,
    setChartWindow,
    chartWindowDays,
    mainIntradayChartData,
    mainIntradayLoading,
    assetPerformance,
    targetPerformance,
    dataCoverage,
  } = data;

  const kpiItems = useMemo(() => [
    {
      label: 'Valore Totale',
      value: portfolioSummary ? formatMoney(portfolioSummary.market_value, mvpCurrency) : 'N/D',
      icon: IconCoin,
      iconColor: 'blue' as const,
    },
    {
      label: 'P/L Totale',
      value: portfolioSummary ? formatMoney(portfolioSummary.unrealized_pl, mvpCurrency, true) : 'N/D',
      color: getVariationColor(portfolioSummary?.unrealized_pl ?? 0),
      icon: IconActivity,
      iconColor: 'teal' as const,
    },
    {
      label: 'P/L %',
      value: portfolioSummary ? formatPct(portfolioSummary.unrealized_pl_pct) : 'N/D',
      color: getVariationColor(portfolioSummary?.unrealized_pl_pct ?? 0),
      icon: IconArrowUpRight,
      iconColor: 'green' as const,
    },
    {
      label: 'Var. Giornaliera',
      value: portfolioSummary
        ? `${formatMoney(portfolioSummary.day_change, mvpCurrency, true)} (${formatPct(portfolioSummary.day_change_pct)})`
        : 'N/D',
      color: getVariationColor(portfolioSummary?.day_change ?? 0),
      icon: IconArrowUpRight,
      iconColor: 'orange' as const,
    },
    {
      label: 'Cash',
      value: portfolioSummary ? formatMoney(portfolioSummary.cash_balance, mvpCurrency) : 'N/D',
      icon: IconCoin,
      iconColor: 'grape' as const,
    },
  ], [portfolioSummary, mvpCurrency]);

  const chartStats = mvpTimeseriesStats
    ? [
        { label: '', value: formatMoney(mvpTimeseriesStats.last, mvpCurrency), color: 'blue' },
        { label: 'Var', value: formatPct(mvpTimeseriesStats.pct), color: getVariationColor(mvpTimeseriesStats.pct) },
      ]
    : undefined;

  const isPortfolioIntraday = chartWindow === '1';

  const portfolioChartData = useMemo(() => {
    if (!isPortfolioIntraday) return mvpTimeseriesData;
    const currentValue = Number(portfolioSummary?.market_value ?? 0);
    const points = mainIntradayChartData;
    if (!Number.isFinite(currentValue) || currentValue <= 0 || !points.length) return [];
    const lastIndex = Number(points[points.length - 1]?.value ?? 0);
    if (!Number.isFinite(lastIndex) || lastIndex <= 0) return [];
    return points.map((p) => ({
      ...p,
      value: currentValue * (Number(p.value) / lastIndex),
    }));
  }, [isPortfolioIntraday, mvpTimeseriesData, portfolioSummary?.market_value, mainIntradayChartData]);

  const portfolioChartStats = useMemo(() => {
    const series = portfolioChartData;
    if (!series.length) return undefined;
    const first = Number(series[0]?.value ?? 0);
    const last = Number(series[series.length - 1]?.value ?? 0);
    if (!Number.isFinite(last)) return undefined;
    const pct = Number.isFinite(first) && first > 0 ? ((last / first) - 1) * 100 : 0;
    return [
      { label: '', value: formatMoney(last, mvpCurrency), color: 'blue' },
      { label: 'Var', value: formatPct(pct), color: getVariationColor(pct) },
    ];
  }, [portfolioChartData, mvpCurrency]);

  const allocationDoughnutData = useMemo<AllocationDoughnutItem[]>(
    () => portfolioAllocation.map((item) => ({ name: item.symbol, value: item.weight_pct, asset_id: item.asset_id })),
    [portfolioAllocation],
  );

  const { best, worst } = useMemo(() => {
    const assets = assetPerformance?.assets ?? [];
    if (assets.length) {
      const sorted = [...assets].sort((a, b) => b.return_pct - a.return_pct);
      const bestItems: PerformerItem[] = sorted.slice(0, 3).map((a) => ({
        symbol: a.symbol, name: a.name, return_pct: a.return_pct, as_of: a.as_of, asset_id: a.asset_id,
      }));
      const worstItems: PerformerItem[] = sorted.slice(-3).reverse().map((a) => ({
        symbol: a.symbol, name: a.name, return_pct: a.return_pct, as_of: a.as_of, asset_id: a.asset_id,
      }));
      return { best: bestItems, worst: worstItems };
    }
    const b = targetPerformance?.best;
    const w = targetPerformance?.worst;
    return {
      best: b ? [{ symbol: b.symbol, name: b.name, return_pct: b.return_pct, as_of: b.as_of, asset_id: b.asset_id }] : [],
      worst: w ? [{ symbol: w.symbol, name: w.name, return_pct: w.return_pct, as_of: w.as_of, asset_id: w.asset_id }] : [],
    };
  }, [assetPerformance, targetPerformance]);

  const totalAllocationPct = portfolioAllocation.reduce((sum, item) => sum + item.weight_pct, 0);
  const bestWorstPeriodLabel = chartWindow === '1' ? '1g' : `${chartWindowDays}g`;

  const insufficientAssets = useMemo(
    () => (dataCoverage?.assets ?? []).filter((a) => a.coverage_pct < (dataCoverage?.threshold_pct ?? 80)),
    [dataCoverage],
  );

  return (
    <>
      {dataCoverage && !dataCoverage.sufficient && insufficientAssets.length > 0 && (
        <Alert
          color="yellow"
          icon={<IconAlertTriangle size={18} />}
          title="Dati storici insufficienti"
          mb="md"
        >
          Alcuni asset hanno una copertura dati insufficiente per i grafici:{' '}
          {insufficientAssets.map((a) => `${a.symbol} (${a.coverage_pct.toFixed(0)}%)`).join(', ')}.
          Premi il pulsante &quot;Aggiorna&quot; per scaricare lo storico prezzi.
        </Alert>
      )}

      <KpiStatsGrid items={kpiItems} />

      <div style={{ marginTop: 16 }}>
        <PerformanceChart
          title={`Andamento Portafoglio (${chartWindow === '1' ? '1g' : `${chartWindowDays}g`})`}
          data={portfolioChartData}
          xKey={isPortfolioIntraday ? 'time' : 'date'}
          gradientId="mvpTimeseriesGradient"
          color="#16a34a"
          stats={portfolioChartStats ?? chartStats}
          loading={isPortfolioIntraday ? mainIntradayLoading : false}
          emptyMessage={isPortfolioIntraday ? 'Nessun dato intraday disponibile per oggi' : 'Nessun dato disponibile'}
          subtitle={isPortfolioIntraday
            ? 'Stima intraday del controvalore (scalata su indice target intraday)'
            : 'Calcolato da transazioni + storico prezzi'}
          headerRight={
            <SegmentedControl
              size="xs"
              value={chartWindow}
              onChange={setChartWindow}
              data={DASHBOARD_WINDOWS.map((w) => ({ label: w.label, value: w.value }))}
            />
          }
          tooltipContent={({ active, payload, label }: any) => {
            if (!active || !payload?.length) return null;
            const value = Number(payload[0]?.value ?? 0);
            if (!Number.isFinite(value)) return null;
            return (
              <Paper withBorder p="xs" radius="sm" shadow="xs">
                <Text size="xs" c="dimmed">{isPortfolioIntraday ? `Ora ${label}` : `Data ${label}`}</Text>
                <Text size="sm" fw={600}>{formatMoney(value, mvpCurrency)}</Text>
              </Paper>
            );
          }}
        />
      </div>

      <Grid gutter="md" mt="md">
        <Grid.Col span={{ base: 12, md: 7 }}>
          <BestWorstCards best={best} worst={worst} periodLabel={bestWorstPeriodLabel} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <AllocationDoughnut
            title="Allocazione Portafoglio"
            data={allocationDoughnutData}
            centerLabel={totalAllocationPct > 0 ? `${totalAllocationPct.toFixed(0)}%` : '0%'}
          />
        </Grid.Col>
      </Grid>
    </>
  );
}
