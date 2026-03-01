import { useMemo } from 'react';
import { Card, Grid, Paper, SegmentedControl, Text } from '@mantine/core';
import { AnalysisKpiGrid } from '../analysis/AnalysisKpiGrid';
import { PerformanceMetrics } from '../analysis/PerformanceMetrics';
import { PerformanceChart } from '../summary/PerformanceChart';
import { AssetMiniChartsGrid } from '../analysis/AssetMiniChartsGrid';
import { AllocationDoughnut } from '../summary/AllocationDoughnut';
import { PerformersTable } from '../analysis/PerformersTable';
import { IntradayModal } from '../analysis/IntradayModal';
import { DASHBOARD_WINDOWS } from '../constants';
import { formatPct, getVariationColor } from '../formatters';
import type { DashboardData, AllocationDoughnutItem, PerformerItem } from '../types';

interface AnalisiTabProps {
  data: DashboardData;
}

export function AnalisiTab({ data }: AnalisiTabProps) {
  const {
    allocation,
    portfolioSummary,
    targetPerformance,
    selectedPortfolio,
    chartWindow,
    setChartWindow,
    chartData,
    mainIntradayChartData,
    mainIntradayLoading,
    assetMiniCharts,
    assetIntradayLoading,
    chartWindowDays,
    indexCardStats,
    mainChartStats,
    handleDailyChartClick,
    intradayOpen,
    setIntradayOpen,
    intradayLoading,
    intradayError,
    intradayChartData,
    intradayStats,
    intradayDateLabel,
    mvpCurrency,
  } = data;

  const totalAssignedWeight = allocation.reduce((sum, item) => sum + item.weight_pct, 0);

  const targetAllocationData = useMemo<AllocationDoughnutItem[]>(
    () => allocation.map((item) => ({ name: item.symbol, value: item.weight_pct, asset_id: item.asset_id })),
    [allocation],
  );

  const performerStats = useMemo(() => {
    const computed = assetMiniCharts
      .map((asset) => {
        const values = asset.chart
          .map((p) => Number(p.value))
          .filter((v) => Number.isFinite(v));
        if (values.length < 2) return null;
        const first = values[0];
        const last = values[values.length - 1];
        if (!Number.isFinite(first) || !Number.isFinite(last) || first <= 0) return null;
        const returnPct = ((last / first) - 1) * 100;
        return {
          symbol: asset.symbol,
          name: asset.name,
          return_pct: returnPct,
          as_of: asset.as_of,
          asset_id: asset.asset_id,
        } satisfies PerformerItem;
      })
      .filter(Boolean) as PerformerItem[];

    if (!computed.length) {
      return { best: null as PerformerItem | null, worst: null as PerformerItem | null, rows: [] as PerformerItem[] };
    }

    const sorted = [...computed].sort((a, b) => b.return_pct - a.return_pct);
    const best = sorted[0] ?? null;
    const worst = sorted[sorted.length - 1] ?? null;
    const rows = best && worst && best.asset_id !== worst.asset_id ? [best, worst] : best ? [best] : [];
    return { best, worst, rows };
  }, [assetMiniCharts]);

  const isIntraday = chartWindow === '1';
  const activeChartData = isIntraday ? mainIntradayChartData : chartData;
  const chartXKey = isIntraday ? 'time' : 'date';

  const chartStats = mainChartStats
    ? [
        { label: 'Indice', value: mainChartStats.last.toFixed(2), color: 'blue' },
        { label: 'Var', value: formatPct(mainChartStats.periodPct), color: getVariationColor(mainChartStats.periodPct) },
      ]
    : undefined;

  const renderIndexTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const rawValue = Number(payload[0]?.value ?? 0);
    if (!Number.isFinite(rawValue)) return null;
    const pct = ((rawValue / 100) - 1) * 100;
    return (
      <Paper withBorder p="xs" radius="sm" shadow="xs">
        <Text size="xs" c="dimmed">{isIntraday ? `Ora ${label}` : `Data ${label}`}</Text>
        <Text size="sm" fw={600}>Indice: {rawValue.toFixed(2)}</Text>
        <Text size="sm" c={getVariationColor(pct)} fw={500}>Variazione: {formatPct(pct)}</Text>
      </Paper>
    );
  };

  return (
    <>
      <PerformanceMetrics portfolioId={selectedPortfolio?.id ?? null} />

      <AnalysisKpiGrid
        indexCardStats={indexCardStats}
        totalAssignedWeight={totalAssignedWeight}
        allocation={allocation}
        selectedPortfolio={selectedPortfolio}
        portfolioSummary={portfolioSummary}
        currency={mvpCurrency}
        bestPerformer={performerStats.best}
        worstPerformer={performerStats.worst}
      />

      <div style={{ marginTop: 16 }}>
        <PerformanceChart
          title="Indice Target (media pesata, base 100)"
          data={activeChartData}
          xKey={chartXKey}
          gradientId={isIntraday ? 'colorValueIntradayMain' : 'colorValue'}
          color="#228be6"
          height={300}
          loading={isIntraday ? mainIntradayLoading : false}
          emptyMessage={isIntraday ? 'Nessun dato intraday disponibile per oggi' : 'Nessun dato storico disponibile'}
          onClick={!isIntraday ? handleDailyChartClick : undefined}
          stats={chartStats}
          tooltipContent={renderIndexTooltip}
          headerRight={
            <SegmentedControl
              size="xs"
              value={chartWindow}
              onChange={setChartWindow}
              data={DASHBOARD_WINDOWS.map((w) => ({ label: w.label, value: w.value }))}
            />
          }
        />
      </div>

      <Card withBorder radius="md" p="md" mt="md" shadow="sm">
        <Text fw={500} mb="md">
          Andamento per Titolo ({chartWindowDays === 1 ? 'oggi' : `ultimi ${chartWindowDays} giorni`})
        </Text>
        <AssetMiniChartsGrid
          assets={assetMiniCharts}
          chartWindow={chartWindow}
          assetIntradayLoading={assetIntradayLoading}
        />
      </Card>

      <Grid gutter="md" mt="md">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <AllocationDoughnut
            title="Allocazione Target"
            data={targetAllocationData}
            centerLabel={totalAssignedWeight > 0 ? `${Math.round(totalAssignedWeight)}%` : '0%'}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card withBorder radius="md" p={0} shadow="sm">
            <PerformersTable performers={performerStats.rows} />
          </Card>
        </Grid.Col>
      </Grid>

      <IntradayModal
        opened={intradayOpen}
        onClose={() => setIntradayOpen(false)}
        dateLabel={intradayDateLabel}
        loading={intradayLoading}
        error={intradayError}
        chartData={intradayChartData}
        stats={intradayStats}
      />
    </>
  );
}
