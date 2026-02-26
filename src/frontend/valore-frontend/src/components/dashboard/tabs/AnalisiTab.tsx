import { useMemo } from 'react';
import { Card, Grid, Paper, SegmentedControl, Text } from '@mantine/core';
import { AnalysisKpiGrid } from '../analysis/AnalysisKpiGrid';
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

  const performers = useMemo<PerformerItem[]>(() => {
    const best = targetPerformance?.best;
    const worst = targetPerformance?.worst;
    return [best, worst].filter(Boolean).map((p) => ({
      symbol: p!.symbol,
      name: p!.name,
      return_pct: p!.return_pct,
      as_of: p!.as_of,
      asset_id: p!.asset_id,
    }));
  }, [targetPerformance]);

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
      <AnalysisKpiGrid
        indexCardStats={indexCardStats}
        totalAssignedWeight={totalAssignedWeight}
        targetPerformance={targetPerformance}
        allocation={allocation}
        selectedPortfolio={selectedPortfolio}
        portfolioSummary={portfolioSummary}
        currency={mvpCurrency}
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
            <PerformersTable performers={performers} />
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
